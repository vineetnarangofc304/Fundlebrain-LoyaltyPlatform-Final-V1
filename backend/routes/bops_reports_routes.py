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
    match: Dict[str, Any] = {}
    if store_id:
        match["home_store_id"] = store_id
    pipe = [
        {"$match": match},
        {"$group": {
            "_id": "$home_store_id",
            "no_mapping": {"$sum": {"$cond": [{"$not": [_HAS_MOBILE]}, 1, 0]}},
            "active": {"$sum": {"$cond": [{"$and": [_HAS_MOBILE, {"$gte": [lv, cut6]}]}, 1, 0]}},
            "win_back_lost": {"$sum": {"$cond": [
                {"$and": [_HAS_MOBILE, {"$lt": [lv, cut6]}, {"$gte": [lv, cut12]}]}, 1, 0]}},
            "at_risk": {"$sum": {"$cond": [
                {"$and": [_HAS_MOBILE, {"$lt": [lv, cut12]}]}, 1, 0]}},
            "grand_total": {"$sum": 1},
        }},
    ]
    raw = await customers_col.aggregate(pipe, allowDiskUse=True).to_list(5000)
    smap = await _store_map()
    rows: List[Dict[str, Any]] = []
    for g in raw:
        sid = g.get("_id")
        s = smap.get(sid or "", {})
        rows.append({
            "store_id": sid or "",
            "store_code": s.get("code") or "—",
            "store_name": s.get("name") or (s.get("code") if s else None) or ("Unmapped Store" if not sid else "—"),
            "zone": s.get("region") or "—",
            "store_class": s.get("store_class") or "—",
            "active": int(g.get("active", 0) or 0),
            "no_mapping": int(g.get("no_mapping", 0) or 0),
            "win_back_lost": int(g.get("win_back_lost", 0) or 0),
            "at_risk": int(g.get("at_risk", 0) or 0),
            "grand_total": int(g.get("grand_total", 0) or 0),
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
    user: dict = Depends(get_current_user),
):
    now = datetime.now(timezone.utc)
    if as_of:
        try:
            now = datetime.fromisoformat(as_of).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    with pymongo.timeout(90):
        rows = await _customer_count_by_store(now, store_id)
    return {"rows": rows, "count": len(rows), "totals": _ccs_totals(rows),
            "as_of": now.date().isoformat(),
            "columns": [{"key": k, "label": l} for k, l in CCS_COLUMNS]}

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
