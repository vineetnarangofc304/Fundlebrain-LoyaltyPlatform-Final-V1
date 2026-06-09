"""Iteration 54 — CRM registered-account store-code extraction + linking.

'Registred Account' = '<STORECODE>@KAZO.com'. Verify:
  - K00078@KAZO.com / F00028@KAZO.com → registered_store_code + registered_store_id + home_store_id set
  - stub stores auto-created for codes not yet provisioned
  - system accounts (crm.loyalty@, application@) → registered_store_code = None (not a store)
"""
import asyncio, sys
sys.path.insert(0, "/app/backend")
from datetime import datetime, timezone
from database import customers_col, stores_col
from routes.historic_routes import _run_ingest_job, historic_jobs_col, _store_code_from_account

MOB = ["7100000001", "7100000002", "7100000003", "7100000004"]
CSV = (
    "Mobile,Name,City,Registred Account\n"
    "7100000001,Asha,Mumbai,K00078@KAZO.com\n"
    "7100000002,Bina,Delhi,F00028@KAZO.com\n"
    "7100000003,Chetan,Pune,crm.loyalty@kazo.com\n"
    "7100000004,Dev,Surat,application@KAZO.com\n"
)


async def cleanup():
    await customers_col.delete_many({"mobile": {"$in": MOB}})
    await historic_jobs_col.delete_many({"id": "repro_store"})
    await stores_col.delete_many({"code": {"$in": ["K00078", "F00028"]}, "source": "registered_account"})


async def main():
    # unit: parser
    assert _store_code_from_account("K00078@KAZO.com") == "K00078"
    assert _store_code_from_account("F00028@KAZO.com") == "F00028"
    assert _store_code_from_account("crm.loyalty@kazo.com") is None
    assert _store_code_from_account("application@KAZO.com") is None
    assert _store_code_from_account("") is None
    print("parser unit OK")

    await cleanup()
    await historic_jobs_col.update_one({"id": "repro_store"}, {"$set": {
        "id": "repro_store", "dataset": "customers", "filename": "s.csv", "status": "running",
        "queued_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    await _run_ingest_job("repro_store", "customers", CSV, "upsert", False)

    rows = {c["mobile"]: c for c in await customers_col.find(
        {"mobile": {"$in": MOB}}, {"_id": 0, "mobile": 1, "registered_store_code": 1,
        "registered_store_id": 1, "home_store_id": 1}).to_list(10)}
    for m in MOB:
        print(m, rows.get(m))

    assert rows["7100000001"]["registered_store_code"] == "K00078"
    assert rows["7100000001"]["registered_store_id"], "K00078 customer must get a store id"
    assert rows["7100000001"]["home_store_id"] == rows["7100000001"]["registered_store_id"]
    assert rows["7100000002"]["registered_store_code"] == "F00028"
    assert rows["7100000003"]["registered_store_code"] is None
    assert rows["7100000004"]["registered_store_code"] is None

    stores = await stores_col.find({"code": {"$in": ["K00078", "F00028"]}}, {"_id": 0, "code": 1, "id": 1}).to_list(10)
    codes = {s["code"] for s in stores}
    assert {"K00078", "F00028"} <= codes, f"stub stores not created: {codes}"
    print("stub stores created:", codes)

    await cleanup()
    print("\nALL ASSERTIONS PASSED ✓")


if __name__ == "__main__":
    asyncio.run(main())
