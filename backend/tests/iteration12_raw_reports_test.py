"""Iteration 12 — Raw Reports backend tests."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://fundle-brain-ai-1.preview.emergentagent.com").rstrip("/")
LOGIN = {"email": "superadmin@fundle.io", "password": "Fundle@2026"}


@pytest.fixture(scope="module")
def auth():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=LOGIN, timeout=15)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"}


# --- Customer Data (all 6 group_by) ---
@pytest.mark.parametrize("gb", ["location", "city", "state", "zone", "month", "tier"])
def test_customer_data_groupings(auth, gb):
    r = requests.post(f"{BASE_URL}/api/raw-reports/customer-data", json={"group_by": gb, "page_size": 50}, headers=auth, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["group_by"] == gb
    assert "rows" in data and "totals" in data
    if data["rows"]:
        sample = data["rows"][0]
        assert "group_key" in sample
        assert "total_customers" in sample
        # location/city/state/zone -> txn fields
        if gb in {"location", "city", "state", "zone"}:
            assert "total_bills" in sample
            assert "repeat_pct" in sample
            assert "avg_lifetime_spend" in sample
        else:  # month / tier
            assert "avg_lifetime_spend" in sample


def test_customer_data_month_differs_from_location(auth):
    a = requests.post(f"{BASE_URL}/api/raw-reports/customer-data", json={"group_by": "location"}, headers=auth, timeout=30).json()
    b = requests.post(f"{BASE_URL}/api/raw-reports/customer-data", json={"group_by": "month"}, headers=auth, timeout=30).json()
    keys_a = sorted(r["group_key"] for r in a["rows"])
    keys_b = sorted(r["group_key"] for r in b["rows"])
    assert keys_a != keys_b, "month grouping returned same group_keys as location (the historical bug)"
    if keys_b:
        # YYYY-MM format
        assert all(len(str(k)) == 7 and str(k)[4] == "-" for k in keys_b), f"month keys not YYYY-MM: {keys_b[:5]}"


def test_customer_data_tier_differs(auth):
    b = requests.post(f"{BASE_URL}/api/raw-reports/customer-data", json={"group_by": "tier"}, headers=auth, timeout=30).json()
    keys = {r["group_key"] for r in b["rows"]}
    # Tier should typically include some of: silver/gold/platinum/bronze
    assert keys, "tier grouping returned no rows"


# --- Transaction Data ---
@pytest.mark.parametrize("gb", ["location", "city", "state", "zone", "month"])
def test_transaction_data(auth, gb):
    r = requests.post(f"{BASE_URL}/api/raw-reports/transaction-data", json={"group_by": gb}, headers=auth, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    if data["rows"]:
        s = data["rows"][0]
        for col in ("total_gross_purchase", "total_discount", "discount_pct", "avg_bill_value", "avg_customer_spend"):
            assert col in s, f"Missing enriched col {col} in transaction-data/{gb}"


# --- Repeat Purchases ---
def test_repeat_purchases(auth):
    r = requests.post(f"{BASE_URL}/api/raw-reports/repeat-purchases", json={"group_by": "location"}, headers=auth, timeout=60)
    assert r.status_code == 200, r.text
    data = r.json()
    if data["rows"]:
        s = data["rows"][0]
        required = [
            "purchase_unique_customers", "purchase_total_bills", "purchase_total_purchase",
            "repeat_total_unique_customers", "repeat_total_bills", "repeat_total_purchase",
            "repeat_current_unique_customers", "repeat_current_bills", "repeat_current_purchase",
            "repeat_earlier_unique_customers", "repeat_earlier_bills", "repeat_earlier_purchase",
            "group_key",
        ]
        for f in required:
            assert f in s, f"repeat-purchases missing column {f}"
    # totals dict has all 12
    t = data["totals"]
    for f in ("purchase_unique_customers", "purchase_total_bills", "purchase_total_purchase",
              "repeat_total_unique_customers", "repeat_total_bills", "repeat_total_purchase",
              "repeat_current_unique_customers", "repeat_current_bills", "repeat_current_purchase",
              "repeat_earlier_unique_customers", "repeat_earlier_bills", "repeat_earlier_purchase"):
        assert f in t, f"totals missing {f}"


# --- Earn-Redeem ---
def test_earn_redeem(auth):
    r = requests.post(f"{BASE_URL}/api/raw-reports/earn-redeem", json={"group_by": "location"}, headers=auth, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    if data["rows"]:
        s = data["rows"][0]
        assert "gross_points_earned" in s
        assert "redemption_rate_pct" in s
    # totals
    assert "gross_points_earned" in data["totals"] or not data["rows"]


# --- Customers by Visit ---
def test_customers_by_visit(auth):
    r = requests.post(f"{BASE_URL}/api/raw-reports/customers-by-visit", json={"group_by": "location"}, headers=auth, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    if data["rows"]:
        s = data["rows"][0]
        assert "visits" in s
        assert "total_customers" in s
        assert "total_purchase" in s
        assert "avg_customer_spend" in s


# --- Drill ---
def test_drill_customer_data(auth):
    # First get a real group_key
    r = requests.post(f"{BASE_URL}/api/raw-reports/customer-data", json={"group_by": "location"}, headers=auth, timeout=30).json()
    if not r["rows"]:
        pytest.skip("No rows to drill")
    gk = r["rows"][0]["group_key"]
    d = requests.post(f"{BASE_URL}/api/raw-reports/drill",
                      json={"report": "customer-data", "group_by": "location",
                            "group_key": gk, "filters": {"group_by": "location"}},
                      headers=auth, timeout=30)
    assert d.status_code == 200, d.text
    payload = d.json()
    assert "rows" in payload and "total" in payload
    if payload["rows"]:
        c = payload["rows"][0]
        assert "mobile" in c


def test_drill_visits_bucket(auth):
    d = requests.post(f"{BASE_URL}/api/raw-reports/drill",
                      json={"report": "customers-by-visit", "group_by": "location",
                            "group_key": "", "visits": 1, "filters": {"group_by": "location"}},
                      headers=auth, timeout=30)
    assert d.status_code == 200, d.text


# --- Narrative ---
def test_narrative(auth):
    body = {
        "report": "customer-data", "group_by": "location",
        "rows": [{"group_key": "Store A", "total_customers": 100}],
        "totals": {"total_customers": 100},
        "filters": {"group_by": "location"},
    }
    r = requests.post(f"{BASE_URL}/api/raw-reports/narrative", json=body, headers=auth, timeout=90)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["source"] in ("fundle_brain_gpt5", "template_fallback")
    assert "bullets" in data
    assert "narrative" in data


# --- Export ---
@pytest.mark.parametrize("fmt,ctype", [
    ("csv", "text/csv"),
    ("xlsx", "spreadsheetml"),
    ("pdf", "application/pdf"),
])
def test_export(auth, fmt, ctype):
    body = {
        "report": "customer-data", "group_by": "location",
        "columns": [{"key": "group_key", "label": "Location"}, {"key": "total_customers", "label": "Customers"}],
        "rows": [{"group_key": "Store A", "total_customers": 100}],
        "totals": {"total_customers": 100},
        "format": fmt,
    }
    r = requests.post(f"{BASE_URL}/api/raw-reports/export", json=body, headers=auth, timeout=30)
    assert r.status_code == 200, r.text
    assert ctype in r.headers.get("Content-Type", ""), f"got {r.headers.get('Content-Type')}"
    assert "attachment" in r.headers.get("Content-Disposition", "")
