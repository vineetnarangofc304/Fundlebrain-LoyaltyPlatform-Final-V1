import asyncio, os
from dotenv import load_dotenv
load_dotenv()
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone
import uuid

MOB = "9700000091"

async def main():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"]); db = c[os.environ["DB_NAME"]]
    # master user
    u = await db.users.find_one({"email": "masteradmin@fundle.io"}, {"_id": 0})
    user = {"id": u.get("id"), "email": u.get("email"), "role": u.get("role"),
            "is_master_admin": True}
    # seed customer
    await db.customers.delete_many({"mobile": MOB})
    await db.points_ledger.delete_many({"customer_mobile": MOB})
    cid = uuid.uuid4().hex
    await db.customers.insert_one({"id": cid, "mobile": MOB, "name": "TopUp Undo Test",
        "points_balance": 100, "lifetime_points_earned": 100, "lifetime_points_redeemed": 0,
        "tier": "silver", "created_at": datetime.now(timezone.utc).isoformat()})

    from routes.master_brain_tools import _tool_adjust_points, _tool_grant_bonus_points, _tool_undo_action

    async def bal():
        d = await db.customers.find_one({"mobile": MOB}); return d.get("points_balance")

    print("start balance:", await bal(), "(expect 100)")
    # ADJUST -30
    r = await _tool_adjust_points(mobile=MOB, points=-30, reason="QA adjust", confirm=True, user=user)
    print("adjust applied:", r.get("applied"), "audit:", r.get("audit_id"), "-> balance:", await bal(), "(expect 70)")
    adj_audit = r.get("audit_id")
    # GRANT +50 (like a top-up/award)
    r2 = await _tool_grant_bonus_points(mobile=MOB, points=50, reason="QA topup", confirm=True, user=user)
    print("grant applied:", r2.get("applied"), "audit:", r2.get("audit_id"), "-> balance:", await bal(), "(expect 120)")
    grant_audit = r2.get("audit_id")
    # UNDO grant (reverse order)
    r3 = await _tool_undo_action(audit_id=grant_audit, reason="undo topup", confirm=True, user=user)
    print("undo grant:", r3.get("applied"), "-> balance:", await bal(), "(expect 70)")
    # UNDO adjust
    r4 = await _tool_undo_action(audit_id=adj_audit, reason="undo adjust", confirm=True, user=user)
    print("undo adjust:", r4.get("applied"), "-> balance:", await bal(), "(expect 100 = fully restored)")
    finald = await db.customers.find_one({"mobile": MOB})
    print("final lifetime_earned:", finald.get("lifetime_points_earned"), "(expect 100)")
    # cleanup
    await db.customers.delete_many({"mobile": MOB})
    await db.points_ledger.delete_many({"customer_mobile": MOB})
    print("CLEANED UP")

if __name__ == "__main__":
    asyncio.run(main())
