"""Feeds for command-and-control systems: every sealed ledger entry, as it is written.

Consumers get exactly what Sector HQ gets - signed entries - so they can check each one with the
post's public key (GET /api/decision/pubkey) instead of trusting the transport.

* WebSocket: /ws/c2?from_seq=N (app/decision/api.py) replays from entry N, then streams live.
* MQTT: publish to <prefix>/<post>/<kind> (alert, action, anchor, ...), QoS 1, configured in
  post.json as "mqtt": {"host": "10.0.0.5", "port": 1883, "prefix": "rakshak"}. Needs paho-mqtt.
* REST: GET /api/decision/overview, /api/decision/shift-report, /api/decision/ledger/verify.

ONVIF Profile M metadata is not implemented yet (CLAIMS.md, A8).
"""
import json
import logging

log = logging.getLogger(__name__)


def topic(prefix, post, entry):
    return f"{prefix}/{post}/{entry['kind']}"


def payload(entry):
    return json.dumps(entry, ensure_ascii=False, separators=(",", ":"))


class MqttFeed:
    """Ledger listener that publishes each new entry. `client` is a connected paho-mqtt client
    (or anything with publish(topic, payload, qos))."""

    def __init__(self, client, post, prefix="rakshak"):
        self.client, self.post, self.prefix = client, post, prefix
        self.published = 0

    @classmethod
    def connect(cls, post, cfg):
        import paho.mqtt.client as mqtt  # optional dependency, only where an MQTT broker is used
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"rakshak-{post}")
        client.connect_async(cfg["host"], cfg.get("port", 1883))
        client.loop_start()  # reconnects by itself; QoS 1 messages queue while the broker is away
        return cls(client, post, cfg.get("prefix", "rakshak"))

    def __call__(self, entry):
        self.client.publish(topic(self.prefix, self.post, entry), payload(entry), qos=1)
        self.published += 1
