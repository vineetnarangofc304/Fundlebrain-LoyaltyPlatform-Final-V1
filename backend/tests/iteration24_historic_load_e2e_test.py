"""Iteration 24 — End-to-end historic load (CRM Report → Billing Report) integration.

Proves the production load path before the real 133/267/176 MB files:
1. CRM Report ingest → customers created with points_balance, and an 'opening' ledger
   entry per customer expiring 31 Dec 2026 IST.
2. Billing Report ingest (NEW eWards header variants) → transactions created, store
   resolved from the 'Store master' K-code (== POS customer_key), and each customer's
   tier + lifetime_spend rebuilt from bill history (even existing CRM customers).
3. Expiry Points report surfaces the opening balance.

Self-cleaning: removes all test customers/txns/ledger/store/jobs at the end.
"""
import os
import io
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
ADMIN = {"email": "superadmin@fundle.io", "password": "Fundle@2026", "portal": "crm"}
M1, M2 = "9000001001", "9000001002"
STORE_CODE = "KZTEST1"

CRM_CSV = (
    "Mobile,Name,State,City,Added On,Last Visit Date,First Visit Date,"
    "Current Point Balance,Redeem Points,Total Visits,Days Since Last Visit,Country Code,DOB,DOA\n"
    f"{M1},Test Alpha,PB,Pathankot,14-04-2022,01-06-2026,14-04-2022,16445,500,18,7,91,10-05-1990,12-12-2015\n"
    f"{M2},Test Beta,MH,Mumbai,01-01-2023,05-05-2026,01-01-2023,300,0,3,30,91,,\n"
)
BILLING_CSV = (
    "Date,Return Reason,Customer Mobile Number,Customer Name,Outlet(Only For Shopify Marker),"
    "Store master,Transaction Id,Bill Number,New Existing,Recency,Last Visit Date,Total Visits,"
    "Zone Name,City,Class,Time,Net Amount Before Tax,Tax Rate,Tax Total,Discount,"
    "Total Revenue KAZO,Total Billing KAZO\n"
    f"08-06-2026 14:30,,{M1},Test Alpha,KZ Test Outlet,{STORE_CODE},TXNKZ1,BILLKZ1,Existing,Active,"
    "01-06-2026,5,North,Pathankot,B,14:30:00,250000,5,12500,0,262500,262500\n"
    f"09-06-2026 10:00,,{M2},Test Beta,KZ Test Outlet,{STORE_CODE},TXNKZ2,BILLKZ2,New,Active,,1,"
    "North,Pathankot,B,10:00:00,3000,5,150,0,3150,3150\n"
)


def _mongo():
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


@pytest.fixture(scope="module")
def headers():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {(r.json().get('token') or r.json().get('access_token'))}"}


def _cleanup():
    async def _c():
        db = _mongo()
        await db["transactions"].delete_many({"customer_mobile": {"$in": [M1, M2]}})
        await db["customers"].delete_many({"mobile": {"$in": [M1, M2]}})
        await db["points_ledger"].delete_many({"customer_mobile": {"$in": [M1, M2]}})
        await db["stores"].delete_many({"code": STORE_CODE})
    asyncio.run(_c())


@pytest.fixture(scope="module", autouse=True)
def _around():
    _cleanup()
    yield
    _cleanup()


def _ingest(headers, csv_text, dataset, filename):
    files = {"file": (filename, io.BytesIO(csv_text.encode()), "text/csv")}
    data = {"dataset": dataset, "duplicate_mode": "upsert", "dry_run": "false"}
    r = requests.post(f"{BASE_URL}/api/historic-data/ingest", headers=headers,
                      files=files, data=data, timeout=30)
    assert r.status_code == 200, r.text
    job_id = r.json()["id"]
    # poll
    for _ in range(40):
        time.sleep(1)
        jr = requests.get(f"{BASE_URL}/api/historic-data/jobs/{job_id}", headers=headers, timeout=20)
        st = jr.json().get("status")
        if st in {"completed", "previewed", "failed"}:
            return jr.json()
    raise AssertionError(f"job {job_id} did not finish")


def test_full_historic_load(headers):
    # 1. CRM Report → customers + opening-balance ledger
    crm_job = _ingest(headers, CRM_CSV, "customers", "CRM_Report.csv")
    assert crm_job["status"] == "completed", crm_job
    assert crm_job["inserted"] + crm_job["updated"] >= 2

    db = _mongo()

    async def checks():
        db = _mongo()
        c1 = await db["customers"].find_one({"mobile": M1}, {"_id": 0})
        assert c1 and c1["points_balance"] == 16445, c1
        # opening-balance ledger entry, expiring 31 Dec 2026
        ob = await db["points_ledger"].find_one(
            {"customer_mobile": M1, "reference_type": "opening_balance"}, {"_id": 0})
        assert ob, "opening-balance ledger entry missing"
        assert ob["points"] == 16445
        assert ob["type"] == "opening"
        assert ob["expires_at"].startswith("2026-12-31"), ob["expires_at"]
        return c1
    asyncio.run(checks())

    # 2. Billing Report → transactions + store alignment + tier rebuild
    bill_job = _ingest(headers, BILLING_CSV, "transactions", "Billing_Report.csv")
    assert bill_job["status"] == "completed", bill_job
    assert bill_job["inserted"] + bill_job["updated"] >= 2

    async def checks2():
        db = _mongo()
        # transaction stored with store_code from "Store master"
        t1 = await db["transactions"].find_one({"bill_number": "BILLKZ1"}, {"_id": 0})
        assert t1 and t1["store_code"] == STORE_CODE, t1
        assert t1["customer_mobile"] == M1
        # store created + tagged with pos_customer_key == K-code (== customer_key)
        st = await db["stores"].find_one({"code": STORE_CODE}, {"_id": 0})
        assert st, "store not created from Store master"
        assert st.get("pos_customer_key") == STORE_CODE, st
        # tier rebuilt from spend for the EXISTING CRM customer (262500 -> diamond)
        c1 = await db["customers"].find_one({"mobile": M1}, {"_id": 0})
        assert c1["tier"] == "diamond", (c1["tier"], c1.get("lifetime_spend"))
        assert c1["lifetime_spend"] >= 200000
        # balance preserved from CRM (not wiped by the billing recompute)
        assert c1["points_balance"] == 16445
        c2 = await db["customers"].find_one({"mobile": M2}, {"_id": 0})
        assert c2["tier"] == "silver", c2["tier"]
    asyncio.run(checks2())

    # 3. Expiry report surfaces the opening balance (window covering Dec 2026)
    er = requests.get(f"{BASE_URL}/api/legacy-reports/expiry-points",
                      params={"start_date": "2026-12-01", "end_date": "2026-12-31"},
                      headers=headers, timeout=30)
    assert er.status_code == 200, er.text
    rows = er.json().get("rows", [])
    mobiles = {str(r.get("customer_mobile") or r.get("mobile")) for r in rows}
    assert M1 in mobiles, f"expiring opening balance for {M1} not in expiry report"


# --- store name-match: Billing Report carries the OUTLET NAME (no K-code); it must
#     MERGE onto the already-uploaded Store Master by normalised name, not duplicate. ---
M3 = "9000001003"
EXISTING_STORE_CODE = "KZEXIST9"
EXISTING_STORE_NAME = "ZZ Test Plaza, Testville Outlet"
BILLING_NAME_ONLY_CSV = (
    "Date,Customer Mobile Number,Customer Name,Outlet(Only For Shopify Marker),"
    "Transaction Id,Bill Number,Zone Name,City,Time,Net Amount Before Tax,Tax Total,"
    "Discount,Total Revenue KAZO,Total Billing KAZO\n"
    # NOTE: outlet name differs in case/spacing/punctuation from the Store Master on purpose
    f"10-06-2026 11:00,{M3},Test Gamma,zz test  plaza  testville outlet,TXNKZ3,BILLKZ3,East,"
    "Testville,11:00:00,5000,250,0,5250,5250\n"
)


def test_billing_outlet_name_merges_onto_existing_store(headers):
    db = _mongo()

    async def seed():
        db = _mongo()
        await db["stores"].delete_many({"code": EXISTING_STORE_CODE})
        await db["stores"].insert_one({
            "id": "store-exist-9", "code": EXISTING_STORE_CODE, "name": EXISTING_STORE_NAME,
            "city": "Guwahati", "is_active": True, "source": "store_master_test",
            "pos_customer_key": EXISTING_STORE_CODE, "pos_merchant_id": "KAZO_FUNDLE",
        })
    asyncio.run(seed())

    try:
        job = _ingest(headers, BILLING_NAME_ONLY_CSV, "transactions", "Billing_NameOnly.csv")
        assert job["status"] == "completed", job

        async def verify():
            db = _mongo()
            t = await db["transactions"].find_one({"bill_number": "BILLKZ3"}, {"_id": 0})
            assert t, "transaction not created"
            # must have merged onto the existing store (matched by normalised name)
            assert t["store_id"] == "store-exist-9", (t.get("store_id"), t.get("store_name"))
            # no duplicate store created for this outlet
            cnt = await db["stores"].count_documents(
                {"name": {"$regex": "testville", "$options": "i"}, "source": "historic_upload"})
            assert cnt == 0, f"duplicate store created ({cnt})"
        asyncio.run(verify())
    finally:
        async def clean():
            db = _mongo()
            await db["transactions"].delete_many({"customer_mobile": M3})
            await db["customers"].delete_many({"mobile": M3})
            await db["points_ledger"].delete_many({"customer_mobile": M3})
            await db["stores"].delete_many({"code": EXISTING_STORE_CODE})
        asyncio.run(clean())

