"""Iteration 107 - Store KPI loyalty_sales identity + CRM derive Home/First/Last visit + diagnostics + dashboard consistency."""
import os
import io
import csv
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

CRM_EMAIL = "superadmin@fundle.io"
CRM_PASS = "Fundle@2026"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    # Try admin login endpoints
    for path in ("/admin/login", "/auth/login", "/crm/login"):
        try:
            r = s.post(f"{API}{path}", json={"email": CRM_EMAIL, "password": CRM_PASS}, timeout=15)
            if r.status_code == 200:
                try:
                    tok = r.json().get("access_token") or r.json().get("token")
                    if tok:
                        s.headers["Authorization"] = f"Bearer {tok}"
                except Exception:
                    pass
                return s
        except Exception:
            continue
    return s


def _approx(a, b, tol=0.02):
    return abs(float(a) - float(b)) <= tol


class TestStoreKPILoyalty:
    def test_store_kpi_loyalty_identity(self, session):
        r = session.get(f"{API}/kpi-reports/store-kpi", params={"period": "all"}, timeout=60)
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:400]}"
        data = r.json()
        totals = data.get("totals") or {}
        assert "loyalty_sales" in totals, f"loyalty_sales missing in totals: {list(totals.keys())}"
        nv = float(totals.get("new_value", 0))
        rv = float(totals.get("repeat_value", 0))
        ls = float(totals.get("loyalty_sales", 0))
        um = float(totals.get("unmapped_value", 0))
        ret = float(totals.get("return_value", 0))
        ov = float(totals.get("overall_sales", 0))
        assert _approx(nv + rv, ls), f"new+repeat({nv+rv}) != loyalty_sales({ls})"
        assert _approx(ls + um + ret, ov), f"loyalty+unmapped+returns({ls+um+ret}) != overall({ov})"
        # per row check
        rows = data.get("rows") or data.get("data") or []
        for row in rows[:20]:
            if "loyalty_sales" in row:
                assert _approx(float(row.get("new_value", 0)) + float(row.get("repeat_value", 0)),
                               float(row.get("loyalty_sales", 0))), f"row mismatch: {row}"


class TestCRMCustomerDerive:
    def test_crm_customer_home_store_derived(self, session):
        r = session.get(f"{API}/kpi-reports/crm-customers", params={"q": "6000013876", "limit": 5}, timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        j = r.json()
        rows = j.get("rows") or j.get("data") or j.get("items") or []
        assert rows, f"no rows for 6000013876: {j}"
        cust = None
        for row in rows:
            if str(row.get("mobile") or row.get("customer_mobile") or "").endswith("6000013876"):
                cust = row
                break
        cust = cust or rows[0]
        home = (cust.get("home_store") or cust.get("home_store_code") or cust.get("home_store_id") or "")
        assert home, f"home_store empty: {cust}"
        # registered_account 'K00078@KAZO.com' => expect K00078
        assert "K00078" in str(home), f"expected K00078 in home_store, got {home}. cust={cust}"
        assert cust.get("first_purchase_at") or cust.get("first_visit_at") or cust.get("first_visit_date"), f"no first visit: {cust}"
        assert cust.get("last_visit_at") or cust.get("last_visit_date"), f"no last visit: {cust}"

    def test_crm_customer_export_csv(self, session):
        r = session.get(f"{API}/kpi-reports/crm-customers/export", params={"q": "6000013876"}, timeout=90, stream=True)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        content = r.content.decode("utf-8", errors="replace")
        # header check
        first_line = content.split("\n", 1)[0]
        for col in ("Home Store", "First Visit Date", "Last Visit Date"):
            assert col in first_line, f"col {col!r} missing in header: {first_line}"
        # data rows populated
        rdr = list(csv.DictReader(io.StringIO(content)))
        target = [r for r in rdr if "6000013876" in (r.get("Mobile") or r.get("mobile") or "")]
        assert target, f"no data row for 6000013876 in export (rows={len(rdr)})"
        row = target[0]
        assert (row.get("Home Store") or "").strip(), f"Home Store empty: {row}"


class TestDiagnostics:
    def test_diagnostics_shape(self, session):
        r = session.get(f"{API}/kpi-reports/_diagnostics", timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        d = r.json()
        txn = d.get("transactions") or {}
        cust = d.get("customers") or {}
        assert "by_year" in txn, f"transactions.by_year missing: {d}"
        assert "missing_home_store_id" in cust
        assert "missing_first_purchase_at" in cust
        assert "point2_dob_or_doa_equals_visit_or_each_other" in d or "point2_dob_or_doa_equals_visit_or_each_other" in cust, f"point2 field missing: {d}"


class TestDashboardConsistency:
    def test_dashboard_matches_store_kpi(self, session):
        r1 = session.get(f"{API}/dashboard/kpis", params={"period": "all"}, timeout=60)
        r2 = session.get(f"{API}/kpi-reports/store-kpi", params={"period": "all"}, timeout=60)
        assert r1.status_code == 200, f"dashboard {r1.status_code} {r1.text[:300]}"
        assert r2.status_code == 200
        sales = (r1.json().get("sales") or {})
        net = float(sales.get("net", 0))
        loyalty = float((r2.json().get("totals") or {}).get("loyalty_sales", 0))
        assert _approx(net, loyalty, tol=0.05), f"dashboard.sales.net({net}) != store-kpi.loyalty_sales({loyalty})"
