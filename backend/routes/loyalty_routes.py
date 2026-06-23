"""Loyalty configurator — earn engine, redeem engine, tiers, multipliers, festival boosters."""
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from database import loyalty_config_col, customers_col, db
from auth import get_current_user, require_roles, log_audit, MANAGEMENT_ROLES
from models import LoyaltyConfig, TierRule  # noqa: F401  (kept for downstream imports)

retier_jobs_col = db["retier_jobs"]

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


# ============================================================
# Re-tier old (pre-POS) customers from configured tier ranges
# ------------------------------------------------------------
# Old historical customers (imported before the POS integration went live)
# still carry stale "dummy" tiers that don't reflect their actual billing.
# These endpoints re-derive each such customer's tier STRICTLY from the
# CONFIGURED tier_rules (display names included) using their lifetime_spend
# ("Total Billing"). New POS customers (created on/after the cutoff) are
# never touched. Idempotent + scale-safe (bulk update_many per tier band).
# ============================================================
DEFAULT_RETIER_CUTOFF = "2026-06-08"

# Live POS-created customers are managed correctly by the earn engine — they are
# EXCLUDED from re-tiering. Everything else (historic_upload, transaction_derived,
# perf_seed, registered_account, auto_from_transactions, null) is "old / pre-POS".
POS_SOURCES = ["pos_ewards", "pos_auto", "pos_auto_customer_key", "pos_test_seed"]


def _old_customer_filter(mode: str, cutoff: str) -> dict:
    """Identify OLD (pre-POS) customers. Default mode = by SOURCE (reliable, because
    `created_at` is the import timestamp, NOT the customer's join date — a master-CSV
    uploaded today gets today's created_at). Optional 'date' mode keeps the created_at
    cutoff for brands whose created_at really is the join date."""
    if mode == "date" and cutoff:
        return {"created_at": {"$lt": cutoff}}
    return {"source": {"$nin": POS_SOURCES}}


def _active_sorted_tiers(cfg: dict) -> List[dict]:
    tiers = [t for t in (cfg.get("tier_rules") or []) if t.get("is_active", True)]
    return sorted(tiers, key=lambda t: float(t.get("min_lifetime_spend") or 0))


def _proposed_tier_switch(sorted_tiers: List[dict]) -> dict:
    """$switch expr → the configured tier SLUG a customer belongs in, by lifetime_spend
    (highest band whose min is reached). Mirrors historic_routes._derive_tier."""
    spend = {"$ifNull": ["$lifetime_spend", 0]}
    branches = [
        {"case": {"$gte": [spend, float(t.get("min_lifetime_spend") or 0)]}, "then": t.get("tier")}
        for t in reversed(sorted_tiers)
    ]
    return {"$switch": {"branches": branches, "default": sorted_tiers[0].get("tier")}}


@router.post("/retier/preview")
async def retier_preview(payload: dict, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    mode = (payload or {}).get("mode") or "source"
    cutoff = (payload or {}).get("cutoff_date") or DEFAULT_RETIER_CUTOFF
    cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0, "tier_rules": 1}) or {}
    sorted_tiers = _active_sorted_tiers(cfg)
    if not sorted_tiers:
        raise HTTPException(400, "No active tiers are configured")
    name_map = {t["tier"]: (t.get("name") or t["tier"]) for t in sorted_tiers}

    # Source breakdown so the user can see exactly which customers count as "old".
    src_rows = await customers_col.aggregate(
        [{"$group": {"_id": "$source", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}],
        maxTimeMS=60000).to_list(100)
    source_breakdown = [{"source": r["_id"] or "—", "count": r["count"],
                         "is_pos": r["_id"] in POS_SOURCES} for r in src_rows]

    pipeline = [
        {"$match": _old_customer_filter(mode, cutoff)},
        {"$set": {"__proposed": _proposed_tier_switch(sorted_tiers)}},
        {"$group": {"_id": {"old": "$tier", "new": "$__proposed"}, "count": {"$sum": 1}}},
    ]
    pairs = await customers_col.aggregate(pipeline, allowDiskUse=True, maxTimeMS=120000).to_list(5000)

    total = changed = 0
    cur: Dict[str, int] = {}
    prop: Dict[str, int] = {}
    for p in pairs:
        old = p["_id"].get("old")
        new = p["_id"].get("new")
        c = p["count"]
        total += c
        cur[old] = cur.get(old, 0) + c
        prop[new] = prop.get(new, 0) + c
        if old != new:
            changed += c

    def fmt(d: Dict[str, int]) -> List[dict]:
        return [{"tier": k, "name": name_map.get(k, k or "—"), "count": v}
                for k, v in sorted(d.items(), key=lambda kv: -kv[1])]

    return {
        "mode": mode,
        "cutoff_date": cutoff,
        "source_breakdown": source_breakdown,
        "total_old_customers": total,
        "changed": changed,
        "unchanged": total - changed,
        "current": fmt(cur),
        "proposed": fmt(prop),
        "configured_tiers": [
            {"tier": t["tier"], "name": t.get("name") or t["tier"],
             "min_lifetime_spend": t.get("min_lifetime_spend") or 0,
             "max_lifetime_spend": t.get("max_lifetime_spend")}
            for t in sorted_tiers
        ],
    }


RETIER_BATCH = 1000


def _derive_slug(spend, bands) -> str:
    """bands = [(slug, min_spend), ...] sorted ascending. Highest band whose min is reached."""
    s = spend or 0
    chosen = bands[0][0]
    for slug, lo in bands:
        if s >= lo:
            chosen = slug
    return chosen


async def _run_retier(job_id: str, old_filter: dict, sorted_tiers: List[dict]) -> None:
    """Single paginated pass over OLD customers (batches of RETIER_BATCH, ordered by _id).
    Each batch is a short, bounded query + bulk_write of ONLY the customers whose tier
    differs — so no individual DB operation runs long enough to hit Atlas socket timeouts."""
    try:
        from pymongo import UpdateOne
        bands = [(t["tier"], float(t.get("min_lifetime_spend") or 0)) for t in sorted_tiers]
        total_updated = 0
        processed = 0
        per_tier: Dict[str, int] = {}
        last_id = None
        while True:
            q = dict(old_filter)
            if last_id is not None:
                q["_id"] = {"$gt": last_id}
            docs = await customers_col.find(
                q, {"_id": 1, "tier": 1, "lifetime_spend": 1}
            ).sort("_id", 1).limit(RETIER_BATCH).max_time_ms(45000).to_list(RETIER_BATCH)
            if not docs:
                break
            ops = []
            for d in docs:
                correct = _derive_slug(d.get("lifetime_spend"), bands)
                if d.get("tier") != correct:
                    ops.append(UpdateOne({"_id": d["_id"]},
                                         {"$set": {"tier": correct, "tier_updated_at": _now_iso()}}))
                    per_tier[correct] = per_tier.get(correct, 0) + 1
            if ops:
                res = await customers_col.bulk_write(ops, ordered=False)
                total_updated += res.modified_count
            processed += len(docs)
            last_id = docs[-1]["_id"]
            await retier_jobs_col.update_one({"id": job_id}, {"$set": {
                "updated": total_updated, "processed": processed, "per_tier": per_tier}})
            if len(docs) < RETIER_BATCH:
                break
        await retier_jobs_col.update_one({"id": job_id}, {"$set": {
            "status": "done", "updated": total_updated, "processed": processed,
            "per_tier": per_tier, "current_tier": None, "finished_at": _now_iso()}})
    except Exception as e:  # noqa: BLE001
        await retier_jobs_col.update_one({"id": job_id}, {"$set": {
            "status": "failed", "error": str(e)[:300], "finished_at": _now_iso()}})


@router.post("/retier/apply")
async def retier_apply(payload: dict, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    mode = (payload or {}).get("mode") or "source"
    cutoff = (payload or {}).get("cutoff_date") or DEFAULT_RETIER_CUTOFF
    if await retier_jobs_col.find_one({"status": "running"}):
        raise HTTPException(409, "A re-tier job is already running")
    cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0, "tier_rules": 1}) or {}
    sorted_tiers = _active_sorted_tiers(cfg)
    if not sorted_tiers:
        raise HTTPException(400, "No active tiers are configured")
    old_filter = _old_customer_filter(mode, cutoff)
    try:
        total = await customers_col.count_documents(old_filter, maxTimeMS=15000)
    except Exception:  # noqa: BLE001 — huge collection counts can be slow; fall back to estimate
        total = await customers_col.estimated_document_count()
    job_id = str(uuid.uuid4())
    await retier_jobs_col.insert_one({
        "id": job_id, "status": "running", "mode": mode, "cutoff_date": cutoff,
        "total": total, "updated": 0, "processed": 0, "per_tier": {}, "current_tier": None,
        "started_by": user.get("name") or user.get("email"),
        "started_at": _now_iso(), "finished_at": None, "error": None,
    })
    asyncio.create_task(_run_retier(job_id, old_filter, sorted_tiers))
    await log_audit(user, "loyalty_retier", "loyalty", "retier",
                    {"mode": mode, "cutoff_date": cutoff, "total_customers": total})
    return {"job_id": job_id, "status": "running", "total": total}


@router.get("/retier/status")
async def retier_status(user: dict = Depends(get_current_user)):
    job = await retier_jobs_col.find_one({}, {"_id": 0}, sort=[("started_at", -1)])
    return job or {"status": "none"}


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
