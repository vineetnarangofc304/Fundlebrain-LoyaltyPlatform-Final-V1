"""Master Brain — privileged ACTION tools (write-back to the database).

Master Brain = Fundle Brain (read) + this action layer. Only users with
`is_master_admin == True` may execute these. Every mutating tool follows a
two-step protocol so nothing is ever changed without explicit human approval:

    1. The model FIRST calls the tool with confirm=false  -> returns a PREVIEW
       (what will change, affected count, sample) and mutates NOTHING.
    2. After the human approves AND gives a reason, the model calls again with
       confirm=true + reason -> the action runs, is AUDIT-LOGGED (who/when/why
       + before->after) and a result is returned.

Points changes always write a `points_ledger` row (never silent) so they are
traceable and reversible. Audit entries use action `master_brain.*`.
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from pymongo import UpdateOne
from database import (
    customers_col, points_ledger_col, audit_logs_col, loyalty_config_col,
    mb_action_snapshots_col, master_campaigns_col,
)

# Inline apply is bounded to keep the chat request fast; bigger jobs are routed
# to the dedicated batched re-tier tool on the Loyalty Rules page.
INLINE_CAP = 20000
BATCH = 1000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_master(user: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not user:
        return {"error": "User context missing — Master Brain actions require an authenticated session."}
    if user.get("is_demo"):
        return {"error": "This is a read-only demo account — Master Brain actions are disabled."}
    if not user.get("is_master_admin"):
        return {"error": "Permission denied. Master Brain actions require Master Admin rights. "
                         "Ask a super admin to grant 'Master Admin' in User Management."}
    return None


def _mobile_candidates(mobile: Any):
    raw = str(mobile or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    strs = set()
    if raw:
        strs.add(raw)
    if digits:
        strs.add(digits)
        strs.add(digits[-10:])
        strs.add("91" + digits[-10:])
    ints = set()
    for c in list(strs):
        if c.isdigit():
            try:
                ints.add(int(c))
            except Exception:
                pass
    return list(strs), list(ints)


async def _find_customer(mobile: Any) -> Optional[Dict[str, Any]]:
    strs, ints = _mobile_candidates(mobile)
    if not strs and not ints:
        return None
    return await customers_col.find_one({"mobile": {"$in": strs + ints}}, {"_id": 0})


async def _log_master(user: Dict[str, Any], action: str, entity: str, entity_id: str,
                      reason: str, metadata: Dict[str, Any]) -> str:
    doc_id = str(uuid.uuid4())
    await audit_logs_col.insert_one({
        "id": doc_id,
        "action": f"master_brain.{action}",
        "entity": entity,
        "entity_id": entity_id,
        "user_id": user.get("id"),
        "user_email": user.get("email"),
        "user_name": user.get("name"),
        "reason": reason,
        "metadata": metadata,
        "source": "master_brain",
        "timestamp": _now_iso(),
    })
    return doc_id


async def _ledger(mobile: str, points: int, kind: str, reason: str, user: Dict[str, Any],
                  extra: Optional[Dict[str, Any]] = None) -> None:
    doc = {
        "id": str(uuid.uuid4()),
        "customer_mobile": mobile,
        "points": int(points),
        "type": kind,
        "kind": kind,
        "reference_type": "master_brain",
        "reason": reason,
        "created_at": _now_iso(),
        "created_by": user.get("email"),
        "via": "master_brain",
    }
    if extra:
        doc.update(extra)
    await points_ledger_col.insert_one(doc)


def _need_reason(reason: str) -> Optional[Dict[str, Any]]:
    if not (reason or "").strip():
        return {"error": "A reason is mandatory to apply this action. Ask the user for a business reason, "
                         "then call again with confirm=true and the reason."}
    return None


# ============================================================
# 1) Grant bonus points to ONE customer
# ============================================================
async def _tool_grant_bonus_points(mobile: str, points: int, reason: str = "",
                                   confirm: bool = False, user=None) -> Dict[str, Any]:
    err = _require_master(user)
    if err:
        return err
    try:
        points = int(points)
    except Exception:
        return {"error": "points must be a positive integer"}
    if points <= 0:
        return {"error": "points must be a positive integer (use adjust_points to deduct)"}
    cust = await _find_customer(mobile)
    if not cust:
        return {"found": False, "mobile": mobile, "error": "No customer found for that mobile."}
    cur = int(cust.get("points_balance") or 0)
    plan = {
        "action": "grant_bonus_points", "mobile": cust.get("mobile"), "name": cust.get("name"),
        "current_balance": cur, "points_to_add": points, "new_balance_after": cur + points,
    }
    if not confirm:
        plan["preview"] = True
        plan["confirmation_required"] = ("Confirm with the user, capture a reason, then call again "
                                         "with confirm=true and reason.")
        return plan
    rerr = _need_reason(reason)
    if rerr:
        return rerr
    await customers_col.update_one({"id": cust["id"]}, {"$inc": {
        "points_balance": points, "lifetime_points_earned": points}})
    await _ledger(cust.get("mobile"), points, "bonus", reason, user)
    lt_before = int(cust.get("lifetime_points_earned") or 0)
    audit_id = await _log_master(user, "grant_bonus_points", "customer", cust.get("id"), reason,
                                 {"mobile": cust.get("mobile"), "points": points,
                                  "balance_before": cur, "balance_after": cur + points})
    await _record_snapshot(audit_id, "grant_bonus_points", [{
        "cust_id": cust["id"], "mobile": cust.get("mobile"),
        "points_before": cur, "points_after": cur + points,
        "lifetime_before": lt_before, "lifetime_after": lt_before + points}])
    return {"ok": True, "applied": True, "audit_id": audit_id, **plan,
            "message": f"Granted {points} bonus points to {cust.get('mobile')}. New balance {cur + points}."}


# ============================================================
# 2) Adjust (add or deduct) points for ONE customer
# ============================================================
async def _tool_adjust_points(mobile: str, points: int, reason: str = "",
                              confirm: bool = False, user=None) -> Dict[str, Any]:
    err = _require_master(user)
    if err:
        return err
    try:
        points = int(points)
    except Exception:
        return {"error": "points must be a non-zero integer (negative to deduct)"}
    if points == 0:
        return {"error": "points must be non-zero (positive to add, negative to deduct)"}
    cust = await _find_customer(mobile)
    if not cust:
        return {"found": False, "mobile": mobile, "error": "No customer found for that mobile."}
    cur = int(cust.get("points_balance") or 0)
    plan = {
        "action": "adjust_points", "mobile": cust.get("mobile"), "name": cust.get("name"),
        "current_balance": cur, "delta": points, "new_balance_after": cur + points,
    }
    if not confirm:
        plan["preview"] = True
        plan["confirmation_required"] = "Confirm with the user, capture a reason, then call again with confirm=true."
        return plan
    rerr = _need_reason(reason)
    if rerr:
        return rerr
    await customers_col.update_one({"id": cust["id"]}, {"$inc": {"points_balance": points}})
    await _ledger(cust.get("mobile"), points, "adjust", reason, user)
    audit_id = await _log_master(user, "adjust_points", "customer", cust.get("id"), reason,
                                 {"mobile": cust.get("mobile"), "delta": points,
                                  "balance_before": cur, "balance_after": cur + points})
    await _record_snapshot(audit_id, "adjust_points", [{
        "cust_id": cust["id"], "mobile": cust.get("mobile"),
        "points_before": cur, "points_after": cur + points}])
    return {"ok": True, "applied": True, "audit_id": audit_id, **plan,
            "message": f"Adjusted {cust.get('mobile')} by {points:+d}. New balance {cur + points}."}


# ============================================================
# 3) Fix negative points balances (single or bulk)
# ============================================================
async def _tool_fix_negative_balances(mobile: Optional[str] = None, reason: str = "",
                                      confirm: bool = False, user=None) -> Dict[str, Any]:
    err = _require_master(user)
    if err:
        return err
    if mobile:
        cust = await _find_customer(mobile)
        if not cust:
            return {"found": False, "mobile": mobile, "error": "No customer found."}
        bal = int(cust.get("points_balance") or 0)
        if bal >= 0:
            return {"action": "fix_negative_balances", "mobile": cust.get("mobile"),
                    "current_balance": bal, "message": "Balance is not negative — nothing to fix."}
        plan = {"action": "fix_negative_balances", "scope": "single", "mobile": cust.get("mobile"),
                "current_balance": bal, "new_balance_after": 0, "points_restored": -bal}
        if not confirm:
            plan["preview"] = True
            return plan
        rerr = _need_reason(reason)
        if rerr:
            return rerr
        await customers_col.update_one({"id": cust["id"]}, {"$set": {"points_balance": 0}})
        await _ledger(cust.get("mobile"), -bal, "adjust", f"Negative-balance reset to 0 — {reason}", user)
        audit_id = await _log_master(user, "fix_negative_balance", "customer", cust.get("id"), reason,
                                     {"mobile": cust.get("mobile"), "balance_before": bal, "balance_after": 0})
        await _record_snapshot(audit_id, "fix_negative_balance", [{
            "cust_id": cust["id"], "mobile": cust.get("mobile"),
            "points_before": bal, "points_after": 0}])
        return {"ok": True, "applied": True, "audit_id": audit_id, **plan,
                "message": f"Reset {cust.get('mobile')} from {bal} to 0 ({-bal} points restored)."}

    # ---- Bulk: all customers with negative balance ----
    fil = {"points_balance": {"$lt": 0}}
    count = await customers_col.count_documents(fil)
    agg = await customers_col.aggregate([
        {"$match": fil}, {"$group": {"_id": None, "total": {"$sum": "$points_balance"}}}],
        allowDiskUse=True).to_list(1)
    total_neg = int(agg[0]["total"]) if agg else 0
    sample = await customers_col.find(fil, {"_id": 0, "mobile": 1, "name": 1, "points_balance": 1}) \
        .sort("points_balance", 1).limit(20).to_list(20)
    plan = {"action": "fix_negative_balances", "scope": "bulk_all_negatives",
            "customers_affected": count, "total_negative_points": total_neg,
            "points_to_restore": -total_neg, "sample": sample}
    if not confirm:
        plan["preview"] = True
        plan["confirmation_required"] = ("This will set EVERY negative balance to 0. Confirm count with the "
                                         "user, capture a reason, then call again with confirm=true.")
        return plan
    rerr = _need_reason(reason)
    if rerr:
        return rerr
    if count > INLINE_CAP:
        return {"error": f"{count} customers exceeds the inline cap ({INLINE_CAP}). This is too large to run "
                         f"safely inside a chat turn — please run smaller scopes or contact the team for a batch job."}
    # Bounded batched apply
    updated = 0
    restored = 0
    changes: List[Dict[str, Any]] = []
    last_id = None
    while True:
        q = dict(fil)
        if last_id is not None:
            q["_id"] = {"$gt": last_id}
        docs = await customers_col.find(q, {"_id": 1, "id": 1, "mobile": 1, "points_balance": 1}) \
            .sort("_id", 1).limit(BATCH).to_list(BATCH)
        if not docs:
            break
        ops = []
        ledger_docs = []
        for d in docs:
            bal = int(d.get("points_balance") or 0)
            if bal >= 0:
                continue
            ops.append(UpdateOne({"_id": d["_id"]}, {"$set": {"points_balance": 0}}))
            restored += -bal
            changes.append({"cust_id": d.get("id"), "mobile": d.get("mobile"),
                            "points_before": bal, "points_after": 0})
            ledger_docs.append({
                "id": str(uuid.uuid4()), "customer_mobile": d.get("mobile"), "points": -bal,
                "type": "adjust", "kind": "adjust", "reference_type": "master_brain",
                "reason": f"Negative-balance reset to 0 — {reason}", "created_at": _now_iso(),
                "created_by": user.get("email"), "via": "master_brain",
            })
        if ops:
            res = await customers_col.bulk_write(ops, ordered=False)
            updated += res.modified_count
        if ledger_docs:
            await points_ledger_col.insert_many(ledger_docs, ordered=False)
        last_id = docs[-1]["_id"]
        if len(docs) < BATCH:
            break
    audit_id = await _log_master(user, "fix_negative_balances_bulk", "customers", "bulk", reason,
                                 {"customers_affected": updated, "points_restored": restored,
                                  "total_negative_before": total_neg})
    await _record_snapshot(audit_id, "fix_negative_balances_bulk", changes)
    return {"ok": True, "applied": True, "audit_id": audit_id, "customers_updated": updated,
            "points_restored": restored,
            "message": f"Reset {updated} customers to 0 ({restored} points restored). Logged to the action log."}


# ============================================================
# 4) Re-tier customers onto the configured slabs (NO bonus points)
# ============================================================
async def _tool_retier_customers(mobile: Optional[str] = None, scope: str = "legacy",
                                 reason: str = "", confirm: bool = False, user=None) -> Dict[str, Any]:
    err = _require_master(user)
    if err:
        return err
    from routes.loyalty_routes import _active_sorted_tiers, _derive_slug
    cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0, "tier_rules": 1}) or {}
    sorted_tiers = _active_sorted_tiers(cfg)
    if not sorted_tiers:
        return {"error": "No active tiers are configured. Set up tiers on the Loyalty Rules page first."}
    bands = [(t["tier"], float(t.get("min_lifetime_spend") or 0)) for t in sorted_tiers]
    active_slugs = [t["tier"] for t in sorted_tiers]
    name_map = {t["tier"]: (t.get("name") or t["tier"]) for t in sorted_tiers}

    if mobile:
        cust = await _find_customer(mobile)
        if not cust:
            return {"found": False, "mobile": mobile, "error": "No customer found."}
        correct = _derive_slug(cust.get("lifetime_spend"), bands)
        plan = {"action": "retier_customers", "scope": "single", "mobile": cust.get("mobile"),
                "current_tier": cust.get("tier"), "correct_tier": correct,
                "correct_tier_name": name_map.get(correct, correct),
                "lifetime_spend": cust.get("lifetime_spend"), "awards_bonus": False}
        if cust.get("tier") == correct:
            plan["message"] = "Already on the correct tier — nothing to change."
            return plan
        if not confirm:
            plan["preview"] = True
            return plan
        rerr = _need_reason(reason)
        if rerr:
            return rerr
        await customers_col.update_one({"id": cust["id"]},
                                       {"$set": {"tier": correct, "tier_updated_at": _now_iso()}})
        audit_id = await _log_master(user, "retier_customer", "customer", cust.get("id"), reason,
                                     {"mobile": cust.get("mobile"), "from": cust.get("tier"), "to": correct})
        await _record_snapshot(audit_id, "retier_customer", [{
            "cust_id": cust["id"], "mobile": cust.get("mobile"),
            "tier_before": cust.get("tier"), "tier_after": correct}])
        return {"ok": True, "applied": True, "audit_id": audit_id, **plan,
                "message": f"Moved {cust.get('mobile')} from '{cust.get('tier')}' to '{correct}' (no bonus points)."}

    # ---- Bulk ----
    if scope == "all":
        fil: Dict[str, Any] = {"mobile": {"$nin": [None, ""]}}
    else:  # 'legacy' = customers sitting on a tier that is NOT a configured slab (e.g. Silver/Gold)
        fil = {"tier": {"$nin": active_slugs + [None, ""]}}
    count = await customers_col.count_documents(fil)
    sample_docs = await customers_col.find(fil, {"_id": 0, "mobile": 1, "tier": 1, "lifetime_spend": 1}) \
        .limit(20).to_list(20)
    sample = [{"mobile": d.get("mobile"), "from": d.get("tier"),
               "to": _derive_slug(d.get("lifetime_spend"), bands)} for d in sample_docs]
    plan = {"action": "retier_customers", "scope": scope, "customers_matched": count,
            "configured_tiers": [{"tier": t["tier"], "name": name_map.get(t["tier"]),
                                  "min_lifetime_spend": t.get("min_lifetime_spend") or 0} for t in sorted_tiers],
            "sample": sample, "awards_bonus": False}
    if not confirm:
        plan["preview"] = True
        plan["confirmation_required"] = ("Re-maps these customers onto the configured slabs by lifetime spend "
                                         "with NO bonus points. Confirm with the user + reason, then confirm=true.")
        return plan
    rerr = _need_reason(reason)
    if rerr:
        return rerr
    if count > INLINE_CAP:
        return {"error": f"{count} customers exceeds the inline cap ({INLINE_CAP}). Use the batched "
                         f"'Re-tier Old Customers' tool on the Loyalty Rules page for very large runs."}
    updated = 0
    per_tier: Dict[str, int] = {}
    changes: List[Dict[str, Any]] = []
    last_id = None
    while True:
        q = dict(fil)
        if last_id is not None:
            q["_id"] = {"$gt": last_id}
        docs = await customers_col.find(q, {"_id": 1, "id": 1, "mobile": 1, "tier": 1, "lifetime_spend": 1}) \
            .sort("_id", 1).limit(BATCH).to_list(BATCH)
        if not docs:
            break
        ops = []
        for d in docs:
            correct = _derive_slug(d.get("lifetime_spend"), bands)
            if d.get("tier") != correct:
                ops.append(UpdateOne({"_id": d["_id"]},
                                     {"$set": {"tier": correct, "tier_updated_at": _now_iso()}}))
                per_tier[correct] = per_tier.get(correct, 0) + 1
                changes.append({"cust_id": d.get("id"), "mobile": d.get("mobile"),
                                "tier_before": d.get("tier"), "tier_after": correct})
        if ops:
            res = await customers_col.bulk_write(ops, ordered=False)
            updated += res.modified_count
        last_id = docs[-1]["_id"]
        if len(docs) < BATCH:
            break
    audit_id = await _log_master(user, "retier_customers_bulk", "customers", "bulk", reason,
                                 {"scope": scope, "matched": count, "updated": updated, "per_tier": per_tier})
    await _record_snapshot(audit_id, "retier_customers_bulk", changes)
    return {"ok": True, "applied": True, "audit_id": audit_id, "customers_matched": count,
            "customers_updated": updated, "per_tier": per_tier, "awarded_bonus": False,
            "message": f"Re-tiered {updated} customers onto the configured slabs (no bonus points). "
                       f"Breakdown by new tier: {per_tier}."}


# ============================================================
# 5) Read: Master Brain action log
# ============================================================
async def _tool_master_action_log(days: int = 7, limit: int = 30, user=None) -> Dict[str, Any]:
    err = _require_master(user)
    if err:
        return err
    fil: Dict[str, Any] = {"source": "master_brain"}
    if days and days > 0:
        fil["timestamp"] = {"$gte": (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()}
    rows = await audit_logs_col.find(fil, {"_id": 0}).sort("timestamp", -1).limit(min(limit, 100)).to_list(100)
    return {"count": len(rows), "actions": rows}


# ============================================================
# 6) Act on the customers listed in an UPLOADED report (CSV/XLSX/PDF)
# ============================================================
async def _tool_apply_to_uploaded_report(attachment_id: str, action: str, points: Optional[int] = None,
                                         reason: str = "", confirm: bool = False, user=None) -> Dict[str, Any]:
    err = _require_master(user)
    if err:
        return err
    from database import mb_attachments_col
    att = None
    if attachment_id:
        att = await mb_attachments_col.find_one(
            {"id": attachment_id, "user_id": user.get("id")}, {"_id": 0})
    if not att:
        # Fallback: the most recent report uploaded in this chat session (handles the
        # preview -> confirm turn where the UI no longer re-sends the attachment id).
        q: Dict[str, Any] = {"user_id": user.get("id"), "kind": "report"}
        if user.get("_mb_session"):
            q["session_id"] = user["_mb_session"]
        att = await mb_attachments_col.find_one(q, {"_id": 0}, sort=[("created_at", -1)])
    if not att:
        return {"error": "No uploaded report found for this conversation. Please attach the report again."}
    mobiles = att.get("mobiles") or []
    if not mobiles:
        return {"error": "No mobile numbers were detected in that file. Make sure it has a phone/mobile column."}
    action = (action or "").lower()
    if action not in {"grant_points", "adjust_points", "fix_negative", "retier"}:
        return {"error": "action must be one of: grant_points, adjust_points, fix_negative, retier"}
    if action in {"grant_points", "adjust_points"}:
        try:
            points = int(points)
        except Exception:
            return {"error": f"points (integer) is required for {action}"}
        if action == "grant_points" and points <= 0:
            return {"error": "grant_points needs a positive points value"}
        if action == "adjust_points" and points == 0:
            return {"error": "adjust_points needs a non-zero points value"}

    plan = {"action": "apply_to_uploaded_report", "file": att.get("filename"),
            "row_action": action, "points": points, "mobiles_in_file": len(mobiles),
            "awards_bonus": action == "grant_points",
            "note": "Re-tier awards NO bonus points." if action == "retier" else None}
    if not confirm:
        # sample resolve for the preview
        sample = []
        for m in mobiles[:8]:
            c = await _find_customer(m)
            sample.append({"mobile": m, "found": bool(c),
                           "name": (c or {}).get("name"), "balance": (c or {}).get("points_balance")})
        plan["preview"] = True
        plan["sample"] = sample
        plan["confirmation_required"] = ("Confirm with the user + capture a reason, then call again with "
                                         "confirm=true. Will process every mobile in the file.")
        return plan
    rerr = _need_reason(reason)
    if rerr:
        return rerr
    if len(mobiles) > INLINE_CAP:
        return {"error": f"{len(mobiles)} rows exceeds the inline cap ({INLINE_CAP})."}

    bands = None
    if action == "retier":
        from routes.loyalty_routes import _active_sorted_tiers, _derive_slug
        cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0, "tier_rules": 1}) or {}
        st = _active_sorted_tiers(cfg)
        if not st:
            return {"error": "No active tiers configured."}
        bands = [(t["tier"], float(t.get("min_lifetime_spend") or 0)) for t in st]

    matched = 0
    changed = 0
    not_found = 0
    changes: List[Dict[str, Any]] = []
    for m in mobiles:
        cust = await _find_customer(m)
        if not cust:
            not_found += 1
            continue
        matched += 1
        cid = cust["id"]
        cur = int(cust.get("points_balance") or 0)
        if action == "grant_points":
            lt_before = int(cust.get("lifetime_points_earned") or 0)
            await customers_col.update_one({"id": cid}, {"$inc": {"points_balance": points,
                                                                  "lifetime_points_earned": points}})
            await _ledger(cust.get("mobile"), points, "bonus", reason, user)
            changes.append({"cust_id": cid, "mobile": cust.get("mobile"),
                            "points_before": cur, "points_after": cur + points,
                            "lifetime_before": lt_before, "lifetime_after": lt_before + points})
            changed += 1
        elif action == "adjust_points":
            await customers_col.update_one({"id": cid}, {"$inc": {"points_balance": points}})
            await _ledger(cust.get("mobile"), points, "adjust", reason, user)
            changes.append({"cust_id": cid, "mobile": cust.get("mobile"),
                            "points_before": cur, "points_after": cur + points})
            changed += 1
        elif action == "fix_negative":
            if cur < 0:
                await customers_col.update_one({"id": cid}, {"$set": {"points_balance": 0}})
                await _ledger(cust.get("mobile"), -cur, "adjust", f"Negative reset — {reason}", user)
                changes.append({"cust_id": cid, "mobile": cust.get("mobile"),
                                "points_before": cur, "points_after": 0})
                changed += 1
        elif action == "retier":
            from routes.loyalty_routes import _derive_slug
            correct = _derive_slug(cust.get("lifetime_spend"), bands)
            if cust.get("tier") != correct:
                await customers_col.update_one({"id": cid},
                                               {"$set": {"tier": correct, "tier_updated_at": _now_iso()}})
                changes.append({"cust_id": cid, "mobile": cust.get("mobile"),
                                "tier_before": cust.get("tier"), "tier_after": correct})
                changed += 1
    audit_id = await _log_master(user, f"upload_{action}", "customers", att["id"], reason,
                                 {"file": att.get("filename"), "mobiles_in_file": len(mobiles),
                                  "matched": matched, "changed": changed, "not_found": not_found,
                                  "points": points})
    await _record_snapshot(audit_id, f"upload_{action}", changes)
    return {"ok": True, "applied": True, "audit_id": audit_id, **plan,
            "matched_customers": matched, "changed": changed, "not_found": not_found,
            "message": f"Processed '{att.get('filename')}': {changed} customers updated "
                       f"({matched} matched, {not_found} not found)."}


CAMPAIGN_CAP = 50000


async def _record_snapshot(audit_id: str, action: str, changes: List[Dict[str, Any]]) -> None:
    """Persist a reversible before/after snapshot so the action can be undone later."""
    if not audit_id or not changes:
        return
    await mb_action_snapshots_col.insert_one({
        "audit_id": audit_id, "action": action, "changes": changes,
        "undone": False, "created_at": _now_iso(),
    })


def _camp_params(c: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    c = c or {}
    return {"name": (c.get("name") or "").split(" ")[0] or "there",
            "tier": c.get("tier") or "", "points_balance": c.get("points_balance") or 0,
            "city": c.get("city") or ""}


# ============================================================
# 7) UNDO a previous Master Brain action (reverse via snapshot)
# ============================================================
async def _apply_undo_change(ch: Dict[str, Any], action: str, reason: str, user: Dict[str, Any]) -> None:
    cid = ch.get("cust_id")
    if cid:
        q: Dict[str, Any] = {"id": cid}
    else:
        strs, ints = _mobile_candidates(ch.get("mobile"))
        q = {"mobile": {"$in": strs + ints}}
    if ch.get("points_before") is not None:
        before = int(ch.get("points_before") or 0)
        after = int(ch.get("points_after") or 0)
        delta = before - after  # inverse of the original change
        inc: Dict[str, Any] = {"points_balance": delta}
        if ch.get("lifetime_before") is not None:
            inc["lifetime_points_earned"] = int(ch.get("lifetime_before") or 0) - int(ch.get("lifetime_after") or 0)
        await customers_col.update_one(q, {"$inc": inc})
        if ch.get("mobile"):
            await _ledger(ch.get("mobile"), delta, "adjust", f"UNDO {action} — {reason}", user)
    if "tier_before" in ch:
        await customers_col.update_one(q, {"$set": {"tier": ch.get("tier_before"),
                                                    "tier_updated_at": _now_iso()}})


async def _tool_undo_action(audit_id: str, reason: str = "", confirm: bool = False, user=None) -> Dict[str, Any]:
    err = _require_master(user)
    if err:
        return err
    doc = await audit_logs_col.find_one({"id": audit_id, "source": "master_brain"}, {"_id": 0})
    if not doc:
        return {"error": "No Master Brain action found for that id."}
    if doc.get("undone"):
        return {"error": "This action has already been undone."}
    act = (doc.get("action") or "").replace("master_brain.", "")
    if act in {"master_action_log", "undo", "send_campaign", "cancel_campaign"}:
        return {"error": f"'{act}' is not an undoable data change."}
    snap = await mb_action_snapshots_col.find_one({"audit_id": audit_id}, {"_id": 0})
    if not snap or not snap.get("changes"):
        return {"error": "This action predates undo support (no reversible snapshot was captured), so it "
                         "can't be auto-undone. Reverse it manually with the per-customer tools instead."}
    changes = snap.get("changes") or []
    plan = {"action": "undo_action", "target_action": act, "target_audit_id": audit_id,
            "original_reason": doc.get("reason"), "changes_to_reverse": len(changes),
            "sample": changes[:8]}
    if not confirm:
        plan["preview"] = True
        plan["confirmation_required"] = ("This reverses the listed change(s) and writes compensating ledger "
                                         "entries. Confirm with the user + a reason, then call again confirm=true.")
        return plan
    rerr = _need_reason(reason)
    if rerr:
        return rerr
    reversed_count = 0
    for ch in changes:
        await _apply_undo_change(ch, act, reason, user)
        reversed_count += 1
    new_audit = await _log_master(user, "undo", doc.get("entity") or "customers", audit_id, reason,
                                  {"undid_action": act, "undid_audit_id": audit_id,
                                   "changes_reversed": reversed_count})
    await audit_logs_col.update_one({"id": audit_id}, {"$set": {
        "undone": True, "undone_at": _now_iso(), "undone_by": user.get("email"),
        "undo_reason": reason, "undo_audit_id": new_audit}})
    await mb_action_snapshots_col.update_one({"audit_id": audit_id}, {"$set": {"undone": True}})
    return {"ok": True, "applied": True, "audit_id": new_audit, **plan,
            "message": f"Undid '{act}' — {reversed_count} change(s) rolled back and logged as an undo."}


# ============================================================
# 8) CAMPAIGN sending & management (Karix Bulk SMS)
# ============================================================
async def _resolve_audience(audience_type, audience_value, attachment_id, mobiles, user, session_id):
    at = (audience_type or "all").lower()
    if at in {"report", "uploaded_report", "attachment"}:
        from database import mb_attachments_col
        att = None
        if attachment_id:
            att = await mb_attachments_col.find_one({"id": attachment_id, "user_id": user.get("id")}, {"_id": 0})
        if not att and session_id:
            att = await mb_attachments_col.find_one(
                {"session_id": session_id, "user_id": user.get("id"), "kind": "report"},
                {"_id": 0}, sort=[("created_at", -1)])
        if not att:
            return None, "No uploaded report found to use as the audience. Attach the report first."
        ms = list(dict.fromkeys(att.get("mobiles") or []))
        return {"mode": "mobiles", "mobiles": ms, "label": f"report:{att.get('filename')}"}, None
    if at == "mobiles":
        ms = list(dict.fromkeys(str(m).strip() for m in (mobiles or []) if str(m).strip()))
        return {"mode": "mobiles", "mobiles": ms, "label": "explicit list"}, None
    if at == "tier" and audience_value:
        return {"mode": "db", "filter": {"tier": audience_value, "mobile": {"$nin": [None, ""]}},
                "label": f"tier={audience_value}"}, None
    if at == "city" and audience_value:
        return {"mode": "db", "filter": {"city": audience_value, "mobile": {"$nin": [None, ""]}},
                "label": f"city={audience_value}"}, None
    if at == "all":
        return {"mode": "db", "filter": {"mobile": {"$nin": [None, ""]}}, "label": "all customers"}, None
    return None, f"Unknown audience_type '{audience_type}'. Use all, tier, city, report or mobiles."


async def _is_campaign_cancelled(cid: str) -> bool:
    c = await master_campaigns_col.find_one({"id": cid}, {"_id": 0, "cancel_requested": 1})
    return bool(c and c.get("cancel_requested"))


async def _run_mb_campaign(cid: str) -> None:
    from routes.communications_routes import send_sms_karix, _render
    from database import templates_col
    camp = await master_campaigns_col.find_one({"id": cid}, {"_id": 0})
    if not camp:
        return
    await master_campaigns_col.update_one({"id": cid}, {"$set": {"status": "running", "started_at": _now_iso()}})
    body = camp.get("message")
    if camp.get("template_id"):
        tpl = await templates_col.find_one({"id": camp["template_id"]}, {"_id": 0})
        if tpl:
            body = tpl.get("body")
    spec = camp.get("audience_spec") or {}
    sent = failed = processed = 0
    try:
        async def _dispatch(mobile, params):
            nonlocal sent, failed
            text = _render(body or "", params)
            res = await send_sms_karix(mobile, text, template_id=camp.get("template_id"),
                                       event_trigger="campaign_bulk",
                                       context={"source": f"master_campaign:{cid}"})
            if res.get("ok"):
                sent += 1
            else:
                failed += 1
        if spec.get("mode") == "mobiles":
            for m in spec.get("mobiles") or []:
                c = await _find_customer(m)
                await _dispatch(m, _camp_params(c))
                processed += 1
                if processed % 25 == 0:
                    if await _is_campaign_cancelled(cid):
                        break
                    await master_campaigns_col.update_one({"id": cid},
                        {"$set": {"processed": processed, "sent": sent, "failed": failed}})
        else:
            cursor = customers_col.find(spec.get("filter") or {},
                {"_id": 0, "mobile": 1, "name": 1, "tier": 1, "points_balance": 1, "city": 1})
            async for c in cursor:
                m = c.get("mobile")
                if not m:
                    continue
                await _dispatch(m, _camp_params(c))
                processed += 1
                if processed % 25 == 0:
                    if await _is_campaign_cancelled(cid):
                        break
                    await master_campaigns_col.update_one({"id": cid},
                        {"$set": {"processed": processed, "sent": sent, "failed": failed}})
        cancelled = await _is_campaign_cancelled(cid)
        await master_campaigns_col.update_one({"id": cid}, {"$set": {
            "status": "cancelled" if cancelled else "completed",
            "processed": processed, "sent": sent, "failed": failed, "completed_at": _now_iso()}})
    except Exception as e:  # noqa: BLE001
        await master_campaigns_col.update_one({"id": cid}, {"$set": {
            "status": "failed", "error": str(e), "processed": processed,
            "sent": sent, "failed": failed, "completed_at": _now_iso()}})


async def _tool_send_campaign(message: Optional[str] = None, template_id: Optional[str] = None,
                              audience_type: str = "all", audience_value: Optional[str] = None,
                              attachment_id: Optional[str] = None, mobiles: Optional[List[str]] = None,
                              reason: str = "", confirm: bool = False, user=None) -> Dict[str, Any]:
    err = _require_master(user)
    if err:
        return err
    if not message and not template_id:
        return {"error": "Provide either a message (raw SMS text) or a template_id."}
    from database import templates_col
    tpl = None
    if template_id:
        tpl = await templates_col.find_one({"id": template_id}, {"_id": 0})
        if not tpl:
            return {"error": "Template not found."}
        if (tpl.get("channel") or "sms") != "sms":
            return {"error": "Only SMS templates are supported for Karix bulk campaigns."}
    session_id = (user or {}).get("_mb_session")
    spec, aerr = await _resolve_audience(audience_type, audience_value, attachment_id, mobiles, user, session_id)
    if aerr:
        return {"error": aerr}
    if spec["mode"] == "mobiles":
        count = len(spec["mobiles"])
        sample = spec["mobiles"][:5]
    else:
        count = await customers_col.count_documents(spec["filter"])
        sdocs = await customers_col.find(spec["filter"], {"_id": 0, "mobile": 1}).limit(5).to_list(5)
        sample = [d.get("mobile") for d in sdocs]
    from routes.communications_routes import _render
    sample_text = _render((tpl.get("body") if tpl else message) or "",
                          {"name": "there", "tier": "", "points_balance": 0, "city": ""})
    plan = {"action": "send_campaign", "channel": "sms", "via": "Karix Bulk SMS",
            "recipients": count, "audience": spec.get("label"),
            "template": tpl.get("name") if tpl else None,
            "message_preview": sample_text, "sample_recipients": sample}
    if count == 0:
        plan["message"] = "No recipients matched this audience — nothing to send."
        return plan
    if not confirm:
        plan["preview"] = True
        plan["confirmation_required"] = (f"This sends an SMS to {count} customers via Karix. Confirm with the "
                                         f"user + capture a reason, then call again confirm=true.")
        return plan
    rerr = _need_reason(reason)
    if rerr:
        return rerr
    if count > CAMPAIGN_CAP:
        return {"error": f"{count} recipients exceeds the safety cap ({CAMPAIGN_CAP}). Narrow the audience."}
    cid = uuid.uuid4().hex
    camp = {"id": cid, "status": "queued", "channel": "sms", "via": "karix",
            "message": (None if tpl else message), "template_id": template_id,
            "template_name": tpl.get("name") if tpl else None,
            "audience_type": (audience_type or "all"), "audience_value": audience_value,
            "audience_label": spec.get("label"), "audience_spec": spec,
            "recipients_total": count, "processed": 0, "sent": 0, "failed": 0,
            "reason": reason, "created_by": user.get("email"), "created_by_name": user.get("name"),
            "created_at": _now_iso(), "cancel_requested": False}
    await master_campaigns_col.insert_one(camp)
    audit_id = await _log_master(user, "send_campaign", "campaign", cid, reason,
                                 {"recipients": count, "channel": "sms", "audience": spec.get("label"),
                                  "template": tpl.get("name") if tpl else "raw_text"})
    await master_campaigns_col.update_one({"id": cid}, {"$set": {"audit_id": audit_id}})
    import asyncio
    asyncio.create_task(_run_mb_campaign(cid))
    return {"ok": True, "applied": True, "audit_id": audit_id, "campaign_id": cid,
            "recipients": count, **plan,
            "message": f"Campaign queued — sending SMS to {count} customers via Karix. "
                       f"Track progress in the Campaigns tab (id {cid})."}


async def _tool_list_campaigns(limit: int = 20, user=None) -> Dict[str, Any]:
    err = _require_master(user)
    if err:
        return err
    rows = await master_campaigns_col.find({}, {"_id": 0, "audience_spec": 0}) \
        .sort("created_at", -1).limit(min(limit, 50)).to_list(50)
    return {"count": len(rows), "campaigns": rows}


async def _tool_cancel_campaign(campaign_id: str, reason: str = "", confirm: bool = False, user=None) -> Dict[str, Any]:
    err = _require_master(user)
    if err:
        return err
    camp = await master_campaigns_col.find_one({"id": campaign_id}, {"_id": 0, "audience_spec": 0})
    if not camp:
        return {"error": "Campaign not found."}
    if camp.get("status") in {"completed", "failed", "cancelled"}:
        return {"action": "cancel_campaign", "status": camp.get("status"),
                "message": f"Campaign is already '{camp.get('status')}' — nothing to cancel."}
    plan = {"action": "cancel_campaign", "campaign_id": campaign_id, "status": camp.get("status"),
            "sent_so_far": camp.get("sent"), "recipients_total": camp.get("recipients_total")}
    if not confirm:
        plan["preview"] = True
        plan["confirmation_required"] = "Confirm with the user + a reason, then call again confirm=true."
        return plan
    rerr = _need_reason(reason)
    if rerr:
        return rerr
    await master_campaigns_col.update_one({"id": campaign_id}, {"$set": {"cancel_requested": True}})
    audit_id = await _log_master(user, "cancel_campaign", "campaign", campaign_id, reason,
                                 {"status_at_cancel": camp.get("status"), "sent_so_far": camp.get("sent")})
    return {"ok": True, "applied": True, "audit_id": audit_id, **plan,
            "message": "Cancellation requested — the campaign will stop after the current batch."}


MASTER_TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {"type": "function", "function": {
        "name": "grant_bonus_points",
        "description": "MUTATION (Master Admin). Grant bonus loyalty points to ONE customer by mobile. "
                       "ALWAYS call first with confirm=false to preview (shows current vs new balance), present "
                       "it, get the user's approval AND a reason, then call again with confirm=true + reason. "
                       "Adds a points_ledger 'bonus' row and is audit-logged.",
        "parameters": {"type": "object", "properties": {
            "mobile": {"type": "string", "description": "Customer mobile (10/12 digits)"},
            "points": {"type": "integer", "description": "Positive number of points to add"},
            "reason": {"type": "string", "description": "Business reason (required when confirm=true)"},
            "confirm": {"type": "boolean", "description": "false = preview only; true = apply", "default": False},
        }, "required": ["mobile", "points"]}}},
    {"type": "function", "function": {
        "name": "adjust_points",
        "description": "MUTATION (Master Admin). Add (positive) or deduct (negative) points for ONE customer. "
                       "Two-step: confirm=false previews, confirm=true + reason applies. Audit-logged + ledger row.",
        "parameters": {"type": "object", "properties": {
            "mobile": {"type": "string"},
            "points": {"type": "integer", "description": "Positive to add, negative to deduct"},
            "reason": {"type": "string"},
            "confirm": {"type": "boolean", "default": False},
        }, "required": ["mobile", "points"]}}},
    {"type": "function", "function": {
        "name": "fix_negative_balances",
        "description": "MUTATION (Master Admin). Reset NEGATIVE points balances to 0. Pass a single `mobile` for "
                       "one customer, or omit it to fix ALL customers with a negative balance (bulk). confirm=false "
                       "previews the count + total + sample; confirm=true + reason applies in safe batches. Writes "
                       "an audited points_ledger 'adjust' row per customer (reversible).",
        "parameters": {"type": "object", "properties": {
            "mobile": {"type": "string", "description": "Optional — single customer; omit for ALL negatives"},
            "reason": {"type": "string"},
            "confirm": {"type": "boolean", "default": False},
        }}}},
    {"type": "function", "function": {
        "name": "retier_customers",
        "description": "MUTATION (Master Admin). Re-map customers onto the CONFIGURED loyalty slabs by lifetime "
                       "spend, awarding NO bonus points. Pass a single `mobile`, or omit it for bulk. scope='legacy' "
                       "(default) targets customers sitting on a tier that is NOT a configured slab (e.g. old "
                       "Silver/Gold); scope='all' recomputes every loyalty customer. confirm=false previews count + "
                       "sample old->new; confirm=true + reason applies in safe batches. Audit-logged.",
        "parameters": {"type": "object", "properties": {
            "mobile": {"type": "string", "description": "Optional — single customer; omit for bulk"},
            "scope": {"type": "string", "enum": ["legacy", "all"], "default": "legacy"},
            "reason": {"type": "string"},
            "confirm": {"type": "boolean", "default": False},
        }}}},
    {"type": "function", "function": {
        "name": "master_action_log",
        "description": "READ. Return the Master Brain action audit trail (who did what, when, why) for the last N "
                       "days. Use for 'what changes were made', compliance, or 'undo' lookups.",
        "parameters": {"type": "object", "properties": {
            "days": {"type": "integer", "default": 7, "description": "0 = all time"},
            "limit": {"type": "integer", "default": 30},
        }}}},
    {"type": "function", "function": {
        "name": "apply_to_uploaded_report",
        "description": "MUTATION (Master Admin). Take a bulk action on EVERY customer listed in an UPLOADED report "
                       "(CSV/XLSX/PDF) the user attached. Use the attachment_id from the attached-report context. "
                       "action: 'grant_points' (needs points>0), 'adjust_points' (needs non-zero points, +/-), "
                       "'fix_negative' (resets negative balances to 0), 'retier' (re-map onto configured slabs, NO "
                       "bonus points). ALWAYS confirm=false first to preview (file, row count, sample), then after "
                       "the user approves + gives a reason, confirm=true + reason. Audit-logged; points changes write "
                       "ledger rows.",
        "parameters": {"type": "object", "properties": {
            "attachment_id": {"type": "string", "description": "id of the uploaded report (from the context block)"},
            "action": {"type": "string", "enum": ["grant_points", "adjust_points", "fix_negative", "retier"]},
            "points": {"type": "integer", "description": "points for grant_points/adjust_points"},
            "reason": {"type": "string"},
            "confirm": {"type": "boolean", "default": False},
        }, "required": ["attachment_id", "action"]}}},
    {"type": "function", "function": {
        "name": "undo_action",
        "description": "MUTATION (Master Admin). REVERSE a previous Master Brain action by its audit log id "
                       "(grant/adjust points, fix negatives, re-tier — single, bulk or uploaded-report). Uses the "
                       "before/after snapshot captured when the action ran, restores the prior values and writes "
                       "compensating ledger entries. ALWAYS confirm=false first to preview how many changes will be "
                       "reversed, then after the user approves + gives a reason, confirm=true + reason. Each action "
                       "can be undone once. Get audit ids from master_action_log.",
        "parameters": {"type": "object", "properties": {
            "audit_id": {"type": "string", "description": "id of the action to undo (from master_action_log)"},
            "reason": {"type": "string"},
            "confirm": {"type": "boolean", "default": False},
        }, "required": ["audit_id"]}}},
    {"type": "function", "function": {
        "name": "send_campaign",
        "description": "MUTATION (Master Admin). Send a BULK SMS CAMPAIGN via the Karix Bulk SMS API. Provide either "
                       "a raw `message` (mustache vars {{name}}/{{tier}}/{{city}}/{{points_balance}} are filled per "
                       "customer) OR an existing SMS `template_id`. Audience: audience_type='all' | 'tier' (audience_value=tier slug) "
                       "| 'city' (audience_value=city) | 'report' (the uploaded report's mobiles, optional attachment_id) "
                       "| 'mobiles' (explicit mobiles list). ALWAYS confirm=false first to preview the recipient count + "
                       "the message + a sample; then after the user approves + gives a reason, confirm=true + reason. "
                       "Sending runs in the background; audit-logged; track/cancel via list_campaigns / cancel_campaign.",
        "parameters": {"type": "object", "properties": {
            "message": {"type": "string", "description": "Raw SMS text (omit if using template_id)"},
            "template_id": {"type": "string", "description": "Existing SMS template id (omit if using message)"},
            "audience_type": {"type": "string", "enum": ["all", "tier", "city", "report", "mobiles"], "default": "all"},
            "audience_value": {"type": "string", "description": "tier slug or city when audience_type is tier/city"},
            "attachment_id": {"type": "string", "description": "uploaded report id when audience_type='report'"},
            "mobiles": {"type": "array", "items": {"type": "string"}, "description": "explicit mobiles when audience_type='mobiles'"},
            "reason": {"type": "string"},
            "confirm": {"type": "boolean", "default": False},
        }}}},
    {"type": "function", "function": {
        "name": "list_campaigns",
        "description": "READ. List recent Master Brain bulk-SMS campaigns with their status (queued/running/completed/"
                       "cancelled/failed), recipients, sent/failed counts and who created them. Use to report progress "
                       "or to find a campaign_id to cancel.",
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "integer", "default": 20},
        }}}},
    {"type": "function", "function": {
        "name": "cancel_campaign",
        "description": "MUTATION (Master Admin). Request cancellation of an in-flight campaign by campaign_id (it stops "
                       "after the current batch). confirm=false previews; confirm=true + reason applies. Audit-logged.",
        "parameters": {"type": "object", "properties": {
            "campaign_id": {"type": "string"},
            "reason": {"type": "string"},
            "confirm": {"type": "boolean", "default": False},
        }, "required": ["campaign_id"]}}},
]

MASTER_TOOL_HANDLERS = {
    "grant_bonus_points": _tool_grant_bonus_points,
    "adjust_points": _tool_adjust_points,
    "fix_negative_balances": _tool_fix_negative_balances,
    "retier_customers": _tool_retier_customers,
    "master_action_log": _tool_master_action_log,
    "apply_to_uploaded_report": _tool_apply_to_uploaded_report,
    "undo_action": _tool_undo_action,
    "send_campaign": _tool_send_campaign,
    "list_campaigns": _tool_list_campaigns,
    "cancel_campaign": _tool_cancel_campaign,
}
