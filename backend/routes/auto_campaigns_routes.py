"""Auto Campaigns — birthday, win-back, abandoned-visit triggers.

Daily worker that scans customer data once per day and fires templated
Karix messages for matching customers. All rules are config-driven via the
`auto_campaign_config` collection so brand managers can enable/disable each
flow without code changes.

Triggers supported (event_trigger names map to comms templates):
    birthday_today       — Customer's birthday is today
    birthday_7d          — Birthday is 7 days from today
    anniversary_today    — Anniversary today (membership anniversary)
    winback_60d          — No visit in 60 days (one-time fire per gap)
    winback_180d         — No visit in 180 days
    abandoned_visit_30d  — Active customer who hasn't visited in 30 days
                           but visited regularly before (recency stretch)

Each fired message is logged into `auto_campaign_log` (audit trail) so the
same customer is never re-fired for the same trigger in the same window.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user, require_roles, MANAGEMENT_ROLES
from database import customers_col, db

logger = logging.getLogger("kazo-fundle.auto_campaigns")

router = APIRouter(prefix="/auto-campaigns", tags=["auto-campaigns"])

auto_campaign_config_col = db["auto_campaign_config"]
auto_campaign_log_col = db["auto_campaign_log"]

# ============================================================
# Rule catalog (canonical list of supported triggers)
# ============================================================
RULES: List[Dict[str, Any]] = [
    {
        "key": "birthday_today",
        "label": "Birthday — Today",
        "description": "Wish the customer on their birthday with a special offer.",
        "category": "lifecycle",
        "default_enabled": True,
        "cooldown_days": 350,  # one greeting per year max
    },
    {
        "key": "birthday_7d",
        "label": "Birthday — 7 days early",
        "description": "Early birthday nudge to drive a visit before the big day.",
        "category": "lifecycle",
        "default_enabled": False,
        "cooldown_days": 350,
    },
    {
        "key": "anniversary_today",
        "label": "Membership Anniversary",
        "description": "Celebrate the customer's membership anniversary with a thank-you offer.",
        "category": "lifecycle",
        "default_enabled": False,
        "cooldown_days": 350,
    },
    {
        "key": "winback_60d",
        "label": "Win-back — 60 days dormant",
        "description": "Re-engage customers who haven't visited in 60 days.",
        "category": "winback",
        "default_enabled": False,
        "cooldown_days": 90,
    },
    {
        "key": "winback_180d",
        "label": "Win-back — 180 days dormant",
        "description": "Major win-back for customers dormant 180+ days.",
        "category": "winback",
        "default_enabled": False,
        "cooldown_days": 180,
    },
    {
        "key": "abandoned_visit_30d",
        "label": "Abandoned Visit — 30 days",
        "description": "Repeat customers (3+ visits) who haven't been seen in 30 days.",
        "category": "winback",
        "default_enabled": False,
        "cooldown_days": 45,
    },
]

RULES_BY_KEY = {r["key"]: r for r in RULES}


# ============================================================
# Config CRUD
# ============================================================
class AutoConfigIn(BaseModel):
    enabled: bool
    template_id: Optional[str] = None
    daily_cap: int = 1000  # max sends per rule per day


@router.get("/rules")
async def list_rules(user: dict = Depends(get_current_user)):
    """List all available auto-campaign rules + their current config."""
    cfgs = await auto_campaign_config_col.find({}, {"_id": 0}).to_list(100)
    by_key = {c["rule_key"]: c for c in cfgs}
    out = []
    for r in RULES:
        cfg = by_key.get(r["key"], {})
        out.append({
            **r,
            "enabled": cfg.get("enabled", r["default_enabled"]),
            "template_id": cfg.get("template_id"),
            "template_name": cfg.get("template_name"),
            "daily_cap": cfg.get("daily_cap", 1000),
            "last_run_at": cfg.get("last_run_at"),
            "last_run_fired": cfg.get("last_run_fired", 0),
            "last_run_skipped": cfg.get("last_run_skipped", 0),
        })
    return {"rules": out}


@router.patch("/rules/{rule_key}")
async def update_rule(rule_key: str, body: AutoConfigIn,
                       user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    if rule_key not in RULES_BY_KEY:
        raise HTTPException(404, "Unknown rule")
    template_name = None
    if body.template_id:
        tpl = await db["communication_templates"].find_one(
            {"id": body.template_id}, {"_id": 0, "name": 1, "status": 1, "channel": 1,
                                          "waba_approval_status": 1, "waba_template_id": 1},
        )
        if not tpl:
            raise HTTPException(400, "Template not found")
        if tpl.get("status") != "active":
            raise HTTPException(400, "Template must be active")
        if tpl["channel"] in {"whatsapp", "rcs"}:
            if not tpl.get("waba_template_id"):
                raise HTTPException(400, "WhatsApp/RCS template needs waba_template_id")
            if tpl.get("waba_approval_status") != "approved":
                raise HTTPException(400, "WhatsApp/RCS template must be approved")
        template_name = tpl.get("name")
    update = {
        "rule_key": rule_key,
        "enabled": body.enabled,
        "template_id": body.template_id,
        "template_name": template_name,
        "daily_cap": max(1, min(int(body.daily_cap or 1000), 100000)),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": user["email"],
    }
    await auto_campaign_config_col.update_one(
        {"rule_key": rule_key},
        {"$set": update},
        upsert=True,
    )
    return update


# ============================================================
# Audience selectors per rule
# ============================================================
def _today_md() -> tuple:
    """Returns today's (month, day) in IST so birthdays line up to the brand's TZ."""
    # India is UTC+5:30 — use a fixed offset rather than zoneinfo to keep deps minimal.
    now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    return (now.month, now.day)


def _md_offset(days: int) -> tuple:
    base = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30) + timedelta(days=days)
    return (base.month, base.day)


def _date_n_days_ago(n: int) -> str:
    """ISO date string n days back from today (UTC)."""
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%d")


async def _audience_for_rule(rule_key: str) -> List[Dict[str, Any]]:
    """Return list of candidate customers for a given rule. Caller still
    deduplicates against `auto_campaign_log` to enforce per-rule cooldown."""
    common_projection = {
        "_id": 0, "id": 1, "mobile": 1, "name": 1, "tier": 1, "city": 1,
        "points_balance": 1, "first_purchase_at": 1, "last_visit_at": 1,
        "visit_count": 1, "birthday": 1, "anniversary": 1,
        "wa_opt_in": 1, "sms_opt_in": 1,
    }
    base = {"mobile": {"$nin": [None, ""]}}

    if rule_key in {"birthday_today", "birthday_7d", "anniversary_today"}:
        if rule_key == "birthday_today":
            m, d = _today_md()
            field = "birthday"
        elif rule_key == "birthday_7d":
            m, d = _md_offset(7)
            field = "birthday"
        else:
            m, d = _today_md()
            field = "anniversary"
        # Birthday is stored as ISO string (YYYY-MM-DD). Regex on month-day.
        regex = f"^\\d{{4}}-{m:02d}-{d:02d}"
        return await customers_col.find(
            {**base, field: {"$regex": regex}},
            common_projection,
        ).limit(20000).to_list(20000)

    if rule_key in {"winback_60d", "winback_180d", "abandoned_visit_30d"}:
        if rule_key == "winback_60d":
            cutoff_low = _date_n_days_ago(75)
            cutoff_high = _date_n_days_ago(60)
            match = {**base, "last_visit_at": {"$gte": cutoff_low, "$lte": cutoff_high}}
        elif rule_key == "winback_180d":
            cutoff_low = _date_n_days_ago(200)
            cutoff_high = _date_n_days_ago(180)
            match = {**base, "last_visit_at": {"$gte": cutoff_low, "$lte": cutoff_high}}
        else:  # abandoned_visit_30d — repeat customer (3+ visits) gone quiet 30+ days
            cutoff_low = _date_n_days_ago(45)
            cutoff_high = _date_n_days_ago(30)
            match = {**base, "last_visit_at": {"$gte": cutoff_low, "$lte": cutoff_high},
                       "visit_count": {"$gte": 3}}
        return await customers_col.find(match, common_projection).limit(20000).to_list(20000)

    return []


async def _customer_already_fired(mobile: str, rule_key: str, cooldown_days: int) -> bool:
    """True if we already fired this rule for this mobile within the cooldown."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=cooldown_days)).isoformat()
    existing = await auto_campaign_log_col.find_one(
        {"mobile": mobile, "rule_key": rule_key, "fired_at": {"$gte": cutoff},
         "status": {"$in": ["sent", "queued"]}},
        {"_id": 0, "id": 1},
    )
    return existing is not None


# ============================================================
# Per-rule executor
# ============================================================
async def _run_rule(rule_key: str, dry_run: bool = False) -> Dict[str, Any]:
    """Execute one rule end-to-end. Returns a stats dict."""
    rule = RULES_BY_KEY.get(rule_key)
    if not rule:
        return {"rule_key": rule_key, "error": "unknown_rule", "fired": 0}
    cfg = await auto_campaign_config_col.find_one({"rule_key": rule_key}, {"_id": 0})
    cfg = cfg or {}
    if not cfg.get("enabled", rule["default_enabled"]):
        return {"rule_key": rule_key, "skipped": "disabled", "fired": 0}
    template_id = cfg.get("template_id")
    if not template_id:
        return {"rule_key": rule_key, "skipped": "no_template", "fired": 0}
    daily_cap = int(cfg.get("daily_cap", 1000))

    audience = await _audience_for_rule(rule_key)
    cooldown = rule["cooldown_days"]
    fired, skipped_cooldown, failed = 0, 0, 0

    # Local imports to avoid circular references at module load
    from routes.communications_routes import (
        templates_col, send_sms_karix, send_whatsapp_karix,
        _render, _waba_positional_params, _params_for_customer,
    )
    t = await templates_col.find_one({"id": template_id}, {"_id": 0})
    if not t:
        return {"rule_key": rule_key, "error": "template_missing", "fired": 0}

    for c in audience:
        if fired >= daily_cap:
            break
        if await _customer_already_fired(c["mobile"], rule_key, cooldown):
            skipped_cooldown += 1
            continue
        if dry_run:
            fired += 1
            continue
        params = _params_for_customer(c)
        try:
            if t["channel"] == "sms":
                res = await send_sms_karix(c["mobile"], _render(t["body"], params),
                                              template_id=t["id"], event_trigger=rule_key)
            elif t["channel"] in {"whatsapp", "rcs"}:
                res = await send_whatsapp_karix(c["mobile"], t["waba_template_id"],
                                                  _waba_positional_params(t, params),
                                                  template_id=t["id"], event_trigger=rule_key)
            else:
                res = {"ok": False, "error": "unsupported_channel"}
            ok = res.get("ok", False)
            await auto_campaign_log_col.insert_one({
                "id": uuid.uuid4().hex,
                "rule_key": rule_key,
                "mobile": c["mobile"],
                "customer_id": c.get("id"),
                "template_id": template_id,
                "channel": t["channel"],
                "status": "sent" if ok else "failed",
                "error": None if ok else res.get("error"),
                "fired_at": datetime.now(timezone.utc).isoformat(),
            })
            if ok:
                fired += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            try:
                await auto_campaign_log_col.insert_one({
                    "id": uuid.uuid4().hex,
                    "rule_key": rule_key,
                    "mobile": c["mobile"],
                    "template_id": template_id,
                    "channel": t["channel"],
                    "status": "exception",
                    "error": str(e),
                    "fired_at": datetime.now(timezone.utc).isoformat(),
                })
            except Exception:
                pass

    # Update run stats on the config doc
    await auto_campaign_config_col.update_one(
        {"rule_key": rule_key},
        {"$set": {
            "last_run_at": datetime.now(timezone.utc).isoformat(),
            "last_run_fired": fired,
            "last_run_skipped": skipped_cooldown,
            "last_run_failed": failed,
            "last_run_dry_run": dry_run,
        }},
        upsert=True,
    )
    return {
        "rule_key": rule_key,
        "audience_size": len(audience),
        "fired": fired,
        "skipped_cooldown": skipped_cooldown,
        "failed": failed,
        "dry_run": dry_run,
    }


async def run_all_auto_campaigns() -> Dict[str, Any]:
    """Daily entry-point — called by the scheduler at 10 AM IST every day."""
    out = {"started_at": datetime.now(timezone.utc).isoformat(),
            "rules": []}
    for rule in RULES:
        try:
            res = await _run_rule(rule["key"])
            out["rules"].append(res)
            logger.info(f"auto-campaign {rule['key']}: {res}")
        except Exception as e:
            out["rules"].append({"rule_key": rule["key"], "error": str(e)})
            logger.exception(f"auto-campaign {rule['key']} crashed")
    out["completed_at"] = datetime.now(timezone.utc).isoformat()
    out["total_fired"] = sum(r.get("fired", 0) for r in out["rules"])
    return out


# ============================================================
# Manual endpoints
# ============================================================
@router.post("/rules/{rule_key}/preview")
async def preview_rule(rule_key: str, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    """Preview matching audience for a rule without sending."""
    if rule_key not in RULES_BY_KEY:
        raise HTTPException(404, "Unknown rule")
    rule = RULES_BY_KEY[rule_key]
    audience = await _audience_for_rule(rule_key)
    cooldown = rule["cooldown_days"]
    fireable = 0
    samples = []
    for c in audience:
        on_cooldown = await _customer_already_fired(c["mobile"], rule_key, cooldown)
        if not on_cooldown:
            fireable += 1
            if len(samples) < 10:
                samples.append({"mobile": c["mobile"], "name": c.get("name"),
                                  "tier": c.get("tier"), "city": c.get("city"),
                                  "last_visit_at": c.get("last_visit_at"),
                                  "birthday": c.get("birthday")})
    return {
        "rule_key": rule_key, "rule_label": rule["label"],
        "audience_total": len(audience),
        "fireable_now": fireable,
        "on_cooldown": len(audience) - fireable,
        "samples": samples,
    }


@router.post("/rules/{rule_key}/run")
async def run_rule_now(rule_key: str, dry_run: bool = False,
                          user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    """Fire one rule immediately (or dry-run)."""
    if rule_key not in RULES_BY_KEY:
        raise HTTPException(404, "Unknown rule")
    return await _run_rule(rule_key, dry_run=dry_run)


@router.post("/run-all")
async def run_all_now(dry_run: bool = False,
                        user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    """Fire every enabled rule immediately."""
    out = {"started_at": datetime.now(timezone.utc).isoformat(), "rules": []}
    for rule in RULES:
        try:
            res = await _run_rule(rule["key"], dry_run=dry_run)
            out["rules"].append(res)
        except Exception as e:
            out["rules"].append({"rule_key": rule["key"], "error": str(e)})
    out["completed_at"] = datetime.now(timezone.utc).isoformat()
    out["total_fired"] = sum(r.get("fired", 0) for r in out["rules"])
    return out


@router.get("/log")
async def get_log(rule_key: Optional[str] = None, limit: int = 100,
                    user: dict = Depends(get_current_user)):
    fil = {}
    if rule_key:
        fil["rule_key"] = rule_key
    rows = await auto_campaign_log_col.find(fil, {"_id": 0}).sort("fired_at", -1).limit(min(limit, 500)).to_list(500)
    return {"rows": rows}
