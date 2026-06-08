"""Fundle Brain — extended tool registry.

Adds 21 new tools to Brain's repertoire:
  Support Desk reads/writes (11):
    - list_deactivated_customers, list_unsubscribed
    - list_redeemed_coupons, list_redeemed_points
    - support_desk_audit_log
    - customer_deactivate, customer_reactivate            [WRITE]
    - unsubscribe_customer, resubscribe_customer          [WRITE]
    - reactivate_coupon_redemption, reactivate_redeem_points [WRITE]

  Legacy reports / data (6):
    - fraud_anomalies
    - pending_bills_summary
    - expiry_points_summary
    - active_coupons_summary
    - location_wise_customer_summary
    - top_customers_report

  Other useful capabilities (4):
    - customer_search
    - recent_bills_for_customer
    - points_ledger_for_customer
    - tickets_summary

Every WRITE tool enforces role membership in
  {super_admin, brand_admin, support_agent}
and emits a `support_desk.*` audit log entry via `auth.log_audit`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from database import (
    customers_col, transactions_col, stores_col, coupons_col,
    coupon_redemptions_col, points_ledger_col, tickets_col,
    audit_logs_col,
)


# ----------------- Helpers -----------------
WRITE_ROLES = {"super_admin", "brand_admin", "support_agent"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm_mobile(m: Optional[str]) -> Optional[str]:
    if not m:
        return None
    s = "".join(ch for ch in str(m) if ch.isdigit())
    if s.startswith("91") and len(s) > 10:
        s = s[2:]
    if len(s) >= 10:
        return s[-10:]
    return s if len(s) >= 7 else None


def _require_write_role(user: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return None if role OK, otherwise an error dict for the model."""
    if not user:
        return {"error": "User context missing — write actions require an authenticated session."}
    if user.get("is_demo"):
        return {"error": "This is a read-only demo account — write actions (deactivate, unsubscribe, reactivate, etc.) are disabled."}
    role = user.get("role") or user.get("primary_role")
    if role not in WRITE_ROLES:
        return {"error": f"Permission denied. Write actions require one of {sorted(WRITE_ROLES)}; your role is '{role}'."}
    return None


async def _log(user: Optional[Dict[str, Any]], action: str, entity: str, entity_id: str, metadata: Dict[str, Any]) -> None:
    if not user:
        return
    await audit_logs_col.insert_one({
        "id": str(uuid.uuid4()),
        "action": action,
        "entity": entity,
        "entity_id": entity_id,
        "user_id": user.get("id"),
        "user_email": user.get("email"),
        "metadata": metadata,
        "timestamp": _now_iso(),
        "source": "fundle_brain",
    })


# ============================================================
# Support Desk reads
# ============================================================
async def _tool_list_deactivated_customers(q: Optional[str] = None, limit: int = 50, user=None) -> Dict[str, Any]:
    fil: Dict[str, Any] = {"is_active": False}
    if q:
        norm = _norm_mobile(q)
        if norm:
            fil["mobile"] = norm
        else:
            fil["name"] = {"$regex": q, "$options": "i"}
    rows = await customers_col.find(fil, {"_id": 0, "mobile": 1, "name": 1, "deactivated_at": 1, "deactivation_reason": 1, "deactivated_by": 1}).sort("deactivated_at", -1).limit(limit).to_list(limit)
    return {"total": len(rows), "rows": rows}


async def _tool_list_unsubscribed(channel: Optional[str] = None, limit: int = 100, user=None) -> Dict[str, Any]:
    fil: Dict[str, Any] = {"unsubscribed": {"$exists": True, "$ne": {}}}
    if channel and channel != "all":
        fil[f"unsubscribed.{channel}"] = True
    rows = await customers_col.find(fil, {"_id": 0, "mobile": 1, "name": 1, "unsubscribed": 1, "unsubscribed_at": 1, "unsubscribed_reason": 1}).sort("unsubscribed_at", -1).limit(limit).to_list(limit)
    for r in rows:
        u = r.get("unsubscribed") or {}
        r["unsub_channels"] = sorted([k for k, v in u.items() if v])
    return {"total": len(rows), "rows": rows}


async def _tool_list_redeemed_coupons(mobile: Optional[str] = None, days: int = 30, limit: int = 30, user=None) -> Dict[str, Any]:
    fil: Dict[str, Any] = {}
    norm = _norm_mobile(mobile)
    if norm:
        fil["customer_mobile"] = norm
    if days and days > 0:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        fil["redeemed_at"] = {"$gte": cutoff}
    rows = await coupon_redemptions_col.find(fil, {"_id": 0}).sort("redeemed_at", -1).limit(limit).to_list(limit)
    return {"total": len(rows), "rows": rows}


async def _tool_list_redeemed_points(mobile: Optional[str] = None, days: int = 30, limit: int = 30, user=None) -> Dict[str, Any]:
    fil: Dict[str, Any] = {"kind": {"$in": ["redeem", "redemption"]}}
    norm = _norm_mobile(mobile)
    if norm:
        fil["customer_mobile"] = norm
    if days and days > 0:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        fil["created_at"] = {"$gte": cutoff}
    rows = await points_ledger_col.find(fil, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"total": len(rows), "rows": rows}


async def _tool_support_desk_audit_log(action: Optional[str] = None, days: int = 7, limit: int = 30, user=None) -> Dict[str, Any]:
    fil: Dict[str, Any] = {"action": {"$regex": "^support_desk\\."}}
    if action:
        fil["action"] = {"$regex": action, "$options": "i"}
    if days and days > 0:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        fil["timestamp"] = {"$gte": cutoff}
    rows = await audit_logs_col.find(fil, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    summary: Dict[str, int] = {}
    for r in rows:
        a = (r.get("action") or "").replace("support_desk.", "")
        summary[a] = summary.get(a, 0) + 1
    return {"total": len(rows), "by_action": summary, "rows": rows}


# ============================================================
# Support Desk writes (role-gated)
# ============================================================
async def _tool_customer_deactivate(mobile: str, reason: str, user=None) -> Dict[str, Any]:
    err = _require_write_role(user)
    if err:
        return err
    norm = _norm_mobile(mobile)
    if not norm:
        return {"error": "Invalid mobile"}
    cust = await customers_col.find_one({"mobile": norm}, {"_id": 0})
    if not cust:
        return {"error": f"No customer with mobile {norm}"}
    if cust.get("is_active") is False:
        return {"error": "Customer already deactivated", "mobile": norm}
    await customers_col.update_one({"mobile": norm}, {"$set": {
        "is_active": False, "deactivated_at": _now_iso(),
        "deactivated_by": user.get("email"), "deactivation_reason": reason,
    }})
    await _log(user, "support_desk.customer_deactivate", "customer", norm,
               {"reason": reason, "via": "fundle_brain"})
    return {"ok": True, "mobile": norm, "name": cust.get("name"),
            "message": f"Customer {cust.get('name') or norm} deactivated."}


async def _tool_customer_reactivate(mobile: str, reason: str, user=None) -> Dict[str, Any]:
    err = _require_write_role(user)
    if err:
        return err
    norm = _norm_mobile(mobile)
    if not norm:
        return {"error": "Invalid mobile"}
    cust = await customers_col.find_one({"mobile": norm}, {"_id": 0})
    if not cust:
        return {"error": f"No customer with mobile {norm}"}
    if cust.get("is_active") is not False:
        return {"error": "Customer already active", "mobile": norm}
    await customers_col.update_one({"mobile": norm}, {
        "$set": {"is_active": True, "reactivated_at": _now_iso(),
                 "reactivated_by": user.get("email"), "reactivation_reason": reason},
        "$unset": {"deactivated_at": "", "deactivation_reason": ""},
    })
    await _log(user, "support_desk.customer_reactivate", "customer", norm,
               {"reason": reason, "via": "fundle_brain"})
    return {"ok": True, "mobile": norm, "message": f"Customer {cust.get('name') or norm} reactivated."}


async def _tool_unsubscribe_customer(mobile: str, channel: str = "all", reason: Optional[str] = None, user=None) -> Dict[str, Any]:
    err = _require_write_role(user)
    if err:
        return err
    norm = _norm_mobile(mobile)
    if not norm:
        return {"error": "Invalid mobile"}
    cust = await customers_col.find_one({"mobile": norm}, {"_id": 0})
    if not cust:
        return {"error": f"No customer with mobile {norm}"}
    unsub = cust.get("unsubscribed", {}) or {}
    if channel == "all":
        unsub = {"sms": True, "whatsapp": True, "email": True, "rcs": True}
    else:
        unsub[channel] = True
    await customers_col.update_one({"mobile": norm}, {"$set": {
        "unsubscribed": unsub, "unsubscribed_at": _now_iso(),
        "unsubscribed_by": user.get("email"), "unsubscribed_reason": reason,
    }})
    await _log(user, "support_desk.unsubscribe", "customer", norm,
               {"channel": channel, "reason": reason, "via": "fundle_brain"})
    return {"ok": True, "mobile": norm, "channel": channel, "unsubscribed_now": sorted(unsub.keys())}


async def _tool_resubscribe_customer(mobile: str, channel: str = "all", user=None) -> Dict[str, Any]:
    err = _require_write_role(user)
    if err:
        return err
    norm = _norm_mobile(mobile)
    if not norm:
        return {"error": "Invalid mobile"}
    cust = await customers_col.find_one({"mobile": norm}, {"_id": 0})
    if not cust:
        return {"error": f"No customer with mobile {norm}"}
    unsub = cust.get("unsubscribed", {}) or {}
    if channel == "all":
        unsub = {}
    else:
        unsub.pop(channel, None)
    await customers_col.update_one({"mobile": norm}, {"$set": {
        "unsubscribed": unsub, "resubscribed_at": _now_iso(), "resubscribed_by": user.get("email"),
    }})
    await _log(user, "support_desk.resubscribe", "customer", norm,
               {"channel": channel, "via": "fundle_brain"})
    return {"ok": True, "mobile": norm, "channel": channel, "remaining_unsub": sorted(unsub.keys())}


async def _tool_reactivate_coupon_redemption(redemption_id: str, reason: str, user=None) -> Dict[str, Any]:
    err = _require_write_role(user)
    if err:
        return err
    red = await coupon_redemptions_col.find_one({"id": redemption_id}, {"_id": 0})
    if not red:
        return {"error": f"No redemption with id {redemption_id}"}
    if red.get("reversed"):
        return {"error": "Already reversed"}
    await coupon_redemptions_col.update_one({"id": redemption_id}, {"$set": {
        "reversed": True, "reversed_at": _now_iso(),
        "reversed_by": user.get("email"), "reversal_reason": reason,
    }})
    code = red.get("code")
    if code:
        await coupons_col.update_one({"code": code}, {"$inc": {"uses_count": -1}})
    await _log(user, "support_desk.reactivate_coupon", "coupon_redemption", redemption_id,
               {"code": code, "reason": reason, "via": "fundle_brain"})
    return {"ok": True, "redemption_id": redemption_id, "code": code,
            "message": f"Coupon {code} reactivated for reuse."}


async def _tool_reactivate_redeem_points(ledger_id: str, reason: str, user=None) -> Dict[str, Any]:
    err = _require_write_role(user)
    if err:
        return err
    led = await points_ledger_col.find_one({"id": ledger_id}, {"_id": 0})
    if not led:
        return {"error": f"No ledger entry with id {ledger_id}"}
    if led.get("reversed"):
        return {"error": "Already reversed"}
    points = abs(int(led.get("points", 0)))
    mobile = led.get("customer_mobile")
    if not mobile or points == 0:
        return {"error": "Missing mobile or zero points"}
    await points_ledger_col.update_one({"id": ledger_id}, {"$set": {
        "reversed": True, "reversed_at": _now_iso(),
        "reversed_by": user.get("email"), "reversal_reason": reason,
    }})
    await points_ledger_col.insert_one({
        "id": str(uuid.uuid4()),
        "customer_mobile": mobile,
        "points": points,
        "kind": "reversal",
        "reason": f"Reversal of redemption {ledger_id} — {reason}",
        "linked_ledger_id": ledger_id,
        "created_at": _now_iso(),
        "created_by": user.get("email"),
    })
    await customers_col.update_one({"mobile": mobile}, {"$inc": {
        "points_balance": points, "lifetime_points_redeemed": -points,
    }})
    await _log(user, "support_desk.reactivate_redeem_points", "points_ledger", ledger_id,
               {"mobile": mobile, "points": points, "reason": reason, "via": "fundle_brain"})
    return {"ok": True, "ledger_id": ledger_id, "mobile": mobile,
            "points_restored": points, "message": f"{points} points restored to {mobile}."}


# ============================================================
# Legacy reports — read tools
# ============================================================
async def _tool_fraud_anomalies(days: int = 30, limit: int = 20, user=None) -> Dict[str, Any]:
    cutoff_iso = ""
    if days and days > 0:
        cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    pipeline = [
        {"$match": {"customer_mobile": {"$nin": [None, ""]}, **({"bill_date": {"$gte": cutoff_iso}} if cutoff_iso else {})}},
        {"$project": {"customer_mobile": 1, "bill_number": 1, "net_amount": 1, "store_id": 1,
                      "hour_bucket": {"$substr": ["$bill_date", 0, 13]}}},
        {"$group": {"_id": {"mobile": "$customer_mobile", "hour": "$hour_bucket"},
                    "bills": {"$sum": 1}, "total_amount": {"$sum": "$net_amount"},
                    "bill_numbers": {"$push": "$bill_number"}, "stores": {"$addToSet": "$store_id"}}},
        {"$match": {"bills": {"$gte": 3}}},
        {"$sort": {"bills": -1}},
        {"$limit": limit},
    ]
    flags = []
    async for d in transactions_col.aggregate(pipeline):
        flags.append({
            "type": "rapid_fire_bills",
            "severity": "high" if d["bills"] >= 5 else "medium",
            "customer_mobile": d["_id"]["mobile"],
            "hour": d["_id"]["hour"],
            "bill_count": d["bills"],
            "total_amount": d["total_amount"],
            "store_count": len(d["stores"]),
            "bill_numbers": d["bill_numbers"][:5],
        })
    async for r in points_ledger_col.find(
        {"kind": {"$in": ["redeem", "redemption"]}, "points": {"$lte": -10000}},
        {"_id": 0},
    ).sort("created_at", -1).limit(20):
        flags.append({
            "type": "large_redemption", "severity": "medium",
            "customer_mobile": r.get("customer_mobile"),
            "points": abs(r.get("points", 0)), "bill_number": r.get("bill_number"),
            "ledger_id": r.get("id"), "created_at": r.get("created_at"),
        })
    return {"total": len(flags), "flags": flags}


async def _tool_pending_bills_summary(days: int = 30, limit: int = 20, user=None) -> Dict[str, Any]:
    fil: Dict[str, Any] = {
        "customer_mobile": {"$nin": [None, ""]},
        "$or": [{"points_earned": {"$in": [0, None]}}, {"points_earned": {"$exists": False}}],
    }
    if days and days > 0:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        fil["bill_date"] = {"$gte": cutoff}
    total = await transactions_col.count_documents(fil)
    rows = await transactions_col.find(fil, {"_id": 0, "bill_number": 1, "customer_mobile": 1,
                                              "net_amount": 1, "bill_date": 1, "store_id": 1}).sort("bill_date", -1).limit(limit).to_list(limit)
    return {"total_pending": total, "sample": rows}


async def _tool_expiry_points_summary(days_ahead: int = 60, tier: Optional[str] = None, limit: int = 25, user=None) -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    cutoff = (datetime.now(timezone.utc) + timedelta(days=days_ahead)).isoformat()
    pipeline = [
        {"$match": {"kind": {"$in": ["earn", "bonus"]}, "expires_at": {"$lte": cutoff, "$gte": now_iso},
                    "reversed": {"$ne": True}}},
        {"$group": {"_id": "$customer_mobile", "expiring_points": {"$sum": "$points"},
                    "earliest_expiry": {"$min": "$expires_at"}}},
        {"$sort": {"expiring_points": -1}},
        {"$limit": limit},
    ]
    rows = []
    total_pts = 0
    async for d in points_ledger_col.aggregate(pipeline):
        cust = await customers_col.find_one({"mobile": d["_id"]}, {"_id": 0, "name": 1, "tier": 1})
        if not cust:
            continue
        if tier and cust.get("tier") != tier:
            continue
        total_pts += d["expiring_points"]
        rows.append({
            "mobile": d["_id"], "name": cust.get("name"), "tier": cust.get("tier"),
            "expiring_points": d["expiring_points"], "earliest_expiry": d["earliest_expiry"],
        })
    return {"days_ahead": days_ahead, "total_customers_with_expiring_pts": len(rows),
            "total_expiring_points": total_pts, "top_at_risk": rows}


async def _tool_active_coupons_summary(code_prefix: Optional[str] = None, limit: int = 25, user=None) -> Dict[str, Any]:
    fil: Dict[str, Any] = {"is_active": True}
    if code_prefix:
        fil["code"] = {"$regex": f"^{code_prefix}", "$options": "i"}
    total = await coupons_col.count_documents(fil)
    rows = await coupons_col.find(fil, {"_id": 0, "code": 1, "name": 1, "discount_value": 1,
                                         "discount_type": 1, "valid_from": 1, "valid_to": 1,
                                         "times_used": 1, "times_issued": 1}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"total_active": total, "rows": rows}


async def _tool_location_wise_customer_summary(limit: int = 15, user=None) -> Dict[str, Any]:
    pipeline = [
        {"$match": {"home_store_id": {"$exists": True, "$ne": None}}},
        {"$group": {"_id": "$home_store_id", "customer_count": {"$sum": 1},
                    "lifetime_spend": {"$sum": "$lifetime_spend"},
                    "total_visits": {"$sum": "$visit_count"}}},
        {"$sort": {"customer_count": -1}},
        {"$limit": limit},
    ]
    rows: List[Dict[str, Any]] = []
    async for d in customers_col.aggregate(pipeline):
        store = await stores_col.find_one({"id": d["_id"]}, {"_id": 0, "name": 1, "city": 1, "code": 1})
        rows.append({
            "store_code": (store or {}).get("code"),
            "store_name": (store or {}).get("name") or d["_id"],
            "city": (store or {}).get("city"),
            "customer_count": d["customer_count"],
            "total_visits": d.get("total_visits", 0),
            "lifetime_spend": d.get("lifetime_spend", 0),
        })
    return {"top_stores_by_customers": rows}


async def _tool_top_customers_report(by: str = "purchase", tier: Optional[str] = None, limit: int = 15, user=None) -> Dict[str, Any]:
    fil: Dict[str, Any] = {}
    if tier:
        fil["tier"] = tier
    sort_field = {"purchase": "lifetime_spend", "visits": "visit_count", "points": "points_balance"}.get(by, "lifetime_spend")
    rows = await customers_col.find(fil, {"_id": 0, "mobile": 1, "name": 1, "tier": 1,
                                           "visit_count": 1, "lifetime_spend": 1, "points_balance": 1,
                                           "home_store_id": 1}).sort(sort_field, -1).limit(limit).to_list(limit)
    return {"sort_by": sort_field, "rows": rows}


# ============================================================
# Other useful capabilities
# ============================================================
async def _tool_customer_search(q: str, limit: int = 10, user=None) -> Dict[str, Any]:
    norm = _norm_mobile(q)
    fil: Dict[str, Any] = {}
    if norm:
        fil["mobile"] = {"$regex": norm}
    else:
        fil["$or"] = [{"name": {"$regex": q, "$options": "i"}},
                       {"email": {"$regex": q, "$options": "i"}}]
    rows = await customers_col.find(fil, {"_id": 0, "mobile": 1, "name": 1, "email": 1,
                                           "tier": 1, "visit_count": 1, "lifetime_spend": 1,
                                           "points_balance": 1, "is_active": 1}).limit(limit).to_list(limit)
    return {"total": len(rows), "rows": rows}


async def _tool_recent_bills_for_customer(mobile: str, limit: int = 10, user=None) -> Dict[str, Any]:
    norm = _norm_mobile(mobile)
    if not norm:
        return {"error": "Invalid mobile"}
    rows = await transactions_col.find({"customer_mobile": norm}, {"_id": 0, "bill_number": 1,
                                                                     "bill_date": 1, "net_amount": 1,
                                                                     "gross_amount": 1, "store_id": 1,
                                                                     "points_earned": 1, "points_redeemed": 1}).sort("bill_date", -1).limit(limit).to_list(limit)
    return {"mobile": norm, "total": len(rows), "rows": rows}


async def _tool_points_ledger_for_customer(mobile: str, kind: Optional[str] = None, limit: int = 20, user=None) -> Dict[str, Any]:
    norm = _norm_mobile(mobile)
    if not norm:
        return {"error": "Invalid mobile"}
    fil: Dict[str, Any] = {"customer_mobile": norm}
    if kind:
        fil["kind"] = kind
    rows = await points_ledger_col.find(fil, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    # Quick summary by kind
    summary: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        k = r.get("kind", "?")
        s = summary.setdefault(k, {"count": 0, "points": 0})
        s["count"] += 1
        s["points"] += int(r.get("points", 0))
    return {"mobile": norm, "summary_by_kind": summary, "rows": rows}


async def _tool_tickets_summary(status: Optional[str] = None, days: int = 30, user=None) -> Dict[str, Any]:
    fil: Dict[str, Any] = {}
    if status:
        fil["status"] = status
    if days and days > 0:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        fil["created_at"] = {"$gte": cutoff}
    rows = await tickets_col.find(fil, {"_id": 0, "id": 1, "status": 1, "priority": 1,
                                         "subject": 1, "customer_mobile": 1, "created_at": 1,
                                         "assigned_to": 1}).sort("created_at", -1).limit(30).to_list(30)
    by_status: Dict[str, int] = {}
    by_priority: Dict[str, int] = {}
    async for t in tickets_col.find(fil, {"status": 1, "priority": 1}):
        by_status[t.get("status", "?")] = by_status.get(t.get("status", "?"), 0) + 1
        by_priority[t.get("priority", "?")] = by_priority.get(t.get("priority", "?"), 0) + 1
    return {"by_status": by_status, "by_priority": by_priority, "recent": rows}


# ============================================================
# Schemas (OpenAI function-calling format)
# ============================================================
EXTRA_TOOL_SCHEMAS: List[Dict[str, Any]] = [
    # ---- Support Desk reads ----
    {"type": "function", "function": {
        "name": "list_deactivated_customers",
        "description": "List customers currently deactivated. Use when asked 'who is deactivated', 'show inactive customers', 'list opt-outs by customer'. Optional q filter by mobile or name.",
        "parameters": {"type": "object", "properties": {
            "q": {"type": "string", "description": "Optional search by name or mobile"},
            "limit": {"type": "integer", "default": 50},
        }},
    }},
    {"type": "function", "function": {
        "name": "list_unsubscribed",
        "description": "List customers who have opted out from one or more channels (sms/whatsapp/rcs/email). Use when asked about DND list, opt-out count, who unsubscribed.",
        "parameters": {"type": "object", "properties": {
            "channel": {"type": "string", "enum": ["all", "sms", "whatsapp", "rcs", "email"], "description": "Filter by specific channel"},
            "limit": {"type": "integer", "default": 100},
        }},
    }},
    {"type": "function", "function": {
        "name": "list_redeemed_coupons",
        "description": "Recent coupon redemptions. Use when asked 'what coupons were redeemed', 'show coupon usage', or before reversing a redemption (so you can find its redemption_id).",
        "parameters": {"type": "object", "properties": {
            "mobile": {"type": "string", "description": "Optional customer mobile filter"},
            "days": {"type": "integer", "default": 30, "description": "Look back this many days; 0 = all time"},
            "limit": {"type": "integer", "default": 30},
        }},
    }},
    {"type": "function", "function": {
        "name": "list_redeemed_points",
        "description": "Recent point-redemption ledger entries. Use to find a ledger_id before reversing a points redemption.",
        "parameters": {"type": "object", "properties": {
            "mobile": {"type": "string"},
            "days": {"type": "integer", "default": 30},
            "limit": {"type": "integer", "default": 30},
        }},
    }},
    {"type": "function", "function": {
        "name": "support_desk_audit_log",
        "description": "Read the support desk audit trail — every deactivate, reactivate, unsubscribe, coupon/points reversal. Use for compliance questions, 'who did what', or 'what reversals happened last week'.",
        "parameters": {"type": "object", "properties": {
            "action": {"type": "string", "description": "Optional sub-action filter, e.g. 'reactivate_coupon', 'customer_deactivate'"},
            "days": {"type": "integer", "default": 7},
            "limit": {"type": "integer", "default": 30},
        }},
    }},

    # ---- Support Desk writes ----
    {"type": "function", "function": {
        "name": "customer_deactivate",
        "description": "MUTATION — deactivate a customer (sets is_active=false; they stop receiving campaigns). Requires super_admin/brand_admin/support_agent role. Always confirm intent with the user before calling. Audit logged.",
        "parameters": {"type": "object", "properties": {
            "mobile": {"type": "string", "description": "Customer mobile (10 digits or legacy 9)"},
            "reason": {"type": "string", "description": "Human-readable reason (required for audit)"},
        }, "required": ["mobile", "reason"]},
    }},
    {"type": "function", "function": {
        "name": "customer_reactivate",
        "description": "MUTATION — restore a previously deactivated customer. Requires admin/support role.",
        "parameters": {"type": "object", "properties": {
            "mobile": {"type": "string"},
            "reason": {"type": "string"},
        }, "required": ["mobile", "reason"]},
    }},
    {"type": "function", "function": {
        "name": "unsubscribe_customer",
        "description": "MUTATION — opt a customer out of one or all communication channels. Use when a customer asks to be removed from campaigns. Channel='all' is the safest default. Audit logged. Requires admin/support role.",
        "parameters": {"type": "object", "properties": {
            "mobile": {"type": "string"},
            "channel": {"type": "string", "enum": ["all", "sms", "whatsapp", "rcs", "email"], "default": "all"},
            "reason": {"type": "string"},
        }, "required": ["mobile"]},
    }},
    {"type": "function", "function": {
        "name": "resubscribe_customer",
        "description": "MUTATION — clear a customer's opt-out for one or all channels. Use only after explicit customer consent.",
        "parameters": {"type": "object", "properties": {
            "mobile": {"type": "string"},
            "channel": {"type": "string", "enum": ["all", "sms", "whatsapp", "rcs", "email"], "default": "all"},
        }, "required": ["mobile"]},
    }},
    {"type": "function", "function": {
        "name": "reactivate_coupon_redemption",
        "description": "MUTATION — reverse a coupon redemption so the coupon becomes reusable. Always find the redemption_id first via list_redeemed_coupons. Requires admin/support role.",
        "parameters": {"type": "object", "properties": {
            "redemption_id": {"type": "string"},
            "reason": {"type": "string"},
        }, "required": ["redemption_id", "reason"]},
    }},
    {"type": "function", "function": {
        "name": "reactivate_redeem_points",
        "description": "MUTATION — reverse a points redemption (restores points to the customer's balance). Find the ledger_id first via list_redeemed_points. Requires admin/support role.",
        "parameters": {"type": "object", "properties": {
            "ledger_id": {"type": "string"},
            "reason": {"type": "string"},
        }, "required": ["ledger_id", "reason"]},
    }},

    # ---- Legacy reports ----
    {"type": "function", "function": {
        "name": "fraud_anomalies",
        "description": "Detect suspicious patterns: rapid-fire bills (3+ from same mobile in same hour) and large point redemptions (>10000). Use for compliance, audit, 'show me fraud', 'are there any anomalies'.",
        "parameters": {"type": "object", "properties": {
            "days": {"type": "integer", "default": 30},
            "limit": {"type": "integer", "default": 20},
        }},
    }},
    {"type": "function", "function": {
        "name": "pending_bills_summary",
        "description": "Bills ingested but not yet awarded points (points_earned=0/null). Use for ops health checks.",
        "parameters": {"type": "object", "properties": {
            "days": {"type": "integer", "default": 30},
            "limit": {"type": "integer", "default": 20},
        }},
    }},
    {"type": "function", "function": {
        "name": "expiry_points_summary",
        "description": "Which customers are about to lose points (within N days). Use for proactive win-back, expiry campaigns, 'what's expiring this month'.",
        "parameters": {"type": "object", "properties": {
            "days_ahead": {"type": "integer", "default": 60},
            "tier": {"type": "string", "description": "Filter by tier e.g. 'gold'"},
            "limit": {"type": "integer", "default": 25},
        }},
    }},
    {"type": "function", "function": {
        "name": "active_coupons_summary",
        "description": "List currently active coupons. Use when asked 'what coupons are live', 'which promo codes are running', or before recommending one.",
        "parameters": {"type": "object", "properties": {
            "code_prefix": {"type": "string"},
            "limit": {"type": "integer", "default": 25},
        }},
    }},
    {"type": "function", "function": {
        "name": "location_wise_customer_summary",
        "description": "Top stores by customer count (with total visits & lifetime spend). Quick alternative to store_performance when the user wants 'which store has most customers'.",
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "integer", "default": 15},
        }},
    }},
    {"type": "function", "function": {
        "name": "top_customers_report",
        "description": "Top N customers sorted by purchase / visits / points balance. Use for VIP outreach, leaderboards, 'who are our biggest spenders'.",
        "parameters": {"type": "object", "properties": {
            "by": {"type": "string", "enum": ["purchase", "visits", "points"], "default": "purchase"},
            "tier": {"type": "string"},
            "limit": {"type": "integer", "default": 15},
        }},
    }},

    # ---- Other ----
    {"type": "function", "function": {
        "name": "customer_search",
        "description": "Search customers by mobile, name, or email. Returns light profile for each. Use when the user gives a partial name or mobile.",
        "parameters": {"type": "object", "properties": {
            "q": {"type": "string"},
            "limit": {"type": "integer", "default": 10},
        }, "required": ["q"]},
    }},
    {"type": "function", "function": {
        "name": "recent_bills_for_customer",
        "description": "Most recent bills for a specific mobile. Use for dispute resolution, 'show me their purchase history'.",
        "parameters": {"type": "object", "properties": {
            "mobile": {"type": "string"},
            "limit": {"type": "integer", "default": 10},
        }, "required": ["mobile"]},
    }},
    {"type": "function", "function": {
        "name": "points_ledger_for_customer",
        "description": "Recent earn/redeem/bonus/expired/reversal entries for one customer. Use for dispute resolution or 'how did their points reach X'.",
        "parameters": {"type": "object", "properties": {
            "mobile": {"type": "string"},
            "kind": {"type": "string", "enum": ["earn", "redeem", "redemption", "bonus", "expired", "reversal"]},
            "limit": {"type": "integer", "default": 20},
        }, "required": ["mobile"]},
    }},
    {"type": "function", "function": {
        "name": "tickets_summary",
        "description": "Support ticket counts grouped by status & priority. Use for 'how many open tickets', 'what's the support backlog'.",
        "parameters": {"type": "object", "properties": {
            "status": {"type": "string", "description": "Filter to one status, e.g. 'open'"},
            "days": {"type": "integer", "default": 30},
        }},
    }},
]


EXTRA_TOOL_HANDLERS = {
    # reads
    "list_deactivated_customers": _tool_list_deactivated_customers,
    "list_unsubscribed": _tool_list_unsubscribed,
    "list_redeemed_coupons": _tool_list_redeemed_coupons,
    "list_redeemed_points": _tool_list_redeemed_points,
    "support_desk_audit_log": _tool_support_desk_audit_log,
    # writes
    "customer_deactivate": _tool_customer_deactivate,
    "customer_reactivate": _tool_customer_reactivate,
    "unsubscribe_customer": _tool_unsubscribe_customer,
    "resubscribe_customer": _tool_resubscribe_customer,
    "reactivate_coupon_redemption": _tool_reactivate_coupon_redemption,
    "reactivate_redeem_points": _tool_reactivate_redeem_points,
    # legacy reports
    "fraud_anomalies": _tool_fraud_anomalies,
    "pending_bills_summary": _tool_pending_bills_summary,
    "expiry_points_summary": _tool_expiry_points_summary,
    "active_coupons_summary": _tool_active_coupons_summary,
    "location_wise_customer_summary": _tool_location_wise_customer_summary,
    "top_customers_report": _tool_top_customers_report,
    # other
    "customer_search": _tool_customer_search,
    "recent_bills_for_customer": _tool_recent_bills_for_customer,
    "points_ledger_for_customer": _tool_points_ledger_for_customer,
    "tickets_summary": _tool_tickets_summary,
}
