"""Iteration 64 — Full E2E validation of the 5 client-requested changes.

Covered here (complementary to iteration63):
  A. POS posAddCustomer — invalid Indian mobile is rejected with HTTP 400
     (response.status_code==400 in the wrapper) and a valid mobile registers
     a new member, credits the GLOBAL welcome bonus exactly once, writes a
     points_ledger entry with reference_type='welcome'.
  B. GET /api/analytics/customer-dashboard — lifecycle_split returns the 3 keys
     {zero_bill, one_timer, repeat} with non-negative ints.
  C. GET /api/message-log — returns rows + total; filter by channel=sms works;
     filter by mobile (trailing digits) works; rows expose the new fields.
  D. GET /api/live-monitor/transactions — exposes is_lost_customer / raw_mobile
     fields on every row.

Runs against the EXTERNAL backend URL (REACT_APP_BACKEND_URL) per the request,
because POS endpoints are scoped to that URL. Cleans up its own data.
"""
import os
import random
import re
import time
from typing import Optional

import httpx
import pytest
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
# also load frontend env to pick up REACT_APP_BACKEND_URL
_FE = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", ".env")
if os.path.exists(_FE):
    load_dotenv(_FE, override=False)

EXT = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
assert EXT, "REACT_APP_BACKEND_URL is required"
API = f"{EXT}/api"

POS_KEY = "ZFQWql7I3vCH0ckuWmA8zVKDDJWYPBtoQGLruEnRrFI"
MERCHANT = "KAZO_FUNDLE"
HEAD_POS = {"x-api-key": POS_KEY, "Content-Type": "application/json"}

ADMIN_EMAIL = os.environ.get("SUPER_ADMIN_EMAIL", "superadmin@fundle.io")
ADMIN_PASSWORD = os.environ.get("SUPER_ADMIN_PASSWORD", "Fundle@2026")


# ---------- helpers ----------
def _admin_token() -> Optional[str]:
    r = httpx.post(f"{API}/auth/login",
                   json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    if r.status_code != 200:
        return None
    j = r.json()
    return j.get("access_token") or j.get("token")


def _store_code_sync() -> Optional[str]:
    import asyncio
    async def _f():
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        s = await db["stores"].find_one({"pos_merchant_id": MERCHANT}, {"_id": 0, "code": 1})
        return s["code"] if s else None
    return asyncio.run(_f())


def _welcome_bonus_sync() -> int:
    import asyncio
    async def _f():
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        cfg = await db["loyalty_config"].find_one({"id": "default"}, {"_id": 0}) or {}
        try:
            return int(float(cfg.get("welcome_bonus", 0) or 0))
        except Exception:
            return 0
    return asyncio.run(_f())


def _cleanup_sync(mobiles, bills):
    import asyncio
    async def _f():
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        if mobiles:
            await db["customers"].delete_many({"mobile": {"$in": mobiles}})
            await db["points_ledger"].delete_many({"customer_mobile": {"$in": mobiles}})
        if bills:
            await db["transactions"].delete_many({"bill_number": {"$in": bills}})
    asyncio.run(_f())


@pytest.fixture(scope="module")
def admin_headers():
    tok = _admin_token()
    if not tok:
        pytest.skip("super admin login failed — cannot test admin endpoints")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def store_code():
    ck = _store_code_sync()
    if not ck:
        pytest.skip("no provisioned KAZO_FUNDLE store")
    return ck


# ---------- A. posAddCustomer mobile gate + welcome bonus ----------
def test_pos_add_customer_rejects_invalid_mobile_and_credits_welcome_once(store_code):
    welcome = _welcome_bonus_sync()
    good = f"97{random.randint(10000000, 99999999)}"
    bills = []
    mobiles = [good]

    try:
        # 1) Invalid mobile → wrapper status_code 400 (HTTP 200 envelope per pos contract)
        r = httpx.post(f"{API}/pos/posAddCustomer", headers=HEAD_POS, timeout=20, json={
            "merchant_id": MERCHANT, "customer_key": store_code,
            "customer": {"mobile": "12345", "name": "Bad Mobile"}})
        assert r.status_code == 200
        body = r.json()
        # Per pos contract, errors return status_code in the body envelope
        assert body.get("status_code") == 400, body

        # 1b) 10-digit but starts with 5 → invalid Indian
        r = httpx.post(f"{API}/pos/posAddCustomer", headers=HEAD_POS, timeout=20, json={
            "merchant_id": MERCHANT, "customer_key": store_code,
            "customer": {"mobile": "5000000000", "name": "Bad Prefix"}})
        assert r.json().get("status_code") == 400, r.json()

        # 2) Valid mobile → registers and credits welcome bonus once
        r = httpx.post(f"{API}/pos/posAddCustomer", headers=HEAD_POS, timeout=20, json={
            "merchant_id": MERCHANT, "customer_key": store_code,
            "customer": {"mobile": good, "name": "Iter64 Tester"}})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("status_code") == 200, body

        # verify DB-side: customer exists with welcome bonus applied
        import asyncio
        async def _check():
            db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
            cust = await db["customers"].find_one({"mobile": good}, {"_id": 0})
            assert cust is not None, "customer not created"
            assert cust.get("welcome_bonus_given") is (welcome > 0)
            assert int(cust.get("points_balance", -1)) == welcome
            assert int(cust.get("lifetime_points_earned", -1)) == welcome
            n = await db["points_ledger"].count_documents(
                {"customer_mobile": good, "reference_type": "welcome"})
            assert n == (1 if welcome > 0 else 0), f"welcome ledger count {n}"
        asyncio.run(_check())

        # 3) Re-register (update) — must NOT double-credit welcome
        r = httpx.post(f"{API}/pos/posAddCustomer", headers=HEAD_POS, timeout=20, json={
            "merchant_id": MERCHANT, "customer_key": store_code,
            "customer": {"mobile": good, "name": "Iter64 Tester Updated"}})
        assert r.json().get("status_code") == 200

        async def _check2():
            db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
            n = await db["points_ledger"].count_documents(
                {"customer_mobile": good, "reference_type": "welcome"})
            assert n == (1 if welcome > 0 else 0), f"after re-register welcome ledger count={n} (must remain 1)"
            cust = await db["customers"].find_one({"mobile": good}, {"_id": 0})
            # balance unchanged by an update
            assert int(cust.get("points_balance", -1)) == welcome
        asyncio.run(_check2())
    finally:
        _cleanup_sync(mobiles, bills)


# ---------- B. customer-dashboard lifecycle_split 3-way ----------
def test_customer_dashboard_lifecycle_split_three_way(admin_headers):
    r = httpx.get(f"{API}/analytics/customer-dashboard", headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    ls = j.get("lifecycle_split")
    assert ls and isinstance(ls, dict), f"lifecycle_split missing: {j.keys()}"
    for k in ("zero_bill", "one_timer", "repeat"):
        assert k in ls, f"key '{k}' missing in lifecycle_split: {ls}"
        assert isinstance(ls[k].get("count"), int) and ls[k]["count"] >= 0
        assert ls[k].get("lifetime_spend") is not None


# ---------- C. message-log filters + fields ----------
def test_message_log_list_and_filters(admin_headers):
    r = httpx.get(f"{API}/message-log", headers=admin_headers,
                  params={"limit": 50}, timeout=20)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "rows" in j and "total" in j
    assert isinstance(j["rows"], list)
    assert j["total"] >= 0
    # New per-row fields exist on at least one row (if any rows present)
    if j["rows"]:
        sample = j["rows"][0]
        # The new fields the message-log writer adds
        for f in ("channel", "status", "mobile", "timestamp"):
            assert f in sample, f"row missing '{f}': {list(sample.keys())[:20]}"

    # Filter by channel=sms
    r2 = httpx.get(f"{API}/message-log", headers=admin_headers,
                   params={"channel": "sms", "limit": 25}, timeout=20)
    assert r2.status_code == 200
    j2 = r2.json()
    assert all(row.get("channel") == "sms" for row in j2["rows"])

    # Trailing-digits mobile filter — pick last 5 digits of any sample row mobile
    if j["rows"]:
        any_m = next((r.get("mobile") for r in j["rows"] if r.get("mobile")), None)
        if any_m:
            digits = re.sub(r"\D", "", str(any_m))[-5:]
            if digits:
                r3 = httpx.get(f"{API}/message-log", headers=admin_headers,
                               params={"mobile": digits, "limit": 20}, timeout=20)
                assert r3.status_code == 200
                for row in r3.json()["rows"]:
                    assert re.sub(r"\D", "", str(row.get("mobile", ""))).endswith(digits)


# ---------- D. live-monitor exposes lost-customer fields ----------
def test_live_monitor_transactions_expose_lost_customer_fields(admin_headers):
    r = httpx.get(f"{API}/live-monitor/transactions",
                  headers=admin_headers, params={"limit": 50}, timeout=20)
    assert r.status_code == 200, r.text
    j = r.json()
    rows = j.get("rows") if isinstance(j, dict) else j
    assert isinstance(rows, list)
    if rows:
        # Every row should expose the new fields (even if False/None)
        for row in rows[:20]:
            assert "is_lost_customer" in row, f"row missing 'is_lost_customer': {list(row.keys())[:20]}"
            assert "raw_mobile" in row, f"row missing 'raw_mobile': {list(row.keys())[:20]}"
