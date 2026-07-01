"""Reproduce a production-scale recon run through the FULL pipeline
(chunk staging -> disk streaming -> parse -> compare), verifying the
memory-efficient path added to fix the OOM stall."""
import asyncio, os, time, io, csv, uuid
from dotenv import load_dotenv
load_dotenv()

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import transactions_col
import routes.recon_routes as R

CHUNK = 1_500_000  # match frontend chunk size


async def build_csv_bytes(n):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Bill Number", "Customer Mobile Number", "Date",
                "Net Amount Before Tax", "Total Tax", "Total Revenue"])
    cnt = 0
    async for t in transactions_col.find(
            {}, {"_id": 0, "bill_number": 1, "net_amount": 1, "customer_mobile": 1}).limit(n):
        net = float(t.get("net_amount") or 0)
        w.writerow([t.get("bill_number"), t.get("customer_mobile") or "", "2025-01-01",
                    round(net * 0.85, 2), round(net * 0.15, 2), net])
        cnt += 1
    data = buf.getvalue().encode("utf-8")
    print(f"[build] {cnt} rows -> {len(data)/1e6:.1f}MB CSV")
    return data


async def main():
    n = int(os.environ.get("RECON_N", "1500054"))
    deep = os.environ.get("RECON_DEEP", "1") == "1"
    data = await build_csv_bytes(n)
    job_id = "repro_" + uuid.uuid4().hex[:8]

    # stage chunks exactly like the chunked upload does
    t0 = time.time()
    idx = 0
    for off in range(0, len(data), CHUNK):
        await R.historic_chunks_col.insert_one(
            {"job_id": job_id, "chunk_index": idx, "data": data[off:off + CHUNK]})
        idx += 1
    print(f"[stage] {idx} chunks inserted in {time.time()-t0:.1f}s")

    await R.recon_jobs_col.insert_one(
        {"id": job_id, "dataset": "transactions", "filename": "Billing_Report.csv",
         "status": "running", "deep_scan": deep, "processed": 0,
         "queued_at": "2026-06-25T00:00:00+00:00"})

    print(f"[recon] running full pipeline job={job_id} n={n} deep={deep}")
    t0 = time.time()
    await R._run_recon_job(job_id)
    dt = time.time() - t0

    job = await R.recon_jobs_col.find_one({"id": job_id}, {"_id": 0})
    import json
    rep = job.get("report") or {}
    print(f"[recon] status={job.get('status')} in {dt:.1f}s error={job.get('error')}")
    print(json.dumps({k: v for k, v in rep.items() if k != "samples"}, indent=2, default=str))
    leftover = await R.historic_chunks_col.count_documents({"job_id": job_id})
    print(f"[cleanup] leftover chunks for job = {leftover} (should be 0)")

    await R.recon_jobs_col.delete_one({"id": job_id})
    await R.recon_mismatch_col.delete_many({"job_id": job_id})
    await R.historic_chunks_col.delete_many({"job_id": job_id})


if __name__ == "__main__":
    asyncio.run(main())
