"""Decision layer: turns tracked people into a small number of ranked, explained alerts.

    tracker output -> movements (events.py) -> score against this post's normal (baseline.py)
    -> alert budget, surge mode, Watch Orders (budget.py) -> sealed in a signed ledger (ledger.py)

Everything here is plain Python (plus `cryptography` for Ed25519) so it can be tested and
benchmarked without cameras or models: see tests/ and `python -m benchmark --all`.
"""
