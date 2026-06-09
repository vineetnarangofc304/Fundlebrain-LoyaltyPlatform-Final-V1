"""Iteration 66 — POS OTP redemption is tolerant of mobile formatting + self-diagnoses.

Root cause of the recurring production "Invalid OTP" / "This number is not registered":
the customer lookup AND the OTP lookup matched the mobile EXACTLY, so a POS that sent the
mobile with a country code / leading 0 / separators never matched the stored 10-digit form.
Now both use a canonical last-10-digit key, and a real OTP-value mismatch logs the exact
reason in the API log (error_reason).

Run: pytest -q backend/tests/iteration66_otp_mobile_format_test.py
"""
import os
import asyncio
import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

BASE = "http://localhost:8001/api/pos"
KEY = "ZFQWql7I3vCH0ckuWmA8zVKDDJWYPBtoQGLruEnRrFI"
MERCHANT = "KAZO_FUNDLE"
HEAD = {"x-api-key": KEY, "Content-Type": "application/json"}
MOBILE = "9123406789"   # canonical stored form (valid Indian mobile)


def test_otp_redemption_mobile_format_tolerant():
    asyncio.run(_run())


async def _run():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    store = await db["stores"].find_one({"pos_merchant_id": MERCHANT}, {"_id": 0, "code": 1})
    ck = store["code"]

    # fresh customer with a known balance
    await db["customers"].delete_many({"mobile": MOBILE})
    await db["customers"].insert_one({
        "id": "iter66cust", "mobile": MOBILE, "name": "Iter66",
        "points_balance": 500, "lifetime_points_earned": 500, "lifetime_points_redeemed": 0,
        "lifetime_spend": 5000, "tier": "", "source": "test_iter66",
    })

    async def req_otp(bill):
        r = await cli.post(f"{BASE}/posRedeemPointRequest", headers=HEAD, json={
            "merchant_id": MERCHANT, "customer_key": ck, "customer_mobile": MOBILE,
            "points": 10, "transaction": {"number": bill}})
        return r.json()["response"].get("otp_demo")

    async with httpx.AsyncClient(timeout=30.0) as cli:
        # 1) Request with the canonical mobile, VERIFY with a country-code-prefixed mobile.
        otp = await req_otp("IT66-1")
        assert otp, "otp_demo not returned (POS_RETURN_OTP_IN_RESPONSE must be on in preview)"
        r = await cli.post(f"{BASE}/posRedeemPointOtpCheck", headers=HEAD, json={
            "merchant_id": MERCHANT, "customer_key": ck,
            "customer_mobile": "+91 9123406789",   # different format, same number
            "points": 10, "otp": otp, "transaction": {"number": "IT66-1"}})
        assert r.json()["status_code"] == 200, r.json()

        # 2) Leading-zero format must still FIND the customer (no "not registered").
        otp = await req_otp("IT66-2")
        r = await cli.post(f"{BASE}/posRedeemPointOtpCheck", headers=HEAD, json={
            "merchant_id": MERCHANT, "customer_key": ck,
            "customer_mobile": "09123406789",
            "points": 10, "otp": otp, "transaction": {"number": "IT66-2"}})
        assert r.json()["status_code"] == 200, r.json()

        # 3) A genuinely WRONG otp -> 400 Invalid OTP, and the API log captures the reason.
        await req_otp("IT66-3")
        r = await cli.post(f"{BASE}/posRedeemPointOtpCheck", headers=HEAD, json={
            "merchant_id": MERCHANT, "customer_key": ck, "customer_mobile": MOBILE,
            "points": 10, "otp": "000001", "transaction": {"number": "IT66-3"}})
        assert r.json()["status_code"] == 400
        assert r.json()["response"]["message"] == "Invalid OTP."

    # diagnostic reason recorded
    log = await db["api_logs"].find_one(
        {"endpoint": "/api/pos/posRedeemPointOtpCheck", "status_code": 400,
         "customer_mobile": MOBILE},
        {"_id": 0, "error_reason": 1}, sort=[("timestamp", -1)])
    assert log and log.get("error_reason") and "OTP value mismatch" in log["error_reason"], log

    # cleanup
    await db["customers"].delete_many({"mobile": MOBILE})
    await db["pos_otp_sessions"].delete_many({"mobile": MOBILE})
    await db["pos_otp"].delete_many({"mobile": MOBILE})
    await db["transactions"].delete_many({"bill_number": {"$in": ["IT66-1", "IT66-2", "IT66-3"]}})
    await db["api_logs"].delete_many({"customer_mobile": MOBILE})
