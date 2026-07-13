import asyncio, os, uuid
import requests
from dotenv import load_dotenv
load_dotenv()
from motor.motor_asyncio import AsyncIOMotorClient

with open("/app/frontend/.env") as f:
    for line in f:
        if line.startswith("REACT_APP_BACKEND_URL"):
            BASE = line.split("=", 1)[1].strip()
API = BASE.rstrip("/") + "/api"

C1 = "9700000011"  # duplicate-redemption case: earn 100, redeem -80 x2 -> bal -60, true 20
C2 = "9700000012"  # genuine over-redemption: earn 50, redeem -70 -> bal -20, true 0

def now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

async def seed():
    c = AsyncIOMotorClient(os.environ["MONGO_URL"]); db = c[os.environ["DB_NAME"]]
    for mob, bal in [(C1, -60), (C2, -20)]:
        await db.customers.delete_many({"mobile": mob})
        await db.points_ledger.delete_many({"customer_mobile": mob})
    id1 = uuid.uuid4().hex; id2 = uuid.uuid4().hex
    await db.customers.insert_one({"id": id1, "mobile": C1, "name": "Dup Redeem", "points_balance": -60,
        "lifetime_points_earned": 100, "lifetime_points_redeemed": 160, "tier": "silver", "created_at": now()})
    await db.customers.insert_one({"id": id2, "mobile": C2, "name": "Over Redeem", "points_balance": -20,
        "lifetime_points_earned": 50, "lifetime_points_redeemed": 70, "tier": "silver", "created_at": now()})
    # C1 ledger: +100 earn, two identical -80 redeems on same bill (one is a duplicate)
    await db.points_ledger.insert_many([
        {"id": uuid.uuid4().hex, "customer_mobile": C1, "customer_id": id1, "points": 100, "type": "earn",
         "reference_type": "transaction", "bill_number": "B1", "created_at": now()},
        {"id": uuid.uuid4().hex, "customer_mobile": C1, "customer_id": id1, "points": -80, "type": "redeem",
         "reference_type": "redemption", "bill_number": "R1", "reference_id": "R1", "created_at": now()},
        {"id": uuid.uuid4().hex, "customer_mobile": C1, "customer_id": id1, "points": -80, "type": "redeem",
         "reference_type": "redemption", "bill_number": "R1", "reference_id": "R1", "created_at": now()},
    ])
    # C2 ledger: +50 earn, single -70 redeem (no duplicate)
    await db.points_ledger.insert_many([
        {"id": uuid.uuid4().hex, "customer_mobile": C2, "customer_id": id2, "points": 50, "type": "earn",
         "reference_type": "transaction", "bill_number": "B2", "created_at": now()},
        {"id": uuid.uuid4().hex, "customer_mobile": C2, "customer_id": id2, "points": -70, "type": "redeem",
         "reference_type": "redemption", "bill_number": "R2", "reference_id": "R2", "created_at": now()},
    ])
    print("SEEDED", C1, C2)

def token():
    r = requests.post(API + "/auth/login", json={"email": "masteradmin@fundle.io", "password": "Master@2026"}, timeout=30)
    return r.json().get("token")

async def bal(db, mob):
    c = await db.customers.find_one({"mobile": mob}); return c.get("points_balance") if c else None

async def main():
    await seed()
    tk = token(); H = {"Authorization": f"Bearer {tk}"}
    print("TOKEN len", len(tk or ""))
    # Preview C1
    r = requests.post(API + "/points-integrity/negative-balances/preview", headers=H, json={"mobile": C1}, timeout=60)
    print("PREVIEW C1:", r.status_code, r.json())
    # Apply C1
    r = requests.post(API + "/points-integrity/negative-balances/apply", headers=H, json={"mobile": C1, "reason": "QA true-value test"}, timeout=60)
    print("APPLY C1:", r.status_code, r.json())
    # Preview + Apply C2
    r = requests.post(API + "/points-integrity/negative-balances/preview", headers=H, json={"mobile": C2}, timeout=60)
    print("PREVIEW C2:", r.status_code, r.json())
    r = requests.post(API + "/points-integrity/negative-balances/apply", headers=H, json={"mobile": C2, "reason": "QA over-redeem floor"}, timeout=60)
    print("APPLY C2:", r.status_code, r.json())
    c = AsyncIOMotorClient(os.environ["MONGO_URL"]); db = c[os.environ["DB_NAME"]]
    print("FINAL BALANCES -> C1:", await bal(db, C1), "(expect 20)  C2:", await bal(db, C2), "(expect 0)")
    # cleanup
    for mob in (C1, C2):
        await db.customers.delete_many({"mobile": mob})
        await db.points_ledger.delete_many({"customer_mobile": mob})
    print("CLEANED UP")

if __name__ == "__main__":
    asyncio.run(main())
