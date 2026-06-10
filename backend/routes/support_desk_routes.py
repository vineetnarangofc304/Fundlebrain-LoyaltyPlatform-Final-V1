"""Support Desk routes — L1 support operations.

Mirrors newu.fundlezone.com / Support Desk module:
- Search Redeem Points OTP / Redeem Coupon OTP (audit search)
- Reactivate Coupon (reverse redemption)
- Reactivate Redeem Points (reverse redemption)
- Customer Deactivate / Reactivate
- Unsubscribe Customer list
- User Logins (use existing users module)
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from database import (
    customers_col, points_ledger_col, coupons_col, coupon_redemptions_col,
    audit_logs_col,
)
from auth import get_current_user, require_roles, log_audit

# Same DB connection as pos_ewards_routes uses
from routes.pos_ewards_routes import pos_otp_col

router = APIRouter(prefix="/support-desk", tags=["support-desk"])


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _norm_mobile(m: Optional[str]) -> Optional[str]:
    if not m:
        return None
    s = "".join(ch for ch in str(m) if ch.isdigit())
    if s.startswith("91") and len(s) > 10:
        s = s[2:]
    if len(s) >= 10:
        return s[-10:]
    # Accept short / non-standard mobiles (legacy data may have 8-9 digits)
    return s if len(s) >= 7 else None


# ---------------- A) OTP audit search — redeem points ----------------

@router.get("/redeem-points-otp")
async def search_redeem_points_otp(
    mobile: Optional[str] = None,
    otp_id: Optional[str] = None,
    bill_number: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    user: dict = Depends(get_current_user),
):
    """Search OTP sessions for redeem-points purpose. Used by support staff to
    audit a redemption attempt (was OTP delivered? verified? when?)."""
    fil: Dict[str, Any] = {"purpose": "redeem_points"}
    norm = _norm_mobile(mobile)
    if norm:
        fil["mobile"] = norm
    if otp_id:
        fil["otp_id"] = otp_id
    if bill_number:
        fil["bill_number"] = bill_number
    if start_date and end_date:
        fil["created_at"] = {"$gte": start_date, "$lte": end_date + "T23:59:59Z"}

    cursor = pos_otp_col.find(fil, {"_id": 0}).sort("created_at", -1).limit(limit)
    rows = await cursor.to_list(limit)
    # OTP value is intentionally surfaced (not masked): with SMS delivery unreliable,
    # support staff read the OTP off this screen to complete a MANUAL redemption.
    return {"total": len(rows), "rows": rows}


@router.get("/redeem-coupon-otp")
async def search_redeem_coupon_otp(
    mobile: Optional[str] = None,
    otp_id: Optional[str] = None,
    coupon_code: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    user: dict = Depends(get_current_user),
):
    """Search OTP sessions for redeem-coupon purpose."""
    fil: Dict[str, Any] = {"purpose": "redeem_coupon"}
    norm = _norm_mobile(mobile)
    if norm:
        fil["mobile"] = norm
    if otp_id:
        fil["otp_id"] = otp_id
    if coupon_code:
        fil["coupon_code"] = coupon_code
    if start_date and end_date:
        fil["created_at"] = {"$gte": start_date, "$lte": end_date + "T23:59:59Z"}

    cursor = pos_otp_col.find(fil, {"_id": 0}).sort("created_at", -1).limit(limit)
    rows = await cursor.to_list(limit)
    # OTP value is intentionally surfaced (not masked) for manual coupon redemption.
    return {"total": len(rows), "rows": rows}


# ---------------- B) Reactivate Coupon (reverse redemption) ----------------

@router.get("/redeemed-coupons")
async def list_redeemed_coupons(
    mobile: Optional[str] = None,
    coupon_code: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    user: dict = Depends(get_current_user),
):
    """List recently redeemed coupons so support staff can pick one to reverse."""
    fil: Dict[str, Any] = {}
    norm = _norm_mobile(mobile)
    if norm:
        fil["customer_mobile"] = norm
    if coupon_code:
        fil["code"] = {"$regex": coupon_code, "$options": "i"}
    if start_date and end_date:
        fil["redeemed_at"] = {"$gte": start_date, "$lte": end_date + "T23:59:59Z"}
    rows = await coupon_redemptions_col.find(fil, {"_id": 0}).sort("redeemed_at", -1).limit(limit).to_list(limit)
    return {"total": len(rows), "rows": rows}


class ReactivateCouponReq(BaseModel):
    redemption_id: str
    reason: str


@router.post("/reactivate-coupon")
async def reactivate_coupon(
    payload: ReactivateCouponReq,
    user: dict = Depends(require_roles("super_admin", "brand_admin", "support_agent")),
):
    """Reverse a coupon redemption.

    1. Find the coupon_redemptions row by id.
    2. Mark it as `reversed=True` (history preserved).
    3. Re-enable the coupon (decrement uses_count, set redeemed_at=None on coupon if exists).
    4. Audit log the action.
    """
    red = await coupon_redemptions_col.find_one({"id": payload.redemption_id}, {"_id": 0})
    if not red:
        raise HTTPException(status_code=404, detail="Redemption record not found")
    if red.get("reversed"):
        raise HTTPException(status_code=400, detail="Already reversed")

    # Mark reversed
    await coupon_redemptions_col.update_one(
        {"id": payload.redemption_id},
        {"$set": {
            "reversed": True,
            "reversed_at": _now_iso(),
            "reversed_by": user.get("email"),
            "reversal_reason": payload.reason,
        }},
    )
    # Decrement uses_count on the coupon master if present
    code = red.get("code")
    if code:
        await coupons_col.update_one(
            {"code": code},
            {"$inc": {"uses_count": -1}},
        )
    await log_audit(user, "support_desk.reactivate_coupon", "coupon_redemption",
                    payload.redemption_id, {"code": code, "reason": payload.reason})
    return {"ok": True, "redemption_id": payload.redemption_id}


# ---------------- C) Reactivate Redeem Points ----------------

@router.get("/redeemed-points")
async def list_redeemed_points(
    mobile: Optional[str] = None,
    bill_number: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    user: dict = Depends(get_current_user),
):
    """List recent point-redemption ledger entries (kind=redeem)."""
    fil: Dict[str, Any] = {"kind": {"$in": ["redeem", "redemption"]}}
    norm = _norm_mobile(mobile)
    if norm:
        fil["customer_mobile"] = norm
    if bill_number:
        fil["bill_number"] = bill_number
    if start_date and end_date:
        fil["created_at"] = {"$gte": start_date, "$lte": end_date + "T23:59:59Z"}
    rows = await points_ledger_col.find(fil, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"total": len(rows), "rows": rows}


class ReactivatePointsReq(BaseModel):
    ledger_id: str
    reason: str


@router.post("/reactivate-redeem-points")
async def reactivate_redeem_points(
    payload: ReactivatePointsReq,
    user: dict = Depends(require_roles("super_admin", "brand_admin", "support_agent")),
):
    """Reverse a point redemption.

    1. Find the points_ledger row.
    2. Insert a compensating ledger entry of equal magnitude with kind='reversal'.
    3. Restore points to customer balance.
    """
    led = await points_ledger_col.find_one({"id": payload.ledger_id}, {"_id": 0})
    if not led:
        raise HTTPException(status_code=404, detail="Ledger entry not found")
    if led.get("reversed"):
        raise HTTPException(status_code=400, detail="Already reversed")

    points = abs(int(led.get("points", 0)))
    mobile = led.get("customer_mobile")
    if not mobile or points == 0:
        raise HTTPException(status_code=400, detail="Cannot reverse: missing mobile or zero points")

    # 1. Mark original as reversed
    await points_ledger_col.update_one(
        {"id": payload.ledger_id},
        {"$set": {"reversed": True, "reversed_at": _now_iso(), "reversed_by": user.get("email"), "reversal_reason": payload.reason}},
    )
    # 2. Insert compensating ledger
    import uuid as _u
    await points_ledger_col.insert_one({
        "id": str(_u.uuid4()),
        "customer_mobile": mobile,
        "points": points,  # positive (credit back)
        "kind": "reversal",
        "reason": f"Reversal of redemption {payload.ledger_id} — {payload.reason}",
        "linked_ledger_id": payload.ledger_id,
        "created_at": _now_iso(),
        "created_by": user.get("email"),
    })
    # 3. Restore points to customer
    await customers_col.update_one(
        {"mobile": mobile},
        {
            "$inc": {"points_balance": points, "lifetime_points_redeemed": -points},
        },
    )
    await log_audit(user, "support_desk.reactivate_redeem_points", "points_ledger",
                    payload.ledger_id, {"mobile": mobile, "points": points, "reason": payload.reason})
    return {"ok": True, "ledger_id": payload.ledger_id, "points_restored": points}


# ---------------- D) Customer Deactivate / Reactivate ----------------

class CustomerActionReq(BaseModel):
    mobile: str
    reason: str


@router.post("/customer-deactivate")
async def customer_deactivate(
    payload: CustomerActionReq,
    user: dict = Depends(require_roles("super_admin", "brand_admin", "support_agent")),
):
    norm = _norm_mobile(payload.mobile)
    if not norm:
        raise HTTPException(status_code=400, detail="Invalid mobile")
    cust = await customers_col.find_one({"mobile": norm}, {"_id": 0})
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    if cust.get("is_active") is False:
        raise HTTPException(status_code=400, detail="Customer already deactivated")
    await customers_col.update_one(
        {"mobile": norm},
        {"$set": {
            "is_active": False,
            "deactivated_at": _now_iso(),
            "deactivated_by": user.get("email"),
            "deactivation_reason": payload.reason,
        }},
    )
    await log_audit(user, "support_desk.customer_deactivate", "customer", norm,
                    {"reason": payload.reason})
    return {"ok": True, "mobile": norm}


@router.post("/customer-reactivate")
async def customer_reactivate(
    payload: CustomerActionReq,
    user: dict = Depends(require_roles("super_admin", "brand_admin", "support_agent")),
):
    norm = _norm_mobile(payload.mobile)
    if not norm:
        raise HTTPException(status_code=400, detail="Invalid mobile")
    cust = await customers_col.find_one({"mobile": norm}, {"_id": 0})
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    if cust.get("is_active") is not False:
        raise HTTPException(status_code=400, detail="Customer already active")
    await customers_col.update_one(
        {"mobile": norm},
        {"$set": {
            "is_active": True,
            "reactivated_at": _now_iso(),
            "reactivated_by": user.get("email"),
            "reactivation_reason": payload.reason,
        }, "$unset": {"deactivated_at": "", "deactivation_reason": ""}},
    )
    await log_audit(user, "support_desk.customer_reactivate", "customer", norm,
                    {"reason": payload.reason})
    return {"ok": True, "mobile": norm}


@router.get("/deactivated-customers")
async def list_deactivated_customers(
    q: Optional[str] = None,
    limit: int = 100,
    user: dict = Depends(get_current_user),
):
    fil: Dict[str, Any] = {"is_active": False}
    norm = _norm_mobile(q)
    if norm:
        fil["mobile"] = norm
    elif q:
        fil["name"] = {"$regex": q, "$options": "i"}
    rows = await customers_col.find(fil, {"_id": 0}).sort("deactivated_at", -1).limit(limit).to_list(limit)
    return {"total": len(rows), "rows": rows}


@router.get("/reactivated-customers")
async def list_reactivated_customers(
    q: Optional[str] = None,
    limit: int = 100,
    user: dict = Depends(get_current_user),
):
    """Customers who were once deactivated and then reactivated (audit trail)."""
    fil: Dict[str, Any] = {"reactivated_at": {"$exists": True}}
    norm = _norm_mobile(q)
    if norm:
        fil["mobile"] = norm
    elif q:
        fil["name"] = {"$regex": q, "$options": "i"}
    rows = await customers_col.find(fil, {"_id": 0}).sort("reactivated_at", -1).limit(limit).to_list(limit)
    return {"total": len(rows), "rows": rows}


# ---------------- E) Unsubscribe Customer ----------------

class UnsubscribeReq(BaseModel):
    mobile: str
    channel: Optional[str] = "all"  # sms | whatsapp | email | all
    reason: Optional[str] = None


@router.post("/unsubscribe")
async def unsubscribe_customer(
    payload: UnsubscribeReq,
    user: dict = Depends(require_roles("super_admin", "brand_admin", "support_agent")),
):
    norm = _norm_mobile(payload.mobile)
    if not norm:
        raise HTTPException(status_code=400, detail="Invalid mobile")
    cust = await customers_col.find_one({"mobile": norm}, {"_id": 0})
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    unsub = cust.get("unsubscribed", {}) or {}
    ch = payload.channel or "all"
    if ch == "all":
        unsub = {"sms": True, "whatsapp": True, "email": True, "rcs": True}
    else:
        unsub[ch] = True
    await customers_col.update_one(
        {"mobile": norm},
        {"$set": {
            "unsubscribed": unsub,
            "unsubscribed_at": _now_iso(),
            "unsubscribed_by": user.get("email"),
            "unsubscribed_reason": payload.reason,
        }},
    )
    await log_audit(user, "support_desk.unsubscribe", "customer", norm,
                    {"channel": ch, "reason": payload.reason})
    return {"ok": True, "mobile": norm, "channel": ch}


@router.post("/resubscribe")
async def resubscribe_customer(
    payload: UnsubscribeReq,
    user: dict = Depends(require_roles("super_admin", "brand_admin", "support_agent")),
):
    """Reverse unsubscribe — clear opt-out for one or all channels."""
    norm = _norm_mobile(payload.mobile)
    if not norm:
        raise HTTPException(status_code=400, detail="Invalid mobile")
    cust = await customers_col.find_one({"mobile": norm}, {"_id": 0})
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    unsub = cust.get("unsubscribed", {}) or {}
    ch = payload.channel or "all"
    if ch == "all":
        unsub = {}
    else:
        unsub.pop(ch, None)
    await customers_col.update_one(
        {"mobile": norm},
        {"$set": {
            "unsubscribed": unsub,
            "resubscribed_at": _now_iso(),
            "resubscribed_by": user.get("email"),
        }},
    )
    await log_audit(user, "support_desk.resubscribe", "customer", norm, {"channel": ch})
    return {"ok": True, "mobile": norm, "channel": ch}


@router.get("/unsubscribed")
async def list_unsubscribed(
    q: Optional[str] = None,
    channel: Optional[str] = None,
    limit: int = 200,
    user: dict = Depends(get_current_user),
):
    """List customers who have unsubscribed from at least one channel."""
    fil: Dict[str, Any] = {"unsubscribed": {"$exists": True, "$ne": {}}}
    norm = _norm_mobile(q)
    if norm:
        fil["mobile"] = norm
    elif q:
        fil["name"] = {"$regex": q, "$options": "i"}
    if channel and channel != "all":
        fil[f"unsubscribed.{channel}"] = True
    rows = await customers_col.find(fil, {"_id": 0}).sort("unsubscribed_at", -1).limit(limit).to_list(limit)
    # Surface unsub channels list per row
    for r in rows:
        u = r.get("unsubscribed") or {}
        r["unsub_channels"] = sorted([k for k, v in u.items() if v])
    return {"total": len(rows), "rows": rows}


# ---------------- F) Support Desk audit log (read-only) ----------------

@router.get("/audit-log")
async def support_desk_audit_log(
    action: Optional[str] = None,
    actor: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    user: dict = Depends(get_current_user),
):
    """Read the support desk's audit trail. Filters: action contains, actor email, date range."""
    fil: Dict[str, Any] = {"action": {"$regex": "^support_desk\\."}}
    if action:
        fil["action"] = {"$regex": action, "$options": "i"}
    if actor:
        fil["user_email"] = {"$regex": actor, "$options": "i"}
    if start_date and end_date:
        fil["timestamp"] = {"$gte": start_date, "$lte": end_date + "T23:59:59Z"}
    rows = await audit_logs_col.find(fil, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    return {"total": len(rows), "rows": rows}
