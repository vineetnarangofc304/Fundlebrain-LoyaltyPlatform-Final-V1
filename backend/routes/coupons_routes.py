"""Coupon engine."""
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from database import coupons_col, coupon_redemptions_col, customers_col
from auth import get_current_user, require_roles, log_audit, MANAGEMENT_ROLES
from models import CouponCreate, Coupon
import uuid
import random
import string

router = APIRouter(prefix="/coupons", tags=["coupons"])


def _gen_code(prefix: str = "KAZO"):
    return f"{prefix}{''.join(random.choices(string.ascii_uppercase + string.digits, k=6))}"


@router.get("")
async def list_coupons(
    is_active: Optional[bool] = None, coupon_type: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    fil = {}
    if is_active is not None:
        fil["is_active"] = is_active
    if coupon_type:
        fil["coupon_type"] = coupon_type
    items = await coupons_col.find(fil, {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)
    return items


@router.post("", response_model=Coupon)
async def create_coupon(payload: CouponCreate, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    if not payload.code:
        payload.code = _gen_code()
    exists = await coupons_col.find_one({"code": payload.code})
    if exists:
        raise HTTPException(status_code=409, detail="Coupon code already exists")
    doc = payload.model_dump()
    # Convert enum and datetime
    if doc.get("target_tier") and hasattr(doc["target_tier"], "value"):
        doc["target_tier"] = doc["target_tier"].value
    for f in ("valid_from", "valid_to"):
        if isinstance(doc.get(f), datetime):
            doc[f] = doc[f].isoformat()
    doc["id"] = uuid.uuid4().hex
    doc["times_used"] = 0
    doc["times_issued"] = 0
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["created_by"] = user["id"]
    await coupons_col.insert_one(doc)
    await log_audit(user, "create_coupon", "coupon", doc["id"], {"code": doc["code"]})
    doc.pop("_id", None)
    return doc


@router.post("/generate-code")
async def generate_code(prefix: str = "KAZO", user: dict = Depends(get_current_user)):
    return {"code": _gen_code(prefix)}


@router.get("/{coupon_id}")
async def get_coupon(coupon_id: str, user: dict = Depends(get_current_user)):
    c = await coupons_col.find_one({"id": coupon_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Coupon not found")
    # redemption stats
    redemptions = await coupon_redemptions_col.find({"coupon_id": coupon_id}, {"_id": 0}).sort("redeemed_at", -1).limit(50).to_list(50)
    return {"coupon": c, "redemptions": redemptions}


@router.patch("/{coupon_id}")
async def update_coupon(coupon_id: str, updates: dict, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    c = await coupons_col.find_one({"id": coupon_id})
    if not c:
        raise HTTPException(404, "Coupon not found")
    for f in ("valid_from", "valid_to"):
        if isinstance(updates.get(f), datetime):
            updates[f] = updates[f].isoformat()
    await coupons_col.update_one({"id": coupon_id}, {"$set": updates})
    await log_audit(user, "update_coupon", "coupon", coupon_id, updates)
    return await coupons_col.find_one({"id": coupon_id}, {"_id": 0})


@router.post("/{coupon_id}/validate")
async def validate_coupon(coupon_id: str, customer_mobile: Optional[str] = None, bill_amount: Optional[float] = None, user: dict = Depends(get_current_user)):
    c = await coupons_col.find_one({"id": coupon_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Coupon not found")
    now = datetime.now(timezone.utc).isoformat()
    if not c["is_active"]:
        return {"valid": False, "reason": "Coupon is inactive"}
    if now < c["valid_from"]:
        return {"valid": False, "reason": "Coupon not yet valid"}
    if now > c["valid_to"]:
        return {"valid": False, "reason": "Coupon expired"}
    if c["times_used"] >= c.get("usage_limit", 0) > 0:
        return {"valid": False, "reason": "Usage limit reached"}
    if bill_amount is not None and bill_amount < c.get("min_bill_amount", 0):
        return {"valid": False, "reason": f"Min bill amount ₹{c['min_bill_amount']}"}
    return {"valid": True, "coupon": c}


@router.post("/validate-by-code/{code}")
async def validate_by_code(code: str, customer_mobile: Optional[str] = None, bill_amount: Optional[float] = None, user: dict = Depends(get_current_user)):
    c = await coupons_col.find_one({"code": code.upper()}, {"_id": 0})
    if not c:
        return {"valid": False, "reason": "Code not found"}
    return await validate_coupon(c["id"], customer_mobile, bill_amount, user)


@router.post("/{coupon_id}/redeem")
async def redeem_coupon(coupon_id: str, customer_mobile: str, bill_number: str, bill_amount: float, store_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    c = await coupons_col.find_one({"id": coupon_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Coupon not found")
    # Calculate discount
    discount = 0.0
    if c["coupon_type"] == "flat":
        discount = c["discount_value"]
    elif c["coupon_type"] == "percentage":
        discount = bill_amount * c["discount_value"] / 100
        if c.get("max_discount"):
            discount = min(discount, c["max_discount"])
    else:
        discount = c["discount_value"]
    discount = round(min(discount, bill_amount), 2)

    customer = await customers_col.find_one({"mobile": customer_mobile}, {"_id": 0})
    await coupon_redemptions_col.insert_one({
        "id": uuid.uuid4().hex,
        "coupon_id": coupon_id,
        "coupon_code": c["code"],
        "customer_id": customer["id"] if customer else None,
        "customer_mobile": customer_mobile,
        "bill_number": bill_number,
        "bill_amount": bill_amount,
        "discount": discount,
        "store_id": store_id,
        "redeemed_at": datetime.now(timezone.utc).isoformat(),
        "redeemed_by": user["id"],
    })
    await coupons_col.update_one({"id": coupon_id}, {"$inc": {"times_used": 1}})
    await log_audit(user, "redeem_coupon", "coupon", coupon_id, {"code": c["code"], "customer": customer_mobile})
    return {"success": True, "discount": discount, "code": c["code"]}
