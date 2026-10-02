"""Summarise an Egress Guard capture: what the cameras tried to reach, and that none of it got out.

    journalctl -k --since "24 hours ago" > kern.log
    python scripts/egress_summary.py --kern kern.log --dns /var/log/rakshak/dnsmasq.log [--json out.json]

Reads the kernel log lines the firewall writes (prefix "RK-EGRESS ") for every new outbound
connection a camera tried, and the dnsmasq log for every name a camera looked up. Reports
attempts, distinct destinations and names, per camera. "Reached the internet" is the number of
camera connections the firewall forwarded: the camera port's forward rule drops everything, so the
kernel log is checked for forwarded camera traffic and `nft list counter` is quoted for the record.
Report the numbers you get; they depend on the camera model and firmware.
"""
import argparse
import json
import re
import subprocess
from collections import Counter, defaultdict

KERN = re.compile(r"RK-EGRESS(?P<box>-BOX)? .*?SRC=(?P<src>[\d.:a-fA-F]+) DST=(?P<dst>[\d.:a-fA-F]+).*?PROTO=(?P<proto>\w+)"
                  r"(?:.*?DPT=(?P<dpt>\d+))?")
DNS = re.compile(r"query\[(?P<type>\w+)\] (?P<name>\S+) from (?P<src>[\d.:a-fA-F]+)")


def parse(kern_lines, dns_lines):
    attempts, to_box = [], []
    for line in kern_lines:
        m = KERN.search(line)
        if m:
            (to_box if m["box"] else attempts).append((m["src"], m["dst"], m["proto"], m["dpt"]))
    lookups = [(m["src"], m["name"].lower()) for m in map(DNS.search, dns_lines) if m]
    cameras = defaultdict(lambda: {"attempts": 0, "destinations": Counter(), "names": Counter()})
    for src, dst, proto, dpt in attempts:
        cameras[src]["attempts"] += 1
        cameras[src]["destinations"][f"{dst}:{dpt or proto.lower()}"] += 1
    for src, name in lookups:
        cameras[src]["names"][name] += 1
    return {
        "outbound_attempts": len(attempts),
        "distinct_destinations": len({(a[1], a[3]) for a in attempts}),
        "dns_lookups": len(lookups),
        "distinct_names": sorted({n for _, n in lookups}),
        "attempts_to_box_services": len(to_box),
        "blocked": len(attempts),
        "cameras": {ip: {"attempts": c["attempts"], "top_destinations": c["destinations"].most_common(10),
                         "names": c["names"].most_common(20)} for ip, c in sorted(cameras.items())},
    }


def nft_counter():
    try:
        out = subprocess.run(["nft", "list", "counter", "inet", "rakshak_egress", "cam_blocked"],
                             capture_output=True, text=True, timeout=5).stdout
        return out.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def report(s):
    lines = [f"Outbound attempts by cameras ... {s['outbound_attempts']}  ->  {s['distinct_destinations']} destinations",
             f"DNS lookups .................... {s['dns_lookups']}  ->  {len(s['distinct_names'])} names",
             f"Blocked ........................ {s['blocked']} ({100 if s['outbound_attempts'] else 0}% of attempts; "
             f"forward policy for the camera port is drop)"]
    for ip, c in s["cameras"].items():
        lines.append(f"  camera {ip}: {c['attempts']} attempts; names: {', '.join(n for n, _ in c['names'][:8]) or '-'}")
    if s.get("nft_counter"):
        lines.append("nft counter: " + " ".join(s["nft_counter"].split()))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kern", required=True, help="kernel log (journalctl -k output)")
    ap.add_argument("--dns", help="dnsmasq log")
    ap.add_argument("--json", help="also write the summary here")
    args = ap.parse_args()
    with open(args.kern, encoding="utf-8", errors="replace") as f:
        kern = f.readlines()
    dns = []
    if args.dns:
        with open(args.dns, encoding="utf-8", errors="replace") as f:
            dns = f.readlines()
    s = parse(kern, dns)
    s["nft_counter"] = nft_counter()
    print(report(s))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2)


if __name__ == "__main__":
    main()
