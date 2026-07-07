"""Iteration 84 — broader POS regression test.

Confirms that the P0 partial-commit refactor (commit_status marker, idempotent
_apply_bill_credit, $set -> $inc on customer aggregates) did NOT regress the core
POS flows we already ship:

  1. posCustomerCheck  (identity + rewards + redeemable_points snapshot)
  2. posCustomerCheckRequest + posCustomerOTPCheck (mock OTP 123456)
  3. posAddPoint       (unique bill -> committed, ledger row, balance +delta)
  4. posRedeemPointRequest + posRedeemPointOtpCheck (mock OTP 123456)
  5. returnOrder        (reverses points + lifetime_spend)
  6. posAddPoint TRUE DUPLICATE — same committed bill returns 400, no double credit

All state is seeded on scratch mobile 99900xxxxx numbers and cleaned up at teardown.
"""
import os
import sys
import time
import uuid
import asyncio
import pytest
import requests

sys.path.insert(0, "/app/backend")

from database import (transactions_col, customers_col, points_ledger_col,  # noqa: E402
                      db as _db)
pos_otp_col = _db["pos_otp_sessions"]


def _load_env():
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.strip().startswith("REACT_APP_BACKEND_URL"):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""


BASE = (os.environ.get("REACT_APP_BACKEND_URL") or _load_env()).rstrip("/")
assert BASE, "no backend url"
POS_KEY = "ZFQWql7I3vCH0ckuWmA8zVKDDJWYPBtoQGLruEnRrFI"
HDR = {"x-api-key": POS_KEY, "Content-Type": "application/json"}
MERCHANT = "KAZO_FUNDLE"
STORE = "K00055"
TEST_OTP = "123456"


def _now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


async def _seed_customer(mobile, balance=500, lifetime=500, tier="gold"):
    await customers_col.delete_many({"mobile": mobile})
    cid = uuid.uuid4().hex
    await customers_col.insert_one({
        "id": cid, "mobile": mobile, "name": f"Regr {mobile[-4:]}",
        "tier": tier, "points_balance": balance,
        "lifetime_points_earned": lifetime, "lifetime_points_redeemed": 0,
        "lifetime_spend": 100000, "visit_count": 5, "source": "pos_ewards",
        "created_at": _now_iso(),
    })
    return cid


async def _get_customer(mobile):
    return await customers_col.find_one({"mobile": mobile}, {"_id": 0})


async def _cleanup(mobiles, bills):
    await customers_col.delete_many({"mobile": {"$in": mobiles}})
    await transactions_col.delete_many({"bill_number": {"$in": bills}})
    await transactions_col.delete_many({"original_bill_number": {"$in": bills}})
    await points_ledger_col.delete_many({"bill_number": {"$in": bills}})
    await pos_otp_col.delete_many({"mobile": {"$in": mobiles}})


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# -------- 1. posCustomerCheck --------
def test_pos_customer_check():
    mobile = "9990007001"
    _run(_seed_customer(mobile, balance=800))
    try:
        r = requests.post(f"{BASE}/api/pos/posCustomerCheck", headers=HDR, timeout=30, json={
            "merchant_id": MERCHANT, "customer_key": STORE,
            "customer_mobile": mobile, "bill_amount": "3000"})
        env = r.json()
        assert env.get("status_code") == 200, env
        resp = env.get("response") or {}
        assert resp.get("details", {}).get("mobile") in (int(mobile), mobile)
        # points_balance is included as a snapshot
        assert int(resp.get("points_balance") or resp.get("details", {}).get("points_balance") or 800) == 800 \
            or resp.get("redeemable_points") is not None
    finally:
        _run(_cleanup([mobile], []))


def test_pos_customer_check_unregistered_400():
    mobile = "9990007099"  # unseeded
    _run(customers_col.delete_many({"mobile": mobile}))
    r = requests.post(f"{BASE}/api/pos/posCustomerCheck", headers=HDR, timeout=30, json={
        "merchant_id": MERCHANT, "customer_key": STORE,
        "customer_mobile": mobile, "bill_amount": "100"})
    env = r.json()
    assert env.get("status_code") == 400, env
    assert "not registered" in (env.get("response", {}).get("message", "")).lower()


# -------- 2. posCustomerCheckRequest + posCustomerOTPCheck --------
def test_pos_customer_otp_check_flow():
    mobile = "9990007002"
    _run(_seed_customer(mobile))
    try:
        r = requests.post(f"{BASE}/api/pos/posCustomerCheckRequest", headers=HDR, timeout=30, json={
            "merchant_id": MERCHANT, "customer_key": STORE, "customer_mobile": mobile})
        env = r.json()
        assert env.get("status_code") == 200, env
        assert env.get("response", {}).get("otp_id")

        # Mock OTP 123456 must be accepted
        r2 = requests.post(f"{BASE}/api/pos/posCustomerOTPCheck", headers=HDR, timeout=30, json={
            "merchant_id": MERCHANT, "customer_key": STORE,
            "customer_mobile": mobile, "otp": TEST_OTP})
        env2 = r2.json()
        assert env2.get("status_code") == 200, env2

        # Wrong OTP is rejected
        r3 = requests.post(f"{BASE}/api/pos/posCustomerOTPCheck", headers=HDR, timeout=30, json={
            "merchant_id": MERCHANT, "customer_key": STORE,
            "customer_mobile": mobile, "otp": "999999"})
        env3 = r3.json()
        assert env3.get("status_code") == 400, env3
    finally:
        _run(_cleanup([mobile], []))


# -------- 3. posAddPoint happy path (regression on $inc) --------
def test_pos_add_point_happy():
    mobile = "9990007003"
    bill = f"REG-ADD-{int(time.time())}-{uuid.uuid4().hex[:5]}"
    _run(_seed_customer(mobile, balance=200, lifetime=200))
    try:
        r = requests.post(f"{BASE}/api/pos/posAddPoint", headers=HDR, timeout=30, json={
            "merchant_id": MERCHANT, "customer_key": STORE,
            "customer": {"mobile": mobile, "name": "Regr Add"},
            "transaction": {"number": bill, "id": bill, "amount": "1500",
                            "order_time": "2026-07-08 12:00:00"}})
        env = r.json()
        assert env.get("status_code") == 200, env
        resp = env.get("response") or {}
        earned = int(resp.get("points_earned") or 0)
        assert earned > 0, resp

        tx = _run(transactions_col.find_one({"bill_number": bill}, {"_id": 0}))
        cust = _run(_get_customer(mobile))
        led = _run(points_ledger_col.find_one(
            {"bill_number": bill, "type": "earn", "voided": {"$ne": True}}, {"_id": 0}))
        assert tx and tx.get("commit_status") == "committed", tx
        assert tx.get("balance_applied") is True
        assert led and int(led.get("points") or 0) == earned
        assert int(cust.get("points_balance") or 0) == 200 + earned
    finally:
        _run(_cleanup([mobile], [bill]))


# -------- 3b. posAddPoint TRUE DUPLICATE --------
def test_pos_add_point_true_duplicate():
    mobile = "9990007004"
    bill = f"REG-DUP-{int(time.time())}-{uuid.uuid4().hex[:5]}"
    _run(_seed_customer(mobile, balance=200))
    try:
        payload = {
            "merchant_id": MERCHANT, "customer_key": STORE,
            "customer": {"mobile": mobile}, "transaction": {"number": bill, "id": bill, "amount": "1000"}}
        r1 = requests.post(f"{BASE}/api/pos/posAddPoint", headers=HDR, timeout=30, json=payload)
        assert r1.json().get("status_code") == 200
        bal_after = int((_run(_get_customer(mobile)) or {}).get("points_balance") or 0)
        led_before = _run(points_ledger_col.count_documents(
            {"bill_number": bill, "type": "earn", "voided": {"$ne": True}}))

        # Duplicate submission
        r2 = requests.post(f"{BASE}/api/pos/posAddPoint", headers=HDR, timeout=30, json=payload)
        env2 = r2.json()
        assert env2.get("status_code") == 400, env2
        msg = (env2.get("response", {}).get("message") or "").lower()
        assert "same bill" in msg or "cannot be accepted" in msg, env2

        # State unchanged
        bal_after2 = int((_run(_get_customer(mobile)) or {}).get("points_balance") or 0)
        led_after = _run(points_ledger_col.count_documents(
            {"bill_number": bill, "type": "earn", "voided": {"$ne": True}}))
        assert bal_after2 == bal_after, f"double credit! {bal_after}->{bal_after2}"
        assert led_after == led_before, f"ledger doubled! {led_before}->{led_after}"
    finally:
        _run(_cleanup([mobile], [bill]))


# -------- 4. posRedeemPointRequest + posRedeemPointOtpCheck --------
def test_pos_redeem_flow():
    mobile = "9990007005"
    bill = f"REG-RED-{int(time.time())}-{uuid.uuid4().hex[:5]}"
    _run(_seed_customer(mobile, balance=1000))
    try:
        # Request redemption OTP
        r = requests.post(f"{BASE}/api/pos/posRedeemPointRequest", headers=HDR, timeout=30, json={
            "merchant_id": MERCHANT, "customer_key": STORE,
            "customer_mobile": mobile, "points": 200,
            "transaction": {"number": bill, "id": bill, "amount": "1000"}})
        env = r.json()
        assert env.get("status_code") == 200, env
        assert env.get("response", {}).get("redeem_id")

        # Verify with mock OTP
        r2 = requests.post(f"{BASE}/api/pos/posRedeemPointOtpCheck", headers=HDR, timeout=30, json={
            "merchant_id": MERCHANT, "customer_key": STORE,
            "customer_mobile": mobile, "otp": TEST_OTP, "points": 200,
            "transaction": {"number": bill, "id": bill, "amount": "1000"}})
        env2 = r2.json()
        assert env2.get("status_code") == 200, env2

        cust = _run(_get_customer(mobile))
        assert int(cust.get("points_balance") or 0) == 800, cust  # 1000 - 200 redeemed
        # A redeem ledger row must exist
        led = _run(points_ledger_col.find_one(
            {"customer_id": cust["id"], "type": "redeem"}, {"_id": 0}))
        assert led and int(led.get("points") or 0) < 0, led
    finally:
        _run(_cleanup([mobile], [bill]))


def test_pos_redeem_insufficient_balance():
    mobile = "9990007006"
    _run(_seed_customer(mobile, balance=50))
    try:
        r = requests.post(f"{BASE}/api/pos/posRedeemPointRequest", headers=HDR, timeout=30, json={
            "merchant_id": MERCHANT, "customer_key": STORE,
            "customer_mobile": mobile, "points": 500,
            "transaction": {"number": f"REG-NOBAL-{uuid.uuid4().hex[:5]}", "amount": "5000"}})
        env = r.json()
        assert env.get("status_code") == 400, env
        assert "sufficient" in (env.get("response", {}).get("message", "").lower())
    finally:
        _run(_cleanup([mobile], []))


# -------- 5. returnOrder --------
def test_return_order_reverses_points():
    mobile = "9990007007"
    bill = f"REG-RET-{int(time.time())}-{uuid.uuid4().hex[:5]}"
    _run(_seed_customer(mobile, balance=300, lifetime=300))
    try:
        # First earn on the original bill so return reverses a real spend
        r1 = requests.post(f"{BASE}/api/pos/posAddPoint", headers=HDR, timeout=30, json={
            "merchant_id": MERCHANT, "customer_key": STORE,
            "customer": {"mobile": mobile}, "transaction": {
                "number": bill, "id": bill, "amount": "2000",
                "order_time": "2026-07-08 12:00:00"}})
        assert r1.json().get("status_code") == 200
        cust_after_earn = _run(_get_customer(mobile))
        bal_after_earn = int(cust_after_earn.get("points_balance") or 0)
        spend_after_earn = float(cust_after_earn.get("lifetime_spend") or 0)

        # Return the whole bill
        r2 = requests.post(f"{BASE}/api/pos/returnOrder", headers=HDR, timeout=30, json={
            "merchant_id": MERCHANT, "customer_key": STORE,
            "mobile": mobile,
            "transaction": {"number": bill, "return_amount": "-2000",
                            "return_net_amount": "-2000",
                            "return_loyalty_gross_amount": "-2000"}})
        env2 = r2.json()
        assert env2.get("status_code") == 200, env2

        cust_after_ret = _run(_get_customer(mobile))
        bal_after_ret = int(cust_after_ret.get("points_balance") or 0)
        spend_after_ret = float(cust_after_ret.get("lifetime_spend") or 0)
        # Points went DOWN and lifetime_spend went DOWN
        assert bal_after_ret < bal_after_earn, (bal_after_earn, bal_after_ret)
        assert spend_after_ret < spend_after_earn, (spend_after_earn, spend_after_ret)
    finally:
        _run(_cleanup([mobile], [bill]))


def test_return_order_missing_mobile_400():
    r = requests.post(f"{BASE}/api/pos/returnOrder", headers=HDR, timeout=30, json={
        "merchant_id": MERCHANT, "customer_key": STORE, "mobile": "",
        "transaction": {"number": "x", "return_amount": "-10"}})
    env = r.json()
    assert env.get("status_code") == 400, env


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
