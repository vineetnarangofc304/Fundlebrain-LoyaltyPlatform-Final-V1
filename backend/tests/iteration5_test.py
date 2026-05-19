"""Iteration 5 backend tests — Cohorts, Points Economics, Campaign ROI,
Executive Summary, Executive Summary PDF, Formula Catalog."""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL').rstrip('/')
ADMIN_EMAIL = "admin@kazo.com"
ADMIN_PW = "Kazo@2026"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PW},
                      timeout=15)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text[:200]}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


# -------- Cohorts & Segmentation --------
class TestCohorts:
    def test_cohorts_schema(self, headers):
        r = requests.get(f"{BASE_URL}/api/dashboard/cohorts-segmentation", headers=headers, timeout=60)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        for k in ["total_customers", "transacted_customers", "untransacted_customers",
                  "frequency_segments", "spend_segments", "tier_segments",
                  "one_timer", "retention_triangle", "acquisition_trend"]:
            assert k in d, f"missing {k}"
        assert d["total_customers"] >= d["transacted_customers"]
        assert d["total_customers"] == d["transacted_customers"] + d["untransacted_customers"]

    def test_freq_segments_mutual_exclusive(self, headers):
        d = requests.get(f"{BASE_URL}/api/dashboard/cohorts-segmentation", headers=headers, timeout=60).json()
        assert len(d["frequency_segments"]) == 5
        total = sum(s["count"] for s in d["frequency_segments"])
        assert total == d["transacted_customers"], f"freq sum {total} vs transacted {d['transacted_customers']}"
        for s in d["frequency_segments"]:
            for f in ["count", "atv", "avg_lifetime_spend", "total_spend", "examples"]:
                assert f in s, f"missing {f} in {s['key']}"

    def test_spend_segments_count(self, headers):
        d = requests.get(f"{BASE_URL}/api/dashboard/cohorts-segmentation", headers=headers, timeout=60).json()
        assert len(d["spend_segments"]) == 5

    def test_one_timer(self, headers):
        d = requests.get(f"{BASE_URL}/api/dashboard/cohorts-segmentation", headers=headers, timeout=60).json()
        ot = d["one_timer"]
        for k in ["count", "total_spend", "avg_first_basket", "recency_distribution",
                  "estimated_recovery_pool_inr"]:
            assert k in ot
        rec = ot["recency_distribution"]
        for b in ["0-30d", "31-90d", "91-180d", "180d+"]:
            assert b in rec
        # recovery_pool = total_spend * 0.15
        assert abs(ot["estimated_recovery_pool_inr"] - ot["total_spend"] * 0.15) < 1

    def test_retention_triangle(self, headers):
        d = requests.get(f"{BASE_URL}/api/dashboard/cohorts-segmentation", headers=headers, timeout=60).json()
        rt = d["retention_triangle"]
        assert "cohorts" in rt and "max_offset" in rt and "rows" in rt
        for row in rt["rows"]:
            assert "cohort_month" in row and "offsets" in row
            if row["offsets"]:
                # offset 0 should be 100% (signup month)
                assert row["offsets"][0]["offset"] == 0
                assert row["offsets"][0]["pct"] == 100.0, f"cohort {row['cohort_month']} offset0 != 100% ({row['offsets'][0]['pct']})"


# -------- Points Economics --------
class TestPointsEcon:
    def test_points_schema(self, headers):
        r = requests.get(f"{BASE_URL}/api/dashboard/points-economics?period_days=90", headers=headers, timeout=60)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        for k in ["window", "liability", "breakage_risk", "monthly_flow", "top_redeemers"]:
            assert k in d
        w = d["window"]
        for k in ["earn_points", "burn_points", "burn_to_earn_pct", "earn_inr_equivalent"]:
            assert k in w
        lib = d["liability"]
        for k in ["outstanding_points", "outstanding_inr", "lifetime_earned",
                  "lifetime_redeemed", "redemption_pct"]:
            assert k in lib
        brk = d["breakage_risk"]
        for k in ["stale_180d_customers", "points_at_risk", "inr_at_risk"]:
            assert k in brk
        assert isinstance(d["monthly_flow"], list)
        assert len(d["monthly_flow"]) <= 12


# -------- Campaign ROI --------
class TestCampaignROI:
    def test_campaign_roi_schema(self, headers):
        r = requests.get(f"{BASE_URL}/api/dashboard/campaign-roi", headers=headers, timeout=60)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        for k in ["totals", "funnel", "by_channel", "leaderboard"]:
            assert k in d
        t = d["totals"]
        for k in ["sent", "delivered", "clicked", "converted", "revenue",
                  "cost", "overall_roi_pct", "overall_ctr_pct", "overall_cvr_pct", "campaigns"]:
            assert k in t, f"missing totals.{k}"
        assert len(d["funnel"]) == 5
        stages = [f["stage"] for f in d["funnel"]]
        assert stages == ["Sent", "Delivered", "Opened", "Clicked", "Converted"]
        for f in d["funnel"]:
            assert "pct_of_sent" in f
        # leaderboard sorted by ROI descending (None pushed to end)
        rois = [c["roi_pct"] for c in d["leaderboard"] if c["roi_pct"] is not None]
        assert rois == sorted(rois, reverse=True)


# -------- Executive Summary --------
class TestExecSummary:
    def test_exec_summary_schema(self, headers):
        r = requests.get(f"{BASE_URL}/api/dashboard/executive-summary?period_days=30", headers=headers, timeout=60)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        for k in ["kpis", "top_stores", "top_cities"]:
            assert k in d
        k = d["kpis"]
        for f in ["net_sales", "net_sales_delta_pct", "transactions", "aov", "items_sold",
                  "active_customers", "total_customers", "outstanding_liability_inr"]:
            assert f in k
        assert len(d["top_stores"]) <= 5
        assert len(d["top_cities"]) <= 5

    def test_exec_summary_pdf(self, headers):
        r = requests.get(f"{BASE_URL}/api/dashboard/executive-summary/pdf?period_days=30", headers=headers, timeout=60)
        assert r.status_code == 200, r.text[:200]
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert len(r.content) > 1024, f"PDF too small: {len(r.content)} bytes"
        assert r.content[:4] == b"%PDF", f"Not a valid PDF: {r.content[:10]}"


# -------- Formula Catalog --------
class TestFormulaCatalog:
    def test_formula_catalog(self, headers):
        r = requests.get(f"{BASE_URL}/api/dashboard/formula-catalog", headers=headers, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["total"] == 23, f"expected 23 formulas, got {d['total']}"
        assert len(d["flat"]) == 23
        cats = {c["category"] for c in d["categories"]}
        expected = {"Revenue", "Customer", "RFM", "Cohort", "Loyalty",
                    "Campaign", "Experience", "Operations"}
        assert expected.issubset(cats), f"missing categories: {expected - cats}"
        # each formula has name/description/formula/live_source
        for f in d["flat"]:
            assert "name" in f and "description" in f and "formula" in f and "live_source" in f


# -------- Auth guard --------
class TestAuth:
    def test_no_auth_rejected(self):
        for path in ["/api/dashboard/cohorts-segmentation",
                     "/api/dashboard/points-economics",
                     "/api/dashboard/campaign-roi",
                     "/api/dashboard/executive-summary",
                     "/api/dashboard/executive-summary/pdf",
                     "/api/dashboard/formula-catalog"]:
            r = requests.get(f"{BASE_URL}{path}", timeout=15)
            assert r.status_code in (401, 403), f"{path} returned {r.status_code} for unauthenticated"
