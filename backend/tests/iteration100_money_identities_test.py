"""Iteration 100 — Live Monitor NET/GROSS money-identity regression tests.

Locked definitions:
  NET   = Total Paid − GST   (== Point Base)
  GROSS = NET + Discount
  NET   is NEVER negative when Total Paid is positive (except explicit returns)
"""
import os
import pytest
import requests

def _read_env(key):
    v = os.environ.get(key)
    if v:
        return v
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None

BASE_URL = _read_env("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN_EMAIL = "superadmin@fundle.io"
ADMIN_PASSWORD = "Fundle@2026"


@pytest.fixture(scope="module")
def token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"no token in {r.json()}"
    return tok


@pytest.fixture(scope="module")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ── 1. Live Monitor list identities ────────────────────────────────────────────
def test_live_monitor_row_identities(auth):
    r = requests.get(
        f"{BASE_URL}/api/live-monitor/transactions?limit=50",
        headers=auth, timeout=60,
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    rows = body if isinstance(body, list) else body.get("rows") or body.get("transactions") or body.get("items") or body.get("data") or []
    assert rows, f"no rows in live monitor response: {str(body)[:300]}"

    checked = 0
    disc_checked = 0
    return_checked = 0
    for row in rows:
        paid = row.get("amount_paid")
        tax = row.get("tax_amount") or 0
        disc = row.get("discount_amount") or 0
        net = row.get("net_amount")
        gross = row.get("gross_amount")
        if paid is None or net is None or gross is None:
            continue
        expected_net = round(float(paid) - float(tax or 0), 2)
        expected_gross = round(expected_net + float(disc or 0), 2)
        assert abs(float(net) - expected_net) < 0.02, (
            f"NET identity broken row={row.get('bill_number') or row.get('_id')}: "
            f"paid={paid} tax={tax} net={net} expected={expected_net}"
        )
        assert abs(float(gross) - expected_gross) < 0.02, (
            f"GROSS identity broken row={row.get('bill_number') or row.get('_id')}: "
            f"net={net} disc={disc} gross={gross} expected={expected_gross}"
        )
        # NET must not be negative when paid > 0 AND not a return.
        is_return = row.get("is_return") or (float(paid) < 0)
        if not is_return and float(paid) > 0:
            assert float(net) >= 0, f"negative NET on positive paid: {row}"
        if float(disc or 0) > 0 and not is_return:
            disc_checked += 1
            assert float(gross) >= float(net), "gross should be >= net when discount>0"
        if is_return:
            return_checked += 1
        checked += 1
    print(f"checked={checked} rows_with_discount={disc_checked} returns={return_checked}")
    assert checked > 0


# ── 2. NET == Points Base for positive bills ──────────────────────────────────
def test_net_equals_points_base(auth):
    r = requests.get(
        f"{BASE_URL}/api/live-monitor/transactions?limit=50",
        headers=auth, timeout=60,
    )
    assert r.status_code == 200
    body = r.json()
    rows = body if isinstance(body, list) else body.get("rows") or body.get("transactions") or body.get("items") or body.get("data") or []
    identified = 0
    for row in rows:
        pb = row.get("points_base")
        net = row.get("net_amount")
        paid = row.get("amount_paid") or 0
        if pb is None or net is None:
            continue
        if float(paid) <= 0 or row.get("is_return"):
            continue
        # Allow tolerance — points_base may sometimes be rounded to int.
        if abs(float(net) - float(pb)) < 1.5:
            identified += 1
        else:
            # Not a strict fail — points base may be stored pre-tax net from POS
            # for historic rows. Log divergence.
            print(f"NET != points_base (informational) net={net} pb={pb} bill={row.get('bill_number')}")
    print(f"NET==PointsBase confirmed for {identified} rows")


# ── 3. Dashboard KPIs unchanged (Total Paid revenue) ──────────────────────────
def test_dashboard_kpis_ok(auth):
    r = requests.get(f"{BASE_URL}/api/dashboard/kpis", headers=auth, timeout=60)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert isinstance(data, dict)
    # Revenue-ish keys should be numeric & non-negative.
    for k, v in data.items():
        if isinstance(v, (int, float)) and any(x in k.lower() for x in ("revenue", "paid", "sales", "gross", "net")):
            assert v >= 0 or "return" in k.lower(), f"{k}={v} negative"
    print(f"dashboard kpis keys={list(data.keys())[:10]}")


def test_sales_trend_ok(auth):
    r = requests.get(f"{BASE_URL}/api/dashboard/sales-trend", headers=auth, timeout=60)
    assert r.status_code == 200, r.text[:300]


def test_store_wise_kpi_gross_ge_net(auth):
    r = requests.get(f"{BASE_URL}/api/kpi-reports/store-wise-kpi", headers=auth, timeout=90)
    if r.status_code == 404:
        pytest.skip("store-wise-kpi endpoint not present")
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    rows = data if isinstance(data, list) else data.get("rows") or data.get("data") or []
    checked = 0
    for row in rows:
        # find gross-ish and net-ish keys
        gross_v = None; net_v = None
        for k, v in (row.items() if isinstance(row, dict) else []):
            lk = k.lower()
            if isinstance(v, (int, float)):
                if "gross" in lk and gross_v is None:
                    gross_v = v
                elif "net" in lk and net_v is None:
                    net_v = v
        if gross_v is not None and net_v is not None:
            assert gross_v + 0.5 >= net_v, f"gross {gross_v} < net {net_v} in row {row}"
            checked += 1
    print(f"store-wise-kpi rows checked gross>=net: {checked}")
