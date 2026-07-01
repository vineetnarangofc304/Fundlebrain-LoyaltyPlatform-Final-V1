"""Iteration 75 — Verify recon large-file OOM fix (disk-stream + pymongo.timeout).

Regression for user report: recon jobs on 170–270MB production billing CSVs
were stuck 'running' and auto-failed with "Stalled — no progress for over 8 min
(likely a server restart mid-run)". Root cause: previous engine loaded the
whole file into memory (chunks + joined bytes + decoded str = 2-4x file size)
which OOM-restarted the pod. Fix: uploaded chunks are now streamed to a temp
file on disk and the CSV parser opens that file — the background body is
wrapped in `pymongo.timeout(1800)` to override aggressive prod timeoutMS.

Tests use Master Admin creds and hit /api/recon/{init,chunk,finalize} then poll
GET /api/recon/jobs/{id} until status='done'. Small (50 rows / 1 chunk) and
LARGE (≥30MB, wide padded rows, 20+ chunks) paths are covered.
"""
import io
import math
import os
import time
from datetime import datetime, timezone

import pytest
import requests


def _load_base_url() -> str:
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        with open("/app/frontend/.env") as f:
            for ln in f:
                if ln.startswith("REACT_APP_BACKEND_URL="):
                    v = ln.split("=", 1)[1].strip()
                    break
    assert v, "REACT_APP_BACKEND_URL not set"
    return v.rstrip("/")


BASE_URL = _load_base_url()
API = f"{BASE_URL}/api"
MASTER_ADMIN = ("masteradmin@fundle.io", "Master@2026")
CHUNK_SIZE = 1_500_000  # matches CsvReconSection.jsx


# -------------------------- auth --------------------------
@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": MASTER_ADMIN[0], "password": MASTER_ADMIN[1]},
                      timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:300]}"
    body = r.json()
    assert "token" in body, f"no token field in login response: {list(body)}"
    return body["token"]


@pytest.fixture(scope="module")
def hdr(token):
    return {"Authorization": f"Bearer {token}"}


# -------------------------- helpers --------------------------
def _build_small_tx_csv(n_rows: int = 50) -> bytes:
    """Exact header requested by the reviewer + ~50 data rows."""
    buf = io.StringIO()
    buf.write("Bill Number,Customer Mobile Number,Date,Net Amount Before Tax,"
              "Total Tax,Total Revenue\n")
    for i in range(n_rows):
        bill = f"TESTBILL{i+1:04d}"
        mob = f"9800{i+1:06d}"
        buf.write(f"{bill},{mob},2025-01-01,850,150,1000\n")
    return buf.getvalue().encode("utf-8")


def _build_wide_tx_csv(n_rows: int, pad_cols: int = 30, pad_val_len: int = 50) -> bytes:
    """Wide CSV — pads each row with extra columns so we exceed ~30MB and
    push the multi-chunk (20+ x 1.5MB) disk-streaming path.

    Only the CSV mapper's known columns are used for actual keying — pad
    columns are ignored by _map_transaction_row (safe additional columns)."""
    base_hdr = ["Bill Number", "Customer Mobile Number", "Date",
                "Net Amount Before Tax", "Total Tax", "Total Revenue"]
    pad_hdr = [f"pad_{i}" for i in range(pad_cols)]
    pad_val = "X" * pad_val_len
    buf = io.StringIO()
    buf.write(",".join(base_hdr + pad_hdr) + "\n")
    row_pad = "," + ",".join([pad_val] * pad_cols)
    for i in range(n_rows):
        bill = f"IT75WIDE{i:08d}"
        mob = f"9{(700000000 + i):09d}"
        buf.write(f"{bill},{mob},2025-01-01,850,150,1000{row_pad}\n")
    return buf.getvalue().encode("utf-8")


def _upload_and_finalize(hdr, data: bytes, filename: str, deep_scan: bool = False):
    total_bytes = len(data)
    total_chunks = max(1, math.ceil(total_bytes / CHUNK_SIZE))
    r = requests.post(f"{API}/recon/init", headers=hdr, json={
        "dataset": "transactions", "filename": filename,
        "total_chunks": total_chunks, "total_bytes": total_bytes,
        "deep_scan": deep_scan}, timeout=30)
    assert r.status_code == 200, f"init failed {r.status_code}: {r.text[:300]}"
    job_id = r.json()["id"]

    for idx in range(total_chunks):
        blob = data[idx * CHUNK_SIZE:(idx + 1) * CHUNK_SIZE]
        files = {"chunk": (f"part{idx}", blob, "application/octet-stream")}
        form = {"job_id": job_id, "chunk_index": str(idx)}
        cr = requests.post(f"{API}/recon/chunk", headers=hdr, data=form,
                           files=files, timeout=120)
        assert cr.status_code == 200, f"chunk {idx}/{total_chunks} failed {cr.status_code}: {cr.text[:200]}"

    fr = requests.post(f"{API}/recon/finalize", headers=hdr,
                       json={"job_id": job_id}, timeout=30)
    assert fr.status_code == 200, f"finalize failed {fr.status_code}: {fr.text[:300]}"
    return job_id, total_chunks, total_bytes


def _poll_until_terminal(hdr, job_id: str, timeout_s: int = 300, interval_s: float = 3.0):
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout_s:
        r = requests.get(f"{API}/recon/jobs/{job_id}", headers=hdr, timeout=20)
        assert r.status_code == 200, f"detail failed {r.status_code}: {r.text[:200]}"
        j = r.json()
        last = j
        if j.get("status") in ("done", "failed"):
            return j, time.time() - t0
        time.sleep(interval_s)
    pytest.fail(f"job {job_id} did not terminate in {timeout_s}s. last={last}")


# ============================================================
# 1. Auth sanity
# ============================================================
class TestAuth:
    def test_master_admin_login_returns_token(self, token):
        assert isinstance(token, str) and len(token) > 20


# ============================================================
# 2. Small recon flow
# ============================================================
class TestSmallReconCompletes:
    def test_small_50_row_transactions_recon(self, hdr):
        n_rows = 50
        data = _build_small_tx_csv(n_rows)
        job_id, chunks, total_bytes = _upload_and_finalize(
            hdr, data, "it75_small.csv", deep_scan=False)
        assert chunks == 1
        job, elapsed = _poll_until_terminal(hdr, job_id, timeout_s=120)
        print(f"[small] done in {elapsed:.1f}s status={job.get('status')}")
        assert job["status"] == "done", (
            f"expected 'done', got {job.get('status')} error={job.get('error')!r}")
        assert not job.get("error"), f"unexpected error: {job.get('error')}"
        report = job.get("report")
        assert isinstance(report, dict), f"report missing: {job}"
        assert report["csv"]["rows"] == n_rows, (
            f"csv.rows {report['csv']['rows']} != {n_rows}")
        # matched + missing_in_db must equal the unique bill count in CSV
        assert report["matched"] + report["missing_in_db"] == report["csv"]["unique_bills"], (
            f"matched({report['matched']})+missing({report['missing_in_db']}) "
            f"!= unique_bills({report['csv']['unique_bills']})")


# ============================================================
# 3. LARGE recon — the core regression
# ============================================================
class TestLargeReconNoStall:
    def test_wide_large_multi_chunk_completes(self, hdr):
        # Target ≥30MB with wide-padded rows so we push 20+ chunks.
        # 60k rows × ~1.6KB/row ≈ 96MB — that's plenty and safely > 20 chunks.
        n_rows = 60_000
        data = _build_wide_tx_csv(n_rows, pad_cols=30, pad_val_len=50)
        size_mb = len(data) / (1024 * 1024)
        est_chunks = math.ceil(len(data) / CHUNK_SIZE)
        print(f"[large] csv size = {size_mb:.1f} MB → {est_chunks} chunks × 1.5MB")
        assert est_chunks >= 20, f"want ≥20 chunks, got {est_chunks} ({size_mb:.1f}MB)"

        t_upload = time.time()
        job_id, chunks, total_bytes = _upload_and_finalize(
            hdr, data, "it75_large_wide.csv", deep_scan=False)
        assert chunks == est_chunks
        upload_s = time.time() - t_upload
        print(f"[large] upload+finalize took {upload_s:.1f}s")

        job, run_s = _poll_until_terminal(hdr, job_id, timeout_s=300, interval_s=3.0)
        total_s = upload_s + run_s
        print(f"[large] processing took {run_s:.1f}s, total wall clock {total_s:.1f}s "
              f"status={job.get('status')}")

        assert job["status"] == "done", (
            f"LARGE recon did NOT complete: status={job.get('status')} "
            f"error={job.get('error')!r} phase={job.get('phase')!r}")
        err = (job.get("error") or "")
        assert "Stalled" not in err, f"job stalled: {err}"
        assert not err, f"unexpected error on large recon: {err}"

        report = job.get("report")
        assert isinstance(report, dict), f"report missing: {job}"
        assert report["csv"]["rows"] == n_rows, (
            f"csv.rows {report['csv']['rows']} != {n_rows}")
        assert report["matched"] + report["missing_in_db"] == report["csv"]["unique_bills"]

        # Watchdog listing must show this job
        lr = requests.get(f"{API}/recon/jobs", headers=hdr, timeout=20)
        assert lr.status_code == 200
        ids = [row.get("id") for row in lr.json().get("jobs", [])]
        assert job_id in ids, f"job {job_id} not in /jobs list (first 20)"


# ============================================================
# 4. Detail + mismatches.csv artefacts (uses small job)
# ============================================================
class TestDetailAndMismatchesCsv:
    def test_detail_has_report_and_mismatches_csv_download(self, hdr):
        # fresh tiny job so we don't depend on ordering
        data = _build_small_tx_csv(20)
        job_id, _, _ = _upload_and_finalize(hdr, data, "it75_detail.csv")
        job, _ = _poll_until_terminal(hdr, job_id, timeout_s=120)
        assert job["status"] == "done", f"prereq: small job must finish. got {job}"
        assert isinstance(job.get("report"), dict)

        # mismatches.csv — always returns 200 with a text/csv content-type
        # (body may be header-only if there are no mismatches).
        mr = requests.get(f"{API}/recon/jobs/{job_id}/mismatches.csv",
                          headers=hdr, timeout=30)
        assert mr.status_code == 200, f"mismatches.csv {mr.status_code}: {mr.text[:200]}"
        ct = mr.headers.get("content-type", "")
        assert "csv" in ct.lower(), f"unexpected content-type {ct!r}"
        first_line = mr.text.splitlines()[0] if mr.text else ""
        assert "type" in first_line and "key" in first_line, (
            f"missing CSV header row: {first_line!r}")


# ============================================================
# 5. Guardrails — unauthed init is rejected
# ============================================================
class TestGuardrails:
    def test_unauthed_init_rejected(self):
        r = requests.post(f"{API}/recon/init", json={
            "dataset": "transactions", "filename": "no.csv",
            "total_chunks": 1, "total_bytes": 10, "deep_scan": False},
            timeout=10)
        assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"
