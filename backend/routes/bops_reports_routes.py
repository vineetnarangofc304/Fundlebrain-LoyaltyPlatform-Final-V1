"""BOPS reports (Wave 1):

* New vs Repeat (Daywise) — per-day distinct New / Existing customer counts + % split.
  Reuses the same new/existing tagging + IST-day bucketing as the Weekly KPI report.
* Store-wise Customer Count — snapshot of each store's MAPPED customer base bucketed by
  recency (as of `as_of`, default today): Active (0-6M) / Win-Back-Lost (6-12M) /
  At-Risk (12M+) plus a "No Mapping" bucket for customers with no mobile. Grouped by the
  customer's home store.

Two routers per report: `router` (request db_deadline) for the paginated/JSON read and
`export_router` (no request-wide deadline) for the streamed CSV.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pymongo
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from auth import get_current_user
from database import customers_col, transactions_col, stores_col
from routes._db_timeout import db_deadline
from routes.reports_kpi_routes import _store_match, IST

logger = logging.getLogger("kazo-fundle.bops_reports")

router = APIRouter(prefix="/bops-reports", tags=["bops-reports"],
                   dependencies=[Depends(db_deadline)])
export_router = APIRouter(prefix="/bops-reports", tags=["bops-reports"])

RECENCY_6M_DAYS = 182
RECENCY_12M_DAYS = 365

_IS_NEW = {"$eq": [{"$toLower": {"$ifNull": ["$new_or_existing", ""]}}, "new"]}
_IS_EXISTING = {"$eq": [{"$toLower": {"$ifNull": ["$new_or_existing", ""]}}, "existing"]}


def _pct(part: int, total: int) -> float:
    return round(part / total, 4) if total else 0.0


# Short-TTL in-process cache for the heavy full-collection segment reports (they scan the
# entire ~800k customer base and are CPU-bound, so an index can't help — but the underlying
# data shifts slowly, so a 10-min cache makes repeat loads instant). `refresh=1` bypasses it.
import time as _time
_REPORT_CACHE: Dict[str, Tuple[float, Any]] = {}
_REPORT_TTL = 600


def _rc_get(key: str):
    v = _REPORT_CACHE.get(key)
    if v and (_time.time() - v[0]) < _REPORT_TTL:
        return v[1]
    return None


def _rc_set(key: str, val: Any) -> None:
    _REPORT_CACHE[key] = (_time.time(), val)
    if len(_REPORT_CACHE) > 300:
        oldest = min(_REPORT_CACHE.items(), key=lambda kv: kv[1][0])[0]
        _REPORT_CACHE.pop(oldest, None)


# ══════════════════════════════════════════════════════════════════════════════
# New vs Repeat (Daywise)
# ══════════════════════════════════════════════════════════════════════════════
NVR_COLUMNS: List[Tuple[str, str]] = [
    ("date", "Date"),
    ("new_customer_count", "New Customer Count"),
    ("existing_customer_count", "Existing Customer Count"),
    ("total_customer_count", "Total Customer Count"),
    ("pct_new", "% New Customer"),
    ("pct_existing", "% Existing Customers"),
]


async def _new_vs_repeat_daywise(match: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Distinct customers per IST bill-day, split New vs Existing (fresh bills only)."""
    cmatch = dict(match)
    cmatch["is_return"] = {"$ne": True}
    cmatch["customer_mobile"] = {"$nin": [None, ""]}
    day = {"$substrCP": ["$bill_date", 0, 10]}
    pipe = [
        {"$match": cmatch},
        {"$group": {"_id": {"d": day, "m": "$customer_mobile"},
                    "isnew": {"$max": {"$cond": [_IS_NEW, 1, 0]}},
                    "isex": {"$max": {"$cond": [_IS_EXISTING, 1, 0]}}}},
        {"$group": {"_id": "$_id.d",
                    "new": {"$sum": "$isnew"},
                    "existing": {"$sum": "$isex"}}},
        {"$sort": {"_id": 1}},
        {"$limit": 1200},
    ]
    raw = await transactions_col.aggregate(pipe, allowDiskUse=True).to_list(1200)
    rows: List[Dict[str, Any]] = []
    for g in raw:
        d = g.get("_id")
        if not d:
            continue
        new = int(g.get("new", 0) or 0)
        ex = int(g.get("existing", 0) or 0)
        tot = new + ex
        rows.append({
            "date": d,
            "new_customer_count": new,
            "existing_customer_count": ex,
            "total_customer_count": tot,
            "pct_new": _pct(new, tot),
            "pct_existing": _pct(ex, tot),
        })
    return rows


@router.get("/new-vs-repeat-daywise")
async def new_vs_repeat_daywise(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    zone: Optional[str] = None,
    city: Optional[str] = None,
    store_class: Optional[str] = None,
    store_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    match = _store_match(start_date, end_date, zone, city, store_class, store_id)
    with pymongo.timeout(90):
        rows = await _new_vs_repeat_daywise(match)
    totals = {
        "new_customer_count": sum(r["new_customer_count"] for r in rows),
        "existing_customer_count": sum(r["existing_customer_count"] for r in rows),
        "total_customer_count": sum(r["total_customer_count"] for r in rows),
    }
    totals["pct_new"] = _pct(totals["new_customer_count"], totals["total_customer_count"])
    totals["pct_existing"] = _pct(totals["existing_customer_count"], totals["total_customer_count"])
    return {"rows": rows, "count": len(rows), "totals": totals,
            "columns": [{"key": k, "label": l} for k, l in NVR_COLUMNS]}


@export_router.get("/new-vs-repeat-daywise/export")
async def new_vs_repeat_daywise_export(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    zone: Optional[str] = None,
    city: Optional[str] = None,
    store_class: Optional[str] = None,
    store_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    match = _store_match(start_date, end_date, zone, city, store_class, store_id)
    with pymongo.timeout(120):
        rows = await _new_vs_repeat_daywise(match)

    def gen():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([l for _, l in NVR_COLUMNS])
        yield buf.getvalue(); buf.seek(0); buf.truncate(0)
        for r in rows:
            w.writerow([r.get(k, "") for k, _ in NVR_COLUMNS])
            yield buf.getvalue(); buf.seek(0); buf.truncate(0)

    fname = f"new_vs_repeat_daywise_{datetime.now(IST).strftime('%Y%m%d')}.csv"
    return StreamingResponse(gen(), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ══════════════════════════════════════════════════════════════════════════════
# Store-wise Customer Count (recency segments)
# ══════════════════════════════════════════════════════════════════════════════
CCS_COLUMNS: List[Tuple[str, str]] = [
    ("store_name", "Store Name"),
    ("active", "Active (0-6 M)"),
    ("no_mapping", "No Mapping (No Mob Num)"),
    ("win_back_lost", "Win Back- Lost (6-12M)"),
    ("at_risk", "Win-Back- At-Risk (12 & Abv M)"),
    ("grand_total", "Grand Total"),
]

_HAS_MOBILE = {"$and": [{"$ne": [{"$ifNull": ["$mobile", None]}, None]}, {"$ne": ["$mobile", ""]}]}


async def _store_map() -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    async for s in stores_col.find({}, {"_id": 0, "id": 1, "code": 1, "name": 1,
                                        "region": 1, "store_class": 1}):
        if s.get("id"):
            out[s["id"]] = s
    return out


async def _customer_count_by_store(as_of: datetime, store_id: Optional[str] = None) -> List[Dict[str, Any]]:
    cut6 = (as_of - timedelta(days=RECENCY_6M_DAYS)).isoformat()
    cut12 = (as_of - timedelta(days=RECENCY_12M_DAYS)).isoformat()
    lv = {"$ifNull": ["$last_visit_at", ""]}
    # Compute each customer's segment ONCE via $switch (short-circuits) instead of evaluating
    # four separate $cond conditions per doc — ~2x faster on the full-collection scan.
    seg = {"$switch": {"branches": [
        {"case": {"$not": [_HAS_MOBILE]}, "then": "no_mapping"},
        {"case": {"$gte": [lv, cut6]}, "then": "active"},
        {"case": {"$gte": [lv, cut12]}, "then": "win_back_lost"},
    ], "default": "at_risk"}}
    match: Dict[str, Any] = {}
    if store_id:
        match["home_store_id"] = store_id
    pipe: List[Dict[str, Any]] = []
    if match:
        pipe.append({"$match": match})
    pipe += [
        {"$project": {"home_store_id": 1, "seg": seg}},
        {"$group": {"_id": {"s": "$home_store_id", "seg": "$seg"}, "n": {"$sum": 1}}},
    ]
    raw = await customers_col.aggregate(pipe, allowDiskUse=True).to_list(20000)
    agg: Dict[str, Dict[str, int]] = {}
    for g in raw:
        sid = g["_id"].get("s")
        key = g["_id"].get("seg")
        n = int(g.get("n", 0) or 0)
        d = agg.setdefault(sid or "", {"active": 0, "no_mapping": 0, "win_back_lost": 0, "at_risk": 0, "grand_total": 0})
        d[key] = d.get(key, 0) + n
        d["grand_total"] += n
    smap = await _store_map()
    rows: List[Dict[str, Any]] = []
    for sid, d in agg.items():
        s = smap.get(sid, {})
        rows.append({
            "store_id": sid,
            "store_code": s.get("code") or "—",
            "store_name": s.get("name") or (s.get("code") if s else None) or ("Unmapped Store" if not sid else "—"),
            "zone": s.get("region") or "—",
            "store_class": s.get("store_class") or "—",
            "active": d["active"],
            "no_mapping": d["no_mapping"],
            "win_back_lost": d["win_back_lost"],
            "at_risk": d["at_risk"],
            "grand_total": d["grand_total"],
        })
    rows.sort(key=lambda r: r["grand_total"], reverse=True)
    return rows


def _ccs_totals(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    return {k: sum(int(r.get(k, 0) or 0) for r in rows)
            for k in ("active", "no_mapping", "win_back_lost", "at_risk", "grand_total")}


@router.get("/customer-count-by-store")
async def customer_count_by_store(
    as_of: Optional[str] = None,
    store_id: Optional[str] = None,
    refresh: bool = False,
    user: dict = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    if as_of:
        try:
            now = datetime.fromisoformat(as_of).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    ck = f"ccs:{now.date().isoformat()}:{store_id or ''}"
    if not refresh:
        cached = _rc_get(ck)
        if cached is not None:
            return {**cached, "cached": True}
    with pymongo.timeout(90):
        rows = await _customer_count_by_store(now, store_id)
    out = {"rows": rows, "count": len(rows), "totals": _ccs_totals(rows),
           "as_of": now.date().isoformat(),
           "columns": [{"key": k, "label": l} for k, l in CCS_COLUMNS]}
    _rc_set(ck, out)
    return out

@export_router.get("/customer-count-by-store/export")
async def customer_count_by_store_export(
    as_of: Optional[str] = None,
    store_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    if as_of:
        try:
            now = datetime.fromisoformat(as_of).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    with pymongo.timeout(120):
        rows = await _customer_count_by_store(now, store_id)
    totals = _ccs_totals(rows)

    def gen():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow([l for _, l in CCS_COLUMNS])
        yield buf.getvalue(); buf.seek(0); buf.truncate(0)
        for r in rows:
            w.writerow([r.get(k, "") for k, _ in CCS_COLUMNS])
            yield buf.getvalue(); buf.seek(0); buf.truncate(0)
        w.writerow(["Grand Total", totals["active"], totals["no_mapping"],
                    totals["win_back_lost"], totals["at_risk"], totals["grand_total"]])
        yield buf.getvalue()

    fname = f"customer_count_by_store_{datetime.now(IST).strftime('%Y%m%d')}.csv"
    return StreamingResponse(gen(), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})



# ══════════════════════════════════════════════════════════════════════════════
# Sales MTD — customer base split by recency segment with lifetime revenue and the
# count of customers acquired month-to-date (first purchase this month). Derived in a
# single pass over customers_col (lifetime_spend / last_visit_at / first_purchase_at),
# so it is fast even at full scale.
# ══════════════════════════════════════════════════════════════════════════════
SMTD_COLUMNS: List[Tuple[str, str]] = [
    ("segment", "Segment"),
    ("count", "Customer Count"),
    ("revenue", "Total Revenue"),
    ("new_count", "New Customer Count (MTD)"),
]

_SMTD_SEG = {
    "active": "Active (0-6 M)",
    "no_mapping": "No Mapping (No Mob Num)",
    "win_back_lost": "Win Back- Lost (6-12M)",
    "at_risk": "Win-Back- At-Risk (12 & Abv M)",
}


def _month_window(month: Optional[str]) -> Tuple[str, str, str]:
    """Return (label 'YYYY-MM', month_start iso-prefix, next_month_start iso-prefix)."""
    ist_now = datetime.now(IST)
    y, m = ist_now.year, ist_now.month
    if month:
        try:
            parts = month.split("-")
            y, m = int(parts[0]), int(parts[1])
        except Exception:
            pass
    start = f"{y:04d}-{m:02d}-01"
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    nxt = f"{ny:04d}-{nm:02d}-01"
    return f"{y:04d}-{m:02d}", start, nxt


async def _sales_mtd(as_of: datetime, month_start: str, next_month: str,
                     store_id: Optional[str]) -> List[Dict[str, Any]]:
    cut6 = (as_of - timedelta(days=RECENCY_6M_DAYS)).isoformat()
    cut12 = (as_of - timedelta(days=RECENCY_12M_DAYS)).isoformat()
    lv = {"$ifNull": ["$last_visit_at", ""]}
    fp = {"$ifNull": ["$first_purchase_at", ""]}
    # Segment computed ONCE per doc via $switch (short-circuits) — ~2x faster than four $cond.
    seg = {"$switch": {"branches": [
        {"case": {"$not": [_HAS_MOBILE]}, "then": "no_mapping"},
        {"case": {"$gte": [lv, cut6]}, "then": "active"},
        {"case": {"$gte": [lv, cut12]}, "then": "win_back_lost"},
    ], "default": "at_risk"}}
    isnew = {"$and": [{"$ne": [fp, ""]}, {"$gte": [fp, month_start]}, {"$lt": [fp, next_month]}]}
    match: Dict[str, Any] = {}
    if store_id:
        match["home_store_id"] = store_id
    pipe: List[Dict[str, Any]] = []
    if match:
        pipe.append({"$match": match})
    pipe += [
        {"$project": {"seg": seg, "sp": {"$ifNull": ["$lifetime_spend", 0]},
                      "nw": {"$cond": [isnew, 1, 0]}}},
        {"$group": {"_id": "$seg", "count": {"$sum": 1},
                    "revenue": {"$sum": "$sp"}, "new_count": {"$sum": "$nw"}}},
    ]
    raw = await customers_col.aggregate(pipe, allowDiskUse=True).to_list(10)
    by = {g["_id"]: g for g in raw}
    rows: List[Dict[str, Any]] = []
    for key in ("active", "no_mapping", "win_back_lost", "at_risk"):
        g = by.get(key, {})
        rows.append({
            "segment": _SMTD_SEG[key],
            "key": key,
            "count": int(g.get("count", 0) or 0),
            "revenue": round(float(g.get("revenue", 0) or 0), 2),
            "new_count": int(g.get("new_count", 0) or 0),
        })
    return rows


def _smtd_totals(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "count": sum(int(r.get("count", 0) or 0) for r in rows),
        "revenue": round(sum(float(r.get("revenue", 0) or 0) for r in rows), 2),
        "new_count": sum(int(r.get("new_count", 0) or 0) for r in rows),
    }


@router.get("/sales-mtd")
async def sales_mtd(
    as_of: Optional[str] = None,
    month: Optional[str] = None,
    store_id: Optional[str] = None,
    refresh: bool = False,
    user: dict = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    if as_of:
        try:
            now = datetime.fromisoformat(as_of).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    label, m_start, m_next = _month_window(month)
    ck = f"smtd:{now.date().isoformat()}:{label}:{store_id or ''}"
    if not refresh:
        cached = _rc_get(ck)
        if cached is not None:
            return {**cached, "cached": True}
    with pymongo.timeout(90):
        rows = await _sales_mtd(now, m_start, m_next, store_id)
    out = {"rows": rows, "count": len(rows), "totals": _smtd_totals(rows),
           "month": label, "as_of": now.date().isoformat(),
           "columns": [{"key": k, "label": l} for k, l in SMTD_COLUMNS]}
    _rc_set(ck, out)
    return out
