#!/usr/bin/env bash
# Rakshak AI Egress Guard installer for the edge box (Debian / Ubuntu, run as root).
#
#   sudo ./install.sh <camera interface> [box address on that port, default 192.168.50.1]
#   sudo ./install.sh enx00e04c680001
#
# Puts the cameras on their own port with DHCP, DNS and time from the box, and blocks and logs
# every connection they try to make outwards. Undo: nft delete table inet rakshak_egress;
# rm /etc/dnsmasq.d/rakshak.conf; systemctl restart dnsmasq.
# NOT YET TESTED ON THE N100 BOX (see CLAIMS.md, S1). Test on a spare machine first.
set -euo pipefail

CAM_IF="${1:?usage: install.sh <camera interface> [box address]}"
BOX_IP="${2:-192.168.50.1}"
NET="${BOX_IP%.*}"
HERE="$(cd "$(dirname "$0")" && pwd)"

if [[ $EUID -ne 0 ]]; then echo "Run as root (sudo)." >&2; exit 1; fi
if ! ip link show "$CAM_IF" >/dev/null 2>&1; then echo "No interface $CAM_IF" >&2; exit 1; fi

apt-get install -y nftables dnsmasq chrony

# Camera port address
ip addr flush dev "$CAM_IF"
ip addr add "$BOX_IP/24" dev "$CAM_IF"
ip link set "$CAM_IF" up
cat > "/etc/systemd/network/10-rakshak-cam.network" <<EOF
[Match]
Name=$CAM_IF
[Network]
Address=$BOX_IP/24
EOF

# Forwarding stays on so that camera attempts reach the forward chain and are logged there.
sysctl -w net.ipv4.ip_forward=1 >/dev/null
echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/90-rakshak.conf

# Firewall
mkdir -p /etc/nftables.d
sed -e "s/\"cam0\"/\"$CAM_IF\"/" -e "s/192\.168\.50\.1/$BOX_IP/" "$HERE/rakshak-egress.nft" > /etc/nftables.d/rakshak-egress.nft
nft -f /etc/nftables.d/rakshak-egress.nft
grep -q rakshak-egress /etc/nftables.conf || echo 'include "/etc/nftables.d/rakshak-egress.nft"' >> /etc/nftables.conf
systemctl enable nftables

# DHCP + logging DNS sinkhole for the camera port only
mkdir -p /var/log/rakshak
sed -e "s/cam0/$CAM_IF/" -e "s/192\.168\.50\./$NET./g" "$HERE/dnsmasq-rakshak.conf" > /etc/dnsmasq.d/rakshak.conf
systemctl restart dnsmasq

# Time server for the cameras
grep -q "allow $NET.0/24" /etc/chrony/chrony.conf || sed -e "s/192\.168\.50\./$NET./" "$HERE/chrony-rakshak.conf" >> /etc/chrony/chrony.conf
systemctl restart chrony

echo "Egress Guard on $CAM_IF ($BOX_IP). Summary after a capture:"
echo "  journalctl -k --since '24 hours ago' > kern.log"
echo "  python scripts/egress_summary.py --kern kern.log --dns /var/log/rakshak/dnsmasq.log"
