import asyncio, os, time, json
import requests
from dotenv import load_dotenv
load_dotenv()
from motor.motor_asyncio import AsyncIOMotorClient

BASE = os.environ["REACT_APP_BACKEND_URL"] if os.environ.get("REACT_APP_BACKEND_URL") else None
# read from frontend env
if not BASE:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL"):
                BASE = line.split("=",1)[1].strip()
API = BASE.rstrip("/") + "/api/pos"
KEY = "ZFQWql7I3vCH0ckuWmA8zVKDDJWYPBtoQGLruEnRrFI"
HEAD = {"x-api-key": KEY, "Content-Type": "application/json"}
MOBILE = "9812340077"
BILL = "REPRO-BILL-%d" % int(time.time())

def add_point():
    payload = {
        "merchant_id": "KAZO_FUNDLE", "customer_key": "K00055",
        "customer": {"mobile": MOBILE, "name": "Repro Return Test"},
        "transaction": {
            "number": BILL, "amount": 2000, "net_amount": 2000,
            "taxes": [], "order_time": "",
            "items": [{"name": "Dress", "quantity": 1, "total": 2000, "category": "Apparel"}],
            "payment_mode": [{"name": "Cash"}],
        },
    }
    r = requests.post(API + "/posAddPoint", headers=HEAD, json=payload, timeout=60)
    print("ADD_POINT:", r.status_code, r.text[:400])

def do_return():
    payload = {
        "merchant_id": "KAZO_FUNDLE", "customer_key": "K00055",
        "mobile": MOBILE,
        "transaction": {
            "number": BILL,
            "return_amount": -800, "return_net_amount": -800,
            "return_loyalty_gross_amount": -800,
        },
    }
    r = requests.post(API + "/returnOrder", headers=HEAD, json=payload, timeout=60)
    print("RETURN:", r.status_code, r.text[:400])

async def dump(label):
    c = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]
    cust = await db.customers.find_one({"mobile": MOBILE})
    cid = cust.get("id") if cust else None
    print(f"\n===== {label} =====")
    print("CUSTOMER:", {k: cust.get(k) for k in ["mobile","points_balance","lifetime_points_earned","lifetime_spend","visit_count","tier"]} if cust else None)
    txns = await db.transactions.find({"customer_mobile": MOBILE}).sort("bill_date",-1).to_list(20)
    print("TXNS (by customer_mobile):", len(txns))
    for t in txns:
        print("  ", {k: t.get(k) for k in ["bill_number","net_amount","points_earned","is_return","return_marker","commit_status","balance_applied","customer_mobile"]})
    led = await db.points_ledger.find({"$or":[{"customer_mobile": MOBILE},{"customer_id": cid}]}).sort("created_at",-1).to_list(20)
    print("LEDGER (mobile OR id):", len(led))
    for l in led:
        print("  ", {k: l.get(k) for k in ["type","ledger_kind","points","reference_type","bill_number","customer_mobile","customer_id"]})
    # ledger by mobile ONLY (what other reports use)
    led_m = await db.points_ledger.find({"customer_mobile": MOBILE}).to_list(20)
    print("LEDGER by customer_mobile ONLY:", len(led_m))

def cleanup():
    async def _c():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        cust = await db.customers.find_one({"mobile": MOBILE})
        cid = cust.get("id") if cust else None
        await db.transactions.delete_many({"customer_mobile": MOBILE})
        await db.points_ledger.delete_many({"$or":[{"customer_mobile": MOBILE},{"customer_id": cid}]})
        await db.customers.delete_many({"mobile": MOBILE})
        print("CLEANED UP", MOBILE)
    asyncio.run(_c())

if __name__ == "__main__":
    print("BASE:", BASE, "BILL:", BILL)
    add_point()
    asyncio.run(dump("AFTER PURCHASE"))
    do_return()
    asyncio.run(dump("AFTER RETURN"))
    cleanup()
