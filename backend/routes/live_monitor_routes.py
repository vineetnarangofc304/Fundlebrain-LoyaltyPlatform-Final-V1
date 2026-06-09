"""Live Monitor — real-time cockpit data for ALL bills/transactions.

Powers `/enterprise/live-monitor` and serves as a strong report dashboard.
Bills WITH mobile = green; bills WITHOUT mobile = red "Lost Opportunity".
"""
from __future__ import annotations
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from database import transactions_col, customers_col, stores_col
from auth import require_roles

router = APIRouter(prefix="/live-monitor", tags=["live-monitor"])


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


# KAZO operates in IST; "today" for recalc means the current IST calendar day.
IST_TZ = timezone(timedelta(hours=5, minutes=30))


@router.get("/transactions")
async def live_transactions(
    limit: int = Query(200, ge=1, le=2000),
    since: Optional[str] = Query(None, description="ISO timestamp — return only newer bills"),
    since_minutes: Optional[int] = Query(None, ge=1, le=525600,
        description="Convenience window in minutes (1 = 1 min, 1440 = 1d, up to 365d)."
        " Overrides `since` if both given."),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD — date range start (overrides since_minutes)"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD — date range end (inclusive)"),
    store_id: Optional[str] = None,
    store_code: Optional[str] = None,
    city: Optional[str] = None,
    zone: Optional[str] = None,
    region: Optional[str] = None,
    has_mobile: Optional[str] = Query(None, description="all | yes | no — filter by mobile presence"),
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    payment_mode: Optional[str] = None,
    source: Optional[str] = Query(None, description="pos_ewards | historic_upload | etc"),
    is_return: Optional[bool] = None,
    user: dict = Depends(require_roles("super_admin", "brand_admin", "crm_manager",
                                         "marketing_manager", "regional_manager",
                                         "analytics_viewer", "readonly_executive")),
):
    """Paginated list of recent transactions for the cockpit table."""
    fil: dict = {}
    if start_date or end_date:
        # Explicit date range wins over the relative window
        dr: dict = {}
        if start_date:
            dr["$gte"] = start_date
        if end_date:
            dr["$lte"] = end_date + "T23:59:59.999Z"
        fil["bill_date"] = dr
    elif since_minutes:
        # Compute cutoff so the table matches whatever Stats Window the
        # frontend is using — keeps the KPI strip and the row list consistent.
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=since_minutes)).isoformat()
        fil["bill_date"] = {"$gte": cutoff}
    elif since:
        fil["bill_date"] = {"$gt": since}
    if store_id:
        fil["store_id"] = store_id
    if store_code:
        s = await stores_col.find_one({"code": store_code}, {"_id": 0, "id": 1})
        if s:
            fil["store_id"] = s["id"]
    if city:
        fil["city"] = city
    if zone:
        fil["zone"] = zone
    if source:
        fil["source"] = source
    if is_return is not None:
        fil["is_return"] = is_return
    if has_mobile == "yes":
        fil["customer_mobile"] = {"$exists": True, "$nin": [None, ""]}
    elif has_mobile == "no":
        fil["$or"] = [
            {"customer_mobile": {"$in": [None, ""]}},
            {"customer_mobile": {"$exists": False}},
        ]
    if min_amount is not None or max_amount is not None:
        amt_fil: dict = {}
        if min_amount is not None:
            amt_fil["$gte"] = min_amount
        if max_amount is not None:
            amt_fil["$lte"] = max_amount
        fil["net_amount"] = amt_fil
    if payment_mode:
        fil["payment_mode"] = payment_mode

    # Region filter: resolve via stores
    if region:
        store_ids = [s["id"] async for s in stores_col.find({"region": region}, {"_id": 0, "id": 1})]
        fil["store_id"] = {"$in": store_ids}

    rows = await transactions_col.find(fil, {"_id": 0}).sort("bill_date", -1).limit(limit).to_list(limit)

    # Enrich with customer name (best-effort batch)
    mobiles = list({r.get("customer_mobile") for r in rows if r.get("customer_mobile")})
    cust_map = {}
    if mobiles:
        async for c in customers_col.find({"mobile": {"$in": mobiles}},
                                            {"_id": 0, "mobile": 1, "name": 1, "tier": 1,
                                             "points_balance": 1, "first_purchase_at": 1,
                                             "visit_count": 1}):
            cust_map[c["mobile"]] = c

    # Resolve LOC code (store_code) + canonical store name/city/zone from the store
    # master so the cockpit's "Loc Code" column is populated even for bills ingested
    # before store_code was persisted on the transaction (live POS bills + history).
    store_ids = list({r.get("store_id") for r in rows if r.get("store_id")})
    store_map = {}
    if store_ids:
        async for s in stores_col.find({"id": {"$in": store_ids}},
                                        {"_id": 0, "id": 1, "code": 1, "name": 1,
                                         "city": 1, "region": 1}):
            store_map[s["id"]] = s

    enriched = []
    for r in rows:
        mob = r.get("customer_mobile")
        c = cust_map.get(mob) if mob else None
        st = store_map.get(r.get("store_id")) or {}
        # Derive customer_status: walk-in (no mobile) vs new (first ever bill)
        # vs repeat (had earlier bills). "first ever" means this row's bill_date
        # equals the customer's first_purchase_at (same calendar date).
        customer_status = "walk_in"
        if c:
            bill_d = (r.get("bill_date") or "")[:10]
            first_d = (c.get("first_purchase_at") or "")[:10]
            if first_d and bill_d and first_d == bill_d:
                customer_status = "new"
            elif (c.get("visit_count") or 0) <= 1:
                customer_status = "new"
            else:
                customer_status = "repeat"
        elif mob:
            # has mobile but no master record yet — treat as new lead
            customer_status = "new"
        enriched.append({
            "id": r.get("id"),
            "bill_number": r.get("bill_number"),
            "bill_date": r.get("bill_date"),
            "received_at": r.get("created_at"),
            "store_id": r.get("store_id"),
            "store_name": r.get("store_name") or st.get("name"),
            "store_code": r.get("store_code") or st.get("code"),
            "city": r.get("city") or st.get("city"),
            "zone": r.get("zone") or st.get("region"),
            "customer_mobile": mob,
            "customer_name": r.get("customer_name") or (c.get("name") if c else None),
            "tier": (c.get("tier") if c else None) or r.get("tier"),
            "current_points": (c.get("points_balance") if c else None),
            "customer_status": customer_status,
            "gross_amount": r.get("gross_amount"),
            "net_amount": r.get("net_amount"),
            "final_amount": r.get("final_amount"),
            "amount": r.get("amount"),
            "points_base": r.get("loyalty_gross_amount", r.get("amount")),
            "tax_amount": r.get("tax_amount", r.get("loyalty_tax_amount")),
            "bill_with_tax": r.get("bill_with_tax"),
            "discount_amount": r.get("discount_amount"),
            "points_earned": r.get("points_earned", 0),
            "points_redeemed": r.get("points_redeemed", 0),
            "payment_mode": r.get("payment_mode"),
            "is_return": r.get("is_return", False),
            "source": r.get("source"),
            "items_count": len(r.get("items") or []),
            "has_mobile": bool(mob),
            "lost_opportunity": not bool(mob),
            "is_lost_customer": bool(r.get("is_lost_customer")),
            "raw_mobile": r.get("raw_mobile"),
        })
    return {"rows": enriched, "count": len(enriched), "as_of": _now_iso()}


@router.get("/stats")
async def live_stats(
    minutes: int = Query(60, ge=1, le=525600),  # up to 365 days (1 year)
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD — date range start (overrides minutes)"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD — date range end (inclusive)"),
    user: dict = Depends(require_roles("super_admin", "brand_admin", "crm_manager",
                                         "marketing_manager", "regional_manager",
                                         "analytics_viewer", "readonly_executive")),
):
    """Top KPIs for the cockpit: bills, revenue, mobile-attach rate, lost opportunities."""
    if start_date or end_date:
        dr: dict = {}
        if start_date:
            dr["$gte"] = start_date
        if end_date:
            dr["$lte"] = end_date + "T23:59:59.999Z"
        date_match = {"bill_date": dr}
    else:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
        date_match = {"bill_date": {"$gte": cutoff}}
    pipe_total = [
        {"$match": dict(date_match)},
        {"$group": {
            "_id": None,
            "bills": {"$sum": 1},
            # Total Purchase = GROSS SALES (gross_amount = MRP/billed value), returns
            # EXCLUDED (they're surfaced in the separate Returns KPI) so Total Purchase
            # stays a clean superset of Loyalty Purchase.
            "revenue": {"$sum": {"$cond": ["$is_return", 0, "$gross_amount"]}},
            "bills_with_mobile": {
                "$sum": {"$cond": [
                    {"$and": [{"$ne": ["$customer_mobile", None]},
                                {"$ne": ["$customer_mobile", ""]}]},
                    1, 0,
                ]}
            },
            "revenue_with_mobile": {
                "$sum": {"$cond": [
                    {"$and": [{"$not": ["$is_return"]},
                                {"$ne": ["$customer_mobile", None]},
                                {"$ne": ["$customer_mobile", ""]}]},
                    "$gross_amount", 0,
                ]}
            },
            # Loyalty Purchase = gross purchase value of (non-return) bills on which
            # points WERE given (points_earned > 0) — same gross basis as Total Purchase.
            "loyalty_revenue": {
                "$sum": {"$cond": [
                    {"$and": [{"$not": ["$is_return"]},
                                {"$gt": ["$points_earned", 0]}]},
                    "$gross_amount", 0,
                ]}
            },
            "points_earned": {"$sum": "$points_earned"},
            "points_redeemed": {"$sum": "$points_redeemed"},
            "returns": {"$sum": {"$cond": ["$is_return", 1, 0]}},
        }},
    ]
    res = await transactions_col.aggregate(pipe_total).to_list(1)
    base = res[0] if res else {}
    bills = base.get("bills", 0) or 0
    with_mob = base.get("bills_with_mobile", 0) or 0
    lost = bills - with_mob
    revenue = float(base.get("revenue") or 0)
    rev_with = float(base.get("revenue_with_mobile") or 0)
    loyalty_rev = float(base.get("loyalty_revenue") or 0)
    attach_rate = (with_mob / bills * 100) if bills else 0.0

    # Repeat bills — bills whose customer_mobile appears 2+ times in the window
    repeat_pipe = [
        {"$match": {**date_match,
                     "customer_mobile": {"$nin": [None, ""]}}},
        {"$group": {"_id": "$customer_mobile", "n": {"$sum": 1}}},
        {"$match": {"n": {"$gte": 2}}},
        {"$group": {"_id": None,
                     "repeat_customers": {"$sum": 1},
                     "repeat_bills": {"$sum": "$n"}}},
    ]
    rr = await transactions_col.aggregate(repeat_pipe).to_list(1)
    rr_doc = rr[0] if rr else {}
    repeat_bills = int(rr_doc.get("repeat_bills") or 0)
    repeat_customers = int(rr_doc.get("repeat_customers") or 0)

    # Per-store top performers — exclude bills with no store_id (returns/anonymous
    # bills lacking a store were lumping into an "Unknown" card with negative revenue).
    # Revenue here = SALES only (returns excluded) so "Top stores by revenue" reads clean.
    pipe_store = [
        {"$match": {**date_match, "store_id": {"$nin": [None, ""]}}},
        {"$group": {
            "_id": "$store_id",
            "store_name": {"$first": "$store_name"},
            "bills": {"$sum": 1},
            "revenue": {"$sum": {"$cond": ["$is_return", 0, "$net_amount"]}},
            "returns": {"$sum": {"$cond": ["$is_return", 1, 0]}},
            "bills_with_mobile": {
                "$sum": {"$cond": [
                    {"$and": [{"$ne": ["$customer_mobile", None]},
                                {"$ne": ["$customer_mobile", ""]}]},
                    1, 0,
                ]}
            },
        }},
        {"$sort": {"revenue": -1}},
        {"$limit": 10},
    ]
    by_store = await transactions_col.aggregate(pipe_store).to_list(10)
    # Resolve LOC code + canonical name from the store master (txn store_name can be
    # blank/inconsistent).
    bs_ids = [s.get("_id") for s in by_store if s.get("_id")]
    bs_map = {}
    if bs_ids:
        async for s in stores_col.find({"id": {"$in": bs_ids}},
                                        {"_id": 0, "id": 1, "code": 1, "name": 1}):
            bs_map[s["id"]] = s

    return {
        "window_minutes": minutes,
        "as_of": _now_iso(),
        "bills_total": bills,
        "bills_with_mobile": with_mob,
        "bills_without_mobile": lost,
        "repeat_bills": repeat_bills,
        "repeat_customers": repeat_customers,
        "mobile_attach_rate_pct": round(attach_rate, 2),
        "revenue_total": round(revenue, 2),
        "revenue_with_mobile": round(rev_with, 2),
        "loyalty_revenue": round(loyalty_rev, 2),
        "revenue_lost": round(revenue - rev_with, 2),
        "points_earned": int(base.get("points_earned") or 0),
        "points_redeemed": int(base.get("points_redeemed") or 0),
        "returns": int(base.get("returns") or 0),
        "by_store_top10": [
            {
                "store_id": s.get("_id"),
                "store_name": (bs_map.get(s.get("_id")) or {}).get("name") or s.get("store_name") or "Unknown",
                "store_code": (bs_map.get(s.get("_id")) or {}).get("code"),
                "bills": s.get("bills", 0),
                "revenue": round(s.get("revenue", 0) or 0, 2),
                "returns": int(s.get("returns") or 0),
                "bills_with_mobile": s.get("bills_with_mobile", 0),
                "attach_rate_pct": round(
                    (s.get("bills_with_mobile", 0) / s.get("bills", 1) * 100) if s.get("bills") else 0,
                    2,
                ),
            } for s in by_store
        ],
    }


# ---------------- Recalculate points (backfill for bills that earned 0) ----------------
class RecalcBody(BaseModel):
    dry_run: bool = True            # preview counts before applying
    store_id: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    limit: int = 20000
    ignore_loyalty_flag: bool = False  # backfill bills wrongly stored as flag-off by older code


@router.post("/recalc-points")
async def recalc_points(
    body: RecalcBody = RecalcBody(),
    user: dict = Depends(require_roles("super_admin", "brand_admin")),
):
    """Re-credit loyalty points for SALE bills that currently have 0 points but should
    have earned (e.g. bills captured before the earn-engine fix). Idempotent: once a
    bill is credited its points_earned > 0, so it is skipped on subsequent runs.
    Call with dry_run=true first to preview; dry_run=false applies + writes ledger."""
    from database import db
    from routes.pos_ewards_routes import _compute_earn_points
    points_ledger_col = db["points_ledger"]
    loyalty_config_col = db["loyalty_config"]

    cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0}) or {}
    min_bill = float(cfg.get("min_bill_for_earn", 0) or 0)
    tier_mult = {t.get("tier"): t.get("earn_multiplier", 1.0) for t in (cfg.get("tier_rules") or [])}

    # RECALC is scoped to LIVE POS bills ONLY (source=pos_ewards): historic-upload bills
    # get their points via opening balances and must never be touched by recalc. It also
    # defaults to TODAY (IST) — recalc only back-credits the current day's live bills per
    # the configured earn rules, so it can never re-touch older / historic data.
    fil: dict = {"is_return": {"$ne": True},
                 "source": "pos_ewards",
                 "$or": [{"points_earned": {"$lte": 0}}, {"points_earned": None}]}
    if body.store_id:
        fil["store_id"] = body.store_id
    start_date = body.start_date
    end_date = body.end_date
    if not start_date and not end_date:
        start_date = end_date = datetime.now(IST_TZ).strftime("%Y-%m-%d")  # today, IST
    dr: dict = {}
    if start_date:
        dr["$gte"] = start_date
    if end_date:
        dr["$lte"] = end_date + "T23:59:59.999Z"
    fil["bill_date"] = dr

    scanned = eligible = credited = total_points = 0
    skipped = {"loyalty_flag_off": 0, "below_min_or_zero_base": 0,
               "customer_not_found": 0, "computed_zero_rate": 0}
    samples: List[dict] = []
    async for t in transactions_col.find(fil, {"_id": 0}).limit(body.limit):
        scanned += 1
        if not body.ignore_loyalty_flag and \
                str(t.get("loyalty_flag", "1")).strip().lower() in {"0", "false", "no", "n", "off"}:
            skipped["loyalty_flag_off"] += 1
            continue
        base = float(t.get("loyalty_gross_amount") or t.get("amount")
                     or t.get("net_amount") or t.get("final_amount") or 0)
        if base <= 0 or base < min_bill:
            skipped["below_min_or_zero_base"] += 1
            continue
        cust = None
        if t.get("customer_id"):
            cust = await customers_col.find_one({"id": t["customer_id"]}, {"_id": 0, "id": 1, "tier": 1})
        if not cust and t.get("customer_mobile"):
            cust = await customers_col.find_one({"mobile": t["customer_mobile"]}, {"_id": 0, "id": 1, "tier": 1})
        if not cust:
            skipped["customer_not_found"] += 1
            continue
        mult = tier_mult.get(cust.get("tier") or "silver", 1.0)
        pts = _compute_earn_points(base, cfg, mult)
        if pts <= 0:
            skipped["computed_zero_rate"] += 1
            continue
        eligible += 1
        total_points += pts
        if len(samples) < 10:
            samples.append({"bill_number": t.get("bill_number"), "base": base,
                            "points": pts, "mobile": t.get("customer_mobile")})
        if not body.dry_run:
            await transactions_col.update_one({"id": t["id"]}, {"$set": {"points_earned": pts}})
            await customers_col.update_one({"id": cust["id"]},
                {"$inc": {"points_balance": pts, "lifetime_points_earned": pts}})
            await points_ledger_col.insert_one({
                "id": uuid.uuid4().hex, "customer_id": cust["id"], "type": "earn",
                "points": pts, "reference_type": "recalc", "reference_id": t.get("id"),
                "note": f"Points recalculated for bill {t.get('bill_number')}",
                "created_at": _now_iso(),
            })
            credited += 1
    return {"dry_run": body.dry_run, "scanned": scanned, "eligible": eligible,
            "credited": credited, "total_points": total_points, "samples": samples,
            "skipped": skipped, "min_bill_for_earn": min_bill,
            "source": "pos_ewards", "window": {"start": start_date, "end": end_date},
            "earn_mode": cfg.get("earn_mode") or "points_per_spend",
            "earn_ratio": cfg.get("earn_ratio"), "percent_of_spend": cfg.get("percent_of_spend"),
            "ignore_loyalty_flag": body.ignore_loyalty_flag}



# ---------------- POS Credentials (admin-only) ----------------
admin_router = APIRouter(prefix="/admin/pos-credentials", tags=["pos-credentials-admin"])


class POSCredCreate(BaseModel):
    label: str
    merchant_id: str
    customer_key: str
    store_id: Optional[str] = None
    note: Optional[str] = None


@admin_router.get("")
async def list_pos_credentials(
    user: dict = Depends(require_roles("super_admin", "brand_admin")),
):
    from database import db
    rows = await db["pos_credentials"].find({}, {"_id": 0}).sort("created_at", -1).to_list(50)
    return {"credentials": rows}


@admin_router.post("")
async def create_pos_credential(
    body: POSCredCreate,
    user: dict = Depends(require_roles("super_admin", "brand_admin")),
):
    from database import db
    if await db["pos_credentials"].find_one({"label": body.label, "is_active": True}):
        raise HTTPException(400, "Label already in use for an active credential")
    api_key = secrets.token_urlsafe(32)
    doc = {
        "id": uuid.uuid4().hex,
        "label": body.label,
        "merchant_id": body.merchant_id,
        "customer_key": body.customer_key,
        "store_id": body.store_id,
        "api_key": api_key,
        "note": body.note,
        "is_active": True,
        "created_at": _now_iso(),
        "created_by": user.get("email"),
    }
    await db["pos_credentials"].insert_one(doc)
    doc.pop("_id", None)
    return doc


@admin_router.post("/{cred_id}/rotate")
async def rotate_pos_credential(cred_id: str,
                                  user: dict = Depends(require_roles("super_admin", "brand_admin"))):
    from database import db
    new_key = secrets.token_urlsafe(32)
    res = await db["pos_credentials"].update_one(
        {"id": cred_id},
        {"$set": {"api_key": new_key, "rotated_at": _now_iso(),
                   "rotated_by": user.get("email")}},
    )
    if not res.matched_count:
        raise HTTPException(404, "Credential not found")
    return await db["pos_credentials"].find_one({"id": cred_id}, {"_id": 0})


class POSCredSetKey(BaseModel):
    api_key: str


@admin_router.post("/{cred_id}/set-key")
async def set_pos_credential_key(cred_id: str, body: POSCredSetKey,
                                  user: dict = Depends(require_roles("super_admin", "brand_admin"))):
    """Set a SPECIFIC x-api-key (e.g. the key already provisioned at the POS /
    stores) instead of rotating to a random one. Activates the credential and
    makes /api/pos/* authenticate against this exact key immediately.
    """
    from database import db
    key = (body.api_key or "").strip()
    if len(key) < 16:
        raise HTTPException(400, "x-api-key must be at least 16 characters")
    # Block reusing a key that already belongs to a DIFFERENT credential.
    clash = await db["pos_credentials"].find_one({"api_key": key, "id": {"$ne": cred_id}})
    if clash:
        raise HTTPException(400, "This x-api-key is already used by another credential")
    res = await db["pos_credentials"].update_one(
        {"id": cred_id},
        {"$set": {"api_key": key, "is_active": True,
                   "rotated_at": _now_iso(), "rotated_by": user.get("email")}},
    )
    if not res.matched_count:
        raise HTTPException(404, "Credential not found")
    return await db["pos_credentials"].find_one({"id": cred_id}, {"_id": 0})


@admin_router.post("/{cred_id}/deactivate")
async def deactivate_pos_credential(cred_id: str,
                                       user: dict = Depends(require_roles("super_admin", "brand_admin"))):
    from database import db
    res = await db["pos_credentials"].update_one(
        {"id": cred_id},
        {"$set": {"is_active": False, "deactivated_at": _now_iso(),
                   "deactivated_by": user.get("email")}},
    )
    if not res.matched_count:
        raise HTTPException(404, "Credential not found")
    return {"ok": True}


# ---------------- API Logs viewer (full request + response, admin only) ----------------
log_router = APIRouter(prefix="/api-monitor", tags=["api-monitor-detail"])


@log_router.get("/log/{log_id}")
async def get_api_log_detail(log_id: str,
                              user: dict = Depends(require_roles("super_admin", "brand_admin",
                                                                   "crm_manager", "marketing_manager"))):
    from database import api_logs_col
    row = await api_logs_col.find_one({"id": log_id}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Log not found")
    return row


@log_router.get("/logs")
async def list_api_logs(
    limit: int = Query(100, le=500),
    endpoint: Optional[str] = None,
    status_code: Optional[int] = None,
    method: Optional[str] = None,
    customer_mobile: Optional[str] = None,
    bill_number: Optional[str] = None,
    source: Optional[str] = None,
    since: Optional[str] = None,
    user: dict = Depends(require_roles("super_admin", "brand_admin",
                                         "crm_manager", "marketing_manager")),
):
    from database import api_logs_col
    fil: dict = {}
    if endpoint:
        fil["endpoint"] = endpoint
    if status_code is not None:
        fil["status_code"] = status_code
    if method:
        fil["method"] = method.upper()
    if customer_mobile:
        fil["customer_mobile"] = customer_mobile
    if bill_number:
        fil["bill_number"] = bill_number
    if source:
        fil["source"] = source
    if since:
        fil["timestamp"] = {"$gte": since}
    rows = await api_logs_col.find(fil, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    return {"rows": rows, "count": len(rows)}
