"""Iteration 63 — Valid-Indian-mobile gate (Lost Customers) + single global Welcome Bonus.

Client rules locked here:
  1. Points are given ONLY to a VALID Indian mobile (10 digits starting 6-9). A bill with
     an invalid / missing mobile is a NON-LOYALTY "Lost Customer": the bill is STILL recorded
     (for purchase analytics) but earns NO points, creates NO loyalty account, and fires NO SMS.
  2. The single GLOBAL welcome bonus is credited exactly ONCE when a customer first joins
     the programme (their first bill creates them) — never again on later bills/tier moves.

Run: pytest -q backend/tests/iteration63_lost_customer_welcome_bonus_test.py
Hits the running backend on localhost:8001 with the seeded KAZO POS credential.
"""
import os
import asyncio
import random
import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

BASE = "http://localhost:8001/api/pos"
KEY = "ZFQWql7I3vCH0ckuWmA8zVKDDJWYPBtoQGLruEnRrFI"
MERCHANT = "KAZO_FUNDLE"
HEAD = {"x-api-key": KEY, "Content-Type": "application/json"}


async def _store_code(db):
    s = await db["stores"].find_one({"pos_merchant_id": MERCHANT}, {"_id": 0, "code": 1})
    return s["code"] if s else None


def test_lost_customer_and_welcome_bonus():
    asyncio.run(_run())


async def _run():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    ck = await _store_code(db)
    assert ck, "no provisioned store to test against"

    cfg = await db["loyalty_config"].find_one({"id": "default"}, {"_id": 0}) or {}
    welcome = int(float(cfg.get("welcome_bonus", 0) or 0))
    tiers = [t for t in (cfg.get("tier_rules") or []) if t.get("is_active", True)]
    lowest_tier = sorted(tiers, key=lambda t: float(t.get("min_lifetime_spend", 0) or 0))[0]["tier"] if tiers else ""

    good_mobile = f"98{random.randint(10000000, 99999999)}"   # valid: 10 digits, starts 9
    bad_bills = ["IT63-LOST-A", "IT63-LOST-B"]
    good_bills = ["IT63-GOOD-1", "IT63-GOOD-2"]

    async with httpx.AsyncClient(timeout=30.0) as cli:
        # ---------- 1) LOST CUSTOMER: too-short mobile ----------
        r = await cli.post(f"{BASE}/posAddPoint", headers=HEAD, json={
            "merchant_id": MERCHANT, "customer_key": ck,
            "customer": {"mobile": "12345", "name": "Walk In"},
            "transaction": {"number": bad_bills[0], "amount": 2500, "loyalty_flag": "1"}})
        body = r.json()["response"]
        assert r.json()["status_code"] == 200, r.json()
        assert body.get("lost_customer") is True, body
        assert body.get("points_earned") == 0, body
        assert "invalid_or_missing_mobile" in body.get("earn_skip_reason", ""), body
        # bill recorded for analytics, but NON-loyalty
        t = await db["transactions"].find_one({"bill_number": bad_bills[0]}, {"_id": 0})
        assert t and t.get("is_lost_customer") is True
        assert t.get("customer_mobile") is None and t.get("customer_id") is None
        assert t.get("raw_mobile") == "12345"
        assert (t.get("net_amount") or t.get("amount")) == 2500  # purchase value kept
        # NO loyalty account created for the invalid mobile
        assert await db["customers"].find_one({"mobile": "12345"}) is None

        # ---------- LOST CUSTOMER: 10 digits but invalid prefix (starts 5) ----------
        r = await cli.post(f"{BASE}/posAddPoint", headers=HEAD, json={
            "merchant_id": MERCHANT, "customer_key": ck,
            "customer": {"mobile": "5000000000"},
            "transaction": {"number": bad_bills[1], "amount": 999, "loyalty_flag": "1"}})
        assert r.json()["response"].get("lost_customer") is True, r.json()

        # ---------- 2) WELCOME BONUS on a brand-new customer's FIRST bill ----------
        r = await cli.post(f"{BASE}/posAddPoint", headers=HEAD, json={
            "merchant_id": MERCHANT, "customer_key": ck,
            "customer": {"mobile": good_mobile, "name": "Iter63 New"},
            "transaction": {"number": good_bills[0], "amount": 1000, "loyalty_flag": "1"}})
        body = r.json()["response"]
        assert r.json()["status_code"] == 200, r.json()
        earned1 = int(body["points_earned"])
        assert earned1 > 0, body
        cust = await db["customers"].find_one({"mobile": good_mobile}, {"_id": 0})
        assert cust is not None
        # tier comes from configured rules (NOT hardcoded "silver" unless that's configured)
        if lowest_tier:
            assert cust["tier"] in {t["tier"] for t in tiers}, cust["tier"]
        # welcome bonus credited exactly once
        assert cust.get("welcome_bonus_given") is (welcome > 0)
        assert int(cust["points_balance"]) == earned1 + welcome, (cust["points_balance"], earned1, welcome)
        assert int(cust["lifetime_points_earned"]) == earned1 + welcome
        if welcome > 0:
            wl = await db["points_ledger"].find_one({"customer_mobile": good_mobile, "reference_type": "welcome"})
            assert wl and int(wl["points"]) == welcome, wl

        # ---------- 3) SECOND bill -> NO second welcome bonus ----------
        bal1 = int(cust["points_balance"])
        r = await cli.post(f"{BASE}/posAddPoint", headers=HEAD, json={
            "merchant_id": MERCHANT, "customer_key": ck,
            "customer": {"mobile": good_mobile},
            "transaction": {"number": good_bills[1], "amount": 1000, "loyalty_flag": "1"}})
        earned2 = int(r.json()["response"]["points_earned"])
        cust2 = await db["customers"].find_one({"mobile": good_mobile}, {"_id": 0})
        assert int(cust2["points_balance"]) == bal1 + earned2, (bal1, earned2, cust2["points_balance"])
        # only ONE welcome ledger entry ever
        assert await db["points_ledger"].count_documents(
            {"customer_mobile": good_mobile, "reference_type": "welcome"}) == (1 if welcome > 0 else 0)

    # ---------- cleanup ----------
    await db["customers"].delete_one({"mobile": good_mobile})
    await db["points_ledger"].delete_many({"customer_mobile": good_mobile})
    await db["transactions"].delete_many({"bill_number": {"$in": bad_bills + good_bills}})
