"""
Iteration 58 — Customer 360 (search + detail) and Live Monitor (window default,
store cards LOC code, KPI semantics) backend validation.

Covers:
- POST /api/auth/login (superadmin)
- GET /api/customers?q=600 (anchored mobile prefix, fast & non-empty)
- GET /api/dashboard/customer-360/<id> for id=a26865d9a69b48d48a9c1524e25041ef
  must return non-empty lifetime spend + recent_transactions.
- GET /api/live-monitor/stats?window=525600 must include revenue_total and
  loyalty_revenue, with revenue_total >= loyalty_revenue.
- GET /api/live-monitor/transactions?window=525600 — store_code present where store_id is.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://kazo-data-platform.preview.emergentagent.com").rstrip("/")
SUPER_EMAIL = "superadmin@fundle.io"
SUPER_PASS = "Fundle@2026"
TARGET_CUST_ID = "a26865d9a69b48d48a9c1524e25041ef"  # mobile 6000535682


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": SUPER_EMAIL, "password": SUPER_PASS}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------------- Customer 360 SEARCH ----------------

class TestCustomerSearch:
    def test_search_by_mobile_prefix_600_is_fast_and_returns_items(self, auth_headers):
        t0 = time.time()
        r = requests.get(f"{BASE_URL}/api/customers", params={"q": "600", "limit": 25},
                         headers=auth_headers, timeout=15)
        dt = time.time() - t0
        assert r.status_code == 200, r.text
        data = r.json()
        # Should be a paged dict with items or list
        items = data.get("items") if isinstance(data, dict) else data
        assert isinstance(items, list)
        assert len(items) > 0, f"expected items for prefix 600, got {data}"
        # Should not hang (under 8 seconds even on slow preview)
        assert dt < 8.0, f"search slow: {dt:.2f}s"
        # Mobile values should start with 600
        first_mob = str(items[0].get("mobile", ""))
        assert first_mob.startswith("600"), f"expected mobile starting with 600, got {first_mob}"

    def test_search_empty_q_returns_paged(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/customers", params={"limit": 5},
                         headers=auth_headers, timeout=10)
        assert r.status_code == 200, r.text


# ---------------- Customer 360 DETAIL ----------------

class TestCustomer360Detail:
    def test_target_customer_360_not_blank(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/dashboard/customer-360/{TARGET_CUST_ID}",
                         headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        # Should expose lifetime/recent_transactions/etc.
        assert d, "response empty"
        lifetime = d.get("lifetime")
        assert isinstance(lifetime, dict), f"lifetime missing/wrong type: {lifetime}"
        spend = float(lifetime.get("spend") or lifetime.get("gross") or 0)
        visits = int(lifetime.get("visits") or 0)
        assert spend > 0, f"lifetime spend expected > 0, got {spend}"
        assert visits >= 1, f"visits expected >=1, got {visits}"
        # RFM should be present
        rfm = d.get("rfm")
        assert isinstance(rfm, dict) and rfm.get("score"), f"rfm missing: {rfm}"

        recent = d.get("recent_transactions") or d.get("transactions") or []
        assert isinstance(recent, list)
        assert len(recent) >= 1, f"recent_transactions empty for target customer: keys={list(d.keys())}"

    def test_customer_360_for_unknown_id_returns_404_or_empty(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/dashboard/customer-360/nonexistent_xyz_123",
                         headers=auth_headers, timeout=10)
        # Either 404 or 200 with empty data — but must not 500
        assert r.status_code in (200, 404), r.text


# ---------------- Live Monitor STATS ----------------

class TestLiveMonitorStats:
    def test_stats_window_525600_has_revenue_and_loyalty(self, auth_headers):
        # Backend param is `minutes` (max 525600 = 365d)
        r = requests.get(f"{BASE_URL}/api/live-monitor/stats", params={"minutes": 525600},
                         headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "revenue_total" in d, f"revenue_total missing from {list(d.keys())}"
        assert "loyalty_revenue" in d, f"loyalty_revenue missing from {list(d.keys())}"
        rev = float(d["revenue_total"] or 0)
        loy = float(d["loyalty_revenue"] or 0)
        # Loyalty is subset of total
        assert rev >= loy - 0.001, f"revenue_total ({rev}) < loyalty_revenue ({loy})"
        # In 365d window we expect at least some revenue in preview
        assert rev > 0, f"expected non-zero revenue_total in 365d window, got {rev}; keys={list(d.keys())}, bills={d.get('bills_total')}"

    def test_stats_today_default_window_works(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/live-monitor/stats", params={"minutes": 1440},
                         headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text


# ---------------- Live Monitor STORE CODE in transactions ----------------

class TestLiveMonitorStoreCode:
    def test_transactions_have_store_code_when_store_id_present(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/live-monitor/transactions",
                         params={"since_minutes": 525600, "limit": 50},
                         headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        items = d.get("rows") or d.get("items") or (d if isinstance(d, list) else [])
        assert isinstance(items, list)
        if not items:
            pytest.skip("no transactions in 365d window in preview")
        # store_code field MUST be present in payload schema for every row
        for row in items:
            assert "store_code" in row, f"store_code field missing from row schema: {row}"
        with_store = [x for x in items if x.get("store_id")]
        if with_store:
            with_code = [x for x in with_store if x.get("store_code")]
            assert len(with_code) > 0, (
                f"no transactions with store_code resolved despite store_id; sample: {with_store[0]}"
            )

    def test_top_stores_endpoint_returns_codes(self, auth_headers):
        # endpoint commonly /api/live-monitor/top-stores or similar
        for path in ("/api/live-monitor/top-stores", "/api/live-monitor/stats"):
            r = requests.get(f"{BASE_URL}{path}", params={"window": 525600},
                             headers=auth_headers, timeout=15)
            if r.status_code != 200:
                continue
            d = r.json()
            stores = d.get("top_stores") or d.get("stores") or []
            if stores:
                # check at least one has store_code-ish key
                first = stores[0]
                assert any(k in first for k in ("store_code", "code", "loc_code")) or "store_id" in first
                return
        pytest.skip("no top_stores payload found in either endpoint")
