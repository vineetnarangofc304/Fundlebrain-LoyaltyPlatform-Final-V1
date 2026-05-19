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
)
from auth import get_current_user

router = APIRouter(prefix="/dashboard", tags=["fundlebrain"])


# -------------------- helpers --------------------

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

    # ---- Leaderboard ----
    pipe = [
        {"$match": {"bill_date": {"$gte": start}, **scope_match}},
        {"$group": {
            "_id": "$store_id",
            "net": {"$sum": "$net_amount"},
            "gross": {"$sum": "$gross_amount"},
            "discount": {"$sum": "$discount_amount"},
            "txns": {"$sum": 1},
            "items": {"$sum": {"$size": {"$ifNull": ["$items", []]}}},
            "customers": {"$addToSet": "$customer_id"},
        }},
        {"$sort": {"net": -1}},
    ]
    rows = await transactions_col.aggregate(pipe).to_list(200)

    # Previous-period comparison
    prev_pipe = [
        {"$match": {"bill_date": {"$gte": prev_start, "$lt": start}, **scope_match}},
        {"$group": {"_id": "$store_id", "net": {"$sum": "$net_amount"}, "txns": {"$sum": 1}}},
    ]
    prev_rows = await transactions_col.aggregate(prev_pipe).to_list(200)
    prev_map = {r["_id"]: r for r in prev_rows}

    store_ids = [r["_id"] for r in rows]
    stores = {s["id"]: s async for s in stores_col.find({"id": {"$in": store_ids}}, {"_id": 0})}
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
            "unique_customers": len([c for c in r["customers"] if c]),
            "items": r["items"],
            "aov": round(r["net"] / r["txns"], 2) if r["txns"] else 0,
            "upt": round(r["items"] / r["txns"], 2) if r["txns"] else 0,
            "delta_pct": delta,
        })

    # ---- By city ----
    city_pipe = [
        {"$match": {"bill_date": {"$gte": start}, **scope_match}},
        {"$lookup": {"from": "stores", "localField": "store_id", "foreignField": "id", "as": "store"}},
        {"$unwind": "$store"},
        {"$group": {
            "_id": "$store.city",
            "net": {"$sum": "$net_amount"},
            "txns": {"$sum": 1},
            "stores": {"$addToSet": "$store_id"},
            "customers": {"$addToSet": "$customer_id"},
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
        {"$match": {"bill_date": {"$gte": start}, **scope_match}},
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
        {"$match": {"bill_date": {"$gte": start}, **scope_match}},
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
async def rfm_dashboard(user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc)

    customers = await customers_col.find(
        {}, {"_id": 0, "id": 1, "name": 1, "mobile": 1, "city": 1, "tier": 1,
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
