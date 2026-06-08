"""Iteration 22 — returnOrder bill-number drop + Legacy Reports date-range filters.

Covers:
1. POST /api/pos/returnOrder no longer requires the original bill number:
   - mobile + return_loyalty_gross_amount but NO bill number  → 200, points reversed.
   - mobile + an UNKNOWN bill number                          → 200 (falls back to mobile).
   - UNREGISTERED mobile                                      → 400 (no loyalty customer).
   - missing mobile                                           → 400 (required field).
   Customer points_balance / lifetime_spend are decremented by the reversal.
2. Legacy report endpoints accept start_date/end_date without error and still work
   without them (no regression): repeat-customers, top-customers,
   location-wise-customers, active-coupons, expiry-points.

All test-created return rows + ledger entries are cleaned up and the customer is
restored to its original balance.
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
    assert tok
    return {"Authorization": f"Bearer {tok}"}


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


@pytest.fixture(scope="module")
def test_customer():
    """A registered customer with a healthy points balance to reverse against."""
    async def _get():
        db = _mongo()
        return await db["customers"].find_one(
            {"points_balance": {"$gt": 200}}, {"_id": 0}
        )
    cust = asyncio.run(_get())
    assert cust, "need a customer with points to test returns"
    return cust


def _pos_headers(pos_cred):
    return {"x-api-key": pos_cred["api_key"], "Content-Type": "application/json"}


def _base_payload(pos_cred, mobile):
    return {
        "merchant_id": pos_cred["merchant_id"],
        "customer_key": pos_cred["customer_key"],
        "mobile": mobile,
    }


# ---------------------------------------------------------------------------
# 1. returnOrder — bill number is no longer required
# ---------------------------------------------------------------------------
class TestReturnOrderNoBill:
    def test_no_bill_number_succeeds_and_reverses(self, pos_cred, test_customer):
        mobile = str(test_customer["mobile"])

        def bal():
            async def _g():
                db = _mongo()
                c = await db["customers"].find_one({"id": test_customer["id"]},
                                                   {"_id": 0, "points_balance": 1, "lifetime_spend": 1})
                return c
            return asyncio.run(_g())

        before = bal()
        payload = _base_payload(pos_cred, mobile)
        payload["transaction"] = {"return_loyalty_gross_amount": "100",
                                  "return_amount": "-100", "return_net_amount": "-100"}
        r = requests.post(f"{BASE_URL}/api/pos/returnOrder", json=payload,
                          headers=_pos_headers(pos_cred), timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status_code"] == 200, body
        order_id = body["response"]["order_id"]
        assert order_id and order_id != 0

        after = bal()
        # points reversed (>0) and lifetime_spend reduced
        assert after["points_balance"] < before["points_balance"], (before, after)
        assert after["lifetime_spend"] <= before["lifetime_spend"]

        # cleanup this return
        self._cleanup(test_customer["id"], before)

    def test_unknown_bill_falls_back_to_mobile(self, pos_cred, test_customer):
        mobile = str(test_customer["mobile"])

        async def _before():
            db = _mongo()
            return await db["customers"].find_one({"id": test_customer["id"]},
                                                  {"_id": 0, "points_balance": 1, "lifetime_spend": 1})
        before = asyncio.run(_before())

        payload = _base_payload(pos_cred, mobile)
        payload["transaction"] = {"number": "DOES-NOT-EXIST-ITER22",
                                  "return_loyalty_gross_amount": "50", "return_amount": "-50"}
        r = requests.post(f"{BASE_URL}/api/pos/returnOrder", json=payload,
                          headers=_pos_headers(pos_cred), timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["status_code"] == 200
        self._cleanup(test_customer["id"], before)

    def test_unregistered_mobile_rejected(self, pos_cred):
        payload = _base_payload(pos_cred, "9999999999")
        payload["transaction"] = {"return_loyalty_gross_amount": "50"}
        r = requests.post(f"{BASE_URL}/api/pos/returnOrder", json=payload,
                          headers=_pos_headers(pos_cred), timeout=20)
        assert r.status_code == 200, r.text  # business errors return 200 envelope
        body = r.json()
        assert body["status_code"] == 400
        assert "No loyalty customer" in body["response"]["message"]

    def test_missing_mobile_rejected(self, pos_cred):
        payload = {"merchant_id": pos_cred["merchant_id"],
                   "customer_key": pos_cred["customer_key"],
                   "transaction": {"number": "X", "return_loyalty_gross_amount": "50"}}
        r = requests.post(f"{BASE_URL}/api/pos/returnOrder", json=payload,
                          headers=_pos_headers(pos_cred), timeout=20)
        body = r.json()
        assert body["status_code"] == 400
        assert "mobile" in body["response"]["message"].lower()

    @staticmethod
    def _cleanup(customer_id, restore_to):
        async def _c():
            db = _mongo()
            await db["transactions"].delete_many(
                {"is_return": True, "customer_id": customer_id,
                 "original_bill_number": {"$in": [None, "DOES-NOT-EXIST-ITER22"]}})
            await db["points_ledger"].delete_many(
                {"reference_type": "return", "customer_id": customer_id})
            await db["customers"].update_one(
                {"id": customer_id},
                {"$set": {"points_balance": restore_to["points_balance"],
                          "lifetime_spend": restore_to["lifetime_spend"]}})
        asyncio.run(_c())


# ---------------------------------------------------------------------------
# 2. Legacy reports accept date filters (and still work without them)
# ---------------------------------------------------------------------------
class TestLegacyReportDateFilters:
    ENDPOINTS = [
        ("legacy-reports/repeat-customers", {"min_visits": 2}),
        ("legacy-reports/top-customers", {"by": "purchase"}),
        ("legacy-reports/location-wise-customers", {}),
        ("legacy-reports/active-coupons", {}),
        ("legacy-reports/expiry-points", {}),
    ]

    @pytest.mark.parametrize("ep,base_params", ENDPOINTS)
    def test_no_date_filter_ok(self, auth_headers, ep, base_params):
        r = requests.get(f"{BASE_URL}/api/{ep}", params=base_params,
                         headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        assert "rows" in r.json()

    @pytest.mark.parametrize("ep,base_params", ENDPOINTS)
    def test_with_date_filter_ok(self, auth_headers, ep, base_params):
        params = {**base_params, "start_date": "2026-01-01", "end_date": "2026-12-31"}
        r = requests.get(f"{BASE_URL}/api/{ep}", params=params,
                         headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        assert "rows" in r.json()

    def test_date_filter_narrows_results(self, auth_headers):
        """A far-future window should return no/equal-or-fewer repeat customers."""
        wide = requests.get(f"{BASE_URL}/api/legacy-reports/repeat-customers",
                            params={"min_visits": 2}, headers=auth_headers, timeout=20).json()
        future = requests.get(f"{BASE_URL}/api/legacy-reports/repeat-customers",
                              params={"min_visits": 2, "start_date": "2099-01-01",
                                      "end_date": "2099-12-31"},
                              headers=auth_headers, timeout=20).json()
        assert len(future.get("rows", [])) <= len(wide.get("rows", []))
        assert len(future.get("rows", [])) == 0
