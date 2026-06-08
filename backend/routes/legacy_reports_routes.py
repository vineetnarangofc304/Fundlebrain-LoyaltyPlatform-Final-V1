"""Legacy Reports — mirrors newu.fundlezone.com's Analytics > Detailed section.

Twelve reports replicating Fundle's legacy operational reports:
    1. Customer Data           (raw customer list with all filters)
    2. Transaction Data        (raw bill list across all customers)
    3. Repeat Customers        (customers with 2+ visits)
    4. Top Customers           (top N by visits or purchase)
    5. Fraud Report            (anomaly flags)
    6. Pending Bills           (bills awaiting processing / point-award)
    7. Feedback Data           (customer feedback responses)
    8. Missed Call Requests    (IVR / missed-call captures)
    9. Location Wise Customer  (customer count per store)
   10. Expiry Points Report    (points expiring in N days)
   11. Active Coupon Report    (currently-issued unused coupons)
   12. Live Monitor stream     (delegate to existing live monitor)

Every endpoint supports:
    - start_date / end_date (YYYY-MM-DD)
    - q (search / mobile / name)
    - location_id / city / state / zone / tier
    - limit / offset (pagination)
    - export=csv (alternative CSV stream)
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from auth import get_current_user
from database import (
    customers_col, transactions_col, stores_col,
    coupons_col, points_ledger_col, nps_col,
)
from routes._loyalty import LOYALTY_TX_MATCH

logger = logging.getLogger("kazo-fundle.legacy_reports")
router = APIRouter(prefix="/legacy-reports", tags=["legacy-reports"])


def _date_filter(start_date: Optional[str], end_date: Optional[str], field: str = "bill_date") -> Dict[str, Any]:
    """Build a bill_date filter — inclusive of end_date."""
    if not (start_date and end_date):
        return {}
    return {field: {"$gte": start_date, "$lte": end_date + "T23:59:59Z"}}


async def _location_filter(location_id: Optional[str], city: Optional[str], state: Optional[str], zone: Optional[str]) -> Dict[str, Any]:
    """Resolve a city/state/zone choice into a list of store_ids."""
    if location_id:
        return {"store_id": location_id}
    sf: Dict[str, Any] = {}
    if city:
        sf["city"] = city
    if state:
        sf["state"] = state
    if zone:
        sf["zone"] = zone
    if not sf:
        return {}
    ids = [s["id"] async for s in stores_col.find(sf, {"id": 1, "_id": 0})]
    return {"store_id": {"$in": ids}} if ids else {"store_id": "__none__"}


def _to_csv(rows: List[Dict], columns: List[str]) -> StreamingResponse:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(columns)
    for r in rows:
        w.writerow([r.get(c, "") for c in columns])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="report.csv"'})


# ============================================================
# 1) Customer Data — raw customer list
# ============================================================
@router.get("/customer-data")
async def customer_data_report(
    q: Optional[str] = None,
    location_id: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    zone: Optional[str] = None,
    tier: Optional[str] = None,
    start_date: Optional[str] = None,  # registered between
    end_date: Optional[str] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    export: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    fil: Dict[str, Any] = {}
    if q:
        digits = "".join(ch for ch in q if ch.isdigit())
        if digits and len(digits) >= 4:
            fil["mobile"] = {"$regex": digits}
        else:
            fil["$or"] = [
                {"mobile": {"$regex": q, "$options": "i"}},
                {"name": {"$regex": q, "$options": "i"}},
                {"email": {"$regex": q, "$options": "i"}},
            ]
    if tier:
        fil["tier"] = tier
    locf = await _location_filter(location_id, city, state, zone)
    if locf.get("store_id"):
        if isinstance(locf["store_id"], str):
            fil["home_store_id"] = locf["store_id"]
        else:
            fil["home_store_id"] = locf["store_id"]
    if start_date and end_date:
        fil["created_at"] = {"$gte": start_date, "$lte": end_date + "T23:59:59Z"}

    total = await customers_col.count_documents(fil)
    rows = await customers_col.find(fil, {"_id": 0}).sort("created_at", -1).skip(offset).limit(limit).to_list(limit)

    if export == "csv":
        cols = ["mobile", "name", "email", "tier", "home_store_id", "visit_count",
                "lifetime_spend", "points_balance", "created_at", "is_active"]
        return _to_csv(rows, cols)
    return {"total": total, "rows": rows, "offset": offset, "limit": limit}


# ============================================================
# 2) Transaction Data — raw transactions list
# ============================================================
@router.get("/transaction-data")
async def transaction_data_report(
    q: Optional[str] = None,
    location_id: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    zone: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    export: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    fil: Dict[str, Any] = dict(LOYALTY_TX_MATCH)
    fil.update(_date_filter(start_date, end_date))
    locf = await _location_filter(location_id, city, state, zone)
    fil.update(locf)
    if q:
        digits = "".join(ch for ch in q if ch.isdigit())
        if digits:
            fil["$or"] = [{"customer_mobile": {"$regex": digits}}, {"bill_number": {"$regex": q, "$options": "i"}}]

    total = await transactions_col.count_documents(fil)
    rows = await transactions_col.find(fil, {"_id": 0}).sort("bill_date", -1).skip(offset).limit(limit).to_list(limit)

    if export == "csv":
        cols = ["bill_date", "bill_number", "customer_mobile", "store_id", "net_amount",
                "gross_amount", "points_earned", "points_redeemed"]
        return _to_csv(rows, cols)
    return {"total": total, "rows": rows, "offset": offset, "limit": limit}


# ============================================================
# 3) Repeat Customers
# ============================================================
@router.get("/repeat-customers")
async def repeat_customers_report(
    location_id: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    zone: Optional[str] = None,
    min_visits: int = 2,
    start_date: Optional[str] = None,  # last visit between
    end_date: Optional[str] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    export: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    fil: Dict[str, Any] = {"visit_count": {"$gte": min_visits}}
    locf = await _location_filter(location_id, city, state, zone)
    if locf.get("store_id"):
        fil["home_store_id"] = locf["store_id"]
    fil.update(_date_filter(start_date, end_date, "last_visit_at"))

    total = await customers_col.count_documents(fil)
    rows = await customers_col.find(fil, {"_id": 0}).sort("visit_count", -1).skip(offset).limit(limit).to_list(limit)

    if export == "csv":
        cols = ["mobile", "name", "tier", "visit_count", "lifetime_spend", "last_bill_date", "home_store_id"]
        return _to_csv(rows, cols)
    return {"total": total, "rows": rows, "offset": offset, "limit": limit}


# ============================================================
# 4) Top Customers
# ============================================================
@router.get("/top-customers")
async def top_customers_report(
    by: str = "purchase",       # purchase | visits | points
    location_id: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    zone: Optional[str] = None,
    tier: Optional[str] = None,
    start_date: Optional[str] = None,  # last visit between
    end_date: Optional[str] = None,
    limit: int = Query(50, le=500),
    export: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    fil: Dict[str, Any] = {}
    locf = await _location_filter(location_id, city, state, zone)
    if locf.get("store_id"):
        fil["home_store_id"] = locf["store_id"]
    if tier:
        fil["tier"] = tier
    fil.update(_date_filter(start_date, end_date, "last_visit_at"))

    sort_field = {"purchase": "lifetime_spend", "visits": "visit_count", "points": "points_balance"}.get(by, "lifetime_spend")
    rows = await customers_col.find(fil, {"_id": 0}).sort(sort_field, -1).limit(limit).to_list(limit)
    if export == "csv":
        cols = ["mobile", "name", "tier", "visit_count", "lifetime_spend", "points_balance", "home_store_id"]
        return _to_csv(rows, cols)
    return {"rows": rows, "sort_by": sort_field, "limit": limit}


# ============================================================
# 5) Fraud Report — anomaly detection (simple heuristics)
# ============================================================
@router.get("/fraud-report")
async def fraud_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(200, le=1000),
    user: dict = Depends(get_current_user),
):
    """Flags suspicious patterns:
        - Multiple bills from same mobile within 60 minutes (rapid-fire)
        - Single redemption > 10,000 points
        - Customer redeemed > 80% of their lifetime earnings
    """
    flags: List[Dict[str, Any]] = []

    dfil = _date_filter(start_date, end_date) or {}
    # Rapid-fire bills: group by (mobile, hour-bucket) where count >= 3
    pipeline_rapid = [
        {"$match": {**LOYALTY_TX_MATCH, **dfil}},
        {"$project": {"customer_mobile": 1, "bill_number": 1, "bill_date": 1, "net_amount": 1,
                      "store_id": 1, "hour_bucket": {"$substr": ["$bill_date", 0, 13]}}},
        {"$group": {"_id": {"mobile": "$customer_mobile", "hour": "$hour_bucket"},
                    "bills": {"$sum": 1},
                    "total_amount": {"$sum": "$net_amount"},
                    "bill_numbers": {"$push": "$bill_number"},
                    "stores": {"$addToSet": "$store_id"}}},
        {"$match": {"bills": {"$gte": 3}}},
        {"$sort": {"bills": -1}},
        {"$limit": limit // 2 or 50},
    ]
    async for d in transactions_col.aggregate(pipeline_rapid):
        flags.append({
            "type": "rapid_fire_bills",
            "severity": "high" if d["bills"] >= 5 else "medium",
            "customer_mobile": d["_id"]["mobile"],
            "hour": d["_id"]["hour"],
            "bill_count": d["bills"],
            "total_amount": d["total_amount"],
            "bill_numbers": d["bill_numbers"][:10],
            "store_count": len(d["stores"]),
        })

    # Large single redemption (>10000)
    async for r in points_ledger_col.find(
        {"type": {"$in": ["redeem", "redemption"]}, "points": {"$lte": -10000}},
        {"_id": 0},
    ).sort("created_at", -1).limit(50):
        flags.append({
            "type": "large_redemption",
            "severity": "medium",
            "customer_mobile": r.get("customer_mobile"),
            "points": abs(r.get("points", 0)),
            "bill_number": r.get("bill_number"),
            "ledger_id": r.get("id"),
            "created_at": r.get("created_at"),
        })

    flags.sort(key=lambda f: (-{"high": 3, "medium": 2, "low": 1}.get(f.get("severity", "low"), 0)))
    return {"total": len(flags), "flags": flags[:limit]}


# ============================================================
# 6) Pending Bills — bills uploaded but not yet awarded points
# ============================================================
@router.get("/pending-bills")
async def pending_bills_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    location_id: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    zone: Optional[str] = None,
    limit: int = Query(200, le=1000),
    export: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Bills that exist in DB but have no points_earned (0 or null)."""
    fil: Dict[str, Any] = {
        **LOYALTY_TX_MATCH,
        "$or": [
            {"points_earned": {"$in": [0, None]}},
            {"points_earned": {"$exists": False}},
        ],
    }
    fil.update(_date_filter(start_date, end_date))
    locf = await _location_filter(location_id, city, state, zone)
    if locf:
        fil.update(locf)

    total = await transactions_col.count_documents(fil)
    rows = await transactions_col.find(fil, {"_id": 0}).sort("bill_date", -1).limit(limit).to_list(limit)
    if export == "csv":
        cols = ["bill_date", "bill_number", "customer_mobile", "store_id", "net_amount", "points_earned"]
        return _to_csv(rows, cols)
    return {"total": total, "rows": rows}


# ============================================================
# 7) Feedback Data — customer feedback entries (drawn from nps_responses)
# ============================================================
@router.get("/feedback-data")
async def feedback_data_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    bucket: Optional[str] = None,   # promoter | passive | detractor
    has_comment: Optional[bool] = None,
    limit: int = Query(200, le=1000),
    export: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    fil: Dict[str, Any] = {}
    if start_date and end_date:
        fil["created_at"] = {"$gte": start_date, "$lte": end_date + "T23:59:59Z"}
    if bucket:
        fil["bucket"] = bucket
    if has_comment is True:
        fil["feedback"] = {"$nin": [None, ""]}
    if has_comment is False:
        fil["$or"] = [{"feedback": None}, {"feedback": ""}, {"feedback": {"$exists": False}}]
    total = await nps_col.count_documents(fil)
    rows = await nps_col.find(fil, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    if export == "csv":
        cols = ["created_at", "mobile", "score", "bucket", "feedback", "store_id"]
        return _to_csv(rows, cols)
    return {"total": total, "rows": rows}


# ============================================================
# 8) Missed Call Requests — placeholder (no IVR integration yet)
# ============================================================
@router.get("/missed-calls")
async def missed_calls_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(200, le=1000),
    user: dict = Depends(get_current_user),
):
    """Returns IVR / missed-call captures.

    Currently empty — surface ready for future IVR integration.
    Schema kept compatible with legacy Fundle's columns.
    """
    return {
        "total": 0,
        "rows": [],
        "note": "No IVR / missed-call provider integrated yet. Surface ready for future hook.",
        "expected_columns": ["received_at", "mobile", "campaign_code", "status", "store_id"],
    }


# ============================================================
# 9) Location Wise Customer
# ============================================================
@router.get("/location-wise-customers")
async def location_wise_customers_report(
    state: Optional[str] = None,
    zone: Optional[str] = None,
    start_date: Optional[str] = None,  # last visit between
    end_date: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """Customer counts grouped by home_store_id."""
    match: Dict[str, Any] = {"home_store_id": {"$exists": True, "$ne": None}}
    match.update(_date_filter(start_date, end_date, "last_visit_at"))
    pipeline = [
        {"$match": match},
        {"$group": {"_id": "$home_store_id", "customer_count": {"$sum": 1},
                    "lifetime_spend": {"$sum": "$lifetime_spend"},
                    "total_visits": {"$sum": "$visit_count"}}},
        {"$sort": {"customer_count": -1}},
    ]
    rows: List[Dict[str, Any]] = []
    async for d in customers_col.aggregate(pipeline):
        store = await stores_col.find_one({"id": d["_id"]}, {"_id": 0, "name": 1, "city": 1, "state": 1, "zone": 1, "code": 1})
        if state and store and store.get("state") != state:
            continue
        if zone and store and store.get("zone") != zone:
            continue
        rows.append({
            "store_id": d["_id"],
            "store_name": (store or {}).get("name") or d["_id"],
            "store_code": (store or {}).get("code"),
            "city": (store or {}).get("city"),
            "state": (store or {}).get("state"),
            "zone": (store or {}).get("zone"),
            "customer_count": d["customer_count"],
            "lifetime_spend": d.get("lifetime_spend", 0),
            "total_visits": d.get("total_visits", 0),
        })
    return {"total": len(rows), "rows": rows}


# ============================================================
# 10) Expiry Points Report — by customer
# ============================================================
@router.get("/expiry-points")
async def expiry_points_report(
    days_ahead: int = Query(60, ge=1, le=365),
    location_id: Optional[str] = None,
    tier: Optional[str] = None,
    start_date: Optional[str] = None,  # expiry window override
    end_date: Optional[str] = None,
    limit: int = Query(500, le=2000),
    export: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """List customers whose points will expire within N days.

    Uses points_ledger entries with expires_at <= now + days_ahead and not yet expired.
    When start_date/end_date are supplied they override the relative window and match
    points expiring inside that explicit date range.
    """
    now = datetime.now(timezone.utc)
    if start_date and end_date:
        expiry_match = {"$gte": start_date, "$lte": end_date + "T23:59:59Z"}
    else:
        cutoff = (now + timedelta(days=days_ahead)).isoformat()
        expiry_match = {"$lte": cutoff, "$gte": now.isoformat()}

    pipeline = [
        {"$match": {
            "type": {"$in": ["earn", "bonus", "opening"]},
            "expires_at": {"$exists": True, "$ne": None, **expiry_match},
            "reversed": {"$ne": True},
        }},
        {"$group": {
            "_id": "$customer_mobile",
            "expiring_points": {"$sum": "$points"},
            "earliest_expiry": {"$min": "$expires_at"},
            "entry_count": {"$sum": 1},
        }},
        {"$sort": {"expiring_points": -1}},
        {"$limit": limit},
    ]
    rows = []
    async for d in points_ledger_col.aggregate(pipeline):
        cust = await customers_col.find_one(
            {"mobile": d["_id"]},
            {"_id": 0, "name": 1, "tier": 1, "home_store_id": 1, "points_balance": 1},
        )
        if not cust:
            continue
        if tier and cust.get("tier") != tier:
            continue
        if location_id and cust.get("home_store_id") != location_id:
            continue
        rows.append({
            "mobile": d["_id"],
            "name": cust.get("name"),
            "tier": cust.get("tier"),
            "home_store_id": cust.get("home_store_id"),
            "points_balance": cust.get("points_balance", 0),
            "expiring_points": d["expiring_points"],
            "earliest_expiry": d["earliest_expiry"],
            "ledger_entries": d["entry_count"],
        })

    if export == "csv":
        cols = ["mobile", "name", "tier", "home_store_id", "points_balance",
                "expiring_points", "earliest_expiry"]
        return _to_csv(rows, cols)
    return {"total": len(rows), "rows": rows, "days_ahead": days_ahead}


# ============================================================
# 11) Active Coupon Report — issued coupons not yet redeemed
# ============================================================
@router.get("/active-coupons")
async def active_coupons_report(
    code_prefix: Optional[str] = None,
    customer_mobile: Optional[str] = None,
    expiring_within_days: Optional[int] = None,
    start_date: Optional[str] = None,  # issued between
    end_date: Optional[str] = None,
    limit: int = Query(500, le=2000),
    export: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    fil: Dict[str, Any] = {"is_active": True}
    if code_prefix:
        fil["code"] = {"$regex": f"^{code_prefix}", "$options": "i"}
    if customer_mobile:
        digits = "".join(ch for ch in customer_mobile if ch.isdigit())
        if digits:
            fil["customer_mobile"] = {"$regex": digits}
    if expiring_within_days:
        cutoff = (datetime.now(timezone.utc) + timedelta(days=expiring_within_days)).isoformat()
        fil["valid_to"] = {"$lte": cutoff}
    fil.update(_date_filter(start_date, end_date, "created_at"))

    total = await coupons_col.count_documents(fil)
    rows = await coupons_col.find(fil, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    if export == "csv":
        cols = ["code", "customer_mobile", "discount_type", "discount_value",
                "valid_from", "valid_to", "uses_count", "max_uses", "created_at"]
        return _to_csv(rows, cols)
    return {"total": total, "rows": rows}
