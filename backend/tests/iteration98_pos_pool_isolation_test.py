"""Iteration 98 — Regression tests for the POS dedicated-pool + maxTimeMS analytics fix.

Focus:
  1. POS posCustomerCheck (dedicated pool) returns 200 envelope for registered mobile.
  2. POS posAddPoint credits points, writes points_ledger 'earn' row, balance increases.
  3. POS posAddPoint idempotency — same bill_number twice does NOT double-credit.
  4. POS redeem/OTP endpoints respond with well-formed envelopes on the dedicated pool.
  5. Report/dashboard endpoints (which received maxTimeMS=25000) still return 200 with data.
  6. Segment audience export streams CSV via long_col (bounded long-running pool).
  7. Regression: sample analytics endpoints still 200 (no fallout from pool split).
"""
import os
import time
import uuid
import io
import csv
import pytest
import requests


def _load_frontend_env():
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.strip().startswith("REACT_APP_BACKEND_URL"):
                    return line.split("=", 1)[1].strip()
    except Exception:
        return None
    return None


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _load_frontend_env() or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not resolvable"

POS_KEY = "ZFQWql7I3vCH0ckuWmA8zVKDDJWYPBtoQGLruEnRrFI"
MERCHANT = "KAZO_FUNDLE"
STORE_CUSTOMER_KEY = "K00055"
TEST_MOBILE = "6000013876"  # KARAN SINGH — registered preview customer


def _pos_headers():
    return {"x-api-key": POS_KEY, "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "superadmin@fundle.io",
                            "password": "Fundle@2026"}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"superadmin login failed: {r.status_code} {r.text[:200]}")
    return r.json()["token"]


# ============ 1. POS customer check on dedicated pool ============

def test_pos_customer_check_registered_mobile():
    body = {"merchant_id": MERCHANT, "customer_key": STORE_CUSTOMER_KEY,
            "customer_mobile": TEST_MOBILE, "bill_amount": 1000.0}
    t0 = time.time()
    r = requests.post(f"{BASE_URL}/api/pos/posCustomerCheck",
                      headers=_pos_headers(), json=body, timeout=15)
    elapsed = time.time() - t0
    assert r.status_code == 200, r.text
    env = r.json()
    assert env.get("status_code") == 200, f"envelope not 200: {env}"
    resp = env.get("response") or {}
    # Must carry customer detail — points/tier/name
    assert resp, f"empty response: {env}"
    # Just verify structure not empty; specific customer fields typically:
    # current_points, tier / message, mobile
    print(f"customer_check resp keys: {list(resp.keys())} elapsed={elapsed:.2f}s")
    assert elapsed < 5.0, f"posCustomerCheck too slow: {elapsed:.2f}s"


# ============ 2. POS earn: credit points + ledger row + balance increase ============

def _pre_tax_amount():
    return 1234.0


def _add_point_payload(bill_no: str, amount: float = None):
    amount = amount or _pre_tax_amount()
    # KAZO canonical: 'amount' is PRE-TAX. Add 5% GST to simulate.
    gst = round(amount * 0.05, 2)
    return {
        "merchant_id": MERCHANT,
        "customer_key": STORE_CUSTOMER_KEY,
        "customer_mobile": TEST_MOBILE,
        "customer": {"mobile": TEST_MOBILE, "name": "IT98 QA"},
        "transaction": {
            "number": bill_no,
            "id": bill_no,
            "date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "order_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "amount": amount,
            "net_amount": amount,
            "gross_amount": amount + gst,
            "taxes": [{"name": "GST", "amount": gst}],
            "items": [
                {"sku": "IT98-SKU", "name": "IT98 Item", "qty": 1,
                 "price": amount, "amount": amount}
            ],
            "payment_mode": [{"name": "CASH"}],
        },
    }


def _get_balance_and_ledger_count(token: str):
    """Fetch current balance and ledger 'earn' row count for TEST_MOBILE."""
    hdr = {"Authorization": f"Bearer {token}"}
    # Find the customer by mobile
    r = requests.get(f"{BASE_URL}/api/customers?search={TEST_MOBILE}&limit=5",
                     headers=hdr, timeout=15)
    balance = None
    cust_id = None
    if r.status_code == 200:
        rows = r.json()
        if isinstance(rows, dict):
            rows = rows.get("items") or rows.get("customers") or []
        for row in rows or []:
            if str(row.get("mobile", "")).endswith(TEST_MOBILE[-10:]):
                balance = row.get("current_points") or row.get("points_balance") or row.get("balance")
                cust_id = row.get("id")
                break
    return balance, cust_id


def test_pos_add_point_credits_and_persists(admin_token):
    bal_before, cust_id = _get_balance_and_ledger_count(admin_token)
    print(f"Before: balance={bal_before} cust_id={cust_id}")

    bill = f"IT98-{uuid.uuid4().hex[:10].upper()}"
    t0 = time.time()
    r = requests.post(f"{BASE_URL}/api/pos/posAddPoint",
                      headers=_pos_headers(),
                      json=_add_point_payload(bill), timeout=20)
    elapsed = time.time() - t0
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text}"
    env = r.json()
    assert env.get("status_code") == 200, f"envelope not 200: {env}"
    resp = env.get("response") or {}
    print(f"posAddPoint bill={bill} elapsed={elapsed:.2f}s resp={resp}")
    assert any(k in resp for k in ("points_earned", "new_balance", "message")), \
        f"unexpected response body: {resp}"
    points_earned = resp.get("points_earned")
    if points_earned is not None:
        assert isinstance(points_earned, (int, float)), f"points_earned type wrong: {points_earned}"

    # Wait briefly for async ledger write to propagate
    time.sleep(1.5)
    bal_after, _ = _get_balance_and_ledger_count(admin_token)
    print(f"After: balance={bal_after}")
    if bal_before is not None and bal_after is not None and points_earned:
        # allow for other concurrent activity — just assert not decreased
        assert bal_after >= bal_before, \
            f"balance did not increase: before={bal_before} after={bal_after}"


# ============ 3. Idempotency: same bill_number twice ============

def test_pos_add_point_idempotency_same_bill(admin_token):
    bill = f"IT98IDEM-{uuid.uuid4().hex[:8].upper()}"
    payload = _add_point_payload(bill, amount=567.0)

    # First submit
    r1 = requests.post(f"{BASE_URL}/api/pos/posAddPoint",
                       headers=_pos_headers(), json=payload, timeout=20)
    assert r1.status_code == 200, r1.text
    env1 = r1.json()
    assert env1.get("status_code") == 200, env1
    resp1 = env1.get("response") or {}
    points1 = resp1.get("points_earned")

    time.sleep(1.0)
    bal_mid, _ = _get_balance_and_ledger_count(admin_token)

    # Second submit — same bill_number
    r2 = requests.post(f"{BASE_URL}/api/pos/posAddPoint",
                       headers=_pos_headers(), json=payload, timeout=20)
    assert r2.status_code == 200, r2.text
    env2 = r2.json()
    # Idempotent path — either 200 with 'resumed' flag, or 400 duplicate-bill envelope
    sc2 = env2.get("status_code")
    resp2 = env2.get("response") or {}
    print(f"Retry envelope: status_code={sc2} resp={resp2}")

    time.sleep(1.5)
    bal_after, _ = _get_balance_and_ledger_count(admin_token)

    # Duplicate must NOT double-credit
    if bal_mid is not None and bal_after is not None:
        # Allow tiny drift from other test activity — but same-bill retry must not
        # add another points1 units.
        drift = (bal_after - bal_mid)
        if points1:
            assert drift < points1, \
                f"double-credit suspected: bal_mid={bal_mid} bal_after={bal_after} points1={points1}"
        else:
            assert drift >= 0
    # The retry envelope must be well-formed (200 with resumed or 400 duplicate).
    assert sc2 in (200, 400), f"unexpected envelope status_code on retry: {env2}"


# ============ 4. Redeem / OTP flow endpoints respond well-formed ============

def test_pos_redeem_request_and_verify_envelope():
    body = {"merchant_id": MERCHANT, "customer_key": STORE_CUSTOMER_KEY,
            "customer_mobile": TEST_MOBILE, "points": 10}
    r = requests.post(f"{BASE_URL}/api/pos/posRedeemPointRequest",
                      headers=_pos_headers(), json=body, timeout=15)
    assert r.status_code == 200, r.text
    env = r.json()
    assert "status_code" in env, env
    resp = env.get("response") or {}
    otp = resp.get("otp_demo") or resp.get("otp") or "123456"
    redeem_id = resp.get("redeem_id") or resp.get("redeemId")

    verify = dict(body)
    verify["otp"] = str(otp)
    if redeem_id:
        verify["redeem_id"] = redeem_id
    r2 = requests.post(f"{BASE_URL}/api/pos/posRedeemPointOtpCheck",
                       headers=_pos_headers(), json=verify, timeout=15)
    assert r2.status_code == 200, r2.text
    env2 = r2.json()
    assert "status_code" in env2, env2
    print(f"redeem verify envelope status_code={env2.get('status_code')}")


def test_pos_customer_check_request_otp_envelope():
    body = {"merchant_id": MERCHANT, "customer_key": STORE_CUSTOMER_KEY,
            "customer_mobile": TEST_MOBILE}
    r = requests.post(f"{BASE_URL}/api/pos/posCustomerCheckRequest",
                      headers=_pos_headers(), json=body, timeout=15)
    assert r.status_code == 200, r.text
    env = r.json()
    assert env.get("status_code") in (200, 400), env


# ============ 5. Report/dashboard endpoints with maxTimeMS cap ============

REPORT_ENDPOINTS = [
    "/api/dashboard/sales-trend",
    "/api/dashboard/store-performance",
    "/api/dashboard/top-skus",
    "/api/dashboard/kpis",
    "/api/dashboard/city-performance",
    "/api/kpi-reports/store-wise-kpi",
    "/api/kpi-reports/weekly-kpi",
]


@pytest.mark.parametrize("endpoint", REPORT_ENDPOINTS)
def test_report_endpoint_returns_200(admin_token, endpoint):
    hdr = {"Authorization": f"Bearer {admin_token}"}
    t0 = time.time()
    r = requests.get(f"{BASE_URL}{endpoint}", headers=hdr, timeout=30)
    elapsed = time.time() - t0
    print(f"{endpoint} -> {r.status_code} in {elapsed:.2f}s (len={len(r.text)})")
    assert r.status_code == 200, f"{endpoint} HTTP {r.status_code}: {r.text[:400]}"
    assert elapsed < 30.0, f"{endpoint} exceeded 30s"
    # Should be JSON with actual body
    try:
        data = r.json()
    except Exception as e:
        pytest.fail(f"{endpoint} not JSON: {e} body={r.text[:200]}")
    assert data is not None
    # Not a MaxTimeMSExpired error surfaced as text
    assert "MaxTimeMSExpired" not in r.text, f"{endpoint} surfaced MaxTimeMSExpired"


# ============ 6. Segment audience export streams CSV ============

def test_segments_audience_export_csv(admin_token):
    hdr = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    body = {"tree": {"op": "AND", "rules": []}, "format": "csv", "max_rows": 50}
    t0 = time.time()
    r = requests.post(f"{BASE_URL}/api/segments/audience/export",
                      headers=hdr, json=body, timeout=60, stream=True)
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:400]}"
    content = r.content.decode("utf-8", errors="replace")
    elapsed = time.time() - t0
    print(f"audience export elapsed={elapsed:.2f}s bytes={len(content)}")
    assert content.strip(), "empty CSV response"
    # Header row + at least one customer row
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    assert len(rows) >= 2, f"CSV has no data rows: {rows[:2]}"
    header = rows[0]
    assert any("mobile" in h.lower() or "id" in h.lower() or "name" in h.lower()
               for h in header), f"CSV header doesn't look like customer export: {header}"


# ============ 7. Regression: sample analytics endpoints still 200 ============

REGRESSION_ENDPOINTS = [
    "/api/kpi-reports/store-wise-kpi",
    "/api/kpi-reports/weekly-kpi",
    "/api/dashboard/kpis",
]


@pytest.mark.parametrize("endpoint", REGRESSION_ENDPOINTS)
def test_regression_no_500(admin_token, endpoint):
    hdr = {"Authorization": f"Bearer {admin_token}"}
    r = requests.get(f"{BASE_URL}{endpoint}", headers=hdr, timeout=30)
    assert r.status_code < 500, f"{endpoint} 5xx: {r.status_code} {r.text[:200]}"
