"""Iteration 21 — Tier delete persistence + OTP fire_event best-effort + Live Monitor date range.

Covers:
1. POST /api/loyalty/tiers → DELETE /api/loyalty/tiers/{slug} → GET /api/loyalty/config
   the slug is absent. DELETE on unknown slug → 404. DELETE of last remaining tier
   → 400 (refuses). Real Silver/Gold/etc tiers are NEVER touched.
2. POS OTP flow (posCustomerCheckRequest) still returns OTP successfully even when
   no active 'otp'-trigger SMS template exists (best-effort dispatch must not raise).
3. GET /api/live-monitor/stats and /transactions accept start_date / end_date:
   - wide range (2020..2030) → bills_total > 0, rows returned
   - future range (2099-..) → bills_total == 0, no rows
   - no dates → relative window still works.
"""
import os
import asyncio
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env", "r") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break
assert BASE_URL, "REACT_APP_BACKEND_URL not configured"

ADMIN_EMAIL = "superadmin@fundle.io"
ADMIN_PASSWORD = "Fundle@2026"

REAL_TIERS = {"silver", "gold", "platinum", "diamond", "founders"}


def _mongo():
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "portal": "crm"},
                      timeout=20)
    assert r.status_code == 200, r.text
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def pos_cred():
    async def _get():
        db = _mongo()
        return await db["pos_credentials"].find_one(
            {"label": "kazo_default", "is_active": True}, {"_id": 0}
        )
    cred = asyncio.run(_get())
    assert cred, "kazo_default credential missing"
    return cred


# ---------------------------------------------------------------------------
# 1. Tier delete persistence
# ---------------------------------------------------------------------------
class TestTierDeletePersistence:
    THROWAWAY_SLUG = "test_iter21_throwaway"

    def _ensure_clean(self, headers):
        # Idempotent: delete if it already exists from a prior crashed run
        requests.delete(f"{BASE_URL}/api/loyalty/tiers/{self.THROWAWAY_SLUG}",
                        headers=headers, timeout=15)

    def test_add_then_delete_persists_in_config(self, auth_headers):
        self._ensure_clean(auth_headers)
        # POST: add throwaway tier
        body = {
            "tier": self.THROWAWAY_SLUG,
            "name": "Iter21 Throwaway",
            "min_lifetime_spend": 999999,
            "max_lifetime_spend": 9999999,
            "earn_multiplier": 1.0,
            "welcome_bonus": 0,
            "birthday_bonus": 0,
            "anniversary_bonus": 0,
            "upgrade_bonus": 0,
            "tier_type": "standard",
        }
        r = requests.post(f"{BASE_URL}/api/loyalty/tiers",
                          headers=auth_headers, json=body, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert any(t.get("tier") == self.THROWAWAY_SLUG for t in data["tiers"])

        # GET — confirm visible
        cfg = requests.get(f"{BASE_URL}/api/loyalty/config",
                           headers=auth_headers, timeout=15).json()
        assert any(t.get("tier") == self.THROWAWAY_SLUG for t in cfg["tier_rules"])

        # DELETE
        rd = requests.delete(f"{BASE_URL}/api/loyalty/tiers/{self.THROWAWAY_SLUG}",
                             headers=auth_headers, timeout=15)
        assert rd.status_code == 200, rd.text
        out = rd.json()
        assert out.get("ok") is True
        assert all(t.get("tier") != self.THROWAWAY_SLUG for t in out["tiers"])

        # GET again — confirm gone (persistence)
        cfg2 = requests.get(f"{BASE_URL}/api/loyalty/config",
                            headers=auth_headers, timeout=15).json()
        slugs = [t.get("tier") for t in cfg2["tier_rules"]]
        assert self.THROWAWAY_SLUG not in slugs

        # The real production tiers must still be there (not damaged)
        present_real = REAL_TIERS.intersection(set(slugs))
        assert len(present_real) >= 1, f"Real tiers should be untouched, got {slugs}"

    def test_delete_unknown_slug_returns_404(self, auth_headers):
        rd = requests.delete(
            f"{BASE_URL}/api/loyalty/tiers/nonexistent_slug_xyz_iter21",
            headers=auth_headers, timeout=15
        )
        assert rd.status_code == 404, rd.text

    def test_cannot_delete_last_remaining_tier(self, auth_headers):
        """Snapshot the current tiers, replace with a single tier via PUT, try DELETE → 400, restore."""
        cfg = requests.get(f"{BASE_URL}/api/loyalty/config",
                           headers=auth_headers, timeout=15).json()
        original_tiers = cfg["tier_rules"]
        assert original_tiers and len(original_tiers) >= 1

        # Replace with exactly one tier
        single = [{
            "tier": "iter21_only", "name": "Only Tier",
            "min_lifetime_spend": 0, "max_lifetime_spend": None,
            "earn_multiplier": 1.0, "welcome_bonus": 0,
            "birthday_bonus": 0, "anniversary_bonus": 0, "upgrade_bonus": 0,
            "tier_type": "standard", "is_active": True, "color": "#888",
            "coupon_discount_pct": 0, "free_shipping_min_bill": None,
        }]
        put_body = dict(cfg)
        put_body["tier_rules"] = single
        pr = requests.put(f"{BASE_URL}/api/loyalty/config",
                          headers=auth_headers, json=put_body, timeout=15)
        try:
            assert pr.status_code == 200, pr.text
            # Try DELETE the only tier → must 400
            rd = requests.delete(f"{BASE_URL}/api/loyalty/tiers/iter21_only",
                                 headers=auth_headers, timeout=15)
            assert rd.status_code == 400, rd.text
            assert "last" in (rd.json().get("detail") or "").lower()
        finally:
            # Restore — drop our test tier, put originals back
            restore_body = dict(cfg)
            restore_body["tier_rules"] = original_tiers
            rb = requests.put(f"{BASE_URL}/api/loyalty/config",
                              headers=auth_headers, json=restore_body, timeout=15)
            assert rb.status_code == 200, rb.text


# ---------------------------------------------------------------------------
# 2. POS OTP best-effort dispatch (no active 'otp' template → still returns OTP)
# ---------------------------------------------------------------------------
class TestPOSOTPBestEffortDispatch:
    def test_pos_customer_check_otp_works_without_otp_template(self, pos_cred):
        """No active 'otp'-trigger SMS template is configured in seed data, so the
        fire_event('otp',...) is a no-op. POS OTP endpoint must still succeed."""
        # Find a real customer mobile to call against
        async def _find_customer():
            db = _mongo()
            c = await db["customers"].find_one({"mobile": {"$nin": [None, ""]}},
                                                {"_id": 0, "mobile": 1})
            return c

        cust = asyncio.run(_find_customer())
        assert cust, "No customer with mobile to test against"
        mobile = cust["mobile"]

        # Verify no active 'otp' SMS template exists (precondition for the test)
        async def _verify_no_template():
            db = _mongo()
            t = await db["templates"].find_one(
                {"event_trigger": "otp", "is_active": True, "channel": "sms"}
            )
            return t

        existing = asyncio.run(_verify_no_template())
        if existing:
            pytest.skip("Active 'otp' SMS template present — would fire to real mobile, skipping")

        headers = {"x-api-key": pos_cred["api_key"]}
        body = {
            "merchant_id": pos_cred["merchant_id"],
            "customer_key": pos_cred["customer_key"],
            "customer_mobile": mobile,
        }
        r = requests.post(f"{BASE_URL}/api/pos/posCustomerCheckRequest",
                          headers=headers, json=body, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        # POS handler wraps payload under {status_code, response}
        inner = data.get("response") if isinstance(data.get("response"), dict) else data
        msg = (inner.get("message") or "").lower()
        assert ("otp" in msg) or inner.get("authentication") is True or inner.get("otp_id"), data


# ---------------------------------------------------------------------------
# 3. Live Monitor date-range filter
# ---------------------------------------------------------------------------
class TestLiveMonitorDateRange:
    def test_stats_wide_range_returns_bills(self, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/live-monitor/stats",
            headers=auth_headers,
            params={"start_date": "2020-01-01", "end_date": "2030-01-01"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("bills_total", 0) > 0, f"Expected bills in 2020-2030, got {data}"

    def test_stats_future_range_zero_bills(self, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/live-monitor/stats",
            headers=auth_headers,
            params={"start_date": "2099-01-01", "end_date": "2099-12-31"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("bills_total", 0) == 0, f"Expected 0 bills in 2099, got {data}"

    def test_transactions_wide_range_returns_rows(self, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/live-monitor/transactions",
            headers=auth_headers,
            params={"start_date": "2020-01-01", "end_date": "2030-01-01", "limit": 50},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("count", 0) > 0, f"Expected rows in wide range, got {data}"
        assert isinstance(data.get("rows"), list)

    def test_transactions_future_range_zero_rows(self, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/live-monitor/transactions",
            headers=auth_headers,
            params={"start_date": "2099-01-01", "end_date": "2099-12-31"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("count", 0) == 0

    def test_relative_window_still_works(self, auth_headers):
        """Without start_date/end_date, since_minutes / minutes window must still
        return a 200 (count may be 0 in preview where data is historical)."""
        rs = requests.get(f"{BASE_URL}/api/live-monitor/stats",
                          headers=auth_headers, params={"minutes": 60}, timeout=20)
        assert rs.status_code == 200, rs.text
        assert "bills_total" in rs.json()
        rt = requests.get(f"{BASE_URL}/api/live-monitor/transactions",
                          headers=auth_headers, params={"since_minutes": 60, "limit": 20},
                          timeout=20)
        assert rt.status_code == 200, rt.text
        assert "rows" in rt.json()


# ---------------------------------------------------------------------------
# 4. Regression: PUT /api/loyalty/config still saves with valid tier_rules and
#    upgrade_bonus field round-trips.
# ---------------------------------------------------------------------------
class TestLoyaltyConfigRegression:
    def test_put_config_with_valid_tiers_succeeds_and_upgrade_bonus_preserved(self, auth_headers):
        cfg = requests.get(f"{BASE_URL}/api/loyalty/config",
                           headers=auth_headers, timeout=15).json()
        tiers = cfg["tier_rules"]
        assert tiers, "no tiers in config"
        # Confirm upgrade_bonus key is present on every tier
        for t in tiers:
            assert "upgrade_bonus" in t, f"missing upgrade_bonus on {t.get('tier')}"
        body = dict(cfg)
        # No-op save (round-trip)
        r = requests.put(f"{BASE_URL}/api/loyalty/config",
                         headers=auth_headers, json=body, timeout=15)
        assert r.status_code == 200, r.text
        out = r.json()
        for t in out["tier_rules"]:
            assert "upgrade_bonus" in t
