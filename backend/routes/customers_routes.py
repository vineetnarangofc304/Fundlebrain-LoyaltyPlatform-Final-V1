"""Customer 360 routes - search, deep profile, actions."""
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from database import (
    customers_col, transactions_col, points_ledger_col, coupons_col,
    coupon_redemptions_col, tickets_col, nps_col, campaigns_col,
)
from auth import get_current_user, log_audit
from models import CustomerCreate, Customer
import uuid

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("")
async def list_customers(
    q: Optional[str] = None, tier: Optional[str] = None, city: Optional[str] = None,
    churn_risk: Optional[str] = None, limit: int = 50, skip: int = 0,
    user: dict = Depends(get_current_user)
):
    fil = {}
    if q:
        fil["$or"] = [
            {"mobile": {"$regex": q, "$options": "i"}},
            {"email": {"$regex": q, "$options": "i"}},
            {"name": {"$regex": q, "$options": "i"}},
        ]
    if tier:
        fil["tier"] = tier
    if city:
        fil["city"] = city
    if churn_risk:
        fil["churn_risk"] = churn_risk
    total = await customers_col.count_documents(fil)
    customers = await customers_col.find(fil, {"_id": 0}).sort("lifetime_spend", -1).skip(skip).limit(limit).to_list(limit)
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
