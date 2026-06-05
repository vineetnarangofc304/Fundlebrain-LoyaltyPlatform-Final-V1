"""Iteration 16 — Loyalty Logic Editor backend tests.

Coverage:
- GET/PUT /api/loyalty/config (backfill, validations: tier ordering, earn_mode, reset cadence)
- POST/PATCH/DELETE /api/loyalty/tiers (add, toggle, delete + last-tier guard)
- POST/DELETE /api/loyalty/festival-boosters
- POST /api/loyalty/simulate (default mode, percent_of_spend mode, store-type, category, festival booster, min-bill threshold)
"""
import os
import copy
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
if not BASE_URL:
    # Load from frontend/.env
    try:
        with open("/app/frontend/.env", "r") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except FileNotFoundError:
        pass
assert BASE_URL, "REACT_APP_BACKEND_URL not configured"
EMAIL = "superadmin@fundle.io"
PASSWORD = "Fundle@2026"


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD, "portal": "crm"})
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    token = r.json()["token"]
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def original_config(session):
    """Snapshot the existing config so we can restore at module teardown."""
    r = session.get(f"{BASE_URL}/api/loyalty/config")
    assert r.status_code == 200, r.text
    snap = copy.deepcopy(r.json())
    yield snap
    # Restore
    snap.pop("_id", None)
    session.put(f"{BASE_URL}/api/loyalty/config", json=snap)


# ---------- GET /loyalty/config — backfill ----------
class TestLoyaltyConfigRead:
    def test_get_config_has_all_new_fields(self, session, original_config):
        cfg = original_config
        expected_keys = [
            "earn_mode", "percent_of_spend", "max_redeem_pct_of_bill",
            "tier_reset_cadence", "tier_reset_anchor_date",
            "category_multipliers", "store_type_multipliers",
            "festival_boosters", "block_earn_on_returns",
            "earn_ratio", "burn_ratio", "min_redeem_points", "point_expiry_days",
            "welcome_bonus", "birthday_bonus", "anniversary_bonus",
            "referral_points_referrer", "referral_points_referee",
            "tier_rules", "require_otp_for_redeem", "allow_coupon_stacking",
            "min_bill_for_earn",
        ]
        for k in expected_keys:
            assert k in cfg, f"missing field {k} in config response"
        assert cfg["earn_mode"] in ("points_per_spend", "percent_of_spend")
        assert isinstance(cfg["tier_rules"], list) and len(cfg["tier_rules"]) >= 1
        assert isinstance(cfg["category_multipliers"], dict)
        assert isinstance(cfg["store_type_multipliers"], dict)
        assert isinstance(cfg["festival_boosters"], list)


# ---------- PUT /loyalty/config — validations ----------
class TestLoyaltyConfigUpdateValidations:
    def test_invalid_earn_mode_rejected(self, session, original_config):
        body = copy.deepcopy(original_config)
        body["earn_mode"] = "garbage"
        r = session.put(f"{BASE_URL}/api/loyalty/config", json=body)
        assert r.status_code == 400, r.text
        assert "earn_mode" in r.json().get("detail", "")

    def test_invalid_reset_cadence_rejected(self, session, original_config):
        body = copy.deepcopy(original_config)
        body["tier_reset_cadence"] = "weekly"
        r = session.put(f"{BASE_URL}/api/loyalty/config", json=body)
        assert r.status_code == 400, r.text
        assert "tier_reset_cadence" in r.json().get("detail", "")

    def test_tier_ordering_overlap_rejected(self, session, original_config):
        """Force overlap: Silver max=30000, Gold min=20000 (overlap)."""
        body = copy.deepcopy(original_config)
        for t in body["tier_rules"]:
            slug = t.get("tier", "").lower()
            if slug == "silver":
                t["min_lifetime_spend"] = 0
                t["max_lifetime_spend"] = 30000
                t["is_active"] = True
            elif slug == "gold":
                t["min_lifetime_spend"] = 20000  # < silver max -> overlap
                t["max_lifetime_spend"] = 75000
                t["is_active"] = True
        r = session.put(f"{BASE_URL}/api/loyalty/config", json=body)
        assert r.status_code == 400, r.text
        assert "overlap" in r.json().get("detail", "").lower()

    def test_tier_max_less_than_min_rejected(self, session, original_config):
        body = copy.deepcopy(original_config)
        # Pick first tier and force max<min
        t = body["tier_rules"][0]
        t["min_lifetime_spend"] = 5000
        t["max_lifetime_spend"] = 1000
        t["is_active"] = True
        r = session.put(f"{BASE_URL}/api/loyalty/config", json=body)
        assert r.status_code == 400, r.text
        assert "max" in r.json().get("detail", "").lower()

    def test_happy_path_update(self, session, original_config):
        body = copy.deepcopy(original_config)
        body["tier_reset_cadence"] = "annual"
        body["tier_reset_anchor_date"] = "04-01"
        body["max_redeem_pct_of_bill"] = 40.0
        body["block_earn_on_returns"] = True
        r = session.put(f"{BASE_URL}/api/loyalty/config", json=body)
        assert r.status_code == 200, r.text
        cfg = r.json()
        assert cfg["tier_reset_cadence"] == "annual"
        assert cfg["tier_reset_anchor_date"] == "04-01"
        assert cfg["max_redeem_pct_of_bill"] == 40.0
        # GET to confirm persistence
        r2 = session.get(f"{BASE_URL}/api/loyalty/config")
        assert r2.json()["max_redeem_pct_of_bill"] == 40.0


# ---------- POST/PATCH/DELETE /loyalty/tiers ----------
class TestTierCRUD:
    TEST_SLUG = "test-iter16-bronze"

    def test_add_tier(self, session):
        # Cleanup first if exists
        session.delete(f"{BASE_URL}/api/loyalty/tiers/{self.TEST_SLUG}")
        payload = {
            "tier": self.TEST_SLUG,
            "name": "TEST Bronze",
            "min_lifetime_spend": 1,  # >0 so it sorts between existing tiers
            "max_lifetime_spend": 5,
            "earn_multiplier": 1.1,
            "welcome_bonus": 50,
            "tier_type": "entry",
            "color": "#cd7f32",
            "coupon_discount_pct": 2,
        }
        r = session.post(f"{BASE_URL}/api/loyalty/tiers", json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        slugs = [t["tier"] for t in data["tiers"]]
        assert self.TEST_SLUG in slugs
        # Verify sort by min_lifetime_spend ascending
        spends = [t.get("min_lifetime_spend", 0) for t in data["tiers"]]
        assert spends == sorted(spends), f"tiers not sorted: {spends}"

    def test_add_tier_duplicate_rejected(self, session):
        payload = {"tier": self.TEST_SLUG, "name": "Dup", "min_lifetime_spend": 2}
        r = session.post(f"{BASE_URL}/api/loyalty/tiers", json=payload)
        assert r.status_code == 400, r.text
        assert "already exists" in r.json().get("detail", "").lower()

    def test_toggle_tier_active(self, session):
        r = session.patch(f"{BASE_URL}/api/loyalty/tiers/{self.TEST_SLUG}/toggle")
        assert r.status_code == 200, r.text
        tier = next(t for t in r.json()["tiers"] if t["tier"] == self.TEST_SLUG)
        assert tier["is_active"] is False
        # Toggle back
        r2 = session.patch(f"{BASE_URL}/api/loyalty/tiers/{self.TEST_SLUG}/toggle")
        tier2 = next(t for t in r2.json()["tiers"] if t["tier"] == self.TEST_SLUG)
        assert tier2["is_active"] is True

    def test_toggle_unknown_tier_404(self, session):
        r = session.patch(f"{BASE_URL}/api/loyalty/tiers/nonexistent-xyz/toggle")
        assert r.status_code == 404

    def test_delete_tier(self, session):
        r = session.delete(f"{BASE_URL}/api/loyalty/tiers/{self.TEST_SLUG}")
        assert r.status_code == 200, r.text
        slugs = [t["tier"] for t in r.json()["tiers"]]
        assert self.TEST_SLUG not in slugs

    def test_delete_unknown_tier_404(self, session):
        r = session.delete(f"{BASE_URL}/api/loyalty/tiers/nonexistent-xyz")
        assert r.status_code == 404


# ---------- Festival boosters ----------
class TestFestivalBoosters:
    def test_add_and_delete_booster(self, session):
        payload = {
            "name": "TEST Diwali Boost",
            "start_date": "2026-10-15",
            "end_date": "2026-11-05",
            "multiplier": 2.0,
            "applies_to": "all",
        }
        r = session.post(f"{BASE_URL}/api/loyalty/festival-boosters", json=payload)
        assert r.status_code == 200, r.text
        boosters = r.json()["boosters"]
        match = [b for b in boosters if b.get("name") == "TEST Diwali Boost"]
        assert len(match) >= 1
        bid = match[-1]["id"]
        # Delete
        r2 = session.delete(f"{BASE_URL}/api/loyalty/festival-boosters/{bid}")
        assert r2.status_code == 200, r2.text
        remaining_ids = [b["id"] for b in r2.json()["boosters"]]
        assert bid not in remaining_ids


# ---------- Simulator ----------
class TestSimulator:
    def _set_mode(self, session, original_config, mode):
        body = copy.deepcopy(original_config)
        body["earn_mode"] = mode
        # ensure min_bill_for_earn doesn't block
        body["min_bill_for_earn"] = 500.0
        r = session.put(f"{BASE_URL}/api/loyalty/config", json=body)
        assert r.status_code == 200, r.text

    def test_simulate_default_mode(self, session, original_config):
        self._set_mode(session, original_config, "points_per_spend")
        r = session.post(f"{BASE_URL}/api/loyalty/simulate",
                         json={"bill_amount": 5000, "tier": "gold"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "points" in data and "breakdown" in data and "explanation" in data
        assert data["points"] > 0
        steps = [b["step"] for b in data["breakdown"]]
        assert "Base earn" in steps
        # Gold has earn_multiplier 1.25 by default -> Tier multiplier present
        assert any(s == "Tier multiplier" for s in steps)

    def test_simulate_below_min_bill(self, session, original_config):
        self._set_mode(session, original_config, "points_per_spend")
        r = session.post(f"{BASE_URL}/api/loyalty/simulate",
                         json={"bill_amount": 100, "tier": "silver"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["points"] == 0
        assert "below" in data["explanation"].lower() or "min" in data["explanation"].lower()

    def test_simulate_percent_of_spend_mode(self, session, original_config):
        self._set_mode(session, original_config, "percent_of_spend")
        r = session.post(f"{BASE_URL}/api/loyalty/simulate",
                         json={"bill_amount": 5000, "tier": "silver"})
        assert r.status_code == 200, r.text
        data = r.json()
        base_step = next(b for b in data["breakdown"] if b["step"] == "Base earn")
        assert "%" in base_step["detail"], f"Base step detail should show percent: {base_step}"
        # percent_of_spend default 5 -> 250 base
        assert base_step["points"] == pytest.approx(250.0, rel=0.01)
        # Reset back to points_per_spend
        self._set_mode(session, original_config, "points_per_spend")

    def test_simulate_store_type_multiplier(self, session, original_config):
        # Set online store-type multiplier to 1.5
        body = copy.deepcopy(original_config)
        body["earn_mode"] = "points_per_spend"
        body["store_type_multipliers"] = {"online": 1.5, "offline": 1.0}
        body["min_bill_for_earn"] = 500.0
        r0 = session.put(f"{BASE_URL}/api/loyalty/config", json=body)
        assert r0.status_code == 200, r0.text
        r = session.post(f"{BASE_URL}/api/loyalty/simulate",
                         json={"bill_amount": 5000, "tier": "silver", "store_type": "online"})
        data = r.json()
        steps = [b["step"] for b in data["breakdown"]]
        assert "Store-type" in steps

    def test_simulate_category_multiplier(self, session, original_config):
        body = copy.deepcopy(original_config)
        body["earn_mode"] = "points_per_spend"
        body["category_multipliers"] = {"footwear": 2.0}
        body["min_bill_for_earn"] = 500.0
        r0 = session.put(f"{BASE_URL}/api/loyalty/config", json=body)
        assert r0.status_code == 200, r0.text
        r = session.post(f"{BASE_URL}/api/loyalty/simulate",
                         json={"bill_amount": 5000, "tier": "silver", "category": "footwear"})
        data = r.json()
        steps = [b["step"] for b in data["breakdown"]]
        assert "Category" in steps

    def test_simulate_festival_booster_applied(self, session, original_config):
        # Add a booster valid on a fixed date, applies_to=all
        booster = {
            "name": "TEST Sim Boost",
            "start_date": "2026-06-01",
            "end_date": "2026-06-30",
            "multiplier": 3.0,
            "applies_to": "all",
        }
        r0 = session.post(f"{BASE_URL}/api/loyalty/festival-boosters", json=booster)
        assert r0.status_code == 200
        bid = next(b["id"] for b in r0.json()["boosters"] if b.get("name") == "TEST Sim Boost")
        try:
            r = session.post(f"{BASE_URL}/api/loyalty/simulate",
                             json={"bill_amount": 1000, "tier": "silver",
                                   "bill_date": "2026-06-15"})
            data = r.json()
            steps = [b["step"] for b in data["breakdown"]]
            assert "Festival booster" in steps, f"breakdown missing booster: {data['breakdown']}"
        finally:
            session.delete(f"{BASE_URL}/api/loyalty/festival-boosters/{bid}")
