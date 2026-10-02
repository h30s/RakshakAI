"""Tests for the duty-phone dispatcher, the GSM modem driver, C2 feeds, Border Pulse and the API."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.decision import api as decision_api
from app.decision.c2 import MqttFeed
from app.decision.comms import Dispatcher, Modem, ModemError, is_critical
from app.decision.engine import DecisionEngine
from app.decision.events import Movement
from app.decision.ledger import verify_sms
from app.decision.pulse import pulse

T0 = dt.datetime(2026, 8, 4, 10, 0).timestamp()


class FakePort:
    """A serial port that answers like a GSM modem."""

    def __init__(self, fail_sms=False):
        self.written, self.out, self.fail_sms = [], b"", fail_sms

    def write(self, data):
        self.written.append(data)
        if data.endswith(b"\x1a"):
            self.out += b"\r\nERROR\r\n" if self.fail_sms else b"\r\n+CMGS: 17\r\n\r\nOK\r\n"
        elif data.startswith(b"AT+CMGS"):
            self.out += b"\r\n> "
        else:
            self.out += b"\r\nOK\r\n"

    def read(self, n):
        chunk, self.out = self.out[:n], self.out[n:]
        return chunk


class FakeModem:
    def __init__(self, down=0):
        self.sms, self.calls, self.down = [], [], down  # `down`: refuse this many SMS first

    def send_sms(self, number, text):
        if self.down:
            self.down -= 1
            raise ModemError("no network")
        self.sms.append((number, text))

    def call(self, number, clip=None):
        self.calls.append(number)


def engine(tmp):
    (tmp / "post.json").write_text(json.dumps({"post_id": "BOP07"}))
    return DecisionEngine(tmp, {"cam-1": "Gate"})


class ModemTest(unittest.TestCase):
    def test_at_commands_for_one_sms(self):
        port = FakePort()
        Modem(port, timeout=1).send_sms("+910000000000", "RK1 test")
        self.assertEqual(port.written[:3], [b"AT\r", b"AT+CMGF=1\r", b'AT+CMGS="+910000000000"\r'])
        self.assertEqual(port.written[3], b"RK1 test\x1a")
        with self.assertRaises(ModemError):
            Modem(FakePort(fail_sms=True), timeout=1).send_sms("+910000000000", "RK1 test")
        with self.assertRaises(ValueError):
            Modem(FakePort(), timeout=1).send_sms("+91", "x" * 161)


class DispatcherTest(unittest.TestCase):
    def test_sms_every_phone_retries_only_the_failed_and_calls_for_critical(self):
        with tempfile.TemporaryDirectory() as tmp:
            eng = engine(Path(tmp))
            modem = FakeModem(down=1)  # the first SMS attempt fails
            d = Dispatcher(eng, modem, ["+911", "+912"], call_for="critical", retry_s=0)
            a = eng.external_hit("anpr", "cam-1", "UP32AB1234", t=T0)
            self.assertTrue(is_critical(a))
            d.handle(a, sleep=lambda s: None)
            self.assertEqual(sorted(n for n, _ in modem.sms), ["+911", "+912"])  # each phone exactly once
            self.assertTrue(all(verify_sms(text, eng.ledger.key.public_key()) for _, text in modem.sms))
            self.assertEqual(modem.calls, ["+911", "+912"])
            self.assertIn("sms", eng._find(a["id"])["latency"])


class C2Test(unittest.TestCase):
    def test_mqtt_publishes_each_sealed_entry(self):
        class Client:
            def __init__(self):
                self.msgs = []

            def publish(self, topic, payload, qos):
                self.msgs.append((topic, json.loads(payload), qos))

        with tempfile.TemporaryDirectory() as tmp:
            eng = engine(Path(tmp))
            client = Client()
            eng.ledger.listeners.append(MqttFeed(client, "BOP07"))
            a = eng.external_hit("frs", "cam-1", "W-07", t=T0)
            eng.set_status(a["id"], "escalated")
            self.assertEqual([m[0] for m in client.msgs], ["rakshak/BOP07/alert", "rakshak/BOP07/action"])
            self.assertEqual(client.msgs[0][1]["hash"], eng.ledger.entries[0]["hash"])
            self.assertEqual(client.msgs[0][2], 1)

    def test_a_failing_listener_never_blocks_sealing(self):
        with tempfile.TemporaryDirectory() as tmp:
            eng = engine(Path(tmp))
            eng.ledger.listeners.append(lambda e: 1 / 0)
            eng.external_hit("frs", "cam-1", "W-07", t=T0)
            self.assertEqual(len(eng.ledger.entries), 1)


class PulseTest(unittest.TestCase):
    def test_new_path_peak_and_repeat_crosser(self):
        now = T0 + 35 * 86400
        old = [Movement("cam-1", T0 + d * 86400 + 9 * 3600, 0, "r2c0", "r2c3") for d in range(28)]
        new = [Movement("cam-1", now - 86400 * k - 9 * 3600, 0, "r0c1", "r2c3", crossed=True, person="P-9")
               for k in (1, 1, 1, 2)]
        p = pulse(old + new, now)["cameras"][0]
        self.assertEqual(p["new_paths"], [{"path": "r0c1>r2c3", "count": 4}])
        self.assertTrue(p["peak_shifted"])
        self.assertEqual(p["repeat_crossers"][0]["crossings"], 3)
        self.assertEqual(p["night"], 4)


class ApiTest(unittest.TestCase):
    def test_endpoints_and_live_push(self):
        with tempfile.TemporaryDirectory() as tmp:
            eng = engine(Path(tmp))
            decision_api.engine = eng
            app = FastAPI()
            app.include_router(decision_api.router)
            client = TestClient(app)
            hit = client.post("/api/decision/external-hits",
                              json={"source": "anpr", "camera": "cam-1", "label": "UP32AB1234", "confidence": 0.9}).json()
            self.assertEqual(hit["reason"], "ANPR hit: UP32AB1234 (90%)")
            r = client.post(f"/api/decision/alerts/{hit['id']}/delivered", json={"channel": "console"}).json()
            self.assertIn("console", r["latency"])
            self.assertEqual(client.get("/api/decision/latency").json()["console"]["n"], 1)
            pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(client.get("/api/decision/pubkey").text))
            self.assertTrue(verify_sms(hit["sms"], pub))
            self.assertEqual(client.get("/api/decision/shift-report").json()["alerts"][0]["id"], hit["id"])
            self.assertIn("cameras", client.get("/api/decision/pulse").json())
            with client.websocket_connect("/ws/decision") as ws:
                self.assertEqual(ws.receive_json()["alerts"][0]["id"], hit["id"])
            with client.websocket_connect("/ws/c2?from_seq=0") as ws:
                self.assertEqual(ws.receive_json()["kind"], "alert")
            self.assertEqual(client.post("/api/decision/external-hits",
                                         json={"source": "anpr", "camera": "c", "label": "x", "confidence": 2}).status_code, 422)
            eng.cfg["integration_token"] = "s3cret"
            hit = {"source": "frs", "camera": "cam-1", "label": "W-1"}
            self.assertEqual(client.post("/api/decision/external-hits", json=hit).status_code, 401)
            self.assertEqual(client.post("/api/decision/external-hits", json=hit,
                                         headers={"X-Rakshak-Token": "s3cret"}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
