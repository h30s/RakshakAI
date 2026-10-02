"""Tests for the Egress Guard log summary (scripts/egress_summary.py)."""
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("egress_summary", Path(__file__).resolve().parent.parent / "scripts" / "egress_summary.py")
egress = importlib.util.module_from_spec(spec)
spec.loader.exec_module(egress)

KERN = [
    "Oct 02 10:00:01 box kernel: RK-EGRESS IN=cam0 OUT=enp1s0 MAC=aa SRC=192.168.50.120 DST=47.91.1.9 LEN=60 TOS=0x00 "
    "PREC=0x00 TTL=63 ID=1 DF PROTO=TCP SPT=40312 DPT=443 WINDOW=64240 RES=0x00 SYN URGP=0",
    "Oct 02 10:00:05 box kernel: RK-EGRESS IN=cam0 OUT=enp1s0 MAC=aa SRC=192.168.50.120 DST=47.91.1.9 LEN=60 PROTO=TCP SPT=40313 DPT=443",
    "Oct 02 10:01:00 box kernel: RK-EGRESS IN=cam0 OUT=enp1s0 MAC=aa SRC=192.168.50.120 DST=162.159.200.1 LEN=76 PROTO=UDP SPT=123 DPT=123 LEN=56",
    "Oct 02 10:02:00 box kernel: RK-EGRESS-BOX IN=cam0 OUT= MAC=aa SRC=192.168.50.120 DST=192.168.50.1 LEN=60 PROTO=TCP SPT=5000 DPT=22",
    "Oct 02 10:03:00 box kernel: usb 1-1: new high-speed USB device",
]
DNS = [
    "Oct  2 10:00:00 dnsmasq[812]: query[A] p2p.example-cam.com from 192.168.50.120",
    "Oct  2 10:00:00 dnsmasq[812]: config p2p.example-cam.com is 0.0.0.0",
    "Oct  2 10:05:00 dnsmasq[812]: query[A] fw.example-cam.com from 192.168.50.120",
    "Oct  2 10:06:00 dnsmasq[812]: query[AAAA] P2P.example-cam.com from 192.168.50.121",
]


class EgressSummaryTest(unittest.TestCase):
    def test_counts(self):
        s = egress.parse(KERN, DNS)
        self.assertEqual(s["outbound_attempts"], 3)
        self.assertEqual(s["distinct_destinations"], 2)
        self.assertEqual(s["attempts_to_box_services"], 1)
        self.assertEqual(s["blocked"], 3)
        self.assertEqual(s["dns_lookups"], 3)
        self.assertEqual(s["distinct_names"], ["fw.example-cam.com", "p2p.example-cam.com"])
        self.assertEqual(s["cameras"]["192.168.50.120"]["attempts"], 3)
        self.assertIn("3 attempts", egress.report(s))


if __name__ == "__main__":
    unittest.main()
