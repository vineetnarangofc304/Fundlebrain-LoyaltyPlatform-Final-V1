"""Shopper Bill Report — one row per BILL for everyone who shopped in a date range.

Client spec (KAZO):
    Bill Date / Bill Type (Return / Regular) / Customer mobile / Reg store /
    Store code / Trans store name / Trans ID / Bill number / Customer type
    (New / Existing) / Recency / Last Visit / 2nd-last Visit / Total Visit /
    Zone / Customer city / Bill time / Net before tax / Total Tax / Total
    Discount / Total Bill Amount / Total Lifetime purchase / Total lifetime
    bill cuts (NET = sale bills − return bills).

Recency (the shopper's status JUST BEFORE this bill — the gap between this bill's
day and the customer's immediately-preceding visit day; lets you spot shoppers who
had gone dormant/lapsed and have now returned):
    NEW customer (no previous txn)    → Active   (per doc Point 2)
    0-6 months since previous visit   → Active
    6-12 months since previous visit  → Dormant
    12 months + since previous visit  → Lapsed
"Last Visit" / "2nd-last Visit" are therefore shown RELATIVE to the bill (the
previous visit, and the one before that) so each row is self-consistent.

Two routers:
  * `router`        (under db_deadline 45s) — paginated listing + filter options.
  * `export_router` (NO db_deadline)        — streamed CSV (each heavy op wrapped
                                               in its own pymongo.timeout so a
                                               large export streams without the
                                               request-wide 45s ceiling).
"""
from __future__ import annotations

import bisect
import csv
import io
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pymongo
from pymongo.errors import PyMongoError
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from auth import get_current_user
from database import customers_col, transactions_col, stores_col
from routes._db_timeout import db_deadline

logger = logging.getLogger("kazo-fundle.shopper_report")

router = APIRouter(prefix="/shopper-report", tags=["shopper-report"],
                   dependencies=[Depends(db_deadline)])
# Export gets its OWN router with NO request-wide deadline so a big CSV can stream.
export_router = APIRouter(prefix="/shopper-report", tags=["shopper-report"])

# 6 months ≈ 182 days, 12 months = 365 days (per the client's Active/Dormant/Lapsed rule).
RECENCY_6M_DAYS = 182
RECENCY_12M_DAYS = 365
EXPORT_MAX_ROWS = 200_000          # safety ceiling on a single CSV export
ENRICH_BATCH = 2000                # rows enriched per round-trip group

SORT_FIELDS = {
    "bill_date": "bill_date",
    "net_amount": "net_amount",
    "gross_amount": "gross_amount",
    "customer_mobile": "customer_mobile",
    "store_name": "store_name",
    "bill_number": "bill_number",
}

# Column order shared by the API + CSV export.
COLUMNS: List[Tuple[str, str]] = [
    ("bill_date", "Bill Date"),
    ("bill_time", "Bill Time"),
    ("bill_type", "Bill Type"),
    ("customer_mobile", "Customer Mobile"),
    ("reg_store", "Reg Store"),
    ("store_code", "Store Code"),
    ("trans_store_name", "Trans Store Name"),
    ("transaction_id", "Trans ID"),
    ("bill_number", "Bill Number"),
    ("customer_type", "Customer Type"),
    ("recency", "Recency"),
    ("last_visit", "Last Visit"),
    ("second_last_visit", "2nd Last Visit"),
    ("total_visits", "Total Visits"),
    ("zone", "Zone"),
    ("store_class", "Store Class"),
    ("customer_city", "Customer City"),
    ("net_before_tax", "Net Before Tax"),
    ("total_tax", "Total Tax"),
    ("total_discount", "Total Discount"),
    ("total_bill_amount", "Total Bill Amount"),
    ("lifetime_purchase", "Lifetime Purchase"),
    ("lifetime_bill_cuts", "Lifetime Bill Cuts (Net)"),
]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# Canonical display timezone for the whole platform.
IST = timezone(timedelta(hours=5, minutes=30))


def _to_ist_parts(iso: Optional[str]) -> Tuple[str, str]:
    """(date 'YYYY-MM-DD', time 'HH:MM') for an ISO bill_date, rendered in IST so it
    always matches the dashboard (which also renders in Asia/Kolkata). Naive values
    are assumed UTC (how historic uploads are stored)."""
    if not iso:
        return "", ""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)   # naive values are treated as IST (matches the frontend parser)
        dt = dt.astimezone(IST)
        return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")
    except Exception:
        return iso[:10], (iso[11:16] if len(iso) >= 16 else "")


def _ist_date(iso: Optional[str]) -> Optional[str]:
    d, _ = _to_ist_parts(iso)
    return d or None


def _recency_cutoffs(now: datetime) -> Tuple[str, str]:
    """ISO cutoff strings: anything >= cut6 is Active, >= cut12 (and < cut6) is
    Dormant, the rest Lapsed."""
    cut6 = (now - timedelta(days=RECENCY_6M_DAYS)).isoformat()
    cut12 = (now - timedelta(days=RECENCY_12M_DAYS)).isoformat()
    return cut6, cut12


def _recency_label(last_visit: Optional[str], now: datetime) -> str:
    if not last_visit:
        return "—"
    cut6, cut12 = _recency_cutoffs(now)
    if last_visit >= cut6:
        return "Active (0-6M)"
    if last_visit >= cut12:
        return "Dormant (6-12M)"
    return "Lapsed (12M+)"


def _recency_bucket(label: str) -> str:
    """Map a recency LABEL ('Active (0-6M)' …) back to its bucket key."""
    return ("active" if "Active" in label else "dormant" if "Dormant" in label
            else "lapsed" if "Lapsed" in label else "unknown")


def _recency_from_gap(bill_day: Optional[str], prev_day: Optional[str]) -> str:
    """Recency the shopper was in JUST BEFORE this bill = the gap (in days) between
    this bill's day and the customer's immediately-preceding visit day. Per the KAZO
    doc (Point 2): a NEW customer (no previous transaction) is tagged Active; an OLD
    customer is tagged from the gap to their previous/last transaction:
        first-ever visit (no earlier day) → 'Active (0-6M)'   (new customer = Active)
        gap 0-182 days                    → 'Active (0-6M)'
        gap 183-365 days                  → 'Dormant (6-12M)'
        gap 365+ days                     → 'Lapsed (12M+)'
    Both args are IST 'YYYY-MM-DD' day strings (lexically == chronologically sortable)."""
    if not prev_day:
        return "Active (0-6M)"   # new customer (first-ever visit) → Active, per doc Point 2
    if not bill_day:
        return "—"
    try:
        d1 = datetime.strptime(bill_day, "%Y-%m-%d")
        d0 = datetime.strptime(prev_day, "%Y-%m-%d")
    except Exception:
        return "—"
    gap = (d1 - d0).days
    if gap <= RECENCY_6M_DAYS:
        return "Active (0-6M)"
    if gap <= RECENCY_12M_DAYS:
        return "Dormant (6-12M)"
    return "Lapsed (12M+)"


def _build_match(start_date, end_date, bill_type, customer_type, store_id, zone,
                 city, q) -> Dict[str, Any]:
    m: Dict[str, Any] = {}
    if start_date and end_date:
        m["bill_date"] = {"$gte": start_date, "$lte": end_date + "T23:59:59Z"}
    elif start_date:
        m["bill_date"] = {"$gte": start_date}
    elif end_date:
        m["bill_date"] = {"$lte": end_date + "T23:59:59Z"}

    if bill_type == "return":
        m["is_return"] = True
    elif bill_type == "regular":
        m["is_return"] = {"$ne": True}

    if customer_type == "new":
        m["new_or_existing"] = {"$regex": "new", "$options": "i"}
    elif customer_type == "existing":
        m["new_or_existing"] = {"$regex": "exist", "$options": "i"}

    if store_id:
        m["store_id"] = store_id
    if zone:
        m["zone"] = zone
    if city:
        m["city"] = {"$regex": f"^{city}", "$options": "i"}
    if q:
        digits = "".join(ch for ch in q if ch.isdigit())
        ors = []
        if digits:
            ors.append({"customer_mobile": {"$regex": digits}})
        ors.append({"bill_number": {"$regex": q, "$options": "i"}})
        ors.append({"transaction_id": {"$regex": q, "$options": "i"}})
        m["$or"] = ors
    return m


async def _load_stores() -> Dict[str, Dict[str, Any]]:
    """Bounded store master (id → {name, code, region, city})."""
    out: Dict[str, Dict[str, Any]] = {}
    async for s in stores_col.find({}, {"_id": 0, "id": 1, "code": 1, "name": 1,
                                        "region": 1, "city": 1}):
        if s.get("id"):
            out[s["id"]] = s
    return out


async def _customer_map(mobiles: List[str]) -> Dict[str, Dict[str, Any]]:
    if not mobiles:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    cur = customers_col.find(
        {"mobile": {"$in": mobiles}},
        {"_id": 0, "mobile": 1, "name": 1, "city": 1, "last_visit_at": 1,
         "visit_count": 1, "lifetime_spend": 1, "registered_store_id": 1,
         "home_store_id": 1},
    )
    async for c in cur:
        out[c["mobile"]] = c
    return out


async def _visit_map(mobiles: List[str], timeout_s: Optional[int] = None) -> Dict[str, Dict[str, Any]]:
    """Per-mobile: distinct visit DAYS (for last + 2nd-last visit) and the NET
    lifetime bill-cut count (sale bills − return bills) across ALL history."""
    if not mobiles:
        return {}
    pipe = [
        {"$match": {"customer_mobile": {"$in": mobiles}}},
        {"$group": {
            "_id": "$customer_mobile",
            "days": {"$addToSet": {"$dateToString": {
                "date": {"$convert": {"input": "$bill_date", "to": "date",
                                      "onError": None, "onNull": None}},
                "format": "%Y-%m-%d", "timezone": "Asia/Kolkata"}}},
            "sale": {"$sum": {"$cond": [{"$eq": ["$is_return", True]}, 0, 1]}},
            "ret": {"$sum": {"$cond": [{"$eq": ["$is_return", True]}, 1, 0]}},
            "paid": {"$sum": {"$cond": [
                {"$ne": [{"$ifNull": ["$net_amount_before_tax", None]}, None]},
                {"$add": ["$net_amount_before_tax", {"$ifNull": ["$tax_amount", 0]}]},
                {"$ifNull": ["$net_amount", 0]},
            ]}},
        }},
    ]
    out: Dict[str, Dict[str, Any]] = {}

    async def _run():
        async for r in transactions_col.aggregate(pipe, allowDiskUse=True):
            days_desc = sorted([d for d in (r.get("days") or []) if d], reverse=True)
            out[r["_id"]] = {
                "last": days_desc[0] if days_desc else None,
                "second": days_desc[1] if len(days_desc) > 1 else None,
                "days_asc": days_desc[::-1],   # ascending — for per-bill previous-visit lookup
                "sale": int(r.get("sale", 0)),                 # purchase (non-return) bills = "Total Visits"
                "net_cuts": int(r.get("sale", 0)) - int(r.get("ret", 0)),
                "paid": round(float(r.get("paid", 0) or 0), 2),
            }

    if timeout_s:
        with pymongo.timeout(timeout_s):
            await _run()
    else:
        await _run()
    return out


def _fmt_row(tx: Dict[str, Any], cust: Dict[str, Any], visit: Dict[str, Any],
             stores: Dict[str, Dict[str, Any]], now: datetime) -> Dict[str, Any]:
    bill_date = tx.get("bill_date") or ""
    store = stores.get(tx.get("store_id") or "", {})
    reg_store = stores.get((cust or {}).get("registered_store_id") or
                           (cust or {}).get("home_store_id") or "", {})

    bd_date, bd_time = _to_ist_parts(bill_date)
    # Per-bill recency = the shopper's status BEFORE this transaction. Find the visit
    # day immediately preceding this bill's day and measure the gap. "Last Visit" /
    # "2nd Last Visit" are shown RELATIVE to this bill (the previous visit, and the one
    # before that) so the row is self-consistent with its Recency label.
    days_asc = (visit or {}).get("days_asc") or []
    prev_day = prev_prev_day = None
    if bd_date and days_asc:
        idx = bisect.bisect_left(days_asc, bd_date)   # days_asc[:idx] are all < bd_date
        if idx >= 1:
            prev_day = days_asc[idx - 1]
        if idx >= 2:
            prev_prev_day = days_asc[idx - 2]
    recency = _recency_from_gap(bd_date, prev_day)
    net_before_tax = round(float(tx.get("net_amount_before_tax") or tx.get("net_amount") or 0), 2)
    total_tax = round(float(tx.get("tax_amount") or 0), 2)
    total_disc = round(float(tx.get("discount_amount") or tx.get("discount") or 0), 2)
    total_bill = tx.get("bill_with_tax")
    total_bill = round(float(total_bill), 2) if total_bill not in (None, "") else round(net_before_tax + total_tax, 2)

    return {
        "bill_date": bd_date,
        "bill_time": bd_time,
        "bill_type": "Return" if tx.get("is_return") else "Regular",
        "customer_mobile": tx.get("customer_mobile") or "",
        "reg_store": reg_store.get("name") or reg_store.get("code") or "",
        "store_code": tx.get("store_code") or store.get("code") or "",
        "trans_store_name": tx.get("store_name") or store.get("name") or "",
        "transaction_id": tx.get("transaction_id") or "",
        "bill_number": tx.get("bill_number") or "",
        "customer_type": tx.get("new_or_existing") or "",
        "recency": recency,
        "last_visit": prev_day or "",
        "second_last_visit": prev_prev_day or "",
        # Total Visits = number of PURCHASE (non-return) bills, computed live from the
        # bill data so it matches Customer 360 (the stored visit_count counted returns
        # too and could be stale → the "11 vs 12" mismatch).
        "total_visits": (visit or {}).get("sale") if visit else ((cust or {}).get("visit_count") if cust else ""),
        "zone": tx.get("zone") or store.get("region") or "",
        "store_class": tx.get("store_class") or store.get("store_class") or "",
        "customer_city": (cust or {}).get("city") or tx.get("city") or "",
        "net_before_tax": net_before_tax,
        "total_tax": total_tax,
        "total_discount": total_disc,
        "total_bill_amount": total_bill,
        "lifetime_purchase": (visit or {}).get("paid", "") if visit else "",
        "lifetime_bill_cuts": (visit or {}).get("net_cuts", "") if visit else "",
    }


async def _enrich(raw: List[Dict[str, Any]], stores: Dict[str, Dict[str, Any]],
                  now: datetime, timeout_s: Optional[int] = None) -> List[Dict[str, Any]]:
    mobiles = sorted({t.get("customer_mobile") for t in raw if t.get("customer_mobile")})
    cust = await _customer_map(mobiles)
    visit = await _visit_map(mobiles, timeout_s=timeout_s)
    return [_fmt_row(t, cust.get(t.get("customer_mobile") or ""), visit.get(t.get("customer_mobile") or ""),
                     stores, now) for t in raw]


# ============================================================
# Listing (paginated)
# ============================================================
@router.get("/bills")
async def shopper_bills(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    bill_type: Optional[str] = None,        # all | return | regular
    customer_type: Optional[str] = None,    # all | new | existing
    recency: Optional[str] = None,          # all | active | dormant | lapsed
    store_id: Optional[str] = None,
    zone: Optional[str] = None,
    city: Optional[str] = None,
    q: Optional[str] = None,
    sort_by: str = "bill_date",
    sort_dir: str = "desc",
    limit: int = Query(50, le=500),
    offset: int = 0,
    user: dict = Depends(get_current_user),
):
    now = _now_utc()
    match = _build_match(start_date, end_date, bill_type, customer_type, store_id, zone, city, q)
    sort_field = SORT_FIELDS.get(sort_by, "bill_date")
    direction = pymongo.ASCENDING if sort_dir == "asc" else pymongo.DESCENDING
    stores = await _load_stores()

    recency = (recency or "").lower()
    if recency in {"active", "dormant", "lapsed"}:
        # Per-bill recency (the shopper's status BEFORE the bill) can't be pre-filtered
        # by a simple index range, so we STREAM the matched bills in sorted order,
        # enrich them in batches (each batch computes the per-bill recency), keep only
        # the rows whose computed bucket matches, and stop as soon as the requested page
        # is filled. The user's date range + store/zone/city filters bound the scan.
        # Exact total is omitted for this path — pagination uses "has more".
        collected: List[Dict[str, Any]] = []
        skipped = 0
        scanned = 0
        SCAN_CAP = 200_000
        batch: List[Dict[str, Any]] = []

        async def _sift(rows_in: List[Dict[str, Any]]) -> bool:
            nonlocal skipped
            for fr in await _enrich(rows_in, stores, now, timeout_s=30):
                if _recency_bucket(fr.get("recency", "")) != recency:
                    continue
                if skipped < offset:
                    skipped += 1
                    continue
                collected.append(fr)
                if len(collected) > limit:
                    return True   # have limit+1 → know there's a next page
            return False

        try:
            cursor = transactions_col.find(match, {"_id": 0}).sort(
                sort_field, direction).max_time_ms(40000)
            stop = False
            async for tx in cursor:
                batch.append(tx)
                scanned += 1
                if len(batch) >= ENRICH_BATCH:
                    if await _sift(batch):
                        stop = True
                        break
                    batch = []
                    if scanned >= SCAN_CAP:
                        break
            if not stop and batch:
                await _sift(batch)
        except PyMongoError:
            raise HTTPException(
                status_code=400,
                detail="The recency filter needs a narrower date range (or add a "
                       "store / zone / city filter) — too many bills to scan at once.")

        has_more = len(collected) > limit
        rows = collected[:limit]
        return {"total": None, "rows": rows,
                "offset": offset, "limit": limit, "has_more": has_more,
                "columns": [{"key": k, "label": l} for k, l in COLUMNS]}

    total = await transactions_col.count_documents(match, maxTimeMS=40000)
    raw = await transactions_col.find(match, {"_id": 0}).sort(
        sort_field, direction).skip(offset).limit(limit).to_list(limit)

    rows = await _enrich(raw, stores, now)
    return {"total": total, "rows": rows, "offset": offset, "limit": limit,
            "has_more": offset + len(rows) < total,
            "columns": [{"key": k, "label": l} for k, l in COLUMNS]}


@router.get("/filter-options")
async def filter_options(user: dict = Depends(get_current_user)):
    stores = []
    zones = set()
    async for s in stores_col.find({}, {"_id": 0, "id": 1, "code": 1, "name": 1, "region": 1}).limit(1000):
        stores.append({"id": s.get("id"), "code": s.get("code"), "name": s.get("name")})
        if s.get("region"):
            zones.add(s["region"])
    stores.sort(key=lambda x: (x.get("name") or x.get("code") or "").lower())
    return {"stores": stores, "zones": sorted(zones)}


# ============================================================
# CSV export (streamed, uncapped request deadline)
# ============================================================
@export_router.get("/export")
async def export_csv(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    bill_type: Optional[str] = None,
    customer_type: Optional[str] = None,
    recency: Optional[str] = None,
    store_id: Optional[str] = None,
    zone: Optional[str] = None,
    city: Optional[str] = None,
    q: Optional[str] = None,
    sort_by: str = "bill_date",
    sort_dir: str = "desc",
    user: dict = Depends(get_current_user),
):
    now = _now_utc()
    match = _build_match(start_date, end_date, bill_type, customer_type, store_id, zone, city, q)
    sort_field = SORT_FIELDS.get(sort_by, "bill_date")
    direction = pymongo.ASCENDING if sort_dir == "asc" else pymongo.DESCENDING
    recency_f = (recency or "").lower()
    keep_recency = recency_f if recency_f in {"active", "dormant", "lapsed"} else None
    keys = [k for k, _ in COLUMNS]

    async def _gen():
        stores = await _load_stores()
        header_buf = io.StringIO()
        w = csv.writer(header_buf)
        w.writerow([label for _, label in COLUMNS])
        yield header_buf.getvalue()

        written = 0
        batch: List[Dict[str, Any]] = []

        async def _emit(rows: List[Dict[str, Any]]) -> str:
            nonlocal written
            out = io.StringIO()
            ww = csv.writer(out)
            formatted = await _enrich(rows, stores, now, timeout_s=30)
            for fr in formatted:
                if keep_recency:
                    # Recency label → bucket key; skip rows outside the chosen bucket.
                    if _recency_bucket(fr.get("recency", "")) != keep_recency:
                        continue
                ww.writerow([fr.get(k, "") for k in keys])
                written += 1
            return out.getvalue()

        with pymongo.timeout(60):
            cursor = transactions_col.find(match, {"_id": 0}).sort(sort_field, direction)
        async for tx in cursor:
            batch.append(tx)
            if len(batch) >= ENRICH_BATCH:
                yield await _emit(batch)
                batch = []
                if written >= EXPORT_MAX_ROWS:
                    break
        if batch and written < EXPORT_MAX_ROWS:
            yield await _emit(batch)

    fname = f"shopper_bill_report_{now.date().isoformat()}.csv"
    return StreamingResponse(_gen(), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})
