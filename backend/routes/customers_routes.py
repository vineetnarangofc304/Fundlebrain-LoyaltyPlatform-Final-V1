"""Customer 360 routes - search, deep profile, actions."""
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from database import (
    customers_col, transactions_col, points_ledger_col, coupons_col,
    coupon_redemptions_col, tickets_col, nps_col, campaigns_col,
    stores_col,
)
from auth import get_current_user, log_audit
from models import CustomerCreate, Customer
import uuid
import re

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("")
async def list_customers(
    q: Optional[str] = None, tier: Optional[str] = None, city: Optional[str] = None,
    churn_risk: Optional[str] = None, limit: int = 50, skip: int = 0,
    user: dict = Depends(get_current_user)
):
    fil = {}
    search_mode = False
    if q and q.strip():
        search_mode = True
        qs = q.strip()
        if qs.isdigit():
            # Mobile search — anchored PREFIX regex hits the {mobile:1} index, so it
            # stays fast even at 1M+ customers (an unanchored /q/i regex was a full
            # collection scan → the "searches forever / never returns" bug).
            fil["mobile"] = {"$regex": f"^{re.escape(qs)}"}
        else:
            rx = {"$regex": f"^{re.escape(qs)}", "$options": "i"}
            fil["$or"] = [
                {"name": rx},
                {"email": rx},
                {"mobile": {"$regex": f"^{re.escape(qs)}"}},
            ]
    if tier:
        fil["tier"] = tier
    if city:
        fil["city"] = city
    if churn_risk:
        fil["churn_risk"] = churn_risk

    # In search mode, sort by mobile (the index already returns rows in that order so
    # there's no costly in-memory sort of a large match set); otherwise rank by spend.
    sort_key, sort_dir = ("mobile", 1) if search_mode else ("lifetime_spend", -1)
    try:
        total = await customers_col.count_documents(fil, maxTimeMS=6000)
    except Exception:
        total = -1  # count timed out on a heavy name scan; UI still shows the page
    cursor = customers_col.find(fil, {"_id": 0}).sort(sort_key, sort_dir).skip(skip).limit(limit).max_time_ms(9000)
    customers = await cursor.to_list(limit)

    # Enrich each customer with home_store_code + home_store_name from store master,
    # so the Raw Customer Data table can show the "Location code" column (docx #39).
    store_ids = list({c.get("home_store_id") for c in customers if c.get("home_store_id")})
    store_map: dict = {}
    if store_ids:
        async for s in stores_col.find({"id": {"$in": store_ids}}, {"_id": 0, "id": 1, "name": 1, "code": 1}):
            store_map[s["id"]] = s
    for c in customers:
        sid = c.get("home_store_id")
        s = store_map.get(sid) if sid else None
        c["home_store_code"] = (s or {}).get("code") or "—"
        c["home_store_name"] = (s or {}).get("name") or "—"

    return {"total": total, "items": customers}


@router.get("/{customer_id}")
async def get_customer(customer_id: str, user: dict = Depends(get_current_user)):
    cust = await customers_col.find_one({"id": customer_id}, {"_id": 0})
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")

    # transactions
    txns = await transactions_col.find({"customer_id": customer_id}, {"_id": 0}).sort("bill_date", -1).limit(50).to_list(50)
    # points ledger
    ledger = await points_ledger_col.find({"customer_id": customer_id}, {"_id": 0}).sort("created_at", -1).limit(50).to_list(50)
    # coupon redemptions
    redemptions = await coupon_redemptions_col.find({"customer_id": customer_id}, {"_id": 0}).sort("redeemed_at", -1).limit(50).to_list(50)
    # tickets
    tix = await tickets_col.find({"customer_id": customer_id}, {"_id": 0}).sort("created_at", -1).to_list(50)
    # nps
    nps = await nps_col.find({"customer_id": customer_id}, {"_id": 0}).sort("created_at", -1).to_list(20)

    # category affinity
    cat_pipe = [
        {"$match": {"customer_id": customer_id}},
        {"$unwind": "$items"},
        {"$group": {"_id": "$items.category", "qty": {"$sum": "$items.quantity"}, "spend": {"$sum": "$items.total"}}},
        {"$sort": {"spend": -1}},
        {"$limit": 5},
    ]
    cat = await transactions_col.aggregate(cat_pipe).to_list(10)
    favourite_categories = [{"category": c["_id"], "qty": c["qty"], "spend": round(c["spend"], 2)} for c in cat]

    # favourite products
    prod_pipe = [
        {"$match": {"customer_id": customer_id}},
        {"$unwind": "$items"},
        {"$group": {"_id": {"sku": "$items.sku", "name": "$items.name"}, "qty": {"$sum": "$items.quantity"}, "spend": {"$sum": "$items.total"}}},
        {"$sort": {"qty": -1}},
        {"$limit": 5},
    ]
    pr = await transactions_col.aggregate(prod_pipe).to_list(10)
    favourite_products = [{"sku": p["_id"]["sku"], "name": p["_id"]["name"], "qty": p["qty"], "spend": round(p["spend"], 2)} for p in pr]

    return {
        "customer": cust,
        "transactions": txns,
        "points_ledger": ledger,
        "redemptions": redemptions,
        "tickets": tix,
        "nps_responses": nps,
        "favourite_categories": favourite_categories,
        "favourite_products": favourite_products,
    }


@router.post("", response_model=Customer)
async def create_customer(payload: CustomerCreate, user: dict = Depends(get_current_user)):
    existing = await customers_col.find_one({"mobile": payload.mobile})
    if existing:
        raise HTTPException(status_code=409, detail="Customer with this mobile already exists")
    doc = payload.model_dump()
    doc["id"] = uuid.uuid4().hex
    doc["tier"] = "silver"
    doc["points_balance"] = 0
    doc["lifetime_points_earned"] = 0
    doc["lifetime_points_redeemed"] = 0
    doc["lifetime_spend"] = 0.0
    doc["visit_count"] = 0
    doc["churn_risk"] = "low"
    doc["favourite_categories"] = []
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await customers_col.insert_one(doc)
    await log_audit(user, "create_customer", "customer", doc["id"])
    doc.pop("_id", None)
    return doc


@router.post("/{customer_id}/award-points")
async def award_points(customer_id: str, points: int, note: Optional[str] = None, user: dict = Depends(get_current_user)):
    cust = await customers_col.find_one({"id": customer_id}, {"_id": 0})
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    if points <= 0:
        raise HTTPException(status_code=400, detail="Points must be positive")
    await customers_col.update_one(
        {"id": customer_id},
        {"$inc": {"points_balance": points, "lifetime_points_earned": points}}
    )
    await points_ledger_col.insert_one({
        "id": uuid.uuid4().hex,
        "customer_id": customer_id,
        "customer_mobile": cust.get("mobile"),
        "type": "bonus",
        "points": points,
        "reference_type": "manual",
        "note": note or f"Awarded by {user['email']}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user["id"],
    })
    await log_audit(user, "award_points", "customer", customer_id, {"points": points})
    return {"success": True, "points": points}


@router.post("/{customer_id}/deduct-points")
async def deduct_points(customer_id: str, points: int, note: Optional[str] = None, user: dict = Depends(get_current_user)):
    cust = await customers_col.find_one({"id": customer_id}, {"_id": 0})
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    if points <= 0:
        raise HTTPException(status_code=400, detail="Points must be positive")
    if cust.get("points_balance", 0) < points:
        raise HTTPException(status_code=400, detail="Insufficient points")
    await customers_col.update_one(
        {"id": customer_id},
        {"$inc": {"points_balance": -points, "lifetime_points_redeemed": points}}
    )
    await points_ledger_col.insert_one({
        "id": uuid.uuid4().hex,
        "customer_id": customer_id,
        "customer_mobile": cust.get("mobile"),
        "type": "adjust",
        "points": -points,
        "reference_type": "manual",
        "note": note or f"Deducted by {user['email']}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user["id"],
    })
    await log_audit(user, "deduct_points", "customer", customer_id, {"points": points})
    return {"success": True}


@router.get("/search/by-mobile/{mobile}")
async def search_by_mobile(mobile: str, user: dict = Depends(get_current_user)):
    cust = await customers_col.find_one({"mobile": mobile}, {"_id": 0})
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    return cust
