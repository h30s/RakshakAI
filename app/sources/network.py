"""Reaching this computer from a phone: LAN address, HTTPS certificate, pairing token, adb."""
import datetime
import ipaddress
import logging
import os
import secrets
import shutil
import socket
import subprocess
from pathlib import Path

from .. import config

log = logging.getLogger(__name__)

# Required (with the QR code's link) for a device on the network to send video. Phones that
# scanned the current QR code have it; it changes on every server start.
PAIRING_TOKEN = secrets.token_urlsafe(9)


def lan_ip():
    """This computer's address on the local network (the interface with the default route)."""
    if config.PHONE_HOST:
        return config.PHONE_HOST
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # no packet is sent; this just picks the interface
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def is_loopback(host):
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


def ensure_certificate(host):
    """A self-signed certificate for `host` (reused while the address stays the same).

    Phones only allow camera access on HTTPS pages. Without a public domain the certificate
    can't be trusted automatically, so the phone shows a warning once that the user accepts."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    cert_path, key_path = config.CERT_DIR / "phone.crt", config.CERT_DIR / "phone.key"
    if cert_path.exists() and key_path.exists():
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        try:
            names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
            ips = {str(ip) for ip in names.get_values_for_type(x509.IPAddress)}
        except x509.ExtensionNotFound:
            ips = set()
        if host in ips and cert.not_valid_after_utc > datetime.datetime.now(datetime.timezone.utc):
            return cert_path, key_path

    config.CERT_DIR.mkdir(exist_ok=True)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "CCTV Monitor (local)")])
    now = datetime.datetime.now(datetime.timezone.utc)
    alt = [x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
    try:
        alt.append(x509.IPAddress(ipaddress.ip_address(host)))
    except ValueError:
        alt.append(x509.DNSName(host))
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=825))
            .add_extension(x509.SubjectAlternativeName(alt), critical=False)
            .sign(key, hashes.SHA256()))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    log.info("Created a self-signed certificate for %s in %s", host, config.CERT_DIR)
    return cert_path, key_path


# ---------- Phone over USB (Android, adb) ----------

def find_adb():
    candidates = [shutil.which("adb")]
    for base in (os.getenv("ANDROID_HOME"), os.getenv("ANDROID_SDK_ROOT"),
                 os.path.join(os.getenv("LOCALAPPDATA", ""), "Android", "Sdk")):
        if base:
            candidates.append(str(Path(base) / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb")))
    return next((c for c in candidates if c and Path(c).exists()), None)


def connect_phone_over_usb(port, path):
    """Forward the phone's localhost:<port> to this server over the USB cable (adb reverse) and
    open the camera page on the phone. localhost counts as secure, so no certificate is needed.
    Returns (ok, message)."""
    adb = find_adb()
    if not adb:
        return False, "adb (Android platform-tools) was not found on this computer."

    def run(*args):
        return subprocess.run([adb, *args], capture_output=True, text=True, timeout=15)

    try:
        devices = [line.split("\t") for line in run("devices").stdout.splitlines()[1:] if "\t" in line]
        ready = [d for d, state in devices if state == "device"]
        if not ready:
            if any(state == "unauthorized" for _, state in devices):
                return False, "The phone is connected but not authorised: accept the USB debugging prompt on it."
            return False, "No Android phone found. Connect it with a USB cable and turn on USB debugging."
        serial = ready[0]
        rev = run("-s", serial, "reverse", f"tcp:{port}", f"tcp:{port}")
        if rev.returncode:
            return False, f"adb reverse failed: {(rev.stderr or rev.stdout).strip()}"
        url = f"http://localhost:{port}{path}"
        run("-s", serial, "shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url)
        return True, f"Opened {url} on the phone ({serial}). Tap Start camera there."
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"adb failed: {e}"
