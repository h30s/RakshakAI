#!/usr/bin/env bash
# Rakshak AI edge-box installer (Debian 12 / Ubuntu 22.04+, Intel N100 or any x86-64 PC). Run as root
# from a copy of the repository:
#
#   sudo deploy/install-edge.sh [camera interface]      # e.g. enx00e04c680001; omit to skip Egress Guard
#
# Installs to /opt/rakshak, creates the 'rakshak' user, a Python venv with the runtime requirements
# (and OpenVINO), downloads and prepares the models, writes data/post.json from the example, and
# starts the service on port 8000. Time the whole run for the deck's "one-hour install" claim.
# NOT YET TESTED ON THE N100 BOX (CLAIMS.md, E4).
set -euo pipefail

if [[ $EUID -ne 0 ]]; then echo "Run as root (sudo)." >&2; exit 1; fi
SRC="$(cd "$(dirname "$0")/.." && pwd)"
DEST=/opt/rakshak
START=$(date +%s)

apt-get update
apt-get install -y python3 python3-venv python3-pip ffmpeg rsync

id rakshak >/dev/null 2>&1 || useradd --system --home "$DEST" --shell /usr/sbin/nologin rakshak
usermod -aG dialout rakshak   # serial access for the GSM modem and the siren relay
mkdir -p "$DEST"
rsync -a --delete --exclude .git --exclude data --exclude models --exclude videos --exclude .venv --exclude certs "$SRC/" "$DEST/"
mkdir -p "$DEST/data" "$DEST/models" "$DEST/videos" "$DEST/certs"

python3 -m venv "$DEST/.venv"
"$DEST/.venv/bin/pip" install --upgrade pip
"$DEST/.venv/bin/pip" install -r "$DEST/requirements.txt" openvino pyserial paho-mqtt
# Model preparation needs PyTorch and the export tools once; they stay in a separate venv.
python3 -m venv /tmp/rakshak-export
/tmp/rakshak-export/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
/tmp/rakshak-export/bin/pip install -r "$DEST/requirements.txt" -r "$DEST/requirements-export.txt" nncf openvino
(cd "$DEST" && /tmp/rakshak-export/bin/python scripts/fetch_assets.py --models-only \
            && /tmp/rakshak-export/bin/python scripts/quantize_openvino.py || echo "INT8 step skipped: needs videos/ for calibration")
rm -rf /tmp/rakshak-export

[[ -f "$DEST/data/post.json" ]] || cp "$DEST/config/post.example.json" "$DEST/data/post.json"
chown -R rakshak:rakshak "$DEST"
chmod 700 "$DEST/data"

install -m 644 "$DEST/deploy/rakshak.service" /etc/systemd/system/rakshak.service
systemctl daemon-reload
systemctl enable --now rakshak

if [[ -n "${1:-}" ]]; then "$DEST/deploy/egress-guard/install.sh" "$1"; fi

echo "Installed in $(( ($(date +%s) - START) / 60 )) minutes."
echo "Console: http://$(hostname -I | awk '{print $1}'):8000/decision"
echo "Edit $DEST/data/post.json (fences, zones, calendar, comms), then: systemctl restart rakshak"
echo "Register this post at HQ with: sudo -u rakshak $DEST/.venv/bin/python -m app.decision.verify --pubkey"
