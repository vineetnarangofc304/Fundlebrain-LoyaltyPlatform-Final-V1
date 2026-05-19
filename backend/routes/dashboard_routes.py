"""Executive cockpit dashboard - real KPIs from MongoDB."""
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Query
from database import (
    customers_col, transactions_col, stores_col, campaigns_col, coupons_col,
    points_ledger_col, nps_col, tickets_col, api_logs_col
)
from auth import get_current_user

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _date_range(period: str = "30d"):
    now = datetime.now(timezone.utc)
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "7d":
        start = now - timedelta(days=7)
    elif period == "30d":
        start = now - timedelta(days=30)
    elif period == "90d":
        start = now - timedelta(days=90)
    elif period == "mtd":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif period == "ytd":
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start = now - timedelta(days=30)
    return start, now


@router.get("/kpis")
async def kpis(period: str = "30d", store_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    start, end = _date_range(period)
    prev_start = start - (end - start)

    txn_filter = {"bill_date": {"$gte": start.isoformat(), "$lte": end.isoformat()}}
    prev_filter = {"bill_date": {"$gte": prev_start.isoformat(), "$lt": start.isoformat()}}
    if store_id:
        txn_filter["store_id"] = store_id
        prev_filter["store_id"] = store_id

    # Customer metrics
    total_customers = await customers_col.count_documents({})
    new_filter = {"created_at": {"$gte": start.isoformat()}}
    new_customers = await customers_col.count_documents(new_filter)
    active_filter = {"last_visit_at": {"$gte": start.isoformat()}}
    active_customers = await customers_col.count_documents(active_filter)

    # Sales aggregate
    pipeline = [
        {"$match": txn_filter},
        {"$group": {
            "_id": None,
            "gross_sales": {"$sum": "$gross_amount"},
            "net_sales": {"$sum": "$net_amount"},
            "discount": {"$sum": "$discount_amount"},
            "txn_count": {"$sum": 1},
            "items_count": {"$sum": {"$size": {"$ifNull": ["$items", []]}}},
            "unique_customers": {"$addToSet": "$customer_id"},
        }}
    ]
    cur = await transactions_col.aggregate(pipeline).to_list(1)
    sales = cur[0] if cur else {"gross_sales": 0, "net_sales": 0, "discount": 0, "txn_count": 0, "items_count": 0, "unique_customers": []}

    prev_pipeline = [
        {"$match": prev_filter},
        {"$group": {"_id": None, "net_sales": {"$sum": "$net_amount"}, "txn_count": {"$sum": 1}}}
    ]
    prev_cur = await transactions_col.aggregate(prev_pipeline).to_list(1)
    prev = prev_cur[0] if prev_cur else {"net_sales": 0, "txn_count": 0}

    aov = (sales["net_sales"] / sales["txn_count"]) if sales["txn_count"] else 0
    upt = (sales["items_count"] / sales["txn_count"]) if sales["txn_count"] else 0
    atv = aov  # average transaction value

    # Loyalty metrics
    points_issued_pipe = [
        {"$match": {"type": "earn", "created_at": {"$gte": start.isoformat()}}},
        {"$group": {"_id": None, "total": {"$sum": "$points"}}}
    ]
    pi = await points_ledger_col.aggregate(points_issued_pipe).to_list(1)
    points_issued = pi[0]["total"] if pi else 0
    points_redeem_pipe = [
        {"$match": {"type": "redeem", "created_at": {"$gte": start.isoformat()}}},
        {"$group": {"_id": None, "total": {"$sum": "$points"}}}
    ]
    pr = await points_ledger_col.aggregate(points_redeem_pipe).to_list(1)
    points_redeemed = abs(pr[0]["total"]) if pr else 0

    # Outstanding liability = sum of all points_balance
    liab_pipe = [{"$group": {"_id": None, "total": {"$sum": "$points_balance"}}}]
    liab = await customers_col.aggregate(liab_pipe).to_list(1)
    outstanding_points = liab[0]["total"] if liab else 0
    burn_ratio = 0.25
    outstanding_liability = outstanding_points * burn_ratio

    loyalty_customers = await customers_col.count_documents({"lifetime_points_earned": {"$gt": 0}})
    loyalty_penetration = (loyalty_customers / total_customers * 100) if total_customers else 0

    # Repeat / churn
    repeat_customers = await customers_col.count_documents({"visit_count": {"$gte": 2}})
    repeat_rate = (repeat_customers / total_customers * 100) if total_customers else 0
    churned_filter = {"last_visit_at": {"$lt": (datetime.now(timezone.utc) - timedelta(days=180)).isoformat()}}
    churned = await customers_col.count_documents(churned_filter)
    churn_pct = (churned / total_customers * 100) if total_customers else 0

    # Campaigns
    campaign_pipe = [
        {"$group": {"_id": None, "revenue": {"$sum": "$revenue_generated"}, "count": {"$sum": 1}}}
    ]
    cp = await campaigns_col.aggregate(campaign_pipe).to_list(1)
    campaign_revenue = cp[0]["revenue"] if cp else 0
    campaign_count = cp[0]["count"] if cp else 0

    coupon_pipe = [{"$group": {"_id": None, "used": {"$sum": "$times_used"}, "issued": {"$sum": "$times_issued"}}}]
    cu = await coupons_col.aggregate(coupon_pipe).to_list(1)
    coupon_usage = cu[0]["used"] if cu else 0

    # NPS
    nps_pipe = [
        {"$match": {"created_at": {"$gte": start.isoformat()}}},
        {"$group": {
            "_id": None,
            "promoters": {"$sum": {"$cond": [{"$gte": ["$score", 9]}, 1, 0]}},
            "detractors": {"$sum": {"$cond": [{"$lte": ["$score", 6]}, 1, 0]}},
            "total": {"$sum": 1},
        }}
    ]
    npsr = await nps_col.aggregate(nps_pipe).to_list(1)
    if npsr and npsr[0]["total"]:
        nps_score = round(((npsr[0]["promoters"] - npsr[0]["detractors"]) / npsr[0]["total"]) * 100)
    else:
        nps_score = None

    complaint_count = await tickets_col.count_documents({"status": {"$in": ["open", "in_progress", "escalated"]}})

    # API health
    api_total = await api_logs_col.count_documents({"timestamp": {"$gte": start.isoformat()}})
    api_failed = await api_logs_col.count_documents({"status_code": {"$gte": 400}, "timestamp": {"$gte": start.isoformat()}})
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
async def sales_trend(period: str = "30d", user: dict = Depends(get_current_user)):
    start, end = _date_range(period)
    pipeline = [
        {"$match": {"bill_date": {"$gte": start.isoformat(), "$lte": end.isoformat()}}},
        {"$group": {
            "_id": {"$substr": ["$bill_date", 0, 10]},
            "net": {"$sum": "$net_amount"},
            "txns": {"$sum": 1},
            "customers": {"$addToSet": "$customer_id"},
        }},
        {"$sort": {"_id": 1}},
    ]
    rows = await transactions_col.aggregate(pipeline).to_list(500)
    return [
        {"date": r["_id"], "net": round(r["net"], 2), "txns": r["txns"], "customers": len(r["customers"])}
        for r in rows
    ]


@router.get("/store-performance")
async def store_perf(period: str = "30d", user: dict = Depends(get_current_user)):
    start, end = _date_range(period)
    pipeline = [
        {"$match": {"bill_date": {"$gte": start.isoformat(), "$lte": end.isoformat()}}},
        {"$group": {
            "_id": "$store_id",
            "net": {"$sum": "$net_amount"},
            "txns": {"$sum": 1},
            "customers": {"$addToSet": "$customer_id"},
        }},
        {"$sort": {"net": -1}},
        {"$limit": 20},
    ]
    rows = await transactions_col.aggregate(pipeline).to_list(50)
    store_ids = [r["_id"] for r in rows]
    stores = {s["id"]: s async for s in stores_col.find({"id": {"$in": store_ids}}, {"_id": 0})}
    out = []
    for r in rows:
        s = stores.get(r["_id"], {})
        out.append({
            "store_id": r["_id"],
            "store_name": s.get("name", "Unknown"),
            "city": s.get("city", "—"),
            "net": round(r["net"], 2),
            "txns": r["txns"],
            "unique_customers": len(r["customers"]),
            "aov": round(r["net"] / r["txns"], 2) if r["txns"] else 0,
        })
    return out


@router.get("/category-mix")
async def category_mix(period: str = "30d", user: dict = Depends(get_current_user)):
    start, end = _date_range(period)
    pipeline = [
        {"$match": {"bill_date": {"$gte": start.isoformat(), "$lte": end.isoformat()}}},
        {"$unwind": "$items"},
        {"$group": {"_id": "$items.category", "revenue": {"$sum": "$items.total"}, "qty": {"$sum": "$items.quantity"}}},
        {"$sort": {"revenue": -1}},
    ]
    rows = await transactions_col.aggregate(pipeline).to_list(50)
    return [{"category": r["_id"], "revenue": round(r["revenue"], 2), "quantity": r["qty"]} for r in rows]


@router.get("/tier-distribution")
async def tier_distribution(user: dict = Depends(get_current_user)):
    pipeline = [
        {"$group": {"_id": "$tier", "count": {"$sum": 1}, "spend": {"$sum": "$lifetime_spend"}}},
        {"$sort": {"spend": -1}},
    ]
    rows = await customers_col.aggregate(pipeline).to_list(20)
    return [{"tier": r["_id"], "count": r["count"], "lifetime_spend": round(r["spend"], 2)} for r in rows]


@router.get("/top-skus")
async def top_skus(period: str = "30d", limit: int = 10, user: dict = Depends(get_current_user)):
    start, end = _date_range(period)
    pipeline = [
        {"$match": {"bill_date": {"$gte": start.isoformat(), "$lte": end.isoformat()}}},
        {"$unwind": "$items"},
        {"$group": {
            "_id": {"sku": "$items.sku", "name": "$items.name", "category": "$items.category"},
            "revenue": {"$sum": "$items.total"},
            "qty": {"$sum": "$items.quantity"},
        }},
        {"$sort": {"revenue": -1}},
        {"$limit": limit},
    ]
    rows = await transactions_col.aggregate(pipeline).to_list(limit)
    return [
        {"sku": r["_id"]["sku"], "name": r["_id"]["name"], "category": r["_id"]["category"],
         "revenue": round(r["revenue"], 2), "quantity": r["qty"]}
        for r in rows
    ]


@router.get("/command-center")
async def command_center(period: str = "30d", user: dict = Depends(get_current_user)):
    """Live Command Center KPIs + sparkline + cohort distribution + alerts.

    Pure real-time MongoDB aggregations. No snapshots."""
    start, end = _date_range(period)
    prev_start = start - (end - start)
    now = datetime.now(timezone.utc)

    # --- Sales aggregate (current vs previous window) ---
    cur_sales_pipe = [
        {"$match": {"bill_date": {"$gte": start.isoformat(), "$lte": end.isoformat()}}},
        {"$group": {
            "_id": None,
            "net": {"$sum": "$net_amount"},
            "gross": {"$sum": "$gross_amount"},
            "discount": {"$sum": "$discount_amount"},
            "txns": {"$sum": 1},
            "items": {"$sum": {"$size": {"$ifNull": ["$items", []]}}},
            "customers": {"$addToSet": "$customer_id"},
        }},
    ]
    prev_sales_pipe = [
        {"$match": {"bill_date": {"$gte": prev_start.isoformat(), "$lt": start.isoformat()}}},
        {"$group": {"_id": None, "net": {"$sum": "$net_amount"}, "txns": {"$sum": 1}}},
    ]
    cur = (await transactions_col.aggregate(cur_sales_pipe).to_list(1)) or [{}]
    prev = (await transactions_col.aggregate(prev_sales_pipe).to_list(1)) or [{}]
    cur = cur[0] if cur else {}
    prev = prev[0] if prev else {}
    net = cur.get("net", 0) or 0
    txns = cur.get("txns", 0) or 0
    aov = (net / txns) if txns else 0
    upt = ((cur.get("items", 0) or 0) / txns) if txns else 0
    prev_net = prev.get("net", 0) or 0
    prev_txns = prev.get("txns", 0) or 0
    sales_delta = round(((net - prev_net) / prev_net) * 100, 1) if prev_net else None
    txn_delta = round(((txns - prev_txns) / prev_txns) * 100, 1) if prev_txns else None

    # --- Active customers in window ---
    active = await customers_col.count_documents({"last_visit_at": {"$gte": start.isoformat()}})
    total_customers = await customers_col.count_documents({})

    # --- Repeat rate window (customers with >=2 txns in window) ---
    repeat_pipe = [
        {"$match": {"bill_date": {"$gte": start.isoformat(), "$lte": end.isoformat()},
                    "customer_id": {"$ne": None}}},
        {"$group": {"_id": "$customer_id", "n": {"$sum": 1}}},
        {"$group": {"_id": None,
                    "repeat": {"$sum": {"$cond": [{"$gte": ["$n", 2]}, 1, 0]}},
                    "unique": {"$sum": 1}}},
    ]
    rr = (await transactions_col.aggregate(repeat_pipe).to_list(1)) or [{}]
    rr = rr[0] if rr else {}
    repeat_rate = round((rr.get("repeat", 0) / rr["unique"]) * 100, 1) if rr.get("unique") else 0

    # --- NPS in window ---
    nps_pipe = [
        {"$match": {"created_at": {"$gte": start.isoformat()}}},
        {"$group": {"_id": None,
                    "promoters": {"$sum": {"$cond": [{"$gte": ["$score", 9]}, 1, 0]}},
                    "detractors": {"$sum": {"$cond": [{"$lte": ["$score", 6]}, 1, 0]}},
                    "total": {"$sum": 1}}},
    ]
    nps_rows = (await nps_col.aggregate(nps_pipe).to_list(1)) or []
    if nps_rows and nps_rows[0]["total"]:
        nps_score = round(((nps_rows[0]["promoters"] - nps_rows[0]["detractors"]) / nps_rows[0]["total"]) * 100)
    else:
        nps_score = None

    # --- API health in window ---
    api_total = await api_logs_col.count_documents({"timestamp": {"$gte": start.isoformat()}})
    api_failed = await api_logs_col.count_documents({"status_code": {"$gte": 400},
                                                     "timestamp": {"$gte": start.isoformat()}})
    api_health = round(((api_total - api_failed) / api_total) * 100, 2) if api_total else 100.0

    # --- Outstanding loyalty liability ---
    liab_pipe = [{"$group": {"_id": None,
                              "points": {"$sum": "$points_balance"},
                              "issued": {"$sum": "$lifetime_points_earned"},
                              "redeemed": {"$sum": "$lifetime_points_redeemed"}}}]
    liab = (await customers_col.aggregate(liab_pipe).to_list(1)) or [{}]
    liab = liab[0] if liab else {}
    burn_ratio = 0.25
    outstanding_points = int(liab.get("points", 0) or 0)
    outstanding_inr = round(outstanding_points * burn_ratio, 2)

    # --- Cohort distribution: customers acquired today, 7d, 30d, 90d, >90d ---
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    d7 = now - timedelta(days=7)
    d30 = now - timedelta(days=30)
    d90 = now - timedelta(days=90)
    cohort = {
        "today": await customers_col.count_documents({"created_at": {"$gte": today_start.isoformat()}}),
        "last_7d": await customers_col.count_documents({"created_at": {"$gte": d7.isoformat(), "$lt": today_start.isoformat()}}),
        "last_30d": await customers_col.count_documents({"created_at": {"$gte": d30.isoformat(), "$lt": d7.isoformat()}}),
        "last_90d": await customers_col.count_documents({"created_at": {"$gte": d90.isoformat(), "$lt": d30.isoformat()}}),
        "older": await customers_col.count_documents({"created_at": {"$lt": d90.isoformat()}}),
    }

    # --- Sparkline: daily net sales for the window ---
    spark_pipe = [
        {"$match": {"bill_date": {"$gte": start.isoformat(), "$lte": end.isoformat()}}},
        {"$group": {"_id": {"$substr": ["$bill_date", 0, 10]},
                    "net": {"$sum": "$net_amount"},
                    "txns": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    spark_rows = await transactions_col.aggregate(spark_pipe).to_list(400)
    sparkline = [{"date": r["_id"], "net": round(r["net"], 2), "txns": r["txns"]} for r in spark_rows]

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
    open_tickets = await tickets_col.count_documents({"status": {"$in": ["open", "in_progress", "escalated"]}})
    if open_tickets > 10:
        alerts.append({"severity": "medium", "title": "Open complaints",
                       "detail": f"{open_tickets} support tickets need attention.",
                       "link": "/admin/tickets?status=open"})
    if nps_score is not None and nps_score < 30:
        alerts.append({"severity": "high", "title": "NPS below threshold",
                       "detail": f"NPS score is {nps_score} ({period}).",
                       "link": "/admin/dashboards/nps"})

    return {
        "period": period,
        "generated_at": now.isoformat(),
        "kpis": {
            "net_sales": round(net, 2),
            "net_sales_delta_pct": sales_delta,
            "transactions": txns,
            "transactions_delta_pct": txn_delta,
            "aov": round(aov, 2),
            "upt": round(upt, 2),
            "active_customers": active,
            "total_customers": total_customers,
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


@router.get("/city-performance")
async def city_performance(period: str = "30d", user: dict = Depends(get_current_user)):
    start, end = _date_range(period)
    pipeline = [
        {"$match": {"bill_date": {"$gte": start.isoformat(), "$lte": end.isoformat()}}},
        {"$lookup": {"from": "stores", "localField": "store_id", "foreignField": "id", "as": "store"}},
        {"$unwind": "$store"},
        {"$group": {"_id": "$store.city", "net": {"$sum": "$net_amount"}, "txns": {"$sum": 1}}},
        {"$sort": {"net": -1}},
    ]
    rows = await transactions_col.aggregate(pipeline).to_list(50)
    return [{"city": r["_id"], "net": round(r["net"], 2), "txns": r["txns"]} for r in rows]
