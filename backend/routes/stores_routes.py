"""Store management + POS integration endpoints."""
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, File
from database import stores_col, customers_col, transactions_col, points_ledger_col, otp_col, coupons_col, api_logs_col, loyalty_config_col
from auth import get_current_user, require_roles, log_audit, ADMIN_ROLES
from models import StoreCreate, Store
import uuid
import random
import time

router = APIRouter(prefix="/stores", tags=["stores"])


@router.get("")
async def list_stores(city: Optional[str] = None, region: Optional[str] = None, user: dict = Depends(get_current_user)):
    fil = {}
    if city:
        fil["city"] = city
    if region:
        fil["region"] = region
    rows = await stores_col.find(fil, {"_id": 0}).sort("name", 1).limit(500).to_list(500)
    return rows


@router.post("", response_model=Store)
async def create_store(payload: StoreCreate, user: dict = Depends(require_roles(*ADMIN_ROLES))):
    doc = payload.model_dump()
    doc["id"] = uuid.uuid4().hex
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    await stores_col.insert_one(doc)
    await log_audit(user, "create_store", "store", doc["id"])
    doc.pop("_id", None)
    return doc


@router.get("/{store_id}")
async def get_store(store_id: str, user: dict = Depends(get_current_user)):
    s = await stores_col.find_one({"id": store_id}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Store not found")
    return s


@router.patch("/{store_id}")
async def update_store(store_id: str, updates: dict, user: dict = Depends(require_roles(*ADMIN_ROLES))):
    if "_id" in updates:
        del updates["_id"]
    if "id" in updates:
        del updates["id"]
    await stores_col.update_one({"id": store_id}, {"$set": updates})
    await log_audit(user, "update_store", "store", store_id, updates)
    return await stores_col.find_one({"id": store_id}, {"_id": 0})


@router.delete("/{store_id}")
async def delete_store(store_id: str, user: dict = Depends(require_roles(*ADMIN_ROLES))):
    await stores_col.update_one({"id": store_id}, {"$set": {"is_active": False}})
    await log_audit(user, "deactivate_store", "store", store_id)
    return {"success": True}


@router.post("/bulk-upload")
async def bulk_upload_stores(file: UploadFile = File(...), user: dict = Depends(require_roles(*ADMIN_ROLES))):
    import csv as _csv
    import io as _io
    content = await file.read()
    reader = _csv.DictReader(_io.StringIO(content.decode("utf-8")))
    inserted, skipped, errors = 0, 0, []
    for i, row in enumerate(reader, start=2):
        code = (row.get("code") or "").strip().upper()
        if not code:
            errors.append(f"Row {i}: missing code")
            continue
        if await stores_col.find_one({"code": code}):
            skipped += 1
            continue
        try:
            doc = {
                "id": uuid.uuid4().hex,
                "code": code,
                "name": row.get("name", "").strip(),
                "city": row.get("city", "").strip(),
                "state": row.get("state", "").strip(),
                "region": row.get("region", "").strip(),
                "address": row.get("address", "").strip(),
                "phone": row.get("phone"),
                "manager_name": row.get("manager_name"),
                "latitude": float(row.get("latitude") or 0) or None,
                "longitude": float(row.get("longitude") or 0) or None,
                "is_active": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await stores_col.insert_one(doc)
            inserted += 1
        except Exception as e:
            errors.append(f"Row {i}: {str(e)}")
    await log_audit(user, "bulk_upload_stores", "store", None, {"inserted": inserted, "skipped": skipped})
    return {"inserted": inserted, "skipped": skipped, "errors": errors[:20]}


@router.get("/sample-csv/download")
async def stores_sample_csv(user: dict = Depends(get_current_user)):
    from fastapi.responses import Response as FastAPIResponse
    csv_text = "code,name,city,state,region,address,phone,manager_name,latitude,longitude\nKZO-PUN-03,Kazo Pune - Phoenix,Pune,Maharashtra,West,Phoenix Marketcity Pune,9876543210,Sneha Kulkarni,18.5614,73.9151\n"
    return FastAPIResponse(content=csv_text, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=stores_sample.csv"})


# ============================================
# POS Integration API (called by ERP/POS systems)
# Logs every call into api_logs for live monitoring
# ============================================
pos_router = APIRouter(prefix="/pos", tags=["pos-integration"])


async def _log_api(endpoint: str, method: str, status: int, ms: int, customer_mobile: Optional[str] = None, bill_number: Optional[str] = None, error: Optional[str] = None, store_id: Optional[str] = None, payload: Optional[dict] = None):
    await api_logs_col.insert_one({
        "id": uuid.uuid4().hex,
        "endpoint": endpoint,
        "method": method,
        "status_code": status,
        "response_time_ms": ms,
        "customer_mobile": customer_mobile,
        "bill_number": bill_number,
        "error_reason": error,
        "store_id": store_id,
        "request_payload": payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@pos_router.post("/validate-customer")
async def validate_customer(body: dict):
    t0 = time.time()
    mobile = body.get("mobile", "").strip()
    if not mobile:
        await _log_api("/api/pos/validate-customer", "POST", 400, int((time.time() - t0) * 1000), error="missing mobile", payload=body)
        raise HTTPException(400, "Mobile required")
    cust = await customers_col.find_one({"mobile": mobile}, {"_id": 0})
    ms = int((time.time() - t0) * 1000)
    if not cust:
        await _log_api("/api/pos/validate-customer", "POST", 404, ms, customer_mobile=mobile, error="customer not found", payload=body)
        return {"exists": False}
    await _log_api("/api/pos/validate-customer", "POST", 200, ms, customer_mobile=mobile, payload=body)
    return {"exists": True, "name": cust.get("name"), "tier": cust.get("tier"), "points": cust.get("points_balance", 0)}


@pos_router.post("/issue-otp")
async def issue_otp(body: dict):
    t0 = time.time()
    mobile = body.get("mobile", "").strip()
    purpose = body.get("purpose", "redeem")
    if not mobile:
        await _log_api("/api/pos/issue-otp", "POST", 400, int((time.time() - t0) * 1000), error="missing mobile", payload=body)
        raise HTTPException(400, "Mobile required")
    otp = f"{random.randint(100000, 999999)}"
    await otp_col.insert_one({
        "id": uuid.uuid4().hex,
        "mobile": mobile,
        "otp": otp,
        "purpose": purpose,
        "verified": False,
        "expires_at": (datetime.now(timezone.utc).timestamp() + 300),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    ms = int((time.time() - t0) * 1000)
    await _log_api("/api/pos/issue-otp", "POST", 200, ms, customer_mobile=mobile, payload=body)
    return {"success": True, "otp_id": "***masked***", "demo_otp": otp}  # demo_otp only for development


@pos_router.post("/issue-points")
async def issue_points(body: dict):
    t0 = time.time()
    mobile = body.get("mobile")
    bill_number = body.get("bill_number")
    net_amount = body.get("net_amount", 0)
    store_id = body.get("store_id")
    items = body.get("items", [])
    if not mobile or not bill_number or not store_id:
        await _log_api("/api/pos/issue-points", "POST", 400, int((time.time() - t0) * 1000), error="missing required fields", payload=body, bill_number=bill_number, customer_mobile=mobile)
        raise HTTPException(400, "mobile, bill_number, store_id required")
    cust = await customers_col.find_one({"mobile": mobile}, {"_id": 0})
    if not cust:
        await _log_api("/api/pos/issue-points", "POST", 404, int((time.time() - t0) * 1000), error="customer not found", payload=body, bill_number=bill_number, customer_mobile=mobile)
        raise HTTPException(404, "Customer not found. Register first.")
    # Duplicate check
    dup = await transactions_col.find_one({"bill_number": bill_number, "store_id": store_id})
    if dup:
        await _log_api("/api/pos/issue-points", "POST", 409, int((time.time() - t0) * 1000), error="duplicate bill", payload=body, bill_number=bill_number, customer_mobile=mobile)
        raise HTTPException(409, "Bill already exists")
    cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0}) or {"earn_ratio": 1.0, "min_bill_for_earn": 0}
    earn_ratio = cfg.get("earn_ratio", 1.0)
    multiplier = 1.0
    for tr in cfg.get("tier_rules", []):
        if tr.get("tier") == cust.get("tier"):
            multiplier = tr.get("earn_multiplier", 1.0)
            break
    points = int(net_amount * earn_ratio * multiplier) if net_amount >= cfg.get("min_bill_for_earn", 0) else 0

    txn_id = uuid.uuid4().hex
    txn_doc = {
        "id": txn_id,
        "customer_id": cust["id"],
        "customer_mobile": mobile,
        "store_id": store_id,
        "bill_number": bill_number,
        "bill_date": datetime.now(timezone.utc).isoformat(),
        "gross_amount": body.get("gross_amount", net_amount),
        "discount_amount": body.get("discount_amount", 0),
        "net_amount": net_amount,
        "items": items,
        "payment_mode": body.get("payment_mode", "card"),
        "points_earned": points,
        "points_redeemed": 0,
        "coupon_code": body.get("coupon_code"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await transactions_col.insert_one(txn_doc)
    if points > 0:
        await points_ledger_col.insert_one({
            "id": uuid.uuid4().hex,
            "customer_id": cust["id"],
            "type": "earn",
            "points": points,
            "reference_type": "transaction",
            "reference_id": txn_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    await customers_col.update_one(
        {"id": cust["id"]},
        {"$inc": {"points_balance": points, "lifetime_points_earned": points, "lifetime_spend": net_amount, "visit_count": 1},
         "$set": {"last_visit_at": datetime.now(timezone.utc).isoformat()}}
    )
    ms = int((time.time() - t0) * 1000)
    await _log_api("/api/pos/issue-points", "POST", 200, ms, customer_mobile=mobile, bill_number=bill_number, store_id=store_id, payload=body)
    return {"success": True, "points_earned": points, "new_balance": cust["points_balance"] + points, "transaction_id": txn_id}


@pos_router.post("/redeem-points")
async def redeem_points(body: dict):
    t0 = time.time()
    mobile = body.get("mobile")
    points_to_redeem = int(body.get("points", 0))
    otp = body.get("otp", "")
    bill_number = body.get("bill_number")
    if not mobile or not points_to_redeem:
        await _log_api("/api/pos/redeem-points", "POST", 400, int((time.time() - t0) * 1000), error="missing fields", customer_mobile=mobile, bill_number=bill_number, payload=body)
        raise HTTPException(400, "Missing fields")
    cust = await customers_col.find_one({"mobile": mobile}, {"_id": 0})
    if not cust or cust.get("points_balance", 0) < points_to_redeem:
        await _log_api("/api/pos/redeem-points", "POST", 400, int((time.time() - t0) * 1000), error="insufficient points", customer_mobile=mobile, bill_number=bill_number, payload=body)
        raise HTTPException(400, "Insufficient points")
    # OTP check
    otp_doc = await otp_col.find_one({"mobile": mobile, "otp": otp, "verified": False}, {"_id": 0})
    if not otp_doc:
        await _log_api("/api/pos/redeem-points", "POST", 401, int((time.time() - t0) * 1000), error="invalid OTP", customer_mobile=mobile, bill_number=bill_number, payload=body)
        raise HTTPException(401, "Invalid OTP")
    await otp_col.update_one({"id": otp_doc["id"]}, {"$set": {"verified": True}})
    cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0}) or {"burn_ratio": 0.25}
    discount = points_to_redeem * cfg.get("burn_ratio", 0.25)
    await customers_col.update_one(
        {"id": cust["id"]},
        {"$inc": {"points_balance": -points_to_redeem, "lifetime_points_redeemed": points_to_redeem}}
    )
    await points_ledger_col.insert_one({
        "id": uuid.uuid4().hex,
        "customer_id": cust["id"],
        "type": "redeem",
        "points": -points_to_redeem,
        "reference_type": "transaction",
        "reference_id": bill_number,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    ms = int((time.time() - t0) * 1000)
    await _log_api("/api/pos/redeem-points", "POST", 200, ms, customer_mobile=mobile, bill_number=bill_number, payload=body)
    return {"success": True, "discount": discount, "remaining_balance": cust["points_balance"] - points_to_redeem}


@pos_router.post("/redeem-coupon")
async def pos_redeem_coupon(body: dict):
    t0 = time.time()
    code = (body.get("code") or "").upper()
    mobile = body.get("mobile")
    bill_amount = float(body.get("bill_amount", 0))
    bill_number = body.get("bill_number")
    store_id = body.get("store_id")
    c = await coupons_col.find_one({"code": code}, {"_id": 0})
    if not c:
        await _log_api("/api/pos/redeem-coupon", "POST", 404, int((time.time() - t0) * 1000), error="invalid code", customer_mobile=mobile, bill_number=bill_number, payload=body)
        raise HTTPException(404, "Invalid coupon code")
    if c["coupon_type"] == "flat":
        discount = c["discount_value"]
    elif c["coupon_type"] == "percentage":
        discount = bill_amount * c["discount_value"] / 100
        if c.get("max_discount"):
            discount = min(discount, c["max_discount"])
    else:
        discount = c["discount_value"]
    await coupons_col.update_one({"id": c["id"]}, {"$inc": {"times_used": 1}})
    ms = int((time.time() - t0) * 1000)
    await _log_api("/api/pos/redeem-coupon", "POST", 200, ms, customer_mobile=mobile, bill_number=bill_number, store_id=store_id, payload=body)
    return {"success": True, "discount": round(discount, 2), "coupon": c["code"]}
