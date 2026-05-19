"""Loyalty configurator."""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from database import loyalty_config_col, customers_col
from auth import get_current_user, require_roles, log_audit, MANAGEMENT_ROLES
from models import LoyaltyConfig, TierRule, LoyaltyTier

router = APIRouter(prefix="/loyalty", tags=["loyalty"])


DEFAULT_CONFIG = {
    "id": "default",
    "earn_ratio": 1.0,
    "burn_ratio": 0.25,
    "min_redeem_points": 100,
    "point_expiry_days": 365,
    "welcome_bonus": 100,
    "birthday_bonus": 200,
    "anniversary_bonus": 200,
    "referral_points_referrer": 250,
    "referral_points_referee": 100,
    "tier_rules": [
        {"tier": "silver", "min_lifetime_spend": 0, "earn_multiplier": 1.0, "welcome_bonus": 100, "birthday_bonus": 200},
        {"tier": "gold", "min_lifetime_spend": 25000, "earn_multiplier": 1.25, "welcome_bonus": 200, "birthday_bonus": 500},
        {"tier": "platinum", "min_lifetime_spend": 75000, "earn_multiplier": 1.5, "welcome_bonus": 300, "birthday_bonus": 1000},
        {"tier": "diamond", "min_lifetime_spend": 150000, "earn_multiplier": 2.0, "welcome_bonus": 500, "birthday_bonus": 2000},
    ],
    "require_otp_for_redeem": True,
    "allow_coupon_stacking": False,
    "min_bill_for_earn": 500.0,
}


@router.get("/config")
async def get_config(user: dict = Depends(get_current_user)):
    cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0})
    if not cfg:
        cfg = dict(DEFAULT_CONFIG)
        cfg["updated_at"] = datetime.now(timezone.utc).isoformat()
        await loyalty_config_col.insert_one(dict(cfg))
        cfg.pop("_id", None)
    return cfg


@router.put("/config")
async def update_config(payload: dict, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    payload["id"] = "default"
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    payload["updated_by"] = user["id"]
    await loyalty_config_col.update_one({"id": "default"}, {"$set": payload}, upsert=True)
    await log_audit(user, "update_loyalty_config", "loyalty", "default", payload)
    cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0})
    return cfg


@router.get("/tier-stats")
async def tier_stats(user: dict = Depends(get_current_user)):
    pipeline = [
        {"$group": {
            "_id": "$tier",
            "count": {"$sum": 1},
            "avg_spend": {"$avg": "$lifetime_spend"},
            "total_spend": {"$sum": "$lifetime_spend"},
            "points_balance": {"$sum": "$points_balance"},
        }},
        {"$sort": {"total_spend": -1}},
    ]
    rows = await customers_col.aggregate(pipeline).to_list(20)
    return [
        {
            "tier": r["_id"],
            "count": r["count"],
            "avg_spend": round(r["avg_spend"], 2),
            "total_spend": round(r["total_spend"], 2),
            "points_balance": int(r["points_balance"]),
        }
        for r in rows
    ]
