"""Iteration 74 — Recon hang/zombie fix verification.

Critical: a ~200k-row transactions CSV must reach status='done' (NOT stall at ~150k),
and the backend must remain responsive during the run (event loop not blocked).
Also verifies: deep_scan flag toggling, Cancel endpoint, watchdog listing health,
and RBAC on /api/recon/init.
"""
import io
import os
import time
import threading
import random
from datetime import datetime, timezone

import pytest
import requests

def _load_base_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        try:
            with open("/app/frontend/.env") as f:
                for ln in f:
                    if ln.startswith("REACT_APP_BACKEND_URL="):
                        v = ln.split("=", 1)[1].strip()
                        break
        except FileNotFoundError:
            pass
    assert v, "REACT_APP_BACKEND_URL not set"
    return v.rstrip("/")


BASE_URL = _load_base_url()
API = f"{BASE_URL}/api"

SUPER_ADMIN = ("superadmin@fundle.io", "Fundle@2026")
CHUNK_SIZE = 1_500_000  # 1.5 MB


# ---------- auth fixtures ----------
@pytest.fixture(scope="module")
def super_token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": SUPER_ADMIN[0], "password": SUPER_ADMIN[1]},
                      timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def hdr(super_token):
    return {"Authorization": f"Bearer {super_token}"}


# ---------- helpers ----------
def _build_tx_csv(n_rows: int) -> bytes:
    """Build an in-memory transactions CSV of n_rows rows."""
    buf = io.StringIO()
    buf.write("Bill Number,Transaction Id,Customer Mobile Number,Date,"
              "Net Amount Before Tax,Total Revenue,Customer Name\n")
    # generate deterministic-ish rows
    for i in range(n_rows):
        bill = f"IT74BILL{i:08d}"
        txid = f"IT74TX{i:08d}"
        mob = f"9{random.randint(100000000, 999999999)}"
        net = round(100 + (i % 5000) * 0.37, 2)
        buf.write(f"{bill},{txid},{mob},2025-06-10,{net},{net},Cust{i}\n")
    return buf.getvalue().encode("utf-8")


def _build_items_csv(skus):
    buf = io.StringIO()
    buf.write("SKU,Item Name\n")
    for s in skus:
        buf.write(f"{s},Test Item {s}\n")
    return buf.getvalue().encode("utf-8")


def _chunks(data: bytes, size: int = CHUNK_SIZE):
    for i in range(0, len(data), size):
        yield data[i:i + size]


def _upload(hdr, dataset, filename, payload: bytes, deep_scan=False):
    parts = list(_chunks(payload))
    r = requests.post(f"{API}/recon/init", headers=hdr,
                      json={"dataset": dataset, "filename": filename,
                            "total_chunks": len(parts),
                            "total_bytes": len(payload),
                            "deep_scan": deep_scan},
                      timeout=30)
    assert r.status_code == 200, f"init failed: {r.status_code} {r.text[:200]}"
    job_id = r.json()["id"]
    for idx, ch in enumerate(parts):
        files = {"chunk": (f"part{idx}.bin", ch, "application/octet-stream")}
        data = {"job_id": job_id, "chunk_index": str(idx)}
        rc = requests.post(f"{API}/recon/chunk", headers=hdr,
                           files=files, data=data, timeout=60)
        assert rc.status_code == 200, f"chunk {idx} failed: {rc.status_code} {rc.text[:200]}"
    rf = requests.post(f"{API}/recon/finalize", headers=hdr,
                       json={"job_id": job_id}, timeout=30)
    assert rf.status_code == 200, f"finalize failed: {rf.status_code} {rf.text[:200]}"
    return job_id


def _poll(hdr, job_id, timeout_s=240):
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout_s:
        r = requests.get(f"{API}/recon/jobs/{job_id}", headers=hdr, timeout=20)
        assert r.status_code == 200, f"poll failed: {r.status_code} {r.text[:200]}"
        j = r.json()
        last = j
        if j.get("status") in {"done", "failed"}:
            return j
        time.sleep(2)
    return last


# ---------- TEST 1: 200k-row run reaches done + event loop stays responsive ----------
class TestLargeReconNoStall:

    def test_200k_rows_completes_and_backend_responsive(self, hdr):
        N = 200_000
        csv_bytes = _build_tx_csv(N)
        assert 8_000_000 < len(csv_bytes) < 25_000_000, f"unexpected size {len(csv_bytes)}"

        job_id = _upload(hdr, "transactions",
                         f"it74_large_{int(time.time())}.csv", csv_bytes,
                         deep_scan=False)

        # While the job runs, hammer a lightweight endpoint and assert
        # latency is well under "blocked event loop" territory.
        stop = threading.Event()
        latencies = []
        errors = []

        def probe():
            while not stop.is_set():
                t0 = time.time()
                try:
                    rr = requests.get(f"{API}/recon/jobs", headers=hdr, timeout=10)
                    dt = time.time() - t0
                    latencies.append(dt)
                    if rr.status_code != 200:
                        errors.append(f"status={rr.status_code}")
                except Exception as e:
                    errors.append(str(e)[:80])
                time.sleep(1.5)

        th = threading.Thread(target=probe, daemon=True)
        th.start()
        try:
            final = _poll(hdr, job_id, timeout_s=240)
        finally:
            stop.set()
            th.join(timeout=5)

        # 1) Job must complete (NOT stall at ~150k)
        assert final is not None and final.get("status") == "done", (
            f"job did not reach 'done' — final={final.get('status')} "
            f"phase={final.get('phase')} processed={final.get('processed')} "
            f"error={final.get('error')}")
        report = final.get("report") or {}
        assert report.get("csv", {}).get("rows") == N, (
            f"expected csv.rows={N}, got {report.get('csv', {}).get('rows')}")
        # deep_scan=False -> extra_in_db must be null
        assert report.get("extra_in_db") is None, (
            f"deep_scan=False should yield extra_in_db=None, got {report.get('extra_in_db')}")

        # 2) Backend must have stayed responsive while parsing/comparing
        assert errors == [], f"probe errors during run: {errors[:5]}"
        assert latencies, "no probe samples collected"
        # 95th percentile should be quick (event loop not blocked)
        latencies_sorted = sorted(latencies)
        p95 = latencies_sorted[int(0.95 * (len(latencies_sorted) - 1))]
        assert p95 < 5.0, (
            f"GET /recon/jobs p95 latency too high ({p95:.2f}s) — "
            f"event loop likely blocked. samples={latencies[:10]}")
        print(f"Probe samples={len(latencies)} p95={p95:.2f}s max={max(latencies):.2f}s")


# ---------- TEST 2: deep_scan toggles extra_in_db ----------
class TestDeepScanFlag:

    def test_deep_scan_false_yields_null_extra(self, hdr):
        # small transactions file
        data = _build_tx_csv(50)
        job_id = _upload(hdr, "transactions",
                         f"it74_small_nodeep_{int(time.time())}.csv", data,
                         deep_scan=False)
        final = _poll(hdr, job_id, timeout_s=90)
        assert final.get("status") == "done", final
        assert final["report"]["extra_in_db"] is None
        assert final["report"]["deep_scan"] is False

    def test_deep_scan_true_yields_int_extra_items(self, hdr):
        # small items CSV (a couple of random SKUs that almost certainly aren't in DB)
        skus = [f"IT74SKU_{int(time.time())}_{i}" for i in range(5)]
        data = _build_items_csv(skus)
        job_id = _upload(hdr, "items",
                         f"it74_items_deep_{int(time.time())}.csv", data,
                         deep_scan=True)
        final = _poll(hdr, job_id, timeout_s=120)
        assert final.get("status") == "done", final
        rep = final["report"]
        assert rep["deep_scan"] is True
        assert isinstance(rep["extra_in_db"], int), \
            f"expected int extra_in_db, got {type(rep['extra_in_db']).__name__}"
        assert rep["extra_in_db"] >= 0


# ---------- TEST 3: cancel endpoint ----------
class TestCancel:

    def test_cancel_running_job(self, hdr):
        # mid-size file so it actually has a 'running' window
        data = _build_tx_csv(60_000)
        job_id = _upload(hdr, "transactions",
                         f"it74_cancel_{int(time.time())}.csv", data,
                         deep_scan=False)
        # let it tick over into running
        time.sleep(2)
        rc = requests.post(f"{API}/recon/jobs/{job_id}/cancel",
                           headers=hdr, timeout=20)
        assert rc.status_code == 200, f"cancel failed: {rc.status_code} {rc.text[:200]}"
        # status should already be failed
        r2 = requests.get(f"{API}/recon/jobs/{job_id}", headers=hdr, timeout=20)
        j = r2.json()
        assert j["status"] == "failed", j
        assert "Cancelled" in (j.get("error") or ""), j.get("error")


# ---------- TEST 4: list endpoint healthy (watchdog runs on every list) ----------
class TestJobsListHealthy:

    def test_jobs_list_ok(self, hdr):
        r = requests.get(f"{API}/recon/jobs", headers=hdr, timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert "jobs" in body and isinstance(body["jobs"], list)
        # any job still 'running'/'uploading' must have heartbeat newer than 8 min
        # (otherwise the watchdog would have flipped it). just informational.
        now = datetime.now(timezone.utc)
        for j in body["jobs"]:
            if j.get("status") in {"running", "uploading"}:
                hb = j.get("heartbeat")
                assert hb, f"running job missing heartbeat: {j}"


# ---------- TEST 5: RBAC on init + cancel (best effort if test account exists) ----------
class TestRBAC:

    def test_no_auth_init_rejected(self):
        r = requests.post(f"{API}/recon/init",
                          json={"dataset": "transactions", "filename": "x.csv",
                                "total_chunks": 1, "total_bytes": 100,
                                "deep_scan": False},
                          timeout=15)
        assert r.status_code in (401, 403), r.status_code

    def test_no_auth_cancel_rejected(self):
        r = requests.post(f"{API}/recon/jobs/nonexistent/cancel", timeout=15)
        assert r.status_code in (401, 403), r.status_code
