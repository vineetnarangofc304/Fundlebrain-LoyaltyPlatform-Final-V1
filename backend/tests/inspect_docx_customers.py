import asyncio, os, json
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(Path(__file__).parent.parent / ".env")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]


async def main():
    cli = AsyncIOMotorClient(MONGO_URL)
    db = cli[DB_NAME]

    print("TOTAL txns:", await db.transactions.count_documents({}))
    print("TOTAL customers:", await db.customers.count_documents({}))
    print("RETURN txns:", await db.transactions.count_documents({"is_return": True}))

    # Sample one transaction's full field set
    one = await db.transactions.find_one({}, {"_id": 0})
    print("\nSAMPLE TXN KEYS:", sorted(one.keys()) if one else None)
    if one:
        for k in ["gross_amount", "net_amount", "net_amount_before_tax", "tax_amount",
                  "discount_amount", "discount", "amount", "bill_with_tax", "is_return"]:
            print(f"  {k} = {one.get(k)}")

    # Find a customer with many bills including a return
    pipe = [
        {"$group": {"_id": "$customer_mobile",
                    "n": {"$sum": 1},
                    "ret": {"$sum": {"$cond": [{"$eq": ["$is_return", True]}, 1, 0]}}}},
        {"$match": {"_id": {"$nin": [None, ""]}, "n": {"$gte": 3}, "ret": {"$gte": 1}}},
        {"$limit": 3},
    ]
    cands = await db.transactions.aggregate(pipe).to_list(3)
    print("\nCANDIDATES (multi-bill w/ returns):", json.dumps(cands, default=str))

    for cand in cands:
        mob = cand["_id"]
        print("=" * 70)
        print("MOBILE", mob, "bills", cand["n"], "returns", cand["ret"])
        cust = await db.customers.find_one({"mobile": mob}, {"_id": 0, "name": 1, "visit_count": 1, "lifetime_spend": 1, "last_visit_at": 1})
        print("CUSTOMER:", json.dumps(cust, default=str))
        rows = await db.transactions.find({"customer_mobile": mob}, {
            "_id": 0, "bill_number": 1, "bill_date": 1, "is_return": 1,
            "gross_amount": 1, "net_amount": 1, "net_amount_before_tax": 1,
            "tax_amount": 1, "discount_amount": 1,
        }).sort("bill_date", -1).limit(12).to_list(12)
        for r in rows:
            print(json.dumps(r, default=str))
    cli.close()


asyncio.run(main())
