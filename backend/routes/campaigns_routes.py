"""Campaign manager."""
import asyncio
import random
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from database import campaigns_col, customers_col
from auth import get_current_user, require_roles, log_audit, MANAGEMENT_ROLES
from models import CampaignCreate, Campaign

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


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

    fil = await _audience_filter_async(c)
    audience_size = await customers_col.count_documents(fil)

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

        limit = int(c.get("send_limit") or 50000)
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
        asyncio.create_task(_run_bulk_send_job(job_id, template_id, fil, limit))

        await campaigns_col.update_one(
            {"id": campaign_id},
            {"$set": {
                "status": "running",
                "launched_at": datetime.now(timezone.utc).isoformat(),
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
            "launched_at": datetime.now(timezone.utc).isoformat(),
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
