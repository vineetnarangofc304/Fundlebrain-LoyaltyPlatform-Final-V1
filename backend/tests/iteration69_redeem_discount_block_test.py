"""Iteration 69 — Redemption blocked on DISCOUNTED bills/items.

KAZO rule: points redemption is allowed ONLY when there is no discount. If the POS sends a
non-zero discount (bill-level `discount` or any line item `discount`/`Discount`), both
posRedeemPointRequest and posRedeemPointOtpCheck must reject with:
    "Redemption is not allowed on discounted items."

Run: pytest -q backend/tests/iteration69_redeem_discount_block_test.py
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
MOBILE = "9123409999"
MSG = "Redemption is not allowed on discounted items."


def test_redemption_blocked_on_discount():
    asyncio.run(_run())


async def _run():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    store = await db["stores"].find_one({"pos_merchant_id": MERCHANT}, {"_id": 0, "code": 1})
    ck = store["code"]
    await db["customers"].delete_many({"mobile": MOBILE})
    await db["customers"].insert_one({
        "id": "iter69cust", "mobile": MOBILE, "name": "Iter69",
        "points_balance": 500, "lifetime_points_earned": 500, "lifetime_points_redeemed": 0,
        "lifetime_spend": 5000, "tier": "", "source": "test_iter69",
    })

    async def req(items, bill, txn_extra=None):
        txn = {"number": bill, "items": items}
        if txn_extra:
            txn.update(txn_extra)
        return await cli.post(f"{BASE}/posRedeemPointRequest", headers=HEAD, json={
            "merchant_id": MERCHANT, "customer_key": ck, "customer_mobile": MOBILE,
            "points": 10, "transaction": txn})

    async with httpx.AsyncClient(timeout=30.0) as cli:
        # 1) No discount -> allowed (OTP issued)
        r = await req([{"name": "A", "Discount": "0.00"}], "IT69-OK")
        assert r.json()["status_code"] == 200 and r.json()["response"].get("otp_demo"), r.json()

        # 2) Item-level discount (capital Discount) -> blocked
        r = await req([{"name": "A", "Discount": "50.00"}], "IT69-ITEM")
        assert r.json()["status_code"] == 400 and r.json()["response"]["message"] == MSG, r.json()

        # 3) Item-level discount (lowercase discount) -> blocked
        r = await req([{"name": "A", "discount": "5"}], "IT69-ITEM2")
        assert r.json()["status_code"] == 400 and r.json()["response"]["message"] == MSG, r.json()

        # 4) Bill-level discount -> blocked
        r = await req([{"name": "A", "Discount": "0.00"}], "IT69-BILL", {"discount": "100"})
        assert r.json()["status_code"] == 400 and r.json()["response"]["message"] == MSG, r.json()

        # 5) Verify step also blocked when discount present
        r = await cli.post(f"{BASE}/posRedeemPointOtpCheck", headers=HEAD, json={
            "merchant_id": MERCHANT, "customer_key": ck, "customer_mobile": MOBILE,
            "otp": "123456", "points": "0",
            "transaction": {"number": "IT69-ITEM", "items": [{"name": "A", "Discount": "50.00"}]}})
        assert r.json()["status_code"] == 400 and r.json()["response"]["message"] == MSG, r.json()

    await db["customers"].delete_many({"mobile": MOBILE})
    await db["pos_otp_sessions"].delete_many({"mobile": MOBILE})
    await db["api_logs"].delete_many({"customer_mobile": MOBILE})
