"""Seed realistic Kazo demo data.
Usage: python seed.py
"""
import asyncio
import os
import random
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv
from faker import Faker

load_dotenv(Path(__file__).parent / ".env")

from database import (
    customers_col, transactions_col, stores_col, campaigns_col, coupons_col,
    points_ledger_col, api_logs_col, nps_col, tickets_col, users_col, loyalty_config_col,
    coupon_redemptions_col,
)
from auth import hash_password

fake = Faker("en_IN")

KAZO_CATEGORIES = [
    ("TOPS", ["Crepe Top", "Satin Blouse", "Crochet Top", "Smocked Top", "Ribbed Tee"]),
    ("DRESSES", ["Bodycon Dress", "Slip Dress", "Wrap Dress", "Maxi Dress", "Mini Dress"]),
    ("JUMPSUITS", ["Wide-Leg Jumpsuit", "Strapless Jumpsuit", "Cargo Jumpsuit"]),
    ("BOTTOMS", ["High-Waist Jeans", "Wide-Leg Trouser", "Pleated Skirt", "Cargo Pants"]),
    ("CO-ORDS", ["Linen Co-ord", "Satin Co-ord", "Printed Co-ord Set"]),
    ("BAGS", ["Sling Bag", "Mini Bag", "Tote Bag", "Clutch", "Crossbody"]),
    ("JEWELLERY", ["Hoop Earrings", "Layered Necklace", "Stack Rings", "Pearl Choker"]),
    ("PERFUMES", ["Eau de Parfum 50ml", "Body Mist 100ml"]),
    ("DENIM", ["Boyfriend Jeans", "Skinny Jeans", "Flared Jeans"]),
    ("PARTY WEAR", ["Sequin Dress", "Bodycon Mini", "Velvet Co-ord"]),
]

CITIES = [
    ("Mumbai", "Maharashtra", "West", 19.0760, 72.8777),
    ("Delhi", "Delhi", "North", 28.7041, 77.1025),
    ("Bangalore", "Karnataka", "South", 12.9716, 77.5946),
    ("Hyderabad", "Telangana", "South", 17.3850, 78.4867),
    ("Pune", "Maharashtra", "West", 18.5204, 73.8567),
    ("Chennai", "Tamil Nadu", "South", 13.0827, 80.2707),
    ("Kolkata", "West Bengal", "East", 22.5726, 88.3639),
    ("Ahmedabad", "Gujarat", "West", 23.0225, 72.5714),
    ("Jaipur", "Rajasthan", "North", 26.9124, 75.7873),
    ("Lucknow", "Uttar Pradesh", "North", 26.8467, 80.9462),
    ("Chandigarh", "Punjab", "North", 30.7333, 76.7794),
    ("Gurugram", "Haryana", "North", 28.4595, 77.0266),
    ("Noida", "Uttar Pradesh", "North", 28.5355, 77.3910),
    ("Indore", "Madhya Pradesh", "West", 22.7196, 75.8577),
    ("Surat", "Gujarat", "West", 21.1702, 72.8311),
]

MALL_NAMES = [
    "Phoenix Marketcity", "Inorbit Mall", "DLF Promenade", "Select Citywalk",
    "Pacific Mall", "Forum Mall", "Lulu Mall", "Express Avenue",
    "Quest Mall", "Ambience Mall", "Elante Mall", "VR Mall",
    "Orion Mall", "Mall of India", "Phoenix Palladium",
]


async def clear_all():
    for col in [customers_col, transactions_col, stores_col, campaigns_col, coupons_col,
                points_ledger_col, api_logs_col, nps_col, tickets_col, coupon_redemptions_col]:
        await col.delete_many({})
    print("Cleared existing data")


async def seed_users():
    # We keep superadmin and brand admin (created at startup). Add demo users.
    # store_user_map maps email -> city of the store they manage
    store_user_map = {
        "store.mumbai@kazo.com": "Mumbai",
        "staff.delhi@kazo.com": "Delhi",
    }
    demo_users = [
        ("crm@kazo.com", "Priya Sharma", "crm_manager"),
        ("marketing@kazo.com", "Rohan Kapoor", "marketing_manager"),
        ("regional.north@kazo.com", "Anjali Verma", "regional_manager"),
        ("store.mumbai@kazo.com", "Neha Patel", "store_manager"),
        ("staff.delhi@kazo.com", "Karan Singh", "store_staff"),
        ("support@kazo.com", "Riya Mehra", "support_agent"),
        ("analytics@kazo.com", "Aditya Rao", "analytics_viewer"),
        ("executive@kazo.com", "Kavita Iyer", "readonly_executive"),
        ("it@kazo.com", "Vikram Joshi", "brand_admin"),
    ]
    for email, name, role in demo_users:
        if await users_col.find_one({"email": email}):
            continue
        doc = {
            "id": uuid.uuid4().hex,
            "email": email,
            "name": name,
            "role": role,
            "password_hash": hash_password("Kazo@2026"),
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if email in store_user_map:
            s = await stores_col.find_one({"city": store_user_map[email], "is_active": True})
            if s:
                doc["store_id"] = s["id"]
        await users_col.insert_one(doc)
    print(f"Seeded {len(demo_users)} demo users")


async def seed_stores():
    stores = []
    for i, (city, state, region, lat, lng) in enumerate(CITIES):
        # 2 stores per major city
        for j in range(2 if i < 10 else 1):
            sid = uuid.uuid4().hex
            mall = random.choice(MALL_NAMES)
            stores.append({
                "id": sid,
                "code": f"KZO-{city[:3].upper()}-{j+1:02d}",
                "name": f"Kazo {city} - {mall}",
                "city": city,
                "state": state,
                "region": region,
                "address": f"Ground Floor, {mall}, {city}",
                "phone": fake.phone_number(),
                "manager_name": fake.name(),
                "latitude": lat + random.uniform(-0.05, 0.05),
                "longitude": lng + random.uniform(-0.05, 0.05),
                "is_active": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
    await stores_col.insert_many(stores)
    print(f"Seeded {len(stores)} stores")
    return stores


async def seed_customers(stores, n=1500):
    customers = []
    for i in range(n):
        city_idx = random.randint(0, len(CITIES) - 1)
        city, state, region, _, _ = CITIES[city_idx]
        store = random.choice([s for s in stores if s["city"] == city])
        first = fake.first_name_female()
        last = fake.last_name()
        cid = uuid.uuid4().hex
        # Realistic spend distribution
        roll = random.random()
        if roll < 0.05:
            lifetime_spend = random.uniform(150000, 400000)  # diamond
            tier = "diamond"
        elif roll < 0.15:
            lifetime_spend = random.uniform(75000, 150000)
            tier = "platinum"
        elif roll < 0.35:
            lifetime_spend = random.uniform(25000, 75000)
            tier = "gold"
        else:
            lifetime_spend = random.uniform(500, 25000)
            tier = "silver"
        visit_count = max(1, int(lifetime_spend / random.uniform(2500, 4500)))
        points_earned = int(lifetime_spend * 1.0)
        points_redeemed = int(points_earned * random.uniform(0.1, 0.5))
        points_balance = max(0, points_earned - points_redeemed)
        days_since_visit = random.choice([random.randint(1, 30)] * 5 + [random.randint(30, 90)] * 2 + [random.randint(90, 400)])
        last_visit = (datetime.now(timezone.utc) - timedelta(days=days_since_visit)).isoformat()
        churn = "low" if days_since_visit < 60 else ("medium" if days_since_visit < 150 else "high")
        favs = random.sample([c[0] for c in KAZO_CATEGORIES], k=random.randint(1, 3))
        created_at = (datetime.now(timezone.utc) - timedelta(days=visit_count * random.randint(15, 60))).isoformat()
        customers.append({
            "id": cid,
            "mobile": f"9{random.randint(100000000, 999999999)}",
            "name": f"{first} {last}",
            "email": f"{first.lower()}.{last.lower()}{random.randint(1,99)}@gmail.com",
            "city": city,
            "state": state,
            "gender": "female",
            "tier": tier,
            "preferred_store_id": store["id"],
            "points_balance": points_balance,
            "lifetime_points_earned": points_earned,
            "lifetime_points_redeemed": points_redeemed,
            "lifetime_spend": round(lifetime_spend, 2),
            "visit_count": visit_count,
            "last_visit_at": last_visit,
            "first_purchase_at": created_at,
            "churn_risk": churn,
            "favourite_categories": favs,
            "birthday": (datetime.now() - timedelta(days=random.randint(365 * 18, 365 * 45))).date().isoformat() if random.random() > 0.4 else None,
            "created_at": created_at,
        })
    # Insert in batches
    for i in range(0, len(customers), 500):
        await customers_col.insert_many(customers[i:i + 500])
    print(f"Seeded {len(customers)} customers")
    return customers


async def seed_transactions(customers, stores, n=8000):
    txns = []
    ledger = []
    now = datetime.now(timezone.utc)
    for i in range(n):
        cust = random.choice(customers)
        store = next((s for s in stores if s["id"] == cust["preferred_store_id"]), random.choice(stores))
        days_ago = random.randint(0, 365)
        bill_date = now - timedelta(days=days_ago, hours=random.randint(0, 12))
        # items
        num_items = random.choices([1, 2, 3, 4, 5], weights=[35, 30, 20, 10, 5])[0]
        items = []
        gross = 0
        for _ in range(num_items):
            cat, products = random.choice(KAZO_CATEGORIES)
            prod = random.choice(products)
            price = random.choice([1290, 1490, 1990, 2490, 2990, 3490, 3990, 4490, 4990, 5990, 7990])
            qty = 1 if random.random() < 0.85 else 2
            total = price * qty
            gross += total
            items.append({
                "sku": f"K{random.randint(10000, 99999)}",
                "name": f"KAZO {prod}",
                "category": cat,
                "quantity": qty,
                "unit_price": price,
                "total": total,
            })
        discount = round(gross * random.uniform(0, 0.25), 2) if random.random() < 0.4 else 0
        net = round(gross - discount, 2)
        points = int(net * 1.0)
        tid = uuid.uuid4().hex
        txns.append({
            "id": tid,
            "customer_id": cust["id"],
            "customer_mobile": cust["mobile"],
            "store_id": store["id"],
            "bill_number": f"KZO/{store['code']}/{bill_date.strftime('%Y%m%d')}/{random.randint(1000, 9999)}",
            "bill_date": bill_date.isoformat(),
            "gross_amount": gross,
            "discount_amount": discount,
            "net_amount": net,
            "items": items,
            "payment_mode": random.choice(["card", "upi", "cash", "wallet"]),
            "points_earned": points,
            "points_redeemed": 0,
            "coupon_code": random.choice([None, None, None, "KAZOWELCOME20"]),
            "created_at": bill_date.isoformat(),
        })
        ledger.append({
            "id": uuid.uuid4().hex,
            "customer_id": cust["id"],
            "type": "earn",
            "points": points,
            "reference_type": "transaction",
            "reference_id": tid,
            "created_at": bill_date.isoformat(),
        })
    for i in range(0, len(txns), 1000):
        await transactions_col.insert_many(txns[i:i + 1000])
    for i in range(0, len(ledger), 1000):
        await points_ledger_col.insert_many(ledger[i:i + 1000])
    print(f"Seeded {len(txns)} transactions")


async def seed_coupons():
    now = datetime.now(timezone.utc)
    coupons = [
        {"code": "KAZOWELCOME20", "name": "Welcome 20% Off", "coupon_type": "percentage", "discount_value": 20, "min_bill_amount": 1500, "max_discount": 1500, "description": "20% off on your first purchase up to ₹1500"},
        {"code": "KAZOFLAT500", "name": "Flat ₹500 Off", "coupon_type": "flat", "discount_value": 500, "min_bill_amount": 2500, "description": "Flat ₹500 off on orders above ₹2500"},
        {"code": "KAZOVIP15", "name": "VIP 15% Off", "coupon_type": "percentage", "discount_value": 15, "min_bill_amount": 5000, "max_discount": 2000, "target_tier": "platinum", "description": "Exclusive VIP discount for Platinum & Diamond tier"},
        {"code": "KAZOBIRTHDAY", "name": "Birthday Bonanza", "coupon_type": "percentage", "discount_value": 25, "min_bill_amount": 1000, "max_discount": 1500, "description": "25% birthday treat"},
        {"code": "KAZOWINBACK", "name": "We Miss You ₹1000", "coupon_type": "flat", "discount_value": 1000, "min_bill_amount": 3000, "description": "Win-back offer for inactive customers"},
        {"code": "KAZODENIM30", "name": "Denim Days 30%", "coupon_type": "percentage", "discount_value": 30, "min_bill_amount": 2000, "max_discount": 2500, "target_category": "DENIM", "description": "30% off on all denim styles"},
        {"code": "KAZOPARTY", "name": "Party Season 25%", "coupon_type": "percentage", "discount_value": 25, "min_bill_amount": 3000, "max_discount": 2500, "target_category": "PARTY WEAR", "description": "Party-ready savings"},
        {"code": "KAZOJEWEL", "name": "Jewelry ₹300 Off", "coupon_type": "flat", "discount_value": 300, "min_bill_amount": 1500, "target_category": "JEWELLERY", "description": "₹300 off jewelry"},
    ]
    docs = []
    for c in coupons:
        d = {**c, "id": uuid.uuid4().hex, "valid_from": (now - timedelta(days=30)).isoformat(), "valid_to": (now + timedelta(days=90)).isoformat(),
             "usage_limit": 10000, "usage_limit_per_customer": 1, "require_otp": False, "is_active": True,
             "times_used": random.randint(50, 800), "times_issued": random.randint(800, 5000),
             "created_at": (now - timedelta(days=random.randint(5, 60))).isoformat()}
        docs.append(d)
    await coupons_col.insert_many(docs)
    print(f"Seeded {len(docs)} coupons")
    return docs


async def seed_campaigns(coupons):
    now = datetime.now(timezone.utc)
    samples = [
        ("Diwali Sparkle 2025", "Festive collection launch with 25% off", ["whatsapp", "sms"], "all", "Celebrate Diwali in style with KAZO!", "completed"),
        ("Winter Wardrobe", "New winter collection blast", ["whatsapp", "email"], "tier", "Layer up with our new winter edit.", "completed"),
        ("VIP Diamond Preview", "Exclusive preview for Diamond tier", ["email"], "tier", "Your private preview is live, Diamond member.", "completed"),
        ("Win-back Champions", "Bring back 90-day inactive customers", ["whatsapp", "sms"], "cohort", "We miss you! Here's ₹1000 to come back.", "completed"),
        ("Birthday Bonanza Auto", "Automated birthday offer", ["whatsapp"], "cohort", "Happy Birthday! 25% off your special day.", "running"),
        ("Mumbai Anniversary", "Phoenix Marketcity store anniversary", ["sms"], "city", "Celebrate with us — only in Mumbai!", "completed"),
        ("Denim Days", "Denim category push", ["whatsapp", "push"], "all", "30% off the denim you love.", "running"),
        ("Bangalore Launch", "New Bangalore store launch", ["sms", "email"], "city", "Bangalore, KAZO is here!", "completed"),
        ("Summer Soirée Q2", "Summer party wear push", ["whatsapp"], "cohort", "Summer parties start at KAZO.", "scheduled"),
    ]
    docs = []
    for i, (name, desc, channels, atype, msg, status) in enumerate(samples):
        coup = random.choice(coupons)
        af = {}
        if atype == "tier":
            af = {"tier": random.choice(["gold", "platinum", "diamond"])}
        elif atype == "city":
            af = {"city": random.choice(["Mumbai", "Delhi", "Bangalore"])}
        elif atype == "cohort":
            af = {"cohort": random.choice(["high_value", "churn_risk", "new", "vip"])}
        sent = random.randint(2000, 15000) if status in ("completed", "running") else 0
        delivered = int(sent * 0.94)
        opened = int(delivered * random.uniform(0.30, 0.55))
        clicked = int(opened * random.uniform(0.10, 0.25))
        redeemed = int(clicked * random.uniform(0.15, 0.35))
        revenue = redeemed * random.randint(2000, 5000)
        docs.append({
            "id": uuid.uuid4().hex,
            "name": name,
            "description": desc,
            "channels": channels,
            "audience_type": atype,
            "audience_filter": af,
            "message_template": msg,
            "coupon_code": coup["code"],
            "schedule_at": (now + timedelta(days=random.randint(1, 14))).isoformat() if status == "scheduled" else None,
            "status": status,
            "sent": sent, "delivered": delivered, "opened": opened, "clicked": clicked,
            "redeemed": redeemed, "revenue_generated": float(revenue),
            "created_at": (now - timedelta(days=random.randint(5, 60))).isoformat(),
            "launched_at": (now - timedelta(days=random.randint(1, 50))).isoformat() if status in ("completed", "running") else None,
        })
    await campaigns_col.insert_many(docs)
    print(f"Seeded {len(docs)} campaigns")


async def seed_api_logs(stores, n=400):
    endpoints = [
        ("/api/pos/validate-customer", "POST"),
        ("/api/pos/issue-points", "POST"),
        ("/api/pos/redeem-points", "POST"),
        ("/api/pos/issue-otp", "POST"),
        ("/api/pos/redeem-coupon", "POST"),
    ]
    docs = []
    now = datetime.now(timezone.utc)
    for _ in range(n):
        ep, method = random.choice(endpoints)
        ts = now - timedelta(minutes=random.randint(0, 60 * 24))
        success = random.random() < 0.94
        status = 200 if success else random.choice([400, 401, 404, 409, 500])
        err_map = {400: "missing fields", 401: "invalid OTP", 404: "customer not found", 409: "duplicate bill", 500: "internal error"}
        docs.append({
            "id": uuid.uuid4().hex,
            "endpoint": ep,
            "method": method,
            "status_code": status,
            "response_time_ms": random.randint(15, 280),
            "customer_mobile": f"9{random.randint(100000000, 999999999)}",
            "bill_number": f"KZO/{random.randint(10000, 99999)}",
            "store_id": random.choice(stores)["id"],
            "error_reason": err_map.get(status),
            "timestamp": ts.isoformat(),
        })
    await api_logs_col.insert_many(docs)
    print(f"Seeded {len(docs)} api logs")


async def seed_nps(customers, stores, n=300):
    docs = []
    now = datetime.now(timezone.utc)
    for _ in range(n):
        cust = random.choice(customers)
        store = random.choice(stores)
        score = random.choices([10, 9, 8, 7, 5, 3], weights=[35, 25, 15, 10, 10, 5])[0]
        sentiment = "promoter" if score >= 9 else "passive" if score >= 7 else "detractor"
        docs.append({
            "id": uuid.uuid4().hex,
            "customer_id": cust["id"],
            "customer_mobile": cust["mobile"],
            "store_id": store["id"],
            "score": score,
            "sentiment": sentiment,
            "feedback": random.choice([
                "Loved the new collection!", "Staff was very helpful.", "Great fit and quality.",
                "Trial room was crowded.", "Awesome experience.", "Sizes were limited.",
                None, None, None
            ]),
            "category": "overall",
            "created_at": (now - timedelta(days=random.randint(0, 60))).isoformat(),
        })
    await nps_col.insert_many(docs)
    print(f"Seeded {len(docs)} NPS responses")


async def seed_tickets(customers, n=30):
    docs = []
    now = datetime.now(timezone.utc)
    samples = [
        ("Points not credited", "Bought a dress yesterday but points haven't reflected.", "points"),
        ("Coupon code not working", "KAZOBIRTHDAY says invalid at billing.", "coupon"),
        ("OTP not received", "OTP for redeem isn't coming on my mobile.", "otp"),
        ("Wrong tier shown", "I should be Gold tier but profile says Silver.", "general"),
        ("Sync delay", "Bill from Mumbai store hasn't synced to my account.", "sync"),
    ]
    for _ in range(n):
        c = random.choice(customers)
        subj, desc, cat = random.choice(samples)
        status = random.choices(["open", "in_progress", "resolved", "closed", "escalated"], weights=[25, 20, 35, 15, 5])[0]
        created = now - timedelta(days=random.randint(0, 20))
        docs.append({
            "id": uuid.uuid4().hex,
            "customer_id": c["id"],
            "customer_mobile": c["mobile"],
            "subject": subj,
            "description": desc,
            "category": cat,
            "priority": random.choice(["low", "medium", "high"]),
            "status": status,
            "created_at": created.isoformat(),
            "updated_at": created.isoformat(),
            "resolved_at": (created + timedelta(hours=random.randint(2, 48))).isoformat() if status in ("resolved", "closed") else None,
            "notes": [],
        })
    await tickets_col.insert_many(docs)
    print(f"Seeded {len(docs)} tickets")


async def main():
    print("Connecting to MongoDB:", os.environ.get("MONGO_URL"), os.environ.get("DB_NAME"))
    await clear_all()
    await seed_users()
    stores = await seed_stores()
    customers = await seed_customers(stores, n=1500)
    await seed_transactions(customers, stores, n=8000)
    coupons = await seed_coupons()
    await seed_campaigns(coupons)
    await seed_api_logs(stores, n=400)
    await seed_nps(customers, stores, n=300)
    await seed_tickets(customers, n=30)
    print("\n✅ Seed complete")


if __name__ == "__main__":
    asyncio.run(main())
