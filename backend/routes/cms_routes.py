"""CMS for public website (text + image content)."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from database import db
from auth import get_current_user, require_roles, log_audit, MANAGEMENT_ROLES

router = APIRouter(prefix="/cms", tags=["cms"])

cms_col = db["cms_content"]


DEFAULT_CONTENT = {
    "id": "default",
    "home": {
        "hero_eyebrow": "AN EXCLUSIVE PROGRAMME · POWERED BY FUNDLE",
        "hero_headline_1": "Where style",
        "hero_headline_em": "earns",
        "hero_headline_2": "you more.",
        "hero_subtext": "The official KAZO loyalty programme. Every purchase reveals new privileges — from welcome bonuses and birthday gifts to private VIP previews.",
        "hero_image_url": "https://images.unsplash.com/photo-1617551307578-7f5160d6615e?auto=format&fit=crop&w=1400&q=80",
        "stats_members": "1.5L+",
        "stats_cities": "15+",
        "stats_stores": "25+",
        "editorial_image_url": "https://images.pexels.com/photos/7778893/pexels-photo-7778893.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=900&w=1200",
        "editorial_eyebrow": "VIP PREVIEW",
        "editorial_headline": "Before the world sees it.",
        "editorial_body": "Platinum and Diamond members receive private collection previews — 72 hours before public launch. Reserve your size, your shade, your story.",
        "boutique_image_url": "https://images.pexels.com/photos/33327425/pexels-photo-33327425.png?auto=compress&cs=tinysrgb&dpr=2&h=900&w=1200",
        "final_cta_headline": "Your wardrobe. Rewarded.",
        "final_cta_body": "Membership is free. Privileges are forever.",
        "topbar_text": "EXCLUSIVE LOYALTY PROGRAM · EARN ON EVERY PURCHASE · BIRTHDAY PRIVILEGES INSIDE",
    },
    "footer": {
        "tagline": "The official loyalty programme for KAZO — where every purchase becomes a privilege. Designed for the modern Indian woman.",
        "powered_by": "Powered by Fundle",
    },
    "support": {
        "email": "rewards@kazo.com",
        "phone": "1800 123 456",
        "phone_hours": "Mon–Sat, 10AM–8PM",
        "address": "KAZO Fashion Pvt. Ltd., New Delhi, India",
    },
}


@router.get("/content")
async def get_content():
    """Public endpoint - no auth - used by the public site to render content."""
    doc = await cms_col.find_one({"id": "default"}, {"_id": 0})
    if not doc:
        doc = dict(DEFAULT_CONTENT)
        doc["updated_at"] = datetime.now(timezone.utc).isoformat()
        await cms_col.insert_one(dict(doc))
    return doc


@router.put("/content")
async def update_content(payload: dict, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    payload["id"] = "default"
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    payload["updated_by"] = user["id"]
    if "_id" in payload:
        del payload["_id"]
    await cms_col.update_one({"id": "default"}, {"$set": payload}, upsert=True)
    await log_audit(user, "update_cms", "cms", "default", {"sections": list(payload.keys())})
    doc = await cms_col.find_one({"id": "default"}, {"_id": 0})
    return doc
