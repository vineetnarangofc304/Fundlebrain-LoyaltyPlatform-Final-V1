"""Additional drill-down dashboards and entity-level detail views."""
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from database import transactions_col, customers_col, stores_col, campaigns_col, points_ledger_col, nps_col, coupons_col, coupon_redemptions_col
from auth import get_current_user
from routes._loyalty import loyalty_match, LOYALTY_TX_MATCH

router = APIRouter(prefix="/analytics", tags=["analytics"])


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
async def sales_dashboard(period_days: int = 30, user: dict = Depends(get_current_user)):
    start = _start(period_days)

    # Hourly distribution
    hourly_pipe = [
        {"$match": loyalty_match({"bill_date": {"$gte": start}})},
        {"$project": {"hour": {"$hour": {"$dateFromString": {"dateString": "$bill_date"}}}, "net_amount": 1}},
        {"$group": {"_id": "$hour", "net": {"$sum": "$net_amount"}, "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    hourly = await transactions_col.aggregate(hourly_pipe).to_list(24)

    # Weekday
    weekday_pipe = [
        {"$match": loyalty_match({"bill_date": {"$gte": start}})},
        {"$project": {"dow": {"$dayOfWeek": {"$dateFromString": {"dateString": "$bill_date"}}}, "net_amount": 1}},
        {"$group": {"_id": "$dow", "net": {"$sum": "$net_amount"}, "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    weekday = await transactions_col.aggregate(weekday_pipe).to_list(7)
    day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

    # Payment mode mix
    pay_pipe = [
        {"$match": loyalty_match({"bill_date": {"$gte": start}})},
        {"$group": {"_id": "$payment_mode", "net": {"$sum": "$net_amount"}, "count": {"$sum": 1}}},
    ]
    pay = await transactions_col.aggregate(pay_pipe).to_list(10)

    # Discount distribution
    disc_pipe = [
        {"$match": loyalty_match({"bill_date": {"$gte": start}})},
        {"$project": {
            "bucket": {
                "$switch": {
                    "branches": [
                        {"case": {"$eq": ["$discount_amount", 0]}, "then": "0%"},
                        {"case": {"$lte": ["$discount_amount", 500]}, "then": "<=₹500"},
                        {"case": {"$lte": ["$discount_amount", 1500]}, "then": "<=₹1500"},
                    ],
                    "default": ">₹1500",
                },
            },
            "net_amount": 1,
        }},
        {"$group": {"_id": "$bucket", "count": {"$sum": 1}, "net": {"$sum": "$net_amount"}}},
    ]
    disc = await transactions_col.aggregate(disc_pipe).to_list(10)

    return {
        "hourly": [{"hour": r["_id"], "net": round(r["net"], 2), "count": r["count"]} for r in hourly],
        "weekday": [{"day": day_names[(r["_id"] - 1) % 7], "net": round(r["net"], 2), "count": r["count"]} for r in weekday],
        "payment_mix": [{"mode": r["_id"], "net": round(r["net"], 2), "count": r["count"]} for r in pay],
        "discount_distribution": [{"bucket": r["_id"], "count": r["count"], "net": round(r["net"], 2)} for r in disc],
    }


# Customer dashboard - RFM-style + cohorts
@router.get("/customer-dashboard")
async def customer_dashboard(user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc)

    # R1: New customer trend uses first_purchase_at (actual first bill date), not created_at.
    # R5: loyalty members only (must have mobile)
    loyalty_q = {"mobile": {"$nin": [None, ""]}}
    start = (now - timedelta(days=90)).isoformat()
    new_pipe = [
        {"$match": {**loyalty_q, "first_purchase_at": {"$gte": start}}},
        {"$group": {"_id": {"$substr": ["$first_purchase_at", 0, 10]}, "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    new_cust = await customers_col.aggregate(new_pipe).to_list(120)

    # Churn risk distribution (loyalty members only)
    churn_pipe = [{"$match": {"mobile": {"$nin": [None, ""]}}},
                   {"$group": {"_id": "$churn_risk", "count": {"$sum": 1}}}]
    churn = await customers_col.aggregate(churn_pipe).to_list(10)

    # Visit frequency buckets (loyalty members only — R3: by actual bill count)
    freq_pipe = [
        {"$match": {"mobile": {"$nin": [None, ""]}}},
        {"$project": {
            "bucket": {
                "$switch": {
                    "branches": [
                        {"case": {"$eq": ["$visit_count", 1]}, "then": "1 (one-time)"},
                        {"case": {"$lte": ["$visit_count", 3]}, "then": "2-3"},
                        {"case": {"$lte": ["$visit_count", 6]}, "then": "4-6"},
                        {"case": {"$lte": ["$visit_count", 12]}, "then": "7-12"},
                    ],
                    "default": "13+",
                },
            },
        }},
        {"$group": {"_id": "$bucket", "count": {"$sum": 1}}},
    ]
    freq = await customers_col.aggregate(freq_pipe).to_list(10)

    # Top spending customers (loyalty members only)
    top_pipe = [
        {"$match": {"mobile": {"$nin": [None, ""]}}},
        {"$sort": {"lifetime_spend": -1}}, {"$limit": 10},
        {"$project": {"_id": 0, "id": 1, "name": 1, "mobile": 1, "city": 1, "tier": 1, "lifetime_spend": 1, "visit_count": 1}},
    ]
    top = await customers_col.aggregate(top_pipe).to_list(10)

    # City distribution (loyalty members only)
    city_pipe = [
        {"$match": {"mobile": {"$nin": [None, ""]}}},
        {"$group": {"_id": "$city", "count": {"$sum": 1}, "spend": {"$sum": "$lifetime_spend"}}},
        {"$sort": {"spend": -1}}, {"$limit": 15},
    ]
    city = await customers_col.aggregate(city_pipe).to_list(20)

    return {
        "new_customer_trend": [{"date": r["_id"], "count": r["count"]} for r in new_cust],
        "churn_distribution": [{"risk": r["_id"], "count": r["count"]} for r in churn],
        "visit_frequency": [{"bucket": r["_id"], "count": r["count"]} for r in freq],
        "top_customers": top,
        "city_distribution": [{"city": r["_id"], "count": r["count"], "spend": round(r["spend"], 2)} for r in city],
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
async def loyalty_dashboard(user: dict = Depends(get_current_user)):
    # R5: loyalty members only (have mobile)
    loyalty_q = {"mobile": {"$nin": [None, ""]}}
    tier_pipe = [
        {"$match": loyalty_q},
        {"$group": {"_id": "$tier", "count": {"$sum": 1}, "avg_spend": {"$avg": "$lifetime_spend"}, "total_points": {"$sum": "$points_balance"}}},
        {"$sort": {"avg_spend": -1}},
    ]
    tiers = await customers_col.aggregate(tier_pipe).to_list(10)

    # Points issued vs redeemed trend — by BILL DATE (R1) — last 90 days
    start = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    # ledger entries written by ingest carry bill_date; older ones may only have created_at
    issued_pipe = [
        {"$match": {"$or": [{"bill_date": {"$gte": start}},
                              {"bill_date": {"$exists": False}, "created_at": {"$gte": start}}]}},
        {"$project": {
            "date": {"$substr": [{"$ifNull": ["$bill_date", "$created_at"]}, 0, 10]},
            "type": 1, "points": 1,
        }},
        {"$group": {"_id": {"date": "$date", "type": "$type"}, "points": {"$sum": "$points"}}},
        {"$sort": {"_id.date": 1}},
    ]
    rows = await points_ledger_col.aggregate(issued_pipe).to_list(2000)
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
        "tiers": [{"tier": r["_id"], "count": r["count"], "avg_spend": round(r["avg_spend"], 2), "total_points": int(r["total_points"])} for r in tiers],
        "points_trend": sorted(by_date.values(), key=lambda x: x["date"]),
    }


# Store performance dashboard
@router.get("/store-dashboard")
async def store_dashboard(period_days: int = 30, user: dict = Depends(get_current_user)):
    start = _start(period_days)
    pipe = [
        {"$match": loyalty_match({"bill_date": {"$gte": start}})},
        {"$group": {
            "_id": "$store_id",
            "net": {"$sum": "$net_amount"},
            "txns": {"$sum": 1},
            "visitors": {"$addToSet": "$customer_mobile"},
            "discount": {"$sum": "$discount_amount"},
        }},
        {"$sort": {"net": -1}},
    ]
    rows = await transactions_col.aggregate(pipe).to_list(100)
    store_ids = [r["_id"] for r in rows]
    stores = {s["id"]: s async for s in stores_col.find({"id": {"$in": store_ids}}, {"_id": 0})}

    # R2: home customers per store (customers whose first bill was at this store)
    home_pipe = [
        {"$match": {"home_store_id": {"$in": store_ids}, "mobile": {"$nin": [None, ""]}}},
        {"$group": {"_id": "$home_store_id", "count": {"$sum": 1}}},
    ]
    home_counts = {r["_id"]: r["count"] async for r in customers_col.aggregate(home_pipe)}

    out = []
    for r in rows:
        s = stores.get(r["_id"], {})
        out.append({
            "store_id": r["_id"], "store_name": s.get("name", "Unknown"), "code": s.get("code"),
            "city": s.get("city"), "region": s.get("region"),
            "net": round(r["net"], 2), "txns": r["txns"],
            "visitors": len([v for v in r["visitors"] if v]),
            "home_customers": home_counts.get(r["_id"], 0),
            "unique_customers": home_counts.get(r["_id"], 0),  # alias for back-compat
            "aov": round(r["net"] / r["txns"], 2) if r["txns"] else 0,
            "discount": round(r["discount"], 2),
        })
    # Region rollup
    region_pipe = [
        {"$match": loyalty_match({"bill_date": {"$gte": start}})},
        {"$lookup": {"from": "stores", "localField": "store_id", "foreignField": "id", "as": "store"}},
        {"$unwind": "$store"},
        {"$group": {"_id": "$store.region", "net": {"$sum": "$net_amount"}, "txns": {"$sum": 1}}},
        {"$sort": {"net": -1}},
    ]
    regions = await transactions_col.aggregate(region_pipe).to_list(20)
    return {
        "stores": out,
        "regions": [{"region": r["_id"], "net": round(r["net"], 2), "txns": r["txns"]} for r in regions],
    }


# NPS dashboard
@router.get("/nps-dashboard")
async def nps_dashboard(period_days: int = 60, user: dict = Depends(get_current_user)):
    start = _start(period_days)
    # Daily trend
    trend_pipe = [
        {"$match": {"created_at": {"$gte": start}}},
        {"$group": {
            "_id": {"$substr": ["$created_at", 0, 10]},
            "promoters": {"$sum": {"$cond": [{"$gte": ["$score", 9]}, 1, 0]}},
            "detractors": {"$sum": {"$cond": [{"$lte": ["$score", 6]}, 1, 0]}},
            "total": {"$sum": 1},
            "avg": {"$avg": "$score"},
        }},
        {"$sort": {"_id": 1}},
    ]
    rows = await nps_col.aggregate(trend_pipe).to_list(120)
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
    trend = await coupon_redemptions_col.aggregate(by_date_pipe).to_list(120)
    return {"coupon": c, "redemptions": redemptions, "trend": [{"date": r["_id"], "count": r["count"], "discount": round(r["discount"], 2)} for r in trend]}
