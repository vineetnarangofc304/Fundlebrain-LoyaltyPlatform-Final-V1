"""Iteration 61 — tiers assigned STRICTLY from the frontend-configured Tier Rules.

Locks the rule the client confirmed: tier names/ranges come ONLY from the Loyalty
Logic editor (DB `loyalty_config_col.tier_rules`). The historic ingestion and live
POS must NEVER fabricate a hardcoded tier (e.g. "diamond") that the brand hasn't
defined. When no tiers are configured the derivation returns "" (untiered).

Run: pytest -q backend/tests/iteration61_config_driven_tier_test.py
"""
import asyncio

import routes.historic_routes as hist
from routes.pos_ewards_routes import _derive_tier as pos_derive_tier


# A custom config like the client's production tiers (NOT silver/gold/diamond).
CUSTOM_TIERS = [
    {"tier": "kazo_insider", "min_lifetime_spend": 0, "max_lifetime_spend": 25000, "earn_multiplier": 2, "is_active": True},
    {"tier": "trendsetter", "min_lifetime_spend": 25000, "max_lifetime_spend": 75000, "earn_multiplier": 3, "is_active": True},
    {"tier": "style_icon", "min_lifetime_spend": 75000, "max_lifetime_spend": None, "earn_multiplier": 5, "is_active": True},
]
HARDCODED = {"silver", "gold", "platinum", "diamond", "founders"}


def test_historic_uses_only_configured_tier_names():
    hist._TIER_RULES_CACHE = CUSTOM_TIERS
    try:
        assert hist._derive_tier(10000) == "kazo_insider"   # 0..25k
        assert hist._derive_tier(25000) == "trendsetter"    # boundary -> next band
        assert hist._derive_tier(50000) == "trendsetter"    # 25k..75k
        assert hist._derive_tier(75000) == "style_icon"     # 75k+
        assert hist._derive_tier(9_000_000) == "style_icon"  # huge spend, highest band
        # NEVER returns a hardcoded phantom tier
        for spend in (0, 26000, 80000, 300000, 999999):
            assert hist._derive_tier(spend) not in HARDCODED
    finally:
        hist._TIER_RULES_CACHE = []


def test_historic_empty_cache_returns_untiered_not_diamond():
    hist._TIER_RULES_CACHE = []
    # Old bug: 300000 -> "diamond". Must now be "" (no fabricated tier).
    assert hist._derive_tier(300000) == ""
    assert hist._derive_tier(0) == ""


def test_pos_uses_only_configured_tier_names():
    cfg = {"tier_rules": CUSTOM_TIERS}
    assert pos_derive_tier(10000, cfg) == "kazo_insider"
    assert pos_derive_tier(50000, cfg) == "trendsetter"
    assert pos_derive_tier(200000, cfg) == "style_icon"
    for spend in (0, 26000, 80000, 300000):
        assert pos_derive_tier(spend, cfg) not in HARDCODED


def test_pos_empty_config_returns_untiered():
    assert pos_derive_tier(300000, {}) == ""
    assert pos_derive_tier(300000, {"tier_rules": []}) == ""


def test_inactive_tiers_are_ignored():
    rules = [
        {"tier": "kazo_insider", "min_lifetime_spend": 0, "is_active": True},
        {"tier": "trendsetter", "min_lifetime_spend": 25000, "is_active": False},  # disabled
        {"tier": "style_icon", "min_lifetime_spend": 75000, "is_active": True},
    ]
    hist._TIER_RULES_CACHE = rules
    try:
        # 50k would be trendsetter, but it's inactive -> stays in kazo_insider band
        assert hist._derive_tier(50000) == "kazo_insider"
        assert hist._derive_tier(80000) == "style_icon"
    finally:
        hist._TIER_RULES_CACHE = []
    assert pos_derive_tier(50000, {"tier_rules": rules}) == "kazo_insider"


def test_refresh_cache_reads_from_db():
    """_refresh_tier_rules_cache() must load active tier_rules from loyalty_config_col."""
    async def run():
        await hist._refresh_tier_rules_cache()
        return hist._TIER_RULES_CACHE

    cache = asyncio.run(run())
    # The preview DB has a default config with tier_rules -> cache populated.
    assert isinstance(cache, list)
    if cache:
        assert all("min_lifetime_spend" in t for t in cache)
        # every cached tier is marked active
        assert all(t.get("is_active", True) for t in cache)
    hist._TIER_RULES_CACHE = []
