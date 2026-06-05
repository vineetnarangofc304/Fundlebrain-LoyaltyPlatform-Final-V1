"""Fundle Brain - MongoDB function-calling tool registry.

Each tool is a safe, predefined MongoDB query that GPT-5.2 can invoke.
The schemas follow OpenAI's `tools=[{type: "function", function: {...}}]` spec.
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List
from database import (
    customers_col, transactions_col, stores_col, campaigns_col, coupons_col,
    points_ledger_col, nps_col, tickets_col, message_log_col, campaign_metrics_col,
    loyalty_config_col,
)
from routes._loyalty import LOYALTY_TX_MATCH, loyalty_match


# ---------------- Tool JSON schemas (OpenAI function-calling) ----------------
TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_overall_kpis",
            "description": "Return live business KPIs for the brand: total loyalty customers, net sales / txns over the last N days, average order value, points outstanding, OUTSTANDING LIABILITY in ₹ (points × burn_ratio), and the burn/earn ratios. Pass days=0 for ALL-TIME (full historical scan). Use this when asked about liability, points obligation, total points, or any rupee-value of unredeemed points.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Window in days. 0 = all time (full history). Default 30.", "default": 30}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "top_churning_customers",
            "description": "Return high-value customers who have not transacted in N days. Sorted by lifetime_spend desc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "inactive_days": {"type": "integer", "default": 120},
                    "min_lifetime_spend": {"type": "number", "default": 5000},
                    "limit": {"type": "integer", "default": 15},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "store_performance",
            "description": "Sales aggregation by store for last N days. Returns net revenue, txns, AOV per store. Pass days=0 for ALL-TIME.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "0 = all time. Default 30.", "default": 30},
                    "limit": {"type": "integer", "default": 30},
                    "sort": {"type": "string", "enum": ["net_desc", "net_asc", "txns_desc"], "default": "net_desc"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "city_performance",
            "description": "Sales aggregation by city for last N days. Pass days=0 for ALL-TIME.",
            "parameters": {
                "type": "object",
                "properties": {"days": {"type": "integer", "description": "0 = all time.", "default": 30}, "limit": {"type": "integer", "default": 25}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "campaign_leaderboard",
            "description": "List campaigns sorted by ROI / revenue / clicks with their funnel numbers (sent, delivered, clicked, converted, revenue).",
            "parameters": {
                "type": "object",
                "properties": {
                    "sort": {"type": "string", "enum": ["roi", "revenue", "clicks", "converted"], "default": "revenue"},
                    "limit": {"type": "integer", "default": 15},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "top_skus",
            "description": "Top-selling SKUs / products by revenue in last N days. Pass days=0 for ALL-TIME.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "0 = all time.", "default": 30},
                    "limit": {"type": "integer", "default": 15},
                    "category": {"type": "string", "description": "Optional category filter"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tier_distribution",
            "description": "Breakdown of customers by loyalty tier with count, lifetime spend, points balance.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "nps_summary",
            "description": "Net Promoter Score breakdown (promoters / passives / detractors) for last N days plus overall NPS.",
            "parameters": {
                "type": "object",
                "properties": {"days": {"type": "integer", "default": 60}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "customer_lookup",
            "description": "Look up a single customer by mobile number. Returns profile, tier, lifetime spend, recent transactions.",
            "parameters": {
                "type": "object",
                "properties": {"mobile": {"type": "string", "description": "10 or 12 digit mobile"}},
                "required": ["mobile"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "coupon_performance",
            "description": "List coupons with redemption counts and revenue generated through them.",
            "parameters": {
                "type": "object",
                "properties": {
                    "is_active": {"type": "boolean"},
                    "limit": {"type": "integer", "default": 20},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "communication_log_summary",
            "description": "Summary of recent SMS / WhatsApp dispatches: success vs failure counts, per channel.",
            "parameters": {
                "type": "object",
                "properties": {"days": {"type": "integer", "default": 7}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rfm_segments",
            "description": "Distribution of customers across RFM segments (champions, loyal, at-risk, lost, etc.) with counts and avg lifetime spend.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _norm_days(days: int) -> int:
    """`days <= 0` => 'all time' (20-year window). Lets the LLM (and the UI)
    request a full historical scan when the data lives years in the past."""
    if days is None or days <= 0:
        return 365 * 20
    return days


# ---------------- Tool implementations ----------------
async def _tool_get_overall_kpis(days: int = 30) -> Dict[str, Any]:
    days = _norm_days(days)
    start = _iso(datetime.now(timezone.utc) - timedelta(days=days))
    # R5: loyalty members only
    total_cust = await customers_col.count_documents({"mobile": {"$nin": [None, ""]}})
    sales = await transactions_col.aggregate([
        {"$match": loyalty_match({"bill_date": {"$gte": start}})},
        {"$group": {"_id": None, "net": {"$sum": "$net_amount"},
                    "txns": {"$sum": 1}, "gross": {"$sum": "$gross_amount"}}},
    ]).to_list(1)
    pts = await customers_col.aggregate([
        {"$match": {"mobile": {"$nin": [None, ""]}}},
        {"$group": {"_id": None, "outstanding": {"$sum": "$points_balance"},
                    "earned": {"$sum": "$lifetime_points_earned"},
                    "redeemed": {"$sum": "$lifetime_points_redeemed"}}}
    ]).to_list(1)

    # Pull burn_ratio from loyalty_config so the LLM can compute liability in ₹
    # without needing a follow-up question. Default to 0.25 per point (matches
    # Command Center hint).
    cfg = await loyalty_config_col.find_one({}, {"_id": 0})
    burn_ratio = float((cfg or {}).get("burn_ratio") or 0.25)
    earn_ratio = float((cfg or {}).get("earn_ratio") or 1.0)
    outstanding = int(pts[0]["outstanding"]) if pts else 0
    return {
        "window_days": days,
        "total_customers": total_cust,
        "net_sales": round(sales[0]["net"], 2) if sales else 0,
        "transactions": sales[0]["txns"] if sales else 0,
        "average_order_value": round(sales[0]["net"] / sales[0]["txns"], 2) if sales and sales[0]["txns"] else 0,
        "points_outstanding": outstanding,
        "outstanding_liability_inr": round(outstanding * burn_ratio, 2),
        "burn_ratio_inr_per_point": burn_ratio,
        "earn_ratio_pts_per_inr": earn_ratio,
        "lifetime_points_earned": int(pts[0]["earned"]) if pts else 0,
        "lifetime_points_redeemed": int(pts[0]["redeemed"]) if pts else 0,
    }


async def _tool_top_churning_customers(inactive_days: int = 120, min_lifetime_spend: float = 5000,
                                       limit: int = 15) -> Dict[str, Any]:
    inactive_days = _norm_days(inactive_days)
    cutoff = _iso(datetime.now(timezone.utc) - timedelta(days=inactive_days))
    rows = await customers_col.find(
        {"mobile": {"$nin": [None, ""]},  # R5: loyalty members only
         "last_visit_at": {"$lt": cutoff}, "lifetime_spend": {"$gte": min_lifetime_spend}},
        {"_id": 0, "id": 1, "name": 1, "mobile": 1, "city": 1, "tier": 1,
         "lifetime_spend": 1, "points_balance": 1, "last_visit_at": 1, "churn_risk": 1}
    ).sort("lifetime_spend", -1).limit(min(limit, 50)).to_list(50)
    return {"count": len(rows), "customers": rows, "cutoff_date": cutoff}


async def _tool_store_performance(days: int = 30, limit: int = 30, sort: str = "net_desc") -> Dict[str, Any]:
    days = _norm_days(days)
    start = _iso(datetime.now(timezone.utc) - timedelta(days=days))
    sort_field = {"net_desc": ("net", -1), "net_asc": ("net", 1), "txns_desc": ("txns", -1)}[sort]
    pipe = [
        {"$match": loyalty_match({"bill_date": {"$gte": start}})},
        {"$group": {"_id": "$store_id", "net": {"$sum": "$net_amount"},
                    "txns": {"$sum": 1}, "customers": {"$addToSet": "$customer_mobile"}}},
        {"$sort": {sort_field[0]: sort_field[1]}},
        {"$limit": min(limit, 50)},
    ]
    rows = await transactions_col.aggregate(pipe).to_list(50)
    store_ids = [r["_id"] for r in rows if r["_id"]]
    stores = {s["id"]: s async for s in stores_col.find({"id": {"$in": store_ids}}, {"_id": 0})}
    out = []
    for r in rows:
        s = stores.get(r["_id"], {})
        out.append({
            "store": s.get("name", "—"), "code": s.get("code"), "city": s.get("city"),
            "net": round(r["net"], 2), "txns": r["txns"],
            "aov": round(r["net"] / r["txns"], 2) if r["txns"] else 0,
            "unique_customers": len([c for c in r["customers"] if c]),
        })
    return {"window_days": days, "rows": out}


async def _tool_city_performance(days: int = 30, limit: int = 25) -> Dict[str, Any]:
    days = _norm_days(days)
    start = _iso(datetime.now(timezone.utc) - timedelta(days=days))
    pipe = [
        {"$match": loyalty_match({"bill_date": {"$gte": start}})},
        {"$lookup": {"from": "stores", "localField": "store_id", "foreignField": "id", "as": "s"}},
        {"$unwind": "$s"},
        {"$group": {"_id": "$s.city", "net": {"$sum": "$net_amount"}, "txns": {"$sum": 1}}},
        {"$sort": {"net": -1}}, {"$limit": min(limit, 30)},
    ]
    rows = await transactions_col.aggregate(pipe).to_list(30)
    return {
        "window_days": days,
        "rows": [{"city": r["_id"], "net": round(r["net"], 2), "txns": r["txns"],
                  "aov": round(r["net"] / r["txns"], 2) if r["txns"] else 0} for r in rows],
    }


async def _tool_campaign_leaderboard(sort: str = "revenue", limit: int = 15) -> Dict[str, Any]:
    campaigns = await campaigns_col.find({}, {"_id": 0}).to_list(500)
    metrics = await campaign_metrics_col.find({}, {"_id": 0}).to_list(2000)
    by_c: Dict[str, Dict[str, Any]] = {}
    for m in metrics:
        b = by_c.setdefault(m["campaign_id"], {"sent": 0, "delivered": 0, "opened": 0,
                                                "clicked": 0, "converted": 0, "revenue": 0.0, "cost": 0.0})
        for k in ("sent", "delivered", "opened", "clicked", "converted"):
            b[k] += int(m.get(k, 0) or 0)
        b["revenue"] += float(m.get("revenue_generated", 0) or 0)
        b["cost"] += float(m.get("cost", 0) or 0)

    out = []
    for c in campaigns:
        b = by_c.get(c["id"], {})
        sent = b.get("sent") or c.get("sent", 0)
        delivered = b.get("delivered") or c.get("delivered", 0)
        clicked = b.get("clicked") or c.get("clicked", 0)
        converted = b.get("converted") or c.get("redeemed", 0)
        revenue = b.get("revenue") or float(c.get("revenue_generated", 0) or 0)
        cost = b.get("cost", 0)
        roi = round(((revenue - cost) / cost) * 100, 1) if cost else None
        out.append({"name": c.get("name"), "status": c.get("status"),
                    "channels": c.get("channels", []),
                    "sent": sent, "delivered": delivered, "clicked": clicked,
                    "converted": converted, "revenue": round(revenue, 2),
                    "ctr_pct": round(clicked / delivered * 100, 2) if delivered else 0,
                    "cvr_pct": round(converted / clicked * 100, 2) if clicked else 0,
                    "roi_pct": roi})
    key = {"revenue": "revenue", "clicks": "clicked", "converted": "converted",
           "roi": "roi_pct"}[sort]
    out.sort(key=lambda r: (r[key] or 0), reverse=True)
    return {"count": len(out), "rows": out[: min(limit, 30)]}


async def _tool_top_skus(days: int = 30, limit: int = 15, category: str | None = None) -> Dict[str, Any]:
    days = _norm_days(days)
    start = _iso(datetime.now(timezone.utc) - timedelta(days=days))
    pipe: List[Dict[str, Any]] = [
        {"$match": loyalty_match({"bill_date": {"$gte": start}})},
        {"$unwind": "$items"},
    ]
    if category:
        pipe.append({"$match": {"items.category": category}})
    pipe += [
        {"$group": {"_id": {"sku": "$items.sku", "name": "$items.name", "category": "$items.category"},
                    "revenue": {"$sum": "$items.total"}, "qty": {"$sum": "$items.quantity"}}},
        {"$sort": {"revenue": -1}}, {"$limit": min(limit, 30)},
    ]
    rows = await transactions_col.aggregate(pipe).to_list(30)
    return {
        "window_days": days, "category_filter": category,
        "rows": [{"sku": r["_id"]["sku"], "name": r["_id"]["name"],
                  "category": r["_id"]["category"], "revenue": round(r["revenue"], 2),
                  "qty_sold": r["qty"]} for r in rows],
    }


async def _tool_tier_distribution() -> Dict[str, Any]:
    rows = await customers_col.aggregate([
        {"$match": {"mobile": {"$nin": [None, ""]}}},  # R5: loyalty members only
        {"$group": {"_id": "$tier", "count": {"$sum": 1},
                    "spend": {"$sum": "$lifetime_spend"},
                    "points": {"$sum": "$points_balance"}}}
    ]).to_list(20)
    return {
        "tiers": [{"tier": r["_id"], "customers": r["count"],
                    "lifetime_spend": round(r["spend"], 2),
                    "points_outstanding": int(r["points"])} for r in rows],
    }


async def _tool_nps_summary(days: int = 60) -> Dict[str, Any]:
    days = _norm_days(days)
    start = _iso(datetime.now(timezone.utc) - timedelta(days=days))
    rows = await nps_col.aggregate([
        {"$match": {"created_at": {"$gte": start}}},
        {"$group": {"_id": "$sentiment", "count": {"$sum": 1}}}
    ]).to_list(10)
    by_s = {r["_id"]: r["count"] for r in rows}
    total = sum(by_s.values())
    promoters = by_s.get("promoter", 0)
    detractors = by_s.get("detractor", 0)
    nps = round((promoters - detractors) / total * 100, 1) if total else None
    return {"window_days": days, "total_responses": total, "promoters": promoters,
            "passives": by_s.get("passive", 0), "detractors": detractors, "nps": nps}


async def _tool_customer_lookup(mobile: str) -> Dict[str, Any]:
    import re
    digits = re.sub(r"\D", "", mobile or "")
    if len(digits) == 10:
        digits = f"91{digits}"
    cust = await customers_col.find_one(
        {"$or": [{"mobile": mobile}, {"mobile": digits}, {"mobile": digits[-10:]}]},
        {"_id": 0}
    )
    if not cust:
        return {"found": False, "mobile": mobile}
    txns = await transactions_col.find(
        {"$or": [{"customer_mobile": cust.get("mobile")}, {"customer_id": cust.get("id")}]},
        {"_id": 0, "bill_number": 1, "bill_date": 1, "net_amount": 1,
         "store_id": 1, "points_earned": 1}
    ).sort("bill_date", -1).limit(10).to_list(10)
    return {"found": True, "customer": cust, "recent_transactions": txns}


async def _tool_coupon_performance(is_active: bool | None = None, limit: int = 20) -> Dict[str, Any]:
    flt: Dict[str, Any] = {}
    if is_active is not None:
        flt["is_active"] = is_active
    coupons = await coupons_col.find(flt, {"_id": 0, "id": 1, "code": 1, "name": 1,
                                            "coupon_type": 1, "discount_value": 1,
                                            "times_used": 1, "times_issued": 1,
                                            "is_active": 1}).limit(min(limit, 50)).to_list(50)
    return {"count": len(coupons), "coupons": coupons}


async def _tool_communication_log_summary(days: int = 7) -> Dict[str, Any]:
    days = _norm_days(days)
    start = _iso(datetime.now(timezone.utc) - timedelta(days=days))
    rows = await message_log_col.aggregate([
        {"$match": {"timestamp": {"$gte": start}}},
        {"$group": {"_id": {"channel": "$channel", "status": "$status"}, "n": {"$sum": 1}}}
    ]).to_list(50)
    out: Dict[str, Dict[str, int]] = {}
    for r in rows:
        ch = r["_id"]["channel"]
        st = r["_id"]["status"]
        out.setdefault(ch, {"total": 0, "ok": 0, "failed": 0})
        out[ch]["total"] += r["n"]
        if st == "ok":
            out[ch]["ok"] += r["n"]
        else:
            out[ch]["failed"] += r["n"]
    return {"window_days": days, "channels": out}


async def _tool_rfm_segments() -> Dict[str, Any]:
    # Use customers' churn_risk + tier as a proxy if RFM not computed; live aggregation
    rows = await customers_col.aggregate([
        {"$group": {"_id": {"tier": "$tier", "churn_risk": "$churn_risk"},
                    "count": {"$sum": 1},
                    "avg_spend": {"$avg": "$lifetime_spend"}}}
    ]).to_list(40)
    return {"segments": [{"tier": r["_id"].get("tier"), "churn_risk": r["_id"].get("churn_risk"),
                            "count": r["count"], "avg_lifetime_spend": round(r["avg_spend"], 2)}
                            for r in rows]}


TOOL_HANDLERS = {
    "get_overall_kpis": _tool_get_overall_kpis,
    "top_churning_customers": _tool_top_churning_customers,
    "store_performance": _tool_store_performance,
    "city_performance": _tool_city_performance,
    "campaign_leaderboard": _tool_campaign_leaderboard,
    "top_skus": _tool_top_skus,
    "tier_distribution": _tool_tier_distribution,
    "nps_summary": _tool_nps_summary,
    "customer_lookup": _tool_customer_lookup,
    "coupon_performance": _tool_coupon_performance,
    "communication_log_summary": _tool_communication_log_summary,
    "rfm_segments": _tool_rfm_segments,
}

# Merge in extended tools (Support Desk writes + 16 more reads)
from routes.ai_extended_tools import EXTRA_TOOL_SCHEMAS, EXTRA_TOOL_HANDLERS  # noqa: E402
TOOL_SCHEMAS.extend(EXTRA_TOOL_SCHEMAS)
TOOL_HANDLERS.update(EXTRA_TOOL_HANDLERS)


async def execute_tool(name: str, args: Dict[str, Any], user: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Execute a tool by name with the given JSON args. Returns dict.

    `user` is required for any WRITE tool (role enforcement + audit logging).
    Read-only tools simply ignore it.
    """
    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return {"error": f"Unknown tool '{name}'"}
    try:
        # Inspect if handler accepts a `user` keyword
        import inspect
        sig = inspect.signature(handler)
        if "user" in sig.parameters:
            return await handler(**(args or {}), user=user)
        return await handler(**(args or {}))
    except TypeError as e:
        return {"error": f"Bad arguments for {name}: {e}"}
    except Exception as e:
        return {"error": f"Tool {name} failed: {e}"}
