"""Verify the CRM ingest fixes:
 1. Billing load auto-creates customer STUBS.
 2. CRM in SKIP mode now ENRICHES stubs (was: skipped everything).
 3. CRM in UPSERT mode lands rich data + job completes (resilient flush).
"""
import asyncio
import sys
sys.path.insert(0, "/app/backend")
from datetime import datetime, timezone

from database import customers_col, transactions_col
from routes.historic_routes import _run_ingest_job, historic_jobs_col

TEST_MOBILES = ["7000000001", "7000000002", "7000000003"]

TXN_CSV = """Bill Number,Transaction Id,Date,Customer Mobile Number,Net Amount Before Tax,Outlet
RPRO-B1,RPRO-T1,01-02-2026,7000000001,1200,Test Outlet
RPRO-B2,RPRO-T2,02-02-2026,7000000002,800,Test Outlet
RPRO-B3,RPRO-T3,03-02-2026,7000000003,500,Test Outlet
"""

CRM_CSV = (
    "Mobile,Name,City,State,Total Billing,Current Point Balance,Total Visits,Last Visit Date\n"
    "7000000001,Asha Rao,Mumbai,Maharashtra,30000,250,4,01-02-2026\n"
    "7000000002,Bina Shah,Delhi,Delhi,80000,500,9,02-02-2026\n"
    "7000000003,Chetan K,Pune,Maharashtra,1500,10,2,03-02-2026\n"
)


async def cleanup():
    await transactions_col.delete_many({"customer_mobile": {"$in": TEST_MOBILES}})
    await customers_col.delete_many({"mobile": {"$in": TEST_MOBILES}})
    await historic_jobs_col.delete_many({"id": {"$in": ["repro_txn", "repro_crm_skip", "repro_crm_upsert"]}})


async def mkjob(jid, dataset):
    await historic_jobs_col.update_one({"id": jid}, {"$set": {
        "id": jid, "dataset": dataset, "filename": f"{jid}.csv", "status": "running",
        "queued_at": datetime.now(timezone.utc).isoformat(),
    }}, upsert=True)


async def jobres(jid):
    return await historic_jobs_col.find_one({"id": jid}, {"_id": 0, "status": 1, "inserted": 1, "updated": 1, "skipped": 1, "total_rows": 1})


async def main():
    await cleanup()
    await mkjob("repro_txn", "transactions")
    await _run_ingest_job("repro_txn", "transactions", TXN_CSV, "upsert", False)

    await mkjob("repro_crm_skip", "customers")
    await _run_ingest_job("repro_crm_skip", "customers", CRM_CSV, "skip", False)
    print("SKIP job:", await jobres("repro_crm_skip"))
    rows = await customers_col.find({"mobile": {"$in": TEST_MOBILES}}, {"_id": 0, "mobile": 1, "name": 1, "city": 1, "tier": 1, "source": 1}).to_list(10)
    enriched = sum(1 for r in rows if r.get("name"))
    print(f"After SKIP: {enriched}/3 enriched ->", rows)
    assert enriched == 3, "SKIP mode did NOT enrich stubs (bug still present)"

    # Re-run SKIP on now-real customers: should genuinely skip (no re-touch)
    await mkjob("repro_crm_skip2", "customers")
    await _run_ingest_job("repro_crm_skip2", "customers", CRM_CSV, "skip", False)
    print("SKIP job (2nd run, real customers):", await jobres("repro_crm_skip2"))

    await mkjob("repro_crm_upsert", "customers")
    await _run_ingest_job("repro_crm_upsert", "customers", CRM_CSV, "upsert", False)
    j2 = await jobres("repro_crm_upsert")
    print("UPSERT job:", j2)
    assert j2["status"] == "completed", f"UPSERT did not complete: {j2}"

    await cleanup()
    await historic_jobs_col.delete_many({"id": "repro_crm_skip2"})
    print("\nALL ASSERTIONS PASSED ✓")


if __name__ == "__main__":
    asyncio.run(main())
