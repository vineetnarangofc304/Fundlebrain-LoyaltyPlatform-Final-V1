"""
Iteration 71 — Dashboard optimization, legacy reports pagination,
RECON module, and Fundle Brain AI tests.

Scale: DB seeded ~800K customers / 1.5M txns. Heavy endpoints may take 10-45s first time.
"""
import os
import io
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://fundle-brain-ai-1.preview.emergentagent.com").rstrip("/")
EMAIL = "superadmin@fundle.io"
PASSWORD = "Fundle@2026"

HEAVY_TIMEOUT = 120


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text[:200]}"
    j = r.json()
    tok = j.get("token") or j.get("access_token")
    assert tok, f"no token in response: {j}"
    return tok


@pytest.fixture(scope="session")
def session(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


# ───── login ─────
def test_login_returns_token(token):
    assert isinstance(token, str) and len(token) > 10


# ───── dashboard endpoints ─────
def test_command_center_period_all(session):
    t0 = time.time()
    r = session.get(f"{BASE_URL}/api/dashboard/command-center", params={"period": "all"}, timeout=HEAVY_TIMEOUT)
    elapsed = time.time() - t0
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    j = r.json()
    kpis = j.get("kpis", {})
    print(f"command-center 1st call: {elapsed:.1f}s | net_sales={kpis.get('net_sales')} txns={kpis.get('transactions')} customers={kpis.get('total_customers') or kpis.get('customers')}")
    assert kpis.get("net_sales", 0) > 0, "net_sales should be > 0"
    assert kpis.get("transactions", 0) > 0, "transactions should be > 0"
    # degraded should be an EMPTY list (no failed facets)
    deg = j.get("degraded")
    assert isinstance(deg, list), f"degraded should be a list, got {type(deg)}"
    assert deg == [], f"degraded should be empty, got {deg}"
    sparkline = j.get("sparkline") or kpis.get("sparkline") or j.get("sales_sparkline")
    assert sparkline and len(sparkline) > 0, "sparkline should be non-empty"

    # second call -> cache hit
    t1 = time.time()
    r2 = session.get(f"{BASE_URL}/api/dashboard/command-center", params={"period": "all"}, timeout=HEAVY_TIMEOUT)
    elapsed2 = time.time() - t1
    assert r2.status_code == 200
    print(f"command-center cached call: {elapsed2:.1f}s")
    assert elapsed2 < 5, f"cached call should be <5s, got {elapsed2:.1f}s"


def test_dashboard_kpis_all(session):
    r = session.get(f"{BASE_URL}/api/dashboard/kpis", params={"period": "all"}, timeout=HEAVY_TIMEOUT)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    j = r.json()
    sales = j.get("sales", {})
    customers = j.get("customers", {})
    print(f"kpis: sales.net={sales.get('net')} customers.total={customers.get('total')}")
    # endpoint returns sales.net (not net_sales)
    assert (sales.get("net") or sales.get("net_sales", 0)) > 0
    assert customers.get("total", 0) > 100000, f"expected ~800K customers, got {customers.get('total')}"
    assert "loyalty" in j
    assert "api" in j or "api_health" in j or "nps" in j


def test_sales_trend_monthly(session):
    r = session.get(f"{BASE_URL}/api/dashboard/sales-trend", params={"period": "all"}, timeout=HEAVY_TIMEOUT)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    buckets = r.json()
    assert isinstance(buckets, list) and len(buckets) > 0
    sample = buckets[0]
    print(f"sales-trend(all) sample={sample}")
    date_key = sample.get("date") or sample.get("bucket") or sample.get("month")
    assert date_key and len(date_key) == 7, f"expected YYYY-MM, got {date_key}"
    assert (sample.get("net") or sample.get("net_sales") or 0) > 0
    assert (sample.get("txns") or 0) > 0
    assert (sample.get("customers") or 0) > 0


def test_sales_trend_daily_30d(session):
    r = session.get(f"{BASE_URL}/api/dashboard/sales-trend", params={"period": "30d"}, timeout=HEAVY_TIMEOUT)
    assert r.status_code == 200
    buckets = r.json()
    assert isinstance(buckets, list) and len(buckets) > 0
    sample = buckets[0]
    date_key = sample.get("date") or sample.get("bucket") or sample.get("day")
    assert date_key and len(date_key) == 10, f"expected YYYY-MM-DD, got {date_key}"


def test_city_performance_no_500(session):
    r = session.get(f"{BASE_URL}/api/dashboard/city-performance", params={"period": "all"}, timeout=HEAVY_TIMEOUT)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    cities = r.json()
    assert isinstance(cities, list) and len(cities) > 0
    for c in cities[:20]:
        name = c.get("city") or c.get("name") or ""
        assert name != "", f"empty city name found: {c}"


def test_category_mix_no_empty(session):
    r = session.get(f"{BASE_URL}/api/dashboard/category-mix", params={"period": "all"}, timeout=HEAVY_TIMEOUT)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    cats = r.json()
    assert isinstance(cats, list)
    for c in cats:
        name = c.get("category") or c.get("name") or ""
        assert name != "", f"empty category name found: {c}"


def test_executive_summary(session):
    r = session.get(f"{BASE_URL}/api/dashboard/executive-summary", params={"period_days": 0}, timeout=HEAVY_TIMEOUT)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    j = r.json()
    kpis = j.get("kpis") or {}
    print(f"exec-summary: net_sales={kpis.get('net_sales')} active={kpis.get('active_customers')} total={kpis.get('total_customers')}")
    assert (kpis.get("net_sales") or 0) > 0
    assert (kpis.get("active_customers") or 0) <= (kpis.get("total_customers") or 0)
    assert isinstance(j.get("top_stores"), list) and len(j["top_stores"]) > 0
    assert isinstance(j.get("top_cities"), list) and len(j["top_cities"]) > 0


def test_store_performance_v2(session):
    r = session.get(f"{BASE_URL}/api/dashboard/store-performance-v2", params={"period_days": 0}, timeout=HEAVY_TIMEOUT)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    j = r.json()
    lb = j.get("leaderboard") or []
    assert isinstance(lb, list) and len(lb) > 0
    assert any((s.get("visitors") or s.get("customers") or 0) > 0 for s in lb)
    assert isinstance(j.get("by_city"), list)
    assert isinstance(j.get("by_day"), list)
    heatmap = j.get("heatmap") or []
    assert len(heatmap) == 168, f"heatmap should be 168 cells, got {len(heatmap)}"


def test_rfm_all_customers(session):
    r = session.get(f"{BASE_URL}/api/dashboard/rfm", params={"period_days": 0}, timeout=HEAVY_TIMEOUT)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    j = r.json()
    total = j.get("total_customers") or j.get("total") or 0
    print(f"rfm total_customers={total}")
    assert total > 500000, f"expected ~800K customers, got {total} (was capped at 100K bug)"
    heatmap = j.get("heatmap") or []
    assert len(heatmap) == 25, f"rfm heatmap should be 25 cells, got {len(heatmap)}"
    segments = j.get("segments") or []
    assert isinstance(segments, list) and len(segments) > 0
    # at least one segment should have examples
    assert any(isinstance(s.get("examples"), list) for s in segments)


def test_cohorts_segmentation(session):
    r = session.get(f"{BASE_URL}/api/dashboard/cohorts-segmentation", params={"period_days": 0}, timeout=HEAVY_TIMEOUT)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    j = r.json()
    freq = j.get("frequency_segments") or j.get("frequency_bands") or []
    spend = j.get("spend_segments") or j.get("spend_bands") or []
    assert isinstance(freq, list) and len(freq) > 0
    assert isinstance(spend, list) and len(spend) > 0
    # at least one freq segment should have examples
    assert any(isinstance(s.get("examples"), list) and s["examples"] for s in freq)
    rt = j.get("retention_triangle")
    assert rt and (isinstance(rt, list) or (isinstance(rt, dict) and rt.get("rows")))
    assert j.get("one_timer") or j.get("one_timers"), "one_timer block missing"


def test_points_economics(session):
    t0 = time.time()
    r = session.get(f"{BASE_URL}/api/dashboard/points-economics", params={"period_days": 0}, timeout=HEAVY_TIMEOUT)
    elapsed = time.time() - t0
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    j = r.json()
    print(f"points-economics 1st: {elapsed:.1f}s")
    assert j.get("window") or j.get("liability") or j.get("monthly_flow")
    assert isinstance(j.get("monthly_flow"), list)
    assert isinstance(j.get("top_redeemers"), list)


# ───── analytics ─────
@pytest.mark.parametrize("endpoint", [
    "sales-dashboard",
    "customer-dashboard",
    "loyalty-dashboard",
    "store-dashboard",
])
def test_analytics_dashboards(session, endpoint):
    r = session.get(f"{BASE_URL}/api/analytics/{endpoint}", params={"period_days": 0}, timeout=HEAVY_TIMEOUT)
    assert r.status_code == 200, f"{endpoint}: {r.status_code} {r.text[:300]}"
    j = r.json()
    assert j and (isinstance(j, dict) and len(j) > 0)
    if endpoint == "store-dashboard":
        stores = j.get("stores") or []
        regions = j.get("regions") or []
        assert isinstance(stores, list) and len(stores) > 0
        assert any((s.get("visitors") or 0) > 0 for s in stores)
        assert isinstance(regions, list)


# ───── legacy reports ─────
LEGACY_REPORTS = [
    "customer-data", "transaction-data", "repeat-customers", "top-customers",
    "fraud-report", "pending-bills", "feedback-data", "missed-calls",
    "location-wise-customers", "expiry-points", "active-coupons",
]


@pytest.mark.parametrize("report", LEGACY_REPORTS)
def test_legacy_report(session, report):
    params = {"limit": 10, "offset": 0} if report in ("customer-data", "transaction-data") else {}
    r = session.get(f"{BASE_URL}/api/legacy-reports/{report}", params=params, timeout=HEAVY_TIMEOUT)
    assert r.status_code == 200, f"{report}: {r.status_code} {r.text[:300]}"
    j = r.json()
    if report in ("customer-data", "transaction-data"):
        rows = j.get("rows") or j.get("data") or []
        total = j.get("total")
        assert total is not None, f"{report} missing total"
        assert isinstance(rows, list)
        assert len(rows) <= 10, f"{report} returned {len(rows)} rows, expected <=10"


# ───── raw reports ─────
def test_raw_repeat_purchases(session):
    t0 = time.time()
    r = session.post(f"{BASE_URL}/api/raw-reports/repeat-purchases", json={"page": 1, "page_size": 10}, timeout=HEAVY_TIMEOUT)
    elapsed = time.time() - t0
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    assert elapsed < 90, f"repeat-purchases took {elapsed:.1f}s"
    j = r.json()
    rows = j.get("rows") or j.get("data") or []
    assert isinstance(rows, list) and len(rows) > 0
    sample = rows[0]
    keys = " ".join(sample.keys()).lower()
    assert "purchase" in keys and "repeat" in keys, f"missing purchase_/repeat_ fields: {list(sample.keys())}"
    # sanity: repeat_total_bills < purchase_total_bills
    p_bills = sample.get("purchase_total_bills") or sample.get("purchase_bills") or 0
    r_bills = sample.get("repeat_total_bills") or sample.get("repeat_bills") or 0
    if p_bills and r_bills:
        assert r_bills <= p_bills, f"repeat>purchase: r={r_bills} p={p_bills}"


def test_raw_customers_by_visit(session):
    r = session.post(f"{BASE_URL}/api/raw-reports/customers-by-visit", json={"page": 1, "page_size": 10}, timeout=HEAVY_TIMEOUT)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"


def test_raw_drill_customers_by_visit(session):
    body = {"report": "customers_by_visit", "visits": 1, "page": 1, "page_size": 10}
    r = session.post(f"{BASE_URL}/api/raw-reports/drill", json=body, timeout=HEAVY_TIMEOUT)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"


# ───── RECON module ─────
def test_recon_full_flow(session):
    # 1) init
    init_body = {"dataset": "transactions", "filename": "t.csv", "total_chunks": 1, "total_bytes": 200}
    r = session.post(f"{BASE_URL}/api/recon/init", json=init_body, timeout=30)
    assert r.status_code == 200, f"recon init: {r.status_code} {r.text[:300]}"
    job_id = r.json().get("id") or r.json().get("job_id")
    assert job_id

    # find a real bill number from DB (perf_seed format PERF-00000000)
    real_bill = "PERF-00000000"
    csv = (
        "Bill Number,Date,Net Amount,Customer Mobile Number\n"
        f"{real_bill},2023-07-23,5298.45,9000760964\n"
        "FAKE-X,2025-01-01,100,9111111111\n"
    )

    # 2) chunk upload (multipart)
    files = {"chunk": ("chunk0.csv", io.BytesIO(csv.encode()), "text/csv")}
    data = {"job_id": job_id, "chunk_index": "0"}
    s2 = requests.Session()
    s2.headers.update({"Authorization": session.headers["Authorization"]})
    r = s2.post(f"{BASE_URL}/api/recon/chunk", data=data, files=files, timeout=60)
    assert r.status_code == 200, f"recon chunk: {r.status_code} {r.text[:300]}"

    # 3) finalize
    r = session.post(f"{BASE_URL}/api/recon/finalize", json={"job_id": job_id}, timeout=30)
    assert r.status_code == 200, f"recon finalize: {r.status_code} {r.text[:300]}"

    # 4) poll
    deadline = time.time() + 180
    status = None
    while time.time() < deadline:
        r = session.get(f"{BASE_URL}/api/recon/jobs/{job_id}", timeout=30)
        assert r.status_code == 200, f"recon poll: {r.status_code} {r.text[:300]}"
        j = r.json()
        status = j.get("status")
        if status in ("done", "failed", "error", "completed"):
            break
        time.sleep(3)
    assert status in ("done", "completed"), f"recon job final status={status}"
    report = j.get("report") or j.get("summary") or {}
    matched = report.get("matched", 0)
    missing = report.get("missing_in_db", 0)
    print(f"recon report: matched={matched} missing={missing}")
    assert matched >= 1 and missing >= 1

    # 5) mismatches CSV
    r = session.get(f"{BASE_URL}/api/recon/jobs/{job_id}/mismatches.csv", timeout=30)
    assert r.status_code == 200
    assert "FAKE-X" in r.text or "Bill" in r.text


# ───── AI Fundle Brain ─────
def test_ai_run_aggregation(session):
    body = {"message": "Use run_aggregation to count transactions by city, top 3"}
    t0 = time.time()
    r = session.post(f"{BASE_URL}/api/ai/chat", json=body, timeout=180)
    elapsed = time.time() - t0
    assert r.status_code == 200, f"ai chat: {r.status_code} {r.text[:300]}"
    j = r.json()
    reply = (j.get("reply") or j.get("message") or "").lower()
    tools = j.get("tools_used") or j.get("tools") or []
    print(f"ai elapsed={elapsed:.1f}s tools={tools}")
    assert reply, "empty reply"
    if isinstance(tools, list):
        tool_names = " ".join(str(t) for t in tools).lower()
        assert "run_aggregation" in tool_names or "aggregation" in tool_names or "aggregate" in reply
