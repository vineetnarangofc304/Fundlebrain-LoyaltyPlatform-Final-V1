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

All money is the customer's TOTAL PAID (post-discount, incl. GST — the canonical
`amount_paid` / Live-Monitor "Total Paid"). Two routers: the main one runs
under db_deadline (45s); exports get their own deadline-free streaming router.
"""
from __future__ import annotations

import csv
import io
import json
import asyncio
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pymongo
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse

from auth import get_current_user
from database import customers_col, transactions_col
from routes._db_timeout import db_deadline
from routes._dash_cache import cache_get, cache_get_stale, cache_set
from routes._money import PAID_EXPR, NET_EXPR

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

    return {
        "$group": {
            "_id": "$store_id",
            "store_code": {"$first": "$store_code"},
            "store_name": {"$first": "$store_name"},
            "store_class": {"$first": "$store_class"},
            "zone": {"$first": "$zone"},
            "city": {"$first": "$city"},
            "overall_sales": {"$sum": PAID_EXPR},
            "total_discount": {"$sum": "$discount_amount"},
            "net_before_tax": {"$sum": NET_EXPR},
            "total_tax": {"$sum": "$tax_amount"},
            "fresh_bills": fresh_sum(1),
            "fresh_value": fresh_sum(PAID_EXPR),
            "return_bills": {"$sum": {"$cond": [_IS_RETURN, 1, 0]}},
            "return_value": {"$sum": {"$cond": [_IS_RETURN, PAID_EXPR, 0]}},
            "new_txn": {"$sum": {"$cond": [{"$and": [_NE_RETURN, _IS_NEW]}, 1, 0]}},
            "new_value": {"$sum": {"$cond": [{"$and": [_NE_RETURN, _IS_NEW]}, PAID_EXPR, 0]}},
            "repeat_txn": {"$sum": {"$cond": [{"$and": [_NE_RETURN, _IS_EXISTING, _HAS_MOBILE]}, 1, 0]}},
            "repeat_value": {"$sum": {"$cond": [{"$and": [_NE_RETURN, _IS_EXISTING, _HAS_MOBILE]}, PAID_EXPR, 0]}},
            "mapped_txn": {"$sum": {"$cond": [{"$and": [_NE_RETURN, _HAS_MOBILE]}, 1, 0]}},
            "mapped_value": {"$sum": {"$cond": [{"$and": [_NE_RETURN, _HAS_MOBILE]}, PAID_EXPR, 0]}},
            "unmapped_txn": {"$sum": {"$cond": [{"$and": [_NE_RETURN, {"$not": [_HAS_MOBILE]}]}, 1, 0]}},
            "unmapped_value": {"$sum": {"$cond": [{"$and": [_NE_RETURN, {"$not": [_HAS_MOBILE]}]}, PAID_EXPR, 0]}},
        }
    }


def _finalize_store_row(g: Dict[str, Any], cust: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    def atv(value, txn):
        return round(value / txn, 2) if txn else 0.0

    # ── Transaction reconciliation (exact identities, robust to any untagged bill) ──
    # Every MAPPED fresh bill is a New or a Repeat customer transaction; therefore
    #   New Txns + Repeat Txns == Mapped Txns   and   Mapped Txns + Unmapped Txns == Fresh Bills.
    # We derive New = Mapped − Repeat so a bill whose new_or_existing tag was never
    # stamped still reconciles (it counts as New rather than silently disappearing).
    fresh_bills = int(g.get("fresh_bills", 0) or 0)
    mapped_txn = int(g.get("mapped_txn", 0) or 0)
    unmapped_txn = int(g.get("unmapped_txn", 0) or 0)
    repeat_txn = int(g.get("repeat_txn", 0) or 0)
    if repeat_txn > mapped_txn:
        repeat_txn = mapped_txn
    new_txn = mapped_txn - repeat_txn
    mapped_value = round(g.get("mapped_value", 0) or 0, 2)
    repeat_value = round(g.get("repeat_value", 0) or 0, 2)
    new_value = round(mapped_value - repeat_value, 2)

    # ── Sales reconciliation (KAZO doc Point 5): New Cust sale + Repeat Cust sale did
    # not tie to Total (Overall) Sales because Overall Sales ALSO includes the value of
    # UNMAPPED / walk-in fresh bills and RETURN bills. Surfacing Unmapped Value + Return
    # Value makes the identity hold exactly:
    #     Overall Sales == New Value + Repeat Value + Unmapped Value + Return Value
    # unmapped_value is derived as the residual so the four parts always sum to Overall.
    overall_sales = round(g.get("overall_sales", 0) or 0, 2)
    return_value = round(g.get("return_value", 0) or 0, 2)
    unmapped_value = round(overall_sales - return_value - new_value - repeat_value, 2)
    # Total Loyalty Sales — the sacrosanct identity the client checks (KAZO doc Point 5):
    #     Total Loyalty Sales == New Customer Value + Repeat Customer Value
    # and therefore   Overall Sales == Loyalty Sales + Walk-in (Unmapped) + Returns.
    loyalty_sales = round(new_value + repeat_value, 2)

    # ── Customer reconciliation (exact partition): New + Existing == Overall ──
    # Distinct mapped-customer counts come from a separate scalable pipeline (see
    # _store_customer_count_pipe) — NOT $addToSet (which blew the 16 MB group limit → 500 on
    # multi-year ranges). `new` = customers whose first-ever bill is New; Existing = Overall − New.
    cust = cust or {}
    overall_cust = int(cust.get("overall", 0) or 0)
    new_cust = int(cust.get("new", 0) or 0)
    if new_cust > overall_cust:
        new_cust = overall_cust
    existing_cust = overall_cust - new_cust
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
        "fresh_bills": fresh_bills,
        "fresh_value": round(g.get("fresh_value", 0) or 0, 2),
        "return_bills": int(g.get("return_bills", 0) or 0),
        "return_value": return_value,
        "new_txn": new_txn,
        "new_value": new_value,
        "new_atv": atv(new_value, new_txn),
        "repeat_txn": repeat_txn,
        "repeat_value": repeat_value,
        "repeat_atv": atv(repeat_value, repeat_txn),
        "loyalty_sales": loyalty_sales,
        "mapped_txn": mapped_txn,
        "unmapped_txn": unmapped_txn,
        "unmapped_value": unmapped_value,
        "overall_customers": overall_cust,
        "new_customer_count": new_cust,
        "existing_customers": existing_cust,
        "overall_atv": atv(g.get("fresh_value", 0) or 0, fresh_bills),
    }


def _store_customer_count_pipe(match: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Distinct mapped-customer counts per store WITHOUT $addToSet. Two-stage: dedupe by
    (store, mobile) — a bounded per-group flag — then count per store. Scales to years of data."""
    m = dict(match)
    m["is_return"] = {"$ne": True}
    m["customer_mobile"] = {"$nin": [None, ""]}
    return [
        {"$match": m},
        {"$group": {"_id": {"s": "$store_id", "m": "$customer_mobile"},
                    "is_new": {"$max": {"$cond": [_IS_NEW, 1, 0]}}}},
        {"$group": {"_id": "$_id.s", "overall": {"$sum": 1}, "new": {"$sum": "$is_new"}}},
    ]


async def _run_store_kpi(match: Dict[str, Any]) -> List[Dict[str, Any]]:
    sales_pipe = [{"$match": match}, _store_group_stage()]

    async def _sales():
        return await transactions_col.aggregate(
            sales_pipe, allowDiskUse=True, maxTimeMS=40000).to_list(3000)

    async def _counts():
        # Graceful degradation: a very wide range must still return SALES even if the distinct
        # customer count is too heavy — never let counts 500 the whole report (KAZO doc Point 1).
        try:
            rows = await transactions_col.aggregate(
                _store_customer_count_pipe(match), allowDiskUse=True, maxTimeMS=40000).to_list(3000)
            return {r["_id"]: r for r in rows}
        except Exception as e:
            logger.warning("store-kpi customer counts skipped (%s)", e)
            return {}

    sales_raw, cust_map = await asyncio.gather(_sales(), _counts())
    rows = [_finalize_store_row(g, cust_map.get(g.get("_id"))) for g in sales_raw]
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
    "unmapped_txn", "unmapped_value", "overall_customers", "new_customer_count",
    "existing_customers", "overall_atv", "new_atv", "repeat_atv", "loyalty_sales",
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
    ("loyalty_sales", "Total Loyalty Sales"),
    ("mapped_txn", "Mapped Txns"), ("unmapped_txn", "Unmapped Txns"), ("unmapped_value", "Unmapped Value"),
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
        "new_value", "repeat_value", "unmapped_value", "loyalty_sales",
        "overall_customers", "new_customer_count", "existing_customers")}
    for r in rows:
        for k in totals:
            totals[k] += r.get(k, 0) or 0
    for k in ("overall_sales", "total_discount", "net_before_tax", "total_tax",
              "fresh_value", "return_value", "new_value", "repeat_value", "unmapped_value",
              "loyalty_sales"):
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
    ("home_store", "Home Store"),
    ("tier", "Tier"), ("card_validity", "Card Validity"),
    ("points_balance", "Point Balance"), ("lifetime_points_redeemed", "Redeem Points"),
    ("lifetime_spend", "Total Billing"), ("total_purchase", "Total Purchase (incl. Tax)"),
    ("visit_count", "Total Visits"),
    ("days_since_last_visit", "Days Since Last Visit"),
    ("last_visit_at", "Last Visit Date"), ("first_purchase_at", "First Visit Date"),
    ("first_visit_account", "First Visit Account"), ("last_visit_account", "Last Visit Account"),
    ("registered_account", "Registered Account"), ("added_on", "Added On"),
    ("birthday", "DOB"), ("anniversary", "DOA"),
]

CRM_SORT_FIELDS = {
    "mobile", "name", "city", "state", "tier", "points_balance",
    "lifetime_points_redeemed", "lifetime_spend", "total_purchase", "visit_count",
    "days_since_last_visit", "last_visit_at", "first_purchase_at", "added_on",
    "first_visit_account", "last_visit_account",
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _date_days_ago(n: int) -> str:
    """UTC calendar date (YYYY-MM-DD) n days ago — used as an ISO string cutoff on last_visit_at."""
    return (_now_utc() - timedelta(days=n)).strftime("%Y-%m-%d")


def _days_since_iso(v: Any, now_dt: Optional[datetime] = None) -> Optional[int]:
    """Live 'days since last visit' derived from the stored last_visit_at ISO value. There is NO
    stored days field, so this is always current (self-updates every day, no batch job). Returns
    None when the customer has no recorded visit."""
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, ((now_dt or _now_utc()) - dt).days)
    except Exception:
        return None


def _crm_filter(q, city, state, tier, card_validity, recency,
                min_visits, max_visits, min_points, max_points, min_billing,
                store_id=None) -> Dict[str, Any]:
    flt: Dict[str, Any] = {}
    if q:
        flt["$or"] = [{"mobile": {"$regex": _esc(q)}},
                      {"name": {"$regex": _esc(q), "$options": "i"}}]
    if city:
        flt["city"] = city
    if state:
        flt["state"] = state
    if store_id:
        # Home store = the store of the customer's FIRST bill (R2 rule) — the canonical
        # customer↔store link used across the platform. Lets you view a store's customer
        # base (KAZO doc Point 4 — Jasola/K00119 was invisible with no store dimension).
        flt["home_store_id"] = store_id
    if tier:
        flt["tier"] = tier
    if card_validity:
        flt["card_validity"] = card_validity
    if recency in ("active", "dormant", "lapsed"):
        # Recency is derived LIVE from last_visit_at (no stored days field) so it is always
        # current: active ≤6M, dormant 6–12M, lapsed >12M. Customers with no visit are excluded.
        c182 = _date_days_ago(182)
        c365 = _date_days_ago(365)
        if recency == "active":
            flt["last_visit_at"] = {"$gte": c182}
        elif recency == "dormant":
            flt["last_visit_at"] = {"$gte": c365, "$lt": c182}
        else:  # lapsed
            flt["last_visit_at"] = {"$gt": "", "$lt": c365}
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
# home_store is DERIVED from home_store_id (resolved to a store label), so project the id.
_CRM_FIELDS = {"_id": 0, "home_store_id": 1, **{k: 1 for k, _ in CRM_COLUMNS if k != "home_store"}}


async def _store_label_map(store_ids: List[Optional[str]]) -> Dict[str, str]:
    """id → 'CODE · Name' for the given home_store_ids (bounded batch lookup)."""
    from database import stores_col
    ids = list({x for x in store_ids if x})
    if not ids:
        return {}
    out: Dict[str, str] = {}
    async for s in stores_col.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "code": 1, "name": 1}):
        code = (s.get("code") or "").strip()
        name = (s.get("name") or "").strip()
        out[s["id"]] = f"{code} · {name}" if code and name else (code or name)
    return out


async def _store_id_by_code(codes: List[str]) -> Dict[str, Dict[str, Any]]:
    """UPPER(code) → store doc {id, code, name} for resolving a Registered Account store code."""
    from database import stores_col
    codes = list({(c or "").strip().upper() for c in codes if c})
    if not codes:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    async for s in stores_col.find({"code": {"$in": codes}}, {"_id": 0, "id": 1, "code": 1, "name": 1}):
        out[(s.get("code") or "").strip().upper()] = s
    return out


_ACCT_STORE_RE = re.compile(r"^[A-Za-z]{1,4}\d{2,}$")


def _store_code_from_account(account: Optional[str]) -> Optional[str]:
    """Store code = the part before '@' in a Registered Account (e.g. 'K00078@KAZO.com' → 'K00078'),
    only when it matches a store-code pattern. System accounts (crm.loyalty@, application@) → None."""
    if not account or "@" not in account:
        return None
    local = account.split("@", 1)[0].strip().upper()
    return local if _ACCT_STORE_RE.match(local) else None


async def _fill_missing_visits(rows: List[Dict[str, Any]], smap: Dict[str, str]) -> None:
    """Derive First Visit / Last Visit / Home Store from actual data for any row whose stored field
    is blank — so the CRM report matches Customer 360 with NO backfill. Batched, keyed on the
    indexed customer_mobile; rows already populated are skipped (no query).
      First Visit = earliest valid (non-return) bill date.
      Last Visit  = latest valid (non-return) bill date.
      Home Store  = the API/CRM registration store (Registered Account) when present, otherwise the
                    store of the customer's FIRST bill (R2). Never changes once set.
    DOB / DOA are NEVER touched here — they come only from their own fields."""
    need = [r for r in rows if not r.get("first_purchase_at") or not r.get("last_visit_at")
            or not r.get("home_store_id")]
    if not need:
        return
    mobiles = [r["mobile"] for r in need if r.get("mobile")]
    derived: Dict[str, Any] = {}
    if mobiles:
        pipe = [
            {"$match": {"customer_mobile": {"$in": mobiles}, "is_return": {"$ne": True}}},
            {"$sort": {"customer_mobile": 1, "bill_date": 1}},
            {"$group": {"_id": "$customer_mobile",
                        "first": {"$first": "$bill_date"}, "last": {"$last": "$bill_date"},
                        "first_store": {"$first": "$store_id"}}},
        ]
        async for g in transactions_col.aggregate(pipe, allowDiskUse=True, maxTimeMS=60000):
            derived[g["_id"]] = g

    # Registered Account store code → store id (preferred Home/Registered store when present)
    reg_code_for = {r["mobile"]: _store_code_from_account(r.get("registered_account"))
                    for r in need if not r.get("home_store_id") and r.get("mobile")}
    code_map = await _store_id_by_code([c for c in reg_code_for.values() if c])

    new_store_ids: set = set()
    for r in need:
        d = derived.get(r.get("mobile"))
        if not r.get("first_purchase_at") and d and d.get("first"):
            r["first_purchase_at"] = d["first"]
        if not r.get("last_visit_at") and d and d.get("last"):
            r["last_visit_at"] = d["last"]
        if not r.get("home_store_id"):
            code = reg_code_for.get(r.get("mobile"))
            s = code_map.get(code) if code else None
            if s:
                r["home_store_id"] = s["id"]
            elif d and d.get("first_store"):
                r["home_store_id"] = d["first_store"]
            if r.get("home_store_id") and r["home_store_id"] not in smap:
                new_store_ids.add(r["home_store_id"])
    if new_store_ids:
        smap.update(await _store_label_map(list(new_store_ids)))


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
    store_id: Optional[str] = None,
    sort_by: str = "lifetime_spend",
    sort_dir: str = "desc",
    skip: int = 0,
    limit: int = Query(50, le=200),
    user=Depends(get_current_user),
):
    flt = _crm_filter(q, city, state, tier, card_validity, recency,
                      min_visits, max_visits, min_points, max_points, min_billing,
                      store_id=store_id)
    sf = sort_by if sort_by in CRM_SORT_FIELDS else "lifetime_spend"
    direction = pymongo.ASCENDING if sort_dir == "asc" else pymongo.DESCENDING
    if sort_by == "days_since_last_visit":
        # No stored days field — sort by last_visit_at inverted (fewer days = more recent visit).
        sf = "last_visit_at"
        direction = pymongo.DESCENDING if sort_dir == "asc" else pymongo.ASCENDING

    total = await customers_col.count_documents(flt)
    cur = (customers_col.find(flt, _CRM_PROJECT)
           .sort(sf, direction).skip(max(0, skip)).limit(limit))
    rows = await cur.to_list(limit)
    smap = await _store_label_map([r.get("home_store_id") for r in rows])
    await _fill_missing_visits(rows, smap)
    now_dt = _now_utc()
    for r in rows:
        r["home_store"] = smap.get(r.get("home_store_id"), "")
        r["days_since_last_visit"] = _days_since_iso(r.get("last_visit_at"), now_dt)
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
    store_id: Optional[str] = None,
    sort_by: str = "lifetime_spend",
    sort_dir: str = "desc",
    user=Depends(get_current_user),
):
    flt = _crm_filter(q, city, state, tier, card_validity, recency,
                      min_visits, max_visits, min_points, max_points, min_billing,
                      store_id=store_id)
    sf = sort_by if sort_by in CRM_SORT_FIELDS else "lifetime_spend"
    direction = pymongo.ASCENDING if sort_dir == "asc" else pymongo.DESCENDING
    if sort_by == "days_since_last_visit":
        sf = "last_visit_at"
        direction = pymongo.DESCENDING if sort_dir == "asc" else pymongo.ASCENDING

    async def gen():
        from database import stores_col
        # UTF-8 BOM so the file opens cleanly in Excel (names/cities and the Home Store "·"
        # separator are non-ASCII; without the BOM Excel mis-detects the encoding → the client's
        # "CRM export cannot open / garbled" report, Oct batch lower Point 4).
        yield "\ufeff"
        smap: Dict[str, str] = {}
        async for s in stores_col.find({}, {"_id": 0, "id": 1, "code": 1, "name": 1}):
            code = (s.get("code") or "").strip()
            name = (s.get("name") or "").strip()
            smap[s["id"]] = f"{code} · {name}" if code and name else (code or name)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([l for _, l in CRM_COLUMNS])
        yield buf.getvalue(); buf.seek(0); buf.truncate(0)
        sent = 0
        now_dt = _now_utc()

        def _row(c):
            dslv = _days_since_iso(c.get("last_visit_at"), now_dt)
            return [
                smap.get(c.get("home_store_id"), "") if k == "home_store"
                else ((dslv if dslv is not None else "") if k == "days_since_last_visit"
                      else c.get(k, ""))
                for k, _ in CRM_COLUMNS]

        with pymongo.timeout(900):
            cur = customers_col.find(flt, _CRM_FIELDS).sort(sf, direction).allow_disk_use(True)
            # Stream in batches so blank First/Last Visit + Home Store can be derived from bills
            # (one batched aggregation per 1000 rows; batches with nothing missing cost nothing).
            batch: List[Dict[str, Any]] = []
            async for c in cur:
                batch.append(c)
                if len(batch) >= 1000:
                    await _fill_missing_visits(batch, smap)
                    for c2 in batch:
                        w.writerow(_row(c2))
                        yield buf.getvalue(); buf.seek(0); buf.truncate(0)
                        sent += 1
                    batch = []
                    if sent >= EXPORT_MAX_ROWS:
                        break
            if batch and sent < EXPORT_MAX_ROWS:
                await _fill_missing_visits(batch, smap)
                for c2 in batch:
                    w.writerow(_row(c2))
                    yield buf.getvalue(); buf.seek(0); buf.truncate(0)
                    sent += 1

    fname = f"crm_customers_{datetime.now(IST).strftime('%Y%m%d')}.csv"
    return StreamingResponse(gen(), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ── KPI Trend (Weekly / Monthly / Daily) ──────────────────────────────────────
async def _compute_trend(start_date, end_date, granularity, zone, city, store_class, store_id):
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
            "sales": {"$sum": PAID_EXPR},
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
    raw = await transactions_col.aggregate(pipe, allowDiskUse=True, maxTimeMS=25000).to_list(500)
    return [{
        "period": g.get("_id") or "—",
        "sales": round(g.get("sales", 0) or 0, 2),
        "discount": round(g.get("discount", 0) or 0, 2),
        "bills": int(g.get("bills", 0) or 0),
        "returns": int(g.get("returns", 0) or 0),
        "new": int(g.get("new", 0) or 0),
        "repeat": int(g.get("repeat", 0) or 0),
        "customers": len(g.get("customers", []) or []),
    } for g in raw if g.get("_id")]


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
    points = await _compute_trend(start_date, end_date, granularity, zone, city, store_class, store_id)
    return {"granularity": granularity, "points": points}


_TREND_COLS = [("period", "Period"), ("sales", "Sales"), ("discount", "Discount"),
               ("bills", "Bills"), ("returns", "Returns"), ("new", "New"),
               ("repeat", "Repeat"), ("customers", "Customers")]


@export_router.get("/trend/export")
async def kpi_trend_export(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    granularity: str = "month",
    zone: Optional[str] = None,
    city: Optional[str] = None,
    store_class: Optional[str] = None,
    store_id: Optional[str] = None,
    user=Depends(get_current_user),
):
    points = await _compute_trend(start_date, end_date, granularity, zone, city, store_class, store_id)

    def gen():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([l for _, l in _TREND_COLS])
        yield buf.getvalue(); buf.seek(0); buf.truncate(0)
        for p in points:
            w.writerow([p.get(k, "") for k, _ in _TREND_COLS])
            yield buf.getvalue(); buf.seek(0); buf.truncate(0)

    fname = f"kpi_trend_{granularity}_{datetime.now(IST).strftime('%Y%m%d')}.csv"
    return StreamingResponse(gen(), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ── CRM summary (charts: tier / recency / top cities / liability) ─────────────
_REC_LABELS = {"active": "Active (0-6M)", "dormant": "Dormant (6-12M)",
               "lapsed": "Lapsed (12M+)", "unknown": "Unknown"}
_crm_refreshing: set = set()


def _crm_summary_pipe(flt: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {"$match": flt},
        {"$facet": {
            "by_tier": [
                {"$group": {"_id": {"$ifNull": ["$tier", "unknown"]}, "count": {"$sum": 1},
                            "points": {"$sum": "$points_balance"}, "spend": {"$sum": "$lifetime_spend"}}},
                {"$sort": {"count": -1}},
            ],
            # Recency derived LIVE from last_visit_at (no stored days field, always current).
            "by_recency": [
                {"$group": {
                    "_id": {"$let": {"vars": {"lv": {"$ifNull": ["$last_visit_at", ""]}}, "in": {"$switch": {
                        "branches": [
                            {"case": {"$eq": ["$$lv", ""]}, "then": "unknown"},
                            {"case": {"$gte": ["$$lv", _date_days_ago(182)]}, "then": "active"},
                            {"case": {"$gte": ["$$lv", _date_days_ago(365)]}, "then": "dormant"},
                        ], "default": "lapsed"}}}},
                    "count": {"$sum": 1},
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


def _crm_summary_shape(res: Dict[str, Any]) -> Dict[str, Any]:
    totals = (res.get("totals") or [{}])
    totals = totals[0] if totals else {}
    return {
        "partial": False,
        "by_tier": [{"tier": (g["_id"] or "unknown"), "count": g["count"],
                     "points": round(g.get("points", 0) or 0, 2), "spend": round(g.get("spend", 0) or 0, 2)}
                    for g in (res.get("by_tier") or [])],
        "by_recency": [{"bucket": _REC_LABELS.get(g["_id"], str(g["_id"])), "count": g["count"]}
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


async def _crm_summary_compute(key: str, flt: Dict[str, Any]) -> None:
    """Run the heavy facet with a hard time budget (below the 120s proxy ceiling) and cache it.
    Runs in the background so a cold request never blocks — see crm_summary()."""
    try:
        with pymongo.timeout(90):
            res = (await customers_col.aggregate(_crm_summary_pipe(flt), allowDiskUse=True, maxTimeMS=25000).to_list(1)) or [{}]
        cache_set(key, _crm_summary_shape(res[0] if res else {}))
    except Exception:  # noqa: BLE001 — leave any prior cached value in place; endpoint returns partial
        logging.getLogger("kazo-fundle.crm").warning("crm-summary compute failed/timed out for %s", key)
    finally:
        _crm_refreshing.discard(key)


def _crm_kick(key: str, flt: Dict[str, Any]) -> None:
    if key not in _crm_refreshing:
        _crm_refreshing.add(key)
        asyncio.create_task(_crm_summary_compute(key, flt))


_CRM_SUMMARY_PARTIAL = {
    "partial": True, "by_tier": [], "by_recency": [], "top_cities": [],
    "totals": {"customers": None, "points": None, "redeemed": None, "spend": None, "visits": None},
    "message": ("Summary KPIs are being computed for this filter — the customer list below is ready now. "
                "Reopen in a few seconds for the KPIs, or narrow the filters (state / tier / recency) to speed it up."),
}


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
    store_id: Optional[str] = None,
    refresh: bool = False,
    user=Depends(get_current_user),
):
    flt = _crm_filter(q, city, state, tier, card_validity, recency,
                      min_visits, max_visits, min_points, max_points, min_billing,
                      store_id=store_id)
    key = "crm-summary|" + json.dumps({
        "q": q, "city": city, "state": state, "tier": tier, "card_validity": card_validity,
        "recency": recency, "min_visits": min_visits, "max_visits": max_visits,
        "min_points": min_points, "max_points": max_points, "min_billing": min_billing,
        "store_id": store_id,
    }, sort_keys=True, default=str)

    if not refresh:
        fresh = cache_get(key)
        if fresh is not None:
            return fresh
        stale = cache_get_stale(key)
        if stale is not None:
            _crm_kick(key, flt)   # stale-while-revalidate in background
            return stale

    # Cold (or forced refresh): compute in the background and return partial KPIs instantly —
    # NEVER hang to the 120s proxy timeout. The next open (once compute lands) serves real data.
    _crm_kick(key, flt)
    return dict(_CRM_SUMMARY_PARTIAL)


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


# ── Read-only diagnostics (KAZO doc Point 1 & 2) ──────────────────────────────
@router.get("/_diagnostics")
async def report_diagnostics(user=Depends(get_current_user)):
    """Read-only probe explaining why historical data may be absent from reports (Point 1) and
    quantifying the DOB/DOA-vs-visit-date data issue (Point 2). Safe on production (time-capped)."""
    tx_by_year: List[Dict[str, Any]] = []
    async for g in transactions_col.aggregate(
        [{"$group": {"_id": {"$substrCP": [{"$ifNull": ["$bill_date", ""]}, 0, 4]},
                     "bills": {"$sum": 1}, "paid": {"$sum": PAID_EXPR}}},
         {"$sort": {"_id": 1}}], allowDiskUse=True, maxTimeMS=40000):
        tx_by_year.append({"year": g.get("_id") or "(blank)", "bills": g["bills"],
                           "paid": round(g.get("paid", 0) or 0, 2)})
    tx_by_source: List[Dict[str, Any]] = []
    async for g in transactions_col.aggregate(
        [{"$group": {"_id": "$source", "bills": {"$sum": 1}}}], maxTimeMS=40000):
        tx_by_source.append({"source": g.get("_id") or "(none)", "bills": g["bills"]})
    span_rows = await transactions_col.aggregate(
        [{"$group": {"_id": None, "min": {"$min": "$bill_date"}, "max": {"$max": "$bill_date"}}}],
        maxTimeMS=40000).to_list(1)
    span = span_rows[0] if span_rows else {}

    async def _cnt(flt: Dict[str, Any]) -> int:
        try:
            with pymongo.timeout(40):
                return await customers_col.count_documents(flt)
        except Exception:
            return -1

    _blank = lambda f: {"$or": [{f: {"$in": [None, ""]}}, {f: {"$exists": False}}]}
    blanks = {
        "customers_total": await _cnt({}),
        "missing_first_purchase_at": await _cnt(_blank("first_purchase_at")),
        "missing_last_visit_at": await _cnt(_blank("last_visit_at")),
        "missing_home_store_id": await _cnt(_blank("home_store_id")),
        "pos_created": await _cnt({"source": "pos_ewards"}),
    }
    # Point 2 — DOB/DOA equal to a visit date, or DOB == DOA (a source mis-fill, not our mapping)
    suspicious = await customers_col.aggregate([
        {"$match": {"birthday": {"$nin": [None, ""]}}},
        {"$project": {"bad": {"$or": [
            {"$eq": ["$birthday", {"$substrCP": [{"$ifNull": ["$first_purchase_at", ""]}, 0, 10]}]},
            {"$eq": ["$birthday", {"$substrCP": [{"$ifNull": ["$last_visit_at", ""]}, 0, 10]}]},
            {"$and": [{"$ne": [{"$ifNull": ["$anniversary", None]}, None]},
                      {"$eq": ["$birthday", "$anniversary"]}]},
        ]}}},
        {"$match": {"bad": True}},
        {"$count": "n"},
    ], allowDiskUse=True, maxTimeMS=40000).to_list(1)
    dob_doa_equals_visit = suspicious[0]["n"] if suspicious else 0

    from database import stores_col
    return {
        "transactions": {"by_year": tx_by_year, "by_source": tx_by_source,
                         "bill_date_min": span.get("min"), "bill_date_max": span.get("max")},
        "customers": blanks,
        "point2_dob_or_doa_equals_visit_or_each_other": dob_doa_equals_visit,
        "stores_total": await stores_col.count_documents({}),
        "notes": [
            "Point 1: if by_year lists old years but the report shows none, the cause is the report "
            "DATE-RANGE filter (the UI defaults to the current month) or a non-ISO bill_date format "
            "(look for a '(blank)' or malformed year bucket). Reports impose NO go-live cutoff in code.",
            "Point 3/4/6: missing_first_purchase_at / missing_home_store_id are the rows the CRM report "
            "now derives live from bills; POS also stamps them on every future bill.",
            "Point 2: point2_... counts customers whose DOB/DOA equals a visit date or each other — a "
            "source-file mis-fill. The app reads DOB/DOA only from their own fields.",
        ],
    }



# ── Point 2 repair: null DOB/DOA that were mis-filled with a visit date ───────
# A real DOB/DOA never equals the customer's first/last purchase date. The source CRM export
# populated ~136k customers' DOB/DOA with a visit date; this one-off, idempotent, admin-only
# repair nulls exactly those (safe to re-run). The ingest mapper also guards this going forward.
_DOB_REPAIR_STATUS: Dict[str, Any] = {"state": "idle"}


def _visit_mismatch_filter(field: str) -> Dict[str, Any]:
    return {field: {"$nin": [None, ""]}, "$expr": {"$or": [
        {"$eq": [f"${field}", {"$substrCP": [{"$ifNull": ["$first_purchase_at", ""]}, 0, 10]}]},
        {"$eq": [f"${field}", {"$substrCP": [{"$ifNull": ["$last_visit_at", ""]}, 0, 10]}]},
    ]}}


def _require_admin(user: dict) -> None:
    if (user or {}).get("role") not in ("super_admin", "brand_admin"):
        raise HTTPException(403, "Admin only")


async def _run_dob_doa_repair() -> None:
    _DOB_REPAIR_STATUS.update({"state": "running", "started_at": datetime.now(IST).isoformat(),
                               "birthday_cleared": 0, "anniversary_cleared": 0, "error": None})
    try:
        with pymongo.timeout(900):
            rb = await customers_col.update_many(_visit_mismatch_filter("birthday"),
                                                 {"$set": {"birthday": None}})
            ra = await customers_col.update_many(_visit_mismatch_filter("anniversary"),
                                                 {"$set": {"anniversary": None}})
        _DOB_REPAIR_STATUS.update({"state": "done", "finished_at": datetime.now(IST).isoformat(),
                                   "birthday_cleared": rb.modified_count,
                                   "anniversary_cleared": ra.modified_count})
    except Exception as e:
        _DOB_REPAIR_STATUS.update({"state": "error", "error": str(e)})
    logger.info("DOB/DOA repair result: %s", _DOB_REPAIR_STATUS)


@export_router.post("/_repair-dob-doa")
async def repair_dob_doa(dry_run: bool = True, user=Depends(get_current_user)):
    """KAZO doc Point 2. dry_run=true (default) counts affected rows; dry_run=false runs the repair
    in the background (poll /_repair-dob-doa/status). Nulls DOB/DOA that equal a first/last visit date."""
    _require_admin(user)
    if dry_run:
        async def _cnt(field: str) -> int:
            r = await customers_col.aggregate(
                [{"$match": _visit_mismatch_filter(field)}, {"$count": "n"}],
                allowDiskUse=True, maxTimeMS=40000).to_list(1)
            return r[0]["n"] if r else 0
        return {"dry_run": True, "birthday_to_clear": await _cnt("birthday"),
                "anniversary_to_clear": await _cnt("anniversary"),
                "note": "POST ?dry_run=false to apply (background). Only DOB/DOA equal to a visit date are nulled."}
    if _DOB_REPAIR_STATUS.get("state") == "running":
        return {"started": False, "reason": "already running", "status": _DOB_REPAIR_STATUS}
    asyncio.create_task(_run_dob_doa_repair())
    return {"started": True, "status_url": "/api/kpi-reports/_repair-dob-doa/status"}


@export_router.get("/_repair-dob-doa/status")
async def repair_dob_doa_status(user=Depends(get_current_user)):
    _require_admin(user)
    return _DOB_REPAIR_STATUS
