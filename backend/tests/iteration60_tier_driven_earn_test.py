"""Iteration 60 — tier-driven earn engine.

Locks the rule the client confirmed: when the Earn Engine rate is blank/0, the
per-tier multiplier itself IS the % of the bill (Kazo Insider mult 2 -> 2%,
Trendsetter 3 -> 3%, Style Icon 5 -> 5%). When a global rate IS set, the legacy
base x rate x multiplier behaviour is preserved.

Run: pytest -q backend/tests/iteration60_tier_driven_earn_test.py
"""
from routes.pos_ewards_routes import _compute_earn_points as f


def test_tier_driven_percent_mode():
    cfg = {"earn_mode": "percent_of_spend", "percent_of_spend": 0}
    assert f(5000, cfg, 2) == 100   # 2%
    assert f(5000, cfg, 3) == 150   # 3%
    assert f(5000, cfg, 5) == 250   # 5%
    assert f(5000, cfg, 1.0) == 50  # unmatched tier -> mult 1.0 -> 1%
    assert f(5000, cfg, 0) == 0     # tier multiplier truly 0 -> 0


def test_tier_driven_points_mode():
    cfg = {"earn_mode": "points_per_spend", "earn_ratio": 0}
    assert f(5000, cfg, 3) == 150   # tier-driven fallback also works in pts mode


def test_global_rate_preserved():
    # % of spend mode with a global rate set -> base x rate x multiplier
    assert f(5000, {"earn_mode": "percent_of_spend", "percent_of_spend": 5}, 2) == 500
    # points-per-rupee with ratio set
    assert f(5000, {"earn_mode": "points_per_spend", "earn_ratio": 1}, 1) == 5000
    assert f(1000, {"earn_mode": "points_per_spend", "earn_ratio": 1}, 1.25) == 1250


def test_zero_base():
    assert f(0, {"earn_mode": "percent_of_spend", "percent_of_spend": 0}, 5) == 0
