"""Iteration 2 backend tests: CMS, Item Master (+bulk), Stores bulk/edit/delete,
Analytics dashboards, ticket get-single + notes, coupon PATCH, customer filter."""
import io
import os
import time
import uuid
import pytest
import requests

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@kazo.com"
ADMIN_PASS = "Kazo@2026"


# ---------------- Fixtures ----------------
@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(
        f"{API}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS, "portal": "enterprise"},
        timeout=20,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="session")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------------- CMS ----------------
class TestCMS:
    def test_get_content_public_no_auth(self):
        r = requests.get(f"{API}/cms/content", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("home", "footer", "support"):
            assert k in data, f"missing key {k}"
        assert "hero_headline_1" in data["home"]
        assert "email" in data["support"]

    def test_put_content_requires_auth(self):
        r = requests.put(f"{API}/cms/content", json={"home": {"hero_eyebrow": "X"}}, timeout=20)
        assert r.status_code in (401, 403)

    def test_put_content_updates(self, auth_headers):
        marker = f"TEST_HERO_{uuid.uuid4().hex[:8]}"
        payload = {"home": {"hero_eyebrow": marker, "hero_headline_1": "Where style"}, "support": {"email": "rewards@kazo.com"}}
        r = requests.put(f"{API}/cms/content", json=payload, headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["home"]["hero_eyebrow"] == marker
        # Persistence via public GET
        r2 = requests.get(f"{API}/cms/content", timeout=20)
        assert r2.json()["home"]["hero_eyebrow"] == marker


# ---------------- Item Master ----------------
class TestItemMaster:
    created_id = None
    created_sku = f"TESTSKU{uuid.uuid4().hex[:6].upper()}"

    def test_list_items(self, auth_headers):
        r = requests.get(f"{API}/items", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "total" in data and "items" in data
        assert isinstance(data["items"], list)

    def test_create_item(self, auth_headers):
        payload = {
            "sku": TestItemMaster.created_sku,
            "name": "TEST_ Dress",
            "category": "DRESSES",
            "subcategory": "PARTY",
            "description": "test",
            "erp_id": "KZ-TEST-1",
            "barcode": "8900000001",
            "mrp": 1999,
            "season": "SS26",
            "color": "Red",
            "size": "M",
        }
        r = requests.post(f"{API}/items", json=payload, headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["sku"] == TestItemMaster.created_sku
        assert data["name"] == "TEST_ Dress"
        assert data["mrp"] == 1999
        assert "id" in data
        TestItemMaster.created_id = data["id"]

    def test_create_duplicate_sku_409(self, auth_headers):
        payload = {"sku": TestItemMaster.created_sku, "name": "dup", "mrp": 0}
        r = requests.post(f"{API}/items", json=payload, headers=auth_headers, timeout=20)
        assert r.status_code == 409

    def test_patch_item(self, auth_headers):
        iid = TestItemMaster.created_id
        assert iid
        r = requests.patch(f"{API}/items/{iid}", json={"name": "TEST_ Updated", "mrp": 2599}, headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["name"] == "TEST_ Updated"
        assert data["mrp"] == 2599

    def test_delete_item(self, auth_headers):
        iid = TestItemMaster.created_id
        r = requests.delete(f"{API}/items/{iid}", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        assert r.json().get("success") is True

    def test_categories_crud(self, auth_headers):
        name = f"TEST_CAT_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{API}/items/categories", json={"name": name}, headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        # list
        r2 = requests.get(f"{API}/items/categories", headers=auth_headers, timeout=20)
        assert r2.status_code == 200
        assert any(c["id"] == cid for c in r2.json())
        # cleanup
        requests.delete(f"{API}/items/categories/{cid}", headers=auth_headers, timeout=20)

    def test_sample_csv(self, auth_headers):
        r = requests.get(f"{API}/items/sample-csv", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        text = r.text
        assert "sku,name,category" in text
        assert "K10001" in text or "KAZO" in text

    def test_bulk_upload(self, auth_headers):
        sku1 = f"TESTBULK{uuid.uuid4().hex[:5].upper()}"
        sku2 = f"TESTBULK{uuid.uuid4().hex[:5].upper()}"
        csv_text = (
            "sku,name,category,subcategory,description,erp_id,barcode,mrp,season,color,size\n"
            f"{sku1},Test SKU 1,DRESSES,PARTY,desc,KZ-99001,890099001,2999,SS26,Red,M\n"
            f"{sku2},Test SKU 2,TOPS,CASUAL,desc,KZ-99002,890099002,1499,SS26,Blue,S\n"
        )
        files = {"file": ("items.csv", io.BytesIO(csv_text.encode("utf-8")), "text/csv")}
        r = requests.post(f"{API}/items/bulk-upload", files=files, headers=auth_headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["inserted"] >= 2
        assert "skipped" in data and "errors" in data

        # second upload should be all skipped (duplicates)
        files2 = {"file": ("items.csv", io.BytesIO(csv_text.encode("utf-8")), "text/csv")}
        r2 = requests.post(f"{API}/items/bulk-upload", files=files2, headers=auth_headers, timeout=30)
        assert r2.status_code == 200
        assert r2.json()["skipped"] >= 2


# ---------------- Stores ----------------
class TestStores:
    new_store_id = None

    def test_stores_sample_csv(self, auth_headers):
        r = requests.get(f"{API}/stores/sample-csv/download", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        assert "code,name,city" in r.text

    def test_stores_bulk_upload(self, auth_headers):
        code = f"TESTST{uuid.uuid4().hex[:5].upper()}"
        csv_text = (
            "code,name,city,state,region,address,phone,manager_name,latitude,longitude\n"
            f"{code},TEST_ Store,Pune,Maharashtra,West,Test addr,9999999999,Test Mgr,18.5,73.9\n"
        )
        files = {"file": ("stores.csv", io.BytesIO(csv_text.encode("utf-8")), "text/csv")}
        r = requests.post(f"{API}/stores/bulk-upload", files=files, headers=auth_headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["inserted"] >= 1

        # find the inserted store id
        rl = requests.get(f"{API}/stores", headers=auth_headers, timeout=20)
        assert rl.status_code == 200
        for s in rl.json():
            if s.get("code") == code:
                TestStores.new_store_id = s["id"]
                break
        assert TestStores.new_store_id, "Inserted store not found in list"

        # duplicate upload skips
        files2 = {"file": ("stores.csv", io.BytesIO(csv_text.encode("utf-8")), "text/csv")}
        r2 = requests.post(f"{API}/stores/bulk-upload", files=files2, headers=auth_headers, timeout=30)
        assert r2.json()["skipped"] >= 1

    def test_stores_patch(self, auth_headers):
        sid = TestStores.new_store_id
        assert sid
        r = requests.patch(f"{API}/stores/{sid}", json={"name": "TEST_ Store Updated", "manager_name": "New Mgr"}, headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "TEST_ Store Updated"

    def test_stores_delete_deactivates(self, auth_headers):
        sid = TestStores.new_store_id
        r = requests.delete(f"{API}/stores/{sid}", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        g = requests.get(f"{API}/stores/{sid}", headers=auth_headers, timeout=20)
        assert g.status_code == 200
        assert g.json().get("is_active") is False


# ---------------- Analytics ----------------
class TestAnalytics:
    def test_sales_dashboard(self, auth_headers):
        r = requests.get(f"{API}/analytics/sales-dashboard?period_days=30", headers=auth_headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("hourly", "weekday", "payment_mix", "discount_distribution"):
            assert k in data
            assert isinstance(data[k], list)
            assert len(data[k]) > 0, f"{k} is empty"

    def test_customer_dashboard(self, auth_headers):
        r = requests.get(f"{API}/analytics/customer-dashboard", headers=auth_headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("new_customer_trend", "churn_distribution", "visit_frequency", "top_customers", "city_distribution"):
            assert k in data
        assert len(data["top_customers"]) > 0

    def test_loyalty_dashboard(self, auth_headers):
        r = requests.get(f"{API}/analytics/loyalty-dashboard", headers=auth_headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "tiers" in data and "points_trend" in data
        assert len(data["tiers"]) > 0

    def test_campaign_dashboard(self, auth_headers):
        r = requests.get(f"{API}/analytics/campaign-dashboard", headers=auth_headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "all" in data and "by_channel" in data
        assert isinstance(data["all"], list)
        assert isinstance(data["by_channel"], list)

    def test_store_dashboard(self, auth_headers):
        r = requests.get(f"{API}/analytics/store-dashboard", headers=auth_headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "stores" in data and "regions" in data
        # Per spec: 25 stores seeded
        assert len(data["stores"]) >= 1
        assert len(data["regions"]) > 0

    def test_nps_dashboard(self, auth_headers):
        r = requests.get(f"{API}/analytics/nps-dashboard?period_days=60", headers=auth_headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        if data:
            for k in ("date", "nps", "promoters", "detractors", "total"):
                assert k in data[0]

    def test_transaction_detail(self, auth_headers):
        # get a valid txn id
        rt = requests.get(f"{API}/reports/transactions?limit=1", headers=auth_headers, timeout=20)
        assert rt.status_code == 200, rt.text
        body = rt.json()
        txns = body if isinstance(body, list) else body.get("transactions") or body.get("data") or body.get("items") or []
        assert txns, f"No transactions to drill into: {body}"
        txn_id = txns[0]["id"]
        r = requests.get(f"{API}/analytics/transaction/{txn_id}", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "transaction" in data and "store" in data
        assert data["transaction"]["id"] == txn_id

    def test_transaction_detail_404(self, auth_headers):
        r = requests.get(f"{API}/analytics/transaction/nonexistent_xyz", headers=auth_headers, timeout=20)
        assert r.status_code == 404

    def test_coupon_detail(self, auth_headers):
        rc = requests.get(f"{API}/coupons", headers=auth_headers, timeout=20)
        assert rc.status_code == 200
        coupons = rc.json()
        assert coupons, "No coupons seeded"
        cid = coupons[0]["id"]
        r = requests.get(f"{API}/analytics/coupon-detail/{cid}", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("coupon", "redemptions", "trend"):
            assert k in data
        assert data["coupon"]["id"] == cid


# ---------------- Tickets ----------------
class TestTickets:
    ticket_id = None

    def test_create_and_get_single(self, auth_headers):
        # First fetch a customer to attach
        rc = requests.get(f"{API}/customers?limit=1", headers=auth_headers, timeout=20)
        custs = rc.json()
        custs = custs if isinstance(custs, list) else custs.get("customers") or custs.get("data") or []
        cust_id = custs[0]["id"] if custs else "TEST_CUST"
        payload = {
            "customer_id": cust_id,
            "subject": "TEST_ ticket subject",
            "description": "TEST_ description",
            "category": "general",
            "priority": "medium",
        }
        r = requests.post(f"{API}/tickets", json=payload, headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        TestTickets.ticket_id = r.json()["id"]

        g = requests.get(f"{API}/tickets/{TestTickets.ticket_id}", headers=auth_headers, timeout=20)
        assert g.status_code == 200
        body = g.json()
        assert body["id"] == TestTickets.ticket_id
        assert "notes" in body and body["notes"] == []

    def test_add_note_and_visible(self, auth_headers):
        tid = TestTickets.ticket_id
        assert tid
        r = requests.post(f"{API}/tickets/{tid}/notes", json={"content": "TEST_ first note"}, headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        assert r.json()["content"] == "TEST_ first note"

        g = requests.get(f"{API}/tickets/{tid}", headers=auth_headers, timeout=20)
        notes = g.json().get("notes", [])
        assert len(notes) == 1
        assert notes[0]["content"] == "TEST_ first note"
        assert "author_email" in notes[0]

    def test_get_single_404(self, auth_headers):
        r = requests.get(f"{API}/tickets/does_not_exist_xyz", headers=auth_headers, timeout=20)
        assert r.status_code == 404


# ---------------- Coupon PATCH ----------------
class TestCouponEdit:
    def test_patch_coupon(self, auth_headers):
        rc = requests.get(f"{API}/coupons", headers=auth_headers, timeout=20)
        coupons = rc.json()
        assert coupons
        cid = coupons[0]["id"]
        original = coupons[0]
        new_name = f"TEST_PATCH_{uuid.uuid4().hex[:6]}"
        new_val = float(original.get("discount_value", 100)) + 1
        r = requests.patch(
            f"{API}/coupons/{cid}",
            json={"name": new_name, "discount_value": new_val, "is_active": True},
            headers=auth_headers, timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("name") == new_name
        assert float(body.get("discount_value")) == new_val
        assert body.get("is_active") is True

        # restore original name/value
        requests.patch(
            f"{API}/coupons/{cid}",
            json={"name": original.get("name"), "discount_value": original.get("discount_value")},
            headers=auth_headers, timeout=20,
        )


# ---------------- Customer Filter ----------------
class TestCustomerFilter:
    def test_churn_risk_high(self, auth_headers):
        r = requests.get(f"{API}/customers?churn_risk=high", headers=auth_headers, timeout=20)
        assert r.status_code == 200, r.text
        body = r.json()
        rows = body if isinstance(body, list) else body.get("customers") or body.get("data") or body.get("items") or []
        # If there are results, all must have churn_risk == 'high'
        for c in rows[:50]:
            assert c.get("churn_risk") == "high", f"got {c.get('churn_risk')}"
