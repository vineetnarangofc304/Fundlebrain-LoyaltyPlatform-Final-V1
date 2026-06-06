"""Iteration 17 — POS store resolution by (merchant_id + customer_key) combo.

Canonical rule: customer_key IS the store code. The (merchant_id + customer_key)
combo identifies the store on every bill. An unseen combo auto-creates a new store
master row. customer_key is NOT a secret and must not be rejected on mismatch.

Coverage:
- A bill with a brand-new customer_key auto-creates a store (code == customer_key).
- A second bill with the same customer_key reuses the same store (no duplicates).
- A different customer_key (not the master credential value) is NOT rejected (200, not 403).
- The created transaction is linked to the resolved store_id.
"""
import os
import time
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
def new_code():
    code = f"PYTEST_STORE_{int(time.time())}"
    yield code
    # teardown — remove test store + test bills
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


def test_new_customer_key_autocreates_store_and_links_txn(creds, new_code):
    bill = f"PYT_{new_code}_A"
    r = _add_point(creds, new_code, bill)
    assert r.status_code == 200, r.text
    assert r.json()["status_code"] == 200, r.json()

    async def _verify():
        db = _mongo()
        store = await db["stores"].find_one({"pos_customer_key": new_code}, {"_id": 0})
        txn = await db["transactions"].find_one({"bill_number": bill}, {"_id": 0})
        return store, txn
    store, txn = asyncio.run(_verify())
    assert store is not None, "store was not auto-created from customer_key"
    assert store["code"] == new_code
    assert store["pos_merchant_id"] == creds["merchant_id"]
    assert store["source"] == "pos_auto_customer_key"
    assert txn is not None and txn.get("store_id") == store["id"], "txn not linked to resolved store"


def test_repeat_customer_key_reuses_same_store(creds, new_code):
    bill = f"PYT_{new_code}_B"
    r = _add_point(creds, new_code, bill)
    assert r.status_code == 200, r.text

    async def _count():
        db = _mongo()
        return await db["stores"].count_documents({"pos_customer_key": new_code})
    assert asyncio.run(_count()) == 1, "duplicate store created for same customer_key"


def test_nonmatching_customer_key_not_rejected(creds):
    # A customer_key different from the master credential value must NOT 403.
    weird_key = f"PYT_NOTSECRET_{int(time.time())}"
    bill = f"PYT_{weird_key}_X"
    r = _add_point(creds, weird_key, bill)
    assert r.status_code == 200, f"customer_key wrongly rejected: {r.status_code} {r.text}"
    assert r.json()["status_code"] == 200, r.json()
    # cleanup
    async def _cleanup():
        db = _mongo()
        await db["stores"].delete_many({"pos_customer_key": weird_key})
        await db["transactions"].delete_many({"bill_number": bill})
    asyncio.run(_cleanup())
