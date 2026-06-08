"""Iteration 17 (updated for strict store validation) — POS store resolution.

Canonical rule (REVERSED from earlier auto-create behaviour):
customer_key IS the store code. The (merchant_id + customer_key) combo identifies
the store on every bill. STRICT_STORE_VALIDATION=true (default) means an UNKNOWN
(unprovisioned) store code is REJECTED with a 400 instead of auto-creating a store.

Coverage:
- A bill with a customer_key that matches a provisioned store SUCCEEDS (200) and
  the created transaction is linked to that store's id.
- A second bill with the same (known) customer_key reuses the same store.
- A bill with an UNKNOWN customer_key is REJECTED (400 "Unknown store code") and
  no store is auto-created for it.
"""
import os
import time
import uuid
import asyncio
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
if not BASE_URL:
    try:
        with open("/app/frontend/.env", "r") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except FileNotFoundError:
        pass
assert BASE_URL, "REACT_APP_BACKEND_URL not configured"

TEST_MOBILE = "9266681235"  # bootstrapped POS test customer


def _mongo():
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def creds():
    async def _get():
        db = _mongo()
        c = await db["pos_credentials"].find_one({"label": "kazo_default", "is_active": True}, {"_id": 0})
        return c
    cred = asyncio.run(_get())
    assert cred, "default POS credential not bootstrapped"
    return cred


@pytest.fixture(scope="module")
def provisioned_code(creds):
    """Provision a store with a known code + (merchant_id, customer_key) combo."""
    code = f"PYTEST_STORE_{int(time.time())}"

    async def _setup():
        db = _mongo()
        await db["stores"].insert_one({
            "id": uuid.uuid4().hex,
            "code": code,
            "name": "Pytest Provisioned Outlet",
            "city": "", "state": "", "region": "", "address": "",
            "is_active": True,
            "source": "pytest_seed",
            "pos_merchant_id": creds["merchant_id"],
            "pos_customer_key": code,
            "created_at": "2026-01-01T00:00:00+00:00",
        })
    asyncio.run(_setup())
    yield code

    async def _cleanup():
        db = _mongo()
        await db["stores"].delete_many({"pos_customer_key": code})
        await db["transactions"].delete_many({"bill_number": {"$regex": f"^PYT_{code}"}})
    asyncio.run(_cleanup())


def _add_point(cred, customer_key, bill_number, amount=1200):
    return requests.post(
        f"{BASE_URL}/api/pos/posAddPoint",
        headers={"x-api-key": cred["api_key"], "Content-Type": "application/json"},
        json={
            "merchant_id": cred["merchant_id"],
            "customer_key": customer_key,
            "customer": {"mobile": TEST_MOBILE},
            "transaction": {"number": bill_number, "net_amount": amount, "loyalty_flag": "1"},
        },
        timeout=30,
    )


def test_known_store_code_accepts_and_links_txn(creds, provisioned_code):
    bill = f"PYT_{provisioned_code}_A"
    r = _add_point(creds, provisioned_code, bill)
    assert r.status_code == 200, r.text
    assert r.json()["status_code"] == 200, r.json()

    async def _verify():
        db = _mongo()
        store = await db["stores"].find_one({"pos_customer_key": provisioned_code}, {"_id": 0})
        txn = await db["transactions"].find_one({"bill_number": bill}, {"_id": 0})
        return store, txn
    store, txn = asyncio.run(_verify())
    assert store is not None
    assert txn is not None and txn.get("store_id") == store["id"], "txn not linked to provisioned store"


def test_repeat_known_store_code_reuses_same_store(creds, provisioned_code):
    bill = f"PYT_{provisioned_code}_B"
    r = _add_point(creds, provisioned_code, bill)
    assert r.status_code == 200, r.text

    async def _count():
        db = _mongo()
        return await db["stores"].count_documents({"pos_customer_key": provisioned_code})
    assert asyncio.run(_count()) == 1, "duplicate store created for same customer_key"


def test_unknown_store_code_is_rejected(creds):
    # An unprovisioned customer_key must be REJECTED (strict validation) — not auto-created.
    unknown_key = f"PYT_UNKNOWN_{int(time.time())}"
    bill = f"PYT_{unknown_key}_X"
    r = _add_point(creds, unknown_key, bill)
    # HTTP layer returns 200 envelope with inner status_code, OR raises 400 — accept either shape
    body = r.json()
    inner = body.get("status_code", r.status_code)
    assert inner == 400, f"unknown store code should be rejected: {r.status_code} {r.text}"
    msg = (body.get("response", {}).get("message") or body.get("detail") or "").lower()
    assert "unknown store" in msg or "not provisioned" in msg, body

    async def _verify():
        db = _mongo()
        store = await db["stores"].find_one({"pos_customer_key": unknown_key}, {"_id": 0})
        txn = await db["transactions"].find_one({"bill_number": bill}, {"_id": 0})
        return store, txn
    store, txn = asyncio.run(_verify())
    assert store is None, "unknown store code must NOT auto-create a store under strict validation"
    assert txn is None, "no transaction should be created for a rejected bill"
