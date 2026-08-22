"""Campaign manager."""
import asyncio
import logging
import random
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
import pymongo
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from database import (
    campaigns_col, customers_col, transactions_col, coupon_redemptions_col,
    message_log_col, db,
)
from routes._money import NET_EXPR
from auth import get_current_user, require_roles, log_audit, MANAGEMENT_ROLES
from models import CampaignCreate, Campaign

router = APIRouter(prefix="/campaigns", tags=["campaigns"])
logger = logging.getLogger("kazo-fundle.campaigns")

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


class AudiencePreviewIn(BaseModel):
    audience_type: str = "all"
    audience_filter: Dict[str, Any] = {}


@router.post("/audience-preview")
async def audience_preview(body: AudiencePreviewIn, user: dict = Depends(get_current_user)):
    """Ad-hoc audience size + sample for the Campaign Wizard (before a campaign is created)."""
    af = body.audience_filter or {}
    at = body.audience_type or "all"
    from routes.blacklist_util import blacklist_col, blacklisted_set, norm10
    blacklisted = await blacklist_col.count_documents({})
    # Marketing DB — the audience is EVERY number in the list (members + non-members), NOT just
    # those in the loyalty base. Count the raw mobile list (blacklist-excluded), not customers_col.
    if at == "marketing_db":
        mdb_id = af.get("marketing_db_id")
        if not mdb_id:
            return {"total_audience": 0, "sample": [], "needs_filter": True,
                    "blacklisted_total": blacklisted}
        mdb = await db["marketing_databases"].find_one(
            {"id": mdb_id}, {"_id": 0, "mobiles": 1, "member_count": 1, "non_member_count": 1})
        mobiles = (mdb or {}).get("mobiles") or []
        bl = await blacklisted_set()
        eff = [m for m in mobiles if norm10(m) not in bl] if bl else list(mobiles)
        sample_mobiles = eff[:10]
        member_map: Dict[str, Any] = {}
        if sample_mobiles:
            async for cst in customers_col.find(
                    {"mobile": {"$in": sample_mobiles}},
                    {"_id": 0, "mobile": 1, "name": 1, "tier": 1, "city": 1}):
                member_map[cst["mobile"]] = cst
        sample = [
            ({"mobile": m, "name": member_map[m].get("name"), "tier": member_map[m].get("tier"),
              "city": member_map[m].get("city")} if m in member_map
             else {"mobile": m, "name": None, "tier": "non-member"})
            for m in sample_mobiles
        ]
        return {"total_audience": len(eff), "sample": sample,
                "member_count": (mdb or {}).get("member_count"),
                "non_member_count": (mdb or {}).get("non_member_count"),
                "blacklisted_total": blacklisted}
    # Guard: an audience type that REQUIRES a filter key but has none must not degenerate to the
    # whole base (which is misleading in the wizard) — report needs_filter with a 0 count instead.
    required = {"tier": "tier", "city": "city", "cohort": "cohort", "segment": "segment_id"}
    if at in required and not af.get(required[at]):
        return {"total_audience": 0, "sample": [], "needs_filter": True,
                "blacklisted_total": blacklisted}
    fake = {"audience_type": at, "audience_filter": af}
    fil = await _audience_filter_async(fake)
    total = await customers_col.count_documents(fil)
    sample = await customers_col.find(
        fil, {"_id": 0, "mobile": 1, "name": 1, "tier": 1, "city": 1}).limit(10).to_list(10)
    return {"total_audience": total, "sample": sample, "blacklisted_total": blacklisted}


# ─────────────────────────── Blacklist (Phase 4) ───────────────────────────
class BlacklistAddIn(BaseModel):
    mobile: str
    reason: str = "manual"


@router.get("/blacklist")
async def get_blacklist(q: Optional[str] = None, limit: int = 500,
                        user: dict = Depends(get_current_user)):
    from routes.blacklist_util import list_blacklist
    return await list_blacklist(limit=limit, q=q)


@router.post("/blacklist")
async def add_blacklist(body: BlacklistAddIn, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    from routes.blacklist_util import add_to_blacklist
    ok = await add_to_blacklist(body.mobile, reason=body.reason or "manual",
                                source="manual", by=user.get("email"))
    if not ok:
        raise HTTPException(400, "Invalid mobile — need at least 10 digits")
    await log_audit(user, "blacklist_add", "blacklist", body.mobile, {"reason": body.reason})
    return {"ok": True, "mobile": body.mobile}


@router.delete("/blacklist/{mobile}")
async def delete_blacklist(mobile: str, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    from routes.blacklist_util import remove_from_blacklist
    n = await remove_from_blacklist(mobile)
    await log_audit(user, "blacklist_remove", "blacklist", mobile, {"removed": n})
    return {"ok": True, "removed": n}


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
    if c.get("audience_type") == "marketing_db":
        mdb_id = (c.get("audience_filter") or {}).get("marketing_db_id")
        if mdb_id:
            mdb = await db["marketing_databases"].find_one({"id": mdb_id}, {"_id": 0, "mobiles": 1})
            mobiles = (mdb or {}).get("mobiles") or []
            return {"mobile": {"$in": mobiles}} if mobiles else {"mobile": {"$in": ["__none__"]}}
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
    # Phase 4 — never freeze blacklisted numbers into a campaign dataset.
    try:
        from routes.blacklist_util import blacklisted_set, norm10
        bl = await blacklisted_set()
        if bl:
            mobiles = [m for m in mobiles if norm10(m) not in bl]
    except Exception:  # noqa: BLE001
        pass
    await campaign_datasets_col.replace_one(
        {"campaign_id": campaign_id},
        {"campaign_id": campaign_id, "mobiles": mobiles, "size": len(mobiles),
         "t0": t0, "frozen_at": datetime.now(timezone.utc).isoformat()},
        upsert=True)
    return len(mobiles)


async def _freeze_dataset_from_mobiles(campaign_id: str, mobiles: List[str], t0: str) -> int:
    """Freeze an explicit mobile list (Master-Brain 'mobiles'/'report' audiences) as the ROI
    dataset, minus blacklisted numbers."""
    ms = sorted({(m or "").strip() for m in (mobiles or []) if (m or "").strip()})
    try:
        from routes.blacklist_util import blacklisted_set, norm10
        bl = await blacklisted_set()
        if bl:
            ms = [m for m in ms if norm10(m) not in bl]
    except Exception:  # noqa: BLE001
        pass
    await campaign_datasets_col.replace_one(
        {"campaign_id": campaign_id},
        {"campaign_id": campaign_id, "mobiles": ms, "size": len(ms),
         "t0": t0, "frozen_at": datetime.now(timezone.utc).isoformat()},
        upsert=True)
    return len(ms)


async def register_mb_campaign(*, cid: str, name: str, spec: dict, count: int, t0: str,
                               created_by: str, template_id: Optional[str] = None,
                               message: Optional[str] = None, audience_type: str = "all",
                               audience_label: str = "", objective: str = "generic",
                               objective_params: Optional[dict] = None, roi_window: str = "7d",
                               cost: Optional[float] = None) -> int:
    """Register a Master-Brain SMS campaign in the CORE campaigns_col + freeze its dataset so it
    gets the same real ROI + delivery tracking as UI-launched campaigns (unified pipeline)."""
    if (spec or {}).get("mode") == "mobiles":
        frozen = await _freeze_dataset_from_mobiles(cid, spec.get("mobiles") or [], t0)
    else:
        frozen = await _freeze_dataset(cid, (spec or {}).get("filter") or {}, count or 50000, t0)
    core = {
        "id": cid, "name": name,
        "description": f"Executed by Master Brain · {audience_label}".strip(" ·"),
        "channels": ["sms"], "audience_type": audience_type or "all",
        "audience_filter": {"label": audience_label},
        "message_template": message, "template_id": template_id, "coupon_code": "",
        "status": "running",
        "objective": objective or "generic", "objective_params": objective_params or {},
        "roi_window": roi_window or "7d", "cost": cost, "send_limit": count,
        "sent": 0, "delivered": 0, "opened": 0, "clicked": 0, "redeemed": 0, "revenue_generated": 0.0,
        "created_at": datetime.now(timezone.utc).isoformat(), "created_by": created_by,
        "launched_at": t0, "dataset_size": frozen, "send_mode": "karix", "source": "master_brain",
    }
    await campaigns_col.replace_one({"id": cid}, core, upsert=True)
    return frozen


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
    return await _do_launch(c, user)


async def _do_launch(c: dict, user: dict) -> dict:
    campaign_id = c["id"]
    launched_at = datetime.now(timezone.utc).isoformat()
    send_limit = int(c.get("send_limit") or 50000)
    cap = min(send_limit, 50000)

    # Marketing-DB audiences send to EVERY number in the list (members + non-members) — resolve the
    # raw mobile list (dedup + blacklist-exclude + cap) and drive the send/freeze from that, NOT the
    # loyalty base (which would silently drop all non-members).
    explicit_mobiles: Optional[List[str]] = None
    if c.get("audience_type") == "marketing_db":
        mdb_id = (c.get("audience_filter") or {}).get("marketing_db_id")
        mdb = await db["marketing_databases"].find_one(
            {"id": mdb_id}, {"_id": 0, "mobiles": 1}) if mdb_id else None
        raw = (mdb or {}).get("mobiles") or []
        seen: set = set()
        ordered: List[str] = []
        for m in raw:
            mm = (m or "").strip()
            if mm and mm not in seen:
                seen.add(mm)
                ordered.append(mm)
        try:
            from routes.blacklist_util import blacklisted_set, norm10
            bl = await blacklisted_set()
            if bl:
                ordered = [m for m in ordered if norm10(m) not in bl]
        except Exception:  # noqa: BLE001
            pass
        explicit_mobiles = ordered[:cap]

    if explicit_mobiles is not None:
        fil: Dict[str, Any] = {}
        audience_size = len(explicit_mobiles)
        dataset_size = await _freeze_dataset_from_mobiles(campaign_id, explicit_mobiles, launched_at)
    else:
        fil = await _audience_filter_async(c)
        audience_size = await customers_col.count_documents(fil)
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
        asyncio.create_task(_run_bulk_send_job(job_id, template_id, fil, limit, campaign_id,
                                               c.get("coupon_batch_id"), explicit_mobiles))

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
    sent = min(audience_size, send_limit)
    delivered = int(sent * 0.94)
    opened = int(delivered * 0.42)
    clicked = int(opened * 0.18)
    redeemed = int(clicked * 0.25)
    revenue = redeemed * random.randint(1500, 4500)
    await campaigns_col.update_one(
        {"id": campaign_id},
        {"$set": {
            "status": "completed",
            "launched_at": launched_at,
            "completed_at": launched_at,
            "dataset_size": dataset_size,
            "send_mode": "simulated",
            "sent": sent, "delivered": delivered, "opened": opened, "clicked": clicked,
            "redeemed": redeemed, "revenue_generated": float(revenue),
        }}
    )
    await log_audit(user, "launch_campaign", "campaign", campaign_id,
                      {"audience": audience_size, "mode": "simulated"})
    return {"success": True, "audience": audience_size, "sent": sent, "mode": "simulated"}


_SCHED_USER = {"id": "scheduler", "email": "scheduler@system", "role": "super_admin"}


async def run_due_campaigns() -> None:
    """Scheduler tick: auto-launch any campaign whose scheduled time has arrived (no user action)."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        due = await campaigns_col.find(
            {"status": "scheduled", "schedule_at": {"$lte": now}}, {"_id": 0}).limit(25).to_list(25)
    except Exception as e:  # noqa: BLE001
        logger.error("run_due_campaigns query failed: %s", e)
        return
    for c in due:
        try:
            await _do_launch(c, _SCHED_USER)
            logger.info("Auto-launched scheduled campaign %s (%s)", c.get("id"), c.get("name"))
        except Exception as e:  # noqa: BLE001
            logger.error("Auto-launch failed for %s: %s", c.get("id"), e)
            await campaigns_col.update_one(
                {"id": c["id"]},
                {"$set": {"status": "draft", "schedule_error": str(e)[:300]}})


@router.post("/{campaign_id}/unschedule")
async def unschedule_campaign(campaign_id: str, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    """Cancel a pending schedule — reverts the campaign to draft so it will NOT auto-fire."""
    c = await campaigns_col.find_one({"id": campaign_id}, {"_id": 0, "status": 1})
    if not c:
        raise HTTPException(404, "Campaign not found")
    if c.get("status") != "scheduled":
        raise HTTPException(400, "Only a scheduled campaign can be unscheduled")
    await campaigns_col.update_one({"id": campaign_id}, {"$set": {"status": "draft"}, "$unset": {"schedule_at": ""}})
    await log_audit(user, "unschedule_campaign", "campaign", campaign_id, {})
    return {"ok": True}



@router.patch("/{campaign_id}")
async def update_campaign(campaign_id: str, updates: dict, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    if isinstance(updates.get("schedule_at"), datetime):
        updates["schedule_at"] = updates["schedule_at"].isoformat()
    await campaigns_col.update_one({"id": campaign_id}, {"$set": updates})
    await log_audit(user, "update_campaign", "campaign", campaign_id, updates)
    return await campaigns_col.find_one({"id": campaign_id}, {"_id": 0})


@router.delete("/{campaign_id}")
async def delete_campaign(campaign_id: str, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    """Delete a campaign and its frozen ROI dataset. Running campaigns cannot be deleted."""
    c = await campaigns_col.find_one({"id": campaign_id}, {"_id": 0, "status": 1})
    if not c:
        raise HTTPException(404, "Campaign not found")
    if c.get("status") == "running":
        raise HTTPException(400, "Cannot delete a running campaign — cancel/complete it first")
    await campaigns_col.delete_one({"id": campaign_id})
    await campaign_datasets_col.delete_one({"campaign_id": campaign_id})
    await log_audit(user, "delete_campaign", "campaign", campaign_id, {})
    return {"ok": True}


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


@router.get("/{campaign_id}/delivery")
async def campaign_delivery(campaign_id: str, user: dict = Depends(get_current_user)):
    """Delivery report for a campaign — sent / delivered / undelivered / failed / pending
    from message_log (updated by Karix DLRs), with a delivery rate and failure samples."""
    c = await campaigns_col.find_one({"id": campaign_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Campaign not found")
    rows = await message_log_col.aggregate([
        {"$match": {"campaign_id": campaign_id}},
        {"$group": {"_id": "$delivery_status", "n": {"$sum": 1}}},
    ]).to_list(50)
    by = {(r["_id"] or "unknown"): r["n"] for r in rows}
    total = sum(by.values())
    delivered = by.get("delivered", 0)
    counts = {
        "submitted": by.get("submitted", 0),
        "delivered": delivered,
        "undelivered": by.get("undelivered", 0) + by.get("expired", 0),
        "failed": by.get("failed", 0) + by.get("rejected", 0),
        "pending": by.get("submitted", 0),
    }
    fails = await message_log_col.find(
        {"campaign_id": campaign_id,
         "delivery_status": {"$in": ["failed", "undelivered", "expired", "rejected"]}},
        {"_id": 0, "mobile": 1, "delivery_status": 1, "response": 1, "timestamp": 1},
    ).sort("timestamp", -1).limit(20).to_list(20)
    return {
        "campaign_id": campaign_id, "total": total,
        "counts": counts, "by_status": by,
        "delivery_rate_pct": round(delivered / total * 100, 1) if total else 0.0,
        "failure_rate_pct": round((counts["failed"] + counts["undelivered"]) / total * 100, 1) if total else 0.0,
        "failures_sample": fails,
        "webhook_url": "/api/communications/dlr/karix",
    }
