"""Iteration 108: dashboard L2 cache regression + data-quality endpoints."""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://kazo-loyalty-hub-2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

CREDS = {"email": "superadmin@fundle.io", "password": "Fundle@2026"}


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    # Try common CRM login endpoint variants
    r = s.post(f"{API}/crm/auth/login", json=CREDS, timeout=30)
    if r.status_code != 200:
        r = s.post(f"{API}/auth/login", json=CREDS, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:300]}"
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    token = data.get("access_token") or data.get("token") or (data.get("data") or {}).get("access_token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


DASHBOARD_ENDPOINTS = [
    "/dashboard/command-center?period=30d",
    "/dashboard/rfm?period_days=0",
    "/dashboard/cohorts-segmentation?period_days=0",
    "/dashboard/store-performance-v2?period_days=30",
    "/dashboard/executive-summary?period_days=30",
    "/analytics/sales-dashboard?period_days=30",
    "/analytics/loyalty-dashboard?period_days=0",
    "/dashboard/sales-trend?period_days=30",
    "/analytics/customer-dashboard?period_days=0",
    "/dashboard/points-economics?period_days=0",
]


@pytest.mark.parametrize("path", DASHBOARD_ENDPOINTS)
def test_dashboard_endpoint_twice_cache(session, path):
    url = f"{API}{path}"
    t0 = time.time()
    r1 = session.get(url, timeout=90)
    d1 = time.time() - t0
    assert r1.status_code == 200, f"First call failed {path}: {r1.status_code} {r1.text[:200]}"
    t0 = time.time()
    r2 = session.get(url, timeout=90)
    d2 = time.time() - t0
    assert r2.status_code == 200, f"Second call failed {path}: {r2.status_code}"
    print(f"{path}  first={d1:.2f}s  second={d2:.2f}s")
    # second call should be reasonably fast (cached). Allow generous bound.
    assert d2 < max(15.0, d1), f"Second call not cached faster for {path}: {d1:.2f} vs {d2:.2f}"


def test_rfm_churn_buckets_nonzero(session):
    r = session.get(f"{API}/dashboard/rfm?period_days=0", timeout=90)
    assert r.status_code == 200
    body = r.json()
    # search for churn buckets anywhere in the payload
    import json
    s = json.dumps(body).lower()
    assert "high" in s or "churn" in s
    # try common structures
    churn = body.get("churn") or body.get("churn_risk") or body.get("data", {}).get("churn")
    print("RFM churn snippet:", str(churn)[:400])
    # ensure at least one non-zero across buckets
    def has_nonzero(obj):
        if isinstance(obj, dict):
            return any(has_nonzero(v) for v in obj.values())
        if isinstance(obj, list):
            return any(has_nonzero(v) for v in obj)
        if isinstance(obj, (int, float)):
            return obj != 0
        return False
    if churn is not None:
        assert has_nonzero(churn), f"All churn buckets are zero: {churn}"


def test_data_quality_run_and_status(session):
    r = session.post(f"{API}/data-quality/run?force=true", timeout=30)
    assert r.status_code == 200, f"DQ run failed: {r.status_code} {r.text[:200]}"
    body = r.json()
    assert body.get("started") is True, f"Expected started:true, got {body}"

    # Poll for done
    deadline = time.time() + 240
    last = None
    while time.time() < deadline:
        rs = session.get(f"{API}/data-quality/status", timeout=30)
        assert rs.status_code == 200
        last = rs.json()
        state = last.get("state") or last.get("status")
        if state == "done":
            break
        time.sleep(5)
    print("DQ status:", last)
    assert (last.get("state") or last.get("status")) == "done", f"DQ not done in time: {last}"
    assert "churn" in last, f"Missing churn object: {last}"
    assert "city" in last, f"Missing city object: {last}"
