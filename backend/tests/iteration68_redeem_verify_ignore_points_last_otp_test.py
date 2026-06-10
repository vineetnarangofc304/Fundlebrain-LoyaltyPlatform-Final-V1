"""Iteration 68 — posRedeemPointOtpCheck ignores the `points` field & validates the LAST OTP.

Client requirement (from a live API-monitor 400):
- The eWards POS sends `points: "0"` on posRedeemPointOtpCheck because the redemption amount
  was already fixed at posRedeemPointRequest. We must NOT reject this as a "Redemption amount
  mismatch" — the authoritative amount is what the OTP was ISSUED for (snapshot.points).
- We must validate against the LAST OTP issued for the mobile: once a newer OTP is requested,
  an older OTP value is no longer accepted.

Run: pytest -q backend/tests/iteration68_redeem_verify_ignore_points_last_otp_test.py
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
MOBILE = "9123408888"


def test_verify_ignores_points_and_validates_last_otp():
    asyncio.run(_run())


async def _run():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    store = await db["stores"].find_one({"pos_merchant_id": MERCHANT}, {"_id": 0, "code": 1})
    ck = store["code"]

    await db["customers"].delete_many({"mobile": MOBILE})
    await db["customers"].insert_one({
        "id": "iter68cust", "mobile": MOBILE, "name": "Iter68",
        "points_balance": 1000, "lifetime_points_earned": 1000, "lifetime_points_redeemed": 0,
        "lifetime_spend": 50000, "tier": "", "source": "test_iter68",
    })

    async def req(points, bill):
        r = await cli.post(f"{BASE}/posRedeemPointRequest", headers=HEAD, json={
            "merchant_id": MERCHANT, "customer_key": ck, "customer_mobile": MOBILE,
            "points": points, "transaction": {"number": bill}})
        return r.json()["response"].get("otp_demo")

    async def verify(otp, bill, points="0"):
        return await cli.post(f"{BASE}/posRedeemPointOtpCheck", headers=HEAD, json={
            "merchant_id": MERCHANT, "customer_key": ck, "customer_mobile": "91" + MOBILE,
            "country_code": "91", "otp": otp, "points": points,
            "transaction": {"number": bill}})

    async with httpx.AsyncClient(timeout=30.0) as cli:
        # 1) Request 250, verify with points="0" -> success, deduct 250 (not 0, not rejected).
        otp = await req(250, "IT68-1")
        r = await verify(otp, "IT68-1", points="0")
        body = r.json()
        assert body["status_code"] == 200, body
        assert body["response"]["points_value"] == "250", body

        # 2) Validate LAST OTP: issue A then B; A must now be Invalid, B succeeds for 30.
        otp_a = await req(50, "IT68-A")
        otp_b = await req(30, "IT68-B")
        ra = await verify(otp_a, "IT68-A")
        assert ra.json()["status_code"] == 400 and ra.json()["response"]["message"] == "Invalid OTP.", ra.json()
        rb = await verify(otp_b, "IT68-B")
        assert rb.json()["status_code"] == 200 and rb.json()["response"]["points_value"] == "30", rb.json()

    # balance: 1000 - 250 - 30 = 720
    cust = await db["customers"].find_one({"mobile": MOBILE}, {"_id": 0, "points_balance": 1})
    assert cust["points_balance"] == 720, cust

    # cleanup
    await db["customers"].delete_many({"mobile": MOBILE})
    await db["pos_otp_sessions"].delete_many({"mobile": MOBILE})
    await db["points_ledger"].delete_many({"customer_id": "iter68cust"})
    await db["api_logs"].delete_many({"customer_mobile": {"$in": [MOBILE, "91" + MOBILE]}})
