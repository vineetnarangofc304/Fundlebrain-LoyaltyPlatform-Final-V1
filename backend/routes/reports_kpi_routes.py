"""KPI & data reports built from the client's reference Excel/CSV formats:

* Store KPI Report     — per-store metrics (sales, discount, fresh/return bills,
                         new vs repeat vs mapped/unmapped customers, ATV, customer
                         counts) with optional Year-over-Year growth.
                         (MARCH KPI / Store_wise_KPI)
* CRM Customer Report  — the customer master (points, billing, visits, recency,
                         DOB/DOA …) with filters, sorting, column-select, export.
                         (CRM_Report.csv)
* KPI Trend            — sales / bills / customers / discount bucketed by
                         day / week / month for the trend charts. (Weekly_KPI)

All money is net revenue (net_amount, post-discount). Two routers: the main one runs
under db_deadline (45s); exports get their own deadline-free streaming router.
"""
from __future__ import annotations

import csv
import io
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pymongo
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from auth import get_current_user
from database import customers_col, transactions_col
from routes._db_timeout import db_deadline

logger = logging.getLogger("kazo-fundle.kpi_reports")

router = APIRouter(prefix="/kpi-reports", tags=["kpi-reports"],
                   dependencies=[Depends(db_deadline)])
export_router = APIRouter(prefix="/kpi-reports", tags=["kpi-reports"])

EXPORT_MAX_ROWS = 2_000_000
IST = timezone(timedelta(hours=5, minutes=30))


def _esc(s: str) -> str:
    return re.escape((s or "").strip())


def _date_match(start_date: Optional[str], end_date: Optional[str]) -> Dict[str, Any]:
    m: Dict[str, Any] = {}
    if start_date and end_date:
        m["bill_date"] = {"$gte": start_date, "$lte": end_date + "T23:59:59Z"}
    elif start_date:
        m["bill_date"] = {"$gte": start_date}
    elif end_date:
        m["bill_date"] = {"$lte": end_date + "T23:59:59Z"}
    return m


def _store_match(start_date, end_date, zone, city, store_class, store_id) -> Dict[str, Any]:
    m = _date_match(start_date, end_date)
    if zone:
        m["zone"] = zone
    if city:
        m["city"] = city
    if store_class:
        m["store_class"] = store_class
    if store_id:
        m["store_id"] = store_id
    return m


# ── Store KPI aggregation ─────────────────────────────────────────────────────
_NE_RETURN = {"$ne": ["$is_return", True]}
_IS_RETURN = {"$eq": ["$is_return", True]}
_IS_NEW = {"$eq": [{"$toLower": {"$ifNull": ["$new_or_existing", ""]}}, "new"]}
_IS_EXISTING = {"$eq": [{"$toLower": {"$ifNull": ["$new_or_existing", ""]}}, "existing"]}
_HAS_MOBILE = {"$ne": [{"$ifNull": ["$customer_mobile", None]}, None]}


def _store_group_stage() -> Dict[str, Any]:
    def fresh_sum(expr):  # sum `expr` only on fresh (non-return) bills
        return {"$sum": {"$cond": [_NE_RETURN, expr, 0]}}

    def addset(cond):
        return {"$addToSet": {"$cond": [cond, "$customer_mobile", "$$REMOVE"]}}

    return {
        "$group": {
            "_id": "$store_id",
            "store_code": {"$first": "$store_code"},
            "store_name": {"$first": "$store_name"},
            "store_class": {"$first": "$store_class"},
            "zone": {"$first": "$zone"},
            "city": {"$first": "$city"},
            "overall_sales": {"$sum": "$net_amount"},
            "total_discount": {"$sum": "$discount_amount"},
            "net_before_tax": {"$sum": "$net_amount_before_tax"},
            "total_tax": {"$sum": "$tax_amount"},
            "fresh_bills": fresh_sum(1),
            "fresh_value": fresh_sum("$net_amount"),
            "return_bills": {"$sum": {"$cond": [_IS_RETURN, 1, 0]}},
            "return_value": {"$sum": {"$cond": [_IS_RETURN, "$net_amount", 0]}},
            "new_txn": {"$sum": {"$cond": [{"$and": [_NE_RETURN, _IS_NEW]}, 1, 0]}},
            "new_value": {"$sum": {"$cond": [{"$and": [_NE_RETURN, _IS_NEW]}, "$net_amount", 0]}},
            "repeat_txn": {"$sum": {"$cond": [{"$and": [_NE_RETURN, _IS_EXISTING]}, 1, 0]}},
            "repeat_value": {"$sum": {"$cond": [{"$and": [_NE_RETURN, _IS_EXISTING]}, "$net_amount", 0]}},
            "mapped_txn": {"$sum": {"$cond": [{"$and": [_NE_RETURN, _HAS_MOBILE]}, 1, 0]}},
            "unmapped_txn": {"$sum": {"$cond": [{"$and": [_NE_RETURN, {"$not": [_HAS_MOBILE]}]}, 1, 0]}},
            "customers": addset({"$and": [_NE_RETURN, _HAS_MOBILE]}),
            "new_customers": addset({"$and": [_NE_RETURN, _IS_NEW, _HAS_MOBILE]}),
            "existing_customers": addset({"$and": [_NE_RETURN, _IS_EXISTING, _HAS_MOBILE]}),
        }
    }


def _finalize_store_row(g: Dict[str, Any]) -> Dict[str, Any]:
    def atv(value, txn):
        return round(value / txn, 2) if txn else 0.0

    overall_cust = len(g.get("customers", []) or [])
    new_cust = len(g.get("new_customers", []) or [])
    existing_cust = len(g.get("existing_customers", []) or [])
    return {
        "store_id": g.get("_id") or "",
        "store_code": g.get("store_code") or "—",
        "store_name": g.get("store_name") or "—",
        "store_class": g.get("store_class") or "—",
        "zone": g.get("zone") or "—",
        "city": g.get("city") or "—",
        "overall_sales": round(g.get("overall_sales", 0) or 0, 2),
        "total_discount": round(g.get("total_discount", 0) or 0, 2),
        "net_before_tax": round(g.get("net_before_tax", 0) or 0, 2),
        "total_tax": round(g.get("total_tax", 0) or 0, 2),
        "fresh_bills": int(g.get("fresh_bills", 0) or 0),
        "fresh_value": round(g.get("fresh_value", 0) or 0, 2),
        "return_bills": int(g.get("return_bills", 0) or 0),
        "return_value": round(g.get("return_value", 0) or 0, 2),
        "new_txn": int(g.get("new_txn", 0) or 0),
        "new_value": round(g.get("new_value", 0) or 0, 2),
        "new_atv": atv(g.get("new_value", 0) or 0, g.get("new_txn", 0) or 0),
        "repeat_txn": int(g.get("repeat_txn", 0) or 0),
        "repeat_value": round(g.get("repeat_value", 0) or 0, 2),
        "repeat_atv": atv(g.get("repeat_value", 0) or 0, g.get("repeat_txn", 0) or 0),
        "mapped_txn": int(g.get("mapped_txn", 0) or 0),
        "unmapped_txn": int(g.get("unmapped_txn", 0) or 0),
        "overall_customers": overall_cust,
        "new_customer_count": new_cust,
        "existing_customers": existing_cust,
        "overall_atv": atv(g.get("fresh_value", 0) or 0, g.get("fresh_bills", 0) or 0),
    }


async def _run_store_kpi(match: Dict[str, Any]) -> List[Dict[str, Any]]:
    pipe = [{"$match": match}, _store_group_stage()]
    raw = await transactions_col.aggregate(pipe, allowDiskUse=True).to_list(2000)
    rows = [_finalize_store_row(g) for g in raw]
    await _fill_store_identity(rows)
    return rows


async def _fill_store_identity(rows: List[Dict[str, Any]]) -> None:
    """Backfill store_name / code / class / zone from the stores master when the bill
    rows didn't carry the denormalized values (keeps the report readable on any data)."""
    ids = [r["store_id"] for r in rows if r.get("store_id") and (
        r.get("store_name") in (None, "—") or r.get("store_code") in (None, "—")
        or r.get("store_class") in (None, "—") or r.get("zone") in (None, "—"))]
    if not ids:
        return
    from database import stores_col
    smap = {}
    async for s in stores_col.find({"id": {"$in": ids}},
                                   {"_id": 0, "id": 1, "name": 1, "code": 1, "store_class": 1, "region": 1}):
        smap[s["id"]] = s
    for r in rows:
        s = smap.get(r.get("store_id"))
        if not s:
            continue
        if r.get("store_name") in (None, "—"):
            r["store_name"] = s.get("name") or r["store_name"]
        if r.get("store_code") in (None, "—"):
            r["store_code"] = s.get("code") or r["store_code"]
        if r.get("store_class") in (None, "—"):
            r["store_class"] = s.get("store_class") or r["store_class"]
        if r.get("zone") in (None, "—"):
            r["zone"] = s.get("region") or r["zone"]


STORE_SORT_FIELDS = {
    "store_name", "store_code", "store_class", "zone", "city",
    "overall_sales", "total_discount", "fresh_bills", "fresh_value",
    "return_bills", "return_value", "new_txn", "repeat_txn", "mapped_txn",
    "unmapped_txn", "overall_customers", "new_customer_count",
    "existing_customers", "overall_atv", "new_atv", "repeat_atv",
}

STORE_COLUMNS: List[Tuple[str, str]] = [
    ("store_code", "Store Code"), ("store_name", "Store"), ("store_class", "Class"),
    ("zone", "Zone"), ("city", "City"),
    ("overall_sales", "Overall Sales"), ("total_discount", "Total Discount"),
    ("net_before_tax", "Net Before Tax"), ("total_tax", "Total Tax"),
    ("fresh_bills", "Fresh Bills"), ("fresh_value", "Fresh Bill Value"),
    ("return_bills", "Return Bills"), ("return_value", "Return Bill Value"),
    ("new_txn", "New Cust Txns"), ("new_value", "New Cust Value"), ("new_atv", "New ATV"),
    ("repeat_txn", "Repeat Cust Txns"), ("repeat_value", "Repeat Cust Value"), ("repeat_atv", "Repeat ATV"),
    ("mapped_txn", "Mapped Txns"), ("unmapped_txn", "Unmapped Txns"),
    ("overall_customers", "Overall Customers"), ("new_customer_count", "New Customers"),
    ("existing_customers", "Existing Customers"), ("overall_atv", "Overall ATV"),
]


def _shift_year(d: Optional[str], years: int) -> Optional[str]:
    if not d:
        return d
    try:
        dt = datetime.fromisoformat(d)
        try:
            return dt.replace(year=dt.year - years).isoformat()[:10]
        except ValueError:  # Feb-29
            return dt.replace(year=dt.year - years, day=28).isoformat()[:10]
    except Exception:
        return d


def _growth(cur: float, prev: float) -> Optional[float]:
    if not prev:
        return None
    return round((cur - prev) / prev, 4)


@router.get("/store-kpi")
async def store_kpi(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    zone: Optional[str] = None,
    city: Optional[str] = None,
    store_class: Optional[str] = None,
    store_id: Optional[str] = None,
    compare: bool = False,
    sort_by: str = "overall_sales",
    sort_dir: str = "desc",
    user=Depends(get_current_user),
):
    match = _store_match(start_date, end_date, zone, city, store_class, store_id)
    rows = await _run_store_kpi(match)

    if compare and (start_date or end_date):
        for years, key in ((1, "prev"), (2, "prev2")):
            m2 = _store_match(_shift_year(start_date, years), _shift_year(end_date, years),
                              zone, city, store_class, store_id)
            prev_rows = {r["store_id"]: r for r in await _run_store_kpi(m2)}
            for r in rows:
                pr = prev_rows.get(r["store_id"], {})
                r[f"{key}_sales"] = pr.get("overall_sales", 0)
                r[f"{key}_customers"] = pr.get("overall_customers", 0)
            # growth vs prev year (only attach the 25-26 style growth once, for `prev`)
            if key == "prev":
                for r in rows:
                    r["growth_sales"] = _growth(r["overall_sales"], r.get("prev_sales", 0))
                    r["growth_customers"] = _growth(r["overall_customers"], r.get("prev_customers", 0))

    sf = sort_by if sort_by in STORE_SORT_FIELDS else "overall_sales"
    rows.sort(key=lambda r: (r.get(sf) is None, r.get(sf)), reverse=(sort_dir != "asc"))

    totals = {k: 0 for k in (
        "overall_sales", "total_discount", "net_before_tax", "total_tax",
        "fresh_bills", "fresh_value", "return_bills", "return_value",
        "new_txn", "repeat_txn", "mapped_txn", "unmapped_txn",
        "overall_customers", "new_customer_count", "existing_customers")}
    for r in rows:
        for k in totals:
            totals[k] += r.get(k, 0) or 0
    for k in ("overall_sales", "total_discount", "net_before_tax", "total_tax", "fresh_value", "return_value"):
        totals[k] = round(totals[k], 2)

    return {"rows": rows, "totals": totals, "count": len(rows), "compare": compare,
            "columns": [{"key": k, "label": l} for k, l in STORE_COLUMNS]}


@export_router.get("/store-kpi/export")
async def store_kpi_export(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    zone: Optional[str] = None,
    city: Optional[str] = None,
    store_class: Optional[str] = None,
    store_id: Optional[str] = None,
    sort_by: str = "overall_sales",
    sort_dir: str = "desc",
    user=Depends(get_current_user),
):
    match = _store_match(start_date, end_date, zone, city, store_class, store_id)
    with pymongo.timeout(120):
        rows = await _run_store_kpi(match)
    sf = sort_by if sort_by in STORE_SORT_FIELDS else "overall_sales"
    rows.sort(key=lambda r: (r.get(sf) is None, r.get(sf)), reverse=(sort_dir != "asc"))

    def gen():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([l for _, l in STORE_COLUMNS])
        yield buf.getvalue(); buf.seek(0); buf.truncate(0)
        for r in rows:
            w.writerow([r.get(k, "") for k, _ in STORE_COLUMNS])
            yield buf.getvalue(); buf.seek(0); buf.truncate(0)

    fname = f"store_kpi_{datetime.now(IST).strftime('%Y%m%d')}.csv"
    return StreamingResponse(gen(), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ── CRM Customer Report ───────────────────────────────────────────────────────
CRM_COLUMNS: List[Tuple[str, str]] = [
    ("mobile", "Mobile"), ("name", "Name"), ("city", "City"), ("state", "State"),
    ("tier", "Tier"), ("card_validity", "Card Validity"),
    ("points_balance", "Point Balance"), ("lifetime_points_redeemed", "Redeem Points"),
    ("lifetime_spend", "Total Billing"), ("visit_count", "Total Visits"),
    ("days_since_last_visit", "Days Since Last Visit"),
    ("last_visit_at", "Last Visit Date"), ("first_purchase_at", "First Visit Date"),
    ("registered_account", "Registered Account"), ("added_on", "Added On"),
    ("birthday", "DOB"), ("anniversary", "DOA"),
]

CRM_SORT_FIELDS = {
    "mobile", "name", "city", "state", "tier", "points_balance",
    "lifetime_points_redeemed", "lifetime_spend", "visit_count",
    "days_since_last_visit", "last_visit_at", "first_purchase_at", "added_on",
}


def _crm_filter(q, city, state, tier, card_validity, recency,
                min_visits, max_visits, min_points, max_points, min_billing) -> Dict[str, Any]:
    flt: Dict[str, Any] = {}
    if q:
        flt["$or"] = [{"mobile": {"$regex": _esc(q)}},
                      {"name": {"$regex": _esc(q), "$options": "i"}}]
    if city:
        flt["city"] = city
    if state:
        flt["state"] = state
    if tier:
        flt["tier"] = tier
    if card_validity:
        flt["card_validity"] = card_validity
    if recency == "active":
        flt["days_since_last_visit"] = {"$lte": 182}
    elif recency == "dormant":
        flt["days_since_last_visit"] = {"$gt": 182, "$lte": 365}
    elif recency == "lapsed":
        flt["days_since_last_visit"] = {"$gt": 365}
    v_range: Dict[str, Any] = {}
    if min_visits is not None:
        v_range["$gte"] = min_visits
    if max_visits is not None:
        v_range["$lte"] = max_visits
    if v_range:
        flt["visit_count"] = v_range
    p_range: Dict[str, Any] = {}
    if min_points is not None:
        p_range["$gte"] = min_points
    if max_points is not None:
        p_range["$lte"] = max_points
    if p_range:
        flt["points_balance"] = p_range
    if min_billing is not None:
        flt["lifetime_spend"] = {"$gte": min_billing}
    return flt


_CRM_PROJECT = {"_id": 0, "password_hash": 0}
# Minimal projection (only report columns) — keeps streamed export rows small.
_CRM_FIELDS = {"_id": 0, **{k: 1 for k, _ in CRM_COLUMNS}}


@router.get("/crm-customers")
async def crm_customers(
    q: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    tier: Optional[str] = None,
    card_validity: Optional[str] = None,
    recency: Optional[str] = None,
    min_visits: Optional[int] = None,
    max_visits: Optional[int] = None,
    min_points: Optional[int] = None,
    max_points: Optional[int] = None,
    min_billing: Optional[float] = None,
    sort_by: str = "lifetime_spend",
    sort_dir: str = "desc",
    skip: int = 0,
    limit: int = Query(50, le=200),
    user=Depends(get_current_user),
):
    flt = _crm_filter(q, city, state, tier, card_validity, recency,
                      min_visits, max_visits, min_points, max_points, min_billing)
    sf = sort_by if sort_by in CRM_SORT_FIELDS else "lifetime_spend"
    direction = pymongo.ASCENDING if sort_dir == "asc" else pymongo.DESCENDING

    total = await customers_col.count_documents(flt)
    cur = (customers_col.find(flt, _CRM_PROJECT)
           .sort(sf, direction).skip(max(0, skip)).limit(limit))
    rows = await cur.to_list(limit)
    return {"total": total, "rows": rows, "skip": skip, "limit": limit,
            "has_more": skip + len(rows) < total,
            "columns": [{"key": k, "label": l} for k, l in CRM_COLUMNS]}


@export_router.get("/crm-customers/export")
async def crm_customers_export(
    q: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    tier: Optional[str] = None,
    card_validity: Optional[str] = None,
    recency: Optional[str] = None,
    min_visits: Optional[int] = None,
    max_visits: Optional[int] = None,
    min_points: Optional[int] = None,
    max_points: Optional[int] = None,
    min_billing: Optional[float] = None,
    sort_by: str = "lifetime_spend",
    sort_dir: str = "desc",
    user=Depends(get_current_user),
):
    flt = _crm_filter(q, city, state, tier, card_validity, recency,
                      min_visits, max_visits, min_points, max_points, min_billing)
    sf = sort_by if sort_by in CRM_SORT_FIELDS else "lifetime_spend"
    direction = pymongo.ASCENDING if sort_dir == "asc" else pymongo.DESCENDING

    async def gen():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([l for _, l in CRM_COLUMNS])
        yield buf.getvalue(); buf.seek(0); buf.truncate(0)
        sent = 0
        with pymongo.timeout(900):
            cur = customers_col.find(flt, _CRM_FIELDS).sort(sf, direction).allow_disk_use(True)
            async for c in cur:
                w.writerow([c.get(k, "") for k, _ in CRM_COLUMNS])
                yield buf.getvalue(); buf.seek(0); buf.truncate(0)
                sent += 1
                if sent >= EXPORT_MAX_ROWS:
                    break

    fname = f"crm_customers_{datetime.now(IST).strftime('%Y%m%d')}.csv"
    return StreamingResponse(gen(), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ── KPI Trend (Weekly / Monthly / Daily) ──────────────────────────────────────
@router.get("/trend")
async def kpi_trend(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    granularity: str = "month",
    zone: Optional[str] = None,
    city: Optional[str] = None,
    store_class: Optional[str] = None,
    store_id: Optional[str] = None,
    user=Depends(get_current_user),
):
    match = _store_match(start_date, end_date, zone, city, store_class, store_id)

    if granularity == "day":
        bucket = {"$substrCP": ["$bill_date", 0, 10]}
    elif granularity == "week":
        bucket = {"$dateToString": {
            "format": "%G-W%V",
            "date": {"$dateFromString": {"dateString": "$bill_date", "onError": None, "onNull": None}},
        }}
    else:  # month
        bucket = {"$substrCP": ["$bill_date", 0, 7]}

    pipe = [
        {"$match": match},
        {"$group": {
            "_id": bucket,
            "sales": {"$sum": "$net_amount"},
            "discount": {"$sum": "$discount_amount"},
            "bills": {"$sum": {"$cond": [_NE_RETURN, 1, 0]}},
            "returns": {"$sum": {"$cond": [_IS_RETURN, 1, 0]}},
            "new": {"$sum": {"$cond": [{"$and": [_NE_RETURN, _IS_NEW]}, 1, 0]}},
            "repeat": {"$sum": {"$cond": [{"$and": [_NE_RETURN, _IS_EXISTING]}, 1, 0]}},
            "customers": {"$addToSet": {"$cond": [_HAS_MOBILE, "$customer_mobile", "$$REMOVE"]}},
        }},
        {"$sort": {"_id": 1}},
        {"$limit": 500},
    ]
    raw = await transactions_col.aggregate(pipe, allowDiskUse=True).to_list(500)
    points = [{
        "period": g.get("_id") or "—",
        "sales": round(g.get("sales", 0) or 0, 2),
        "discount": round(g.get("discount", 0) or 0, 2),
        "bills": int(g.get("bills", 0) or 0),
        "returns": int(g.get("returns", 0) or 0),
        "new": int(g.get("new", 0) or 0),
        "repeat": int(g.get("repeat", 0) or 0),
        "customers": len(g.get("customers", []) or []),
    } for g in raw if g.get("_id")]
    return {"granularity": granularity, "points": points}


# ── CRM summary (charts: tier / recency / top cities / liability) ─────────────
@router.get("/crm-summary")
async def crm_summary(
    q: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    tier: Optional[str] = None,
    card_validity: Optional[str] = None,
    recency: Optional[str] = None,
    min_visits: Optional[int] = None,
    max_visits: Optional[int] = None,
    min_points: Optional[int] = None,
    max_points: Optional[int] = None,
    min_billing: Optional[float] = None,
    user=Depends(get_current_user),
):
    flt = _crm_filter(q, city, state, tier, card_validity, recency,
                      min_visits, max_visits, min_points, max_points, min_billing)
    pipe = [
        {"$match": flt},
        {"$facet": {
            "by_tier": [
                {"$group": {"_id": {"$ifNull": ["$tier", "unknown"]}, "count": {"$sum": 1},
                            "points": {"$sum": "$points_balance"}, "spend": {"$sum": "$lifetime_spend"}}},
                {"$sort": {"count": -1}},
            ],
            "by_recency": [
                {"$bucket": {
                    "groupBy": {"$ifNull": ["$days_since_last_visit", 10 ** 9]},
                    "boundaries": [0, 183, 366, 10 ** 9],
                    "default": "unknown",
                    "output": {"count": {"$sum": 1}},
                }},
            ],
            "top_cities": [
                {"$group": {"_id": {"$ifNull": ["$city", "Unknown"]}, "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}, {"$limit": 10},
            ],
            "totals": [
                {"$group": {"_id": None, "customers": {"$sum": 1},
                            "points": {"$sum": "$points_balance"},
                            "redeemed": {"$sum": "$lifetime_points_redeemed"},
                            "spend": {"$sum": "$lifetime_spend"},
                            "visits": {"$sum": "$visit_count"}}},
            ],
        }},
    ]
    res = (await customers_col.aggregate(pipe, allowDiskUse=True).to_list(1)) or [{}]
    res = res[0] if res else {}
    rec_labels = {0: "Active (0-6M)", 183: "Dormant (6-12M)", 366: "Lapsed (12M+)", "unknown": "Unknown"}
    totals = (res.get("totals") or [{}])
    totals = totals[0] if totals else {}
    return {
        "by_tier": [{"tier": (g["_id"] or "unknown"), "count": g["count"],
                     "points": round(g.get("points", 0) or 0, 2), "spend": round(g.get("spend", 0) or 0, 2)}
                    for g in (res.get("by_tier") or [])],
        "by_recency": [{"bucket": rec_labels.get(g["_id"], str(g["_id"])), "count": g["count"]}
                       for g in (res.get("by_recency") or [])],
        "top_cities": [{"city": g["_id"], "count": g["count"]} for g in (res.get("top_cities") or [])],
        "totals": {
            "customers": int(totals.get("customers", 0) or 0),
            "points": round(totals.get("points", 0) or 0, 2),
            "redeemed": round(totals.get("redeemed", 0) or 0, 2),
            "spend": round(totals.get("spend", 0) or 0, 2),
            "visits": int(totals.get("visits", 0) or 0),
        },
    }


# ── Filter options for the report dropdowns ───────────────────────────────────
@router.get("/filter-options")
async def filter_options(user=Depends(get_current_user)):
    async def safe_distinct(col, field):
        try:
            with pymongo.timeout(15):
                vals = await col.distinct(field)
            return sorted([v for v in vals if v not in (None, "")])
        except Exception:
            return []

    return {
        "zones": await safe_distinct(transactions_col, "zone"),
        "cities": await safe_distinct(transactions_col, "city"),
        "store_classes": await safe_distinct(transactions_col, "store_class"),
        "tiers": await safe_distinct(customers_col, "tier"),
        "card_validities": await safe_distinct(customers_col, "card_validity"),
        "states": await safe_distinct(customers_col, "state"),
    }
