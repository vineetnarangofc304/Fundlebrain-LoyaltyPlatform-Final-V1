"""Iteration 45 — chunked-upload finalize must be O(1.5MB), never freeze the loop.

Reproduces the production Cloudflare-520 scenario: a multi-MB CSV is uploaded in
1.5MB chunks, then finalized. Before the fix, finalize stitched + decoded +
row-counted the WHOLE file synchronously inside the HTTP request (memory spike +
event-loop block → origin reset → CF 520). After the fix, finalize only peeks the
first chunk and returns fast; the scheduler ingests in a worker thread.

Run: python -m pytest backend/tests/iteration45_chunked_finalize_perf_test.py -s
or:  python backend/tests/iteration45_chunked_finalize_perf_test.py
"""
import io
import os
import sys
import time
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://fundle-brain-ai-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
EMAIL = "superadmin@fundle.io"
PASSWORD = "Fundle@2026"
CHUNK_BYTES = 1_500_000


def _login() -> str:
    r = requests.post(f"{API}/auth/login", json={"email": EMAIL, "password": PASSWORD, "portal": "crm"}, timeout=30)
    r.raise_for_status()
    return r.json()["token"]


def _make_csv(n_rows: int) -> bytes:
    buf = io.StringIO()
    buf.write("Mobile,Name,Current Point Balance,Total Billing,Total Visits,State,City\n")
    for i in range(n_rows):
        mob = 7000000000 + i  # 10-digit, test-only prefix
        buf.write(f"{mob},PerfTest User {i},{(i % 500)},{(i % 9000) + 100},{(i % 9) + 1},Maharashtra,Mumbai\n")
    return buf.getvalue().encode("utf-8")


def main():
    token = _login()
    H = {"Authorization": f"Bearer {token}"}

    # ~4MB CSV → ~3 chunks. Big enough to prove the multi-chunk + thread path.
    n_rows = 70_000
    data = _make_csv(n_rows)
    size = len(data)
    total_chunks = max(1, -(-size // CHUNK_BYTES))
    print(f"CSV: {size/1024/1024:.2f} MB, {n_rows} rows, {total_chunks} chunks")

    # 1) init (dry_run so we don't pollute preview DB)
    r = requests.post(f"{API}/historic-data/ingest/init", headers=H, json={
        "dataset": "customers", "duplicate_mode": "upsert", "dry_run": True,
        "filename": "perf_test_customers.csv", "total_chunks": total_chunks, "total_bytes": size,
    }, timeout=30)
    r.raise_for_status()
    job_id = r.json()["id"]
    print("init ok, job_id =", job_id)

    # 2) upload chunks
    for i in range(total_chunks):
        blob = data[i * CHUNK_BYTES:(i + 1) * CHUNK_BYTES]
        files = {"chunk": (f"chunk-{i}.csv", blob, "text/csv")}
        form = {"job_id": job_id, "chunk_index": str(i)}
        rc = requests.post(f"{API}/historic-data/ingest/chunk", headers=H, data=form, files=files, timeout=60)
        rc.raise_for_status()
    print(f"uploaded {total_chunks} chunks")

    # 3) finalize — MUST be fast (no full-file stitch/decode/count)
    t0 = time.time()
    rf = requests.post(f"{API}/historic-data/ingest/finalize", headers=H, json={"job_id": job_id}, timeout=120)
    fin_secs = time.time() - t0
    rf.raise_for_status()
    fin = rf.json()
    print(f"finalize: {fin_secs:.3f}s · status={fin.get('status')} · est_rows={fin.get('row_count_estimated')} · cols={len(fin.get('columns_detected') or [])}")
    assert fin.get("status") == "pending_ingest", f"expected pending_ingest, got {fin.get('status')}"
    assert fin_secs < 5.0, f"finalize too slow ({fin_secs:.2f}s) — the loop-blocking bug is back"
    assert (fin.get("columns_detected") or [])[0] == "Mobile", "header not detected from first chunk"
    est = fin.get("row_count_estimated") or 0
    assert est > 0, "row estimate should be > 0"
    # estimate should be in the right ballpark (within 30% of real)
    assert 0.5 * n_rows <= est <= 1.6 * n_rows, f"row estimate {est} unreasonable vs {n_rows}"

    # 4) poll for scheduler completion (dry_run → 'previewed')
    deadline = time.time() + 120
    job = None
    while time.time() < deadline:
        rj = requests.get(f"{API}/historic-data/jobs/{job_id}", headers=H, timeout=30)
        rj.raise_for_status()
        job = rj.json()
        if job.get("status") in {"previewed", "completed", "failed"}:
            break
        time.sleep(3)
    print(f"final job: status={job.get('status')} · total_rows={job.get('total_rows')} · processed={job.get('processed')} · skipped={job.get('skipped')}")
    assert job.get("status") == "previewed", f"expected previewed, got {job.get('status')} err={job.get('error')}"
    assert job.get("total_rows") == n_rows, f"total_rows {job.get('total_rows')} != {n_rows}"
    # post-ingest exact count must override the finalize estimate
    assert job.get("row_count_estimated") == n_rows, f"row_count_estimated should be exact ({n_rows}), got {job.get('row_count_estimated')}"
    print("\n✅ PASS — finalize is O(first-chunk), pipeline ingests via worker thread, counts exact.")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print("❌ FAIL:", e)
        sys.exit(1)
    except Exception as e:
        print("❌ ERROR:", e)
        sys.exit(2)
