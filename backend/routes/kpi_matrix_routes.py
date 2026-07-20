"""Two client-requested reports + the CRM visit-account denormalisation.

* Store-wise KPI  — the FULL per-outlet matrix from `Store_wise__KPI.xlsx`:
  overall sales/discount, fresh & return bills/value/discount, and the
  New / Repeat / Mapped / Unmapped customer × Fresh / Return matrix
  (transactions, order value, ATV) plus Overall / New / Existing customer counts.
* Weekly KPI      — the business KPI summary from `Weekly_KPI.xlsx` bucketed by
  day / week / month so trends & graphs can be built on it.
* CRM visit accounts — backfills each customer's First / Last Visit Account
  (store CODE · NAME) and Total Purchase (bill amount incl. tax = Σ net_amount)
  so the CRM Customer Report can show/sort/filter/graph them.

Reuses the shared aggregation helpers from reports_kpi_routes (date/store match,
return/new/existing/mapped conditions).  All money = net_amount (post-discount,
incl. GST), matching the rest of the KPI reports.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pymongo
from pymongo import UpdateOne
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth import get_current_user
from database import customers_col, transactions_col, stores_col
from routes._db_timeout import db_deadline
from routes.reports_kpi_routes import (
    _store_match, _date_match, _fill_store_identity, _shift_year, _esc,
    _NE_RETURN, _IS_RETURN, _IS_NEW, _IS_EXISTING, _HAS_MOBILE, IST,
)

logger = logging.getLogger("kazo-fundle.kpi_matrix")

router = APIRouter(prefix="/kpi-reports", tags=["kpi-reports"],
                   dependencies=[Depends(db_deadline)])
export_router = APIRouter(prefix="/kpi-reports", tags=["kpi-reports"])


def _atv(value: float, txn: float) -> float:
    return round(value / txn, 2) if txn else 0.0


def _r2(v: Any) -> float:
    return round(float(v or 0), 2)


# ══════════════════════════════════════════════════════════════════════════════
# STORE-WISE KPI  (full matrix)
# ══════════════════════════════════════════════════════════════════════════════
def _and(*xs):
    return {"$and": list(xs)}


def _not_mapped():
    return {"$not": [_HAS_MOBILE]}


def _sumif(cond, expr):
    return {"$sum": {"$cond": [cond, expr, 0]}}


_FRESH, _RET = _NE_RETURN, _IS_RETURN


def _store_matrix_group() -> Dict[str, Any]:
    return {"$group": {
        "_id": "$store_id",
        "store_code": {"$first": "$store_code"},
        "store_name": {"$first": "$store_name"},
        "store_class": {"$first": "$store_class"},
        "zone": {"$first": "$zone"},
        "city": {"$first": "$city"},
        "overall_sales": {"$sum": "$net_amount"},
        "total_discount": {"$sum": "$discount_amount"},
        "fresh_bills": _sumif(_FRESH, 1),
        "fresh_value": _sumif(_FRESH, "$net_amount"),
        "fresh_discount": _sumif(_FRESH, "$discount_amount"),
        "return_bills": _sumif(_RET, 1),
        "return_value": _sumif(_RET, "$net_amount"),
        "return_discount": _sumif(_RET, "$discount_amount"),
        "new_fresh_txn": _sumif(_and(_FRESH, _IS_NEW), 1),
        "new_return_txn": _sumif(_and(_RET, _IS_NEW), 1),
        "new_fresh_value": _sumif(_and(_FRESH, _IS_NEW), "$net_amount"),
        "new_return_value": _sumif(_and(_RET, _IS_NEW), "$net_amount"),
        "repeat_fresh_txn": _sumif(_and(_FRESH, _IS_EXISTING), 1),
        "repeat_return_txn": _sumif(_and(_RET, _IS_EXISTING), 1),
        "repeat_fresh_value": _sumif(_and(_FRESH, _IS_EXISTING), "$net_amount"),
        "repeat_return_value": _sumif(_and(_RET, _IS_EXISTING), "$net_amount"),
        "mapped_fresh_txn": _sumif(_and(_FRESH, _HAS_MOBILE), 1),
        "mapped_return_txn": _sumif(_and(_RET, _HAS_MOBILE), 1),
        "mapped_fresh_value": _sumif(_and(_FRESH, _HAS_MOBILE), "$net_amount"),
        "mapped_return_value": _sumif(_and(_RET, _HAS_MOBILE), "$net_amount"),
        "unmapped_fresh_txn": _sumif(_and(_FRESH, _not_mapped()), 1),
        "unmapped_return_txn": _sumif(_and(_RET, _not_mapped()), 1),
        "unmapped_fresh_value": _sumif(_and(_FRESH, _not_mapped()), "$net_amount"),
        "unmapped_return_value": _sumif(_and(_RET, _not_mapped()), "$net_amount"),
        "customers": {"$addToSet": {"$cond": [_and(_FRESH, _HAS_MOBILE), "$customer_mobile", "$$REMOVE"]}},
        "new_customers": {"$addToSet": {"$cond": [_and(_FRESH, _IS_NEW, _HAS_MOBILE), "$customer_mobile", "$$REMOVE"]}},
        "existing_customers": {"$addToSet": {"$cond": [_and(_FRESH, _IS_EXISTING, _HAS_MOBILE), "$customer_mobile", "$$REMOVE"]}},
    }}


def _finalize_matrix_row(g: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "store_id": g.get("_id") or "",
        "store_code": g.get("store_code") or "—",
        "store_name": g.get("store_name") or "—",
        "store_class": g.get("store_class") or "—",
        "zone": g.get("zone") or "—",
        "city": g.get("city") or "—",
        "overall_sales": _r2(g.get("overall_sales")),
        "total_discount": _r2(g.get("total_discount")),
        "fresh_bills": int(g.get("fresh_bills", 0) or 0),
        "fresh_value": _r2(g.get("fresh_value")),
        "fresh_discount": _r2(g.get("fresh_discount")),
        "return_bills": int(g.get("return_bills", 0) or 0),
        "return_value": _r2(g.get("return_value")),
        "return_discount": _r2(g.get("return_discount")),
        "new_fresh_txn": int(g.get("new_fresh_txn", 0) or 0),
        "new_return_txn": int(g.get("new_return_txn", 0) or 0),
        "new_fresh_value": _r2(g.get("new_fresh_value")),
        "new_return_value": _r2(g.get("new_return_value")),
        "new_fresh_atv": _atv(g.get("new_fresh_value", 0) or 0, g.get("new_fresh_txn", 0) or 0),
        "new_return_atv": _atv(g.get("new_return_value", 0) or 0, g.get("new_return_txn", 0) or 0),
        "repeat_fresh_txn": int(g.get("repeat_fresh_txn", 0) or 0),
        "repeat_return_txn": int(g.get("repeat_return_txn", 0) or 0),
        "repeat_fresh_value": _r2(g.get("repeat_fresh_value")),
        "repeat_return_value": _r2(g.get("repeat_return_value")),
        "repeat_fresh_atv": _atv(g.get("repeat_fresh_value", 0) or 0, g.get("repeat_fresh_txn", 0) or 0),
        "repeat_return_atv": _atv(g.get("repeat_return_value", 0) or 0, g.get("repeat_return_txn", 0) or 0),
        "mapped_fresh_txn": int(g.get("mapped_fresh_txn", 0) or 0),
        "mapped_return_txn": int(g.get("mapped_return_txn", 0) or 0),
        "mapped_fresh_value": _r2(g.get("mapped_fresh_value")),
        "mapped_return_value": _r2(g.get("mapped_return_value")),
        "mapped_fresh_atv": _atv(g.get("mapped_fresh_value", 0) or 0, g.get("mapped_fresh_txn", 0) or 0),
        "mapped_return_atv": _atv(g.get("mapped_return_value", 0) or 0, g.get("mapped_return_txn", 0) or 0),
        "unmapped_fresh_txn": int(g.get("unmapped_fresh_txn", 0) or 0),
        "unmapped_return_txn": int(g.get("unmapped_return_txn", 0) or 0),
        "unmapped_fresh_value": _r2(g.get("unmapped_fresh_value")),
        "unmapped_return_value": _r2(g.get("unmapped_return_value")),
        "unmapped_fresh_atv": _atv(g.get("unmapped_fresh_value", 0) or 0, g.get("unmapped_fresh_txn", 0) or 0),
        "unmapped_return_atv": _atv(g.get("unmapped_return_value", 0) or 0, g.get("unmapped_return_txn", 0) or 0),
        "overall_customers": len(g.get("customers", []) or []),
        "new_customer_count": len(g.get("new_customers", []) or []),
        "existing_customers": len(g.get("existing_customers", []) or []),
    }


async def _run_store_matrix(match: Dict[str, Any]) -> List[Dict[str, Any]]:
    pipe = [{"$match": match}, _store_matrix_group()]
    raw = await transactions_col.aggregate(pipe, allowDiskUse=True).to_list(3000)
    rows = [_finalize_matrix_row(g) for g in raw]
    await _fill_store_identity(rows)
    for r in rows:
        code = r.get("store_code")
        r["email"] = f"{code}@KAZO.com" if code and code != "—" else "—"
    return rows


STORE_MATRIX_COLUMNS: List[Tuple[str, str]] = [
    ("store_name", "Outlet"), ("email", "Email"), ("store_code", "Store Code"),
    ("store_class", "Class"), ("zone", "Zone"), ("city", "City"),
    ("overall_sales", "Overall Sales"), ("total_discount", "Total Discount"),
    ("fresh_bills", "Fresh Bills"), ("fresh_value", "Fresh Bill Value"), ("fresh_discount", "Fresh Bill Discount"),
    ("return_bills", "Return Bills"), ("return_value", "Return Bills Value"), ("return_discount", "Return Bills Discount"),
    ("new_fresh_txn", "New Customer (Fresh Transaction)"), ("new_return_txn", "New Customer (Return Transaction)"),
    ("new_fresh_value", "New Customer Order Value (Fresh Bills)"), ("new_return_value", "New Customer Order Value (Return Bills)"),
    ("repeat_fresh_txn", "Repeat Customer (Fresh Transaction)"), ("repeat_return_txn", "Repeat Customer Transactions (Return)"),
    ("repeat_fresh_value", "Repeat Customer Order Value (Fresh)"), ("repeat_return_value", "Repeat Customer Order Value (Return)"),
    ("new_fresh_atv", "New Customer ATV (Fresh)"), ("new_return_atv", "New Customer ATV (Return)"),
    ("repeat_fresh_atv", "Repeat Customer ATV (Fresh)"), ("repeat_return_atv", "Repeat Customer ATV (Return)"),
    ("mapped_fresh_txn", "Mapped Customer Transaction (Fresh)"), ("mapped_return_txn", "Mapped Customer Transactions (Return)"),
    ("mapped_fresh_value", "Mapped Customer Order Value (Fresh)"), ("mapped_return_value", "Mapped Customer Order Value (Return)"),
    ("mapped_fresh_atv", "Mapped Customers ATV (Fresh)"), ("mapped_return_atv", "Mapped Customer ATV (Return)"),
    ("unmapped_fresh_txn", "Unmapped Customer Transaction (Fresh)"), ("unmapped_return_txn", "Unmapped Customer Transaction (Return)"),
    ("unmapped_fresh_value", "Unmapped Customer Order Value (Fresh)"), ("unmapped_return_value", "Unmapped Customer Order Value (Return)"),
    ("unmapped_fresh_atv", "Unmapped Customer ATV (Fresh)"), ("unmapped_return_atv", "Unmapped Customer ATV (Return)"),
    ("overall_customers", "Overall Customers"), ("new_customer_count", "New Customer Count"), ("existing_customers", "Existing Customers"),
]

STORE_MATRIX_SORT = {k for k, _ in STORE_MATRIX_COLUMNS}
_MATRIX_TOTAL_KEYS = [k for k, _ in STORE_MATRIX_COLUMNS
                      if k not in ("store_name", "email", "store_code", "store_class", "zone", "city")
                      and not k.endswith("_atv")]


@router.get("/store-wise-kpi")
async def store_wise_kpi(
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
    rows = await _run_store_matrix(match)
    sf = sort_by if sort_by in STORE_MATRIX_SORT else "overall_sales"
    rows.sort(key=lambda r: (r.get(sf) is None, r.get(sf)), reverse=(sort_dir != "asc"))
    totals = {k: 0 for k in _MATRIX_TOTAL_KEYS}
    for r in rows:
        for k in _MATRIX_TOTAL_KEYS:
            totals[k] += r.get(k, 0) or 0
    totals = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in totals.items()}
    return {"rows": rows, "totals": totals, "count": len(rows),
            "columns": [{"key": k, "label": l} for k, l in STORE_MATRIX_COLUMNS]}


@export_router.get("/store-wise-kpi/export")
async def store_wise_kpi_export(
    start_date: Optional[str] = None, end_date: Optional[str] = None,
    zone: Optional[str] = None, city: Optional[str] = None,
    store_class: Optional[str] = None, store_id: Optional[str] = None,
    sort_by: str = "overall_sales", sort_dir: str = "desc",
    user=Depends(get_current_user),
):
    match = _store_match(start_date, end_date, zone, city, store_class, store_id)
    with pymongo.timeout(180):
        rows = await _run_store_matrix(match)
    sf = sort_by if sort_by in STORE_MATRIX_SORT else "overall_sales"
    rows.sort(key=lambda r: (r.get(sf) is None, r.get(sf)), reverse=(sort_dir != "asc"))

    def gen():
        buf = io.StringIO(); w = csv.writer(buf)
        w.writerow([l for _, l in STORE_MATRIX_COLUMNS])
        yield buf.getvalue(); buf.seek(0); buf.truncate(0)
        for r in rows:
            w.writerow([r.get(k, "") for k, _ in STORE_MATRIX_COLUMNS])
            yield buf.getvalue(); buf.seek(0); buf.truncate(0)

    fname = f"store_wise_kpi_{datetime.now(IST).strftime('%Y%m%d')}.csv"
    return StreamingResponse(gen(), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ══════════════════════════════════════════════════════════════════════════════
# WEEKLY KPI  (business summary bucketed by day / week / month)
# ══════════════════════════════════════════════════════════════════════════════
def _bucket_expr(granularity: str):
    if granularity == "day":
        return {"$substrCP": ["$bill_date", 0, 10]}
    if granularity == "month":
        return {"$substrCP": ["$bill_date", 0, 7]}
    if granularity == "year":
        return {"$substrCP": ["$bill_date", 0, 4]}
    return {"$dateToString": {"format": "%G-W%V",
            "date": {"$dateFromString": {"dateString": "$bill_date", "onError": None, "onNull": None}}}}


async def _weekly_kpi(match: Dict[str, Any], granularity: str) -> List[Dict[str, Any]]:
    bucket = _bucket_expr(granularity)
    big = {"$gt": ["$net_amount", 10000]}
    main = [
        {"$match": match},
        {"$group": {
            "_id": bucket,
            "overall_sales": {"$sum": "$net_amount"},
            "total_discount": {"$sum": "$discount_amount"},
            "total_orders": _sumif(_FRESH, 1),
            "return_bills": _sumif(_RET, 1),
            "mapped_orders": _sumif(_and(_FRESH, _HAS_MOBILE), 1),
            "unmapped_orders": _sumif(_and(_FRESH, _not_mapped()), 1),
            "new_order": _sumif(_and(_FRESH, _IS_NEW), 1),
            "repeat_orders": _sumif(_and(_FRESH, _IS_EXISTING), 1),
            "fresh_value": _sumif(_FRESH, "$net_amount"),
            "mapped_sales": _sumif(_HAS_MOBILE, "$net_amount"),
            "unmapped_sales": _sumif(_not_mapped(), "$net_amount"),
            "new_value": _sumif(_and(_FRESH, _IS_NEW), "$net_amount"),
            "repeat_value": _sumif(_and(_FRESH, _IS_EXISTING), "$net_amount"),
            "mapped_value": _sumif(_and(_FRESH, _HAS_MOBILE), "$net_amount"),
            "big_value": _sumif(_and(_FRESH, big), "$net_amount"),
            "big_bills": _sumif(_and(_FRESH, big), 1),
            "stores": {"$addToSet": "$store_id"},
        }},
        {"$sort": {"_id": 1}}, {"$limit": 800},
    ]
    raw = await transactions_col.aggregate(main, allowDiskUse=True).to_list(800)

    # per-bucket distinct customer counts (memory-safe: group by mobile first)
    cmatch = dict(match); cmatch["is_return"] = {"$ne": True}
    cmatch["customer_mobile"] = {"$nin": [None, ""]}
    cust = [
        {"$match": cmatch},
        {"$group": {"_id": {"b": bucket, "m": "$customer_mobile"},
                    "isnew": {"$max": {"$cond": [_IS_NEW, 1, 0]}},
                    "isex": {"$max": {"$cond": [_IS_EXISTING, 1, 0]}}}},
        {"$group": {"_id": "$_id.b", "overall": {"$sum": 1},
                    "new": {"$sum": "$isnew"}, "existing": {"$sum": "$isex"}}},
    ]
    craw = await transactions_col.aggregate(cust, allowDiskUse=True).to_list(800)
    cmap = {c["_id"]: c for c in craw}

    out = []
    for g in raw:
        b = g.get("_id")
        if not b:
            continue
        c = cmap.get(b, {})
        overall_cust = int(c.get("overall", 0) or 0)
        new_cust = int(c.get("new", 0) or 0)
        rep_cust = int(c.get("existing", 0) or 0)
        total_orders = int(g.get("total_orders", 0) or 0)
        mapped_orders = int(g.get("mapped_orders", 0) or 0)
        repeat_orders = int(g.get("repeat_orders", 0) or 0)
        unmapped_orders = int(g.get("unmapped_orders", 0) or 0)
        new_order = int(g.get("new_order", 0) or 0)
        out.append({
            "period": b,
            "number_of_stores": len([s for s in (g.get("stores") or []) if s]),
            "total_orders": total_orders,
            "mapped_orders": mapped_orders,
            "new_order": new_order,
            "repeat_orders": repeat_orders,
            "unmapped_orders": unmapped_orders,
            "overall_customers": overall_cust,
            "new_customer_count": new_cust,
            "repeat_customers": rep_cust,
            "new_vs_repeat_ratio": round(new_cust / rep_cust, 4) if rep_cust else 0.0,
            "overall_sales": _r2(g.get("overall_sales")),
            "total_discount": _r2(g.get("total_discount")),
            "mapped_sales": _r2(g.get("mapped_sales")),
            "unmapped_sales": _r2(g.get("unmapped_sales")),
            "new_customer_value": _r2(g.get("new_value")),
            "repeat_customer_sales": _r2(g.get("repeat_value")),
            "data_collection": round(mapped_orders / total_orders, 4) if total_orders else 0.0,
            "business_atv": _atv(g.get("fresh_value", 0) or 0, total_orders),
            "business_atv_10k": _atv(g.get("big_value", 0) or 0, g.get("big_bills", 0) or 0),
            "mapped_customer_atv": _atv(g.get("mapped_value", 0) or 0, mapped_orders),
            "new_customer_atv": _atv(g.get("new_value", 0) or 0, new_order),
            "repeat_customer_atv": _atv(g.get("repeat_value", 0) or 0, repeat_orders),
            "mapped_customer_frequency": round(mapped_orders / overall_cust, 4) if overall_cust else 0.0,
            "repeat_customer_frequency": round(rep_cust / repeat_orders, 4) if repeat_orders else 0.0,
            "pct_unmapped_order": round(unmapped_orders / total_orders, 4) if total_orders else 0.0,
            "pct_repeat_orders": round(repeat_orders / total_orders, 4) if total_orders else 0.0,
        })
    return out


WEEKLY_COLUMNS: List[Tuple[str, str]] = [
    ("period", "Period"), ("number_of_stores", "Stores"),
    ("total_orders", "Total Orders"), ("mapped_orders", "Mapped Orders"),
    ("new_order", "New Orders"), ("repeat_orders", "Repeat Orders"), ("unmapped_orders", "Unmapped Orders"),
    ("overall_customers", "Overall Customers"), ("new_customer_count", "New Customers"), ("repeat_customers", "Repeat Customers"),
    ("new_vs_repeat_ratio", "New vs Repeat"), ("overall_sales", "Overall Sales"), ("total_discount", "Total Discount"),
    ("mapped_sales", "Mapped Sales"), ("unmapped_sales", "Unmapped Sales"),
    ("new_customer_value", "New Cust Order Value (Fresh)"), ("repeat_customer_sales", "Repeat Customer Sales"),
    ("data_collection", "Data Collection"), ("business_atv", "Business ATV"), ("business_atv_10k", "Business ATV (>10k)"),
    ("mapped_customer_atv", "Mapped Cust ATV"), ("new_customer_atv", "New Cust ATV"), ("repeat_customer_atv", "Repeat Cust ATV"),
    ("mapped_customer_frequency", "Mapped Cust Frequency"), ("repeat_customer_frequency", "Repeat Cust Frequency"),
    ("pct_unmapped_order", "% Unmapped Orders"), ("pct_repeat_orders", "% Repeat Orders"),
]
WEEKLY_SORT = {k for k, _ in WEEKLY_COLUMNS}


@router.get("/weekly-kpi")
async def weekly_kpi(
    start_date: Optional[str] = None, end_date: Optional[str] = None,
    granularity: str = "week",
    zone: Optional[str] = None, city: Optional[str] = None,
    store_class: Optional[str] = None, store_id: Optional[str] = None,
    sort_by: str = "period", sort_dir: str = "asc",
    user=Depends(get_current_user),
):
    if granularity not in ("day", "week", "month", "year"):
        granularity = "week"
    match = _store_match(start_date, end_date, zone, city, store_class, store_id)
    rows = await _weekly_kpi(match, granularity)
    sf = sort_by if sort_by in WEEKLY_SORT else "period"
    rows.sort(key=lambda r: (r.get(sf) is None, r.get(sf)), reverse=(sort_dir == "desc"))
    return {"rows": rows, "count": len(rows), "granularity": granularity,
            "columns": [{"key": k, "label": l} for k, l in WEEKLY_COLUMNS]}


@export_router.get("/weekly-kpi/export")
async def weekly_kpi_export(
    start_date: Optional[str] = None, end_date: Optional[str] = None,
    granularity: str = "week",
    zone: Optional[str] = None, city: Optional[str] = None,
    store_class: Optional[str] = None, store_id: Optional[str] = None,
    sort_by: str = "period", sort_dir: str = "asc",
    user=Depends(get_current_user),
):
    if granularity not in ("day", "week", "month", "year"):
        granularity = "week"
    match = _store_match(start_date, end_date, zone, city, store_class, store_id)
    with pymongo.timeout(180):
        rows = await _weekly_kpi(match, granularity)
    sf = sort_by if sort_by in WEEKLY_SORT else "period"
    rows.sort(key=lambda r: (r.get(sf) is None, r.get(sf)), reverse=(sort_dir == "desc"))

    def gen():
        buf = io.StringIO(); w = csv.writer(buf)
        w.writerow([l for _, l in WEEKLY_COLUMNS])
        yield buf.getvalue(); buf.seek(0); buf.truncate(0)
        for r in rows:
            w.writerow([r.get(k, "") for k, _ in WEEKLY_COLUMNS])
            yield buf.getvalue(); buf.seek(0); buf.truncate(0)

    fname = f"weekly_kpi_{granularity}_{datetime.now(IST).strftime('%Y%m%d')}.csv"
    return StreamingResponse(gen(), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ══════════════════════════════════════════════════════════════════════════════
# CRM visit-account + total-purchase backfill (denormalise onto customers)
# ══════════════════════════════════════════════════════════════════════════════
def _acct(code: Optional[str], name: Optional[str]) -> str:
    code = (code or "").strip()
    name = (name or "").strip()
    if code and name:
        return f"{code} · {name}"
    return code or name or "—"


async def _compute_visit_accounts(mobile_filter: Optional[str]) -> Tuple[int, int]:
    """Aggregate first/last visit store + Σ net_amount per customer_mobile and
    denormalise first_visit_account / last_visit_account / total_purchase onto customers.
    Returns (customers_updated, mobiles_scanned)."""
    match: Dict[str, Any] = {"customer_mobile": {"$nin": [None, ""]}}
    if mobile_filter:
        match["customer_mobile"] = mobile_filter
    pipe = [
        {"$match": match},
        {"$sort": {"bill_date": 1}},
        {"$group": {
            "_id": "$customer_mobile",
            "first_store_id": {"$first": "$store_id"},
            "first_store_name": {"$first": "$store_name"},
            "first_store_code": {"$first": "$store_code"},
            "last_store_id": {"$last": "$store_id"},
            "last_store_name": {"$last": "$store_name"},
            "last_store_code": {"$last": "$store_code"},
            "total_purchase": {"$sum": "$net_amount"},
        }},
    ]
    groups = await transactions_col.aggregate(pipe, allowDiskUse=True).to_list(None)
    if not groups:
        return 0, 0
    # resolve store code/name from the stores master where the bill lacked them
    store_ids = {g.get(k) for g in groups for k in ("first_store_id", "last_store_id") if g.get(k)}
    smap: Dict[str, Dict[str, Any]] = {}
    if store_ids:
        async for s in stores_col.find({"id": {"$in": list(store_ids)}},
                                       {"_id": 0, "id": 1, "name": 1, "code": 1}):
            smap[s["id"]] = s

    def resolve(code, name, sid):
        s = smap.get(sid) or {}
        return (code or s.get("code"), name or s.get("name"))

    ops = []
    for g in groups:
        fc, fn = resolve(g.get("first_store_code"), g.get("first_store_name"), g.get("first_store_id"))
        lc, ln = resolve(g.get("last_store_code"), g.get("last_store_name"), g.get("last_store_id"))
        ops.append(UpdateOne(
            {"mobile": g["_id"]},
            {"$set": {
                "first_visit_account": _acct(fc, fn),
                "last_visit_account": _acct(lc, ln),
                "total_purchase": round(float(g.get("total_purchase", 0) or 0), 2),
            }}))
    updated = 0
    for i in range(0, len(ops), 2000):
        with pymongo.timeout(120):
            res = await customers_col.bulk_write(ops[i:i + 2000], ordered=False)
            updated += (res.modified_count or 0)
    return updated, len(groups)


class VisitBackfillIn(BaseModel):
    mobile: str = ""


@router.get("/crm-visit-accounts/audit")
async def crm_visit_accounts_audit(user=Depends(get_current_user)):
    """How many customers still lack the denormalised visit-account fields."""
    total = await customers_col.count_documents({})
    missing = await customers_col.count_documents(
        {"$or": [{"first_visit_account": {"$exists": False}}, {"first_visit_account": None},
                 {"total_purchase": {"$exists": False}}, {"total_purchase": None}]})
    return {"total_customers": total, "missing_visit_accounts": missing}


@router.post("/crm-visit-accounts/backfill")
async def crm_visit_accounts_backfill(body: VisitBackfillIn, user=Depends(get_current_user)):
    """Populate First/Last Visit Account (store code · name) + Total Purchase (Σ net_amount,
    incl. GST) on customers from their transactions. Optional `mobile` scopes to one customer."""
    updated, scanned = await _compute_visit_accounts((body.mobile or "").strip() or None)
    return {"ok": True, "customers_updated": updated, "mobiles_scanned": scanned,
            "message": f"Updated visit accounts + total purchase for {updated} customer(s)."}


# ══════════════════════════════════════════════════════════════════════════════
# New / Existing denormalisation on transactions (drives the Store-wise / Weekly
# KPI New-vs-Repeat matrix). Definition: a customer's EARLIEST purchase bill = "new",
# every later bill = "existing". Live posAddPoint stamps this per bill going forward;
# this backfill retro-fills it on all existing mapped transactions (and normalises any
# legacy CSV casing to the exact lowercase the KPI aggregations match).
# ══════════════════════════════════════════════════════════════════════════════
async def _compute_new_or_existing(mobile_filter: Optional[str]) -> Tuple[int, int, int]:
    """Set new_or_existing on every MAPPED transaction: default all to "existing", then flip
    each customer's earliest non-return bill to "new". Returns (new_count, existing_count,
    mobiles_scanned)."""
    match: Dict[str, Any] = {"customer_mobile": {"$nin": [None, ""]}}
    if mobile_filter:
        match["customer_mobile"] = mobile_filter

    # 1) default every mapped bill to "existing"
    with pymongo.timeout(1800):
        existing_res = await transactions_col.update_many(
            match, {"$set": {"new_or_existing": "existing"}})

    # 2) find each customer's EARLIEST non-return bill id (collect first, then batch-update
    #    so we never mutate the collection while its aggregation cursor is open)
    pipe = [
        {"$match": {**match, "is_return": {"$ne": True}}},
        {"$sort": {"bill_date": 1}},
        {"$group": {"_id": "$customer_mobile", "first_id": {"$first": "$id"}}},
    ]
    first_ids: List[str] = []
    with pymongo.timeout(1800):
        async for g in transactions_col.aggregate(pipe, allowDiskUse=True):
            fid = g.get("first_id")
            if fid:
                first_ids.append(fid)

    new_count = 0
    for i in range(0, len(first_ids), 5000):
        with pymongo.timeout(300):
            res = await transactions_col.update_many(
                {"id": {"$in": first_ids[i:i + 5000]}}, {"$set": {"new_or_existing": "new"}})
            new_count += (res.modified_count or 0)

    existing_count = max((existing_res.modified_count or 0) - new_count, 0)
    return new_count, existing_count, len(first_ids)


class NewExistingBackfillIn(BaseModel):
    mobile: str = ""


@router.get("/new-or-existing/audit")
async def new_or_existing_audit(user=Depends(get_current_user)):
    """Breakdown of new_or_existing across mapped transactions (drives the KPI New/Repeat
    counts). `missing` are mapped bills with no usable value — these read as 0 New/Repeat."""
    pipe = [
        {"$match": {"customer_mobile": {"$nin": [None, ""]}}},
        {"$group": {"_id": {"$toLower": {"$ifNull": ["$new_or_existing", ""]}}, "count": {"$sum": 1}}},
    ]
    with pymongo.timeout(300):
        rows = await transactions_col.aggregate(pipe, allowDiskUse=True).to_list(50)
    by = {(r.get("_id") or ""): int(r.get("count") or 0) for r in rows}
    total_mapped = sum(by.values())
    new_cnt = by.get("new", 0)
    existing_cnt = by.get("existing", 0)
    missing = total_mapped - new_cnt - existing_cnt
    return {"total_mapped": total_mapped, "new": new_cnt, "existing": existing_cnt,
            "missing": missing, "breakdown": by}


@router.post("/new-or-existing/backfill")
async def new_or_existing_backfill(body: NewExistingBackfillIn, user=Depends(get_current_user)):
    """Retro-fill new_or_existing on all mapped transactions (earliest bill per customer =
    "new", rest = "existing"). Optional `mobile` scopes to one customer. Fixes the Store-wise
    / Weekly KPI New-vs-Repeat metrics reading zero for live bills / mismatched legacy casing."""
    new_c, exist_c, scanned = await _compute_new_or_existing((body.mobile or "").strip() or None)
    return {"ok": True, "new": new_c, "existing": exist_c, "mobiles_scanned": scanned,
            "message": f"Stamped {new_c} New + {exist_c} Existing bill(s) across {scanned} customer(s)."}
