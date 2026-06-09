"""Loyalty configurator — earn engine, redeem engine, tiers, multipliers, festival boosters."""
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from database import loyalty_config_col, customers_col
from auth import get_current_user, require_roles, log_audit, MANAGEMENT_ROLES
from models import LoyaltyConfig, TierRule  # noqa: F401  (kept for downstream imports)

router = APIRouter(prefix="/loyalty", tags=["loyalty"])


DEFAULT_CONFIG = {
    "id": "default",
    # Earn engine
    "earn_mode": "points_per_spend",
    "earn_ratio": 1.0,
    "percent_of_spend": 5.0,
    # Redeem engine
    "burn_ratio": 0.25,
    "min_redeem_points": 100,
    "max_redeem_pct_of_bill": 50.0,
    "point_expiry_days": 365,
    # Bonuses
    "welcome_bonus": 100,
    "birthday_bonus": 200,
    "anniversary_bonus": 200,
    "referral_points_referrer": 250,
    "referral_points_referee": 100,
    # Tiers
    "tier_rules": [
        {"tier": "silver", "name": "Silver", "min_lifetime_spend": 0, "max_lifetime_spend": 25000,
         "earn_multiplier": 1.0, "welcome_bonus": 100, "birthday_bonus": 200, "anniversary_bonus": 100,
         "upgrade_bonus": 0,
         "tier_type": "entry", "is_active": True, "color": "#9ca3af",
         "coupon_discount_pct": 0, "free_shipping_min_bill": None},
        {"tier": "gold", "name": "Gold", "min_lifetime_spend": 25000, "max_lifetime_spend": 75000,
         "earn_multiplier": 1.25, "welcome_bonus": 200, "birthday_bonus": 500, "anniversary_bonus": 250,
         "upgrade_bonus": 500,
         "tier_type": "standard", "is_active": True, "color": "#d4af37",
         "coupon_discount_pct": 5, "free_shipping_min_bill": 2000},
        {"tier": "platinum", "name": "Platinum", "min_lifetime_spend": 75000, "max_lifetime_spend": 150000,
         "earn_multiplier": 1.5, "welcome_bonus": 300, "birthday_bonus": 1000, "anniversary_bonus": 500,
         "upgrade_bonus": 1500,
         "tier_type": "premium", "is_active": True, "color": "#7e7e7e",
         "coupon_discount_pct": 8, "free_shipping_min_bill": 1500},
        {"tier": "diamond", "name": "Diamond", "min_lifetime_spend": 150000, "max_lifetime_spend": None,
         "earn_multiplier": 2.0, "welcome_bonus": 500, "birthday_bonus": 2000, "anniversary_bonus": 1000,
         "upgrade_bonus": 5000,
         "tier_type": "vip", "is_active": True, "color": "#b9f2ff",
         "coupon_discount_pct": 10, "free_shipping_min_bill": 0,
         "point_expiry_override_days": 730},  # 2 years for diamond
    ],
    "tier_reset_cadence": "never",
    "tier_reset_anchor_date": "01-01",
    # Multipliers
    "category_multipliers": {},
    "store_type_multipliers": {"online": 1.0, "offline": 1.0},
    "festival_boosters": [],
    # Compliance
    "require_otp_for_redeem": True,
    "allow_coupon_stacking": False,
    "min_bill_for_earn": 500.0,
    "block_earn_on_returns": True,
    # Earn & Burn control — master switches + scheduled pause windows (blackout dates)
    "earn_enabled": True,
    "burn_enabled": True,
    "earn_burn_pauses": [],
}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


@router.get("/config")
async def get_config(user: dict = Depends(get_current_user)):
    cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0})
    if not cfg:
        cfg = dict(DEFAULT_CONFIG)
        cfg["updated_at"] = _now_iso()
        await loyalty_config_col.insert_one(dict(cfg))
        cfg.pop("_id", None)
    # Backfill any newly-added defaults onto an old document
    changed = False
    for k, v in DEFAULT_CONFIG.items():
        if k not in cfg:
            cfg[k] = v
            changed = True
    # Backfill newly-added per-tier fields (e.g. upgrade_bonus) onto existing tiers
    for t in (cfg.get("tier_rules") or []):
        if "upgrade_bonus" not in t:
            t["upgrade_bonus"] = 0
            changed = True
    if changed:
        await loyalty_config_col.update_one({"id": "default"}, {"$set": cfg}, upsert=True)
    return cfg


@router.put("/config")
async def update_config(payload: dict, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    # Validate tier ordering — min_lifetime_spend must be ascending
    tiers = payload.get("tier_rules") or []
    if tiers:
        sorted_tiers = sorted([t for t in tiers if t.get("is_active", True)],
                              key=lambda t: t.get("min_lifetime_spend", 0))
        prev_max = None
        for t in sorted_tiers:
            if prev_max is not None and t.get("min_lifetime_spend", 0) < prev_max:
                raise HTTPException(status_code=400,
                                    detail=f"Tier '{t.get('name') or t.get('tier')}' overlaps the previous tier (min < previous max)")
            if t.get("max_lifetime_spend") is not None:
                if t.get("max_lifetime_spend") <= t.get("min_lifetime_spend", 0):
                    raise HTTPException(status_code=400,
                                        detail=f"Tier '{t.get('name') or t.get('tier')}' has max <= min")
                prev_max = t.get("max_lifetime_spend")

    # Validate earn_mode
    if payload.get("earn_mode") and payload["earn_mode"] not in ("points_per_spend", "percent_of_spend"):
        raise HTTPException(status_code=400, detail="earn_mode must be 'points_per_spend' or 'percent_of_spend'")
    # Validate reset cadence
    if payload.get("tier_reset_cadence") and payload["tier_reset_cadence"] not in ("never", "annual", "rolling_12m"):
        raise HTTPException(status_code=400, detail="tier_reset_cadence must be 'never' | 'annual' | 'rolling_12m'")

    payload["id"] = "default"
    payload["updated_at"] = _now_iso()
    payload["updated_by"] = user.get("id") or user.get("email")
    await loyalty_config_col.update_one({"id": "default"}, {"$set": payload}, upsert=True)
    await log_audit(user, "update_loyalty_config", "loyalty", "default",
                    {"keys": list(payload.keys())})
    cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0})
    return cfg


class TierCreatePayload(BaseModel):
    tier: str
    name: Optional[str] = None
    min_lifetime_spend: float = 0
    max_lifetime_spend: Optional[float] = None
    earn_multiplier: float = 1.0
    welcome_bonus: int = 0
    birthday_bonus: int = 0
    anniversary_bonus: int = 0
    upgrade_bonus: int = 0
    tier_type: str = "standard"
    color: Optional[str] = None
    coupon_discount_pct: float = 0
    free_shipping_min_bill: Optional[float] = None
    point_expiry_override_days: Optional[int] = None
    visit_threshold: Optional[int] = None


@router.post("/tiers")
async def add_tier(payload: TierCreatePayload, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0}) or dict(DEFAULT_CONFIG)
    tiers = cfg.get("tier_rules") or []
    # Slug must be unique
    if any(t.get("tier", "").lower() == payload.tier.lower() for t in tiers):
        raise HTTPException(status_code=400, detail=f"Tier slug '{payload.tier}' already exists")
    new_tier = payload.model_dump()
    new_tier["tier"] = new_tier["tier"].lower().strip()
    new_tier["name"] = new_tier.get("name") or new_tier["tier"].capitalize()
    new_tier["is_active"] = True
    tiers.append(new_tier)
    # Re-sort by min_lifetime_spend
    tiers.sort(key=lambda t: t.get("min_lifetime_spend", 0))
    await loyalty_config_col.update_one({"id": "default"},
                                         {"$set": {"tier_rules": tiers,
                                                   "updated_at": _now_iso(),
                                                   "updated_by": user.get("email")}})
    await log_audit(user, "add_loyalty_tier", "loyalty", payload.tier, new_tier)
    return {"ok": True, "tier": new_tier, "tiers": tiers}


@router.patch("/tiers/{tier_slug}/toggle")
async def toggle_tier(tier_slug: str, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0})
    if not cfg:
        raise HTTPException(status_code=404, detail="No config")
    tiers = cfg.get("tier_rules") or []
    found = False
    for t in tiers:
        if t.get("tier", "").lower() == tier_slug.lower():
            t["is_active"] = not t.get("is_active", True)
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail=f"Tier '{tier_slug}' not found")
    await loyalty_config_col.update_one({"id": "default"}, {"$set": {"tier_rules": tiers, "updated_at": _now_iso()}})
    await log_audit(user, "toggle_loyalty_tier", "loyalty", tier_slug, {})
    return {"ok": True, "tiers": tiers}


@router.delete("/tiers/{tier_slug}")
async def delete_tier(tier_slug: str, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    """Hard-delete a tier. Use toggle to soft-deactivate instead in most cases."""
    cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0})
    if not cfg:
        raise HTTPException(status_code=404, detail="No config")
    tiers = [t for t in (cfg.get("tier_rules") or []) if t.get("tier", "").lower() != tier_slug.lower()]
    if len(tiers) == len(cfg.get("tier_rules") or []):
        raise HTTPException(status_code=404, detail=f"Tier '{tier_slug}' not found")
    if len(tiers) == 0:
        raise HTTPException(status_code=400, detail="Cannot delete the last tier")
    await loyalty_config_col.update_one({"id": "default"}, {"$set": {"tier_rules": tiers, "updated_at": _now_iso()}})
    await log_audit(user, "delete_loyalty_tier", "loyalty", tier_slug, {})
    return {"ok": True, "tiers": tiers}


class FestivalBoosterPayload(BaseModel):
    name: str
    start_date: str  # ISO YYYY-MM-DD
    end_date: str
    multiplier: float
    applies_to: str = "all"  # 'all' | 'tier:<slug>' | 'category:<name>'


@router.post("/festival-boosters")
async def add_festival_booster(payload: FestivalBoosterPayload,
                                user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0}) or dict(DEFAULT_CONFIG)
    boosters = cfg.get("festival_boosters") or []
    item = payload.model_dump()
    item["id"] = f"fb_{int(datetime.now(timezone.utc).timestamp())}"
    boosters.append(item)
    await loyalty_config_col.update_one({"id": "default"},
                                         {"$set": {"festival_boosters": boosters,
                                                   "updated_at": _now_iso()}})
    await log_audit(user, "add_festival_booster", "loyalty", item["id"], item)
    return {"ok": True, "boosters": boosters}


@router.delete("/festival-boosters/{booster_id}")
async def delete_festival_booster(booster_id: str,
                                    user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0})
    if not cfg:
        raise HTTPException(status_code=404, detail="No config")
    boosters = [b for b in (cfg.get("festival_boosters") or []) if b.get("id") != booster_id]
    await loyalty_config_col.update_one({"id": "default"},
                                         {"$set": {"festival_boosters": boosters,
                                                   "updated_at": _now_iso()}})
    await log_audit(user, "delete_festival_booster", "loyalty", booster_id, {})
    return {"ok": True, "boosters": boosters}


# ============================================================
# Earn & Burn control — master switches + scheduled pause windows
# ============================================================
class EarnBurnControlPayload(BaseModel):
    earn_enabled: Optional[bool] = None
    burn_enabled: Optional[bool] = None


@router.put("/earn-burn-control")
async def set_earn_burn_control(payload: EarnBurnControlPayload,
                                user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    """Immediate master ON/OFF for earning and/or burning of points."""
    upd: Dict[str, Any] = {"updated_at": _now_iso()}
    if payload.earn_enabled is not None:
        upd["earn_enabled"] = payload.earn_enabled
    if payload.burn_enabled is not None:
        upd["burn_enabled"] = payload.burn_enabled
    await loyalty_config_col.update_one({"id": "default"}, {"$set": upd}, upsert=True)
    await log_audit(user, "set_earn_burn_control", "loyalty", "default", upd)
    cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0})
    return {"ok": True, "earn_enabled": cfg.get("earn_enabled", True),
            "burn_enabled": cfg.get("burn_enabled", True)}


class PauseWindowPayload(BaseModel):
    label: str = ""
    start_date: str  # YYYY-MM-DD
    end_date: str
    pause_earn: bool = True
    pause_burn: bool = False


@router.post("/pauses")
async def add_pause_window(payload: PauseWindowPayload,
                           user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    if payload.start_date > payload.end_date:
        raise HTTPException(status_code=400, detail="start_date must be on or before end_date")
    if not (payload.pause_earn or payload.pause_burn):
        raise HTTPException(status_code=400, detail="Select at least one of pause earn / pause burn")
    cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0}) or dict(DEFAULT_CONFIG)
    pauses = cfg.get("earn_burn_pauses") or []
    item = payload.model_dump()
    item["id"] = f"pause_{int(datetime.now(timezone.utc).timestamp())}"
    item["active"] = True
    pauses.append(item)
    await loyalty_config_col.update_one({"id": "default"},
                                         {"$set": {"earn_burn_pauses": pauses,
                                                   "updated_at": _now_iso()}}, upsert=True)
    await log_audit(user, "add_pause_window", "loyalty", item["id"], item)
    return {"ok": True, "pauses": pauses}


@router.patch("/pauses/{pause_id}/toggle")
async def toggle_pause_window(pause_id: str,
                              user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0})
    if not cfg:
        raise HTTPException(status_code=404, detail="No config")
    pauses = cfg.get("earn_burn_pauses") or []
    found = False
    for p in pauses:
        if p.get("id") == pause_id:
            p["active"] = not p.get("active", True)
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="Pause window not found")
    await loyalty_config_col.update_one({"id": "default"},
                                         {"$set": {"earn_burn_pauses": pauses,
                                                   "updated_at": _now_iso()}})
    await log_audit(user, "toggle_pause_window", "loyalty", pause_id, {})
    return {"ok": True, "pauses": pauses}


@router.delete("/pauses/{pause_id}")
async def delete_pause_window(pause_id: str,
                              user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0})
    if not cfg:
        raise HTTPException(status_code=404, detail="No config")
    pauses = [p for p in (cfg.get("earn_burn_pauses") or []) if p.get("id") != pause_id]
    await loyalty_config_col.update_one({"id": "default"},
                                         {"$set": {"earn_burn_pauses": pauses,
                                                   "updated_at": _now_iso()}})
    await log_audit(user, "delete_pause_window", "loyalty", pause_id, {})
    return {"ok": True, "pauses": pauses}


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
            "avg_spend": round(r["avg_spend"] or 0, 2),
            "total_spend": round(r["total_spend"] or 0, 2),
            "points_balance": int(r["points_balance"] or 0),
        }
        for r in rows
    ]


@router.post("/simulate")
async def simulate_earn(payload: dict, user: dict = Depends(get_current_user)):
    """Preview how many points a hypothetical bill would earn under the current config.

    Body: { bill_amount: float, tier: str, store_type?: str, category?: str, bill_date?: str (YYYY-MM-DD) }
    Returns: { points, breakdown: [...], explanation }
    """
    cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0}) or dict(DEFAULT_CONFIG)
    bill = float(payload.get("bill_amount") or 0)
    tier_slug = (payload.get("tier") or "").lower()
    if bill < cfg.get("min_bill_for_earn", 0):
        return {"points": 0, "breakdown": [],
                "explanation": f"Bill ₹{bill} below min earn threshold of ₹{cfg.get('min_bill_for_earn', 0)}."}

    # Resolve the tier rule first (needed for the tier-driven mode).
    tier_rule = next((t for t in (cfg.get("tier_rules") or [])
                       if t.get("tier", "").lower() == tier_slug and t.get("is_active", True)), None)
    tier_mult = tier_rule.get("earn_multiplier", 1.0) if tier_rule else 1.0

    # Step 1: base points
    if cfg.get("earn_mode") == "percent_of_spend":
        rate = float(cfg.get("percent_of_spend") or 0) / 100.0
        mode_explain = f"{cfg.get('percent_of_spend', 0)}% of ₹{bill}"
    else:
        rate = float(cfg.get("earn_ratio") or 0)
        mode_explain = f"{cfg.get('earn_ratio', 0)} pts × ₹{bill}"

    if rate > 0:
        base = bill * rate
        breakdown = [{"step": "Base earn", "detail": mode_explain, "points": round(base, 2)}]
        pts = base
        # Step 2: tier multiplier
        if tier_rule and tier_mult != 1.0:
            extra = pts * (tier_mult - 1)
            breakdown.append({"step": "Tier multiplier",
                              "detail": f"{tier_rule.get('name', tier_slug)} ×{tier_mult}",
                              "points": round(extra, 2)})
            pts *= tier_mult
    else:
        # Tier-driven: no global earn rate set → the tier multiplier IS the % of the bill.
        pts = bill * (tier_mult / 100.0)
        breakdown = [{"step": "Tier-driven earn",
                      "detail": f"{(tier_rule or {}).get('name', tier_slug) or 'tier'}: {tier_mult}% of ₹{bill}",
                      "points": round(pts, 2)}]

    # Step 3: store-type multiplier
    store_type = payload.get("store_type")
    if store_type and cfg.get("store_type_multipliers", {}).get(store_type, 1.0) != 1.0:
        mult = cfg["store_type_multipliers"][store_type]
        extra = pts * (mult - 1)
        breakdown.append({"step": "Store-type",
                          "detail": f"{store_type} ×{mult}",
                          "points": round(extra, 2)})
        pts *= mult

    # Step 4: category multiplier
    cat = payload.get("category")
    if cat and cfg.get("category_multipliers", {}).get(cat, 1.0) != 1.0:
        mult = cfg["category_multipliers"][cat]
        extra = pts * (mult - 1)
        breakdown.append({"step": "Category",
                          "detail": f"{cat} ×{mult}",
                          "points": round(extra, 2)})
        pts *= mult

    # Step 5: festival booster (active on bill_date)
    bd = payload.get("bill_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for b in (cfg.get("festival_boosters") or []):
        if b.get("start_date") <= bd <= b.get("end_date"):
            applies = b.get("applies_to", "all")
            if applies == "all" or applies == f"tier:{tier_slug}" or applies == f"category:{cat}":
                mult = b.get("multiplier", 1.0)
                if mult != 1.0:
                    extra = pts * (mult - 1)
                    breakdown.append({"step": "Festival booster",
                                      "detail": f"{b.get('name')} ×{mult}",
                                      "points": round(extra, 2)})
                    pts *= mult

    return {
        "points": round(pts, 2),
        "breakdown": breakdown,
        "explanation": f"₹{bill} earns {round(pts, 2)} points for a {tier_rule.get('name', tier_slug) if tier_rule else tier_slug} customer.",
    }
