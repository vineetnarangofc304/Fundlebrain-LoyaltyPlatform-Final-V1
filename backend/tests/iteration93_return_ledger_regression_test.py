"""
Iteration 93 - Regression test for POS return ledger attribution fix.

Bug: /api/pos/returnOrder previously wrote reversal ledger row with ONLY customer_id
(no customer_mobile/bill_number/ledger_kind). This made the return invisible when
points_ledger is queried by customer_mobile only (customer-by-mobile endpoint), and
also hid it from the Customer 360 timeline.

Fix asserted here:
- After purchase + return, points_ledger row for the return MUST have:
    customer_mobile, bill_number (starts with 'RET-'), ledger_kind='return',
    points < 0 (negative reversal).
- customer_360 (by id): points_ledger contains BOTH earn row and return/adjust row.
- customer-by-mobile (filters by customer_mobile ONLY): MUST include the return row
  (this is the core regression check).
- recent_transactions in both endpoints includes the RET- bill with is_return true.
- Balance = credited - reversed.
"""
import os
import time
import asyncio
import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE = None
with open("/app/frontend/.env") as f:
    for line in f:
        if line.startswith("REACT_APP_BACKEND_URL"):
            BASE = line.split("=", 1)[1].strip()
BASE = BASE.rstrip("/")

POS_API = BASE + "/api/pos"
POS_KEY = "ZFQWql7I3vCH0ckuWmA8zVKDDJWYPBtoQGLruEnRrFI"
POS_HEAD = {"x-api-key": POS_KEY, "Content-Type": "application/json"}

CRM_EMAIL = "superadmin@fundle.io"
CRM_PASS = "Fundle@2026"

MOBILE = "9812345670"
BILL = f"QATEST-{int(time.time())}"
MERCHANT = "KAZO_FUNDLE"
STORE = "K00055"

# Shared state across tests (module scoped fixture would be nicer but keep simple)
STATE = {}


@pytest.fixture(scope="module")
def auth_token():
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": CRM_EMAIL, "password": CRM_PASS}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:300]}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"No token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="module", autouse=True)
def cleanup_at_end():
    yield
    async def _c():
        mongo = os.environ.get("MONGO_URL")
        dbname = os.environ.get("DB_NAME")
        if not mongo or not dbname:
            # try backend/.env
            with open("/app/backend/.env") as f:
                for line in f:
                    if line.startswith("MONGO_URL=") and not mongo:
                        os.environ["MONGO_URL"] = line.split("=", 1)[1].strip()
                    if line.startswith("DB_NAME=") and not dbname:
                        os.environ["DB_NAME"] = line.split("=", 1)[1].strip()
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        cust = await db.customers.find_one({"mobile": MOBILE})
        cid = cust.get("id") if cust else None
        await db.transactions.delete_many({"customer_mobile": MOBILE})
        q = {"customer_mobile": MOBILE}
        if cid:
            q = {"$or": [{"customer_mobile": MOBILE}, {"customer_id": cid}]}
        await db.points_ledger.delete_many(q)
        await db.customers.delete_many({"mobile": MOBILE})
        print(f"CLEANED {MOBILE}")
    asyncio.run(_c())


def test_01_pos_add_point_earn():
    """POS purchase earns points and credits balance."""
    payload = {
        "merchant_id": MERCHANT, "customer_key": STORE,
        "customer": {"mobile": MOBILE, "name": "QA Return Regression"},
        "transaction": {
            "number": BILL, "amount": 2000, "net_amount": 2000,
            "taxes": [], "order_time": "",
            "items": [{"name": "Dress", "quantity": 1, "total": 2000, "category": "Apparel"}],
            "payment_mode": [{"name": "Cash"}],
        },
    }
    r = requests.post(f"{POS_API}/posAddPoint", headers=POS_HEAD, json=payload, timeout=60)
    assert r.status_code == 200, f"posAddPoint failed: {r.status_code} {r.text[:400]}"
    data = r.json()
    resp = data.get("response") or data.get("data") or data
    earned = resp.get("points_earned", 0)
    new_balance = resp.get("new_balance", 0)
    assert earned > 0, f"Expected points_earned > 0, got {earned}. Full: {data}"
    assert new_balance > 0, f"Expected new_balance > 0, got {new_balance}"
    STATE["credited"] = new_balance
    STATE["earned"] = earned
    print(f"EARN OK: earned={earned}, balance={new_balance}")


def test_02_return_order():
    """POS return reverses some portion of the earn."""
    payload = {
        "merchant_id": MERCHANT, "customer_key": STORE, "mobile": MOBILE,
        "transaction": {
            "number": BILL,
            "return_amount": -800, "return_net_amount": -800,
            "return_loyalty_gross_amount": -800,
        },
    }
    r = requests.post(f"{POS_API}/returnOrder", headers=POS_HEAD, json=payload, timeout=60)
    assert r.status_code == 200, f"returnOrder failed: {r.status_code} {r.text[:400]}"
    data = r.json()
    print(f"RETURN OK: {data}")
    STATE["return_response"] = data


def test_03_ledger_by_mobile_only_has_return_row():
    """CORE REGRESSION CHECK: points_ledger queried by customer_mobile ONLY
    must return the return/adjust row (previously missing)."""
    async def _q():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        rows = await db.points_ledger.find({"customer_mobile": MOBILE}).to_list(50)
        return rows
    rows = asyncio.run(_q())
    assert len(rows) >= 2, f"Expected >=2 ledger rows keyed by mobile, got {len(rows)}: {rows}"
    return_rows = [r for r in rows if (r.get("points", 0) < 0) or r.get("ledger_kind") == "return"]
    assert return_rows, f"No return row in ledger-by-mobile! rows={rows}"
    rr = return_rows[0]
    assert rr.get("customer_mobile") == MOBILE, f"customer_mobile missing on return row: {rr}"
    bn = rr.get("bill_number") or ""
    assert bn.startswith("RET-"), f"bill_number should start with RET-, got: {bn}"
    assert rr.get("ledger_kind") == "return", f"ledger_kind should be 'return', got: {rr.get('ledger_kind')}"
    assert rr.get("points", 0) < 0, f"return points should be negative, got {rr.get('points')}"
    print(f"Return ledger row OK: {rr}")


def test_04_customer_360_by_id_contains_earn_and_return(auth_token):
    """GET /api/dashboard/customer-360/{customer_id} returns points_ledger
    with earn row AND return/adjust row."""
    # look up customer id
    async def _cust():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        return await db.customers.find_one({"mobile": MOBILE})
    cust = asyncio.run(_cust())
    assert cust, "Customer not created"
    cid = cust["id"]
    STATE["cid"] = cid

    h = {"Authorization": f"Bearer {auth_token}"}
    r = requests.get(f"{BASE}/api/dashboard/customer-360/{cid}", headers=h, timeout=30)
    assert r.status_code == 200, f"customer-360 failed: {r.status_code} {r.text[:400]}"
    data = r.json()
    ledger = data.get("points_ledger") or []
    assert ledger, f"points_ledger empty in customer-360 response"
    earn_rows = [l for l in ledger if (l.get("points", 0) > 0) and l.get("ledger_kind") != "return"]
    ret_rows = [l for l in ledger if (l.get("points", 0) < 0) or l.get("ledger_kind") == "return"]
    assert earn_rows, f"No earn row in ledger: {ledger}"
    assert ret_rows, f"No return/adjust row in ledger: {ledger}"

    rr = ret_rows[0]
    assert rr.get("customer_mobile") == MOBILE, f"return row missing customer_mobile: {rr}"
    assert (rr.get("bill_number") or "").startswith("RET-"), f"bill_number not RET-: {rr}"

    # recent_transactions must include RET-
    rt = data.get("recent_transactions") or data.get("transactions") or []
    ret_tx = [t for t in rt if (t.get("bill_number") or "").startswith("RET-") or t.get("is_return")]
    assert ret_tx, f"recent_transactions missing RET-/is_return row: {rt}"
    assert any(t.get("is_return") for t in ret_tx), f"No is_return=true tx: {ret_tx}"

    # balance sanity
    balance = data.get("customer", {}).get("points_balance") or data.get("points_balance")
    print(f"customer-360 balance={balance}, earn_rows={len(earn_rows)}, ret_rows={len(ret_rows)}")


def test_05_customer_by_mobile_contains_return(auth_token):
    """GET /api/fundlebrain/customer-by-mobile/{mobile} filters ledger by
    customer_mobile ONLY. MUST include the return row (regression check)."""
    h = {"Authorization": f"Bearer {auth_token}"}
    # Route mounted under /api/dashboard (router prefix) - review-request path
    # /api/fundlebrain/... is wrong; verified in server.py
    r = requests.get(f"{BASE}/api/dashboard/customer-by-mobile/{MOBILE}", headers=h, timeout=30)
    assert r.status_code == 200, f"customer-by-mobile failed: {r.status_code} {r.text[:400]}"
    data = r.json()
    ledger = data.get("points_ledger") or []
    assert ledger, f"points_ledger empty in customer-by-mobile: {data}"
    ret_rows = [l for l in ledger if (l.get("points", 0) < 0) or l.get("ledger_kind") == "return"]
    assert ret_rows, f"REGRESSION: return row missing in customer-by-mobile ledger: {ledger}"
    rr = ret_rows[0]
    assert (rr.get("bill_number") or "").startswith("RET-"), f"bill_number not RET-: {rr}"
    # customer-by-mobile serializer projects type='adjust' (ledger_kind not in projection).
    # DB-level ledger_kind='return' is verified in test_03.
    assert rr.get("type") in ("adjust", "return"), f"row type should be adjust/return: {rr}"

    rt = data.get("recent_transactions") or data.get("transactions") or []
    assert any(
        (t.get("bill_number") or "").startswith("RET-")
        and (t.get("is_return") or t.get("return_marker") == "Return" or t.get("points_earned", 0) < 0)
        for t in rt
    ), f"recent_transactions missing RET- return row: {rt}"
    print(f"customer-by-mobile ledger rows={len(ledger)}, return rows={len(ret_rows)}")


def test_06_balance_math():
    """Balance = credited - reversed (via DB check)."""
    async def _q():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        cust = await db.customers.find_one({"mobile": MOBILE})
        rows = await db.points_ledger.find({"customer_mobile": MOBILE}).to_list(50)
        return cust, rows
    cust, rows = asyncio.run(_q())
    total = sum(r.get("points", 0) for r in rows)
    bal = cust.get("points_balance", 0)
    assert bal == total, f"Balance {bal} != sum(ledger.points) {total}. rows={rows}"
    assert bal >= 0, f"Balance should be non-negative: {bal}"
    print(f"Balance math OK: balance={bal}, ledger sum={total}")
