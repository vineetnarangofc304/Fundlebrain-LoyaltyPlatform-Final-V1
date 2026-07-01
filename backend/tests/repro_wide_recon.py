"""Reproduce the EXACT production failure: a WIDE ~270MB billing CSV (~150k rows,
like the SKU-wise report). Streams rows straight into staged chunks so the test
harness itself never holds the whole file, then runs the recon and samples peak
RSS to prove the disk-streaming fix keeps memory bounded (old code peaked at
2-4x file size and OOM-restarted the pod)."""
import asyncio, os, io, csv, uuid, time, threading, resource
from dotenv import load_dotenv
load_dotenv()

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import transactions_col
import routes.recon_routes as R

CHUNK = 1_500_000
PAD_COLS = [f"Attr_{i}" for i in range(28)]        # widen each row to ~1.8KB
PAD_VALS = ["X" * 55 for _ in PAD_COLS]


def peak_rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


async def stage_wide_csv(job_id, n):
    """Write n wide rows (first n real bills) directly into staged chunks."""
    header = ["Bill Number", "Customer Mobile Number", "Date",
              "Net Amount Before Tax", "Total Tax", "Total Revenue"] + PAD_COLS
    buf = io.StringIO(); w = csv.writer(buf); w.writerow(header)
    idx = 0; total_bytes = 0; rows = 0
    pending = buf.getvalue().encode(); buf = None

    async def flush_full():
        nonlocal pending, idx, total_bytes
        while len(pending) >= CHUNK:
            await R.historic_chunks_col.insert_one(
                {"job_id": job_id, "chunk_index": idx, "data": pending[:CHUNK]})
            total_bytes += CHUNK; idx += 1
            pending = pending[CHUNK:]

    async for t in transactions_col.find(
            {}, {"_id": 0, "bill_number": 1, "net_amount": 1, "customer_mobile": 1}).limit(n):
        net = float(t.get("net_amount") or 0)
        b = io.StringIO(); w = csv.writer(b)
        w.writerow([t.get("bill_number"), t.get("customer_mobile") or "", "2025-01-01",
                    round(net * 0.85, 2), round(net * 0.15, 2), net] + PAD_VALS)
        pending += b.getvalue().encode()
        rows += 1
        if len(pending) >= CHUNK:
            await flush_full()
    if pending:
        await R.historic_chunks_col.insert_one(
            {"job_id": job_id, "chunk_index": idx, "data": pending})
        total_bytes += len(pending); idx += 1
    return rows, idx, total_bytes


async def main():
    n = int(os.environ.get("RECON_N", "150000"))
    deep = os.environ.get("RECON_DEEP", "0") == "1"     # user runs WITHOUT deep scan
    job_id = "reprowide_" + uuid.uuid4().hex[:8]
    rows, chunks, nbytes = await stage_wide_csv(job_id, n)
    print(f"[stage] {rows} wide rows -> {chunks} chunks, {nbytes/1e6:.0f}MB file; RSS now {peak_rss_mb():.0f}MB")

    await R.recon_jobs_col.insert_one(
        {"id": job_id, "dataset": "transactions", "filename": "SKU-wise_Billing.csv",
         "status": "running", "deep_scan": deep, "processed": 0,
         "queued_at": "2026-06-25T00:00:00+00:00"})

    stop = False
    peak = [peak_rss_mb()]
    def sampler():
        while not stop:
            peak[0] = max(peak[0], peak_rss_mb()); time.sleep(0.2)
    th = threading.Thread(target=sampler); th.start()

    print(f"[recon] full pipeline job={job_id} rows={rows} deep={deep}")
    t0 = time.time()
    await R._run_recon_job(job_id)
    stop = True; th.join()
    dt = time.time() - t0

    job = await R.recon_jobs_col.find_one({"id": job_id}, {"_id": 0})
    rep = job.get("report") or {}
    import json
    print(f"[recon] status={job.get('status')} in {dt:.1f}s error={job.get('error')}")
    print("report:", json.dumps({k: v for k, v in rep.items() if k != 'samples'}, default=str))
    print(f"[MEM] PEAK RSS during full run = {peak[0]:.0f} MB (file was {nbytes/1e6:.0f}MB)")
    leftover = await R.historic_chunks_col.count_documents({"job_id": job_id})
    print(f"[cleanup] leftover chunks = {leftover} (should be 0)")

    await R.recon_jobs_col.delete_one({"id": job_id})
    await R.recon_mismatch_col.delete_many({"job_id": job_id})
    await R.historic_chunks_col.delete_many({"job_id": job_id})


if __name__ == "__main__":
    asyncio.run(main())
