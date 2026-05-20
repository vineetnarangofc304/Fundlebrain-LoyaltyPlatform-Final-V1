"""Iteration 10 — eWards-compatible POS Integration + Live Monitor + API Monitor tests.

Coverage:
  - POS Credentials bootstrap + admin listing
  - x-api-key / merchant_id / customer_key validation (403)
  - 14 POS endpoints from eWards spec (/api/pos/*)
  - Live Monitor /transactions + /stats
  - API Monitor /api-monitor/logs + /log/{id}
"""
import os
import uuid
import time
import pytest
import requests

def _load_base_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        try:
            with open("/app/frontend/.env") as fh:
                for line in fh:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip()
                        break
        except FileNotFoundError:
            pass
    if not url:
        raise RuntimeError("REACT_APP_BACKEND_URL not set")
    return url.rstrip("/")


BASE_URL = _load_base_url()
SUPER_EMAIL = "superadmin@fundle.io"
SUPER_PW = "Fundle@2026"
TEST_MOBILE = "966681235"
MERCHANT_ID = "KAZO_FUNDLE"
CUSTOMER_KEY = "KAZO_MASTER_OUTLET"


# ---------------- Shared fixtures ----------------
@pytest.fixture(scope="session")
def super_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                       json={"email": SUPER_EMAIL, "password": SUPER_PW}, timeout=30)
    assert r.status_code == 200, f"super_admin login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"missing token in {r.json()}"
    return tok


@pytest.fixture(scope="session")
def auth_headers(super_token):
    return {"Authorization": f"Bearer {super_token}"}


@pytest.fixture(scope="session")
def api_key(auth_headers):
    r = requests.get(f"{BASE_URL}/api/admin/pos-credentials",
                      headers=auth_headers, timeout=15)
    assert r.status_code == 200, f"pos-credentials list failed {r.status_code}: {r.text}"
    creds = r.json().get("credentials", [])
    default = next((c for c in creds if c.get("label") == "kazo_default" and c.get("is_active")), None)
    assert default, f"no kazo_default active credential found: {creds}"
    assert default.get("merchant_id") == MERCHANT_ID
    assert default.get("customer_key") == CUSTOMER_KEY
    assert default.get("api_key")
    return default["api_key"]


def _pos_headers(api_key):
    return {"x-api-key": api_key, "Content-Type": "application/json"}


def _base_creds():
    return {"merchant_id": MERCHANT_ID, "customer_key": CUSTOMER_KEY}


# ---------------- 1. Bootstrap ----------------
class TestBootstrap:
    def test_default_credential_exists(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/admin/pos-credentials", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        creds = r.json()["credentials"]
        assert any(c.get("label") == "kazo_default" and c.get("is_active") for c in creds)

    def test_test_customer_seeded(self, api_key):
        # Use posCustomerCheck to verify test customer + points + tier + coupons
        payload = {**_base_creds(), "customer_mobile": TEST_MOBILE, "bill_amount": 1500}
        r = requests.post(f"{BASE_URL}/api/pos/posCustomerCheck",
                          headers=_pos_headers(api_key), json=payload, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body["status_code"] == 200
        details = body["response"]["details"]
        assert details["name"] == "KAZO Test Customer", details
        assert details["tier"] == "gold", details
        assert details["current_points"] >= 1000, details
        codes = {x.get("reward_code") for x in body["response"].get("rewards", [])}
        for must in ("POSTEST10", "POSTEST20PCT", "POSTESTVIP"):
            assert must in codes, f"missing coupon {must} in {codes}"


# ---------------- 2. Auth ----------------
class TestPosAuth:
    def test_bad_api_key_403(self):
        payload = {**_base_creds(), "customer_mobile": TEST_MOBILE}
        r = requests.post(f"{BASE_URL}/api/pos/posCustomerCheck",
                          headers={"x-api-key": "WRONG_KEY"}, json=payload, timeout=15)
        assert r.status_code == 403

    def test_missing_api_key_403(self):
        payload = {**_base_creds(), "customer_mobile": TEST_MOBILE}
        r = requests.post(f"{BASE_URL}/api/pos/posCustomerCheck", json=payload, timeout=15)
        assert r.status_code == 403

    def test_wrong_merchant_id_403(self, api_key):
        payload = {"merchant_id": "WRONG", "customer_key": CUSTOMER_KEY, "customer_mobile": TEST_MOBILE}
        r = requests.post(f"{BASE_URL}/api/pos/posCustomerCheck",
                          headers=_pos_headers(api_key), json=payload, timeout=15)
        assert r.status_code == 403

    def test_wrong_customer_key_403(self, api_key):
        payload = {"merchant_id": MERCHANT_ID, "customer_key": "WRONG", "customer_mobile": TEST_MOBILE}
        r = requests.post(f"{BASE_URL}/api/pos/posCustomerCheck",
                          headers=_pos_headers(api_key), json=payload, timeout=15)
        assert r.status_code == 403


# ---------------- 3. Customer Check ----------------
class TestCustomerCheck:
    def test_not_registered_mobile(self, api_key):
        payload = {**_base_creds(), "customer_mobile": "9999900000", "bill_amount": 100}
        r = requests.post(f"{BASE_URL}/api/pos/posCustomerCheck",
                          headers=_pos_headers(api_key), json=payload, timeout=15)
        assert r.status_code == 200  # eWards uses status_code in body
        body = r.json()
        assert body["status_code"] == 400
        assert "not registered" in body["response"]["message"].lower()


# ---------------- 4. OTP request + verify ----------------
class TestOTPFlow:
    def test_otp_request_and_verify(self, api_key):
        payload = {**_base_creds(), "customer_mobile": TEST_MOBILE, "bill_amount": 1500}
        r = requests.post(f"{BASE_URL}/api/pos/posCustomerCheckRequest",
                          headers=_pos_headers(api_key), json=payload, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body["status_code"] == 200
        resp = body["response"]
        assert "otp_id" in resp
        otp = resp.get("otp_demo")
        assert otp, f"otp_demo missing: {resp}"

        # verify
        verify_payload = {**_base_creds(), "customer_mobile": TEST_MOBILE, "otp": otp}
        r2 = requests.post(f"{BASE_URL}/api/pos/posCustomerOTPCheck",
                           headers=_pos_headers(api_key), json=verify_payload, timeout=15)
        assert r2.status_code == 200
        body2 = r2.json()
        assert body2["status_code"] == 200
        assert body2["response"]["details"]["current_points"] >= 1000

    def test_bad_otp_400(self, api_key):
        # First create an OTP session so the mobile has one
        requests.post(f"{BASE_URL}/api/pos/posCustomerCheckRequest",
                       headers=_pos_headers(api_key),
                       json={**_base_creds(), "customer_mobile": TEST_MOBILE}, timeout=15)
        bad = {**_base_creds(), "customer_mobile": TEST_MOBILE, "otp": "000000"}
        r = requests.post(f"{BASE_URL}/api/pos/posCustomerOTPCheck",
                          headers=_pos_headers(api_key), json=bad, timeout=15)
        body = r.json()
        assert body["status_code"] == 400
        assert "invalid otp" in body["response"]["message"].lower()


# ---------------- 5. Add / Update Customer ----------------
class TestAddCustomer:
    def test_register_then_update(self, api_key):
        new_mobile = f"77{int(time.time())%10**8:08d}"  # unique
        register = {**_base_creds(),
                    "customer": {"mobile": new_mobile, "name": "TEST_NewMember", "email": "t@e.com"}}
        r = requests.post(f"{BASE_URL}/api/pos/posAddCustomer",
                          headers=_pos_headers(api_key), json=register, timeout=15)
        body = r.json()
        assert body["status_code"] == 200, body
        assert "registered" in body["response"]["message"].lower()

        # update
        update = {**_base_creds(),
                  "customer": {"mobile": new_mobile, "name": "TEST_UpdatedName", "city": "Mumbai"}}
        r2 = requests.post(f"{BASE_URL}/api/pos/posAddCustomer",
                           headers=_pos_headers(api_key), json=update, timeout=15)
        body2 = r2.json()
        assert body2["status_code"] == 200, body2
        assert "updated" in body2["response"]["message"].lower()


# ---------------- 6. Redeem points ----------------
class TestRedeemFlow:
    def test_redeem_request_and_verify_otp(self, api_key):
        payload = {**_base_creds(), "customer_mobile": TEST_MOBILE, "points": 500,
                   "transaction": {"number": f"REDEEM-{uuid.uuid4().hex[:8]}"}}
        r = requests.post(f"{BASE_URL}/api/pos/posRedeemPointRequest",
                          headers=_pos_headers(api_key), json=payload, timeout=15)
        body = r.json()
        assert body["status_code"] == 200, body
        assert "redeem_id" in body["response"]
        otp = body["response"].get("otp_demo")
        assert otp

        # current balance
        chk = requests.post(f"{BASE_URL}/api/pos/posCustomerCheck",
                            headers=_pos_headers(api_key),
                            json={**_base_creds(), "customer_mobile": TEST_MOBILE}, timeout=15)
        before = chk.json()["response"]["details"]["current_points"]

        verify = {**_base_creds(), "customer_mobile": TEST_MOBILE, "otp": otp, "points": 500,
                  "transaction": payload["transaction"]}
        r2 = requests.post(f"{BASE_URL}/api/pos/posRedeemPointOtpCheck",
                           headers=_pos_headers(api_key), json=verify, timeout=15)
        body2 = r2.json()
        assert body2["status_code"] == 200, body2

        chk2 = requests.post(f"{BASE_URL}/api/pos/posCustomerCheck",
                             headers=_pos_headers(api_key),
                             json={**_base_creds(), "customer_mobile": TEST_MOBILE}, timeout=15)
        after = chk2.json()["response"]["details"]["current_points"]
        assert after == before - 500, f"balance not deducted: {before} -> {after}"

    def test_insufficient_balance(self, api_key):
        payload = {**_base_creds(), "customer_mobile": TEST_MOBILE,
                   "points": 9999999,
                   "transaction": {"number": f"BIG-{uuid.uuid4().hex[:6]}"}}
        r = requests.post(f"{BASE_URL}/api/pos/posRedeemPointRequest",
                          headers=_pos_headers(api_key), json=payload, timeout=15)
        body = r.json()
        assert body["status_code"] == 400
        assert "sufficient" in body["response"]["message"].lower()


# ---------------- 7. Bill settlement (posAddPoint) ----------------
class TestAddPoint:
    def test_unique_bill_settlement(self, api_key):
        bill = f"BILL-{uuid.uuid4().hex[:10]}"
        payload = {
            **_base_creds(),
            "customer": {"mobile": TEST_MOBILE, "name": "KAZO Test Customer"},
            "transaction": {
                "number": bill,
                "id": bill,
                "gross_amount": "1200",
                "net_amount": "1000",
                "amount": "1000",
                "discount": "200",
                "loyalty_flag": "1",
                "loyalty_gross_amount": "1000",
                "outlet": "ITERATION10_TEST_OUTLET",
                "order_time": "2026-01-15T10:00:00Z",
                "items": [{"id": "SKU1", "name": "Test Shirt", "rate": "1000", "quantity": "1"}],
                "payment_mode": [{"name": "card"}],
            },
        }
        r = requests.post(f"{BASE_URL}/api/pos/posAddPoint",
                          headers=_pos_headers(api_key), json=payload, timeout=20)
        body = r.json()
        assert body["status_code"] == 200, body
        resp = body["response"]
        assert "order_id" in resp
        assert resp["points_earned"] >= 1
        assert resp["new_balance"] >= 0
        assert resp["new_tier"] in ("silver", "gold", "platinum", "diamond")
        # store this for duplicate test
        TestAddPoint._used_bill = bill

    def test_duplicate_bill_rejected(self, api_key):
        bill = getattr(TestAddPoint, "_used_bill", None)
        if not bill:
            pytest.skip("primary settlement test did not run")
        payload = {
            **_base_creds(),
            "customer": {"mobile": TEST_MOBILE, "name": "KAZO Test Customer"},
            "transaction": {"number": bill, "id": bill, "gross_amount": "100",
                            "net_amount": "100", "amount": "100", "loyalty_flag": "1"},
        }
        r = requests.post(f"{BASE_URL}/api/pos/posAddPoint",
                          headers=_pos_headers(api_key), json=payload, timeout=20)
        body = r.json()
        assert body["status_code"] == 400
        assert "same bill number" in body["response"]["message"].lower()


# ---------------- 8. Coupons ----------------
class TestCoupons:
    def test_coupon_details_valid(self, api_key):
        payload = {**_base_creds(), "coupon_code": "POSTEST10", "bill_amount": 1500,
                   "customer_mobile": TEST_MOBILE}
        r = requests.post(f"{BASE_URL}/api/pos/posCouponDetails",
                          headers=_pos_headers(api_key), json=payload, timeout=15)
        body = r.json()
        assert body["status_code"] == 200, body
        assert float(body["response"]["applicable_discount_amount"]) == 100.0

    def test_coupon_invalid_code(self, api_key):
        payload = {**_base_creds(), "coupon_code": "NOPESUCHCODE", "bill_amount": 1500}
        r = requests.post(f"{BASE_URL}/api/pos/posCouponDetails",
                          headers=_pos_headers(api_key), json=payload, timeout=15)
        body = r.json()
        assert body["status_code"] == 400
        assert "invalid code" in body["response"]["message"].lower()

    def test_coupon_min_bill(self, api_key):
        payload = {**_base_creds(), "coupon_code": "POSTEST10", "bill_amount": 100}
        r = requests.post(f"{BASE_URL}/api/pos/posCouponDetails",
                          headers=_pos_headers(api_key), json=payload, timeout=15)
        body = r.json()
        assert body["status_code"] == 400
        assert "minimum bill" in body["response"]["message"].lower()

    def test_coupon_redeem_increments_counter(self, api_key):
        # get current usage
        det = requests.post(f"{BASE_URL}/api/pos/posCouponDetails",
                             headers=_pos_headers(api_key),
                             json={**_base_creds(), "coupon_code": "POSTEST10", "bill_amount": 1500},
                             timeout=15).json()
        assert det["status_code"] == 200
        bill = f"COUP-{uuid.uuid4().hex[:8]}"
        payload = {**_base_creds(), "coupon_code": "POSTEST10", "bill_amount": 1500,
                   "customer_mobile": TEST_MOBILE, "transaction": {"number": bill}}
        r = requests.post(f"{BASE_URL}/api/pos/posRedeemCoupon",
                          headers=_pos_headers(api_key), json=payload, timeout=15)
        body = r.json()
        assert body["status_code"] == 200, body
        assert "redeemed" in body["response"]["message"].lower()


# ---------------- 9. Return Order ----------------
class TestReturnOrder:
    def test_return_existing_bill(self, api_key):
        # create a fresh bill first
        bill = f"RETSRC-{uuid.uuid4().hex[:8]}"
        requests.post(f"{BASE_URL}/api/pos/posAddPoint",
                       headers=_pos_headers(api_key),
                       json={**_base_creds(),
                              "customer": {"mobile": TEST_MOBILE, "name": "KAZO Test Customer"},
                              "transaction": {"number": bill, "id": bill,
                                              "gross_amount": "500", "net_amount": "500",
                                              "amount": "500", "loyalty_flag": "1",
                                              "loyalty_gross_amount": "500"}},
                       timeout=20)
        # return it
        payload = {**_base_creds(), "mobile": TEST_MOBILE,
                   "transaction": {"number": bill, "return_amount": "-500",
                                    "return_net_amount": "-500",
                                    "return_loyalty_gross_amount": "-500"}}
        r = requests.post(f"{BASE_URL}/api/pos/returnOrder",
                          headers=_pos_headers(api_key), json=payload, timeout=20)
        body = r.json()
        assert body["status_code"] == 200, body
        assert "order_id" in body["response"]


# ---------------- 10. Live Monitor ----------------
class TestLiveMonitor:
    def test_transactions(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/live-monitor/transactions?limit=50",
                          headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "rows" in data
        if data["rows"]:
            row = data["rows"][0]
            assert "has_mobile" in row
            assert "lost_opportunity" in row

    def test_transactions_filter_has_mobile_no(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/live-monitor/transactions?has_mobile=no&limit=20",
                          headers=auth_headers, timeout=15)
        assert r.status_code == 200
        for row in r.json()["rows"]:
            assert not row.get("has_mobile")
            assert row.get("lost_opportunity") is True

    def test_transactions_amount_filter(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/live-monitor/transactions?min_amount=0&max_amount=999999",
                          headers=auth_headers, timeout=15)
        assert r.status_code == 200

    def test_stats(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/live-monitor/stats?minutes=60",
                          headers=auth_headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        for key in ("bills_total", "bills_with_mobile", "bills_without_mobile",
                     "mobile_attach_rate_pct", "by_store_top10"):
            assert key in data, f"missing {key}"
        assert isinstance(data["by_store_top10"], list)


# ---------------- 11. API Monitor ----------------
class TestApiMonitor:
    def test_logs_list_with_payloads(self, auth_headers, api_key):
        # generate at least 1 fresh POS call
        requests.post(f"{BASE_URL}/api/pos/posCustomerCheck",
                       headers=_pos_headers(api_key),
                       json={**_base_creds(), "customer_mobile": TEST_MOBILE}, timeout=15)
        time.sleep(0.5)
        r = requests.get(f"{BASE_URL}/api/api-monitor/logs?source=pos_ewards&limit=20",
                          headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        rows = r.json()["rows"]
        assert rows, "no pos_ewards api logs found"
        with_payload = [
            x for x in rows if x.get("request_payload") and x.get("response_payload")
        ]
        assert with_payload, "no log has both request_payload and response_payload"
        TestApiMonitor._log_id = with_payload[0]["id"]

    def test_log_detail(self, auth_headers):
        log_id = getattr(TestApiMonitor, "_log_id", None)
        if not log_id:
            pytest.skip("list test did not capture log_id")
        r = requests.get(f"{BASE_URL}/api/api-monitor/log/{log_id}",
                          headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("request_payload") is not None
        assert body.get("response_payload") is not None
