# Data protection impact assessment (DPDP Act, 2023)

Version 1 (draft) · 2026-10-02 · **This is the team's own assessment, not legal advice.** It must
be reviewed by the deploying force's legal / data-protection officer before any pilot.

## 1. What the system does with personal data

Rakshak AI analyses video from cameras a border force already operates at its own posts. It
detects people and vehicles, follows their movement through the camera views, and alerts an
operator about the few movements that are unusual for that post. Most people it sees are lawful
crossers: villagers, traders, students.

## 2. Data, purpose and retention

| Data | Where | Purpose | Kept |
|---|---|---|---|
| Live video frames | Memory on the edge box | Detection | Not stored (display buffer of a few seconds) |
| Evidence snapshot of an alert (may show faces) | `data/evidence/` on the box | Evidence of an alert | 30 days, deleted by policy unless the alert was escalated; the deletion is sealed in the ledger |
| Movement summary: camera, grid cells, times, speed, group size, pseudonymous tracker ID | `data/movements.csv` | Learning what is normal at the post; benchmark | 180 days, then pruned |
| Appearance embedding for re-identification | Memory | Following a person across cameras | Not stored; tracker IDs reset on restart |
| Ledger: alerts, operator actions, anchors | `data/ledger/` on the box; HQ | Audit and evidence integrity | Kept as the audit log (no images) |
| Face / number plate (planned: gates only) | — | Watchlist / vehicle checks | Not yet implemented; to be assessed before it is |
| Operator feedback on the website | `data/feedback.jsonl` | Improving the prototype | Readable only on the server |

## 3. Legal basis (to be confirmed by the force's legal officer)

- Processing by or for a State instrumentality for the security of the State, which the Act allows to be exempted by notification (s.17(2)(a)).
- Even where exempt, the system keeps to the Act's safeguards (s.8(5): reasonable security safeguards; s.8(7): erasure when the purpose is served). Exemption is not used as a reason to collect more.

## 4. Principles applied

- **Purpose limitation.** Border-crossing alerts only. No search of a named person across days, and no export of movement logs outside the force.
- **Minimisation.** Video is not recorded by Rakshak (the force's existing VMS does that under its own policy). Only alert snapshots are kept; movements hold grid cells, not images.
- **Storage limitation.** 30 days for alert clips, 180 days for movement logs (CERT-In 2022 log retention), both enforced in code.
- **Neutral language.** Records say "restricted area entry", never "infiltrator".
- **Security.** Signed hash chain, Egress Guard, no data in git, HTTPS for the phone page; see `docs/threat-model.md`.
- **Accountability.** Every operator action and Watch Order is sealed and visible to HQ.

## 5. Risks to residents

| Risk | Likelihood | Severity | Mitigation | Residual |
|---|---|---|---|---|
| Lawful crossers repeatedly flagged (harassment, lost livelihood on haat days) | Medium | High | Day-type baselines (haat, festival); alert budget; drift watch on operator feedback | Medium: needs the field precision test (OAT-2) |
| Function creep into general surveillance of villages | Medium | High | Camera scope limited to the border line and gates; purpose written in the deployment order; audit by HQ | Medium |
| "Repeat crosser" leads treated as identification | Medium | Medium | Border Pulse labels them as pseudonymous leads for review; tracker IDs reset on restart | Low |
| Snapshot of a bystander leaks | Low | Medium | Only on the box; 30-day deletion; access on the post LAN only | Low |
| Bias: model works worse in poor light, on certain clothing or postures | Medium | Medium | Night/thermal evaluation (LLVIP); measure recall by condition before the pilot | Medium until measured |
| Faces / plates added later without assessment | Low | High | This DPIA must be updated before face or plate recognition is turned on | Low |

## 6. Rights and contact

Residents should be told cameras are in use (signage at gates and haat crossings, in Hindi and the
local language). Requests and complaints go to the force's grievance officer. Data on the
prototype website (feedback form) can be deleted on request.

## 7. Before a pilot

- [ ] Legal officer reviews sections 3–5
- [ ] Signage text agreed
- [ ] Retention periods confirmed in the deployment order
- [ ] Recall measured by light condition (bias check)
- [ ] Operator login (threat model T8) in place, so access is attributable
