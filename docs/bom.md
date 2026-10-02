# Parts list per post (bill of materials)

**Status: estimates only. No quotes collected yet.** The deck states ₹32,500 per post plus about
₹4,000 a year. That figure must be backed by **dated vendor quotes** in the "Quote" columns below
(save each quote as a PDF or screenshot in `docs/quotes/`). If the quoted total differs from
₹32,500, update this file and say so; never adjust the quotes to match the deck.

Assumes the post's existing IP cameras and network cable; one box per post with up to 10 cameras.

| # | Item | Needed for | Rough estimate (not a quote) | Quote (₹) | Vendor | Date | File |
|---|---|---|---|---|---|---|---|
| 1 | Intel N100 mini PC, 16 GB RAM, 512 GB SSD, 2 Ethernet ports | Edge box | ₹14,000 – 20,000 | | | | |
| 2 | USB 3.0 gigabit Ethernet adapter (if the PC has one port) | Egress Guard camera port | ₹800 – 1,500 | | | | |
| 3 | USB GSM modem with voice, 4G with 2G fallback (e.g. SIM7600 class) | SMS, voice call | ₹3,000 – 6,000 | | | | |
| 4 | USB serial relay + 12 V siren | Post siren | ₹800 – 2,000 | | | | |
| 5 | DC mini-UPS or 600 VA UPS | Power cuts | ₹2,500 – 5,000 | | | | |
| 6 | Enclosure, cables, mounting | Install | ₹1,000 – 2,000 | | | | |
| 7 | PoE switch (only if the cameras' switch can't be reused) | Cameras | ₹4,000 – 8,000 (optional) | | | | |
| | **One-time total** | | **₹22,000 – 36,500** (without item 7) | | | | |

## Running cost per year

| Item | Rough estimate | Quote | Notes |
|---|---|---|---|
| SIM with voice + SMS plan | ₹1,800 – 3,000 | | One per box |
| Power (box ≈ 12 W average, plus modem) | ≈ 110 kWh ≈ ₹800 – 1,000 | — | Measure the real draw with a plug-in meter (deck claims 11.6 W) |
| Spares and maintenance | ₹1,000 – 2,000 | | |
| **Per year** | **≈ ₹3,600 – 6,000** | | |

## Fleet estimate (to recompute from quotes)

734 BOPs × one-time total = ________ ; × running cost = ________ per year.
Deck: ≈ ₹2.4 cr one-time, 0.05% of SSB's ₹4,775 cr 2015–26 spend (MHA, Lok Sabha Q488, 3 Feb 2026).
