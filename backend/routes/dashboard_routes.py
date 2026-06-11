"""Executive cockpit dashboard - real KPIs from MongoDB."""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Any, Dict, List
from fastapi import APIRouter, Depends, Query
from database import (
    customers_col, transactions_col, stores_col, campaigns_col, coupons_col,
    points_ledger_col, nps_col, tickets_col, api_logs_col, loyalty_config_col
)
from auth import get_current_user
from routes._loyalty import loyalty_match, LOYALTY_TX_MATCH
from routes._db_timeout import db_deadline
from routes._dash_cache import dash_cache
import logging

logger = logging.getLogger("kazo-fundle")
router = APIRouter(prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(db_deadline)])

# ── Command Center response cache ──────────────────────────────────────────
# The all-time ("period=all") view scans the full transactions collection
# (8L+ rows) across ~16 concurrent aggregations. That's a few seconds even when
# healthy, so we cache the assembled response briefly: the page auto-refreshes
# every 30s and users navigate in/out, so a 60s TTL turns "slow every time" into
# "slow at most once a minute" while keeping live POS bills near-real-time.
import time as _time
_CC_CACHE: Dict[str, tuple] = {}
_CC_TTL = 60.0


async def _safe_agg(col, pipeline, limit=1, default=None, max_ms=40000):
    """Run a dashboard aggregation that must NEVER 500 the endpoint.

    On timeout (pymongo ExecutionTimeout from maxTimeMS) or any error we log and
    return `default` so the dashboard degrades gracefully (partial data) instead
    of returning a 500 that blanks the whole page. The short 8s cap keeps the
    worst case bounded; the command-center fires these CONCURRENTLY (gather) so
    even under a running ingest job the endpoint returns in seconds, not minutes.
    """
    try:
        return await col.aggregate(pipeline, allowDiskUse=True, maxTimeMS=max_ms).to_list(limit)
    except Exception as e:
        logger.warning(f"dashboard agg degraded ({col.name}): {e}")
        return [] if default is None else default


async def _safe_count(col, filt, default=0, max_ms=40000):
    try:
        return await col.count_documents(filt, maxTimeMS=max_ms)
    except Exception as e:
        logger.warning(f"dashboard count degraded ({col.name}): {e}")
        return default


async def _burn_ratio() -> float:
    """₹ value of 1 loyalty point for liability — sourced from the loyalty config
    (the Loyalty Configurator drives it) instead of being hardcoded. Falls back to
    0.25 only if the config doc is somehow absent (it's seeded in every env)."""
    try:
        cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0, "burn_ratio": 1})
        if cfg and cfg.get("burn_ratio") is not None:
            return float(cfg["burn_ratio"])
    except Exception as e:
        logger.warning(f"burn_ratio config read degraded: {e}")
    return 0.25


def _date_range(period: str = "30d"):
    now = datetime.now(timezone.utc)
    # Treat any "<=0d" / "0" / "all" as all-time so historical CSV uploads
    # (whose bill_dates can be years old) are included.
    if period in ("all", "0", "0d") or period is None or period == "":
        start = now - timedelta(days=365 * 20)
        return start, now
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "7d":
        start = now - timedelta(days=7)
    elif period == "30d":
        start = now - timedelta(days=30)
    elif period == "90d":
        start = now - timedelta(days=90)
    elif period == "1y":
        start = now - timedelta(days=365)
    elif period == "mtd":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "ytd":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period.endswith("d") and period[:-1].isdigit():
        # generic "Nd" — e.g. 365d from the date-range picker presets
        start = now - timedelta(days=int(period[:-1]))
    else:
        start = now - timedelta(days=30)
    return start, now


@router.get("/kpis")
@dash_cache("kpis")
async def kpis(
    period: str = "30d",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    store_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    # Custom date range takes precedence over preset period
    if start_date and end_date:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
        except ValueError:
            start, end = _date_range(period)
    else:
        start, end = _date_range(period)
    prev_start = start - (end - start)

    # R5: loyalty data only — bills must have customer_mobile attached
    txn_filter = loyalty_match({"bill_date": {"$gte": start.isoformat(), "$lte": end.isoformat()}})
    prev_filter = loyalty_match({"bill_date": {"$gte": prev_start.isoformat(), "$lt": start.isoformat()}})
    if store_id:
        txn_filter["store_id"] = store_id
        prev_filter["store_id"] = store_id

    # ONE facet scan of customers + ONE of transactions + ONE of the ledger,
    # everything gathered concurrently (was ~14 sequential full scans).
    loyalty_cust_q = {"mobile": {"$nin": [None, ""]}}
    churn_cutoff = (datetime.now(timezone.utc) - timedelta(days=180)).isoformat()
    cust_facet_pipe = [
        {"$match": loyalty_cust_q},
        {"$facet": {
            "summary": [{"$group": {
                "_id": None, "total": {"$sum": 1},
                "liability": {"$sum": "$points_balance"},
                "new": {"$sum": {"$cond": [{"$and": [
                    {"$gte": [{"$ifNull": ["$first_purchase_at", ""]}, start.isoformat()]},
                    {"$lte": [{"$ifNull": ["$first_purchase_at", ""]}, end.isoformat()]},
                ]}, 1, 0]}},
                "active": {"$sum": {"$cond": [
                    {"$gte": [{"$ifNull": ["$last_visit_at", ""]}, start.isoformat()]}, 1, 0]}},
                "loyalty": {"$sum": {"$cond": [
                    {"$gt": [{"$ifNull": ["$lifetime_points_earned", 0]}, 0]}, 1, 0]}},
                "repeat": {"$sum": {"$cond": [
                    {"$gte": [{"$ifNull": ["$visit_count", 0]}, 2]}, 1, 0]}},
                "churned": {"$sum": {"$cond": [{"$and": [
                    {"$ne": [{"$ifNull": ["$last_visit_at", None]}, None]},
                    {"$lt": ["$last_visit_at", churn_cutoff]},
                ]}, 1, 0]}},
            }}],
        }},
    ]

    pipeline = [
        {"$match": txn_filter},
        {"$group": {
            "_id": None,
            "gross_sales": {"$sum": "$gross_amount"},
            "net_sales": {"$sum": "$net_amount"},
            "discount": {"$sum": "$discount_amount"},
            "txn_count": {"$sum": 1},
            # UPT = Units Per Transaction. Sum each line item's `quantity` (or
            # `qty` for older docs) defaulting to 1 when missing. Bills with NO
            # items array still count as 1 unit so UPT ≥ 1.0 for any non-empty
            # window (matches retail convention).
            "units_count": {"$sum": {
                "$cond": [
                    {"$gt": [{"$size": {"$ifNull": ["$items", []]}}, 0]},
                    {"$reduce": {
                        "input": {"$ifNull": ["$items", []]},
                        "initialValue": 0,
                        "in": {"$add": [
                            "$$value",
                            {"$ifNull": [
                                {"$toInt": {"$ifNull": ["$$this.quantity", "$$this.qty"]}},
                                1,
                            ]},
                        ]},
                    }},
                    1,
                ],
            }},
            "items_count": {"$sum": {"$size": {"$ifNull": ["$items", []]}}},
        }}
    ]
    prev_pipeline = [
        {"$match": prev_filter},
        {"$group": {"_id": None, "net_sales": {"$sum": "$net_amount"}, "txn_count": {"$sum": 1}}}
    ]

    # Loyalty metrics — points ledger is timestamped on the BILL, not the ingest time
    # Use bill_date when present (historic ingest now writes it), else fall back to created_at
    ledger_window = {"$or": [{"bill_date": {"$gte": start.isoformat()}},
                             {"bill_date": {"$exists": False}, "created_at": {"$gte": start.isoformat()}}]}
    ledger_pipe = [
        {"$match": {**ledger_window, "type": {"$in": ["earn", "redeem"]}}},
        {"$group": {"_id": "$type", "total": {"$sum": "$points"}}},
    ]

    campaign_pipe = [
        {"$group": {"_id": None, "revenue": {"$sum": "$revenue_generated"}, "count": {"$sum": 1}}}
    ]
    coupon_pipe = [{"$group": {"_id": None, "used": {"$sum": "$times_used"}, "issued": {"$sum": "$times_issued"}}}]
    nps_pipe = [
        {"$match": {"created_at": {"$gte": start.isoformat()}}},
        {"$group": {
            "_id": None,
            "promoters": {"$sum": {"$cond": [{"$gte": ["$score", 9]}, 1, 0]}},
            "detractors": {"$sum": {"$cond": [{"$lte": ["$score", 6]}, 1, 0]}},
            "total": {"$sum": 1},
        }}
    ]

    (cust_facet_res, cur, prev_cur, ledger_rows, cp, cu, npsr,
     complaint_count, api_total, api_failed, burn_ratio) = await asyncio.gather(
        _safe_agg(customers_col, cust_facet_pipe),
        _safe_agg(transactions_col, pipeline),
        _safe_agg(transactions_col, prev_pipeline),
        _safe_agg(points_ledger_col, ledger_pipe, limit=4),
        _safe_agg(campaigns_col, campaign_pipe),
        _safe_agg(coupons_col, coupon_pipe),
        _safe_agg(nps_col, nps_pipe),
        _safe_count(tickets_col, {"status": {"$in": ["open", "in_progress", "escalated"]}}),
        _safe_count(api_logs_col, {"timestamp": {"$gte": start.isoformat()}}),
        _safe_count(api_logs_col, {"status_code": {"$gte": 400}, "timestamp": {"$gte": start.isoformat()}}),
        _burn_ratio(),
    )

    summary = (((cust_facet_res[0] if cust_facet_res else {}) or {}).get("summary") or [{}])[0] or {}
    total_customers = int(summary.get("total", 0) or 0)
    new_customers = int(summary.get("new", 0) or 0)
    active_customers = int(summary.get("active", 0) or 0)
    repeat_customers = int(summary.get("repeat", 0) or 0)
    churned = int(summary.get("churned", 0) or 0)
    loyalty_customers = int(summary.get("loyalty", 0) or 0)
    outstanding_points = summary.get("liability", 0) or 0

    sales = cur[0] if cur else {"gross_sales": 0, "net_sales": 0, "discount": 0,
                                "txn_count": 0, "items_count": 0, "units_count": 0}
    prev = prev_cur[0] if prev_cur else {"net_sales": 0, "txn_count": 0}

    aov = (sales["net_sales"] / sales["txn_count"]) if sales["txn_count"] else 0
    # UPT — units per transaction (corrected: was line-item-count which under-reported)
    upt = (sales["units_count"] / sales["txn_count"]) if sales["txn_count"] else 0
    atv = aov  # average transaction value

    ledger_map = {r["_id"]: r["total"] for r in (ledger_rows or [])}
    points_issued = ledger_map.get("earn", 0) or 0
    points_redeemed = abs(ledger_map.get("redeem", 0) or 0)

    outstanding_liability = outstanding_points * burn_ratio
    loyalty_penetration = (loyalty_customers / total_customers * 100) if total_customers else 0
    repeat_rate = (repeat_customers / total_customers * 100) if total_customers else 0
    churn_pct = (churned / total_customers * 100) if total_customers else 0

    campaign_revenue = cp[0]["revenue"] if cp else 0
    campaign_count = cp[0]["count"] if cp else 0
    coupon_usage = cu[0]["used"] if cu else 0

    if npsr and npsr[0]["total"]:
        nps_score = round(((npsr[0]["promoters"] - npsr[0]["detractors"]) / npsr[0]["total"]) * 100)
    else:
        nps_score = None

    api_health = ((api_total - api_failed) / api_total * 100) if api_total else 100

    def delta(curr, prev):
        if not prev:
            return None
        return round(((curr - prev) / prev) * 100, 1)

    return {
        "period": period,
        "customers": {
            "total": total_customers,
            "active": active_customers,
            "new": new_customers,
            "repeat": repeat_customers,
            "churned": churned,
        },
        "sales": {
            "gross": round(sales["gross_sales"], 2),
            "net": round(sales["net_sales"], 2),
            "discount": round(sales["discount"], 2),
            "txn_count": sales["txn_count"],
            "aov": round(aov, 2),
            "atv": round(atv, 2),
            "upt": round(upt, 2),
            "delta_pct": delta(sales["net_sales"], prev["net_sales"]),
            "txn_delta_pct": delta(sales["txn_count"], prev["txn_count"]),
        },
        "loyalty": {
            "penetration_pct": round(loyalty_penetration, 1),
            "repeat_rate_pct": round(repeat_rate, 1),
            "churn_pct": round(churn_pct, 1),
            "points_issued": int(points_issued),
            "points_redeemed": int(points_redeemed),
            "outstanding_points": int(outstanding_points),
            "outstanding_liability_inr": round(outstanding_liability, 2),
        },
        "campaigns": {
            "count": campaign_count,
            "revenue_generated": round(campaign_revenue, 2),
            "coupon_usage": coupon_usage,
        },
        "nps": {"score": nps_score, "complaints_open": complaint_count},
        "api": {"health_pct": round(api_health, 2), "failed": api_failed, "total": api_total},
    }


@router.get("/sales-trend")
@dash_cache("sales-trend")
async def sales_trend(
    period: str = "30d",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    start, end = _date_range(period)
    # Explicit custom range overrides the named period (date-range picker)
    if start_date and end_date:
        try:
            start = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
            end = datetime.fromisoformat(end_date).replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc)
        except ValueError:
            pass
    # Monthly buckets for long windows (daily over 20 years would truncate the
    # chart at to_list cap); two-stage group gives EXACT distinct-customer counts
    # without the $addToSet memory blow-up at production scale.
    span_days = (end - start).days
    key_len = 7 if (period in {"1y", "ytd", "all", "0", "0d", ""} or span_days > 270) else 10
    date_key = {"$cond": [
        {"$eq": [{"$type": "$bill_date"}, "string"]},
        {"$substr": ["$bill_date", 0, key_len]},
        {"$dateToString": {"format": "%Y-%m" if key_len == 7 else "%Y-%m-%d", "date": "$bill_date"}},
    ]}
    pipeline = [
        {"$match": loyalty_match({"bill_date": {"$gte": start.isoformat(), "$lte": end.isoformat()}})},
        {"$group": {
            "_id": {"d": date_key, "m": "$customer_mobile"},
            "net": {"$sum": "$net_amount"},
            "txns": {"$sum": 1},
        }},
        {"$group": {
            "_id": "$_id.d",
            "net": {"$sum": "$net"},
            "txns": {"$sum": "$txns"},
            "customers": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
    ]
    rows = await transactions_col.aggregate(pipeline, allowDiskUse=True).to_list(2000)
    return [
        {"date": r["_id"], "net": round(r["net"], 2), "txns": r["txns"], "customers": r["customers"]}
        for r in rows
    ]


@router.get("/store-performance")
@dash_cache("store-perf")
async def store_perf(period: str = "30d", user: dict = Depends(get_current_user)):
    """Store performance — revenue & txns aggregate from bills in window.
    Per R2: 'unique_customers' on this view = customers whose HOME STORE
    (first bill ever) is this store (within the window's existence; we use
    customers_col home_store_id which is set at first transaction)."""
    start, end = _date_range(period)
    pipeline = [
        {"$match": loyalty_match({"bill_date": {"$gte": start.isoformat(), "$lte": end.isoformat()}})},
        # two-stage: exact distinct visitors per store without $addToSet memory blow-up
        {"$group": {
            "_id": {"s": "$store_id", "m": "$customer_mobile"},
            "net": {"$sum": "$net_amount"},
            "txns": {"$sum": 1},
        }},
        {"$group": {
            "_id": "$_id.s",
            "net": {"$sum": "$net"},
            "txns": {"$sum": "$txns"},
            "visitors": {"$sum": 1},
        }},
        {"$sort": {"net": -1}},
        {"$limit": 20},
    ]
    rows = await transactions_col.aggregate(pipeline, allowDiskUse=True).to_list(50)
    store_ids = [r["_id"] for r in rows]
    stores = {s["id"]: s async for s in stores_col.find({"id": {"$in": store_ids}}, {"_id": 0})}

    # R2: count customers whose HOME store is each of these (lifetime, not windowed)
    home_pipe = [
        {"$match": {"home_store_id": {"$in": store_ids}, "mobile": {"$nin": [None, ""]}}},
        {"$group": {"_id": "$home_store_id", "count": {"$sum": 1}}},
    ]
    home_counts = {r["_id"]: r["count"] async for r in customers_col.aggregate(home_pipe, allowDiskUse=True)}

    out = []
    for r in rows:
        s = stores.get(r["_id"], {})
        out.append({
            "store_id": r["_id"],
            "store_name": s.get("name", "Unknown"),
            "city": s.get("city", "—"),
            "net": round(r["net"], 2),
            "txns": r["txns"],
            "visitors": r["visitors"],                            # window-scoped distinct shoppers
            "home_customers": home_counts.get(r["_id"], 0),       # R2: customers anchored to this store
            "unique_customers": home_counts.get(r["_id"], 0),     # alias for back-compat
            "aov": round(r["net"] / r["txns"], 2) if r["txns"] else 0,
        })
    return out


@router.get("/category-mix")
@dash_cache("cat-mix")
async def category_mix(period: str = "30d", user: dict = Depends(get_current_user)):
    start, end = _date_range(period)
    cat_key = {"$cond": [{"$in": [{"$ifNull": ["$items.category", ""]}, ["", None]]},
                         "Uncategorised", "$items.category"]}
    pipeline = [
        {"$match": loyalty_match({"bill_date": {"$gte": start.isoformat(), "$lte": end.isoformat()}})},
        {"$unwind": "$items"},
        {"$group": {"_id": cat_key, "revenue": {"$sum": "$items.total"}, "qty": {"$sum": "$items.quantity"}}},
        {"$sort": {"revenue": -1}},
    ]
    rows = await transactions_col.aggregate(pipeline, allowDiskUse=True).to_list(50)
    return [{"category": r["_id"], "revenue": round(r["revenue"], 2), "quantity": r["qty"]} for r in rows]


@router.get("/tier-distribution")
async def tier_distribution(user: dict = Depends(get_current_user)):
    pipeline = [
        {"$match": {"mobile": {"$nin": [None, ""]}}},  # loyalty members only
        {"$group": {"_id": "$tier", "count": {"$sum": 1}, "spend": {"$sum": "$lifetime_spend"}}},
        {"$sort": {"spend": -1}},
    ]
    rows = await customers_col.aggregate(pipeline, allowDiskUse=True).to_list(20)
    return [{"tier": r["_id"], "count": r["count"], "lifetime_spend": round(r["spend"], 2)} for r in rows]


@router.get("/top-skus")
@dash_cache("top-skus")
async def top_skus(period: str = "30d", limit: int = 10, user: dict = Depends(get_current_user)):
    start, end = _date_range(period)
    pipeline = [
        {"$match": loyalty_match({"bill_date": {"$gte": start.isoformat(), "$lte": end.isoformat()}})},
        {"$unwind": "$items"},
        {"$group": {
            "_id": {"sku": {"$ifNull": ["$items.sku", "—"]},
                    "name": {"$cond": [{"$in": [{"$ifNull": ["$items.name", ""]}, ["", None]]},
                                       "Unnamed item", "$items.name"]},
                    "category": {"$cond": [{"$in": [{"$ifNull": ["$items.category", ""]}, ["", None]]},
                                           "Uncategorised", "$items.category"]}},
            "revenue": {"$sum": "$items.total"},
            "qty": {"$sum": "$items.quantity"},
        }},
        {"$sort": {"revenue": -1}},
        {"$limit": limit},
    ]
    rows = await transactions_col.aggregate(pipeline, allowDiskUse=True).to_list(limit)
    return [
        {"sku": r["_id"]["sku"], "name": r["_id"]["name"], "category": r["_id"]["category"],
         "revenue": round(r["revenue"], 2), "quantity": r["qty"]}
        for r in rows
    ]


@router.get("/filter-options")
async def filter_options(user: dict = Depends(get_current_user)):
    """Return distinct cities and active stores for the global filters.

    Cities come from BOTH the stores master AND the transactions city field
    so brands whose POS tags a bill with a city that has no explicit store
    master row (e.g. ecommerce / new branch) can still filter by that city.
    """
    store_cities = await stores_col.distinct("city", {"is_active": True})
    txn_cities = await transactions_col.distinct("city", {"city": {"$nin": [None, ""]}})
    all_cities = sorted(set([c for c in (store_cities + txn_cities) if c]))
    stores = await stores_col.find(
        {"is_active": True},
        {"_id": 0, "id": 1, "code": 1, "name": 1, "city": 1}
    ).sort("name", 1).to_list(500)
    return {"cities": all_cities, "stores": stores}


@router.get("/command-center")
async def command_center(
    period: str = "30d",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    store_id: Optional[str] = None,
    city: Optional[str] = None,
    refresh: bool = False,
    user: dict = Depends(get_current_user),
):
    """Live Command Center KPIs + sparkline + cohort distribution + alerts.

    Filters (all real-time, no snapshots):
      - period: today | 7d | 30d | 90d | mtd | ytd | all  (legacy)
      - start_date / end_date: explicit YYYY-MM-DD override (takes precedence)
      - store_id: limit to a single store
      - city: limit to stores in this city (resolves to a store_id list)
    """
    # Cached briefly (60s) — see _CC_CACHE note. Live POS bills appear within the TTL.
    # An explicit user Refresh (refresh=true) bypasses the cache for fresh numbers.
    _ck = f"{period}|{start_date}|{end_date}|{store_id}|{city}"
    _hit = _CC_CACHE.get(_ck)
    if not refresh and _hit and (_time.monotonic() - _hit[0]) < _CC_TTL:
        return _hit[1]
    # Custom date range takes precedence over preset period
    if start_date and end_date:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(days=1)
        except ValueError:
            start, end = _date_range(period)
    else:
        start, end = _date_range(period)
    prev_start = start - (end - start)
    now = datetime.now(timezone.utc)

    # Resolve city -> store_ids
    # We accept the city filter against EITHER stores.city OR transactions.city
    # because some bills are tagged with a city that doesn't have an explicit
    # store master row (e.g. ecommerce / pop-up / new branch not yet seeded).
    scoped_store_ids: Optional[List[str]] = None
    scoped_city_value: Optional[str] = None
    if store_id:
        scoped_store_ids = [store_id]
    elif city:
        scoped_city_value = city
        rows = await stores_col.find({"city": city, "is_active": True}, {"_id": 0, "id": 1}).to_list(500)
        scoped_store_ids = [r["id"] for r in rows]
        # If no store rows match this city, we'll fall back to txn.city in _txn_match below.

    # Customer-scope under a store/city filter: R2 — a customer "belongs to" the
    # store of their FIRST bill (home_store_id). The previous approach ran an
    # unguarded distinct() over transactions and pushed the resulting mobile list
    # back as a giant $in — that breaks (16MB limit / timeout) at production scale.
    def _cust_match(extra: Optional[dict] = None) -> dict:
        # R5: loyalty customers (have mobile) only
        m: Dict[str, Any] = {"mobile": {"$nin": [None, ""]}}
        if extra:
            m.update(extra)
        if scoped_store_ids is not None:
            m["home_store_id"] = {"$in": scoped_store_ids}
        return m

    def _txn_match(time_field: str, gte, lt=None) -> dict:
        # R5: loyalty data only
        m: Dict[str, Any] = dict(LOYALTY_TX_MATCH)
        m[time_field] = {"$gte": gte}
        if lt is not None:
            m[time_field]["$lt"] = lt
        else:
            m[time_field]["$lte"] = end.isoformat()
        # City + store filter — match either explicit store_id list OR txn.city
        if scoped_store_ids and scoped_city_value:
            m["$or"] = [{"store_id": {"$in": scoped_store_ids}}, {"city": scoped_city_value}]
        elif scoped_store_ids:
            m["store_id"] = {"$in": scoped_store_ids}
        elif scoped_city_value:
            m["city"] = scoped_city_value
        return m

    # --- ONE scan of the window's transactions ($facet) + ONE scan of customers ---
    # Previously ~16 separate queries each re-scanned the collections; at production
    # scale several silently timed out → the dashboard showed ₹0 / 0 txns while
    # customer counts still worked. Now: 1 txn facet + 1 prev-window group +
    # 1 customers facet + cheap indexed counts, all concurrent, with an explicit
    # `degraded` list in the response when anything times out.
    degraded: List[str] = []

    async def _agg(col, pipeline, limit=1, label="", default=None):
        try:
            return await col.aggregate(pipeline, allowDiskUse=True, maxTimeMS=40000).to_list(limit)
        except Exception as e:
            logger.warning(f"command-center agg degraded ({label}): {e}")
            degraded.append(label)
            return [] if default is None else default

    async def _count(col, filt, label=""):
        try:
            return await col.count_documents(filt, maxTimeMS=40000)
        except Exception as e:
            logger.warning(f"command-center count degraded ({label}): {e}")
            degraded.append(label)
            return 0

    units_expr = {
        "$cond": [
            {"$gt": [{"$size": {"$ifNull": ["$items", []]}}, 0]},
            {"$reduce": {
                "input": {"$ifNull": ["$items", []]},
                "initialValue": 0,
                "in": {"$add": ["$$value",
                                {"$ifNull": [{"$toInt": {"$ifNull": ["$$this.quantity", "$$this.qty"]}}, 1]}]},
            }},
            1,
        ],
    }
    # Sparkline: daily for short windows, monthly for 1y/all/ytd to keep it small
    spark_length = 7 if period in {"1y", "all", "ytd"} else 10
    spark_key = {"$cond": [
        {"$eq": [{"$type": "$bill_date"}, "string"]},
        {"$substr": ["$bill_date", 0, spark_length]},
        {"$dateToString": {"format": "%Y-%m" if spark_length == 7 else "%Y-%m-%d", "date": "$bill_date"}},
    ]}
    txn_facet_pipe = [
        {"$match": _txn_match("bill_date", start.isoformat())},
        {"$facet": {
            "sales": [{"$group": {
                "_id": None,
                "net": {"$sum": "$net_amount"},
                "gross": {"$sum": "$gross_amount"},
                "discount": {"$sum": "$discount_amount"},
                "txns": {"$sum": 1},
                "units": {"$sum": units_expr},
                "items": {"$sum": {"$size": {"$ifNull": ["$items", []]}}},
            }}],
            # distinct shoppers + repeat split in one two-stage group
            "repeat": [
                {"$group": {"_id": "$customer_mobile", "n": {"$sum": 1}}},
                {"$group": {"_id": None,
                            "repeat": {"$sum": {"$cond": [{"$gte": ["$n", 2]}, 1, 0]}},
                            "unique": {"$sum": 1}}},
            ],
            "spark": [
                {"$group": {"_id": spark_key, "net": {"$sum": "$net_amount"}, "txns": {"$sum": 1}}},
                {"$sort": {"_id": 1}},
                {"$limit": 2000},
            ],
        }},
    ]
    prev_sales_pipe = [
        {"$match": _txn_match("bill_date", prev_start.isoformat(), lt=start.isoformat())},
        {"$group": {"_id": None, "net": {"$sum": "$net_amount"}, "txns": {"$sum": 1}}},
    ]

    # Customers: total + liability + acquisition cohorts in ONE facet scan
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    d7 = now - timedelta(days=7)
    d30 = now - timedelta(days=30)
    d90 = now - timedelta(days=90)
    cohort_switch = {"$switch": {"branches": [
        {"case": {"$eq": [{"$ifNull": ["$first_purchase_at", None]}, None]}, "then": "never"},
        {"case": {"$gte": ["$first_purchase_at", today_start.isoformat()]}, "then": "today"},
        {"case": {"$gte": ["$first_purchase_at", d7.isoformat()]}, "then": "last_7d"},
        {"case": {"$gte": ["$first_purchase_at", d30.isoformat()]}, "then": "last_30d"},
        {"case": {"$gte": ["$first_purchase_at", d90.isoformat()]}, "then": "last_90d"},
    ], "default": "older"}}
    cust_facet_pipe = [
        {"$match": _cust_match()},
        {"$facet": {
            "summary": [{"$group": {"_id": None, "total": {"$sum": 1},
                                    "points": {"$sum": "$points_balance"}}}],
            "cohorts": [{"$group": {"_id": cohort_switch, "count": {"$sum": 1}}}],
        }},
    ]

    # NPS in window (filter by scoped store_ids if present)
    nps_match: Dict[str, Any] = {"created_at": {"$gte": start.isoformat()}}
    if scoped_store_ids:
        nps_match["store_id"] = {"$in": scoped_store_ids}
    nps_pipe = [
        {"$match": nps_match},
        {"$group": {"_id": None,
                    "promoters": {"$sum": {"$cond": [{"$gte": ["$score", 9]}, 1, 0]}},
                    "detractors": {"$sum": {"$cond": [{"$lte": ["$score", 6]}, 1, 0]}},
                    "total": {"$sum": 1}}},
    ]
    # API health in window (scoped by store_id when filter active)
    api_match: Dict[str, Any] = {"timestamp": {"$gte": start.isoformat()}}
    if scoped_store_ids:
        api_match["store_id"] = {"$in": scoped_store_ids}
    # Open complaints
    tickets_match: Dict[str, Any] = {"status": {"$in": ["open", "in_progress", "escalated"]}}
    if scoped_store_ids:
        tickets_match["store_id"] = {"$in": scoped_store_ids}

    (txn_facet_res, prev_res, cust_facet_res, nps_rows,
     api_total, api_failed, open_tickets, burn_ratio) = await asyncio.gather(
        _agg(transactions_col, txn_facet_pipe, label="sales-window"),
        _agg(transactions_col, prev_sales_pipe, label="previous-window", default=[{}]),
        _agg(customers_col, cust_facet_pipe, label="customer-base"),
        _agg(nps_col, nps_pipe, label="nps", default=[{}]),
        _count(api_logs_col, api_match, label="api-health"),
        _count(api_logs_col, {**api_match, "status_code": {"$gte": 400}}, label="api-failed"),
        _count(tickets_col, tickets_match, label="complaints"),
        _burn_ratio(),
    )

    # ── Derive KPIs from the gathered results ──
    txn_facet = (txn_facet_res[0] if txn_facet_res else {}) or {}
    cur = ((txn_facet.get("sales") or [{}]) + [{}])[0] or {}
    prev = (prev_res[0] if prev_res else {}) or {}
    net = cur.get("net", 0) or 0
    txns = cur.get("txns", 0) or 0
    aov = (net / txns) if txns else 0
    upt = ((cur.get("units", 0) or 0) / txns) if txns else 0
    prev_net = prev.get("net", 0) or 0
    prev_txns = prev.get("txns", 0) or 0
    sales_delta = round(((net - prev_net) / prev_net) * 100, 1) if prev_net else None
    txn_delta = round(((txns - prev_txns) / prev_txns) * 100, 1) if prev_txns else None

    cust_facet = (cust_facet_res[0] if cust_facet_res else {}) or {}
    summary = ((cust_facet.get("summary") or [{}]) + [{}])[0] or {}
    total_customers = int(summary.get("total", 0) or 0)

    rr = ((txn_facet.get("repeat") or [{}]) + [{}])[0] or {}
    active = int(rr.get("unique", 0) or 0)
    # Invariant: active must never exceed total.
    active = min(active, total_customers) if total_customers else active
    repeat_rate = round((rr.get("repeat", 0) / rr["unique"]) * 100, 1) if rr.get("unique") else 0

    nps_rows = nps_rows or []
    if nps_rows and nps_rows[0].get("total"):
        nps_score = round(((nps_rows[0]["promoters"] - nps_rows[0]["detractors"]) / nps_rows[0]["total"]) * 100)
    else:
        nps_score = None

    api_health = round(((api_total - api_failed) / api_total) * 100, 2) if api_total else 100.0

    outstanding_points = int(summary.get("points", 0) or 0)
    outstanding_inr = round(outstanding_points * burn_ratio, 2)

    cohort_map = {r["_id"]: r["count"] for r in (cust_facet.get("cohorts") or [])}
    cohort = {
        "today": cohort_map.get("today", 0), "last_7d": cohort_map.get("last_7d", 0),
        "last_30d": cohort_map.get("last_30d", 0), "last_90d": cohort_map.get("last_90d", 0),
        "older": cohort_map.get("older", 0),
    }
    sparkline = [{"date": r["_id"], "net": round(r["net"], 2), "txns": r["txns"]}
                 for r in (txn_facet.get("spark") or [])]

    # --- Alerts (live computed) ---
    alerts = []
    if sales_delta is not None and sales_delta < -10:
        alerts.append({"severity": "high", "title": "Sales decline",
                       "detail": f"Net sales down {abs(sales_delta)}% vs previous {period} window.",
                       "link": "/admin/dashboards/sales"})
    if api_health < 95 and api_total > 0:
        alerts.append({"severity": "medium", "title": "API health degraded",
                       "detail": f"{api_failed} of {api_total} requests failed ({api_health}% healthy).",
                       "link": "/admin/api-monitor"})
    if open_tickets > 10:
        alerts.append({"severity": "medium", "title": "Open complaints",
                       "detail": f"{open_tickets} support tickets need attention.",
                       "link": "/admin/tickets?status=open"})
    if nps_score is not None and nps_score < 30:
        alerts.append({"severity": "high", "title": "NPS below threshold",
                       "detail": f"NPS score is {nps_score} ({period}).",
                       "link": "/admin/dashboards/nps"})

    # Resolve filter labels for echo
    filter_meta: Dict[str, Any] = {"period": period}
    if store_id:
        s = await stores_col.find_one({"id": store_id}, {"_id": 0, "name": 1, "code": 1, "city": 1})
        filter_meta["store"] = s
    if city:
        filter_meta["city"] = city

    result = {
        "period": period,
        "filters": filter_meta,
        "generated_at": now.isoformat(),
        "degraded": degraded,   # non-empty = these blocks timed out; UI shows a retry banner
        "kpis": {
            "net_sales": round(net, 2),
            "net_sales_delta_pct": sales_delta,
            "transactions": txns,
            "transactions_delta_pct": txn_delta,
            "aov": round(aov, 2),
            "upt": round(upt, 2),
            "items_sold": int(cur.get("units", 0) or 0),
            "active_customers": active,
            "total_customers": total_customers,
            "repeat_customers": int(rr.get("repeat", 0) or 0),
            "repeat_rate_pct": repeat_rate,
            "nps_score": nps_score,
            "api_health_pct": api_health,
            "outstanding_points": outstanding_points,
            "outstanding_liability_inr": outstanding_inr,
            "open_complaints": open_tickets,
        },
        "cohort_distribution": cohort,
        "sparkline": sparkline,
        "alerts": alerts,
    }
    if not degraded:
        # Don't cache partial (timed-out) responses — a retry should recompute.
        _CC_CACHE[_ck] = (_time.monotonic(), result)
    return result


@router.get("/city-performance")
@dash_cache("city-perf")
async def city_performance(period: str = "30d", user: dict = Depends(get_current_user)):
    """City revenue rollup. Groups bills by store_id (small cardinality) then
    resolves the city from the stores master in Python — the previous
    $lookup-per-bill scan timed out (500) on production-scale data. Bills whose
    store has no master row fall back to the transaction's own city field."""
    start, end = _date_range(period)
    pipeline = [
        {"$match": loyalty_match({"bill_date": {"$gte": start.isoformat(), "$lte": end.isoformat()}})},
        {"$group": {"_id": {"s": "$store_id", "c": "$city"},
                    "net": {"$sum": "$net_amount"}, "txns": {"$sum": 1}}},
    ]
    rows = await transactions_col.aggregate(pipeline, allowDiskUse=True).to_list(2000)
    store_ids = list({r["_id"].get("s") for r in rows if r["_id"].get("s")})
    s_map = {s["id"]: s async for s in stores_col.find({"id": {"$in": store_ids}},
                                                       {"_id": 0, "id": 1, "city": 1})}
    city_agg: Dict[str, Dict[str, float]] = {}
    for r in rows:
        city = s_map.get(r["_id"].get("s"), {}).get("city") or r["_id"].get("c") or "Unknown"
        c = city_agg.setdefault(city, {"net": 0.0, "txns": 0})
        c["net"] += r.get("net", 0) or 0
        c["txns"] += r.get("txns", 0) or 0
    return [{"city": city, "net": round(v["net"], 2), "txns": v["txns"]}
            for city, v in sorted(city_agg.items(), key=lambda kv: -kv[1]["net"])[:50]]

