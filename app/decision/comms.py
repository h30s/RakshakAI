"""Duty-phone alerts through a USB GSM modem: one signed SMS per alert, a voice call, a siren.

No data connection is needed: plain SMS and voice work on 2G. Every alert's SMS already carries
its Ed25519 signature (ledger.sms_alert), so the duty phone and Sector HQ can check it was sent by
this post and not changed on the way.

Configure in post.json:

    "comms": {
      "modem": "/dev/ttyUSB2",          # or "COM5"; the modem's AT-command port
      "baud": 115200,
      "duty_phones": ["+91XXXXXXXXXX"],  # keep real numbers out of git (data/ is ignored)
      "call_for": "critical",           # "critical", "all" or "none"
      "voice_clip": "alert_hi.amr",      # optional: Hindi audio stored on the modem, played in the call
      "siren": {"port": "/dev/ttyUSB0", "on": "A00101A2", "off": "A00100A1", "seconds": 20}
    }

The siren defaults are for the common single-channel USB serial relay (LCUS-1); change them for
other relays. Voice playback uses AT+CCMXPLAY (SIMCom SIM7600 family); other modems ring only.
Untested on hardware so far: see CLAIMS.md (A3).
"""
import logging
import queue
import threading
import time

log = logging.getLogger(__name__)

CRITICAL_PREFIXES = ("Watchlist", "Fence crossing while", "Virtual-fence breach", "FRS hit", "ANPR hit", "WATCHLIST hit")


class ModemError(RuntimeError):
    pass


class Modem:
    """Minimal AT-command driver. `port` is anything with write(bytes), read(n) and timeout,
    for example serial.Serial (pyserial)."""

    def __init__(self, port, timeout=10.0):
        self.port, self.timeout = port, timeout
        self.lock = threading.Lock()

    @classmethod
    def open(cls, device, baud=115200):
        import serial  # pyserial, only needed on the edge box
        return cls(serial.Serial(device, baud, timeout=0.2))

    def _read_until(self, *endings, timeout=None):
        deadline, buf = time.monotonic() + (timeout or self.timeout), b""
        while time.monotonic() < deadline:
            buf += self.port.read(256) or b""
            text = buf.decode(errors="replace")
            for e in endings:
                if e in text:
                    return text
            if "ERROR" in text:
                raise ModemError(text.strip())
        raise ModemError(f"no {' / '.join(endings)} from modem; got {buf!r}")

    def command(self, cmd, expect="OK", timeout=None):
        self.port.write((cmd + "\r").encode())
        return self._read_until(expect, timeout=timeout)

    def send_sms(self, number, text):
        """Send one GSM-7 text SMS; returns when the network accepted it (+CMGS)."""
        if len(text) > 160:
            raise ValueError("an alert SMS must fit in 160 characters")
        with self.lock:
            self.command("AT")
            self.command("AT+CMGF=1")
            self.port.write(f'AT+CMGS="{number}"\r'.encode())
            self._read_until(">")
            self.port.write(text.encode("ascii", "replace") + b"\x1a")
            return self._read_until("+CMGS", timeout=60)

    def call(self, number, ring_s=25, clip=None):
        """Ring the duty phone; play a stored audio clip if the modem supports it; hang up."""
        with self.lock:
            self.command(f"ATD{number};", timeout=20)
            if clip:
                try:
                    self.command(f'AT+CCMXPLAY="{clip}",1,0', timeout=5)
                except ModemError as exc:
                    log.info("Voice clip not played (%s); ringing only", exc)
            time.sleep(ring_s)
            self.command("ATH")


class Siren:
    """Serial relay that switches the post siren on for a few seconds."""

    def __init__(self, port, on, off, seconds=20):
        self.port, self.on, self.off, self.seconds = port, bytes.fromhex(on), bytes.fromhex(off), seconds

    @classmethod
    def open(cls, cfg):
        import serial
        return cls(serial.Serial(cfg["port"], cfg.get("baud", 9600), timeout=1),
                   cfg.get("on", "A00101A2"), cfg.get("off", "A00100A1"), cfg.get("seconds", 20))

    def sound(self):
        self.port.write(self.on)
        time.sleep(self.seconds)
        self.port.write(self.off)


def is_critical(alert):
    return alert.get("source", "rakshak") != "rakshak" or alert["reason"].startswith(CRITICAL_PREFIXES)


class Dispatcher(threading.Thread):
    """Queue of alerts to send. Each alert: an SMS to every duty phone (retried until the modem
    accepts it), then a call and the siren for critical alerts. engine.notifiers.append(d.notify)."""

    def __init__(self, engine, modem, phones, call_for="critical", voice_clip=None, siren=None, retry_s=30):
        super().__init__(daemon=True, name="comms")
        self.engine, self.modem, self.phones = engine, modem, phones
        self.call_for, self.voice_clip, self.siren, self.retry_s = call_for, voice_clip, siren, retry_s
        self.q = queue.Queue()
        self.status = {"sent": 0, "failed_attempts": 0, "queued": 0, "last_error": None}

    @classmethod
    def from_config(cls, engine, cfg):
        modem = Modem.open(cfg["modem"], cfg.get("baud", 115200))
        siren = Siren.open(cfg["siren"]) if cfg.get("siren") else None
        return cls(engine, modem, cfg.get("duty_phones", []), cfg.get("call_for", "critical"),
                   cfg.get("voice_clip"), siren)

    def notify(self, alert):
        self.q.put(alert)
        self.status["queued"] = self.q.qsize()

    def send(self, alert, phones):
        """SMS the alert to `phones`; returns the numbers still to do (the network refused them)."""
        left = []
        for number in phones:
            try:
                self.modem.send_sms(number, alert["sms"])
                self.status["sent"] += 1
                self.engine.delivered(alert["id"], "sms")  # the first phone reached sets the SMS latency
            except Exception as exc:
                left.append(number)
                self.status.update(failed_attempts=self.status["failed_attempts"] + 1, last_error=str(exc))
                log.warning("SMS for %s to a duty phone failed: %s", alert["id"], exc)
        return left

    def call(self, alert):
        for number in self.phones:
            try:
                self.modem.call(number, clip=self.voice_clip)
            except Exception as exc:
                log.warning("Call for %s failed: %s", alert["id"], exc)

    def handle(self, alert, sleep=time.sleep):
        critical = is_critical(alert)
        if self.siren and critical:  # local: never waits for the mobile network
            threading.Thread(target=self.siren.sound, daemon=True).start()
        left = list(self.phones)
        while left:  # store-and-forward: keep trying the phones the network has not taken yet
            left = self.send(alert, left)
            if left:
                sleep(self.retry_s)
        if self.call_for == "all" or (self.call_for == "critical" and critical):
            self.call(alert)

    def run(self):
        while True:
            alert = self.q.get()
            self.handle(alert)
            self.status["queued"] = self.q.qsize()
