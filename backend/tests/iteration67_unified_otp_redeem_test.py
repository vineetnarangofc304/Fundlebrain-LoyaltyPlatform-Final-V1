"""Iteration 67 — Unified POS OTP collection across BOTH redeem implementations.

Root cause of the recurring production "Invalid OTP": there were TWO POS redemption
implementations writing OTPs to two DIFFERENT Mongo collections —
  - eWards (x-api-key) flow  -> `pos_otp_sessions`
  - legacy /pos/* flow       -> `otps`
so an OTP issued by one could never be verified by the other (permanent "Invalid OTP").

Fix: the legacy `/pos/issue-otp` + `/pos/redeem-points` now read/write the SAME
`pos_otp_sessions` collection with the same last-10-digit mobile normalisation and the
same diagnostic reasons. This test proves both cross-flow directions now succeed.

Run: pytest -q backend/tests/iteration67_unified_otp_redeem_test.py
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
MOBILE = "9123407777"


def test_unified_otp_cross_flow():
    asyncio.run(_run())


async def _run():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    store = await db["stores"].find_one({"pos_merchant_id": MERCHANT}, {"_id": 0, "code": 1})
    ck = store["code"]

    await db["customers"].delete_many({"mobile": MOBILE})
    await db["customers"].insert_one({
        "id": "iter67cust", "mobile": MOBILE, "name": "Iter67",
        "points_balance": 500, "lifetime_points_earned": 500, "lifetime_points_redeemed": 0,
        "lifetime_spend": 5000, "tier": "", "source": "test_iter67",
    })

    async with httpx.AsyncClient(timeout=30.0) as cli:
        # CROSS-FLOW A: OTP issued by eWards posRedeemPointRequest, verified by LEGACY
        # /pos/redeem-points with a country-code-prefixed mobile (format mismatch).
        r = await cli.post(f"{BASE}/posRedeemPointRequest", headers=HEAD, json={
            "merchant_id": MERCHANT, "customer_key": ck, "customer_mobile": MOBILE,
            "points": 10, "transaction": {"number": "IT67-A"}})
        otp_a = r.json()["response"].get("otp_demo")
        assert otp_a, "otp_demo not returned"
        r = await cli.post(f"{BASE}/redeem-points", json={
            "mobile": "+91 " + MOBILE, "points": 10, "otp": otp_a, "bill_number": "IT67-A"})
        assert r.status_code == 200 and r.json().get("success") is True, r.text

        # CROSS-FLOW B: OTP issued by LEGACY /pos/issue-otp, verified by eWards check.
        r = await cli.post(f"{BASE}/issue-otp", json={"mobile": MOBILE, "purpose": "redeem"})
        otp_b = r.json().get("demo_otp")
        assert otp_b, "legacy issue-otp did not return demo_otp"
        r = await cli.post(f"{BASE}/posRedeemPointOtpCheck", headers=HEAD, json={
            "merchant_id": MERCHANT, "customer_key": ck, "customer_mobile": MOBILE,
            "points": 10, "otp": otp_b, "transaction": {"number": "IT67-B"}})
        assert r.json()["status_code"] == 200, r.json()

        # NEGATIVE: a wrong OTP on the legacy endpoint returns a PRECISE diagnostic
        # (not a bare "Invalid OTP").
        await cli.post(f"{BASE}/issue-otp", json={"mobile": MOBILE, "purpose": "redeem"})
        r = await cli.post(f"{BASE}/redeem-points", json={
            "mobile": MOBILE, "points": 10, "otp": "000000", "bill_number": "IT67-N"})
        assert r.status_code == 401
        assert "OTP value mismatch" in r.json()["detail"], r.json()

    # balance went 500 -> 490 (A) -> 480 (B)
    cust = await db["customers"].find_one({"mobile": MOBILE}, {"_id": 0, "points_balance": 1})
    assert cust["points_balance"] == 480, cust

    # cleanup
    await db["customers"].delete_many({"mobile": MOBILE})
    await db["pos_otp_sessions"].delete_many({"mobile": MOBILE})
    await db["points_ledger"].delete_many({"customer_id": "iter67cust"})
    await db["api_logs"].delete_many({"customer_mobile": {"$in": [MOBILE, "9123407777"]}})
