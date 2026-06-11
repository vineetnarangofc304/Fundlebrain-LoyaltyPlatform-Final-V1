"""Seed production-scale synthetic data (tagged perf_seed=True) to reproduce
production-scale dashboard performance locally. PURGE after testing with:
  python3 seed_perf_data.py purge
"""
import asyncio, os, random, sys, uuid
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import BulkWriteError
from dotenv import load_dotenv


async def safe_insert(col, docs):
    try:
        await col.insert_many(docs, ordered=False)
    except BulkWriteError:
        pass  # ignore duplicate keys against pre-existing test data

load_dotenv("/app/backend/.env")
client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

N_CUSTOMERS = 800_000
N_TXNS = 1_500_000
BATCH = 5000

CITIES = ["Mumbai", "Delhi", "Bengaluru", "Hyderabad", "Pune", "Chennai", "Kolkata",
          "Ahmedabad", "Jaipur", "Lucknow", "Chandigarh", "Indore", "Surat", "Noida", "Gurugram"]
TIERS = ["silver", "gold", "platinum"]
NOW = datetime(2026, 6, 11, tzinfo=timezone.utc)
EPOCH_START = datetime(2019, 1, 1, tzinfo=timezone.utc)
SPAN_DAYS = (NOW - EPOCH_START).days


def rand_date():
    # Weight towards recent years slightly
    f = random.random() ** 0.7
    return EPOCH_START + timedelta(days=f * SPAN_DAYS, hours=random.randint(9, 21), minutes=random.randint(0, 59))


async def seed_stores():
    stores = []
    for i in range(50):
        stores.append({
            "id": f"perfstore{i:03d}", "code": f"PERF{i:03d}", "name": f"KAZO Perf Store {i:03d}",
            "city": random.choice(CITIES), "state": "NA", "zone": random.choice(["North", "South", "East", "West"]),
            "region": random.choice(["North", "South", "East", "West"]),
            "is_active": True, "perf_seed": True, "pos_merchant_id": "PERF",
            "created_at": EPOCH_START.isoformat(),
        })
    await db.stores.insert_many(stores)
    return [s["id"] for s in stores]


async def seed_customers():
    docs = []
    inserted = 0
    for i in range(N_CUSTOMERS):
        mob = f"9{random.randint(100000000, 999999999)}{i % 10}"[:10]
        mob = f"9{i:09d}"  # guaranteed unique 10-digit starting 9
        first = rand_date()
        visits = max(1, int(random.expovariate(0.8)) + (1 if random.random() < 0.35 else 0))
        spend = round(random.uniform(500, 4000) * visits, 2)
        last = first + timedelta(days=random.randint(0, max(1, (NOW - first).days)))
        docs.append({
            "id": uuid.uuid4().hex, "mobile": mob, "name": f"Perf Customer {i}",
            "city": random.choice(CITIES), "state": "NA",
            "tier": random.choices(TIERS, weights=[70, 22, 8])[0],
            "visit_count": visits, "lifetime_spend": spend,
            "points_balance": random.randint(0, 5000),
            "lifetime_points_earned": int(spend), "lifetime_points_redeemed": random.randint(0, 500),
            "first_purchase_at": first.isoformat(), "last_visit_at": last.isoformat(),
            "home_store_id": f"perfstore{random.randint(0, 49):03d}",
            "created_at": first.isoformat(), "source": "perf_seed", "perf_seed": True,
            "churn_risk": random.choices(["low", "medium", "high"], weights=[60, 25, 15])[0],
            "is_active": True,
        })
        if len(docs) >= BATCH:
            await safe_insert(db.customers, docs)
            inserted += len(docs)
            docs = []
            if inserted % 100000 == 0:
                print(f"customers: {inserted}", flush=True)
    if docs:
        await safe_insert(db.customers, docs)
        inserted += len(docs)
    print(f"customers done: {inserted}", flush=True)


async def seed_txns():
    docs = []
    ledger = []
    inserted = 0
    for i in range(N_TXNS):
        mob = f"9{random.randint(0, N_CUSTOMERS - 1):09d}"
        dt = rand_date()
        net = round(random.uniform(400, 9000), 2)
        sid = f"perfstore{random.randint(0, 49):03d}"
        has_mobile = random.random() > 0.04  # ~4% lost customers
        tx = {
            "id": uuid.uuid4().hex,
            "bill_number": f"PERF-{i:08d}",
            "bill_date": dt.isoformat(),
            "customer_mobile": mob if has_mobile else None,
            "store_id": sid,
            "city": random.choice(CITIES),
            "net_amount": net, "gross_amount": round(net * 1.05, 2),
            "discount_amount": round(net * random.choice([0, 0, 0, 0.05, 0.1]), 2),
            "points_earned": int(net) if has_mobile else 0,
            "points_redeemed": 0,
            "payment_mode": random.choice(["card", "upi", "cash", None]),
            "items": [{"sku": f"SKU{random.randint(1, 500):04d}", "name": f"Item {random.randint(1, 500)}",
                       "category": random.choice(["Dresses", "Tops", "Bottoms", "Accessories", ""]),
                       "quantity": random.randint(1, 3), "total": net}] if random.random() < 0.6 else [],
            "source": "perf_seed", "perf_seed": True,
            "is_lost_customer": not has_mobile,
            "created_at": dt.isoformat(),
        }
        docs.append(tx)
        if has_mobile:
            ledger.append({
                "id": uuid.uuid4().hex, "customer_mobile": mob, "type": "earn",
                "points": int(net), "bill_number": tx["bill_number"], "bill_date": tx["bill_date"],
                "created_at": tx["bill_date"], "reference_type": "bill", "perf_seed": True,
                "expires_at": (dt + timedelta(days=365)).isoformat(),
            })
            if random.random() < 0.05:
                ledger.append({
                    "id": uuid.uuid4().hex, "customer_mobile": mob, "type": "redeem",
                    "points": -random.randint(50, 800), "bill_number": tx["bill_number"],
                    "bill_date": tx["bill_date"], "created_at": tx["bill_date"],
                    "reference_type": "bill", "perf_seed": True,
                })
        if len(docs) >= BATCH:
            await safe_insert(db.transactions, docs)
            if ledger:
                await safe_insert(db.points_ledger, ledger)
            inserted += len(docs)
            docs, ledger = [], []
            if inserted % 100000 == 0:
                print(f"txns: {inserted}", flush=True)
    if docs:
        await safe_insert(db.transactions, docs)
    if ledger:
        await safe_insert(db.points_ledger, ledger)
    print(f"txns done", flush=True)


async def purge():
    for col in ["customers", "transactions", "points_ledger", "stores"]:
        r = await db[col].delete_many({"perf_seed": True})
        print(f"purged {col}: {r.deleted_count}", flush=True)


async def main():
    if len(sys.argv) > 1 and sys.argv[1] == "purge":
        await purge()
        return
    print("seeding stores...", flush=True)
    await seed_stores()
    print("seeding customers...", flush=True)
    await seed_customers()
    print("seeding transactions...", flush=True)
    await seed_txns()
    print("ALL DONE", flush=True)


asyncio.run(main())
