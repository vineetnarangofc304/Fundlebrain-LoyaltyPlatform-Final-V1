"""Iteration 20 — Loyalty upgrade_bonus + strict store validation regression.

Verifies:
1. GET /api/loyalty/config returns tier_rules with `upgrade_bonus` integer on each tier.
2. PUT /api/loyalty/config (super_admin) persists updated upgrade_bonus values.
3. POS rejection on unknown store code is logged into api_logs.
4. Tier promotion credits upgrade_bonus + writes a points_ledger entry of
   type='bonus' / reference_type='tier_upgrade' on the bill that crosses the slab.
"""
import os
import time
import uuid
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
    assert tok, r.text
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
# Loyalty config: upgrade_bonus field surfaces and persists
# ---------------------------------------------------------------------------
class TestLoyaltyConfigUpgradeBonus:
    def test_get_config_returns_upgrade_bonus_on_each_tier(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/loyalty/config", headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        cfg = r.json()
        tiers = cfg.get("tier_rules") or []
        assert len(tiers) >= 2, "tier_rules should be populated"
        for t in tiers:
            assert "upgrade_bonus" in t, f"tier {t.get('tier')} missing upgrade_bonus"
            assert isinstance(t["upgrade_bonus"], int), t

    def test_put_config_persists_upgrade_bonus(self, auth_headers):
        # GET current
        cur = requests.get(f"{BASE_URL}/api/loyalty/config", headers=auth_headers, timeout=15).json()
        tiers = cur.get("tier_rules") or []
        assert tiers, "no tiers"

        # Bump every upgrade_bonus by a unique offset, then put back
        marker = 1234
        for t in tiers:
            t["upgrade_bonus"] = int(t.get("upgrade_bonus") or 0) + marker

        body = dict(cur)
        body["tier_rules"] = tiers
        body.pop("_id", None)
        r = requests.put(f"{BASE_URL}/api/loyalty/config", headers=auth_headers, json=body, timeout=15)
        assert r.status_code == 200, r.text

        # Re-fetch and check
        cur2 = requests.get(f"{BASE_URL}/api/loyalty/config", headers=auth_headers, timeout=15).json()
        new_tiers = {t["tier"]: t["upgrade_bonus"] for t in cur2["tier_rules"]}
        for t in tiers:
            assert new_tiers.get(t["tier"]) == t["upgrade_bonus"], (
                f"upgrade_bonus not persisted for {t['tier']}: got {new_tiers.get(t['tier'])}, expected {t['upgrade_bonus']}")

        # Restore (subtract marker back) for idempotency
        for t in tiers:
            t["upgrade_bonus"] = int(t["upgrade_bonus"]) - marker
        body["tier_rules"] = tiers
        rr = requests.put(f"{BASE_URL}/api/loyalty/config", headers=auth_headers, json=body, timeout=15)
        assert rr.status_code == 200, rr.text


# ---------------------------------------------------------------------------
# Strict store validation rejection is logged into api_logs
# ---------------------------------------------------------------------------
class TestPOSRejectionLogged:
    def test_unknown_store_logs_api_monitor_400(self, pos_cred):
        unknown_key = f"PYT_NOLOG_{int(time.time())}"
        bill = f"PYT_NOLOG_BILL_{int(time.time())}"
        r = requests.post(
            f"{BASE_URL}/api/pos/posAddPoint",
            headers={"x-api-key": pos_cred["api_key"], "Content-Type": "application/json"},
            json={
                "merchant_id": pos_cred["merchant_id"],
                "customer_key": unknown_key,
                "customer": {"mobile": "9266681235"},
                "transaction": {"number": bill, "net_amount": 100, "loyalty_flag": "1"},
            },
            timeout=20,
        )
        body = r.json()
        inner = body.get("status_code", r.status_code)
        assert inner == 400, body

        # api_logs entry should exist with 400 status for /api/pos/posAddPoint
        async def _find_log():
            db = _mongo()
            # search recent logs
            cur = db["api_logs"].find({"endpoint": {"$regex": "posAddPoint"}, "status_code": 400})
            cur = cur.sort([("created_at", -1)]).limit(20)
            return [doc async for doc in cur]
        logs = asyncio.run(_find_log())
        assert logs, "expected at least one api_logs entry with status_code=400 for posAddPoint"


# ---------------------------------------------------------------------------
# Upgrade bonus credited on tier promotion
# ---------------------------------------------------------------------------
class TestUpgradeBonusCredit:
    def test_tier_promotion_credits_upgrade_bonus(self, pos_cred, auth_headers):
        """Set a known upgrade_bonus on the 'gold' tier, then post a bill big
        enough to push a fresh customer's lifetime_spend across the gold slab.
        Verify (a) points_ledger entry of type='bonus' / reference_type='tier_upgrade'
        with the configured upgrade_bonus and (b) customer's points_balance reflects it.
        """
        # 1) Get current cfg + find gold tier slab
        cur = requests.get(f"{BASE_URL}/api/loyalty/config", headers=auth_headers, timeout=15).json()
        tiers = sorted(cur.get("tier_rules") or [], key=lambda t: t.get("min_spend", 0))
        # find 'gold' (or highest tier) — pick something we can promote into
        gold = next((t for t in tiers if t.get("tier", "").lower() == "gold"), None)
        if not gold:
            pytest.skip("no 'gold' tier in config")
        TEST_BONUS = 4321  # easy to spot in ledger
        original_bonus = int(gold.get("upgrade_bonus") or 0)
        gold["upgrade_bonus"] = TEST_BONUS

        body = dict(cur)
        body["tier_rules"] = tiers
        body.pop("_id", None)
        rp = requests.put(f"{BASE_URL}/api/loyalty/config", headers=auth_headers, json=body, timeout=15)
        assert rp.status_code == 200, rp.text

        # 2) Provision a store
        store_code = f"PYT_PROMO_{int(time.time())}"
        store_id = uuid.uuid4().hex
        test_mobile = f"9{int(time.time()) % 1000000000:09d}"  # fresh mobile per run

        async def _seed_store():
            db = _mongo()
            await db["stores"].insert_one({
                "id": store_id,
                "code": store_code,
                "name": "Pytest Promo Outlet",
                "city": "", "state": "", "region": "", "address": "",
                "is_active": True,
                "source": "pytest_seed",
                "pos_merchant_id": pos_cred["merchant_id"],
                "pos_customer_key": store_code,
                "created_at": "2026-01-01T00:00:00+00:00",
            })

        asyncio.run(_seed_store())

        try:
            # 3) Post a big bill > gold.min_spend so the fresh customer crosses into gold
            big_amount = int(gold.get("min_spend") or 50000) + 5000
            bill = f"PYT_PROMO_BILL_{int(time.time())}"
            r = requests.post(
                f"{BASE_URL}/api/pos/posAddPoint",
                headers={"x-api-key": pos_cred["api_key"], "Content-Type": "application/json"},
                json={
                    "merchant_id": pos_cred["merchant_id"],
                    "customer_key": store_code,
                    "customer": {"mobile": test_mobile},
                    "transaction": {"number": bill, "net_amount": big_amount, "loyalty_flag": "1"},
                },
                timeout=30,
            )
            assert r.status_code == 200 and r.json().get("status_code") == 200, r.text

            # 4) Verify ledger + customer
            async def _verify():
                db = _mongo()
                cust = await db["customers"].find_one({"mobile": test_mobile}, {"_id": 0})
                ledger = None
                if cust:
                    ledger = await db["points_ledger"].find_one({
                        "customer_id": cust["id"],
                        "type": "bonus",
                        "reference_type": "tier_upgrade",
                    }, {"_id": 0})
                return cust, ledger

            cust, ledger = asyncio.run(_verify())
            assert cust, "customer should exist"
            assert ledger, "expected points_ledger 'bonus' entry with reference_type='tier_upgrade'"
            assert int(ledger.get("points") or 0) == TEST_BONUS, (
                f"upgrade_bonus credited mismatch: ledger={ledger}, expected {TEST_BONUS}")
            # Customer's points_balance should be at least the bonus (plus earned base)
            assert int(cust.get("points_balance") or 0) >= TEST_BONUS, cust
            assert (cust.get("tier") or "").lower() in ("gold", "platinum"), cust
        finally:
            # Cleanup: restore upgrade_bonus + delete seeded data
            gold["upgrade_bonus"] = original_bonus
            body["tier_rules"] = tiers
            requests.put(f"{BASE_URL}/api/loyalty/config", headers=auth_headers, json=body, timeout=15)

            async def _cleanup():
                db = _mongo()
                await db["stores"].delete_many({"pos_customer_key": store_code})
                cust = await db["customers"].find_one({"mobile": test_mobile}, {"_id": 0})
                if cust:
                    await db["points_ledger"].delete_many({"customer_id": cust["id"]})
                await db["customers"].delete_many({"mobile": test_mobile})
                await db["transactions"].delete_many({"bill_number": {"$regex": f"^PYT_PROMO_BILL"}})
            asyncio.run(_cleanup())
