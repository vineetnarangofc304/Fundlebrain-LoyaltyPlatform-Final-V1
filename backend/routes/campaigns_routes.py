"""Campaign manager."""
import asyncio
import random
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
import pymongo
from fastapi import APIRouter, Depends, HTTPException
from database import (
    campaigns_col, customers_col, transactions_col, coupon_redemptions_col, db,
)
from routes._money import NET_EXPR
from auth import get_current_user, require_roles, log_audit, MANAGEMENT_ROLES
from models import CampaignCreate, Campaign

router = APIRouter(prefix="/campaigns", tags=["campaigns"])

campaign_datasets_col = db["campaign_datasets"]   # frozen targeted-mobile snapshot per campaign
items_col = db["items"]                            # SKU master (sku, category, subcategory)


@router.get("")
async def list_campaigns(status: Optional[str] = None, user: dict = Depends(get_current_user)):
    fil = {}
    if status:
        fil["status"] = status
    items = await campaigns_col.find(fil, {"_id": 0}).sort("created_at", -1).limit(500).to_list(500)
    return items


@router.post("", response_model=Campaign)
async def create_campaign(payload: CampaignCreate, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    doc = payload.model_dump()
    if isinstance(doc.get("schedule_at"), datetime):
        doc["schedule_at"] = doc["schedule_at"].isoformat()
    doc["id"] = uuid.uuid4().hex
    doc["sent"] = 0
    doc["delivered"] = 0
    doc["opened"] = 0
    doc["clicked"] = 0
    doc["redeemed"] = 0
    doc["revenue_generated"] = 0.0
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["created_by"] = user["id"]
    await campaigns_col.insert_one(doc)
    await log_audit(user, "create_campaign", "campaign", doc["id"], {"name": doc["name"]})
    doc.pop("_id", None)
    return doc


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: str, user: dict = Depends(get_current_user)):
    c = await campaigns_col.find_one({"id": campaign_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Campaign not found")
    return c


@router.post("/{campaign_id}/preview-audience")
async def preview_audience(campaign_id: str, user: dict = Depends(get_current_user)):
    c = await campaigns_col.find_one({"id": campaign_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Campaign not found")
    fil = await _audience_filter_async(c)
    total = await customers_col.count_documents(fil)
    sample = await customers_col.find(fil, {"_id": 0, "mobile": 1, "name": 1, "tier": 1, "city": 1}).limit(20).to_list(20)
    return {"total_audience": total, "sample": sample}


def _audience_filter(c: dict) -> dict:
    fil = {}
    # NEW: segment-builder audience — compile the saved segment's filter tree
    if c.get("audience_type") == "segment" and (c.get("audience_filter") or {}).get("segment_id"):
        # Compiled-tree lookup happens at launch via async helper below
        return {}
    af = c.get("audience_filter") or {}
    if c.get("audience_type") == "tier" and af.get("tier"):
        fil["tier"] = af["tier"]
    if c.get("audience_type") == "city" and af.get("city"):
        fil["city"] = af["city"]
    if c.get("audience_type") == "cohort":
        cohort = af.get("cohort", "")
        if cohort == "high_value":
            fil["lifetime_spend"] = {"$gte": 50000}
        elif cohort == "churn_risk":
            fil["churn_risk"] = {"$in": ["medium", "high"]}
        elif cohort == "new":
            fil["visit_count"] = {"$lte": 1}
        elif cohort == "vip":
            fil["tier"] = {"$in": ["platinum", "diamond"]}
    return fil


async def _audience_filter_async(c: dict) -> dict:
    """Resolves audience filter — including segment-builder segments which
    require compiling a tree via segments_routes.compile_tree."""
    if c.get("audience_type") == "segment":
        seg_id = (c.get("audience_filter") or {}).get("segment_id")
        if seg_id:
            from database import db as _db
            from routes.segments_routes import compile_tree
            seg = await _db["segments"].find_one({"id": seg_id}, {"_id": 0})
            if seg:
                return await compile_tree(seg["tree"])
    return _audience_filter(c)


def _parse_window(w: Optional[str]) -> timedelta:
    """'72h' | '3d' | '5d' | '7d' | '30d' | '<n>h' | '<n>d' -> timedelta (default 7 days)."""
    m = re.fullmatch(r"\s*(\d+)\s*([hd])\s*", (w or "7d").lower())
    if not m:
        return timedelta(days=7)
    n, unit = int(m.group(1)), m.group(2)
    return timedelta(hours=n) if unit == "h" else timedelta(days=n)


async def _freeze_dataset(campaign_id: str, fil: dict, limit: int, t0: str) -> int:
    """Snapshot the exact targeted mobiles at launch so ROI is measured against a fixed
    dataset (not a live/moving filter). Capped at the send limit (max 50k, matching the
    bulk-send worker)."""
    cap = min(int(limit or 50000), 50000)
    with pymongo.timeout(120):
        rows = await customers_col.find(
            fil or {}, {"_id": 0, "mobile": 1}).limit(cap).to_list(cap)
    mobiles = sorted({(r.get("mobile") or "").strip() for r in rows if (r.get("mobile") or "").strip()})
    await campaign_datasets_col.replace_one(
        {"campaign_id": campaign_id},
        {"campaign_id": campaign_id, "mobiles": mobiles, "size": len(mobiles),
         "t0": t0, "frozen_at": datetime.now(timezone.utc).isoformat()},
        upsert=True)
    return len(mobiles)


@router.post("/{campaign_id}/launch")
async def launch_campaign(campaign_id: str, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    """Launch a campaign.

    - If the campaign has a `template_id` linking to an active comms template,
      we enqueue a REAL Karix bulk-send job (SMS / WhatsApp / RCS) and link
      the resulting `bulk_job_id` back onto the campaign.
    - If no template_id is set, we fall back to the legacy SIMULATED metrics
      mode so demo/preview campaigns still work.
    """
    c = await campaigns_col.find_one({"id": campaign_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Campaign not found")
    if c["status"] not in ("draft", "scheduled"):
        raise HTTPException(400, f"Campaign already {c['status']}")

    launched_at = datetime.now(timezone.utc).isoformat()
    fil = await _audience_filter_async(c)
    audience_size = await customers_col.count_documents(fil)
    send_limit = int(c.get("send_limit") or 50000)
    dataset_size = await _freeze_dataset(campaign_id, fil, send_limit, launched_at)

    template_id = c.get("template_id")
    if template_id:
        # ---------- REAL Karix bulk send path ----------
        from database import db as _db
        templates_col = _db["communication_templates"]
        bulk_jobs_col = _db["bulk_send_jobs"]
        from routes.communications_routes import _run_bulk_send_job

        t = await templates_col.find_one({"id": template_id}, {"_id": 0})
        if not t:
            raise HTTPException(400, "Linked template not found — clear template_id or pick another template")
        if t.get("status") != "active":
            raise HTTPException(400, "Template must be active to launch a real send")
        if t["channel"] in {"whatsapp", "rcs"}:
            if not t.get("waba_template_id"):
                raise HTTPException(400, "WhatsApp/RCS template requires waba_template_id")
            if t.get("waba_approval_status") != "approved":
                raise HTTPException(400, "WhatsApp/RCS template must be approved before launch")

        limit = send_limit
        job_id = uuid.uuid4().hex
        job_doc = {
            "id": job_id,
            "template_id": template_id,
            "template_name": t.get("name"),
            "channel": t["channel"],
            "audience_filter": fil,
            "audience_size_total": audience_size,
            "limit": limit,
            "status": "queued",
            "processed": 0, "sent": 0, "failed": 0,
            "queued_at": datetime.now(timezone.utc).isoformat(),
            "queued_by": user["email"],
            "source": "campaign",
            "campaign_id": campaign_id,
        }
        await bulk_jobs_col.insert_one(job_doc)

        # Fire-and-forget background task
        asyncio.create_task(_run_bulk_send_job(job_id, template_id, fil, limit, campaign_id))

        await campaigns_col.update_one(
            {"id": campaign_id},
            {"$set": {
                "status": "running",
                "launched_at": launched_at,
                "dataset_size": dataset_size,
                "bulk_job_id": job_id,
                "send_mode": "karix",
                "sent": 0, "delivered": 0, "opened": 0, "clicked": 0,
                "redeemed": 0, "revenue_generated": 0.0,
            }},
        )
        await log_audit(user, "launch_campaign", "campaign", campaign_id,
                          {"audience": audience_size, "bulk_job_id": job_id, "mode": "karix"})
        return {"success": True, "audience": audience_size, "bulk_job_id": job_id,
                 "mode": "karix", "channel": t["channel"]}

    # ---------- SIMULATED metrics path (fallback) ----------
    sent = audience_size
    delivered = int(sent * 0.94)
    opened = int(delivered * 0.42)
    clicked = int(opened * 0.18)
    redeemed = int(clicked * 0.25)
    revenue = redeemed * random.randint(1500, 4500)
    await campaigns_col.update_one(
        {"id": campaign_id},
        {"$set": {
            "status": "running",
            "launched_at": launched_at,
            "dataset_size": dataset_size,
            "send_mode": "simulated",
            "sent": sent, "delivered": delivered, "opened": opened, "clicked": clicked,
            "redeemed": redeemed, "revenue_generated": float(revenue),
        }}
    )
    await log_audit(user, "launch_campaign", "campaign", campaign_id,
                      {"audience": audience_size, "mode": "simulated"})
    return {"success": True, "audience": audience_size, "sent": sent, "mode": "simulated"}


@router.patch("/{campaign_id}")
async def update_campaign(campaign_id: str, updates: dict, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    if isinstance(updates.get("schedule_at"), datetime):
        updates["schedule_at"] = updates["schedule_at"].isoformat()
    await campaigns_col.update_one({"id": campaign_id}, {"$set": updates})
    await log_audit(user, "update_campaign", "campaign", campaign_id, updates)
    return await campaigns_col.find_one({"id": campaign_id}, {"_id": 0})


ROI_WINDOWS = ["72h", "3d", "5d", "7d", "14d", "30d"]


@router.get("/{campaign_id}/roi")
async def campaign_roi_detail(campaign_id: str, window: Optional[str] = None,
                              user: dict = Depends(get_current_user)):
    """Real ROI attribution for one campaign: of the FROZEN targeted dataset, who made a
    real bill within `window` of launch — with universal + objective-specific breakdowns
    (store-wise / coupon redemptions / target-SKU units & value)."""
    c = await campaigns_col.find_one({"id": campaign_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Campaign not found")
    ds = await campaign_datasets_col.find_one({"campaign_id": campaign_id}, {"_id": 0})
    t0 = c.get("launched_at") or (ds or {}).get("t0")
    if not ds or not t0:
        raise HTTPException(400, "Launch the campaign first — ROI is measured against the dataset frozen at launch")

    win = window or c.get("roi_window") or "7d"
    delta = _parse_window(win)
    t0_dt = datetime.fromisoformat(t0.replace("Z", "+00:00"))
    end_dt = t0_dt + delta
    t0_iso, end_iso = t0_dt.isoformat(), end_dt.isoformat()

    mobiles = ds.get("mobiles") or []
    size = len(mobiles)
    base_match = {
        "customer_mobile": {"$in": mobiles},
        "is_return": {"$ne": True},
        "bill_date": {"$gte": t0_iso, "$lte": end_iso},
    }

    # ---- Universal ROI: who came back and shopped ----
    urows = await transactions_col.aggregate([
        {"$match": base_match},
        {"$group": {"_id": "$customer_mobile", "rev": {"$sum": NET_EXPR}, "bills": {"$sum": 1}}},
    ], allowDiskUse=True, maxTimeMS=30000).to_list(200000)
    converters = len(urows)
    revenue = round(sum((r.get("rev") or 0) for r in urows), 2)
    bills = sum((r.get("bills") or 0) for r in urows)
    cost = c.get("cost")
    roi_pct = round((revenue - cost) / cost * 100, 1) if cost else None

    out: Dict[str, Any] = {
        "campaign_id": campaign_id, "name": c.get("name"),
        "objective": c.get("objective", "generic"),
        "window": win, "windows": ROI_WINDOWS, "t0": t0_iso, "window_end": end_iso,
        "dataset_size": size, "sent": c.get("sent") or size,
        "universal": {
            "converters": converters,
            "conversion_rate_pct": round(converters / size * 100, 2) if size else 0.0,
            "attributed_bills": bills,
            "attributed_net_revenue": revenue,
            "revenue_per_recipient": round(revenue / size, 2) if size else 0.0,
            "cost": cost, "roi_pct": roi_pct,
        },
    }

    params = c.get("objective_params") or {}

    # ---- Store-wise breakdown (always computed; highlighted for store campaigns) ----
    srows = await transactions_col.aggregate([
        {"$match": base_match},
        {"$group": {"_id": {"code": "$store_code", "name": "$store_name"},
                    "rev": {"$sum": NET_EXPR}, "customers": {"$addToSet": "$customer_mobile"}}},
        {"$project": {"_id": 0, "store_code": "$_id.code", "store_name": "$_id.name",
                      "revenue": {"$round": ["$rev", 2]}, "converters": {"$size": "$customers"}}},
        {"$sort": {"revenue": -1}}, {"$limit": 100},
    ], allowDiskUse=True, maxTimeMS=30000).to_list(100)
    if c.get("objective") == "store":
        tcodes = set(params.get("store_codes") or [])
        tgt = [s for s in srows if s.get("store_code") in tcodes]
        out["store"] = {
            "target_store_codes": list(tcodes),
            "target_converters": sum(s["converters"] for s in tgt),
            "target_revenue": round(sum(s["revenue"] for s in tgt), 2),
            "breakdown": srows,
        }
    else:
        out["store_breakdown"] = srows[:10]

    # ---- Coupon redemptions ----
    codes = params.get("coupon_codes") or ([c["coupon_code"]] if c.get("coupon_code") else [])
    if codes:
        crows = await coupon_redemptions_col.aggregate([
            {"$match": {"coupon_code": {"$in": codes}, "customer_mobile": {"$in": mobiles},
                        "created_at": {"$gte": t0_iso, "$lte": end_iso}}},
            {"$group": {"_id": None, "redemptions": {"$sum": 1},
                        "discount": {"$sum": {"$ifNull": ["$discount_amount", 0]}},
                        "customers": {"$addToSet": "$customer_mobile"}}},
        ], maxTimeMS=20000).to_list(1)
        cr = crows[0] if crows else {}
        out["coupon"] = {
            "coupon_codes": codes,
            "redemptions": cr.get("redemptions", 0),
            "redeemers": len(cr.get("customers") or []),
            "discount_given": round(cr.get("discount") or 0, 2),
        }

    # ---- Target-SKU units & value (resolve category/subcategory -> SKUs via master) ----
    if c.get("objective") == "sku" or params.get("skus") or params.get("categories") or params.get("subcategories"):
        target_skus = set(params.get("skus") or [])
        cats = params.get("categories") or []
        subs = params.get("subcategories") or []
        if cats or subs:
            m: Dict[str, Any] = {}
            if cats:
                m["category"] = {"$in": cats}
            if subs:
                m["subcategory"] = {"$in": subs}
            target_skus |= set(await items_col.distinct("sku", m))
        item_or = []
        if target_skus:
            item_or.append({"items.sku": {"$in": list(target_skus)}})
        if cats:
            item_or.append({"items.category": {"$in": cats}})
        sk: Dict[str, Any] = {}
        if item_or:
            skrows = await transactions_col.aggregate([
                {"$match": base_match},
                {"$unwind": "$items"},
                {"$match": {"$or": item_or}},
                {"$group": {"_id": None,
                            "units": {"$sum": {"$ifNull": ["$items.quantity", 1]}},
                            "value": {"$sum": {"$ifNull": ["$items.subtotal",
                                     {"$multiply": [{"$ifNull": ["$items.unit_price", 0]},
                                                    {"$ifNull": ["$items.quantity", 1]}]}]}},
                            "customers": {"$addToSet": "$customer_mobile"}}},
            ], allowDiskUse=True, maxTimeMS=30000).to_list(1)
            sk = skrows[0] if skrows else {}
        out["sku"] = {
            "target_sku_count": len(target_skus),
            "categories": cats, "subcategories": subs,
            "units_sold": sk.get("units", 0),
            "value_sold": round(sk.get("value") or 0, 2),
            "buyers": len(sk.get("customers") or []),
        }

    return out
