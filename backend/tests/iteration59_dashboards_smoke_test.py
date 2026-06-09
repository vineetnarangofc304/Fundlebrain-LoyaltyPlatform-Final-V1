"""
Iteration 59 — Smoke test for ALL dashboards + raw reports + sales/live-monitor
after applying allowDiskUse=True and Command Center timeout/cache fixes.

We only assert: 200 status, JSON parseable, and (where applicable) the expected
top-level keys. Data magnitude is NOT validated — preview has tiny data.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "http://localhost:8001"

CREDS = {"email": "superadmin@fundle.io", "password": "Fundle@2026"}


@pytest.fixture(scope="session")
def auth_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json=CREDS, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("token") or r.json().get("access_token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# --- 1) Command Center ----------------------------------------------------- #
class TestCommandCenter:
    def test_command_center_period_all(self, auth_session):
        r = auth_session.get(
            f"{BASE_URL}/api/dashboard/command-center",
            params={"period": "all"},
            timeout=60,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        body = r.json()
        assert "kpis" in body and isinstance(body["kpis"], dict)
        # required KPI keys (preview values may be 0)
        for key in [
            "net_sales", "aov", "active_customers", "total_customers",
            "repeat_rate_pct", "api_health_pct", "transactions",
            "outstanding_points", "outstanding_liability_inr",
        ]:
            assert key in body["kpis"], f"missing kpi {key}"
        assert "cohort_distribution" in body
        assert "alerts" in body
        assert "sparkline" in body

    @pytest.mark.parametrize("period", ["today", "7d", "30d", "90d", "1y", "mtd", "ytd"])
    def test_command_center_other_periods(self, auth_session, period):
        r = auth_session.get(
            f"{BASE_URL}/api/dashboard/command-center",
            params={"period": period},
            timeout=60,
        )
        assert r.status_code == 200, f"period={period} -> {r.status_code} {r.text[:200]}"

    def test_command_center_with_city_filter(self, auth_session):
        # pull a valid city first
        opts = auth_session.get(f"{BASE_URL}/api/dashboard/filter-options", timeout=30)
        assert opts.status_code == 200
        cities = opts.json().get("cities", [])
        if not cities:
            pytest.skip("no cities in filter-options (preview empty)")
        r = auth_session.get(
            f"{BASE_URL}/api/dashboard/command-center",
            params={"period": "all", "city": cities[0]},
            timeout=60,
        )
        assert r.status_code == 200


# --- 2) Sales / Customer / Loyalty / Campaign / Store / NPS dashboards ----- #
class TestAnalyticsDashboards:
    @pytest.mark.parametrize("path", [
        "/api/analytics/sales-dashboard",
        "/api/analytics/customer-dashboard",
        "/api/analytics/loyalty-dashboard",
        "/api/analytics/campaign-dashboard",
        "/api/analytics/store-dashboard",
        "/api/analytics/nps-dashboard",
    ])
    def test_dashboard_200(self, auth_session, path):
        r = auth_session.get(f"{BASE_URL}{path}", params={"period": "all"}, timeout=60)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:300]}"


# --- 3) Fundle-brain dashboards (RFM / Cohorts / Points / ROI / Exec) ------ #
class TestFundleBrainDashboards:
    @pytest.mark.parametrize("path", [
        "/api/dashboard/rfm",
        "/api/dashboard/cohorts-segmentation",
        "/api/dashboard/points-economics",
        "/api/dashboard/campaign-roi",
        "/api/dashboard/executive-summary",
        "/api/dashboard/store-performance-v2",
    ])
    def test_fb_dashboard_200(self, auth_session, path):
        r = auth_session.get(f"{BASE_URL}{path}", params={"period": "all"}, timeout=60)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:300]}"


# --- 4) Sales-trend + filter-options + city-performance -------------------- #
class TestSalesAuxEndpoints:
    def test_sales_trend(self, auth_session):
        r = auth_session.get(
            f"{BASE_URL}/api/dashboard/sales-trend",
            params={"period": "all"},
            timeout=60,
        )
        assert r.status_code == 200

    def test_filter_options(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/dashboard/filter-options", timeout=30)
        assert r.status_code == 200
        body = r.json()
        assert "cities" in body and "stores" in body

    def test_city_performance(self, auth_session):
        r = auth_session.get(
            f"{BASE_URL}/api/dashboard/city-performance",
            params={"period": "all"},
            timeout=60,
        )
        assert r.status_code == 200


# --- 5) Raw reports (POST) ------------------------------------------------- #
class TestRawReports:
    @pytest.mark.parametrize("endpoint,group_by", [
        ("customer-data", "city"),
        ("customer-data", "tier"),
        ("customer-data", "month"),
        ("customer-data", "state"),
        ("customer-data", "zone"),
        ("transaction-data", "city"),
        ("transaction-data", "month"),
        ("transaction-data", "location"),
        ("repeat-purchases", None),
        ("earn-redeem", None),
        ("customers-by-visit", None),
    ])
    def test_report_200(self, auth_session, endpoint, group_by):
        payload = {"period": "all", "page": 1, "page_size": 25}
        if group_by:
            payload["group_by"] = group_by
        r = auth_session.post(
            f"{BASE_URL}/api/raw-reports/{endpoint}",
            json=payload,
            timeout=120,
        )
        assert r.status_code == 200, (
            f"{endpoint} group_by={group_by} -> {r.status_code} {r.text[:300]}"
        )
        body = r.json()
        # Most reports return either a list or {rows/data,total,...}
        assert isinstance(body, (dict, list))


# --- 6) Live monitor ------------------------------------------------------- #
class TestLiveMonitor:
    def test_stats_today(self, auth_session):
        r = auth_session.get(
            f"{BASE_URL}/api/live-monitor/stats", params={"minutes": 1440}, timeout=30
        )
        assert r.status_code == 200
        body = r.json()
        # Total purchase >= loyalty purchase
        rt = body.get("revenue_total", 0) or 0
        lr = body.get("loyalty_revenue", 0) or 0
        assert rt >= lr, f"revenue_total({rt}) must be >= loyalty_revenue({lr})"

    def test_stats_365d(self, auth_session):
        r = auth_session.get(
            f"{BASE_URL}/api/live-monitor/stats", params={"minutes": 525600}, timeout=30
        )
        assert r.status_code == 200


# --- 7) Customer 360 list + detail ----------------------------------------- #
class TestCustomer360:
    def test_customers_list_paginated(self, auth_session):
        r = auth_session.get(
            f"{BASE_URL}/api/customers", params={"page": 1, "page_size": 25}, timeout=30
        )
        assert r.status_code == 200

    def test_customers_search_prefix(self, auth_session):
        r = auth_session.get(
            f"{BASE_URL}/api/customers", params={"q": "9", "page": 1, "page_size": 5}, timeout=20
        )
        assert r.status_code == 200

    def test_customer_360_detail(self, auth_session):
        r = auth_session.get(
            f"{BASE_URL}/api/customers", params={"page": 1, "page_size": 1}, timeout=20
        )
        assert r.status_code == 200
        items = r.json().get("items") or r.json().get("data") or r.json()
        if isinstance(items, dict):
            items = items.get("items") or []
        if not items:
            pytest.skip("no customers in preview")
        cid = items[0].get("id") or items[0].get("_id")
        if not cid:
            pytest.skip("customer id missing")
        d = auth_session.get(
            f"{BASE_URL}/api/dashboard/customer-360/{cid}", timeout=30
        )
        assert d.status_code == 200, f"detail -> {d.status_code} {d.text[:200]}"
