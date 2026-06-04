"""FundleBrain Phase 3A — live, real-time analytics endpoints.

All aggregations run on demand; nothing is pre-computed. Endpoints:
  GET /api/dashboard/customer-360/{customer_id}    — RFM + monthly spend
  GET /api/dashboard/store-performance-v2          — leaderboard / city / day
  GET /api/dashboard/rfm                           — 5x5 heatmap + 11 segments
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, Any, Dict, List
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, Query

from database import (
    customers_col, transactions_col, stores_col, points_ledger_col, nps_col,
    campaigns_col, campaign_metrics_col, coupons_col, coupon_redemptions_col,
    loyalty_config_col,
)
from auth import get_current_user
from routes._loyalty import loyalty_match, LOYALTY_TX_MATCH

router = APIRouter(prefix="/dashboard", tags=["fundlebrain"])


# -------------------- helpers --------------------

def _norm_period_days(period_days: Optional[int]) -> int:
    """`period_days <= 0` means 'All time' (20-year window). Used by frontend's
    'All time' filter so historical CSV uploads (years-old bill_dates) are included."""
    if period_days is None or period_days <= 0:
        return 365 * 20
    return period_days


def _quintile(value: float, breakpoints: List[float]) -> int:
    """Return 1..5 based on which quintile `value` falls into.
    breakpoints must be sorted ascending and have 4 entries (cuts q1|q2|q3|q4|q5).
    """
    for i, bp in enumerate(breakpoints):
        if value <= bp:
            return i + 1
    return 5


def _segment_label(r: int, f: int, m: int) -> str:
    """11-segment classifier (Champions / Loyalists / Big Spenders / Promising /
    New / Potential Loyalists / At Risk / Cant Lose / Hibernating / About to Sleep /
    Lost). r/f/m are quintiles 1..5 where 5 is best.

    NOTE: Conditions are intentionally evaluated in priority order with
    early-return. Some r/f/m combinations could theoretically match multiple
    branches (e.g. r=2,f=4,m=4 matches both 'Cant Lose Them' and 'At Risk');
    the earlier branch wins. This is per the RFM spec and matches industry
    convention — do not refactor to "exclusive" segments without a product call.
    """
    if r >= 4 and f >= 4 and m >= 4:
        return "Champions"
    if r >= 4 and f >= 3:
        return "Loyalists"
    if m >= 4 and f >= 3:
        return "Big Spenders"
    if r >= 4 and f <= 2:
        return "New Customers" if f == 1 else "Promising"
    if r == 3 and f >= 3:
        return "Potential Loyalists"
    if r == 3 and f <= 2:
        return "About to Sleep"
    if r == 2 and f >= 4 and m >= 4:
        return "Cant Lose Them"
    if r <= 2 and f >= 3:
        return "At Risk"
    if r <= 2 and f <= 2 and m <= 2:
        return "Lost"
    if r == 2 and f <= 3:
        return "Hibernating"
    return "Lost"


SEGMENT_ORDER = [
    "Champions", "Loyalists", "Big Spenders", "Promising", "New Customers",
    "Potential Loyalists", "Cant Lose Them", "At Risk", "About to Sleep",
    "Hibernating", "Lost",
]


# ============================================================
# Customer 360 v2 — RFM + lifetime + monthly spend + visits
# ============================================================
@router.get("/customer-360/{customer_id}")
async def customer_360_v2(customer_id: str, user: dict = Depends(get_current_user)):
    customer = await customers_col.find_one({"id": customer_id}, {"_id": 0})
    if not customer:
        raise HTTPException(404, "Customer not found")

    # ---- monthly spend (last 24 months, live aggregate) ----
    pipe = [
        {"$match": {"customer_id": customer_id}},
        {"$group": {
            "_id": {"$substr": ["$bill_date", 0, 7]},
            "spend": {"$sum": "$net_amount"},
            "visits": {"$sum": 1},
            "items": {"$sum": {"$size": {"$ifNull": ["$items", []]}}},
            "discount": {"$sum": "$discount_amount"},
        }},
        {"$sort": {"_id": 1}},
    ]
    monthly_rows = await transactions_col.aggregate(pipe).to_list(60)
    monthly = [{
        "month": r["_id"],
        "spend": round(r["spend"], 2),
        "visits": r["visits"],
        "items": r["items"],
        "aov": round(r["spend"] / r["visits"], 2) if r["visits"] else 0,
        "discount": round(r["discount"], 2),
    } for r in monthly_rows]

    # ---- store affinity (top stores by visit count) ----
    store_pipe = [
        {"$match": {"customer_id": customer_id}},
        {"$group": {"_id": "$store_id", "visits": {"$sum": 1}, "spend": {"$sum": "$net_amount"}}},
        {"$sort": {"visits": -1}}, {"$limit": 5},
    ]
    s_rows = await transactions_col.aggregate(store_pipe).to_list(10)
    s_ids = [r["_id"] for r in s_rows]
    stores = {s["id"]: s async for s in stores_col.find({"id": {"$in": s_ids}}, {"_id": 0})}
    store_affinity = [{
        "store_id": r["_id"],
        "name": stores.get(r["_id"], {}).get("name", "Unknown"),
        "city": stores.get(r["_id"], {}).get("city", "—"),
        "visits": r["visits"],
        "spend": round(r["spend"], 2),
    } for r in s_rows]

    # ---- category affinity ----
    cat_pipe = [
        {"$match": {"customer_id": customer_id}},
        {"$unwind": "$items"},
        {"$group": {"_id": "$items.category", "qty": {"$sum": "$items.quantity"},
                    "spend": {"$sum": "$items.total"}}},
        {"$sort": {"spend": -1}}, {"$limit": 8},
    ]
    cat_rows = await transactions_col.aggregate(cat_pipe).to_list(20)
    categories = [{"category": r["_id"], "qty": r["qty"], "spend": round(r["spend"], 2)} for r in cat_rows]

    # ---- RFM scores (live, single-customer evaluation against full population) ----
    # recency in days since last_visit
    now = datetime.now(timezone.utc)
    last_visit_str = customer.get("last_visit_at")
    if last_visit_str:
        try:
            last_visit_dt = datetime.fromisoformat(last_visit_str.replace("Z", "+00:00"))
            recency_days = max(0, (now - last_visit_dt).days)
        except Exception:
            recency_days = 9999
    else:
        recency_days = 9999

    # Quintile breakpoints from the whole population (single aggregation)
    rfm_breakpoints = await _rfm_breakpoints()
    r_q = 6 - _quintile(recency_days, rfm_breakpoints["recency"])  # lower recency = better
    f_q = _quintile(customer.get("visit_count", 0) or 0, rfm_breakpoints["frequency"])
    m_q = _quintile(customer.get("lifetime_spend", 0) or 0, rfm_breakpoints["monetary"])
    segment = _segment_label(r_q, f_q, m_q)

    # ---- recent transactions (last 10) ----
    recent = await transactions_col.find(
        {"customer_id": customer_id}, {"_id": 0}
    ).sort("bill_date", -1).limit(10).to_list(10)

    # ---- points ledger (last 25) ----
    ledger = await points_ledger_col.find(
        {"customer_id": customer_id}, {"_id": 0}
    ).sort("created_at", -1).limit(25).to_list(25)

    # ---- NPS history ----
    nps = await nps_col.find(
        {"customer_id": customer_id}, {"_id": 0}
    ).sort("created_at", -1).limit(10).to_list(10)

    # ---- lifetime stats (live recompute, NOT cached counters) ----
    lifetime_pipe = [
        {"$match": {"customer_id": customer_id}},
        {"$group": {
            "_id": None,
            "spend": {"$sum": "$net_amount"},
            "gross": {"$sum": "$gross_amount"},
            "discount": {"$sum": "$discount_amount"},
            "visits": {"$sum": 1},
            "items": {"$sum": {"$size": {"$ifNull": ["$items", []]}}},
            "first": {"$min": "$bill_date"},
            "last": {"$max": "$bill_date"},
        }},
    ]
    life = (await transactions_col.aggregate(lifetime_pipe).to_list(1)) or [{}]
    life = life[0] if life else {}
    lifetime = {
        "spend": round(life.get("spend", 0) or 0, 2),
        "gross": round(life.get("gross", 0) or 0, 2),
        "discount": round(life.get("discount", 0) or 0, 2),
        "visits": life.get("visits", 0) or 0,
        "items": life.get("items", 0) or 0,
        "aov": round((life.get("spend", 0) or 0) / (life.get("visits", 1) or 1), 2) if life.get("visits") else 0,
        "first_purchase": life.get("first"),
        "last_purchase": life.get("last"),
    }

    customer.pop("password_hash", None)

    return {
        "customer": customer,
        "lifetime": lifetime,
        "rfm": {
            "recency_days": recency_days,
            "frequency": customer.get("visit_count", 0),
            "monetary": round(customer.get("lifetime_spend", 0) or 0, 2),
            "r": r_q, "f": f_q, "m": m_q,
            "score": f"{r_q}{f_q}{m_q}",
            "segment": segment,
        },
        "monthly_spend": monthly,
        "store_affinity": store_affinity,
        "category_affinity": categories,
        "recent_transactions": recent,
        "points_ledger": ledger,
        "nps_history": nps,
    }


# ============================================================
# Customer 360 by mobile (R4: mobile is the canonical loyalty identity).
# Same payload shape as customer-360 by id but every lookup uses mobile.
# ============================================================
@router.get("/customer-by-mobile/{mobile}")
async def customer_360_by_mobile(mobile: str, user: dict = Depends(get_current_user)):
    customer = await customers_col.find_one({"mobile": mobile}, {"_id": 0})
    if not customer:
        raise HTTPException(404, "Customer not found")

    # Monthly spend (last 24 months)
    monthly_pipe = [
        {"$match": {"customer_mobile": mobile}},
        {"$group": {
            "_id": {"$substr": ["$bill_date", 0, 7]},
            "spend": {"$sum": "$net_amount"}, "visits": {"$sum": 1},
            "items": {"$sum": {"$size": {"$ifNull": ["$items", []]}}},
            "discount": {"$sum": "$discount_amount"},
        }},
        {"$sort": {"_id": 1}},
    ]
    monthly_rows = await transactions_col.aggregate(monthly_pipe).to_list(60)
    monthly = [{
        "month": r["_id"],
        "spend": round(r["spend"], 2),
        "visits": r["visits"],
        "items": r["items"],
        "aov": round(r["spend"] / r["visits"], 2) if r["visits"] else 0,
        "discount": round(r["discount"], 2),
    } for r in monthly_rows]

    # Store affinity
    store_pipe = [
        {"$match": {"customer_mobile": mobile}},
        {"$group": {"_id": "$store_id", "visits": {"$sum": 1}, "spend": {"$sum": "$net_amount"}}},
        {"$sort": {"visits": -1}}, {"$limit": 8},
    ]
    s_rows = await transactions_col.aggregate(store_pipe).to_list(10)
    s_ids = [r["_id"] for r in s_rows if r["_id"]]
    stores = {s["id"]: s async for s in stores_col.find({"id": {"$in": s_ids}}, {"_id": 0})}
    store_affinity = [{
        "store_id": r["_id"],
        "name": stores.get(r["_id"], {}).get("name", "Unknown"),
        "city": stores.get(r["_id"], {}).get("city", "—"),
        "code": stores.get(r["_id"], {}).get("code"),
        "visits": r["visits"],
        "spend": round(r["spend"], 2),
    } for r in s_rows]

    # Category affinity
    cat_pipe = [
        {"$match": {"customer_mobile": mobile}},
        {"$unwind": "$items"},
        {"$group": {"_id": "$items.category", "qty": {"$sum": "$items.quantity"},
                    "spend": {"$sum": "$items.total"}}},
        {"$sort": {"spend": -1}}, {"$limit": 8},
    ]
    cat_rows = await transactions_col.aggregate(cat_pipe).to_list(20)
    categories = [{"category": r["_id"], "qty": r["qty"], "spend": round(r["spend"], 2)} for r in cat_rows]

    # RFM
    now = datetime.now(timezone.utc)
    last_visit_str = customer.get("last_visit_at")
    recency_days = 9999
    if last_visit_str:
        try:
            last_visit_dt = datetime.fromisoformat(last_visit_str.replace("Z", "+00:00"))
            recency_days = max(0, (now - last_visit_dt).days)
        except Exception:
            pass
    rfm_breakpoints = await _rfm_breakpoints()
    r_q = 6 - _quintile(recency_days, rfm_breakpoints["recency"])
    f_q = _quintile(customer.get("visit_count", 0) or 0, rfm_breakpoints["frequency"])
    m_q = _quintile(customer.get("lifetime_spend", 0) or 0, rfm_breakpoints["monetary"])
    segment = _segment_label(r_q, f_q, m_q)

    # Recent transactions (last 25)
    recent = await transactions_col.find(
        {"customer_mobile": mobile},
        {"_id": 0, "id": 1, "bill_number": 1, "bill_date": 1, "store_id": 1, "store_name": 1,
         "city": 1, "net_amount": 1, "gross_amount": 1, "discount_amount": 1, "tax_amount": 1,
         "items": 1, "points_earned": 1, "points_redeemed": 1, "bonus_points": 1, "return_marker": 1}
    ).sort("bill_date", -1).limit(25).to_list(25)

    # Points ledger (last 30)
    ledger = await points_ledger_col.find(
        {"customer_mobile": mobile},
        {"_id": 0, "type": 1, "points": 1, "reason": 1, "bill_date": 1, "created_at": 1, "bill_number": 1}
    ).sort("bill_date", -1).limit(30).to_list(30)

    # NPS history
    nps = await nps_col.find(
        {"customer_mobile": mobile},
        {"_id": 0, "score": 1, "comment": 1, "created_at": 1}
    ).sort("created_at", -1).limit(10).to_list(10)
    # NPS may also be keyed by customer_id legacy
    if not nps and customer.get("id"):
        nps = await nps_col.find(
            {"customer_id": customer["id"]},
            {"_id": 0, "score": 1, "comment": 1, "created_at": 1}
        ).sort("created_at", -1).limit(10).to_list(10)

    # Lifetime live recompute
    lifetime_pipe = [
        {"$match": {"customer_mobile": mobile}},
        {"$group": {
            "_id": None,
            "spend": {"$sum": "$net_amount"},
            "gross": {"$sum": "$gross_amount"},
            "discount": {"$sum": "$discount_amount"},
            "visits": {"$sum": 1},
            "items": {"$sum": {"$size": {"$ifNull": ["$items", []]}}},
            "first": {"$min": "$bill_date"},
            "last": {"$max": "$bill_date"},
            "first_store": {"$first": "$store_id"},
        }},
    ]
    life = (await transactions_col.aggregate(lifetime_pipe).to_list(1)) or [{}]
    life = life[0] if life else {}
    lifetime = {
        "spend": round(life.get("spend", 0) or 0, 2),
        "gross": round(life.get("gross", 0) or 0, 2),
        "discount": round(life.get("discount", 0) or 0, 2),
        "visits": life.get("visits", 0) or 0,
        "items": life.get("items", 0) or 0,
        "aov": round((life.get("spend", 0) or 0) / (life.get("visits", 1) or 1), 2) if life.get("visits") else 0,
        "first_purchase": life.get("first"),
        "last_purchase": life.get("last"),
    }

    # Home store details
    home_store = None
    if customer.get("home_store_id"):
        home_store = await stores_col.find_one({"id": customer["home_store_id"]}, {"_id": 0})

    # Day-of-week + time-of-day patterns
    pattern_pipe = [
        {"$match": {"customer_mobile": mobile}},
        {"$project": {
            "dow": {"$dayOfWeek": {"$dateFromString": {"dateString": "$bill_date"}}},
            "hour": {"$hour": {"$dateFromString": {"dateString": "$bill_date"}}},
        }},
    ]
    pattern_rows = await transactions_col.aggregate(pattern_pipe).to_list(1000)
    weekday_n = sum(1 for r in pattern_rows if 2 <= r.get("dow", 0) <= 6)
    weekend_n = sum(1 for r in pattern_rows if r.get("dow") in (1, 7))
    if weekday_n == 0 and weekend_n == 0:
        day_pattern = "—"
    elif weekend_n == 0:
        day_pattern = "weekday_only"
    elif weekday_n == 0:
        day_pattern = "weekend_only"
    else:
        day_pattern = "mixed"
    # Time-of-day histogram
    tod_buckets = {"morning": 0, "afternoon": 0, "evening": 0, "night": 0}
    for r in pattern_rows:
        h = r.get("hour", 0)
        if 6 <= h < 12:
            tod_buckets["morning"] += 1
        elif 12 <= h < 17:
            tod_buckets["afternoon"] += 1
        elif 17 <= h < 21:
            tod_buckets["evening"] += 1
        else:
            tod_buckets["night"] += 1
    dominant_tod = max(tod_buckets, key=lambda k: tod_buckets[k]) if pattern_rows else "—"

    customer.pop("password_hash", None)

    return {
        "customer": customer,
        "home_store": home_store,
        "lifetime": lifetime,
        "rfm": {
            "recency_days": recency_days,
            "frequency": customer.get("visit_count", 0),
            "monetary": round(customer.get("lifetime_spend", 0) or 0, 2),
            "r": r_q, "f": f_q, "m": m_q,
            "score": f"{r_q}{f_q}{m_q}",
            "segment": segment,
        },
        "patterns": {
            "day_pattern": day_pattern,
            "weekday_visits": weekday_n,
            "weekend_visits": weekend_n,
            "time_of_day": tod_buckets,
            "dominant_time_of_day": dominant_tod,
        },
        "monthly_spend": monthly,
        "store_affinity": store_affinity,
        "category_affinity": categories,
        "recent_transactions": recent,
        "points_ledger": ledger,
        "nps_history": nps,
    }


async def _rfm_breakpoints() -> Dict[str, List[float]]:
    """Compute quintile breakpoints for R/F/M from the whole customer base (live)."""
    now = datetime.now(timezone.utc)

    # Pull recency/visit_count/lifetime_spend for every customer
    rows = await customers_col.find(
        {}, {"_id": 0, "id": 1, "last_visit_at": 1, "visit_count": 1, "lifetime_spend": 1}
    ).to_list(100000)

    rec, freq, mon = [], [], []
    for c in rows:
        lv = c.get("last_visit_at")
        if lv:
            try:
                dt = datetime.fromisoformat(lv.replace("Z", "+00:00"))
                rec.append((now - dt).days)
            except Exception:
                rec.append(9999)
        else:
            rec.append(9999)
        freq.append(c.get("visit_count", 0) or 0)
        mon.append(c.get("lifetime_spend", 0) or 0)

    def quintile_cuts(values: List[float]) -> List[float]:
        values = sorted(values)
        n = len(values)
        if n == 0:
            return [0, 0, 0, 0]
        return [values[max(0, min(n - 1, int(n * q)))] for q in (0.2, 0.4, 0.6, 0.8)]

    return {
        "recency": quintile_cuts(rec),
        "frequency": quintile_cuts(freq),
        "monetary": quintile_cuts(mon),
    }


# ============================================================
# Store Performance v2 — leaderboard / by-city / day-of-week
# ============================================================
@router.get("/store-performance-v2")
async def store_performance_v2(
    period_days: int = 30,
    user: dict = Depends(get_current_user),
):
    period_days = _norm_period_days(period_days)
    start = (datetime.now(timezone.utc) - timedelta(days=period_days)).isoformat()
    prev_start = (datetime.now(timezone.utc) - timedelta(days=period_days * 2)).isoformat()

    # Store-scoped roles: only their own store
    role = user.get("role")
    user_store_id = user.get("store_id")
    if role in {"store_manager", "store_staff"}:
        if not user_store_id:
            raise HTTPException(403, "Store-scoped role requires store_id on user profile")
        scope_match: Dict[str, Any] = {"store_id": user_store_id}
    else:
        scope_match = {}

    # ---- Leaderboard (R5: loyalty bills only) ----
    pipe = [
        {"$match": loyalty_match({"bill_date": {"$gte": start}, **scope_match})},
        {"$group": {
            "_id": "$store_id",
            "net": {"$sum": "$net_amount"},
            "gross": {"$sum": "$gross_amount"},
            "discount": {"$sum": "$discount_amount"},
            "txns": {"$sum": 1},
            "items": {"$sum": {"$size": {"$ifNull": ["$items", []]}}},
            "visitors": {"$addToSet": "$customer_mobile"},
        }},
        {"$sort": {"net": -1}},
    ]
    rows = await transactions_col.aggregate(pipe).to_list(200)

    # Previous-period comparison
    prev_pipe = [
        {"$match": loyalty_match({"bill_date": {"$gte": prev_start, "$lt": start}, **scope_match})},
        {"$group": {"_id": "$store_id", "net": {"$sum": "$net_amount"}, "txns": {"$sum": 1}}},
    ]
    prev_rows = await transactions_col.aggregate(prev_pipe).to_list(200)
    prev_map = {r["_id"]: r for r in prev_rows}

    store_ids = [r["_id"] for r in rows]
    stores = {s["id"]: s async for s in stores_col.find({"id": {"$in": store_ids}}, {"_id": 0})}

    # R2: home_store_id = customer's first-bill store
    home_pipe = [
        {"$match": {"home_store_id": {"$in": store_ids}, "mobile": {"$nin": [None, ""]}}},
        {"$group": {"_id": "$home_store_id", "count": {"$sum": 1}}},
    ]
    home_counts = {r["_id"]: r["count"] async for r in customers_col.aggregate(home_pipe)}

    leaderboard = []
    for i, r in enumerate(rows):
        s = stores.get(r["_id"], {})
        p = prev_map.get(r["_id"], {})
        prev_net = p.get("net", 0) or 0
        delta = round(((r["net"] - prev_net) / prev_net) * 100, 1) if prev_net else None
        leaderboard.append({
            "rank": i + 1,
            "store_id": r["_id"],
            "store_name": s.get("name", "Unknown"),
            "code": s.get("code"),
            "city": s.get("city"),
            "region": s.get("region"),
            "net": round(r["net"], 2),
            "gross": round(r["gross"], 2),
            "discount": round(r["discount"], 2),
            "txns": r["txns"],
            "visitors": len([v for v in r["visitors"] if v]),       # window-scoped distinct shoppers
            "home_customers": home_counts.get(r["_id"], 0),         # R2: customers anchored to this store
            "unique_customers": home_counts.get(r["_id"], 0),       # alias for back-compat
            "items": r["items"],
            "aov": round(r["net"] / r["txns"], 2) if r["txns"] else 0,
            "upt": round(r["items"] / r["txns"], 2) if r["txns"] else 0,
            "delta_pct": delta,
        })

    # ---- By city ----
    city_pipe = [
        {"$match": loyalty_match({"bill_date": {"$gte": start}, **scope_match})},
        {"$lookup": {"from": "stores", "localField": "store_id", "foreignField": "id", "as": "store"}},
        {"$unwind": "$store"},
        {"$group": {
            "_id": "$store.city",
            "net": {"$sum": "$net_amount"},
            "txns": {"$sum": 1},
            "stores": {"$addToSet": "$store_id"},
            "customers": {"$addToSet": "$customer_mobile"},
        }},
        {"$sort": {"net": -1}},
    ]
    city_rows = await transactions_col.aggregate(city_pipe).to_list(50)
    by_city = [{
        "city": r["_id"],
        "net": round(r["net"], 2),
        "txns": r["txns"],
        "stores": len(r["stores"]),
        "unique_customers": len([c for c in r["customers"] if c]),
        "aov": round(r["net"] / r["txns"], 2) if r["txns"] else 0,
    } for r in city_rows]

    # ---- Day-of-week analysis ----
    dow_pipe = [
        {"$match": loyalty_match({"bill_date": {"$gte": start}, **scope_match})},
        {"$project": {
            "dow": {"$dayOfWeek": {"$dateFromString": {"dateString": "$bill_date"}}},
            "hour": {"$hour": {"$dateFromString": {"dateString": "$bill_date"}}},
            "net_amount": 1,
        }},
        {"$group": {
            "_id": "$dow",
            "net": {"$sum": "$net_amount"},
            "txns": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
    ]
    dow_rows = await transactions_col.aggregate(dow_pipe).to_list(7)
    day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    by_day = [{
        "day": day_names[(r["_id"] - 1) % 7],
        "net": round(r["net"], 2),
        "txns": r["txns"],
        "aov": round(r["net"] / r["txns"], 2) if r["txns"] else 0,
    } for r in dow_rows]

    # ---- Hour × day heatmap (24×7) ----
    heat_pipe = [
        {"$match": loyalty_match({"bill_date": {"$gte": start}, **scope_match})},
        {"$project": {
            "dow": {"$dayOfWeek": {"$dateFromString": {"dateString": "$bill_date"}}},
            "hour": {"$hour": {"$dateFromString": {"dateString": "$bill_date"}}},
            "net_amount": 1,
        }},
        {"$group": {"_id": {"d": "$dow", "h": "$hour"}, "net": {"$sum": "$net_amount"}, "txns": {"$sum": 1}}},
    ]
    heat_rows = await transactions_col.aggregate(heat_pipe).to_list(500)
    heat_grid = []
    grid: Dict[int, Dict[int, Dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: {"net": 0, "txns": 0}))
    for r in heat_rows:
        d = r["_id"]["d"]
        h = r["_id"]["h"]
        grid[d][h] = {"net": r["net"], "txns": r["txns"]}
    for d in range(1, 8):
        for h in range(0, 24):
            cell = grid[d].get(h, {"net": 0, "txns": 0})
            heat_grid.append({
                "day": day_names[(d - 1) % 7],
                "hour": h,
                "net": round(cell["net"], 2),
                "txns": cell["txns"],
            })

    return {
        "period_days": period_days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "leaderboard": leaderboard,
        "by_city": by_city,
        "by_day": by_day,
        "heatmap": heat_grid,
    }


# ============================================================
# RFM & Churn — 5×5 heatmap + 11 named segments + churn buckets
# ============================================================
@router.get("/rfm")
async def rfm_dashboard(
    period_days: int = Query(0, ge=0, le=3650),
    user: dict = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    # period_days=0 → all time. Otherwise restrict to customers whose last_visit
    # is within the window. This trims the cohort to the recently-active universe.
    base_query: Dict[str, Any] = {}
    if period_days > 0:
        cutoff = (now - timedelta(days=period_days)).isoformat()
        base_query["last_visit_at"] = {"$gte": cutoff}

    customers = await customers_col.find(
        base_query, {"_id": 0, "id": 1, "name": 1, "mobile": 1, "city": 1, "tier": 1,
              "last_visit_at": 1, "visit_count": 1, "lifetime_spend": 1, "churn_risk": 1}
    ).to_list(100000)

    rec_vals, freq_vals, mon_vals = [], [], []
    enriched = []
    for c in customers:
        lv = c.get("last_visit_at")
        if lv:
            try:
                dt = datetime.fromisoformat(lv.replace("Z", "+00:00"))
                rec = (now - dt).days
            except Exception:
                rec = 9999
        else:
            rec = 9999
        freq = c.get("visit_count", 0) or 0
        mon = c.get("lifetime_spend", 0) or 0
        rec_vals.append(rec)
        freq_vals.append(freq)
        mon_vals.append(mon)
        enriched.append({**c, "_recency_days": rec, "_freq": freq, "_mon": mon})

    def cuts(values: List[float]) -> List[float]:
        values = sorted(values)
        n = len(values)
        if n == 0:
            return [0, 0, 0, 0]
        return [values[max(0, min(n - 1, int(n * q)))] for q in (0.2, 0.4, 0.6, 0.8)]

    rec_cuts = cuts(rec_vals)
    freq_cuts = cuts(freq_vals)
    mon_cuts = cuts(mon_vals)

    # 5x5 heatmap (R x F), with M shown as cell average spend
    heatmap_count: Dict[str, int] = defaultdict(int)
    heatmap_spend: Dict[str, float] = defaultdict(float)
    segment_counts: Dict[str, int] = defaultdict(int)
    segment_spend: Dict[str, float] = defaultdict(float)
    segment_examples: Dict[str, List[dict]] = defaultdict(list)
    churn_buckets = {"low": 0, "medium": 0, "high": 0}
    total_population = len(enriched)

    for c in enriched:
        r = 6 - _quintile(c["_recency_days"], rec_cuts)
        f = _quintile(c["_freq"], freq_cuts)
        m = _quintile(c["_mon"], mon_cuts)
        seg = _segment_label(r, f, m)
        key = f"{r},{f}"
        heatmap_count[key] += 1
        heatmap_spend[key] += c["_mon"]
        segment_counts[seg] += 1
        segment_spend[seg] += c["_mon"]
        if len(segment_examples[seg]) < 10:
            segment_examples[seg].append({
                "id": c["id"], "name": c.get("name"), "mobile": c.get("mobile"),
                "city": c.get("city"), "tier": c.get("tier"),
                "recency_days": c["_recency_days"], "visits": c["_freq"],
                "lifetime_spend": round(c["_mon"], 2),
                "rfm": f"{r}{f}{m}",
            })
        risk = c.get("churn_risk") or "low"
        if risk not in churn_buckets:
            risk = "low"
        churn_buckets[risk] += 1

    heatmap = []
    for r in range(1, 6):
        for f in range(1, 6):
            k = f"{r},{f}"
            count = heatmap_count.get(k, 0)
            heatmap.append({
                "r": r,
                "f": f,
                "count": count,
                "avg_spend": round(heatmap_spend.get(k, 0) / count, 2) if count else 0,
                "pct": round((count / total_population) * 100, 2) if total_population else 0,
            })

    segments = []
    for s in SEGMENT_ORDER:
        c = segment_counts.get(s, 0)
        segments.append({
            "segment": s,
            "count": c,
            "pct": round((c / total_population) * 100, 2) if total_population else 0,
            "total_spend": round(segment_spend.get(s, 0), 2),
            "avg_spend": round(segment_spend.get(s, 0) / c, 2) if c else 0,
            "examples": segment_examples.get(s, []),
        })

    return {
        "generated_at": now.isoformat(),
        "total_customers": total_population,
        "rfm_cutoffs": {
            "recency_days_q": rec_cuts,
            "frequency_q": freq_cuts,
            "monetary_inr_q": mon_cuts,
        },
        "heatmap": heatmap,
        "segments": segments,
        "churn_distribution": churn_buckets,
    }


# ============================================================
# Cohorts & Segmentation — one-timers, repeat bands, ATV, retention triangle
# ============================================================
FREQ_BANDS = [
    {"label": "One-timer", "key": "one_timer", "min": 1, "max": 1, "color": "#9F1239"},
    {"label": "Light repeat", "key": "light", "min": 2, "max": 5, "color": "#B45309"},
    {"label": "Regular", "key": "regular", "min": 6, "max": 15, "color": "#1E3A8A"},
    {"label": "Loyal", "key": "loyal", "min": 16, "max": 30, "color": "#0E7C7B"},
    {"label": "VIP", "key": "vip", "min": 31, "max": 999999, "color": "#047857"},
]

SPEND_BANDS = [
    {"label": "₹0 — 5K", "key": "tier_1", "min": 0, "max": 5000, "color": "#94A3B8"},
    {"label": "₹5K — 25K", "key": "tier_2", "min": 5000, "max": 25000, "color": "#64748B"},
    {"label": "₹25K — 75K", "key": "tier_3", "min": 25000, "max": 75000, "color": "#1E3A8A"},
    {"label": "₹75K — 2L", "key": "tier_4", "min": 75000, "max": 200000, "color": "#571326"},
    {"label": "₹2L+", "key": "tier_5", "min": 200000, "max": 99999999, "color": "#047857"},
]


@router.get("/cohorts-segmentation")
async def cohorts_segmentation(
    period_days: int = Query(0, ge=0, le=3650),
    user: dict = Depends(get_current_user),
):
    """Live cohorts + segmentation: one-timers, frequency bands, ATV, retention triangle."""
    now = datetime.now(timezone.utc)
    cohort_query: Dict[str, Any] = {"mobile": {"$nin": [None, ""]}}
    if period_days > 0:
        cutoff = (now - timedelta(days=period_days)).isoformat()
        cohort_query["last_visit_at"] = {"$gte": cutoff}

    # ---- One pass over transactions: per-customer aggregates (R4: by mobile; R5: loyalty only) ----
    cust_pipe = [
        {"$match": LOYALTY_TX_MATCH},
        {"$group": {
            "_id": "$customer_mobile",
            "visits": {"$sum": 1},
            "spend": {"$sum": "$net_amount"},
            "items": {"$sum": {"$size": {"$ifNull": ["$items", []]}}},
            "first": {"$min": "$bill_date"},
            "last": {"$max": "$bill_date"},
        }},
    ]
    cust_rows = await transactions_col.aggregate(cust_pipe).to_list(200000)
    cust_map = {r["_id"]: r for r in cust_rows}

    # Pull customer master for tier/city (loyalty members only) — key by mobile (R4)
    masters = await customers_col.find(
        cohort_query,
        {"_id": 0, "id": 1, "mobile": 1, "tier": 1, "city": 1,
         "first_purchase_at": 1, "name": 1, "home_store_id": 1}
    ).to_list(200000)

    # ---- Frequency segmentation ----
    freq_buckets: Dict[str, Dict[str, Any]] = {b["key"]: {**b, "count": 0, "spend": 0.0,
                                                             "visits": 0, "examples": []}
                                                  for b in FREQ_BANDS}
    spend_buckets: Dict[str, Dict[str, Any]] = {b["key"]: {**b, "count": 0, "spend": 0.0,
                                                              "visits": 0, "examples": []}
                                                   for b in SPEND_BANDS}
    tier_buckets: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"count": 0, "spend": 0.0, "visits": 0})

    # Customers with transactions
    transacted = 0
    for cust in masters:
        cid = cust["id"]
        mob = cust.get("mobile")
        tx = cust_map.get(mob)  # R4: cust_map is keyed by mobile
        if not tx:
            continue
        transacted += 1
        visits = tx["visits"]
        spend = tx["spend"]

        # frequency band
        for b in FREQ_BANDS:
            if b["min"] <= visits <= b["max"]:
                bucket = freq_buckets[b["key"]]
                bucket["count"] += 1
                bucket["spend"] += spend
                bucket["visits"] += visits
                if len(bucket["examples"]) < 10:
                    bucket["examples"].append({
                        "id": cid, "name": cust.get("name"), "mobile": cust.get("mobile"),
                        "city": cust.get("city"), "tier": cust.get("tier"),
                        "visits": visits, "spend": round(spend, 2),
                        "atv": round(spend / visits, 2) if visits else 0,
                    })
                break

        # spend band
        for b in SPEND_BANDS:
            if b["min"] <= spend < b["max"]:
                bucket = spend_buckets[b["key"]]
                bucket["count"] += 1
                bucket["spend"] += spend
                bucket["visits"] += visits
                if len(bucket["examples"]) < 10:
                    bucket["examples"].append({
                        "id": cid, "name": cust.get("name"), "mobile": cust.get("mobile"),
                        "city": cust.get("city"), "tier": cust.get("tier"),
                        "visits": visits, "spend": round(spend, 2),
                        "atv": round(spend / visits, 2) if visits else 0,
                    })
                break

        # tier
        t = (cust.get("tier") or "unknown").lower()
        tier_buckets[t]["count"] += 1
        tier_buckets[t]["spend"] += spend
        tier_buckets[t]["visits"] += visits

    total_pop = len(masters)
    total_with_tx = transacted

    def _finalise(bands_dict: Dict[str, Dict[str, Any]], bands_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = []
        for b in bands_list:
            row = bands_dict[b["key"]]
            count = row["count"]
            visits = row["visits"]
            spend = row["spend"]
            out.append({
                "key": b["key"],
                "label": b["label"],
                "color": b["color"],
                "count": count,
                "pct_of_base": round((count / total_pop) * 100, 2) if total_pop else 0,
                "pct_of_transacted": round((count / total_with_tx) * 100, 2) if total_with_tx else 0,
                "visits": visits,
                "total_spend": round(spend, 2),
                "avg_lifetime_spend": round(spend / count, 2) if count else 0,
                "atv": round(spend / visits, 2) if visits else 0,
                "examples": row["examples"],
            })
        return out

    frequency = _finalise(freq_buckets, FREQ_BANDS)
    spend_seg = _finalise(spend_buckets, SPEND_BANDS)

    tier_seg = []
    for tier_key, tdata in tier_buckets.items():
        if tdata["count"] == 0:
            continue
        tier_seg.append({
            "tier": tier_key,
            "count": tdata["count"],
            "pct_of_base": round((tdata["count"] / total_pop) * 100, 2) if total_pop else 0,
            "visits": tdata["visits"],
            "total_spend": round(tdata["spend"], 2),
            "avg_lifetime_spend": round(tdata["spend"] / tdata["count"], 2) if tdata["count"] else 0,
            "atv": round(tdata["spend"] / tdata["visits"], 2) if tdata["visits"] else 0,
        })
    tier_seg.sort(key=lambda x: -x["total_spend"])

    # ---- Retention triangle: signup month × month-offset ----
    # For each customer, get first_purchase month and all months they transacted
    # Then compute % retained at offset 0,1,2,… (R4: key by mobile; R5: loyalty only)
    monthly_visits = await transactions_col.aggregate([
        {"$match": LOYALTY_TX_MATCH},
        {"$group": {
            "_id": {"cid": "$customer_mobile", "month": {"$substr": ["$bill_date", 0, 7]}},
        }},
    ]).to_list(500000)

    # signup_month per customer = first purchase month
    first_month: Dict[str, str] = {}
    for mob, row in cust_map.items():
        if row.get("first"):
            first_month[mob] = row["first"][:7]

    # build months_active per customer
    months_active: Dict[str, set] = defaultdict(set)
    for r in monthly_visits:
        months_active[r["_id"]["cid"]].add(r["_id"]["month"])

    # Build cohort grid: cohort_month -> [retained_at_offset_0, _1, ...]
    cohort_grid: Dict[str, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
    cohort_size: Dict[str, int] = defaultdict(int)

    def _month_offset(start: str, target: str) -> int:
        sy, sm = int(start[:4]), int(start[5:7])
        ty, tm = int(target[:4]), int(target[5:7])
        return (ty - sy) * 12 + (tm - sm)

    for cid, fm in first_month.items():
        cohort_size[fm] += 1
        for active_m in months_active.get(cid, set()):
            offset = _month_offset(fm, active_m)
            if offset >= 0:
                cohort_grid[fm][offset] += 1

    # Sort cohort months chronologically, keep last 12 cohorts
    sorted_cohorts = sorted(cohort_grid.keys())[-12:]
    max_offset = 0
    for c in sorted_cohorts:
        if cohort_grid[c]:
            max_offset = max(max_offset, max(cohort_grid[c].keys()))
    max_offset = min(max_offset, 11)

    retention_triangle = []
    for c in sorted_cohorts:
        size = cohort_size[c]
        row = {"cohort_month": c, "cohort_size": size, "offsets": []}
        for o in range(max_offset + 1):
            retained = cohort_grid[c].get(o, 0)
            row["offsets"].append({
                "offset": o,
                "retained": retained,
                "pct": round((retained / size) * 100, 1) if size else 0,
            })
        retention_triangle.append(row)

    # ---- Acquisition trend (new customers per FIRST BILL month — R1) ----
    acquisition_pipe = [
        {"$match": {"mobile": {"$nin": [None, ""]},
                    "first_purchase_at": {"$ne": None, "$exists": True}}},
        {"$group": {"_id": {"$substr": ["$first_purchase_at", 0, 7]}, "new": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    acq_rows = await customers_col.aggregate(acquisition_pipe).to_list(60)
    acquisition_trend = [{"month": r["_id"], "new_customers": r["new"]}
                          for r in acq_rows if r["_id"]][-18:]

    # ---- One-timer focus: revenue at risk + recency ----
    one_timer_bucket = freq_buckets["one_timer"]
    # Recency distribution for one-timers — read directly from customers master so it
    # works even when transaction-side enrichment hasn't populated for every cust.
    one_timer_rec = {"0-30d": 0, "31-90d": 0, "91-180d": 0, "180d+": 0}
    onetimer_cursor = customers_col.find(
        {**cohort_query, "visit_count": 1, "last_visit_at": {"$ne": None}},
        {"_id": 0, "last_visit_at": 1},
    )
    async for cust in onetimer_cursor:
        lv = cust.get("last_visit_at")
        if not lv:
            continue
        try:
            last_dt = datetime.fromisoformat(lv.replace("Z", "+00:00"))
            days = (now - last_dt).days
        except Exception:
            continue
        if days <= 30:
            one_timer_rec["0-30d"] += 1
        elif days <= 90:
            one_timer_rec["31-90d"] += 1
        elif days <= 180:
            one_timer_rec["91-180d"] += 1
        else:
            one_timer_rec["180d+"] += 1

    one_timer = {
        "count": one_timer_bucket["count"],
        "pct_of_transacted": round((one_timer_bucket["count"] / total_with_tx) * 100, 2) if total_with_tx else 0,
        "total_spend": round(one_timer_bucket["spend"], 2),
        "avg_first_basket": round(one_timer_bucket["spend"] / one_timer_bucket["count"], 2) if one_timer_bucket["count"] else 0,
        "recency_distribution": one_timer_rec,
        "estimated_recovery_pool_inr": round(one_timer_bucket["spend"] * 0.15, 2),
        # Industry rule of thumb: 15% of one-timers can be reactivated with the right play
    }

    # ---- Repeat customer block (the counterpart to one_timer — addresses
    # docx "Repeat customer data to be visible" in Cohorts & Segments) ----
    # Aggregate all freq_buckets that are NOT 'one_timer' into a single
    # "repeat" summary + a frequency-band breakdown showing how repeats split
    # between 2 visits / 3-5 visits / 6-10 visits / 11+ visits.
    repeat_count = sum(b["count"] for k, b in freq_buckets.items() if k != "one_timer")
    repeat_spend = sum(b["spend"] for k, b in freq_buckets.items() if k != "one_timer")
    repeat_freq_breakdown = []
    for label, key in [("Light repeat (2-5)", "light"), ("Regular (6-15)", "regular"),
                        ("Loyal (16-30)", "loyal"), ("VIP (31+)", "vip")]:
        b = freq_buckets.get(key, {"count": 0, "spend": 0})
        repeat_freq_breakdown.append({
            "band": label,
            "count": b["count"],
            "total_spend": round(b["spend"], 2),
            "avg_spend_per_customer": round(b["spend"] / b["count"], 2) if b["count"] else 0,
        })
    repeat_block = {
        "count": repeat_count,
        "pct_of_transacted": round((repeat_count / total_with_tx) * 100, 2) if total_with_tx else 0,
        "total_spend": round(repeat_spend, 2),
        "avg_spend_per_customer": round(repeat_spend / repeat_count, 2) if repeat_count else 0,
        "frequency_breakdown": repeat_freq_breakdown,
    }

    return {
        "generated_at": now.isoformat(),
        "total_customers": total_pop,
        "transacted_customers": total_with_tx,
        "untransacted_customers": total_pop - total_with_tx,
        "frequency_segments": frequency,
        "spend_segments": spend_seg,
        "tier_segments": tier_seg,
        "one_timer": one_timer,
        "repeat": repeat_block,
        "retention_triangle": {
            "cohorts": sorted_cohorts,
            "max_offset": max_offset,
            "rows": retention_triangle,
        },
        "acquisition_trend": acquisition_trend,
    }

# ============================================================
# Points Economics v2 — earn-burn gauge, liability, monthly flow, top redeemers
# ============================================================
@router.get("/points-economics")
async def points_economics(period_days: int = 90, user: dict = Depends(get_current_user)):
    """Live loyalty economics: earn/burn ratio, liability, monthly flow, top redeemers."""
    period_days = _norm_period_days(period_days)
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=period_days)).isoformat()

    config = await loyalty_config_col.find_one({}, {"_id": 0}) or {}
    earn_ratio = float(config.get("earn_ratio", 1.0))
    burn_ratio = float(config.get("burn_ratio", 0.25))

    # ---- Earn vs Burn in window — by BILL DATE (R1) ----
    # Ledger entries written by historic ingest carry bill_date; older entries may only have created_at
    _t_in_window = {
        "$or": [{"bill_date": {"$gte": start}},
                {"bill_date": {"$exists": False}, "created_at": {"$gte": start}}],
    }
    earn_pipe = [
        {"$match": {**_t_in_window, "points": {"$gt": 0}}},
        {"$group": {"_id": None, "total": {"$sum": "$points"}, "events": {"$sum": 1}}},
    ]
    burn_pipe = [
        {"$match": {**_t_in_window, "points": {"$lt": 0}}},
        {"$group": {"_id": None, "total": {"$sum": "$points"}, "events": {"$sum": 1}}},
    ]
    earn = (await points_ledger_col.aggregate(earn_pipe).to_list(1)) or [{}]
    burn = (await points_ledger_col.aggregate(burn_pipe).to_list(1)) or [{}]
    earn_pts = (earn[0].get("total", 0) or 0)
    burn_pts = abs(burn[0].get("total", 0) or 0)
    earn_events = earn[0].get("events", 0)
    burn_events = burn[0].get("events", 0)
    burn_pct = round((burn_pts / earn_pts) * 100, 2) if earn_pts else 0

    # ---- Outstanding liability (snapshot) — loyalty members only ----
    liab_pipe = [
        {"$match": {"mobile": {"$nin": [None, ""]}}},
        {"$group": {"_id": None,
                    "outstanding": {"$sum": "$points_balance"},
                    "lifetime_earned": {"$sum": "$lifetime_points_earned"},
                    "lifetime_redeemed": {"$sum": "$lifetime_points_redeemed"}}}
    ]
    liab = (await customers_col.aggregate(liab_pipe).to_list(1)) or [{}]
    liab = liab[0] if liab else {}
    outstanding_points = int(liab.get("outstanding", 0) or 0)
    outstanding_inr = round(outstanding_points * burn_ratio, 2)
    lifetime_earned = int(liab.get("lifetime_earned", 0) or 0)
    lifetime_redeemed = int(liab.get("lifetime_redeemed", 0) or 0)

    # ---- Monthly flow (last 12 months by BILL date when available) ----
    monthly_pipe = [
        {"$project": {
            "month": {"$substr": [{"$ifNull": ["$bill_date", "$created_at"]}, 0, 7]},
            "points": 1,
        }},
        {"$group": {
            "_id": "$month",
            "earn": {"$sum": {"$cond": [{"$gt": ["$points", 0]}, "$points", 0]}},
            "burn": {"$sum": {"$cond": [{"$lt": ["$points", 0]}, {"$abs": "$points"}, 0]}},
        }},
        {"$sort": {"_id": 1}},
    ]
    monthly_rows = await points_ledger_col.aggregate(monthly_pipe).to_list(60)
    monthly_flow = [{"month": r["_id"], "earn": r["earn"], "burn": r["burn"],
                      "net": r["earn"] - r["burn"]} for r in monthly_rows if r["_id"]][-12:]

    # ---- Top redeemers in window (R4: key by mobile) ----
    top_redeem_pipe = [
        {"$match": {**_t_in_window, "points": {"$lt": 0}}},
        {"$group": {"_id": "$customer_mobile", "burned": {"$sum": {"$abs": "$points"}}, "events": {"$sum": 1}}},
        {"$sort": {"burned": -1}}, {"$limit": 15},
    ]
    top_redeem_rows = await points_ledger_col.aggregate(top_redeem_pipe).to_list(50)
    mobiles_to_lookup = [r["_id"] for r in top_redeem_rows if r["_id"]]
    custs = {c["mobile"]: c async for c in customers_col.find(
        {"mobile": {"$in": mobiles_to_lookup}},
        {"_id": 0, "id": 1, "name": 1, "mobile": 1, "city": 1, "tier": 1}
    )}
    top_redeemers = [{
        "customer_id": custs.get(r["_id"], {}).get("id"),
        "name": custs.get(r["_id"], {}).get("name"),
        "mobile": r["_id"],
        "city": custs.get(r["_id"], {}).get("city"),
        "tier": custs.get(r["_id"], {}).get("tier"),
        "points_burned": r["burned"],
        "inr_value": round(r["burned"] * burn_ratio, 2),
        "events": r["events"],
    } for r in top_redeem_rows if r["_id"]]

    # ---- Breakage estimate — loyalty customers with no visit in 180+ days holding > 0 points ----
    cutoff_180 = (now - timedelta(days=180)).isoformat()
    breakage_pipe = [
        {"$match": {"mobile": {"$nin": [None, ""]},
                    "points_balance": {"$gt": 0},
                    "$or": [{"last_visit_at": {"$lt": cutoff_180}},
                            {"last_visit_at": {"$exists": False}}]}},
        {"$group": {"_id": None, "points": {"$sum": "$points_balance"}, "customers": {"$sum": 1}}},
    ]
    brk = (await customers_col.aggregate(breakage_pipe).to_list(1)) or [{}]
    brk = brk[0] if brk else {}
    breakage_points = int(brk.get("points", 0) or 0)
    breakage_inr = round(breakage_points * burn_ratio, 2)

    # ---- Top 10 earning + burning stores in window (R6 — points_earned/redeemed
    # are directly on transactions, so we aggregate from there) ----
    stores_earn_pipe = [
        {"$match": {"bill_date": {"$gte": start},
                     "points_earned": {"$gt": 0},
                     "store_id": {"$ne": None}}},
        {"$group": {"_id": "$store_id",
                     "points_earned": {"$sum": "$points_earned"},
                     "bills": {"$sum": 1},
                     "net_amount": {"$sum": "$net_amount"}}},
        {"$sort": {"points_earned": -1}},
        {"$limit": 10},
    ]
    stores_burn_pipe = [
        {"$match": {"bill_date": {"$gte": start},
                     "points_redeemed": {"$gt": 0},
                     "store_id": {"$ne": None}}},
        {"$group": {"_id": "$store_id",
                     "points_redeemed": {"$sum": "$points_redeemed"},
                     "bills": {"$sum": 1},
                     "net_amount": {"$sum": "$net_amount"}}},
        {"$sort": {"points_redeemed": -1}},
        {"$limit": 10},
    ]
    se_rows = await transactions_col.aggregate(stores_earn_pipe).to_list(10)
    sb_rows = await transactions_col.aggregate(stores_burn_pipe).to_list(10)
    store_ids = list({r["_id"] for r in (se_rows + sb_rows) if r.get("_id")})
    store_master = {s["id"]: s async for s in stores_col.find(
        {"id": {"$in": store_ids}}, {"_id": 0, "id": 1, "name": 1, "code": 1, "city": 1})}
    def _hydrate(rows, key):
        out = []
        for r in rows:
            s = store_master.get(r["_id"]) or {}
            out.append({
                "store_id": r["_id"],
                "store_name": s.get("name") or "Unknown",
                "store_code": s.get("code") or "—",
                "city": s.get("city") or "—",
                "points": int(r.get(key, 0) or 0),
                "bills": int(r.get("bills", 0) or 0),
                "inr_value": round(int(r.get(key, 0) or 0) * burn_ratio, 2),
                "net_amount": round(float(r.get("net_amount", 0) or 0), 2),
            })
        return out
    top_stores_earning = _hydrate(se_rows, "points_earned")
    top_stores_burning = _hydrate(sb_rows, "points_redeemed")

    return {
        "period_days": period_days,
        "generated_at": now.isoformat(),
        "config": {"earn_ratio": earn_ratio, "burn_ratio": burn_ratio},
        "window": {
            "earn_points": int(earn_pts),
            "burn_points": int(burn_pts),
            "earn_events": earn_events,
            "burn_events": burn_events,
            "burn_to_earn_pct": burn_pct,
            "earn_inr_equivalent": round(earn_pts * burn_ratio, 2),
            "burn_inr_equivalent": round(burn_pts * burn_ratio, 2),
        },
        "liability": {
            "outstanding_points": outstanding_points,
            "outstanding_inr": outstanding_inr,
            "lifetime_earned": lifetime_earned,
            "lifetime_redeemed": lifetime_redeemed,
            "redemption_pct": round((lifetime_redeemed / lifetime_earned) * 100, 2) if lifetime_earned else 0,
        },
        "breakage_risk": {
            "stale_180d_customers": int(brk.get("customers", 0) or 0),
            "points_at_risk": breakage_points,
            "inr_at_risk": breakage_inr,
        },
        "monthly_flow": monthly_flow,
        "top_redeemers": top_redeemers,
        "top_stores_earning": top_stores_earning,
        "top_stores_burning": top_stores_burning,
    }


# ============================================================
# Campaign ROI v2 — funnel (sent → delivered → clicked → converted)
# ============================================================
@router.get("/campaign-roi")
async def campaign_roi(user: dict = Depends(get_current_user)):
    """Live campaign performance: funnel + leaderboard + channel mix."""
    now = datetime.now(timezone.utc)

    campaigns = await campaigns_col.find({}, {"_id": 0}).to_list(500)
    metrics = await campaign_metrics_col.find({}, {"_id": 0}).to_list(2000)
    # Index metrics by campaign_id
    m_by_c: Dict[str, Dict[str, int]] = defaultdict(lambda: {"sent": 0, "delivered": 0, "opened": 0,
                                                              "clicked": 0, "converted": 0,
                                                              "revenue_generated": 0.0, "cost": 0.0})
    for m in metrics:
        bucket = m_by_c[m["campaign_id"]]
        for k in ("sent", "delivered", "opened", "clicked", "converted"):
            bucket[k] += int(m.get(k, 0) or 0)
        bucket["revenue_generated"] += float(m.get("revenue_generated", 0) or 0)
        bucket["cost"] += float(m.get("cost", 0) or 0)

    total = {"sent": 0, "delivered": 0, "opened": 0, "clicked": 0, "converted": 0,
             "revenue": 0.0, "cost": 0.0}
    by_channel: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"sent": 0, "delivered": 0,
                                                                  "opened": 0, "clicked": 0,
                                                                  "converted": 0,
                                                                  "revenue": 0.0, "cost": 0.0,
                                                                  "campaigns": 0})
    leaderboard = []
    for c in campaigns:
        b = m_by_c.get(c["id"], {})
        sent = b.get("sent", 0)
        delivered = b.get("delivered", 0)
        clicked = b.get("clicked", 0)
        converted = b.get("converted", 0)
        revenue = b.get("revenue_generated", 0.0)
        cost = b.get("cost", 0.0)
        roi = round(((revenue - cost) / cost) * 100, 1) if cost else None
        ctr = round((clicked / delivered) * 100, 2) if delivered else 0
        cvr = round((converted / clicked) * 100, 2) if clicked else 0
        rpc = round(revenue / converted, 2) if converted else 0
        leaderboard.append({
            "id": c["id"], "name": c.get("name"), "channel": c.get("channel"),
            "status": c.get("status"), "type": c.get("type"),
            "sent": sent, "delivered": delivered, "clicked": clicked,
            "converted": converted, "revenue": round(revenue, 2),
            "cost": round(cost, 2), "roi_pct": roi, "ctr_pct": ctr,
            "cvr_pct": cvr, "revenue_per_conversion": rpc,
            "created_at": c.get("created_at"),
        })
        # totals
        total["sent"] += sent
        total["delivered"] += delivered
        total["opened"] += b.get("opened", 0)
        total["clicked"] += clicked
        total["converted"] += converted
        total["revenue"] += revenue
        total["cost"] += cost
        # by channel
        ch = c.get("channel", "unknown")
        ch_b = by_channel[ch]
        for k in ("sent", "delivered", "opened", "clicked", "converted"):
            ch_b[k] += b.get(k, 0)
        ch_b["revenue"] += revenue
        ch_b["cost"] += cost
        ch_b["campaigns"] += 1

    leaderboard.sort(key=lambda x: -(x["roi_pct"] if x["roi_pct"] is not None else -999))

    funnel = [
        {"stage": "Sent", "count": total["sent"], "pct_of_sent": 100.0 if total["sent"] else 0},
        {"stage": "Delivered", "count": total["delivered"],
         "pct_of_sent": round((total["delivered"] / total["sent"]) * 100, 1) if total["sent"] else 0},
        {"stage": "Opened", "count": total["opened"],
         "pct_of_sent": round((total["opened"] / total["sent"]) * 100, 1) if total["sent"] else 0},
        {"stage": "Clicked", "count": total["clicked"],
         "pct_of_sent": round((total["clicked"] / total["sent"]) * 100, 1) if total["sent"] else 0},
        {"stage": "Converted", "count": total["converted"],
         "pct_of_sent": round((total["converted"] / total["sent"]) * 100, 1) if total["sent"] else 0},
    ]

    channel_summary = []
    for ch, b in by_channel.items():
        channel_summary.append({
            "channel": ch,
            "campaigns": b["campaigns"],
            "sent": b["sent"], "delivered": b["delivered"],
            "clicked": b["clicked"], "converted": b["converted"],
            "revenue": round(b["revenue"], 2), "cost": round(b["cost"], 2),
            "roi_pct": round(((b["revenue"] - b["cost"]) / b["cost"]) * 100, 1) if b["cost"] else None,
            "ctr_pct": round((b["clicked"] / b["delivered"]) * 100, 2) if b["delivered"] else 0,
            "cvr_pct": round((b["converted"] / b["clicked"]) * 100, 2) if b["clicked"] else 0,
        })
    channel_summary.sort(key=lambda x: -x["revenue"])

    return {
        "generated_at": now.isoformat(),
        "totals": {
            **{k: int(v) for k, v in total.items() if k not in ("revenue", "cost")},
            "revenue": round(total["revenue"], 2),
            "cost": round(total["cost"], 2),
            "net_revenue": round(total["revenue"] - total["cost"], 2),
            "overall_roi_pct": round(((total["revenue"] - total["cost"]) / total["cost"]) * 100, 1) if total["cost"] else None,
            "overall_ctr_pct": round((total["clicked"] / total["delivered"]) * 100, 2) if total["delivered"] else 0,
            "overall_cvr_pct": round((total["converted"] / total["clicked"]) * 100, 2) if total["clicked"] else 0,
            "campaigns": len(campaigns),
        },
        "funnel": funnel,
        "leaderboard": leaderboard,
        "by_channel": channel_summary,
    }


# ============================================================
# Formula Catalog — auto-generated from a single source of truth
# ============================================================
FORMULA_CATALOG: List[Dict[str, str]] = [
    {"key": "net_sales", "name": "Net Sales", "category": "Revenue",
     "formula": "SUM(transactions.net_amount) WHERE bill_date in [start, end]",
     "description": "Total realised revenue after discounts within the selected window.",
     "live_source": "MongoDB aggregation on `transactions` collection"},
    {"key": "aov", "name": "Average Order Value (AOV)", "category": "Revenue",
     "formula": "net_sales / count(transactions)",
     "description": "Average net spend per bill.",
     "live_source": "Derived from sales aggregation"},
    {"key": "upt", "name": "Units Per Transaction (UPT)", "category": "Revenue",
     "formula": "SUM(transaction.items.length) / count(transactions)",
     "description": "Average number of items in a single bill — basket size proxy.",
     "live_source": "transactions.items array length"},
    {"key": "repeat_rate", "name": "Repeat Rate", "category": "Customer",
     "formula": "count(customers with ≥2 txns in window) / count(unique customers in window) × 100",
     "description": "Share of customers who returned within the selected window.",
     "live_source": "transactions grouped by customer_id"},
    {"key": "active_customer", "name": "Active Customer", "category": "Customer",
     "formula": "customer.id appears in transactions.customer_id within window",
     "description": "Ground-truth definition — a customer who actually transacted.",
     "live_source": "DISTINCT customer_id from transactions in window"},
    {"key": "recency_quintile", "name": "Recency Quintile (R)", "category": "RFM",
     "formula": "days_since(last_visit_at) bucketed into population quintiles; lower days = better; flipped 6-q so 5=best",
     "description": "How recently the customer transacted, relative to the entire base.",
     "live_source": "customers.last_visit_at + dynamic population quintile cuts"},
    {"key": "frequency_quintile", "name": "Frequency Quintile (F)", "category": "RFM",
     "formula": "customer.visit_count bucketed into population quintiles; 5=top quintile",
     "description": "How often the customer transacts vs the rest of the base.",
     "live_source": "customers.visit_count"},
    {"key": "monetary_quintile", "name": "Monetary Quintile (M)", "category": "RFM",
     "formula": "customer.lifetime_spend bucketed into population quintiles; 5=top quintile",
     "description": "Total lifetime spend relative to the base.",
     "live_source": "customers.lifetime_spend"},
    {"key": "atv", "name": "Average Transaction Value (ATV)", "category": "Cohort",
     "formula": "SUM(lifetime_spend) / SUM(visit_count) within a segment",
     "description": "Per-bill spend at the segment level. Same intent as AOV but applied to a customer band.",
     "live_source": "transactions grouped per customer, then per band"},
    {"key": "one_timer", "name": "One-Timer", "category": "Cohort",
     "formula": "customer.visit_count = 1",
     "description": "Has made exactly one purchase ever.",
     "live_source": "transactions grouped by customer_id, count=1"},
    {"key": "recovery_pool", "name": "Recovery Pool (One-Timer)", "category": "Cohort",
     "formula": "one_timer.total_spend × 0.15",
     "description": "Industry rule of thumb — ~15% of one-timers can be reactivated.",
     "live_source": "Derived"},
    {"key": "rfm_segment", "name": "RFM Segment", "category": "Customer",
     "formula": "11-class classifier over R/F/M quintile combinations (Champions, Loyalists, Big Spenders, Promising, New Customers, Potential Loyalists, Cant Lose Them, At Risk, About to Sleep, Hibernating, Lost)",
     "description": "Industry-standard 11-segment RFM model. Conditions evaluated in priority order — first match wins.",
     "live_source": "Live classification at request time"},
    {"key": "churn_risk", "name": "Churn Risk", "category": "Customer",
     "formula": "customers.churn_risk in {low, medium, high} — computed from recency + tier behaviour at signup or update.",
     "description": "Categorical risk of customer attrition.",
     "live_source": "customers.churn_risk field"},
    {"key": "earn_ratio", "name": "Earn Ratio", "category": "Loyalty",
     "formula": "loyalty_config.earn_ratio (default 1.0 point per ₹1)",
     "description": "Points awarded per rupee spent.",
     "live_source": "loyalty_config collection"},
    {"key": "burn_ratio", "name": "Burn Ratio", "category": "Loyalty",
     "formula": "loyalty_config.burn_ratio (default ₹0.25 per point)",
     "description": "Cash value of each redeemed point — the basis of liability valuation.",
     "live_source": "loyalty_config collection"},
    {"key": "outstanding_liability", "name": "Outstanding Liability", "category": "Loyalty",
     "formula": "SUM(customers.points_balance) × burn_ratio",
     "description": "Rupee value of all unredeemed points across the customer base.",
     "live_source": "customers.points_balance"},
    {"key": "breakage", "name": "Breakage (180d stale)", "category": "Loyalty",
     "formula": "SUM(points_balance for customers with no visit in 180d) × burn_ratio",
     "description": "Liability likely to expire — opportunity to write back or run a redemption push.",
     "live_source": "customers.last_visit_at + points_balance"},
    {"key": "campaign_ctr", "name": "CTR (Click-Through Rate)", "category": "Campaign",
     "formula": "clicked / delivered × 100",
     "description": "Engagement quality.",
     "live_source": "campaign_metrics"},
    {"key": "campaign_cvr", "name": "CVR (Conversion Rate)", "category": "Campaign",
     "formula": "converted / clicked × 100",
     "description": "Funnel quality — engaged users who actually buy.",
     "live_source": "campaign_metrics"},
    {"key": "campaign_roi", "name": "Campaign ROI", "category": "Campaign",
     "formula": "(revenue_generated - cost) / cost × 100",
     "description": "Net return on marketing spend.",
     "live_source": "campaign_metrics"},
    {"key": "nps_score", "name": "NPS Score", "category": "Experience",
     "formula": "(promoters - detractors) / total × 100; promoters: score ≥9; detractors: score ≤6",
     "description": "Industry-standard Net Promoter Score.",
     "live_source": "nps_responses"},
    {"key": "retention_pct", "name": "Cohort Retention %", "category": "Cohort",
     "formula": "for each signup_month cohort: count(retained at month-offset N) / cohort_size × 100",
     "description": "Share of a signup cohort still active N months later.",
     "live_source": "transactions grouped by customer first-purchase month vs subsequent months"},
    {"key": "api_health", "name": "API Health", "category": "Operations",
     "formula": "(total - failed) / total × 100 where status_code ≥ 400 = failed",
     "description": "Real-time health of POS / public API integrations.",
     "live_source": "api_logs"},
]


@router.get("/formula-catalog")
async def formula_catalog(user: dict = Depends(get_current_user)):
    """Single source of truth for every KPI definition used across dashboards.
    Auto-grouped by category for the audit page."""
    grouped: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for f in FORMULA_CATALOG:
        grouped[f["category"]].append(f)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(FORMULA_CATALOG),
        "categories": [{"category": k, "count": len(v), "formulas": v}
                       for k, v in grouped.items()],
        "flat": FORMULA_CATALOG,
    }


# ============================================================
# Executive Summary v2 — composite snapshot + ReportLab PDF
# ============================================================
@router.get("/executive-summary")
async def executive_summary(period_days: int = 30, user: dict = Depends(get_current_user)):
    """Composite executive snapshot: KPIs + segments + top stores + alerts in one payload."""
    period_days = _norm_period_days(period_days)
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=period_days)).isoformat()
    prev_start = (now - timedelta(days=period_days * 2)).isoformat()

    # Sales (R5: loyalty bills only)
    cur = (await transactions_col.aggregate([
        {"$match": loyalty_match({"bill_date": {"$gte": start}})},
        {"$group": {"_id": None, "net": {"$sum": "$net_amount"}, "txns": {"$sum": 1},
                    "items": {"$sum": {"$size": {"$ifNull": ["$items", []]}}}}},
    ]).to_list(1)) or [{}]
    prev = (await transactions_col.aggregate([
        {"$match": loyalty_match({"bill_date": {"$gte": prev_start, "$lt": start}})},
        {"$group": {"_id": None, "net": {"$sum": "$net_amount"}, "txns": {"$sum": 1}}},
    ]).to_list(1)) or [{}]
    cur = cur[0] if cur else {}
    prev = prev[0] if prev else {}
    net = cur.get("net", 0) or 0
    txns = cur.get("txns", 0) or 0
    prev_net = prev.get("net", 0) or 0
    sales_delta = round(((net - prev_net) / prev_net) * 100, 1) if prev_net else None

    # Active customers + total (R4 + R5: loyalty members by mobile)
    # CRITICAL: active must be a SUBSET of total. We count distinct mobiles
    # from transactions in the window, then constrain to those that also
    # exist in the customers master. This guarantees active <= total.
    active_mobiles = await transactions_col.distinct("customer_mobile",
                                                      loyalty_match({"bill_date": {"$gte": start}}))
    active_mobiles = [m for m in active_mobiles if m]
    if active_mobiles:
        active = await customers_col.count_documents(
            {"mobile": {"$in": active_mobiles}}
        )
    else:
        active = 0
    total_customers = await customers_col.count_documents({"mobile": {"$nin": [None, ""]}})

    # Top 5 stores
    top_stores_rows = await transactions_col.aggregate([
        {"$match": loyalty_match({"bill_date": {"$gte": start}})},
        {"$group": {"_id": "$store_id", "net": {"$sum": "$net_amount"}}},
        {"$sort": {"net": -1}}, {"$limit": 5},
    ]).to_list(10)
    s_ids = [r["_id"] for r in top_stores_rows]
    s_map = {s["id"]: s async for s in stores_col.find({"id": {"$in": s_ids}}, {"_id": 0})}
    top_stores = [{"name": s_map.get(r["_id"], {}).get("name", "Unknown"),
                    "city": s_map.get(r["_id"], {}).get("city"),
                    "net": round(r["net"], 2)} for r in top_stores_rows]

    # Top 5 cities
    top_cities_rows = await transactions_col.aggregate([
        {"$match": loyalty_match({"bill_date": {"$gte": start}})},
        {"$lookup": {"from": "stores", "localField": "store_id", "foreignField": "id", "as": "store"}},
        {"$unwind": "$store"},
        {"$group": {"_id": "$store.city", "net": {"$sum": "$net_amount"}}},
        {"$sort": {"net": -1}}, {"$limit": 5},
    ]).to_list(10)
    top_cities = [{"city": r["_id"], "net": round(r["net"], 2)} for r in top_cities_rows]

    # Loyalty (members only)
    liab = (await customers_col.aggregate([
        {"$match": {"mobile": {"$nin": [None, ""]}}},
        {"$group": {"_id": None, "outstanding": {"$sum": "$points_balance"}}},
    ]).to_list(1)) or [{}]
    outstanding_points = int(liab[0].get("outstanding", 0) or 0) if liab else 0
    config = await loyalty_config_col.find_one({}, {"_id": 0}) or {}
    burn_ratio = float(config.get("burn_ratio", 0.25))

    return {
        "period_days": period_days,
        "generated_at": now.isoformat(),
        "kpis": {
            "net_sales": round(net, 2),
            "net_sales_delta_pct": sales_delta,
            "transactions": txns,
            "aov": round(net / txns, 2) if txns else 0,
            "items_sold": cur.get("items", 0) or 0,
            "active_customers": active,
            "total_customers": total_customers,
            "outstanding_liability_inr": round(outstanding_points * burn_ratio, 2),
        },
        "top_stores": top_stores,
        "top_cities": top_cities,
    }


@router.get("/executive-summary/pdf")
async def executive_summary_pdf(period_days: int = 30, user: dict = Depends(get_current_user)):
    """Generate a brand-themed PDF using ReportLab."""
    from fastapi.responses import StreamingResponse
    buf = await _build_executive_summary_pdf_bytes(period_days, user)
    fname = f"KAZO_Executive_Summary_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.pdf"
    return StreamingResponse(buf, media_type="application/pdf",
                              headers={"Content-Disposition": f'attachment; filename="{fname}"'})


async def _build_executive_summary_pdf_bytes(period_days: int, user: dict):
    """Build the executive summary PDF and return a BytesIO at position 0."""
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                     TableStyle)
    from reportlab.lib.enums import TA_LEFT

    data = await executive_summary(period_days, user)  # type: ignore
    k = data["kpis"]

    BURGUNDY = colors.HexColor("#571326")
    INDIGO = colors.HexColor("#1E3A8A")
    TEAL = colors.HexColor("#0E7C7B")
    SLATE = colors.HexColor("#334155")
    LIGHT = colors.HexColor("#F9F8F6")
    GREY = colors.HexColor("#94A3B8")

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                             topMargin=2 * cm, bottomMargin=2 * cm,
                             title=f"KAZO Executive Summary · {period_days}d")
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontName="Helvetica-Bold",
                         fontSize=24, textColor=BURGUNDY, alignment=TA_LEFT, spaceAfter=4)
    sub = ParagraphStyle("sub", parent=styles["Normal"], fontName="Helvetica",
                          fontSize=8, textColor=GREY, alignment=TA_LEFT, spaceAfter=20)
    section = ParagraphStyle("section", parent=styles["Heading2"], fontName="Helvetica-Bold",
                              fontSize=13, textColor=SLATE, spaceBefore=18, spaceAfter=8)
    body = ParagraphStyle("body", parent=styles["Normal"], fontName="Helvetica",
                           fontSize=10, textColor=SLATE, spaceAfter=6, leading=14)

    story = []
    story.append(Paragraph("KAZO &nbsp;<font color='#94A3B8'>·</font>&nbsp; Executive Summary", h1))
    story.append(Paragraph(
        f"POWERED BY FUNDLE &nbsp;·&nbsp; LAST {period_days} DAYS &nbsp;·&nbsp; GENERATED {datetime.now(timezone.utc).strftime('%d %b %Y · %H:%M UTC')}",
        sub))

    delta_str = f"{k['net_sales_delta_pct']:+.1f}%" if k.get("net_sales_delta_pct") is not None else "NEW"
    kpi_rows = [
        ["Net Sales", f"₹ {k['net_sales']:,.0f}", "Transactions", f"{k['transactions']:,}"],
        ["AOV", f"₹ {k['aov']:,.0f}", "Items Sold", f"{k['items_sold']:,}"],
        ["Active Customers", f"{k['active_customers']:,}", "Total Customers", f"{k['total_customers']:,}"],
        ["Sales Δ vs prev", delta_str, "Outstanding Liability", f"₹ {k['outstanding_liability_inr']:,.0f}"],
    ]
    kpi_table = Table(kpi_rows, colWidths=[3.5 * cm, 4.5 * cm, 3.5 * cm, 4.5 * cm])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("LINEABOVE", (0, 0), (-1, 0), 1, BURGUNDY),
        ("LINEBELOW", (0, -1), (-1, -1), 1, BURGUNDY),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), GREY),
        ("TEXTCOLOR", (2, 0), (2, -1), GREY),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTNAME", (3, 0), (3, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(kpi_table)

    story.append(Paragraph("TOP 5 STORES", section))
    rows = [["Rank", "Store", "City", "Net ₹"]]
    for i, s in enumerate(data["top_stores"], 1):
        rows.append([str(i), s["name"], s.get("city") or "—", f"{s['net']:,.0f}"])
    t = Table(rows, colWidths=[1.5 * cm, 8 * cm, 3 * cm, 4 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INDIGO),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (3, 0), (3, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, GREY),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)

    story.append(Paragraph("TOP 5 CITIES", section))
    rows = [["Rank", "City", "Net ₹"]]
    for i, c in enumerate(data["top_cities"], 1):
        rows.append([str(i), c["city"], f"{c['net']:,.0f}"])
    t = Table(rows, colWidths=[1.5 * cm, 11 * cm, 4 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TEAL),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, GREY),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)

    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "<font color='#94A3B8'>This report was computed live from the KAZO Fundle MongoDB database. "
        "No snapshots or pre-aggregations were used. Every number reflects the platform state at the "
        "timestamp above.</font>",
        body))

    doc.build(story)
    buf.seek(0)
    return buf


