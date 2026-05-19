"""Campaign manager."""
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from database import campaigns_col, customers_col
from auth import get_current_user, require_roles, log_audit, MANAGEMENT_ROLES
from models import CampaignCreate, Campaign
import uuid
import random

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
    fil = _audience_filter(c)
    total = await customers_col.count_documents(fil)
    sample = await customers_col.find(fil, {"_id": 0, "mobile": 1, "name": 1, "tier": 1, "city": 1}).limit(20).to_list(20)
    return {"total_audience": total, "sample": sample}


def _audience_filter(c: dict) -> dict:
    fil = {}
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


@router.post("/{campaign_id}/launch")
async def launch_campaign(campaign_id: str, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    c = await campaigns_col.find_one({"id": campaign_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Campaign not found")
    if c["status"] not in ("draft", "scheduled"):
        raise HTTPException(400, f"Campaign already {c['status']}")
    fil = _audience_filter(c)
    audience_size = await customers_col.count_documents(fil)
    # Simulate sending metrics (in real system this connects to WhatsApp/SMS gateway)
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
            "sent": sent, "delivered": delivered, "opened": opened, "clicked": clicked,
            "redeemed": redeemed, "revenue_generated": float(revenue),
        }}
    )
    await log_audit(user, "launch_campaign", "campaign", campaign_id, {"audience": audience_size})
    return {"success": True, "audience": audience_size, "sent": sent}


@router.patch("/{campaign_id}")
async def update_campaign(campaign_id: str, updates: dict, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    if isinstance(updates.get("schedule_at"), datetime):
        updates["schedule_at"] = updates["schedule_at"].isoformat()
    await campaigns_col.update_one({"id": campaign_id}, {"$set": updates})
    await log_audit(user, "update_campaign", "campaign", campaign_id, updates)
    return await campaigns_col.find_one({"id": campaign_id}, {"_id": 0})
