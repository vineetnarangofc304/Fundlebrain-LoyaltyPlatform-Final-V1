"""Public-facing website APIs (no auth required) and contact form."""
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from database import stores_col, customers_col
import uuid

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/stores")
async def public_stores(city: Optional[str] = None, q: Optional[str] = None):
    fil = {"is_active": True}
    if city:
        fil["city"] = city
    if q:
        fil["$or"] = [
            {"name": {"$regex": q, "$options": "i"}},
            {"city": {"$regex": q, "$options": "i"}},
            {"address": {"$regex": q, "$options": "i"}},
        ]
    rows = await stores_col.find(fil, {"_id": 0}).sort("city", 1).limit(500).to_list(500)
    return rows


@router.get("/store-cities")
async def public_store_cities():
    pipe = [{"$group": {"_id": "$city", "count": {"$sum": 1}}}, {"$sort": {"_id": 1}}]
    rows = await stores_col.aggregate(pipe).to_list(200)
    return [{"city": r["_id"], "count": r["count"]} for r in rows]


@router.post("/register-interest")
async def register_interest(body: dict):
    name = (body.get("name") or "").strip()
    mobile = (body.get("mobile") or "").strip()
    email = (body.get("email") or "").strip()
    city = body.get("city")
    if not mobile or len(mobile) < 10:
        raise HTTPException(400, "Valid mobile number required")
    existing = await customers_col.find_one({"mobile": mobile}, {"_id": 0})
    if existing:
        return {"success": True, "already_registered": True, "tier": existing.get("tier"), "points": existing.get("points_balance", 0)}
    doc = {
        "id": uuid.uuid4().hex,
        "name": name,
        "mobile": mobile,
        "email": email or None,
        "city": city,
        "tier": "silver",
        "points_balance": 100,  # welcome bonus
        "lifetime_points_earned": 100,
        "lifetime_points_redeemed": 0,
        "lifetime_spend": 0.0,
        "visit_count": 0,
        "churn_risk": "low",
        "favourite_categories": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await customers_col.insert_one(doc)
    doc.pop("_id", None)
    return {"success": True, "welcome_bonus": 100, "customer_id": doc["id"]}


@router.get("/faqs")
async def public_faqs():
    return [
        {"q": "How do I join the KAZO Loyalty Program?", "a": "Sign up at any KAZO store or on this website with your mobile number. You'll instantly receive a 100-point welcome bonus."},
        {"q": "How do I earn points?", "a": "You earn 1 point for every ₹1 spent on KAZO products at any of our stores or partner channels. Gold tier earns 1.25x, Platinum earns 1.5x, Diamond earns 2x."},
        {"q": "How do I redeem points?", "a": "1 point = ₹0.25. Minimum 100 points required to redeem. Inform the store staff at billing — they'll verify via OTP sent to your registered mobile."},
        {"q": "When do my points expire?", "a": "Points expire 12 months from the date they were earned. Stay active to keep your points alive!"},
        {"q": "What are the tier benefits?", "a": "Silver (entry), Gold (₹25k+ lifetime), Platinum (₹75k+), Diamond (₹1.5L+). Higher tiers get bigger birthday bonuses, faster earn rates, and exclusive VIP coupons."},
        {"q": "Do I get a birthday bonus?", "a": "Yes! Silver: 200 pts, Gold: 500, Platinum: 1000, Diamond: 2000. Birthday must be registered in your profile."},
        {"q": "Can I refer friends?", "a": "Absolutely. You earn 250 points for every friend who makes their first purchase using your referral code. Your friend gets 100 welcome points too."},
        {"q": "Can I use a coupon with my loyalty points?", "a": "Coupon stacking is allowed for specific promotions. Check the coupon's terms or ask in-store."},
        {"q": "Where can I check my points balance?", "a": "Your balance appears on every store invoice. You can also ask any staff member or contact our customer support."},
        {"q": "Is the program valid online?", "a": "Yes — points earn and redeem work seamlessly across all KAZO stores and on kazo.com."},
    ]
