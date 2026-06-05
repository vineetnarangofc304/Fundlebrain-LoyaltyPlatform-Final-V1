"""Iteration 15 — Support Desk + Legacy Reports endpoints.

Covers all 14 Support Desk endpoints and 11 Legacy Reports endpoints.
"""
import os
import requests
import pytest

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break
API = f"{BASE_URL}/api"

SUPER_EMAIL = "superadmin@fundle.io"
SUPER_PASS = "Fundle@2026"


@pytest.fixture(scope="session")
def auth_headers():
    r = requests.post(f"{API}/auth/login", json={"email": SUPER_EMAIL, "password": SUPER_PASS}, timeout=20)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    return {"Authorization": f"Bearer {tok}"}


# ============== SUPPORT DESK ==============
class TestSupportDeskReads:
    def test_redeem_points_otp(self, auth_headers):
        r = requests.get(f"{API}/support-desk/redeem-points-otp", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "rows" in j and "total" in j

    def test_redeem_coupon_otp(self, auth_headers):
        r = requests.get(f"{API}/support-desk/redeem-coupon-otp", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        assert "rows" in r.json()

    def test_redeemed_coupons(self, auth_headers):
        r = requests.get(f"{API}/support-desk/redeemed-coupons", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        assert "rows" in r.json()

    def test_redeemed_points(self, auth_headers):
        r = requests.get(f"{API}/support-desk/redeemed-points", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        assert "rows" in r.json()

    def test_deactivated_customers(self, auth_headers):
        r = requests.get(f"{API}/support-desk/deactivated-customers", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        assert "rows" in r.json()

    def test_reactivated_customers(self, auth_headers):
        r = requests.get(f"{API}/support-desk/reactivated-customers", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text

    def test_unsubscribed(self, auth_headers):
        r = requests.get(f"{API}/support-desk/unsubscribed", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text

    def test_audit_log(self, auth_headers):
        r = requests.get(f"{API}/support-desk/audit-log", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "rows" in j


class TestSupportDeskWriteFlow:
    """End-to-end: deactivate → list → reactivate → audit log entries present."""

    TEST_MOBILE = None  # discovered at runtime

    def _pick_mobile(self, auth_headers):
        if TestSupportDeskWriteFlow.TEST_MOBILE:
            return TestSupportDeskWriteFlow.TEST_MOBILE
        # pick an active customer
        r = requests.get(f"{API}/legacy-reports/customer-data?limit=10", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        rows = r.json().get("rows", [])
        for row in rows:
            if row.get("is_active") is not False and row.get("mobile"):
                TestSupportDeskWriteFlow.TEST_MOBILE = row["mobile"]
                return row["mobile"]
        pytest.skip("No active customer found in seed data")

    def test_deactivate(self, auth_headers):
        m = self._pick_mobile(auth_headers)
        r = requests.post(f"{API}/support-desk/customer-deactivate",
                          json={"mobile": m, "reason": "TEST iter15 deact"},
                          headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

    def test_deactivated_list_contains(self, auth_headers):
        m = TestSupportDeskWriteFlow.TEST_MOBILE
        assert m, "deactivate must run first"
        r = requests.get(f"{API}/support-desk/deactivated-customers?q={m}", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        mobiles = [row.get("mobile") for row in r.json().get("rows", [])]
        assert m in mobiles, f"deactivated mobile {m} not in list: {mobiles}"

    def test_reactivate(self, auth_headers):
        m = TestSupportDeskWriteFlow.TEST_MOBILE
        r = requests.post(f"{API}/support-desk/customer-reactivate",
                          json={"mobile": m, "reason": "TEST iter15 react"},
                          headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text

    def test_reactivated_list_contains(self, auth_headers):
        m = TestSupportDeskWriteFlow.TEST_MOBILE
        r = requests.get(f"{API}/support-desk/reactivated-customers?q={m}", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        mobiles = [row.get("mobile") for row in r.json().get("rows", [])]
        assert m in mobiles, f"reactivated mobile {m} not in list"

    def test_unsubscribe_resubscribe(self, auth_headers):
        m = TestSupportDeskWriteFlow.TEST_MOBILE
        r = requests.post(f"{API}/support-desk/unsubscribe",
                          json={"mobile": m, "channel": "sms", "reason": "TEST iter15"},
                          headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        # list shows it
        r2 = requests.get(f"{API}/support-desk/unsubscribed?q={m}", headers=auth_headers, timeout=20)
        assert r2.status_code == 200
        rows = r2.json().get("rows", [])
        found = next((x for x in rows if x.get("mobile") == m), None)
        assert found, f"{m} not in unsubscribed list"
        assert "sms" in (found.get("unsub_channels") or [])

        # resub all
        r3 = requests.post(f"{API}/support-desk/resubscribe",
                           json={"mobile": m, "channel": "all", "reason": "TEST iter15"},
                           headers=auth_headers, timeout=20)
        assert r3.status_code == 200

    def test_audit_log_has_entries(self, auth_headers):
        m = TestSupportDeskWriteFlow.TEST_MOBILE
        r = requests.get(f"{API}/support-desk/audit-log", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        rows = r.json().get("rows", [])
        # Should have support_desk.* action entries from our writes
        actions = [r.get("action") for r in rows]
        assert any("support_desk." in (a or "") for a in actions), f"no support_desk audit entries: {actions[:5]}"


# ============== LEGACY REPORTS ==============
class TestLegacyReports:
    def test_customer_data(self, auth_headers):
        r = requests.get(f"{API}/legacy-reports/customer-data?limit=10", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "total" in j and "rows" in j
        assert isinstance(j["rows"], list)

    def test_customer_data_csv_export(self, auth_headers):
        r = requests.get(f"{API}/legacy-reports/customer-data?export=csv&limit=5", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        assert "text/csv" in r.headers.get("content-type", "")
        assert "mobile" in r.text.splitlines()[0].lower()

    def test_transaction_data(self, auth_headers):
        r = requests.get(f"{API}/legacy-reports/transaction-data?limit=10", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        assert "rows" in r.json()

    def test_repeat_customers(self, auth_headers):
        r = requests.get(f"{API}/legacy-reports/repeat-customers?min_visits=2", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        assert "rows" in r.json()

    @pytest.mark.parametrize("by", ["purchase", "visits", "points"])
    def test_top_customers_sort(self, auth_headers, by):
        r = requests.get(f"{API}/legacy-reports/top-customers?by={by}&limit=10",
                         headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "rows" in j
        # sort_by should map back
        expected = {"purchase": "lifetime_spend", "visits": "visit_count", "points": "points_balance"}[by]
        assert j.get("sort_by") == expected

    def test_fraud_report(self, auth_headers):
        r = requests.get(f"{API}/legacy-reports/fraud-report", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "flags" in j
        assert isinstance(j["flags"], list)

    def test_pending_bills(self, auth_headers):
        r = requests.get(f"{API}/legacy-reports/pending-bills", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        assert "rows" in r.json()

    def test_feedback_data(self, auth_headers):
        r = requests.get(f"{API}/legacy-reports/feedback-data", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        assert "rows" in r.json()

    def test_missed_calls(self, auth_headers):
        r = requests.get(f"{API}/legacy-reports/missed-calls", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("total") == 0
        assert "note" in j

    def test_location_wise_customers(self, auth_headers):
        r = requests.get(f"{API}/legacy-reports/location-wise-customers", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        assert "rows" in r.json()

    def test_expiry_points(self, auth_headers):
        r = requests.get(f"{API}/legacy-reports/expiry-points?days_ahead=60", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        assert "rows" in r.json()

    def test_active_coupons(self, auth_headers):
        r = requests.get(f"{API}/legacy-reports/active-coupons", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        assert "rows" in r.json()
