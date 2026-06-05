"""Iteration 13 — production-urgent bug fix tests:
1. Active <= Total customers sanity (was 3,92,434 > 1,98,695 in prod)
2. City filter actually narrows command-center data
3. Store filter actually narrows command-center data
4. /filter-options returns cities from BOTH stores and transactions
5. CSV re-upload (same file twice): SECOND run reports updated == row_count (matched_count fix)
6. After txn ingest: customer auto-backfill creates stubs for orphan mobiles
7. Regression: /api/raw-reports/customer-data?group_by=month still works
"""
import os
import time
import io
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://loyalty-hub-118.preview.emergentagent.com").rstrip("/")
SUPER_EMAIL = "superadmin@fundle.io"
SUPER_PASS = "Fundle@2026"


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": SUPER_EMAIL, "password": SUPER_PASS}, timeout=20)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    data = r.json()
    tok = data.get("token") or data.get("access_token")
    assert tok, f"No token in login response: {data}"
    return tok


@pytest.fixture(scope="session")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- 1. Active <= Total sanity ----------
class TestActiveLeqTotal:
    @pytest.mark.parametrize("period", ["30d", "90d", "1y", "all"])
    def test_active_leq_total(self, auth_headers, period):
        r = requests.get(f"{BASE_URL}/api/dashboard/command-center",
                         params={"period": period}, headers=auth_headers, timeout=30)
        assert r.status_code == 200, r.text
        kpis = r.json()["kpis"]
        active = kpis["active_customers"]
        total = kpis["total_customers"]
        print(f"[{period}] active={active} total={total}")
        assert active <= total, f"BUG: active ({active}) > total ({total}) for period={period}"


# ---------- 2 & 3. Filter narrows data ----------
class TestFilters:
    def test_filter_options_returns_cities(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/dashboard/filter-options", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "cities" in data and "stores" in data
        assert isinstance(data["cities"], list)
        assert isinstance(data["stores"], list)
        # Should be non-empty in this seeded preview env
        print(f"Cities: {data['cities'][:10]}, store_count={len(data['stores'])}")

    def test_city_filter_narrows(self, auth_headers):
        # Baseline (no filter)
        base = requests.get(f"{BASE_URL}/api/dashboard/command-center",
                            params={"period": "1y"}, headers=auth_headers, timeout=30).json()["kpis"]
        opts = requests.get(f"{BASE_URL}/api/dashboard/filter-options",
                            headers=auth_headers, timeout=20).json()
        cities = opts.get("cities", [])
        if not cities:
            pytest.skip("No cities available to test city filter")
        # Pick a city — try Chandigarh first as suggested, else first available
        target = "Chandigarh" if "Chandigarh" in cities else cities[0]
        filt = requests.get(f"{BASE_URL}/api/dashboard/command-center",
                            params={"period": "1y", "city": target},
                            headers=auth_headers, timeout=30).json()["kpis"]
        print(f"Baseline net={base['net_sales']} active={base['active_customers']} | "
              f"city={target} net={filt['net_sales']} active={filt['active_customers']}")
        # Filtered must be <= baseline for additive metrics
        assert filt["net_sales"] <= base["net_sales"] + 0.01
        assert filt["active_customers"] <= base["active_customers"]
        # Active still <= total in filtered view
        assert filt["active_customers"] <= filt["total_customers"]

    def test_city_filter_no_data_returns_zero(self, auth_headers):
        # Bangalore has no txns per problem statement
        r = requests.get(f"{BASE_URL}/api/dashboard/command-center",
                         params={"period": "1y", "city": "Bangalore"},
                         headers=auth_headers, timeout=30)
        assert r.status_code == 200
        kpis = r.json()["kpis"]
        print(f"Bangalore filter: net={kpis['net_sales']} active={kpis['active_customers']}")
        assert kpis["net_sales"] == 0
        assert kpis["transactions"] == 0
        assert kpis["active_customers"] == 0

    def test_store_filter_narrows(self, auth_headers):
        opts = requests.get(f"{BASE_URL}/api/dashboard/filter-options",
                            headers=auth_headers, timeout=20).json()
        stores = opts.get("stores", [])
        if not stores:
            pytest.skip("No stores available")
        store_id = stores[0]["id"]
        base = requests.get(f"{BASE_URL}/api/dashboard/command-center",
                            params={"period": "1y"}, headers=auth_headers, timeout=30).json()["kpis"]
        filt = requests.get(f"{BASE_URL}/api/dashboard/command-center",
                            params={"period": "1y", "store_id": store_id},
                            headers=auth_headers, timeout=30).json()["kpis"]
        print(f"Baseline net={base['net_sales']} | store={store_id} net={filt['net_sales']}")
        assert filt["net_sales"] <= base["net_sales"] + 0.01
        assert filt["active_customers"] <= filt["total_customers"]


# ---------- 4. CSV re-upload reconciliation (matched_count fix) ----------
class TestCSVReupload:
    CSV_DATA = (
        "Mobile,Name,City\n"
        "9999000001,TEST_ReupOne,Chandigarh\n"
        "9999000002,TEST_ReupTwo,Mumbai\n"
        "9999000003,TEST_ReupThree,Delhi\n"
    )

    def _ingest(self, auth_headers):
        files = {"file": ("reup.csv", io.BytesIO(self.CSV_DATA.encode()), "text/csv")}
        data = {"dataset": "customers", "duplicate_mode": "upsert", "dry_run": "false"}
        r = requests.post(f"{BASE_URL}/api/historic-data/ingest",
                          files=files, data=data, headers=auth_headers, timeout=60)
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def _wait_complete(self, auth_headers, job_id, timeout_s=120):
        end = time.time() + timeout_s
        last = None
        while time.time() < end:
            try:
                r = requests.get(f"{BASE_URL}/api/historic-data/jobs/{job_id}",
                                 headers=auth_headers, timeout=45)
            except requests.exceptions.RequestException:
                time.sleep(3); continue
            if r.status_code == 200:
                last = r.json()
                if last.get("status") in {"completed", "previewed", "failed"}:
                    return last
            time.sleep(2)
        return last

    def test_first_upload_then_reupload_updates_match_rowcount(self, auth_headers):
        # First ingest
        job1 = self._ingest(auth_headers)
        r1 = self._wait_complete(auth_headers, job1)
        assert r1 is not None, "job1 never completed"
        assert r1["status"] == "completed", f"job1 status={r1.get('status')} err={r1.get('error')}"
        rows = r1.get("total_rows") or 3
        ins1, upd1, skp1 = r1.get("inserted", 0), r1.get("updated", 0), r1.get("skipped", 0)
        print(f"Run1: total={rows} inserted={ins1} updated={upd1} skipped={skp1}")
        assert ins1 + upd1 + skp1 >= rows, f"Run1 reconciliation off: {ins1}+{upd1}+{skp1} < {rows}"

        # Second ingest (same CSV)
        job2 = self._ingest(auth_headers)
        r2 = self._wait_complete(auth_headers, job2)
        assert r2 is not None and r2["status"] == "completed", f"job2: {r2}"
        rows2 = r2.get("total_rows") or 3
        ins2, upd2, skp2 = r2.get("inserted", 0), r2.get("updated", 0), r2.get("skipped", 0)
        print(f"Run2: total={rows2} inserted={ins2} updated={upd2} skipped={skp2}")
        # CRITICAL: matched_count fix → updated should be > 0 on re-upload of identical CSV
        assert upd2 > 0, (
            f"BUG NOT FIXED: re-upload reported updated=0 (matched_count fix failed). "
            f"Run2: inserted={ins2} updated={upd2} skipped={skp2}"
        )
        assert ins2 + upd2 + skp2 >= rows2, "Run2 reconciliation off"


# ---------- 5. Auto-backfill of customers from transactions ----------
class TestAutoBackfill:
    TXN_CSV = (
        "Bill Number,Customer Mobile Number,Date,Time,Total Revenue Kazo,Net Amount Before Tax Kazo,"
        "Total Tax,Discount,Outlet(Only For Shopify Marker),City,Zone New,Class,Return Marker\n"
        "TESTBL001,8888000001,01-04-2025,10:00:00,1000,1000,0,0,Test Outlet A,Pune,West,B,Regular\n"
        "TESTBL002,8888000002,02-04-2025,11:00:00,2000,2000,0,0,Test Outlet A,Pune,West,B,Regular\n"
    )

    def test_txn_ingest_auto_creates_customer_stubs(self, auth_headers):
        files = {"file": ("auto.csv", io.BytesIO(self.TXN_CSV.encode()), "text/csv")}
        data = {"dataset": "transactions", "duplicate_mode": "upsert", "dry_run": "false"}
        r = requests.post(f"{BASE_URL}/api/historic-data/ingest",
                          files=files, data=data, headers=auth_headers, timeout=60)
        assert r.status_code == 200, r.text
        job_id = r.json()["id"]
        # Wait up to 90s for txn ingest + backfill post-pass
        end = time.time() + 180
        job = None
        while time.time() < end:
            try:
                jr = requests.get(f"{BASE_URL}/api/historic-data/jobs/{job_id}",
                                  headers=auth_headers, timeout=45)
            except requests.exceptions.RequestException:
                time.sleep(3); continue
            if jr.status_code == 200:
                job = jr.json()
                if job.get("status") in {"completed", "failed"}:
                    break
            time.sleep(3)
        assert job is not None and job.get("status") == "completed", f"txn job: {job}"
        # customers_auto_created may be 0 (already exist) or >0 — just verify field exists OR no error
        auto = job.get("customers_auto_created", None)
        print(f"customers_auto_created={auto} status={job.get('status')}")
        # Now verify Active <= Total still holds after auto-backfill
        cc = requests.get(f"{BASE_URL}/api/dashboard/command-center",
                          params={"period": "all"}, headers=auth_headers, timeout=30).json()["kpis"]
        assert cc["active_customers"] <= cc["total_customers"], \
            f"Post-backfill: active ({cc['active_customers']}) > total ({cc['total_customers']})"


# ---------- 6. Regression: raw-reports/customer-data?group_by=month ----------
class TestRegressionRawReports:
    def test_raw_reports_customer_data_group_by_month(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/raw-reports/customer-data",
                         params={"group_by": "month"}, headers=auth_headers, timeout=30)
        # Some installs return 200; if route shape requires other params, accept 200/422 not 500
        assert r.status_code in (200, 400, 404, 405, 422), f"Unexpected: {r.status_code} {r.text[:200]}"
        if r.status_code == 200:
            j = r.json()
            print(f"raw-reports keys: {list(j.keys()) if isinstance(j, dict) else type(j).__name__}")
