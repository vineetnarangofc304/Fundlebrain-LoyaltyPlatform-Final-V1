import asyncio, os, uuid
from dotenv import load_dotenv
load_dotenv()
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone, timedelta

def iso(dt): return dt.isoformat()
NOW = datetime.now(timezone.utc)

async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"]); db = c[os.environ["DB_NAME"]]
    u = await db.users.find_one({"email": "masteradmin@fundle.io"}, {"_id": 0})
    user = {"id": u.get("id"), "email": u.get("email"), "role": u.get("role"), "is_master_admin": True}
    from routes.master_brain_tools import _tool_reverse_duplicate_bonus_credits as REV

    async def bal(mob):
        d = await db.customers.find_one({"mobile": mob}); return (d.get("points_balance"), d.get("lifetime_points_earned")) if d else None
    async def seed(mob, n_bonus, prior_reversals=0, reason="Top-up campaign"):
        await db.customers.delete_many({"mobile": mob}); await db.points_ledger.delete_many({"customer_mobile": mob})
        cid = uuid.uuid4().hex
        bonus_total = 375 * n_bonus
        bal_now = 125 + bonus_total - prior_reversals * 750
        await db.customers.insert_one({"id": cid, "mobile": mob, "name": "Dup Test",
            "points_balance": bal_now, "lifetime_points_earned": 125 + bonus_total, "lifetime_points_redeemed": 0,
            "tier": "silver", "created_at": iso(NOW)})
        rows = [{"id": uuid.uuid4().hex, "customer_mobile": mob, "customer_id": cid, "points": 125,
                 "type": "bonus", "reference_type": "master_brain", "reason": "Opening", "created_at": iso(NOW - timedelta(days=40))}]
        for i in range(n_bonus):
            rows.append({"id": uuid.uuid4().hex, "customer_mobile": mob, "customer_id": cid, "points": 375,
                         "type": "bonus", "reference_type": "master_brain", "reason": reason,
                         "created_at": iso(NOW - timedelta(days=5, minutes=i))})
        for j in range(prior_reversals):
            rows.append({"id": uuid.uuid4().hex, "customer_mobile": mob, "customer_id": cid, "points": -750,
                         "type": "adjust", "reference_type": "master_brain", "reason": "Reversal of 2 duplicates — earlier",
                         "created_at": iso(NOW - timedelta(days=3, minutes=j))})
        await db.points_ledger.insert_many(rows)

    print("=== CASE A: fresh customer, 3 duplicate top-ups (balance 1250) ===")
    await seed("9700000101", n_bonus=3, prior_reversals=0)
    print(" before:", await bal("9700000101"), "(expect 1250,1375)")
    r1 = await REV(filter_reason="Top-up campaign", confirm=True, reason="fix dupes", user=user)
    print(" run1:", r1.get("message"), "| points_to_reverse", r1.get("total_points_to_reverse"))
    print(" after run1:", await bal("9700000101"), "(expect 500, 625)")
    r2 = await REV(filter_reason="Top-up campaign", confirm=True, reason="fix dupes again", user=user)
    print(" run2 (IDEMPOTENT):", r2.get("message"))
    print(" after run2:", await bal("9700000101"), "(expect STILL 500, 625)")
    r3 = await REV(filter_reason="Top-up campaign", confirm=True, reason="fix dupes 3rd", user=user)
    print(" after run3:", await bal("9700000101"), "(expect STILL 500, 625)")

    print("\n=== CASE B: already OVER-reversed (like 9303632456: 3 bonus + prior reversals) ===")
    await seed("9700000102", n_bonus=3, prior_reversals=2)  # already reversed 1500
    print(" before:", await bal("9700000102"))
    rb = await REV(filter_reason="Top-up campaign", confirm=True, reason="should skip", user=user)
    print(" result:", rb.get("message"))
    print(" after:", await bal("9700000102"), "(must NOT drop further)")

    # cleanup
    for mob in ("9700000101", "9700000102"):
        await db.customers.delete_many({"mobile": mob}); await db.points_ledger.delete_many({"customer_mobile": mob})
    print("\nCLEANED UP")

if __name__ == "__main__":
    asyncio.run(main())
