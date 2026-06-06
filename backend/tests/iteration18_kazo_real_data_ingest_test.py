"""Iteration 18 — Real KAZO data ingestion alignment.

Validates the historic upload parser against the client's real file formats:
- Customer Master (Mobile, Total Billing, DOA/DOB, Days Since Last Visit ...)
- Billwise (Store master K-code drives store identity == POS customer_key)
- SKU-wise / line items (attach to bills by Transaction Id + build item master)
"""
import os
import time
import asyncio
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break
assert BASE_URL


def _mongo():
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "superadmin@fundle.io", "password": "Fundle@2026", "portal": "crm"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _ingest(token, dataset, csv_text, fname):
    r = requests.post(
        f"{BASE_URL}/api/historic-data/ingest",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (fname, csv_text, "text/csv")},
        data={"dataset": dataset, "duplicate_mode": "upsert", "dry_run": "false"},
        timeout=60,
    )
    assert r.status_code == 200, r.text
    job_id = r.json()["id"]
    # poll
    for _ in range(20):
        time.sleep(1)
        jr = requests.get(f"{BASE_URL}/api/historic-data/jobs/{job_id}",
                          headers={"Authorization": f"Bearer {token}"})
        j = jr.json()
        if j.get("status") in {"completed", "failed"}:
            return j
    raise AssertionError("ingest job did not complete in time")


def test_schema_exposes_store_master_and_sku_dataset(token):
    s = requests.get(f"{BASE_URL}/api/historic-data/schema/transactions",
                     headers={"Authorization": f"Bearer {token}"}).json()
    assert "Store master" in s["recognised_columns"]
    sku = requests.get(f"{BASE_URL}/api/historic-data/schema/sku_transactions",
                       headers={"Authorization": f"Bearer {token}"}).json()
    assert "Item Id" in sku["recognised_columns"]
    assert "Transaction Id" in sku["required_columns"]


def test_billwise_store_master_drives_store_identity(token):
    ts = int(time.time())
    code = f"KPYT{ts % 100000}"
    bill = f"PYTBILL{ts}"
    csv_text = (
        "Date,Return Marker,Customer Mobile Number,Outlet(Only For Shopify Marker),"
        "Store master,Transaction Id,Bill Number,Zone New,City,Class,Time,"
        "Net Amount Before Tax Kazo,Total Tax,Discount,Total Revenue Kazo\n"
        f"01-04-2021 00:00,Regular,6000535682,PyTest Mall,{code},{bill},{bill},"
        "East,Guwahati,B,12:30:00,1490,0,0,1490\n"
    )
    j = _ingest(token, "transactions", csv_text, "bw.csv")
    assert j["status"] == "completed" and j["errors_count"] == 0, j

    async def _verify():
        db = _mongo()
        store = await db["stores"].find_one({"code": code}, {"_id": 0})
        txn = await db["transactions"].find_one({"bill_number": bill}, {"_id": 0})
        return store, txn
    store, txn = asyncio.run(_verify())
    assert store is not None, "store not created from Store master K-code"
    assert store["pos_customer_key"] == code, "store K-code not aligned to POS customer_key"
    assert store["name"] == "PyTest Mall"
    assert txn["store_code"] == code and txn["store_id"] == store["id"], "txn not linked to K-code store"

    # cleanup
    async def _cleanup():
        db = _mongo()
        await db["stores"].delete_many({"code": code})
        await db["transactions"].delete_many({"bill_number": bill})
    asyncio.run(_cleanup())


def test_sku_lines_attach_to_bill_and_build_item_master(token):
    ts = int(time.time())
    code = f"KPYS{ts % 100000}"
    txid = f"PYTXN{ts}"
    item_id = f"PYITEM{ts}"
    # 1) create the bill first
    bw = (
        "Date,Return Marker,Customer Mobile Number,Outlet(Only For Shopify Marker),"
        "Store master,Transaction Id,Bill Number,City,Time,Total Revenue Kazo\n"
        f"04-02-2025,Regular,8789277792,PyTest Outlet,{code},{txid},{txid},Chennai,12:00:00,790\n"
    )
    j1 = _ingest(token, "transactions", bw, "bw2.csv")
    assert j1["status"] == "completed", j1
    # 2) ingest SKU line referencing that Transaction Id
    sku = (
        "Date,Transaction Id,Bill Number,Store code,Mobile,Item Name,Item Id,Season,"
        "Item Master Category,Quantity,Rate,discount,Sub Total,Category 1(Logic)\n"
        f"04-02-2025,{txid},INVPYT{ts},{code},8789277792,PYT EARRINGS,{item_id},"
        "SPRING/SUMMER,Jwellery,2,790,0,1580,BAJW\n"
    )
    j2 = _ingest(token, "sku_transactions", sku, "sku.csv")
    assert j2["status"] == "completed" and j2["errors_count"] == 0, j2

    async def _verify():
        db = _mongo()
        txn = await db["transactions"].find_one({"transaction_id": txid}, {"_id": 0})
        item = await db["items"].find_one({"sku": item_id}, {"_id": 0})
        return txn, item
    txn, item = asyncio.run(_verify())
    assert txn and txn.get("items"), "SKU items not attached to the bill"
    assert txn["items"][0]["sku"] == item_id
    assert txn["units_count"] == 2, "units_count should sum quantities"
    assert item is not None and item["category"] == "Jwellery", "item master not built"

    async def _cleanup():
        db = _mongo()
        await db["stores"].delete_many({"code": code})
        await db["transactions"].delete_many({"transaction_id": txid})
        await db["items"].delete_many({"sku": item_id})
    asyncio.run(_cleanup())
