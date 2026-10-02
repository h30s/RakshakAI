# Security scan report

Scanned on 2026-10-02 with **bandit 1.9.4** (static analysis of our Python code) and
**pip-audit 2.10.1** (known vulnerabilities in our dependencies). Raw output: `bandit.txt` and
`pip-audit.txt` in this folder. Re-run before every release:

```bash
pip install bandit pip-audit
python -m bandit -r app hq scripts benchmark -f txt -o docs/security-scan/bandit.txt
python -m pip_audit -r requirements.txt
```

## Results

| Check | Result |
|---|---|
| pip-audit, `requirements.txt` (runtime) | **No known vulnerabilities** |
| bandit, high severity | **0** |
| bandit, medium severity | 3 (reviewed below) |
| bandit, low severity | 25 (reviewed below) |

## Fixed in this scan

| Finding | Where | Fix |
|---|---|---|
| B615 model downloads not pinned (supply chain) | `scripts/fetch_assets.py` | Hugging Face downloads pinned to a commit; YOLOX files checked against pinned SHA-256 and refused if different |
| B614 unsafe `torch.load` (code can run on load) | `app/tracking/reid.py` | `weights_only=True` |
| B310 `urlopen` with any URL scheme | `app/decision/sync.py` | `hq_url` must be http(s) |
| B110 exception silently ignored | `app/decision/ledger.py` | logged (a failing C2 feed still never stops sealing) |

## Reviewed and accepted

| Finding | Where | Why it is acceptable |
|---|---|---|
| B104 bind to all interfaces (medium) | `app/sources/api.py` | The phone-camera page must be reachable from phones on the post LAN. Keep the edge box off public networks (Egress Guard, post LAN only) |
| B310 `urlopen` (medium) | `scripts/fetch_assets.py` | Fixed https URLs in the script, run once by the team |
| B603 / B607 / B404 subprocess | `benchmark/run.py`, `scripts/*.py`, `app/sources/network.py` | Fixed argument lists (`git`, `nft`, `powershell`, `adb` for a USB-connected phone); no shell |
| B311 `random` | benchmark and preview | Synthetic test data only; all cryptography uses `cryptography` (Ed25519) and `hashlib` |
| B101 `assert` | export and benchmark self-checks | Development-time checks, not security controls |

## Not covered by these tools

The threat model (`docs/threat-model.md`) covers what static scans can't see: a stolen box, a
compromised camera, forged SMS, insider misuse. A penetration test of the edge box and the HQ
service is still to do.
