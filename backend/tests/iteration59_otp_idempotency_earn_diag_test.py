"""Iteration 59 — POS OTP idempotency + earn diagnostics + registration event.

Covers the production-blocker fixes:
  1. posRedeemPointOtpCheck is IDEMPOTENT — a retry/double-submit returns 200
     (already_redeemed) and does NOT deduct points twice; a bogus OTP is still
     "Invalid OTP."; an unrelated OTP still rejected.
  2. posAddPoint records an `earn_skip_reason` whenever a bill earns 0 points
     (below_min_bill / zero_base / loyalty_flag_off) so the API Monitor self-diagnoses.
  3. posAddCustomer (new member) succeeds and the "registration" event is a wired
     trigger (so a configured welcome SMS can fire).

Run: pytest -q backend/tests/iteration59_otp_idempotency_earn_diag_test.py
Hits the running backend on localhost:8001 with the seeded KAZO POS credential.
Creates + cleans up its own test customer/bills.
"""
import os
import asyncio
import random
import httpx
import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

BASE = "http://localhost:8001/api/pos"
KEY = "ZFQWql7I3vCH0ckuWmA8zVKDDJWYPBtoQGLruEnRrFI"
MERCHANT = "KAZO_FUNDLE"
HEAD = {"x-api-key": KEY, "Content-Type": "application/json"}


async def _provisioned_store_code(db):
    s = await db["stores"].find_one({"pos_merchant_id": MERCHANT}, {"_id": 0, "code": 1})
    return s["code"] if s else None


def test_otp_idempotency_and_earn_diag_and_registration():
    asyncio.run(_run())


async def _run():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    ck = await _provisioned_store_code(db)
    assert ck, "no provisioned store to test against"
    mobile = f"9777{random.randint(100000, 999999)}"

    async with httpx.AsyncClient(timeout=30.0) as cli:
        # ---- registration: new member ----
        r = await cli.post(f"{BASE}/posAddCustomer", headers=HEAD, json={
            "merchant_id": MERCHANT, "customer_key": ck,
            "customer": {"mobile": mobile, "name": "Iter59 Tester", "city": "Delhi"}})
        assert r.json()["status_code"] == 200
        assert "registered" in r.json()["response"]["message"].lower()

        # ---- earn happy path: give the customer points to redeem ----
        r = await cli.post(f"{BASE}/posAddPoint", headers=HEAD, json={
            "merchant_id": MERCHANT, "customer_key": ck,
            "customer": {"mobile": mobile},
            "transaction": {"number": "IT59-EARN", "amount": 1000, "loyalty_flag": "1"}})
        body = r.json()["response"]
        assert body["points_earned"] > 0, body
        assert "earn_skip_reason" not in body

        # ---- earn diag: below min bill ----
        r = await cli.post(f"{BASE}/posAddPoint", headers=HEAD, json={
            "merchant_id": MERCHANT, "customer_key": ck,
            "customer": {"mobile": mobile},
            "transaction": {"number": "IT59-LOW", "amount": 10, "loyalty_flag": "1"}})
        body = r.json()["response"]
        assert body["points_earned"] == 0
        assert "below_min_bill" in body.get("earn_skip_reason", "")

        # ---- earn diag: zero base (no amount) ----
        r = await cli.post(f"{BASE}/posAddPoint", headers=HEAD, json={
            "merchant_id": MERCHANT, "customer_key": ck,
            "customer": {"mobile": mobile},
            "transaction": {"number": "IT59-ZERO", "loyalty_flag": "1"}})
        assert "zero_base" in r.json()["response"].get("earn_skip_reason", "")

        # ---- earn diag: loyalty flag off ----
        r = await cli.post(f"{BASE}/posAddPoint", headers=HEAD, json={
            "merchant_id": MERCHANT, "customer_key": ck,
            "customer": {"mobile": mobile},
            "transaction": {"number": "IT59-FLAG", "amount": 1000, "loyalty_flag": "0"}})
        assert "loyalty_flag_off" in r.json()["response"].get("earn_skip_reason", "")

        # ---- balance before redemption ----
        cust = await db["customers"].find_one({"mobile": mobile}, {"_id": 0, "points_balance": 1})
        bal0 = int(cust["points_balance"])
        assert bal0 >= 30

        # ---- redeem request -> OTP ----
        r = await cli.post(f"{BASE}/posRedeemPointRequest", headers=HEAD, json={
            "merchant_id": MERCHANT, "customer_key": ck, "customer_mobile": mobile,
            "points": 30, "transaction": {"number": "IT59-RDM"}})
        otp = r.json()["response"]["otp_demo"]

        # ---- verify #1: deducts ----
        r = await cli.post(f"{BASE}/posRedeemPointOtpCheck", headers=HEAD, json={
            "merchant_id": MERCHANT, "customer_key": ck, "customer_mobile": mobile,
            "otp": otp, "points": 30, "transaction": {"number": "IT59-RDM"}})
        assert r.json()["status_code"] == 200
        cust = await db["customers"].find_one({"mobile": mobile}, {"_id": 0, "points_balance": 1})
        bal1 = int(cust["points_balance"])
        assert bal1 == bal0 - 30, (bal0, bal1)

        # ---- verify #2 RETRY same OTP: idempotent, NO double-deduct ----
        r = await cli.post(f"{BASE}/posRedeemPointOtpCheck", headers=HEAD, json={
            "merchant_id": MERCHANT, "customer_key": ck, "customer_mobile": mobile,
            "otp": otp, "points": 30, "transaction": {"number": "IT59-RDM"}})
        assert r.json()["status_code"] == 200
        assert r.json()["response"].get("already_redeemed") is True
        cust = await db["customers"].find_one({"mobile": mobile}, {"_id": 0, "points_balance": 1})
        assert int(cust["points_balance"]) == bal1, "retry must NOT deduct again"

        # ---- bogus OTP still Invalid ----
        r = await cli.post(f"{BASE}/posRedeemPointOtpCheck", headers=HEAD, json={
            "merchant_id": MERCHANT, "customer_key": ck, "customer_mobile": mobile,
            "otp": "000111", "points": 30, "transaction": {"number": "IT59-RDM"}})
        assert r.json()["status_code"] == 400
        assert "Invalid" in r.json()["response"]["message"]

    # ---- registration event is a wired trigger ----
    from routes.communications_routes import EVENTS
    assert "registration" in EVENTS

    # ---- cleanup ----
    await db["customers"].delete_one({"mobile": mobile})
    await db["transactions"].delete_many({"bill_number": {"$in": ["IT59-EARN", "IT59-LOW", "IT59-ZERO", "IT59-FLAG"]}})
    await db["points_ledger"].delete_many({"customer_mobile": mobile})
    await db["points_ledger"].delete_many({"reference_id": "IT59-RDM"})
    await db["pos_otp_sessions"].delete_many({"mobile": mobile})
