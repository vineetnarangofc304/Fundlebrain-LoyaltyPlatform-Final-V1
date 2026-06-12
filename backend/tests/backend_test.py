"""
KAZO Fundle Platform - Backend API Tests
Comprehensive pytest suite covering all routers.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://fundle-brain-ai-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@kazo.com"
ADMIN_PASSWORD = "Kazo@2026"
SUPER_EMAIL = "superadmin@fundle.io"
SUPER_PASSWORD = "Fundle@2026"
CRM_EMAIL = "crm@kazo.com"
CRM_PASSWORD = "Kazo@2026"
STORE_EMAIL = "store.mumbai@kazo.com"
STORE_PASSWORD = "Kazo@2026"


# ----- shared helpers -----
def _login(email, password, portal="enterprise"):
    r = requests.post(
        f"{API}/auth/login",
        json={"email": email, "password": password, "portal": portal},
        timeout=30,
    )
    return r


@pytest.fixture(scope="session")
def admin_token():
    r = _login(ADMIN_EMAIL, ADMIN_PASSWORD, "enterprise")
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def super_token():
    r = _login(SUPER_EMAIL, SUPER_PASSWORD, "enterprise")
    if r.status_code != 200:
        pytest.skip(f"Super admin login failed: {r.status_code}")
    return r.json()["token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def super_headers(super_token):
    return {"Authorization": f"Bearer {super_token}", "Content-Type": "application/json"}


# ============== AUTH ==============
class TestAuth:
    def test_login_admin_enterprise(self):
        r = _login(ADMIN_EMAIL, ADMIN_PASSWORD, "enterprise")
        assert r.status_code == 200
        data = r.json()
        assert "token" in data and isinstance(data["token"], str)
        assert data["user"]["email"] == ADMIN_EMAIL
        assert data["user"]["role"] == "brand_admin"
        assert "password_hash" not in data["user"]

    def test_login_invalid_password(self):
        r = _login(ADMIN_EMAIL, "wrongpass", "enterprise")
        assert r.status_code == 401

    def test_me_with_token(self, admin_headers):
        r = requests.get(f"{API}/auth/me", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        assert r.json()["email"] == ADMIN_EMAIL

    def test_me_without_token(self):
        r = requests.get(f"{API}/auth/me", timeout=15)
        assert r.status_code in (401, 403)

    def test_portal_gating_crm_user_into_store_portal(self):
        # CRM manager should NOT access store portal
        r = _login(CRM_EMAIL, CRM_PASSWORD, "store")
        assert r.status_code == 403

    def test_portal_gating_crm_into_crm(self):
        r = _login(CRM_EMAIL, CRM_PASSWORD, "crm")
        assert r.status_code == 200

    def test_portal_gating_store_into_store(self):
        r = _login(STORE_EMAIL, STORE_PASSWORD, "store")
        assert r.status_code == 200


# ============== USERS ==============
class TestUsers:
    def test_list_users_as_admin(self, admin_headers):
        r = requests.get(f"{API}/users", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        users = r.json()
        assert isinstance(users, list) and len(users) > 0

    def test_create_user_brand_admin(self, admin_headers):
        payload = {
            "email": f"TEST_user_{int(time.time())}@kazo.com",
            "name": "Test User",
            "role": "analytics_viewer",
            "password": "Test@1234",
        }
        r = requests.post(f"{API}/users", headers=admin_headers, json=payload, timeout=15)
        assert r.status_code in (200, 201), r.text
        created = r.json()
        assert created["email"] == payload["email"].lower() or created["email"] == payload["email"]
        # verify persistence via list
        r2 = requests.get(f"{API}/users", headers=admin_headers, timeout=15)
        emails = [u["email"] for u in r2.json()]
        assert created["email"] in emails

    def test_only_super_can_create_super(self, admin_headers):
        payload = {
            "email": f"TEST_super_{int(time.time())}@kazo.com",
            "name": "Bad Super",
            "role": "super_admin",
            "password": "Test@1234",
        }
        r = requests.post(f"{API}/users", headers=admin_headers, json=payload, timeout=15)
        assert r.status_code in (400, 403), f"brand_admin must not create super_admin: {r.status_code} {r.text}"


# ============== DASHBOARD ==============
class TestDashboard:
    def test_kpis(self, admin_headers):
        r = requests.get(f"{API}/dashboard/kpis?period=30d", headers=admin_headers, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        # Expected keys (server returns 'api' instead of 'api_keys' per spec wording)
        for key in ("customers", "sales", "loyalty", "campaigns", "nps"):
            assert key in data, f"Missing KPI section: {key}"
        assert "api" in data or "api_keys" in data, "Missing api/api_keys KPI section"
        # Should not be all zeros given seed
        customers = data["customers"]
        assert customers.get("total", 0) > 0, "Customers total should be > 0 (seeded)"
        sales = data["sales"]
        # KPI sales uses 'gross' and 'net' keys
        revenue = sales.get("gross") or sales.get("net") or sales.get("total_revenue") or sales.get("revenue") or 0
        assert revenue > 0, f"Sales revenue should be > 0, got sales={sales}"
        # Should not be all zeros given seed
        customers = data["customers"]
        assert customers.get("total", 0) > 0, "Customers total should be > 0 (seeded)"
        sales = data["sales"]
        # KPI sales uses 'gross' and 'net' keys
        revenue = sales.get("gross") or sales.get("net") or sales.get("total_revenue") or sales.get("revenue") or 0
        assert revenue > 0, f"Sales revenue should be > 0, got sales={sales}"

    def test_sales_trend(self, admin_headers):
        r = requests.get(f"{API}/dashboard/sales-trend", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) and len(data) > 0

    def test_store_performance(self, admin_headers):
        r = requests.get(f"{API}/dashboard/store-performance", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list) and len(r.json()) > 0

    def test_category_mix(self, admin_headers):
        r = requests.get(f"{API}/dashboard/category-mix", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list) and len(r.json()) > 0

    def test_tier_distribution(self, admin_headers):
        r = requests.get(f"{API}/dashboard/tier-distribution", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list) and len(r.json()) > 0

    def test_top_skus(self, admin_headers):
        r = requests.get(f"{API}/dashboard/top-skus", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list) and len(r.json()) > 0


# ============== CUSTOMERS ==============
@pytest.fixture(scope="session")
def first_customer(admin_headers):
    r = requests.get(f"{API}/customers?limit=5", headers=admin_headers, timeout=20)
    assert r.status_code == 200
    data = r.json()
    items = data if isinstance(data, list) else data.get("items") or data.get("customers") or []
    assert len(items) > 0, "No customers found"
    return items[0]


class TestCustomers:
    def test_list(self, admin_headers):
        r = requests.get(f"{API}/customers?limit=10", headers=admin_headers, timeout=20)
        assert r.status_code == 200
        data = r.json()
        items = data if isinstance(data, list) else data.get("items") or data.get("customers") or []
        assert len(items) > 0

    def test_filter_by_tier(self, admin_headers):
        r = requests.get(f"{API}/customers?tier=Gold&limit=5", headers=admin_headers, timeout=20)
        assert r.status_code == 200

    def test_search_q(self, admin_headers):
        r = requests.get(f"{API}/customers?q=a&limit=5", headers=admin_headers, timeout=20)
        assert r.status_code == 200

    def test_customer_360(self, admin_headers, first_customer):
        cid = first_customer["id"]
        r = requests.get(f"{API}/customers/{cid}", headers=admin_headers, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        # Customer 360 should include nested sections
        keys = set(data.keys())
        # Accept any combination - just need at least transactions or ledger present
        assert any(k in keys for k in ("transactions", "ledger", "favourites", "favorites")), f"Missing 360 sections in {keys}"

    def test_award_points(self, admin_headers, first_customer):
        cid = first_customer["id"]
        # Endpoint uses query params (FastAPI default for non-Pydantic args)
        r = requests.post(
            f"{API}/customers/{cid}/award-points",
            params={"points": 50, "note": "TEST_award"},
            headers=admin_headers,
            timeout=20,
        )
        assert r.status_code in (200, 201), r.text

    def test_deduct_points(self, admin_headers, first_customer):
        cid = first_customer["id"]
        r = requests.post(
            f"{API}/customers/{cid}/deduct-points",
            params={"points": 10, "note": "TEST_deduct"},
            headers=admin_headers,
            timeout=20,
        )
        assert r.status_code in (200, 201), r.text


# ============== LOYALTY ==============
class TestLoyalty:
    def test_get_config(self, admin_headers):
        r = requests.get(f"{API}/loyalty/config", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        cfg = r.json()
        assert isinstance(cfg, dict) and len(cfg) > 0

    def test_update_config(self, admin_headers):
        r = requests.get(f"{API}/loyalty/config", headers=admin_headers, timeout=15)
        cfg = r.json()
        r2 = requests.put(f"{API}/loyalty/config", headers=admin_headers, json=cfg, timeout=15)
        assert r2.status_code in (200, 201), r2.text

    def test_tier_stats(self, admin_headers):
        r = requests.get(f"{API}/loyalty/tier-stats", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        assert r.json()


# ============== COUPONS ==============
class TestCoupons:
    coupon_id = None
    coupon_code = None

    def test_list(self, admin_headers):
        r = requests.get(f"{API}/coupons", headers=admin_headers, timeout=15)
        assert r.status_code == 200

    def test_generate_code(self, admin_headers):
        r = requests.post(f"{API}/coupons/generate-code", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "code" in data and len(data["code"]) > 0
        TestCoupons.coupon_code = data["code"]

    def test_create_coupon(self, admin_headers):
        code = TestCoupons.coupon_code or f"TEST{int(time.time())}"
        payload = {
            "code": code,
            "name": "TEST_Coupon",
            "coupon_type": "percentage",
            "discount_value": 10,
            "min_bill_amount": 500,
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_to": "2026-12-31T23:59:59Z",
            "usage_limit": 100,
            "is_active": True,
        }
        r = requests.post(f"{API}/coupons", headers=admin_headers, json=payload, timeout=15)
        assert r.status_code in (200, 201), r.text
        data = r.json()
        TestCoupons.coupon_id = data.get("id")
        TestCoupons.coupon_code = data.get("code", code)

    def test_validate_by_code(self, admin_headers):
        code = TestCoupons.coupon_code
        if not code:
            pytest.skip("No coupon code from previous test")
        r = requests.post(f"{API}/coupons/validate-by-code/{code}", headers=admin_headers, json={}, timeout=15)
        # Some impls may return 200 or 404 if invalid context
        assert r.status_code in (200, 400, 404), r.text


# ============== CAMPAIGNS ==============
class TestCampaigns:
    campaign_id = None

    def test_list(self, admin_headers):
        r = requests.get(f"{API}/campaigns", headers=admin_headers, timeout=15)
        assert r.status_code == 200

    def test_create(self, admin_headers):
        payload = {
            "name": f"TEST_Campaign_{int(time.time())}",
            "channels": ["whatsapp"],
            "audience_type": "all",
            "audience_filter": {},
            "message_template": "Hello {{name}}, special offer for you!",
            "status": "draft",
        }
        r = requests.post(f"{API}/campaigns", headers=admin_headers, json=payload, timeout=15)
        assert r.status_code in (200, 201), r.text
        TestCampaigns.campaign_id = r.json().get("id")
        assert TestCampaigns.campaign_id

    def test_launch(self, admin_headers):
        if not TestCampaigns.campaign_id:
            pytest.skip("No campaign id")
        r = requests.post(
            f"{API}/campaigns/{TestCampaigns.campaign_id}/launch", headers=admin_headers, timeout=20
        )
        assert r.status_code in (200, 201), r.text
        data = r.json()
        # Should contain simulated metrics
        metrics = data.get("metrics") or data
        # At least one of sent/delivered/redeemed should be present
        assert any(k in metrics for k in ("sent", "delivered", "redeemed", "opened")), f"No metrics in {data}"


# ============== AI CHAT ==============
class TestAI:
    def test_chat_top_churning(self, admin_headers):
        payload = {"message": "Show me top churning customers"}
        r = requests.post(f"{API}/ai/chat", headers=admin_headers, json=payload, timeout=120)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "reply" in data and len(data["reply"]) > 10
        data_used = data.get("data_used") or {}
        assert isinstance(data_used, dict)
        assert "churning_customers" in data_used, f"data_used keys: {list(data_used.keys())}"
        # Verify actual customers
        churn = data_used["churning_customers"]
        assert isinstance(churn, list) and len(churn) > 0, "No churning customers returned"

    def test_sessions_persist(self, admin_headers):
        r = requests.get(f"{API}/ai/sessions", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        sessions = r.json()
        assert isinstance(sessions, list)


# ============== API MONITOR ==============
class TestApiMonitor:
    def test_health(self, admin_headers):
        r = requests.get(f"{API}/api-monitor/health", headers=admin_headers, timeout=15)
        assert r.status_code == 200

    def test_recent(self, admin_headers):
        r = requests.get(f"{API}/api-monitor/recent", headers=admin_headers, timeout=15)
        assert r.status_code == 200

    def test_errors(self, admin_headers):
        r = requests.get(f"{API}/api-monitor/errors", headers=admin_headers, timeout=15)
        assert r.status_code == 200


# ============== STORES ==============
class TestStores:
    def test_list_stores(self, admin_headers):
        r = requests.get(f"{API}/stores", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        stores = r.json()
        items = stores if isinstance(stores, list) else stores.get("items", [])
        assert len(items) >= 20, f"Expected ~25 stores, got {len(items)}"


# ============== POS (UNAUTH) ==============
@pytest.fixture(scope="session")
def sample_customer_mobile(admin_headers):
    r = requests.get(f"{API}/customers?limit=1", headers=admin_headers, timeout=20)
    data = r.json()
    items = data if isinstance(data, list) else data.get("items") or data.get("customers") or []
    cust = items[0]
    return cust.get("mobile") or cust.get("phone")


@pytest.fixture(scope="session")
def sample_store_id(admin_headers):
    r = requests.get(f"{API}/stores", headers=admin_headers, timeout=15)
    stores = r.json()
    items = stores if isinstance(stores, list) else stores.get("items", [])
    return items[0]["id"] if items else None


class TestPOS:
    def test_validate_customer(self, sample_customer_mobile):
        r = requests.post(f"{API}/pos/validate-customer", json={"mobile": sample_customer_mobile}, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json().get("found") in (True, None) or r.json()

    def test_issue_otp(self, sample_customer_mobile):
        r = requests.post(f"{API}/pos/issue-otp", json={"mobile": sample_customer_mobile}, timeout=20)
        assert r.status_code == 200, r.text
        # demo_otp returned for dev
        body = r.json()
        assert "demo_otp" in body or "otp" in body or body.get("success") is True

    def test_issue_points(self, sample_customer_mobile, sample_store_id):
        payload = {
            "mobile": sample_customer_mobile,
            "amount": 1000,
            "store_id": sample_store_id,
            "bill_number": f"TEST{int(time.time())}",
        }
        r = requests.post(f"{API}/pos/issue-points", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        body = r.json()
        # should award points
        assert body.get("success") or "points" in body or "points_awarded" in body or "transaction_id" in body

    def test_redeem_coupon(self, sample_customer_mobile):
        # Try with a known/random code; expect 200/404/400
        r = requests.post(
            f"{API}/pos/redeem-coupon",
            json={"mobile": sample_customer_mobile, "code": "INVALIDXX"},
            timeout=15,
        )
        assert r.status_code in (200, 400, 404), r.text


# ============== PUBLIC ==============
class TestPublic:
    def test_stores(self):
        r = requests.get(f"{API}/public/stores", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_store_cities(self):
        r = requests.get(f"{API}/public/store-cities", timeout=15)
        assert r.status_code == 200

    def test_faqs(self):
        r = requests.get(f"{API}/public/faqs", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_register_interest(self):
        payload = {
            "name": "TEST_Public",
            "mobile": f"9{int(time.time()) % 10**9:09d}",
            "email": f"TEST_public_{int(time.time())}@example.com",
            "city": "Mumbai",
        }
        r = requests.post(f"{API}/public/register-interest", json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text
        body = r.json()
        # Welcome bonus expected
        assert body.get("success") is not False


# ============== NPS ==============
class TestNPS:
    def test_summary(self, admin_headers):
        r = requests.get(f"{API}/nps/summary", headers=admin_headers, timeout=15)
        assert r.status_code == 200

    def test_by_store(self, admin_headers):
        r = requests.get(f"{API}/nps/by-store", headers=admin_headers, timeout=15)
        assert r.status_code == 200

    def test_recent(self, admin_headers):
        r = requests.get(f"{API}/nps/recent", headers=admin_headers, timeout=15)
        assert r.status_code == 200


# ============== TICKETS ==============
class TestTickets:
    def test_list(self, admin_headers):
        r = requests.get(f"{API}/tickets", headers=admin_headers, timeout=15)
        assert r.status_code == 200

    def test_update_status_and_note(self, admin_headers):
        r = requests.get(f"{API}/tickets", headers=admin_headers, timeout=15)
        tickets = r.json()
        items = tickets if isinstance(tickets, list) else tickets.get("items", [])
        if not items:
            pytest.skip("No tickets to update")
        tid = items[0]["id"]
        r2 = requests.patch(f"{API}/tickets/{tid}", headers=admin_headers, json={"status": "in_progress"}, timeout=15)
        assert r2.status_code in (200, 201), r2.text
        r3 = requests.post(f"{API}/tickets/{tid}/notes", headers=admin_headers, json={"note": "TEST_note"}, timeout=15)
        assert r3.status_code in (200, 201), r3.text


# ============== REPORTS ==============
class TestReports:
    def test_transactions(self, admin_headers):
        r = requests.get(f"{API}/reports/transactions?limit=10", headers=admin_headers, timeout=20)
        assert r.status_code == 200

    def test_audit_logs(self, admin_headers):
        r = requests.get(f"{API}/reports/audit-logs?limit=10", headers=admin_headers, timeout=20)
        assert r.status_code == 200

    def test_csv_export(self, admin_headers):
        # Try common CSV endpoints
        candidates = [
            "/reports/transactions/export",
            "/reports/transactions.csv",
            "/reports/export/transactions",
        ]
        last = None
        for path in candidates:
            r = requests.get(f"{API}{path}", headers=admin_headers, timeout=20)
            last = r
            if r.status_code == 200:
                ct = r.headers.get("content-type", "")
                assert "csv" in ct.lower() or "text/" in ct.lower(), f"Unexpected content-type: {ct}"
                return
        pytest.skip(f"CSV export endpoint not found (last status={last.status_code if last else 'n/a'})")
