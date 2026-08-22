"""Coupon engine."""
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from database import coupons_col, coupon_redemptions_col, customers_col, db
from auth import get_current_user, require_roles, log_audit, MANAGEMENT_ROLES
from models import CouponCreate, Coupon
import uuid
import re
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


@router.get("/recent-issuances")
async def recent_issuances(
    limit: int = 200,
    coupon_code: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """List of recent coupon issuances/redemptions with customer mobile, bill #,
    discount amount, coupon code and code/created_at.
    Addresses docx 'Coupon Engine — customer mobile not visible / dummy
    coupon code visible'."""
    fil: dict = {}
    if coupon_code:
        fil["coupon_code"] = coupon_code
    rows = await coupon_redemptions_col.find(fil, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)

    # Enrich with customer name (best-effort batch)
    mobiles = list({r.get("customer_mobile") for r in rows if r.get("customer_mobile")})
    cust_map: dict = {}
    if mobiles:
        async for c in customers_col.find({"mobile": {"$in": mobiles}},
                                            {"_id": 0, "mobile": 1, "name": 1, "tier": 1}):
            cust_map[c["mobile"]] = c
    for r in rows:
        m = r.get("customer_mobile")
        c = cust_map.get(m) if m else None
        r["customer_name"] = (c or {}).get("name") or "—"
        r["customer_tier"] = (c or {}).get("tier") or "—"
    return {"rows": rows, "count": len(rows)}


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


@router.post("/{coupon_id}/issue-to-customer")
async def issue_coupon_to_customer(coupon_id: str, customer_mobile: str,
                                     user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    """Issue an existing coupon to a specific customer (fires coupon_issued SMS/WhatsApp template)."""
    c = await coupons_col.find_one({"id": coupon_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Coupon not found")
    cust = await customers_col.find_one({"mobile": customer_mobile}, {"_id": 0})
    if not cust:
        raise HTTPException(404, "Customer not found")
    await coupons_col.update_one({"id": coupon_id}, {"$inc": {"times_issued": 1}})
    await log_audit(user, "issue_coupon", "coupon", coupon_id,
                     {"code": c["code"], "to": customer_mobile})

    # Fire coupon_issued templates
    try:
        from routes.communications_routes import fire_event
        await fire_event("coupon_issued", customer_mobile, {
            "name": (cust.get("name") or "").split(" ")[0] or "there",
            "coupon_code": c["code"],
            "discount_value": c.get("discount_value"),
            "valid_to": c.get("valid_to", ""),
            "tier": cust.get("tier", "silver"),
        })
    except Exception:
        pass
    return {"issued": True, "coupon_code": c["code"], "customer_mobile": customer_mobile}


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


# ═══════════════════════ Unique (per-mobile) coupons ═══════════════════════
# A "batch" defines an offer once; one UNIQUE code is generated per mobile and locked to that
# mobile (single-use, redeemable only by that number at POS). Sending is done separately (via a
# campaign that references the batch, or by Master Brain).
unique_coupons_col = db["unique_coupons"]
coupon_batches_col = db["coupon_batches"]


def _gen_unique_code(prefix: str) -> str:
    return f"{prefix}{''.join(random.choices(string.ascii_uppercase + string.digits, k=8))}"


def _norm10(m) -> str:
    d = re.sub(r"\D", "", str(m or ""))
    return d[-10:] if len(d) >= 10 else d


class UniqueAudience(BaseModel):
    source: str  # segment | marketing_db | mobiles
    segment_id: Optional[str] = None
    marketing_db_id: Optional[str] = None
    mobiles: Optional[List[str]] = None


class UniqueAllocateIn(BaseModel):
    name: str
    coupon_type: str = "flat"  # flat | percentage
    discount_value: float
    min_bill_amount: float = 0.0
    max_discount: Optional[float] = None
    valid_from: datetime
    valid_to: datetime
    prefix: str = "KAZO"
    audience: UniqueAudience


async def _resolve_unique_audience(a: UniqueAudience) -> List[str]:
    if a.source == "mobiles":
        raw = a.mobiles or []
    elif a.source == "marketing_db":
        mdb = await db["marketing_databases"].find_one({"id": a.marketing_db_id}, {"_id": 0, "mobiles": 1})
        if not mdb:
            raise HTTPException(404, "Marketing database not found")
        raw = mdb.get("mobiles") or []
    elif a.source == "segment":
        seg = await db["segments"].find_one({"id": a.segment_id}, {"_id": 0, "tree": 1})
        if not seg:
            raise HTTPException(404, "Segment not found")
        from routes.segments_routes import compile_tree
        fil = await compile_tree(seg["tree"])
        raw = await customers_col.distinct("mobile", fil)
    else:
        raise HTTPException(400, "Invalid audience source (use segment | marketing_db | mobiles)")
    return sorted({_norm10(m) for m in raw if len(_norm10(m)) == 10})


@router.post("/unique/allocate")
async def allocate_unique(body: UniqueAllocateIn, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    mobiles = await _resolve_unique_audience(body.audience)
    if not mobiles:
        raise HTTPException(400, "No valid recipients resolved for this audience")
    if len(mobiles) > 200000:
        raise HTTPException(400, "Too many recipients (max 200000)")
    batch_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    vf = body.valid_from.isoformat() if isinstance(body.valid_from, datetime) else body.valid_from
    vt = body.valid_to.isoformat() if isinstance(body.valid_to, datetime) else body.valid_to
    prefix = (re.sub(r"[^A-Za-z0-9]", "", body.prefix or "KAZO")[:10] or "KAZO").upper()
    used, docs = set(), []
    for m in mobiles:
        code = _gen_unique_code(prefix)
        while code in used:
            code = _gen_unique_code(prefix)
        used.add(code)
        docs.append({
            "id": uuid.uuid4().hex, "code": code, "mobile": m, "batch_id": batch_id,
            "status": "allocated", "created_at": now, "redeemed_at": None,
            "bill_number": None, "discount": None, "name": body.name,
            "coupon_type": body.coupon_type, "discount_value": body.discount_value,
            "min_bill_amount": body.min_bill_amount, "max_discount": body.max_discount,
            "valid_from": vf, "valid_to": vt,
        })
    for i in range(0, len(docs), 5000):
        await unique_coupons_col.insert_many(docs[i:i + 5000], ordered=False)
    batch = {
        "id": batch_id, "name": body.name, "coupon_type": body.coupon_type,
        "discount_value": body.discount_value, "min_bill_amount": body.min_bill_amount,
        "max_discount": body.max_discount, "valid_from": vf, "valid_to": vt, "prefix": prefix,
        "source": body.audience.source,
        "source_ref": body.audience.marketing_db_id or body.audience.segment_id,
        "total": len(docs), "redeemed": 0, "created_at": now,
        "created_by": user["id"], "created_by_email": user.get("email"),
    }
    await coupon_batches_col.insert_one(batch)
    await log_audit(user, "allocate_unique_coupons", "coupon_batch", batch_id,
                    {"name": body.name, "total": len(docs)})
    batch.pop("_id", None)
    return batch


@router.get("/unique/batches")
async def list_unique_batches(user: dict = Depends(get_current_user)):
    rows = await coupon_batches_col.find({}, {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)
    return {"rows": rows, "total": len(rows)}


@router.get("/unique/batches/{batch_id}")
async def get_unique_batch(batch_id: str, page: int = 1, page_size: int = 50,
                           status: Optional[str] = None, q: Optional[str] = None,
                           user: dict = Depends(get_current_user)):
    b = await coupon_batches_col.find_one({"id": batch_id}, {"_id": 0})
    if not b:
        raise HTTPException(404, "Batch not found")
    fil: dict = {"batch_id": batch_id}
    if status in ("allocated", "redeemed"):
        fil["status"] = status
    if q:
        needle = _norm10(q) or re.sub(r"\D", "", q)
        fil["$or"] = [{"mobile": {"$regex": needle}}, {"code": {"$regex": q.upper()}}]
    total = await unique_coupons_col.count_documents(fil)
    redeemed = await unique_coupons_col.count_documents({"batch_id": batch_id, "status": "redeemed"})
    rows = await unique_coupons_col.find(
        fil, {"_id": 0, "code": 1, "mobile": 1, "status": 1, "redeemed_at": 1,
              "bill_number": 1, "discount": 1}).skip(max(0, (page - 1) * page_size)).limit(page_size).to_list(page_size)
    return {"batch": b, "rows": rows, "total": total, "redeemed": redeemed,
            "allocated": b.get("total", 0) - redeemed, "page": page, "page_size": page_size}


@router.get("/unique/batches/{batch_id}/export")
async def export_unique_batch(batch_id: str, user: dict = Depends(get_current_user)):
    b = await coupon_batches_col.find_one({"id": batch_id}, {"_id": 0, "name": 1})
    if not b:
        raise HTTPException(404, "Batch not found")
    import io
    import csv
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["code", "mobile", "status", "redeemed_at", "bill_number", "discount"])
    async for u in unique_coupons_col.find({"batch_id": batch_id}, {"_id": 0}):
        w.writerow([u.get("code"), u.get("mobile"), u.get("status"), u.get("redeemed_at") or "",
                    u.get("bill_number") or "", u.get("discount") if u.get("discount") is not None else ""])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="unique_coupons_{batch_id}.csv"'})


@router.delete("/unique/batches/{batch_id}")
async def delete_unique_batch(batch_id: str, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    res = await coupon_batches_col.delete_one({"id": batch_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Batch not found")
    await unique_coupons_col.delete_many({"batch_id": batch_id})
    await log_audit(user, "delete_unique_batch", "coupon_batch", batch_id, {})
    return {"ok": True}
