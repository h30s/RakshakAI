# Threat model

Version 1 · 2026-10-02 · Method: STRIDE per component · Review again after every architecture change.

**Status labels:** **In code** = implemented and tested in this repository. **Deployment** =
depends on how the box is installed. **Open** = not yet addressed.

## 1. What we protect

| Asset | Why it matters |
|---|---|
| Alerts reaching the right person, on time | The point of the system; a suppressed or delayed alert is the worst failure |
| Integrity of evidence (clips, ledger) | Must stand up under BSA s.63(4); edits must be detectable |
| The post's signing key | Whoever holds it can sign alerts and ledger entries as the post |
| Footage and movement data of residents | Personal data (DPDP Act); lawful crossers are the majority |
| The camera network | Cheap IP cameras phone home to vendor clouds; a camera can be a way in |

## 2. Components and trust boundaries

```
 [IP cameras] --camera port (Egress Guard)--> [Edge box: detector, decision engine, ledger, key]
                                                 |  post LAN: duty console (browser)
                                                 |  GSM modem: signed SMS / call -> [duty phones]
                                                 |  link (when up): ledger entries -> [Sector HQ service]
                                                 |  optional: MQTT / WebSocket -> [C2 systems]
                                                 |  optional: FRS / ANPR hits <- [SSB systems]
```

Trust boundaries: camera port ↔ box; post LAN ↔ box; mobile network; post ↔ HQ link; box ↔ C2.

## 3. Threats and mitigations

| # | Component | STRIDE | Threat | Mitigation | Status |
|---|---|---|---|---|---|
| T1 | Cameras | Info disclosure | Camera sends video or metadata to a vendor cloud | Egress Guard: camera port has no route out; every attempt logged and dropped; DNS sinkholed | In code (`deploy/egress-guard`), untested on the N100 |
| T2 | Cameras | Elevation | Compromised camera attacks the box or other networks | Camera port may reach only DHCP / DNS / NTP on the box; no forwarding; other connections logged | In code (nftables rules) |
| T3 | Cameras | Tampering / DoS | Camera covered, turned or unplugged | Camera health monitor raises a stall (`app/threats/monitor.py`); scene-change check | Partly (stall only); scene-change **Open** |
| T4 | Evidence | Tampering | Clip or ledger entry edited after the fact | SHA-256 chain + Ed25519 signature per entry; `verify` finds any change; hourly Merkle root held at HQ | In code, tested |
| T5 | Evidence | Repudiation | Clip deleted to hide an incident | A missing clip fails verification unless a signed retention entry records its deletion under policy | In code, tested |
| T6 | Edge box | Info disclosure / spoofing | Box stolen; key used to sign false entries | Entries up to the theft are anchored at HQ and cannot be rewritten; HQ removes the post's key from `posts.json` | In code (anchors). Key in TPM / encrypted disk: **Deployment** |
| T7 | Edge box | DoS | Power cut, disk full, box crash | Ledger is append-only and reloaded on start; alerts, statuses and the shift budget are restored from it; retention job prunes logs | In code. UPS: **Deployment** |
| T8 | Duty console | Spoofing / repudiation | Anyone on the post LAN acknowledges, dismisses or escalates alerts, sets surge off or adds Watch Orders | Every action is sealed in the ledger with a time stamp, but **not tied to a person** | **Open:** operator login (PIN per operator) |
| T9 | Alerts | DoS | Flood of fake external hits (they bypass the budget) | `integration_token` in post.json; requests without the token are refused | In code, tested |
| T10 | Alerts | DoS | A real flood (surge) hides the one alert that matters | Always-alert classes never budgeted; surge mode lifts the cap and tells the commander | In code, tested |
| T11 | Alerts | Evasion | Crossers blend in with normal traffic (same path, hour, speed) | Stated limit; Watch Orders raise sensitivity; shift digest keeps everything | Limit stated; red-team test **Open** |
| T12 | SMS | Spoofing / tampering | Forged or edited alert SMS | Ed25519 signature checked on the phone (`/verify`) and at HQ (`/api/hq/sms/verify`) | In code, tested |
| T13 | SMS | Replay | An old genuine SMS is sent again (the signature still verifies) | `/verify` shows the alert's age and warns past 15 minutes; the ledger head in the SMS ties it to one point in the chain | In code. Date in the SMS: **Open** (space) |
| T14 | HQ link | Tampering / spoofing | Forged entries sent to HQ in a post's name | HQ accepts only entries that extend that post's chain and carry its registered key's signature; recomputes every anchor root | In code, tested |
| T15 | HQ link | Info disclosure | Entries read in transit | Entries carry no images; use the SSB network or a VPN; HTTPS on the HQ service | **Deployment** |
| T16 | C2 feeds | Spoofing | A consumer is fed false events | Feeds carry the signed ledger entries; consumers verify with `/api/decision/pubkey` | In code |
| T17 | Models | Tampering | Model file swapped for a trojaned one | Downloads pinned (Hugging Face revision, YOLOX SHA-256); safe `torch.load`; models never fetched at run time | In code |
| T18 | Data | Info disclosure | Footage of residents leaks or is kept too long | Clips only for alerts; 30-day deletion unless escalated; movement logs hold grid cells and pseudonymous IDs, no images; `data/` never in git | In code; see `docs/dpia.md` |
| T19 | Insider | Elevation | Operator uses the system to follow a person without cause | Watch Orders and actions are sealed and visible to the commander and HQ; no free-text person search across days | Partly; audit review routine: **Deployment** |
| T20 | Software | Tampering | Update replaced with a malicious one | Signed OTA updates | **Open** (roadmap) |

## 4. Open items, in priority order

1. **T8 operator login.** A PIN per operator, sent with every action and sealed in the ledger, so every tap has a name.
2. **T6 key protection.** Keep the signing key in the box's TPM or on an encrypted volume (LUKS) and register it at HQ during install.
3. **T13 date in the SMS.** Add a day-of-month field once the 160-character budget allows; until then rely on the age warning.
4. **T11 red-team test** (`docs/red-team.md`) to measure the evasion limit instead of only stating it.
5. **T20 signed updates** before any deployment beyond the pilot.
