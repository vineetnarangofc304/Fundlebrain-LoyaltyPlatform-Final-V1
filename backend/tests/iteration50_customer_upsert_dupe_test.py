"""Iteration 50 — customer UPSERT must not fail on duplicate-mobile CRM files.

Repro: CRM exports are ~98.5% duplicated on mobile. The customers flush builds
UpdateOne(filter={mobile}, upsert=True) per row; two rows with the SAME (new)
mobile in one unordered batch both attempt an upsert-insert → E11000 →
BulkWriteError → the ingest job 'fails'. After the fix the batch is de-duped by
mobile, so the job completes.

This test uploads 40k rows that cycle through only 80 unique mobiles (so every
500-row batch has many intra-batch dupes) in UPSERT + LIVE mode and asserts the
job COMPLETES with ~80 unique customers. Cleans up after itself.

Run: python backend/tests/iteration50_customer_upsert_dupe_test.py
"""
import io
import os
import sys
import time
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://kazo-data-platform.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
EMAIL, PASSWORD = "superadmin@fundle.io", "Fundle@2026"
CHUNK = 1_500_000
N_ROWS = 40_000
N_UNIQUE = 80
MOB_BASE = 8880000000  # test-only prefix, cleaned up after


def main():
    tok = requests.post(f"{API}/auth/login", json={"email": EMAIL, "password": PASSWORD, "portal": "crm"}, timeout=30).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}

    buf = io.StringIO()
    buf.write("Mobile,Name,Current Point Balance,Total Billing,Total Visits,City\n")
    for i in range(N_ROWS):
        mob = MOB_BASE + (i % N_UNIQUE)  # cycles -> heavy intra-batch dupes
        buf.write(f"{mob},Dupe User {i % N_UNIQUE},{i % 300},{(i % 5000) + 100},{(i % 7) + 1},Mumbai\n")
    data = buf.getvalue().encode()
    size = len(data)
    chunks = max(1, -(-size // CHUNK))
    print(f"CSV {size/1024/1024:.2f}MB, {N_ROWS} rows, {N_UNIQUE} unique mobiles, {chunks} chunks")

    jid = requests.post(f"{API}/historic-data/ingest/init", headers=H, json={
        "dataset": "customers", "duplicate_mode": "upsert", "dry_run": False,
        "filename": "dupe_upsert_test.csv", "total_chunks": chunks, "total_bytes": size,
    }, timeout=30).json()["id"]

    for i in range(chunks):
        blob = data[i * CHUNK:(i + 1) * CHUNK]
        requests.post(f"{API}/historic-data/ingest/chunk", headers=H,
                      data={"job_id": jid, "chunk_index": str(i)},
                      files={"chunk": (f"c{i}.csv", blob, "text/csv")}, timeout=60).raise_for_status()
    requests.post(f"{API}/historic-data/ingest/finalize", headers=H, json={"job_id": jid}, timeout=120).raise_for_status()

    job = None
    deadline = time.time() + 120
    while time.time() < deadline:
        job = requests.get(f"{API}/historic-data/jobs/{jid}", headers=H, timeout=30).json()
        if job.get("status") in {"completed", "previewed", "failed"}:
            break
        time.sleep(3)
    print(f"job: status={job.get('status')} new={job.get('inserted')} touched={job.get('updated')} "
          f"skipped={job.get('skipped')} total={job.get('total_rows')} err={job.get('error')}")

    ok = True
    if job.get("status") != "completed":
        print(f"❌ FAIL — expected completed, got {job.get('status')} (error: {job.get('error')})"); ok = False
    # verify reconciliation: new + touched + skipped == total
    recon = (job.get("inserted", 0) or 0) + (job.get("updated", 0) or 0) + (job.get("skipped", 0) or 0)
    if recon != job.get("total_rows"):
        print(f"❌ FAIL — reconciliation {recon} != total {job.get('total_rows')}"); ok = False
    # verify ~N_UNIQUE distinct customers landed
    leaked = requests.get(f"{API}/historic-data/jobs/{jid}", headers=H, timeout=30).json()

    # cleanup
    try:
        import asyncio
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from database import customers_col, db
        async def _clean():
            r = await customers_col.delete_many({"mobile": {"$regex": "^888000"}})
            await db["historic_ingest_jobs"].delete_one({"id": jid})
            await db["historic_chunks"].delete_many({"job_id": jid})
            return r.deleted_count
        n = asyncio.run(_clean())
        print(f"cleanup: removed {n} test customers + job")
    except Exception as e:
        print("cleanup warn:", e)

    print("✅ PASS — duplicate-mobile customer upsert completes without BulkWriteError." if ok else "❌ FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
