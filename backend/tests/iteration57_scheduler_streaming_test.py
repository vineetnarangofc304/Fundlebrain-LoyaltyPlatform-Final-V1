"""Iteration 57 — harden the big-CSV ingest pipeline so it can't hang/loop.

Verifies:
 1. STREAM-FROM-DISK: _run_ingest_job(csv_path=...) reads a CSV from a temp file
    on disk (O(1) memory) and completes — no giant in-memory decoded string.
 2. HEARTBEAT: a heartbeat is written through the run (so the stale-recovery
    watchdog never re-queues a still-working job → no "ingests forever" loop).
 3. RECOVERY CAP: process_pending_ingests() FAILS a stale 'running' job once it
    has been recovered MAX_RECOVERIES (4) times instead of re-running it forever.
 4. RECOVERY INCREMENT: a stale 'running' job under the cap is re-queued with
    recovery_count incremented.
"""
import asyncio
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "/app/backend")

from database import customers_col, points_ledger_col
from routes.historic_routes import (
    _run_ingest_job, process_pending_ingests, historic_jobs_col, historic_chunks_col,
)

TEST_MOBILES = [f"7300000{str(i).zfill(3)}" for i in range(50)]
JOB_DISK = "it57_disk"
JOB_FAILCAP = "it57_failcap"
JOB_REQUEUE = "it57_requeue"
ALL_JOBS = [JOB_DISK, JOB_FAILCAP, JOB_REQUEUE]


def build_crm_csv() -> str:
    lines = ["Mobile,Name,City,State,Total Billing,Current Point Balance,Total Visits,Last Visit Date"]
    for i, m in enumerate(TEST_MOBILES):
        lines.append(f"{m},Cust {i},Mumbai,Maharashtra,{30000 + i},{100 + i},{1 + (i % 5)},01-02-2026")
    return "\n".join(lines) + "\n"


async def cleanup():
    await customers_col.delete_many({"mobile": {"$in": TEST_MOBILES}})
    await points_ledger_col.delete_many({"customer_mobile": {"$in": TEST_MOBILES}})
    await historic_jobs_col.delete_many({"id": {"$in": ALL_JOBS}})
    await historic_chunks_col.delete_many({"job_id": {"$in": ALL_JOBS}})


async def mkjob(jid, dataset, **extra):
    doc = {
        "id": jid, "dataset": dataset, "filename": f"{jid}.csv",
        "duplicate_mode": "upsert", "dry_run": False,
        "queued_at": datetime.now(timezone.utc).isoformat(),
    }
    doc.update(extra)
    await historic_jobs_col.update_one({"id": jid}, {"$set": doc}, upsert=True)


async def main():
    await cleanup()

    # ---- 1 + 2: stream-from-disk ingest completes + writes a heartbeat ----
    csv_text = build_crm_csv()
    fd, path = tempfile.mkstemp(suffix=".csv", prefix="it57_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(csv_text)
    try:
        await mkjob(JOB_DISK, "customers", status="running")
        await _run_ingest_job(JOB_DISK, "customers", None, "upsert", False, csv_path=path)
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass

    j = await historic_jobs_col.find_one({"id": JOB_DISK}, {"_id": 0})
    print("DISK job:", {k: j.get(k) for k in ("status", "inserted", "updated", "skipped", "total_rows", "heartbeat")})
    assert j["status"] == "completed", f"disk-stream ingest did not complete: {j.get('status')}"
    assert j.get("total_rows") == len(TEST_MOBILES), f"row count off: {j.get('total_rows')}"
    assert j.get("heartbeat"), "no heartbeat written during the run"
    landed = await customers_col.count_documents({"mobile": {"$in": TEST_MOBILES}})
    assert landed == len(TEST_MOBILES), f"customers not all landed from disk stream: {landed}"
    # opening-balance ledger post-pass (with heartbeat) ran for positive balances
    ob = await points_ledger_col.count_documents(
        {"customer_mobile": {"$in": TEST_MOBILES}, "reference_type": "opening_balance"})
    assert ob == len(TEST_MOBILES), f"opening-balance ledger missing: {ob}"
    print(f"PASS 1+2: streamed {landed} customers from disk, {ob} opening-balance ledger entries, heartbeat present.")

    # ---- 3: recovery CAP — stale running job at the cap is FAILED, not re-run ----
    old_hb = (datetime.now(timezone.utc) - timedelta(minutes=12)).isoformat()
    await mkjob(JOB_FAILCAP, "customers", status="running", heartbeat=old_hb, recovery_count=4)
    # give it a stray chunk to prove cleanup happens on fail
    await historic_chunks_col.insert_one({"job_id": JOB_FAILCAP, "chunk_index": 0, "data": b"x"})
    await process_pending_ingests()
    f1 = await historic_jobs_col.find_one({"id": JOB_FAILCAP}, {"_id": 0, "status": 1, "error": 1})
    print("FAILCAP job:", f1)
    assert f1["status"] == "failed", f"stale job past cap should be FAILED, got {f1['status']}"
    leftover = await historic_chunks_col.count_documents({"job_id": JOB_FAILCAP})
    assert leftover == 0, "chunks of a capped-failed job should be cleaned up"
    print("PASS 3: stale job past recovery cap was failed + chunks cleaned (no infinite re-run).")

    # ---- 4: recovery INCREMENT — stale running job under the cap is re-queued ----
    await mkjob(JOB_REQUEUE, "customers", status="running", heartbeat=old_hb, recovery_count=1)
    await process_pending_ingests()
    r1 = await historic_jobs_col.find_one({"id": JOB_REQUEUE}, {"_id": 0, "recovery_count": 1, "status": 1})
    print("REQUEUE job:", r1)
    assert int(r1.get("recovery_count") or 0) == 2, f"recovery_count should increment to 2, got {r1.get('recovery_count')}"
    print("PASS 4: stale job under cap had recovery_count incremented (1 -> 2).")

    await cleanup()
    print("\nALL ASSERTIONS PASSED \u2713")


if __name__ == "__main__":
    asyncio.run(main())
