"""Live Monitor — real-time cockpit data for ALL bills/transactions.

Powers `/enterprise/live-monitor` and serves as a strong report dashboard.
Bills WITH mobile = green; bills WITHOUT mobile = red "Lost Opportunity".
"""
from __future__ import annotations
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from database import transactions_col, customers_col, stores_col
from auth import require_roles

router = APIRouter(prefix="/live-monitor", tags=["live-monitor"])


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


@router.get("/transactions")
async def live_transactions(
    limit: int = Query(200, ge=1, le=2000),
    since: Optional[str] = Query(None, description="ISO timestamp — return only newer bills"),
    store_id: Optional[str] = None,
    store_code: Optional[str] = None,
    city: Optional[str] = None,
    zone: Optional[str] = None,
    region: Optional[str] = None,
    has_mobile: Optional[str] = Query(None, description="all | yes | no — filter by mobile presence"),
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    payment_mode: Optional[str] = None,
    source: Optional[str] = Query(None, description="pos_ewards | historic_upload | etc"),
    is_return: Optional[bool] = None,
    user: dict = Depends(require_roles("super_admin", "brand_admin", "crm_manager",
                                         "marketing_manager", "regional_manager",
                                         "analytics_viewer", "readonly_executive")),
):
    """Paginated list of recent transactions for the cockpit table."""
    fil: dict = {}
    if since:
        fil["bill_date"] = {"$gt": since}
    if store_id:
        fil["store_id"] = store_id
    if store_code:
        s = await stores_col.find_one({"code": store_code}, {"_id": 0, "id": 1})
        if s:
            fil["store_id"] = s["id"]
    if city:
        fil["city"] = city
    if zone:
        fil["zone"] = zone
    if source:
        fil["source"] = source
    if is_return is not None:
        fil["is_return"] = is_return
    if has_mobile == "yes":
        fil["customer_mobile"] = {"$exists": True, "$nin": [None, ""]}
    elif has_mobile == "no":
        fil["$or"] = [
            {"customer_mobile": {"$in": [None, ""]}},
            {"customer_mobile": {"$exists": False}},
        ]
    if min_amount is not None or max_amount is not None:
        amt_fil: dict = {}
        if min_amount is not None:
            amt_fil["$gte"] = min_amount
        if max_amount is not None:
            amt_fil["$lte"] = max_amount
        fil["net_amount"] = amt_fil
    if payment_mode:
        fil["payment_mode"] = payment_mode

    # Region filter: resolve via stores
    if region:
        store_ids = [s["id"] async for s in stores_col.find({"region": region}, {"_id": 0, "id": 1})]
        fil["store_id"] = {"$in": store_ids}

    rows = await transactions_col.find(fil, {"_id": 0}).sort("bill_date", -1).limit(limit).to_list(limit)

    # Enrich with customer name (best-effort batch)
    mobiles = list({r.get("customer_mobile") for r in rows if r.get("customer_mobile")})
    cust_map = {}
    if mobiles:
        async for c in customers_col.find({"mobile": {"$in": mobiles}},
                                            {"_id": 0, "mobile": 1, "name": 1, "tier": 1, "points_balance": 1}):
            cust_map[c["mobile"]] = c

    enriched = []
    for r in rows:
        mob = r.get("customer_mobile")
        c = cust_map.get(mob) if mob else None
        enriched.append({
            "id": r.get("id"),
            "bill_number": r.get("bill_number"),
            "bill_date": r.get("bill_date"),
            "store_id": r.get("store_id"),
            "store_name": r.get("store_name"),
            "store_code": r.get("store_code"),
            "city": r.get("city"),
            "zone": r.get("zone"),
            "customer_mobile": mob,
            "customer_name": r.get("customer_name") or (c.get("name") if c else None),
            "tier": (c.get("tier") if c else None) or r.get("tier"),
            "current_points": (c.get("points_balance") if c else None),
            "gross_amount": r.get("gross_amount"),
            "net_amount": r.get("net_amount"),
            "final_amount": r.get("final_amount"),
            "discount_amount": r.get("discount_amount"),
            "points_earned": r.get("points_earned", 0),
            "points_redeemed": r.get("points_redeemed", 0),
            "payment_mode": r.get("payment_mode"),
            "is_return": r.get("is_return", False),
            "source": r.get("source"),
            "items_count": len(r.get("items") or []),
            "has_mobile": bool(mob),
            "lost_opportunity": not bool(mob),
        })
    return {"rows": enriched, "count": len(enriched), "as_of": _now_iso()}


@router.get("/stats")
async def live_stats(
    minutes: int = Query(60, ge=1, le=525600),  # up to 365 days (1 year)
    user: dict = Depends(require_roles("super_admin", "brand_admin", "crm_manager",
                                         "marketing_manager", "regional_manager",
                                         "analytics_viewer", "readonly_executive")),
):
    """Top KPIs for the cockpit: bills, revenue, mobile-attach rate, lost opportunities."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    pipe_total = [
        {"$match": {"bill_date": {"$gte": cutoff}}},
        {"$group": {
            "_id": None,
            "bills": {"$sum": 1},
            "revenue": {"$sum": "$net_amount"},
            "bills_with_mobile": {
                "$sum": {"$cond": [
                    {"$and": [{"$ne": ["$customer_mobile", None]},
                                {"$ne": ["$customer_mobile", ""]}]},
                    1, 0,
                ]}
            },
            "revenue_with_mobile": {
                "$sum": {"$cond": [
                    {"$and": [{"$ne": ["$customer_mobile", None]},
                                {"$ne": ["$customer_mobile", ""]}]},
                    "$net_amount", 0,
                ]}
            },
            "points_earned": {"$sum": "$points_earned"},
            "points_redeemed": {"$sum": "$points_redeemed"},
            "returns": {"$sum": {"$cond": ["$is_return", 1, 0]}},
        }},
    ]
    res = await transactions_col.aggregate(pipe_total).to_list(1)
    base = res[0] if res else {}
    bills = base.get("bills", 0) or 0
    with_mob = base.get("bills_with_mobile", 0) or 0
    lost = bills - with_mob
    revenue = float(base.get("revenue") or 0)
    rev_with = float(base.get("revenue_with_mobile") or 0)
    attach_rate = (with_mob / bills * 100) if bills else 0.0

    # Repeat bills — bills whose customer_mobile appears 2+ times in the window
    repeat_pipe = [
        {"$match": {"bill_date": {"$gte": cutoff},
                     "customer_mobile": {"$nin": [None, ""]}}},
        {"$group": {"_id": "$customer_mobile", "n": {"$sum": 1}}},
        {"$match": {"n": {"$gte": 2}}},
        {"$group": {"_id": None,
                     "repeat_customers": {"$sum": 1},
                     "repeat_bills": {"$sum": "$n"}}},
    ]
    rr = await transactions_col.aggregate(repeat_pipe).to_list(1)
    rr_doc = rr[0] if rr else {}
    repeat_bills = int(rr_doc.get("repeat_bills") or 0)
    repeat_customers = int(rr_doc.get("repeat_customers") or 0)

    # Per-store top performers
    pipe_store = [
        {"$match": {"bill_date": {"$gte": cutoff}}},
        {"$group": {
            "_id": "$store_id",
            "store_name": {"$first": "$store_name"},
            "bills": {"$sum": 1},
            "revenue": {"$sum": "$net_amount"},
            "bills_with_mobile": {
                "$sum": {"$cond": [
                    {"$and": [{"$ne": ["$customer_mobile", None]},
                                {"$ne": ["$customer_mobile", ""]}]},
                    1, 0,
                ]}
            },
        }},
        {"$sort": {"revenue": -1}},
        {"$limit": 10},
    ]
    by_store = await transactions_col.aggregate(pipe_store).to_list(10)

    return {
        "window_minutes": minutes,
        "as_of": _now_iso(),
        "bills_total": bills,
        "bills_with_mobile": with_mob,
        "bills_without_mobile": lost,
        "repeat_bills": repeat_bills,
        "repeat_customers": repeat_customers,
        "mobile_attach_rate_pct": round(attach_rate, 2),
        "revenue_total": round(revenue, 2),
        "revenue_with_mobile": round(rev_with, 2),
        "revenue_lost": round(revenue - rev_with, 2),
        "points_earned": int(base.get("points_earned") or 0),
        "points_redeemed": int(base.get("points_redeemed") or 0),
        "returns": int(base.get("returns") or 0),
        "by_store_top10": [
            {
                "store_id": s.get("_id"),
                "store_name": s.get("store_name") or "Unknown",
                "bills": s.get("bills", 0),
                "revenue": round(s.get("revenue", 0) or 0, 2),
                "bills_with_mobile": s.get("bills_with_mobile", 0),
                "attach_rate_pct": round(
                    (s.get("bills_with_mobile", 0) / s.get("bills", 1) * 100) if s.get("bills") else 0,
                    2,
                ),
            } for s in by_store
        ],
    }


# ---------------- POS Credentials (admin-only) ----------------
admin_router = APIRouter(prefix="/admin/pos-credentials", tags=["pos-credentials-admin"])


class POSCredCreate(BaseModel):
    label: str
    merchant_id: str
    customer_key: str
    store_id: Optional[str] = None
    note: Optional[str] = None


@admin_router.get("")
async def list_pos_credentials(
    user: dict = Depends(require_roles("super_admin", "brand_admin")),
):
    from database import db
    rows = await db["pos_credentials"].find({}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {"credentials": rows}


@admin_router.post("")
async def create_pos_credential(
    body: POSCredCreate,
    user: dict = Depends(require_roles("super_admin", "brand_admin")),
):
    from database import db
    if await db["pos_credentials"].find_one({"label": body.label, "is_active": True}):
        raise HTTPException(400, "Label already in use for an active credential")
    api_key = secrets.token_urlsafe(32)
    doc = {
        "id": uuid.uuid4().hex,
        "label": body.label,
        "merchant_id": body.merchant_id,
        "customer_key": body.customer_key,
        "store_id": body.store_id,
        "api_key": api_key,
        "note": body.note,
        "is_active": True,
        "created_at": _now_iso(),
        "created_by": user.get("email"),
    }
    await db["pos_credentials"].insert_one(doc)
    doc.pop("_id", None)
    return doc


@admin_router.post("/{cred_id}/rotate")
async def rotate_pos_credential(cred_id: str,
                                  user: dict = Depends(require_roles("super_admin", "brand_admin"))):
    from database import db
    new_key = secrets.token_urlsafe(32)
    res = await db["pos_credentials"].update_one(
        {"id": cred_id},
        {"$set": {"api_key": new_key, "rotated_at": _now_iso(),
                   "rotated_by": user.get("email")}},
    )
    if not res.matched_count:
        raise HTTPException(404, "Credential not found")
    return await db["pos_credentials"].find_one({"id": cred_id}, {"_id": 0})


@admin_router.post("/{cred_id}/deactivate")
async def deactivate_pos_credential(cred_id: str,
                                       user: dict = Depends(require_roles("super_admin", "brand_admin"))):
    from database import db
    res = await db["pos_credentials"].update_one(
        {"id": cred_id},
        {"$set": {"is_active": False, "deactivated_at": _now_iso(),
                   "deactivated_by": user.get("email")}},
    )
    if not res.matched_count:
        raise HTTPException(404, "Credential not found")
    return {"ok": True}


# ---------------- API Logs viewer (full request + response, admin only) ----------------
log_router = APIRouter(prefix="/api-monitor", tags=["api-monitor-detail"])


@log_router.get("/log/{log_id}")
async def get_api_log_detail(log_id: str,
                              user: dict = Depends(require_roles("super_admin", "brand_admin",
                                                                   "crm_manager", "marketing_manager"))):
    from database import api_logs_col
    row = await api_logs_col.find_one({"id": log_id}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Log not found")
    return row


@log_router.get("/logs")
async def list_api_logs(
    limit: int = Query(100, le=500),
    endpoint: Optional[str] = None,
    status_code: Optional[int] = None,
    method: Optional[str] = None,
    customer_mobile: Optional[str] = None,
    bill_number: Optional[str] = None,
    source: Optional[str] = None,
    since: Optional[str] = None,
    user: dict = Depends(require_roles("super_admin", "brand_admin",
                                         "crm_manager", "marketing_manager")),
):
    from database import api_logs_col
    fil: dict = {}
    if endpoint:
        fil["endpoint"] = endpoint
    if status_code is not None:
        fil["status_code"] = status_code
    if method:
        fil["method"] = method.upper()
    if customer_mobile:
        fil["customer_mobile"] = customer_mobile
    if bill_number:
        fil["bill_number"] = bill_number
    if source:
        fil["source"] = source
    if since:
        fil["timestamp"] = {"$gte": since}
    rows = await api_logs_col.find(fil, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    return {"rows": rows, "count": len(rows)}
