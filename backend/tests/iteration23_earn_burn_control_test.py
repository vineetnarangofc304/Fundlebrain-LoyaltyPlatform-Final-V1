"""Iteration 23 — Earn & Burn control (master switches + scheduled pause windows)
+ Live Monitor RETURN type / receive time.

Covers:
1. PUT /api/loyalty/earn-burn-control flips earn_enabled / burn_enabled and persists.
2. With earning OFF, posAddPoint settles a sale with points_earned == 0; with earning
   back ON the same-shaped bill earns > 0.
3. POST /api/loyalty/pauses validates (start<=end, at least one of earn/burn) and
   appends a window; PATCH toggle flips active; DELETE removes it.
4. A burn pause window covering today blocks posRedeemPointRequest (400); once removed
   the redeem request issues an OTP again (200).
5. GET /api/live-monitor/transactions exposes `received_at` and `is_return`.

All POS test data is cleaned up and the loyalty config is reset to earn/burn ON, no pauses.
"""
import os
import asyncio
import datetime as dt
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
TEST_MOBILE = "9000000088"
STORE_KEY = "K00055"  # a provisioned store code


def _mongo():
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def auth_headers():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "portal": "crm"},
                      timeout=20)
    assert r.status_code == 200, r.text
    tok = r.json().get("token") or r.json().get("access_token")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def pos_headers():
    async def _get():
        db = _mongo()
        return await db["pos_credentials"].find_one({"label": "kazo_default", "is_active": True}, {"_id": 0})
    cred = asyncio.run(_get())
    assert cred
    return {"x-api-key": cred["api_key"], "Content-Type": "application/json"}


def _now_iso():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def _cleanup():
    async def _c():
        db = _mongo()
        await db["transactions"].delete_many({"customer_mobile": TEST_MOBILE})
        await db["customers"].delete_many({"mobile": TEST_MOBILE})
        await db["loyalty_config"].update_one(
            {"id": "default"},
            {"$set": {"earn_enabled": True, "burn_enabled": True, "earn_burn_pauses": []}})
    asyncio.run(_c())


@pytest.fixture(scope="module", autouse=True)
def _around():
    _cleanup()
    yield
    _cleanup()


def _add_sale(pos_headers, bill_no):
    payload = {
        "merchant_id": "KAZO_FUNDLE", "customer_key": STORE_KEY,
        "customer": {"mobile": TEST_MOBILE, "name": "EBC Test"},
        "transaction": {"number": bill_no, "amount": "2000", "loyalty_flag": "1", "order_time": _now_iso()},
    }
    r = requests.post(f"{BASE_URL}/api/pos/posAddPoint", json=payload, headers=pos_headers, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
class TestEarnBurnMaster:
    def test_earn_off_then_on(self, auth_headers, pos_headers):
        # OFF
        r = requests.put(f"{BASE_URL}/api/loyalty/earn-burn-control",
                         json={"earn_enabled": False}, headers=auth_headers, timeout=20)
        assert r.status_code == 200 and r.json()["earn_enabled"] is False, r.text
        body = _add_sale(pos_headers, "EBC-EARN-OFF-1")
        assert body["response"]["points_earned"] == 0, body

        # ON
        r = requests.put(f"{BASE_URL}/api/loyalty/earn-burn-control",
                         json={"earn_enabled": True}, headers=auth_headers, timeout=20)
        assert r.status_code == 200 and r.json()["earn_enabled"] is True
        body = _add_sale(pos_headers, "EBC-EARN-ON-1")
        assert body["response"]["points_earned"] > 0, body


class TestPauseWindowCrud:
    def test_validation_and_crud(self, auth_headers):
        # invalid: start > end
        r = requests.post(f"{BASE_URL}/api/loyalty/pauses",
                          json={"start_date": "2026-02-10", "end_date": "2026-02-01",
                                "pause_earn": True}, headers=auth_headers, timeout=20)
        assert r.status_code == 400
        # invalid: neither earn nor burn
        r = requests.post(f"{BASE_URL}/api/loyalty/pauses",
                          json={"start_date": "2026-02-01", "end_date": "2026-02-10",
                                "pause_earn": False, "pause_burn": False}, headers=auth_headers, timeout=20)
        assert r.status_code == 400
        # valid add
        r = requests.post(f"{BASE_URL}/api/loyalty/pauses",
                          json={"label": "Crud test", "start_date": "2026-02-01",
                                "end_date": "2026-02-10", "pause_earn": True}, headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        pid = r.json()["pauses"][-1]["id"]
        # toggle
        r = requests.patch(f"{BASE_URL}/api/loyalty/pauses/{pid}/toggle", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        assert any(p["id"] == pid and p["active"] is False for p in r.json()["pauses"])
        # delete
        r = requests.delete(f"{BASE_URL}/api/loyalty/pauses/{pid}", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        assert all(p["id"] != pid for p in r.json()["pauses"])


class TestBurnPauseBlocksRedeem:
    def test_burn_pause_blocks_then_allows(self, auth_headers, pos_headers):
        # seed a customer with points and earning ON
        requests.put(f"{BASE_URL}/api/loyalty/earn-burn-control",
                     json={"earn_enabled": True, "burn_enabled": True}, headers=auth_headers, timeout=20)
        _add_sale(pos_headers, "EBC-REDEEM-SEED-1")

        today = _today()
        r = requests.post(f"{BASE_URL}/api/loyalty/pauses",
                          json={"label": "Burn blackout", "start_date": today, "end_date": today,
                                "pause_earn": False, "pause_burn": True}, headers=auth_headers, timeout=20)
        pid = r.json()["pauses"][-1]["id"]

        redeem = {"merchant_id": "KAZO_FUNDLE", "customer_key": STORE_KEY,
                  "customer_mobile": TEST_MOBILE, "points": 100,
                  "transaction": {"number": "EBC-REDEEM-BLOCKED-1"}}
        r = requests.post(f"{BASE_URL}/api/pos/posRedeemPointRequest", json=redeem, headers=pos_headers, timeout=20)
        assert r.json()["status_code"] == 400
        assert "unavailable" in r.json()["response"]["message"].lower()

        # remove pause → redeem works
        requests.delete(f"{BASE_URL}/api/loyalty/pauses/{pid}", headers=auth_headers, timeout=20)
        r = requests.post(f"{BASE_URL}/api/pos/posRedeemPointRequest", json=redeem, headers=pos_headers, timeout=20)
        assert r.json()["status_code"] == 200, r.text


class TestLiveMonitorFields:
    def test_received_at_and_is_return_present(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/live-monitor/transactions",
                         params={"start_date": "2026-05-01", "end_date": "2026-06-30", "limit": 50},
                         headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        rows = r.json().get("rows", [])
        assert rows, "expected some transactions in May-Jun 2026"
        for row in rows:
            assert "received_at" in row
            assert "is_return" in row
