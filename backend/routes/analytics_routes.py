"""Additional drill-down dashboards and entity-level detail views."""
from datetime import datetime, timezone, timedelta
import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.errors import PyMongoError
from database import transactions_col, customers_col, stores_col, campaigns_col, points_ledger_col, nps_col, coupons_col, coupon_redemptions_col
from auth import get_current_user
from routes._loyalty import loyalty_match, LOYALTY_TX_MATCH
from routes._db_timeout import db_deadline
from routes._dash_cache import dash_cache

logger = logging.getLogger("kazo-fundle.analytics")

router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=[Depends(db_deadline)])


def _start(period_days: int):
    """Return ISO timestamp of the lookback window start.

    `period_days <= 0` is a sentinel meaning **all time** — used by the
    frontend's "All time" filter so historical CSV uploads (whose bill dates
    can be years old) are included.
    """
    if period_days is None or period_days <= 0:
        period_days = 365 * 20
    return (datetime.now(timezone.utc) - timedelta(days=period_days)).isoformat()


# Drill-down: get a single transaction with full details
@router.get("/transaction/{txn_id}")
async def transaction_detail(txn_id: str, user: dict = Depends(get_current_user)):
    t = await transactions_col.find_one({"id": txn_id}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Transaction not found")
    customer = None
    if t.get("customer_id"):
        customer = await customers_col.find_one({"id": t["customer_id"]}, {"_id": 0})
    store = await stores_col.find_one({"id": t["store_id"]}, {"_id": 0})
    return {"transaction": t, "customer": customer, "store": store}


# Sales dashboard - hourly + weekday + payment breakdown
@router.get("/sales-dashboard")
@dash_cache("an-sales")
async def sales_dashboard(
    period_days: int = 30,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    from ._date_range import parse_date_range
    start_iso, end_iso = parse_date_range(start_date, end_date, period_days)
    start = start_iso or _start(period_days)
    bill_filter: Dict[str, Any] = {"$gte": start}
    if end_iso:
        bill_filter["$lt"] = end_iso

    # ONE scan via $facet (was 4 scans, 3 of which IGNORED the end bound) with
    # crash-proof date parsing — $dateFromString without onError throws on any
    # malformed bill_date and 500s the whole dashboard.
    _bill_dt = {"$cond": {
        "if": {"$eq": [{"$type": "$bill_date"}, "date"]},
        "then": "$bill_date",
        "else": {"$dateFromString": {"dateString": {"$ifNull": ["$bill_date", ""]}, "onError": None}},
    }}
    facet_pipe = [
        {"$match": loyalty_match({"bill_date": bill_filter})},
        {"$facet": {
            "hourly": [
                {"$project": {"dt": _bill_dt, "net_amount": 1}},
                {"$match": {"dt": {"$ne": None}}},
                {"$group": {"_id": {"$hour": "$dt"}, "net": {"$sum": "$net_amount"}, "count": {"$sum": 1}}},
                {"$sort": {"_id": 1}},
            ],
            "weekday": [
                {"$project": {"dt": _bill_dt, "net_amount": 1}},
                {"$match": {"dt": {"$ne": None}}},
                {"$group": {"_id": {"$dayOfWeek": "$dt"}, "net": {"$sum": "$net_amount"}, "count": {"$sum": 1}}},
                {"$sort": {"_id": 1}},
            ],
            "payment": [
                {"$group": {"_id": {"$ifNull": ["$payment_mode", "Unknown"]},
                            "net": {"$sum": "$net_amount"}, "count": {"$sum": 1}}},
                {"$sort": {"net": -1}},
            ],
            "discount": [
                {"$project": {
                    "bucket": {"$switch": {"branches": [
                        {"case": {"$eq": [{"$ifNull": ["$discount_amount", 0]}, 0]}, "then": "0%"},
                        {"case": {"$lte": ["$discount_amount", 500]}, "then": "<=₹500"},
                        {"case": {"$lte": ["$discount_amount", 1500]}, "then": "<=₹1500"},
                    ], "default": ">₹1500"}},
                    "net_amount": 1,
                }},
                {"$group": {"_id": "$bucket", "count": {"$sum": 1}, "net": {"$sum": "$net_amount"}}},
            ],
        }},
    ]
    res = await transactions_col.aggregate(facet_pipe, allowDiskUse=True).to_list(1)
    facet = res[0] if res else {}
    hourly = facet.get("hourly", [])
    weekday = facet.get("weekday", [])
    pay = facet.get("payment", [])
    disc = facet.get("discount", [])
    day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

    return {
        "hourly": [{"hour": r["_id"], "net": round(r["net"], 2), "count": r["count"]} for r in hourly],
        "weekday": [{"day": day_names[(r["_id"] - 1) % 7], "net": round(r["net"], 2), "count": r["count"]} for r in weekday],
        "payment_mix": [{"mode": r["_id"], "net": round(r["net"], 2), "count": r["count"]} for r in pay],
        "discount_distribution": [{"bucket": r["_id"], "count": r["count"], "net": round(r["net"], 2)} for r in disc],
    }


# Customer dashboard - RFM-style + cohorts
@router.get("/customer-dashboard")
@dash_cache("an-customer")
async def customer_dashboard(
    period_days: int = Query(0, ge=0, le=3650),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    from ._date_range import parse_date_range
    now = datetime.now(timezone.utc)
    start_iso, end_iso = parse_date_range(start_date, end_date, period_days)

    # R1: New customer trend uses first_purchase_at (actual first bill date), not created_at.
    # R5: loyalty members only (must have mobile)
    loyalty_q = {"mobile": {"$nin": [None, ""]}}
    if start_iso:
        rng = {"$gte": start_iso}
        if end_iso:
            rng["$lt"] = end_iso
        loyalty_q["last_visit_at"] = rng
    # New-customer trend respects the selected window (was hardcoded to last 90d
    # regardless of filter). Monthly buckets for long/all-time windows.
    trend_start = start_iso or (now - timedelta(days=90)).isoformat()
    fp_rng: Dict[str, Any] = {"$gte": trend_start} if start_iso else {"$gte": trend_start}
    if start_iso and end_iso:
        fp_rng["$lt"] = end_iso
    span_days = 90
    if start_iso:
        try:
            _s = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
            _e = datetime.fromisoformat(end_iso.replace("Z", "+00:00")) if end_iso else now
            span_days = (_e - _s).days
        except Exception:
            span_days = 90
    else:
        span_days = 90
    if period_days == 0 and not start_date:
        # all-time → monthly over the entire history
        fp_rng = {"$gt": ""}
        span_days = 10000
    key_len = 7 if span_days > 180 else 10
    new_pipe = [
        {"$match": {"mobile": {"$nin": [None, ""]}, "first_purchase_at": fp_rng}},
        {"$group": {"_id": {"$substr": ["$first_purchase_at", 0, key_len]}, "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    try:
        new_cust = await customers_col.aggregate(new_pipe, allowDiskUse=True).to_list(1200)
    except PyMongoError as e:
        logger.warning(f"customer-dashboard new_pipe timed out: {e}")
        new_cust = []

    # ---- Top spenders: cheap & index-backed (ix_cust_lifetime_spend), so keep it as its
    # own tiny query (reads ~10 docs via the index). ----
    top_pipe = [
        {"$match": {"mobile": {"$nin": [None, ""]}}},
        {"$sort": {"lifetime_spend": -1}}, {"$limit": 10},
        {"$project": {"_id": 0, "id": 1, "name": 1, "mobile": 1, "city": 1, "tier": 1, "lifetime_spend": 1, "visit_count": 1}},
    ]

    # ---- Everything else is a full-collection bucketing pass over the SAME loyalty members.
    # Running them as 7 separate aggregations meant 7 collection scans and blew past the 10s
    # server time limit on production-scale Atlas data (MaxTimeMSExpired). Collapse them into
    # ONE $facet so the collection is scanned a single time. ----
    _date_match = {"last_visit_at": loyalty_q["last_visit_at"]} if "last_visit_at" in loyalty_q else {}
    _recency_switch = {"$switch": {"branches": [
        {"case": {"$gte": ["$last_visit_at", (now - timedelta(days=7)).isoformat()]}, "then": "0-7d"},
        {"case": {"$gte": ["$last_visit_at", (now - timedelta(days=30)).isoformat()]}, "then": "8-30d"},
        {"case": {"$gte": ["$last_visit_at", (now - timedelta(days=90)).isoformat()]}, "then": "31-90d"},
        {"case": {"$gte": ["$last_visit_at", (now - timedelta(days=180)).isoformat()]}, "then": "91-180d"},
        {"case": {"$gte": ["$last_visit_at", (now - timedelta(days=365)).isoformat()]}, "then": "181-365d"},
    ], "default": "365d+"}}
    _facet = {
        "churn": [{"$group": {"_id": "$churn_risk", "count": {"$sum": 1}}}],
        "freq": [
            {"$project": {"bucket": {"$switch": {"branches": [
                {"case": {"$eq": ["$visit_count", 1]}, "then": "1 (one-time)"},
                {"case": {"$lte": ["$visit_count", 3]}, "then": "2-3"},
                {"case": {"$lte": ["$visit_count", 6]}, "then": "4-6"},
                {"case": {"$lte": ["$visit_count", 12]}, "then": "7-12"},
            ], "default": "13+"}}}},
            {"$group": {"_id": "$bucket", "count": {"$sum": 1}}},
        ],
        "city": [
            {"$group": {"_id": "$city", "count": {"$sum": 1}, "spend": {"$sum": "$lifetime_spend"}}},
            {"$sort": {"spend": -1}}, {"$limit": 15},
        ],
        "health": [
            *([{"$match": _date_match}] if _date_match else []),
            {"$project": {"bucket": {"$switch": {"branches": [
                {"case": {"$eq": [{"$ifNull": ["$last_visit_at", None]}, None]}, "then": "Never transacted"},
                {"case": {"$gte": ["$last_visit_at", (now - timedelta(days=30)).isoformat()]}, "then": "Healthy"},
                {"case": {"$gte": ["$last_visit_at", (now - timedelta(days=90)).isoformat()]}, "then": "Slipping"},
                {"case": {"$gte": ["$last_visit_at", (now - timedelta(days=180)).isoformat()]}, "then": "At Risk"},
            ], "default": "Lost"}}}},
            {"$group": {"_id": "$bucket", "count": {"$sum": 1}}},
        ],
        "recency": [
            {"$match": {"last_visit_at": {"$ne": None}}},
            {"$project": {"bucket": _recency_switch}},
            {"$group": {"_id": "$bucket", "count": {"$sum": 1}}},
        ],
        "onetimer": [
            {"$match": {**_date_match, "visit_count": 1, "last_visit_at": {"$ne": None}}},
            {"$project": {"bucket": _recency_switch}},
            {"$group": {"_id": "$bucket", "count": {"$sum": 1}}},
        ],
        "lifecycle": [
            *([{"$match": _date_match}] if _date_match else []),
            {"$group": {
                "_id": {"$switch": {"branches": [
                    {"case": {"$gte": [{"$ifNull": ["$visit_count", 0]}, 2]}, "then": "repeat"},
                    {"case": {"$eq": [{"$ifNull": ["$visit_count", 0]}, 1]}, "then": "one_timer"},
                ], "default": "zero_bill"}},
                "count": {"$sum": 1},
                "lifetime_spend": {"$sum": "$lifetime_spend"},
            }},
        ],
    }
    facet_pipe = [{"$match": {"mobile": {"$nin": [None, ""]}}}, {"$facet": _facet}]

    # Resilient: if a query still exceeds the server time limit on an extreme dataset, degrade
    # to empty buckets (HTTP 200) rather than 500-ing the whole dashboard.
    try:
        top = await customers_col.aggregate(top_pipe, allowDiskUse=True).to_list(10)
    except PyMongoError as e:
        logger.warning(f"customer-dashboard top_pipe timed out: {e}")
        top = []
    try:
        _fr = await customers_col.aggregate(facet_pipe, allowDiskUse=True).to_list(1)
        facet = _fr[0] if _fr else {}
    except PyMongoError as e:
        logger.warning(f"customer-dashboard facet timed out: {e}")
        facet = {}

    churn = facet.get("churn", [])
    freq = facet.get("freq", [])
    city = facet.get("city", [])

    HEALTH_ORDER = ["Healthy", "Slipping", "At Risk", "Lost", "Never transacted"]
    health_map = {r["_id"]: r["count"] for r in facet.get("health", [])}
    health_distribution = [{"bucket": b, "count": health_map.get(b, 0)} for b in HEALTH_ORDER]

    REC_ORDER = ["0-7d", "8-30d", "31-90d", "91-180d", "181-365d", "365d+"]
    rec_map = {r["_id"]: r["count"] for r in facet.get("recency", [])}
    recency_distribution = [{"bucket": b, "count": rec_map.get(b, 0)} for b in REC_ORDER]

    ot_map = {r["_id"]: r["count"] for r in facet.get("onetimer", [])}
    one_timer_recency_distribution = [{"bucket": b, "count": ot_map.get(b, 0)} for b in REC_ORDER]

    life_map = {r["_id"]: r for r in facet.get("lifecycle", [])}
    lifecycle_split = {
        "zero_bill": {
            "count": life_map.get("zero_bill", {}).get("count", 0),
            "lifetime_spend": round(life_map.get("zero_bill", {}).get("lifetime_spend", 0), 2),
        },
        "one_timer": {
            "count": life_map.get("one_timer", {}).get("count", 0),
            "lifetime_spend": round(life_map.get("one_timer", {}).get("lifetime_spend", 0), 2),
        },
        "repeat": {
            "count": life_map.get("repeat", {}).get("count", 0),
            "lifetime_spend": round(life_map.get("repeat", {}).get("lifetime_spend", 0), 2),
        },
    }

    return {
        "new_customer_trend": [{"date": r["_id"], "count": r["count"]} for r in new_cust],
        "churn_distribution": [{"risk": r["_id"] or "unscored", "count": r["count"]} for r in churn],
        "visit_frequency": [{"bucket": r["_id"], "count": r["count"]} for r in freq],
        "top_customers": top,
        "city_distribution": [{"city": r["_id"], "count": r["count"], "spend": round(r["spend"], 2)} for r in city],
        "health_distribution": health_distribution,
        "recency_distribution": recency_distribution,
        "one_timer_recency_distribution": one_timer_recency_distribution,
        "lifecycle_split": lifecycle_split,
    }


# Campaign performance dashboard
@router.get("/campaign-dashboard")
async def campaign_dashboard(user: dict = Depends(get_current_user)):
    all_camp = await campaigns_col.find({}, {"_id": 0}).sort("revenue_generated", -1).to_list(100)
    # Channel rollup
    by_channel = {}
    for c in all_camp:
        for ch in c.get("channels", []):
            d = by_channel.setdefault(ch, {"sent": 0, "delivered": 0, "redeemed": 0, "revenue": 0, "campaigns": 0})
            d["sent"] += c.get("sent", 0)
            d["delivered"] += c.get("delivered", 0)
            d["redeemed"] += c.get("redeemed", 0)
            d["revenue"] += c.get("revenue_generated", 0)
            d["campaigns"] += 1
    return {
        "all": all_camp,
        "by_channel": [{"channel": k, **v, "revenue": round(v["revenue"], 2)} for k, v in by_channel.items()],
    }


# Loyalty dashboard
@router.get("/loyalty-dashboard")
@dash_cache("an-loyalty")
async def loyalty_dashboard(
    period_days: int = Query(0, ge=0, le=3650),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    from ._date_range import parse_date_range
    # R5: loyalty members only (have mobile)
    loyalty_q: Dict[str, Any] = {"mobile": {"$nin": [None, ""]}}
    start_iso, end_iso = parse_date_range(start_date, end_date, period_days)
    if start_iso:
        rng = {"$gte": start_iso}
        if end_iso:
            rng["$lt"] = end_iso
        loyalty_q["last_visit_at"] = rng
    tier_pipe = [
        {"$match": loyalty_q},
        {"$group": {"_id": "$tier", "count": {"$sum": 1}, "avg_spend": {"$avg": "$lifetime_spend"},
                     "total_spend": {"$sum": "$lifetime_spend"}, "total_points": {"$sum": "$points_balance"}}},
        {"$sort": {"avg_spend": -1}},
    ]
    tiers = await customers_col.aggregate(tier_pipe, allowDiskUse=True).to_list(10)

    # Points issued vs redeemed trend — by BILL DATE (R1). Respects the selected
    # window (was hardcoded to last 90 days); monthly buckets for long windows.
    now_dt = datetime.now(timezone.utc)
    trend_start = start_iso or (now_dt - timedelta(days=90)).isoformat()
    span_days = 90
    if start_iso:
        try:
            _s = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
            _e = datetime.fromisoformat(end_iso.replace("Z", "+00:00")) if end_iso else now_dt
            span_days = (_e - _s).days
        except Exception:
            span_days = 90
    if period_days == 0 and not start_date:
        trend_start = "1900-01-01"
        span_days = 10000
    key_len = 7 if span_days > 180 else 10
    window_or = [{"bill_date": {"$gte": trend_start}},
                 {"bill_date": {"$exists": False}, "created_at": {"$gte": trend_start}}]
    # ledger entries written by ingest carry bill_date; older ones may only have created_at
    issued_pipe = [
        {"$match": {"$or": window_or}},
        {"$project": {
            "date": {"$substr": [{"$ifNull": ["$bill_date", "$created_at"]}, 0, key_len]},
            "type": 1, "points": 1,
        }},
        {"$group": {"_id": {"date": "$date", "type": "$type"}, "points": {"$sum": "$points"}}},
        {"$sort": {"_id.date": 1}},
    ]
    rows = await points_ledger_col.aggregate(issued_pipe, allowDiskUse=True).to_list(3000)
    by_date = {}
    for r in rows:
        d = r["_id"]["date"]
        t = r["_id"]["type"]
        v = by_date.setdefault(d, {"date": d, "issued": 0, "redeemed": 0, "bonus": 0})
        if t == "earn":
            v["issued"] = r["points"]
        elif t == "redeem":
            v["redeemed"] = abs(r["points"])
        elif t == "bonus":
            v["bonus"] = r["points"]
    return {
        "tiers": [{"tier": r["_id"], "count": r["count"], "avg_spend": round(r["avg_spend"], 2),
                    "total_spend": round(r.get("total_spend", 0), 2),
                    "total_points": int(r["total_points"])} for r in tiers],
        "points_trend": sorted(by_date.values(), key=lambda x: x["date"]),
    }


# Store performance dashboard
@router.get("/store-dashboard")
@dash_cache("an-store")
async def store_dashboard(
    period_days: int = 30,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    from ._date_range import parse_date_range
    start_iso, end_iso = parse_date_range(start_date, end_date, period_days)
    start = start_iso or _start(period_days)
    bill_rng: Dict[str, Any] = {"$gte": start}
    if end_iso:
        bill_rng["$lt"] = end_iso
    # Two-stage group: exact distinct visitors per store WITHOUT $addToSet
    # (which broke the 16MB group limit / 500'd at production scale).
    pipe = [
        {"$match": loyalty_match({"bill_date": bill_rng})},
        {"$group": {
            "_id": {"s": "$store_id", "m": "$customer_mobile"},
            "net": {"$sum": "$net_amount"},
            "txns": {"$sum": 1},
            "discount": {"$sum": "$discount_amount"},
        }},
        {"$group": {
            "_id": "$_id.s",
            "net": {"$sum": "$net"},
            "txns": {"$sum": "$txns"},
            "discount": {"$sum": "$discount"},
            "visitors": {"$sum": 1},
        }},
        {"$sort": {"net": -1}},
    ]
    rows = await transactions_col.aggregate(pipe, allowDiskUse=True).to_list(300)
    store_ids = [r["_id"] for r in rows]
    stores = {s["id"]: s async for s in stores_col.find({"id": {"$in": store_ids}}, {"_id": 0})}

    # R2: home customers per store (customers whose first bill was at this store)
    home_pipe = [
        {"$match": {"home_store_id": {"$in": store_ids}, "mobile": {"$nin": [None, ""]}}},
        {"$group": {"_id": "$home_store_id", "count": {"$sum": 1}}},
    ]
    home_counts = {r["_id"]: r["count"] async for r in customers_col.aggregate(home_pipe, allowDiskUse=True)}

    out = []
    region_agg: Dict[str, Dict[str, float]] = {}
    for r in rows:
        s = stores.get(r["_id"], {})
        out.append({
            "store_id": r["_id"], "store_name": s.get("name", "Unknown"), "code": s.get("code"),
            "city": s.get("city"), "region": s.get("region"),
            "net": round(r["net"], 2), "txns": r["txns"],
            "visitors": r["visitors"],
            "home_customers": home_counts.get(r["_id"], 0),
            "unique_customers": home_counts.get(r["_id"], 0),  # alias for back-compat
            "aov": round(r["net"] / r["txns"], 2) if r["txns"] else 0,
            "discount": round(r["discount"], 2),
        })
        # Region rollup from the same scan via the stores master (no per-bill $lookup)
        region = s.get("region") or "Unknown"
        ra = region_agg.setdefault(region, {"net": 0.0, "txns": 0})
        ra["net"] += r["net"]
        ra["txns"] += r["txns"]
    return {
        "stores": out,
        "regions": [{"region": k, "net": round(v["net"], 2), "txns": v["txns"]}
                    for k, v in sorted(region_agg.items(), key=lambda kv: -kv[1]["net"])],
    }


# NPS dashboard
@router.get("/nps-dashboard")
async def nps_dashboard(
    period_days: int = 60,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    from ._date_range import parse_date_range
    start_iso, end_iso = parse_date_range(start_date, end_date, period_days)
    if not start_iso:
        # Default for NPS: last 60 days (the old behaviour)
        start_iso = _start(60)
    match: Dict[str, Any] = {"created_at": {"$gte": start_iso}}
    if end_iso:
        match["created_at"]["$lt"] = end_iso
    # Daily trend
    trend_pipe = [
        {"$match": match},
        {"$group": {
            "_id": {"$substr": ["$created_at", 0, 10]},
            "promoters": {"$sum": {"$cond": [{"$gte": ["$score", 9]}, 1, 0]}},
            "detractors": {"$sum": {"$cond": [{"$lte": ["$score", 6]}, 1, 0]}},
            "total": {"$sum": 1},
            "avg": {"$avg": "$score"},
        }},
        {"$sort": {"_id": 1}},
    ]
    rows = await nps_col.aggregate(trend_pipe, allowDiskUse=True).to_list(120)
    return [
        {
            "date": r["_id"],
            "nps": round(((r["promoters"] - r["detractors"]) / r["total"]) * 100) if r["total"] else None,
            "promoters": r["promoters"], "detractors": r["detractors"], "total": r["total"], "avg": round(r["avg"], 2),
        }
        for r in rows
    ]


# Coupon usage drill-down
@router.get("/coupon-detail/{coupon_id}")
async def coupon_detail(coupon_id: str, user: dict = Depends(get_current_user)):
    c = await coupons_col.find_one({"id": coupon_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Not found")
    redemptions = await coupon_redemptions_col.find({"coupon_id": coupon_id}, {"_id": 0}).sort("redeemed_at", -1).limit(200).to_list(200)
    by_date_pipe = [
        {"$match": {"coupon_id": coupon_id}},
        {"$group": {"_id": {"$substr": ["$redeemed_at", 0, 10]}, "count": {"$sum": 1}, "discount": {"$sum": "$discount"}}},
        {"$sort": {"_id": 1}},
    ]
    trend = await coupon_redemptions_col.aggregate(by_date_pipe, allowDiskUse=True).to_list(120)
    return {"coupon": c, "redemptions": redemptions, "trend": [{"date": r["_id"], "count": r["count"], "discount": round(r["discount"], 2)} for r in trend]}
