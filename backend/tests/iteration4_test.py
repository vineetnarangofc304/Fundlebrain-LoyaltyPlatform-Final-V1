"""Iteration 4 — FundleBrain v2 endpoints: customer-360, store-performance-v2, rfm."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://loyalty-hub-118.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@kazo.com"
ADMIN_PASSWORD = "Kazo@2026"
STORE_EMAIL = "store.mumbai@kazo.com"
STORE_PASSWORD = "Kazo@2026"


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json().get("token") or r.json().get("access_token")


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def high_value_customer_id(admin_headers):
    """Find a customer with rich data via drilldown."""
    r = requests.post(
        f"{BASE_URL}/api/dashboard/drilldown",
        json={"collection": "customers", "filters": {}, "sort": [["lifetime_spend", -1]],
              "page": 1, "page_size": 5},
        headers=admin_headers, timeout=20,
    )
    assert r.status_code == 200, f"drilldown customers failed: {r.text}"
    rows = r.json().get("rows") or []
    assert rows, "no customers returned"
    cust_id = rows[0].get("id")
    assert cust_id
    return cust_id


# ============================================================
# Customer 360 v2
# ============================================================
class TestCustomer360V2:
    def test_404_on_unknown_id(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/dashboard/customer-360/UNKNOWN_ID_XYZ",
                         headers=admin_headers, timeout=20)
        assert r.status_code == 404

    def test_returns_full_payload(self, admin_headers, high_value_customer_id):
        r = requests.get(f"{BASE_URL}/api/dashboard/customer-360/{high_value_customer_id}",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        # Top-level structure
        for key in ("customer", "lifetime", "rfm", "monthly_spend",
                    "store_affinity", "category_affinity", "recent_transactions",
                    "points_ledger", "nps_history"):
            assert key in d, f"missing top-level key: {key}"

        # No mongo _id leaked
        assert "_id" not in d["customer"]
        assert "password_hash" not in d["customer"]

        # Lifetime aggregates have required keys
        for k in ("spend", "visits", "aov", "first_purchase", "last_purchase"):
            assert k in d["lifetime"], f"lifetime missing {k}"

        # RFM structure
        rfm = d["rfm"]
        for k in ("r", "f", "m", "score", "segment", "recency_days", "frequency", "monetary"):
            assert k in rfm
        assert 1 <= rfm["r"] <= 5
        assert 1 <= rfm["f"] <= 5
        assert 1 <= rfm["m"] <= 5
        valid_segments = {"Champions", "Loyalists", "Big Spenders", "Promising",
                          "New Customers", "Potential Loyalists", "Cant Lose Them",
                          "At Risk", "About to Sleep", "Hibernating", "Lost"}
        assert rfm["segment"] in valid_segments, f"unexpected segment {rfm['segment']}"

        # monthly_spend is list, each row has month + spend
        assert isinstance(d["monthly_spend"], list)
        if d["monthly_spend"]:
            row = d["monthly_spend"][0]
            assert "month" in row and "spend" in row and "visits" in row

        # affinity lists
        assert isinstance(d["store_affinity"], list)
        assert isinstance(d["category_affinity"], list)
        assert isinstance(d["recent_transactions"], list)


# ============================================================
# Store Performance v2
# ============================================================
class TestStorePerformanceV2:
    @pytest.mark.parametrize("period_days", [7, 30, 90])
    def test_period_variants(self, admin_headers, period_days):
        r = requests.get(f"{BASE_URL}/api/dashboard/store-performance-v2",
                         params={"period_days": period_days},
                         headers=admin_headers, timeout=60)
        assert r.status_code == 200, f"period={period_days}: {r.text}"
        d = r.json()
        assert d["period_days"] == period_days
        for key in ("leaderboard", "by_city", "by_day", "heatmap", "generated_at"):
            assert key in d, f"missing {key}"

        # Heatmap is 7*24 = 168 cells
        assert len(d["heatmap"]) == 168, f"heatmap has {len(d['heatmap'])} cells"
        # Heatmap cells
        cell = d["heatmap"][0]
        for k in ("day", "hour", "net", "txns"):
            assert k in cell

        # by_day has up to 7 weekdays
        assert isinstance(d["by_day"], list)
        assert len(d["by_day"]) <= 7
        if d["by_day"]:
            assert "day" in d["by_day"][0]
            assert "net" in d["by_day"][0]

    def test_leaderboard_structure(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/dashboard/store-performance-v2",
                         params={"period_days": 30}, headers=admin_headers, timeout=60)
        d = r.json()
        lb = d["leaderboard"]
        assert isinstance(lb, list)
        if lb:
            row = lb[0]
            for k in ("rank", "store_id", "store_name", "net", "aov", "upt",
                      "unique_customers", "txns", "delta_pct"):
                assert k in row, f"leaderboard row missing {k}"
            assert row["rank"] == 1
            # rows sorted by net desc
            nets = [r["net"] for r in lb]
            assert nets == sorted(nets, reverse=True)

    def test_by_city_has_stores_count(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/dashboard/store-performance-v2",
                         params={"period_days": 30}, headers=admin_headers, timeout=60)
        d = r.json()
        by_city = d["by_city"]
        assert isinstance(by_city, list)
        if by_city:
            row = by_city[0]
            for k in ("city", "net", "txns", "stores", "unique_customers", "aov"):
                assert k in row
            assert isinstance(row["stores"], int)
            assert row["stores"] >= 1


# ============================================================
# RFM & Churn dashboard
# ============================================================
class TestRFMDashboard:
    @pytest.fixture(scope="class")
    def rfm(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/dashboard/rfm", headers=admin_headers, timeout=60)
        assert r.status_code == 200, r.text
        return r.json()

    def test_structure(self, rfm):
        for k in ("total_customers", "rfm_cutoffs", "heatmap", "segments",
                  "churn_distribution", "generated_at"):
            assert k in rfm

    def test_cutoffs(self, rfm):
        cuts = rfm["rfm_cutoffs"]
        for key in ("recency_days_q", "frequency_q", "monetary_inr_q"):
            assert key in cuts
            assert len(cuts[key]) == 4, f"{key} should have 4 quintile cuts"

    def test_heatmap_25_cells(self, rfm):
        hm = rfm["heatmap"]
        assert len(hm) == 25
        # all r in 1..5 and f in 1..5
        rs = sorted({c["r"] for c in hm})
        fs = sorted({c["f"] for c in hm})
        assert rs == [1, 2, 3, 4, 5]
        assert fs == [1, 2, 3, 4, 5]
        for c in hm:
            assert "count" in c and "pct" in c and "avg_spend" in c

    def test_heatmap_count_sum_equals_total(self, rfm):
        total = rfm["total_customers"]
        s = sum(c["count"] for c in rfm["heatmap"])
        assert s == total, f"heatmap sum {s} != total {total}"

    def test_11_segments_exist(self, rfm):
        segs = rfm["segments"]
        assert len(segs) == 11
        names = {s["segment"] for s in segs}
        expected = {"Champions", "Loyalists", "Big Spenders", "Promising",
                    "New Customers", "Potential Loyalists", "Cant Lose Them",
                    "At Risk", "About to Sleep", "Hibernating", "Lost"}
        assert names == expected
        for s in segs:
            for k in ("count", "pct", "total_spend", "examples"):
                assert k in s
            assert isinstance(s["examples"], list)

    def test_segment_counts_close_to_total(self, rfm):
        """11-segment classifier is permissive — sum may differ slightly. Allow 5% overlap."""
        total = rfm["total_customers"]
        seg_sum = sum(s["count"] for s in rfm["segments"])
        # Sum should be within ±10% of total (per spec note)
        assert abs(seg_sum - total) <= max(50, int(total * 0.10)), \
            f"segment sum {seg_sum} not close to total {total}"

    def test_churn_buckets(self, rfm):
        ch = rfm["churn_distribution"]
        for k in ("low", "medium", "high"):
            assert k in ch
            assert isinstance(ch[k], int)


# ============================================================
# Auth checks
# ============================================================
class TestAuth:
    def test_customer_360_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/dashboard/customer-360/anything", timeout=15)
        assert r.status_code in (401, 403)

    def test_store_perf_v2_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/dashboard/store-performance-v2", timeout=15)
        assert r.status_code in (401, 403)

    def test_rfm_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/dashboard/rfm", timeout=15)
        assert r.status_code in (401, 403)


# ============================================================
# Regression: existing iteration-3 endpoints still work
# ============================================================
class TestRegression:
    def test_command_center(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/dashboard/command-center",
                         params={"period": "30d"}, headers=admin_headers, timeout=30)
        assert r.status_code == 200

    def test_sales_dashboard(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/analytics/sales-dashboard",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200

    def test_customer_dashboard(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/analytics/customer-dashboard",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200

    def test_loyalty_dashboard(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/analytics/loyalty-dashboard",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200

    def test_campaign_dashboard(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/analytics/campaign-dashboard",
                         headers=admin_headers, timeout=30)
        assert r.status_code == 200
