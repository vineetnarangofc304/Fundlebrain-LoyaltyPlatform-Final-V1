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
import json
import asyncio
import hashlib
import logging
import time as _time
import pymongo
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from pymongo import UpdateOne
from database import (
    customers_col, points_ledger_col, audit_logs_col, loyalty_config_col,
    mb_action_snapshots_col, master_campaigns_col, mb_credit_jobs_col,
    mb_credit_receipts_col, transactions_col,
)

# Historical / live boundary. Bills BEFORE this date are HISTORICAL — the migrated
# points_balance is the sole authoritative points figure and NOTHING is computed for
# them. Bills ON/AFTER are LIVE POS — points are computed + ledgered in real time.
DEFAULT_POINTS_CUTOFF = "2026-06-08"


async def _points_cutoff() -> str:
    """Single source of truth for the historical/live cutoff (YYYY-MM-DD), read from
    loyalty_config so it always matches the ingest pipeline. Audits REPORT this value
    so the operator can verify it is correct for their dataset."""
    try:
        cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0, "points_cutoff_date": 1})
        return ((cfg or {}).get("points_cutoff_date") or DEFAULT_POINTS_CUTOFF)
    except Exception:
        return DEFAULT_POINTS_CUTOFF

# Inline apply is bounded to keep the chat request fast; bigger jobs are routed
# to the dedicated batched re-tier tool on the Loyalty Rules page.
INLINE_CAP = 20000
# Bulk bonus credits via efficient batched bulk_write (CREDIT_BATCH=2000), so a much
# larger single run is safe — raised to 1 lakh on client request (was 20000).
BULK_BONUS_CAP = 100000
BATCH = 1000

logger = logging.getLogger("kazo-fundle.master-brain-tools")


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
                      reason: str, metadata: Dict[str, Any], audit_id: Optional[str] = None) -> str:
    doc_id = audit_id or str(uuid.uuid4())
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
        # The chat session this action came from (when run via chat) so the Action Log can
        # deep-link back into the conversation. None for direct-endpoint (panel) actions.
        "session_id": (user or {}).get("_mb_session"),
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
async def _dup_redemption_excess(mobile: Optional[str], cust_id: Optional[str]) -> int:
    """Points WRONGLY deducted from one customer by DUPLICATE redemption ledger rows.
    A duplicate = the SAME redemption (keyed by bill_number|reference_id + the exact negative
    amount) recorded more than once. Excess = Σ over each duplicate group of (count-1)*|points|.
    Only genuine redemption/return rows are considered — our own compensating `master_brain`
    adjust rows are excluded so a correction is never mistaken for a duplicate."""
    q = {"$or": [{"customer_mobile": mobile}, {"customer_id": cust_id}], "points": {"$lt": 0}}
    groups: Dict[Any, int] = {}
    async for r in points_ledger_col.find(
            q, {"_id": 0, "points": 1, "bill_number": 1, "reference_id": 1, "reference_type": 1}):
        if (r.get("reference_type") or "") == "master_brain":
            continue  # skip our own compensating corrections
        pts = int(r.get("points") or 0)
        if pts >= 0:
            continue
        key = (r.get("bill_number") or r.get("reference_id") or "?", pts)
        groups[key] = groups.get(key, 0) + 1
    excess = 0
    for (key, cnt) in groups.items():
        if cnt > 1:
            excess += (cnt - 1) * (-key[1])  # -key[1] = |points|
    return excess


async def _neg_balance_targets(fil: Dict[str, Any]) -> List[Dict[str, Any]]:
    """For every customer under `fil` with a negative balance, compute the TRUE balance =
    current + points added back from duplicate redemptions, floored at 0. Returns a list of
    {doc, cur, true, restored}. Bounded by INLINE_CAP+1 so callers can reject oversized runs."""
    negs = await customers_col.find(
        fil, {"_id": 1, "id": 1, "mobile": 1, "name": 1, "points_balance": 1}) \
        .sort("points_balance", 1).limit(INLINE_CAP + 1).to_list(INLINE_CAP + 1)
    out: List[Dict[str, Any]] = []
    for d in negs:
        cur = int(d.get("points_balance") or 0)
        if cur >= 0:
            continue
        excess = await _dup_redemption_excess(d.get("mobile"), d.get("id"))
        true_bal = max(0, cur + excess)
        out.append({"doc": d, "cur": cur, "true": true_bal, "restored": true_bal - cur,
                    "excess": excess})
    return out


async def _tool_fix_negative_balances(mobile: Optional[str] = None, reason: str = "",
                                      confirm: bool = False, user=None) -> Dict[str, Any]:
    """Correct customers whose balance went negative (usually from DUPLICATE redemption rows).
    Restores each customer's TRUE balance = current + points wrongly deducted by duplicate
    redemptions, floored at 0 — NOT a blanket reset to 0. Preview (confirm=false) shows the
    per-customer target; apply (confirm=true + reason) is audited, snapshotted and UNDOABLE."""
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
        excess = await _dup_redemption_excess(cust.get("mobile"), cust.get("id"))
        target = max(0, bal + excess)
        restored = target - bal
        plan = {"action": "fix_negative_balances", "scope": "single", "mobile": cust.get("mobile"),
                "current_balance": bal, "duplicate_excess": excess, "new_balance_after": target,
                "points_restored": restored, "floored_to_zero": (bal + excess) < 0}
        if not confirm:
            plan["preview"] = True
            return plan
        rerr = _need_reason(reason)
        if rerr:
            return rerr
        await customers_col.update_one({"id": cust["id"]}, {"$set": {"points_balance": target}})
        _note = (f"Negative balance corrected to true value {target} "
                 f"(added back {excess} from duplicate redemptions) — {reason}" if excess
                 else f"Negative balance floored to {target} — {reason}")
        await _ledger(cust.get("mobile"), restored, "adjust", _note, user)
        audit_id = await _log_master(user, "fix_negative_balance", "customer", cust.get("id"), reason,
                                     {"mobile": cust.get("mobile"), "balance_before": bal,
                                      "balance_after": target, "duplicate_excess": excess})
        await _record_snapshot(audit_id, "fix_negative_balance", [{
            "cust_id": cust["id"], "mobile": cust.get("mobile"),
            "points_before": bal, "points_after": target}])
        return {"ok": True, "applied": True, "audit_id": audit_id, **plan,
                "message": f"Corrected {cust.get('mobile')} from {bal} to {target} "
                           f"({restored} points restored)."}

    # ---- Bulk: all customers with negative balance ----
    fil = {"points_balance": {"$lt": 0}}
    count = await customers_col.count_documents(fil)
    if count > INLINE_CAP:
        return {"error": f"{count} customers exceeds the inline cap ({INLINE_CAP}). This is too large to run "
                         f"safely in one pass — please scope by mobile or contact the team for a batch job."}
    with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
        targets = await _neg_balance_targets(fil)
    total_neg = sum(t["cur"] for t in targets)
    total_restored = sum(t["restored"] for t in targets)
    dup_customers = sum(1 for t in targets if t["excess"] > 0)
    sample = [{"mobile": t["doc"].get("mobile"), "name": t["doc"].get("name"),
               "points_balance": t["cur"], "true_balance": t["true"],
               "restored": t["restored"]} for t in targets[:20]]
    plan = {"action": "fix_negative_balances", "scope": "bulk_all_negatives",
            "customers_affected": len(targets), "customers_with_duplicates": dup_customers,
            "total_negative_points": total_neg, "points_to_restore": total_restored,
            "sample": sample}
    if not confirm:
        plan["preview"] = True
        plan["confirmation_required"] = (
            "This sets each negative balance to its TRUE value — current balance + points that were "
            "wrongly deducted by DUPLICATE redemptions, floored at 0 (never below). Confirm with a reason.")
        return plan
    rerr = _need_reason(reason)
    if rerr:
        return rerr
    updated = 0
    restored = 0
    changes: List[Dict[str, Any]] = []
    for i in range(0, len(targets), BATCH):
        chunk = targets[i:i + BATCH]
        ops = []
        ledger_docs = []
        for t in chunk:
            d, cur, tgt, rest = t["doc"], t["cur"], t["true"], t["restored"]
            ops.append(UpdateOne({"_id": d["_id"]}, {"$set": {"points_balance": tgt}}))
            restored += rest
            changes.append({"cust_id": d.get("id"), "mobile": d.get("mobile"),
                            "points_before": cur, "points_after": tgt})
            _note = (f"Negative balance corrected to true value (added back {t['excess']} "
                     f"from duplicate redemptions) — {reason}" if t["excess"]
                     else f"Negative balance floored to {tgt} — {reason}")
            ledger_docs.append({
                "id": str(uuid.uuid4()), "customer_mobile": d.get("mobile"), "points": rest,
                "type": "adjust", "kind": "adjust", "reference_type": "master_brain",
                "reason": _note, "created_at": _now_iso(),
                "created_by": user.get("email"), "via": "master_brain",
            })
        if ops:
            res = await customers_col.bulk_write(ops, ordered=False)
            updated += res.modified_count
        if ledger_docs:
            await points_ledger_col.insert_many(ledger_docs, ordered=False)
    audit_id = await _log_master(user, "fix_negative_balances_bulk", "customers", "bulk", reason,
                                 {"customers_affected": updated, "points_restored": restored,
                                  "customers_with_duplicates": dup_customers,
                                  "total_negative_before": total_neg})
    await _record_snapshot(audit_id, "fix_negative_balances_bulk", changes)
    return {"ok": True, "applied": True, "audit_id": audit_id, "customers_updated": updated,
            "points_restored": restored, "customers_with_duplicates": dup_customers,
            "message": f"Corrected {updated} customers to their true balance "
                       f"({restored} points restored; {dup_customers} had duplicate redemptions). "
                       f"Logged to the action log."}


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

# Per-row credit / large undo processing tuning. Heavy multi-thousand-row writes are
# run in a BACKGROUND task (decoupled from the 46s chat request) using batched bulk_write,
# each batch wrapped in pymongo.timeout() so it OVERRIDES the aggressive prod client
# timeoutMS (~10s) — otherwise the shard connection times out mid-run (the reported bug).
CREDIT_JOB_DB_DEADLINE = 600
CREDIT_BATCH = 2000
# Run the credit INLINE for the whole allowed range (up to INLINE_CAP). The efficient batched
# path (indexed bulk find + bulk_write + insert_many) does even 7-8k rows in ~2-5s — well within
# the tool's DB budget — so it returns results INSTANTLY and never needs a fragile background queue.
CREDIT_INLINE_THRESHOLD = INLINE_CAP


def _last10(v: Any) -> str:
    d = "".join(ch for ch in str(v or "") if ch.isdigit())
    return d[-10:] if len(d) >= 10 else d


async def _bulk_find_customers(mobiles: List[str]) -> Dict[str, Dict[str, Any]]:
    """Resolve many 10-digit mobiles to customer docs in a FEW batched `$in` queries
    (not one find per mobile). Returns {last10 -> customer}. Matches the several stored
    mobile formats (str/int, with/without 91 prefix)."""
    out: Dict[str, Dict[str, Any]] = {}
    uniq = list(dict.fromkeys(m for m in mobiles if m))
    proj = {"_id": 0, "id": 1, "mobile": 1, "name": 1,
            "points_balance": 1, "lifetime_points_earned": 1}
    for i in range(0, len(uniq), 800):
        chunk = uniq[i:i + 800]
        cands: List[Any] = []
        for m in chunk:
            cands.append(m)
            cands.append("91" + m)
            try:
                cands.append(int(m))
                cands.append(int("91" + m))
            except Exception:
                pass
        with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
            async for c in customers_col.find({"mobile": {"$in": cands}}, proj):
                k = _last10(c.get("mobile"))
                if k and k not in out:
                    out[k] = c
    return out


async def _credit_pairs(pairs, reason, user, job_id=None):
    """Core crediting engine (shared by inline + background). Efficient: batched find +
    bulk_write + insert_many. Returns a result dict; writes audit + snapshot for undo."""
    email = user.get("email")
    cust_map = await _bulk_find_customers([p["mobile"] for p in pairs])
    matched = changed = not_found = skipped_zero = 0
    total_credited = 0
    upd_ops: List[Any] = []
    ledger_docs: List[Dict[str, Any]] = []
    changes: List[Dict[str, Any]] = []
    for p in pairs:
        pts = int(p.get("points") or 0)
        if pts == 0:
            skipped_zero += 1
            continue
        cust = cust_map.get(_last10(p["mobile"]))
        if not cust:
            not_found += 1
            continue
        matched += 1
        cid = cust["id"]
        cur = int(cust.get("points_balance") or 0)
        lt_before = int(cust.get("lifetime_points_earned") or 0)
        upd_ops.append(UpdateOne({"id": cid}, {"$inc": {"points_balance": pts,
                                                        "lifetime_points_earned": pts}}))
        ledger_docs.append({"id": str(uuid.uuid4()), "customer_mobile": cust.get("mobile"),
                            "points": pts, "type": "bonus", "kind": "bonus",
                            "reference_type": "master_brain", "reason": reason,
                            "created_at": _now_iso(), "created_by": email, "via": "master_brain"})
        changes.append({"cust_id": cid, "mobile": cust.get("mobile"),
                        "points_before": cur, "points_after": cur + pts,
                        "lifetime_before": lt_before, "lifetime_after": lt_before + pts})
        changed += 1
        total_credited += pts

    done = 0
    total_ops = len(upd_ops)
    prog = (user or {}).get("_mb_progress")
    for i in range(0, len(upd_ops), CREDIT_BATCH):
        with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
            await customers_col.bulk_write(upd_ops[i:i + CREDIT_BATCH], ordered=False)
        done += len(upd_ops[i:i + CREDIT_BATCH])
        if job_id:
            await mb_credit_jobs_col.update_one({"id": job_id},
                {"$set": {"processed": done, "changed": changed, "heartbeat": _now_iso()}})
        if prog:
            try: await prog(done, total_ops, "customers credited")
            except Exception: pass
    for i in range(0, len(ledger_docs), CREDIT_BATCH):
        with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
            await points_ledger_col.insert_many(ledger_docs[i:i + CREDIT_BATCH], ordered=False)
        if job_id:
            await mb_credit_jobs_col.update_one({"id": job_id}, {"$set": {"heartbeat": _now_iso()}})

    audit_id = await _log_master(user, "upload_credit_points", "customers", job_id or "inline", reason,
                                 {"rows": len(pairs), "matched": matched, "changed": changed,
                                  "not_found": not_found, "skipped_zero": skipped_zero,
                                  "total_points_credited": total_credited})
    await _record_snapshot(audit_id, "upload_credit_points", changes)
    return {"audit_id": audit_id, "matched": matched, "changed": changed,
            "not_found": not_found, "skipped_zero": skipped_zero,
            "total_points_credited": total_credited}


def _credit_signature(pairs: List[Dict[str, Any]]) -> str:
    """Stable content hash of the (mobile, points) set — identifies the SAME credit file
    regardless of upload id, so an accidental re-run can be detected and blocked."""
    body = ";".join(f"{p.get('mobile')}:{int(p.get('points') or 0)}"
                    for p in sorted(pairs, key=lambda x: str(x.get("mobile"))))
    return hashlib.sha256(body.encode()).hexdigest()


async def _tool_credit_points_from_file(attachment_id: str = "", reason: str = "",
                                        confirm: bool = False, force: bool = False,
                                        user=None) -> Dict[str, Any]:
    """Credit a DIFFERENT (per-row) number of points to each mobile listed in an uploaded
    CSV/XLSX that has a mobile column AND a points column. Points are added as BONUS
    (points_balance + lifetime_points_earned); tier is spend-based so it is unaffected.
    Runs INLINE with an efficient indexed bulk lookup + bulk_write, so even several thousand
    rows finish in a couple of seconds and results are returned immediately. IDEMPOTENT: the
    same file (same mobiles+points) cannot be credited twice within 30 days unless force=true."""
    err = _require_master(user)
    if err:
        return err
    from database import mb_attachments_col
    att = None
    if attachment_id:
        att = await mb_attachments_col.find_one(
            {"id": attachment_id, "user_id": user.get("id")}, {"_id": 0})
    if not att:
        q: Dict[str, Any] = {"user_id": user.get("id"), "kind": "report"}
        if user.get("_mb_session"):
            q["session_id"] = user["_mb_session"]
        att = await mb_attachments_col.find_one(q, {"_id": 0}, sort=[("created_at", -1)])
    if not att:
        return {"error": "No uploaded report found for this conversation. Please attach the points file again."}
    pairs = att.get("mobile_points") or []
    if not pairs:
        return {"error": "No per-row points were detected in that file. It needs BOTH a mobile column and a "
                         "points column (e.g. 'MOBILE' and 'Points to be Credit'). If every number should get "
                         "the SAME amount, use apply_to_uploaded_report with grant_points instead."}
    total_points = sum(int(p.get("points") or 0) for p in pairs)
    sig = _credit_signature(pairs)
    # Idempotency: has this exact file already been credited recently?
    since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    prior = await mb_credit_receipts_col.find_one(
        {"signature": sig, "created_at": {"$gte": since}}, {"_id": 0}, sort=[("created_at", -1)])
    plan = {"action": "credit_points_from_file", "file": att.get("filename"),
            "rows": len(pairs), "total_points": total_points, "awards_bonus": True,
            "dup_mobiles": att.get("dup_mobiles") or 0}
    when_disp = None
    if prior:
        _t = _parse_iso(prior.get("created_at"))
        when_disp = _t.strftime("%d %b %Y, %H:%M UTC") if _t else str(prior.get("created_at"))
        plan["already_credited"] = {
            "when": when_disp, "when_iso": prior.get("created_at"), "by": prior.get("created_by"),
            "audit_id": prior.get("audit_id"), "customers_credited": prior.get("changed"),
            "points_credited": prior.get("total_points_credited"),
            "note": "Show 'when' EXACTLY as given — do not reformat or recompute the date."}
    if not confirm:
        sample_map = await _bulk_find_customers([p["mobile"] for p in pairs[:8]])
        sample = []
        for p in pairs[:8]:
            c = sample_map.get(_last10(p["mobile"]))
            sample.append({"mobile": p["mobile"], "points_to_add": int(p.get("points") or 0),
                           "found": bool(c), "name": (c or {}).get("name"),
                           "balance_before": (c or {}).get("points_balance")})
        plan["preview"] = True
        plan["sample"] = sample
        if prior and not force:
            plan["warning"] = ("⚠️ This EXACT file (same mobiles + points) was ALREADY credited on "
                               f"{when_disp} by {prior.get('created_by')} "
                               f"({prior.get('changed')} customers, {prior.get('total_points_credited')} points, "
                               f"audit {prior.get('audit_id')}). Crediting again would DOUBLE their points. "
                               "Only proceed if the user EXPLICITLY confirms they want to credit it a SECOND "
                               "time — in which case call again with confirm=true AND force=true.")
        plan["confirmation_required"] = ("Confirm with the user + capture a reason, then call again with "
                                          "confirm=true. Credits each mobile ITS OWN points value from the file.")
        return plan
    rerr = _need_reason(reason)
    if rerr:
        return rerr
    if len(pairs) > INLINE_CAP:
        return {"error": f"{len(pairs)} rows exceeds the cap ({INLINE_CAP}). Split the file and run it in parts."}
    # IDEMPOTENCY BLOCK: refuse a duplicate credit of the same file unless explicitly forced.
    if prior and not force:
        return {"error": "ALREADY_CREDITED", "blocked": True, **plan,
                "message": (f"🛑 NOT credited — this exact file was already credited on {when_disp} "
                            f"by {prior.get('created_by')} ({prior.get('changed')} customers, "
                            f"{prior.get('total_points_credited')} points; audit {prior.get('audit_id')}). "
                            "I blocked it to prevent double-crediting. If you truly intend to credit these "
                            "customers a SECOND time, say 'yes, credit again (force)' and I'll proceed.")}

    # Run INLINE (efficient batched: indexed bulk find + bulk_write + insert_many). Even a
    # 7-8k row file finishes in ~2-5s, so we return the applied result immediately — no queue.
    r = await _credit_pairs(pairs, reason, user)
    await mb_credit_receipts_col.insert_one({
        "id": str(uuid.uuid4()), "signature": sig, "attachment_id": att.get("id"),
        "filename": att.get("filename"), "audit_id": r["audit_id"], "changed": r["changed"],
        "matched": r["matched"], "total_points_credited": r["total_points_credited"],
        "reason": reason, "created_at": _now_iso(), "created_by": user.get("email"),
        "forced": bool(force)})
    return {"ok": True, "applied": True, **plan, "audit_id": r["audit_id"],
            "matched_customers": r["matched"], "changed": r["changed"],
            "not_found": r["not_found"], "skipped_zero": r["skipped_zero"],
            "total_points_credited": r["total_points_credited"], "was_forced_recredit": bool(prior),
            "message": f"Credited points from '{att.get('filename')}': {r['changed']} customers credited "
                       f"{r['total_points_credited']} points total ({r['matched']} matched, "
                       f"{r['not_found']} not found"
                       + (f", {r['skipped_zero']} zero-value rows skipped" if r['skipped_zero'] else "")
                       + (" [FORCED re-credit]" if prior and force else "") + ")."}


def _parse_iso(ts: Any):
    try:
        return datetime.fromisoformat(str(ts))
    except Exception:
        return None


def _bulk_bonus_signature(mode: str, value: int, validity_key: str,
                          pairs: List[Dict[str, Any]]) -> str:
    """Content hash of a bulk-bonus batch (mode + value + validity INPUT + the exact set of
    mobile:points awards). Uses the validity input (not the computed expiry timestamp) so a
    quick re-submit of the same batch produces the SAME signature and is caught as a duplicate."""
    body = f"{mode}|{value}|{validity_key}|" + ";".join(
        f"{p['mobile']}:{int(p['points'])}" for p in sorted(pairs, key=lambda x: str(x['mobile'])))
    return hashlib.sha256(body.encode()).hexdigest()


async def bulk_award_bonus(attachment_id: str = "", mode: str = "flat", value: int = 0,
                           expiry_days: int = 0, expiry_date: str = "", reason: str = "",
                           confirm: bool = False, force: bool = False, user=None) -> Dict[str, Any]:
    """Award BONUS loyalty points in BULK to the mobiles listed in an uploaded CSV/XLSX/PDF.
      mode='flat'  → add `value` points to every matched customer.
      mode='topup' → top each matched customer UP TO `value` (award max(0, value - current balance)).
    Validity: `expiry_date` (YYYY-MM-DD) wins, else `expiry_days` from now, else no expiry.
    Points post as `bonus` (points_balance + lifetime_points_earned; tier is spend-based, untouched).
    Preview with confirm=false, apply with confirm=true + reason. IDEMPOTENT — the SAME batch is
    blocked within 30 days unless force=true (prevents the duplicate-bonus problem). Audited,
    snapshotted, UNDOABLE."""
    err = _require_master(user)
    if err:
        return err
    mode = (mode or "flat").lower()
    if mode not in ("flat", "topup"):
        return {"error": "mode must be 'flat' or 'topup'."}
    try:
        value = int(value)
    except Exception:
        return {"error": "The points/target value must be a whole number."}
    if value <= 0:
        return {"error": "The points/target value must be greater than 0."}

    from database import mb_attachments_col
    att = await mb_attachments_col.find_one(
        {"id": attachment_id, "user_id": user.get("id")}, {"_id": 0})
    if not att:
        return {"error": "Uploaded file not found — please upload the mobile-number file again."}
    mobiles = list(dict.fromkeys(att.get("mobiles") or []))
    if not mobiles:
        return {"error": "No valid 10-digit mobile numbers were detected in that file."}

    expires_at = None
    validity_key = "noexp"
    if (expiry_date or "").strip():
        try:
            d = datetime.fromisoformat(expiry_date.strip()[:10])
            expires_at = d.replace(hour=23, minute=59, second=59, tzinfo=timezone.utc).isoformat()
            validity_key = "date:" + expiry_date.strip()[:10]
        except Exception:
            return {"error": "expiry_date must be in YYYY-MM-DD format."}
    elif expiry_days and int(expiry_days) > 0:
        expires_at = (datetime.now(timezone.utc) + timedelta(days=int(expiry_days))).isoformat()
        validity_key = f"days:{int(expiry_days)}"

    cust_map = await _bulk_find_customers(mobiles)
    pairs: List[Dict[str, Any]] = []
    not_found_mobiles: List[str] = []
    matched = not_found = skipped_zero = 0
    for m in mobiles:
        c = cust_map.get(_last10(m))
        if not c:
            not_found += 1
            not_found_mobiles.append(m)
            continue
        matched += 1
        cur = int(c.get("points_balance") or 0)
        pts = value if mode == "flat" else max(0, value - cur)
        if pts <= 0:
            skipped_zero += 1
            continue
        pairs.append({"mobile": c.get("mobile"), "cust_id": c["id"], "points": pts,
                      "balance_before": cur, "name": c.get("name"),
                      "lifetime_before": int(c.get("lifetime_points_earned") or 0)})
    total_points = sum(p["points"] for p in pairs)

    sig = _bulk_bonus_signature(mode, value, validity_key, pairs)
    since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    prior = await mb_credit_receipts_col.find_one(
        {"signature": sig, "created_at": {"$gte": since}}, {"_id": 0}, sort=[("created_at", -1)])

    plan = {"action": "bulk_award_bonus", "mode": mode, "value": value,
            "file": att.get("filename"), "expires_at": expires_at,
            "mobiles_in_file": len(mobiles), "matched_customers": matched,
            "not_found": not_found, "skipped_zero": skipped_zero,
            "not_found_mobiles": not_found_mobiles,
            "customers_to_credit": len(pairs), "total_points": total_points}
    if prior:
        plan["already_awarded"] = {"when": prior.get("created_at"), "by": prior.get("created_by"),
                                   "audit_id": prior.get("audit_id"), "customers": prior.get("changed"),
                                   "points": prior.get("total_points_credited")}

    if not confirm:
        plan["preview"] = True
        plan["sample"] = [{"mobile": p["mobile"], "name": p["name"],
                           "balance_before": p["balance_before"], "points_to_add": p["points"]}
                          for p in pairs[:12]]
        if prior and not force:
            plan["blocked_prior"] = True
            plan["warning"] = (f"This EXACT batch was already awarded on {prior.get('created_at')} by "
                               f"{prior.get('created_by')} ({prior.get('changed')} customers, "
                               f"{prior.get('total_points_credited')} pts). Awarding again would DOUBLE it — "
                               "tick 'award again' (force) only if you truly intend a second award.")
        return plan

    rerr = _need_reason(reason)
    if rerr:
        return rerr
    if not pairs:
        return {"error": "Nothing to award — no matched customer needs points for this batch "
                         f"({not_found} not found, {skipped_zero} already at/above target)."}
    if len(pairs) > BULK_BONUS_CAP:
        return {"error": f"{len(pairs)} customers exceeds the {BULK_BONUS_CAP} cap — split the file and run it in parts."}
    if prior and not force:
        return {"error": "ALREADY_AWARDED", "blocked": True, **plan,
                "message": (f"Blocked to prevent double-crediting — this exact batch was already awarded on "
                            f"{prior.get('created_at')} by {prior.get('created_by')} "
                            f"({prior.get('changed')} customers, {prior.get('total_points_credited')} pts; "
                            f"audit {prior.get('audit_id')}). Re-submit with force=true only to award a SECOND time.")}

    audit_id = str(uuid.uuid4())
    email = user.get("email")
    upd_ops: List[Any] = []
    ledger_docs: List[Dict[str, Any]] = []
    changes: List[Dict[str, Any]] = []
    for p in pairs:
        cid, pts = p["cust_id"], p["points"]
        upd_ops.append(UpdateOne({"id": cid}, {"$inc": {"points_balance": pts,
                                                        "lifetime_points_earned": pts}}))
        ledger_docs.append({"id": str(uuid.uuid4()), "customer_id": cid,
                            "customer_mobile": p["mobile"], "points": pts, "type": "bonus",
                            "kind": "bonus", "reference_type": "bulk_bonus", "reason": reason,
                            "note": f"Bulk bonus ({mode}) from {att.get('filename')}",
                            "expires_at": expires_at, "created_at": _now_iso(),
                            "created_by": email, "via": "bulk_bonus", "fix_audit_id": audit_id})
        changes.append({"cust_id": cid, "mobile": p["mobile"],
                        "points_before": p["balance_before"], "points_after": p["balance_before"] + pts,
                        "lifetime_before": p["lifetime_before"], "lifetime_after": p["lifetime_before"] + pts})
    for i in range(0, len(upd_ops), CREDIT_BATCH):
        with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
            await customers_col.bulk_write(upd_ops[i:i + CREDIT_BATCH], ordered=False)
    for i in range(0, len(ledger_docs), CREDIT_BATCH):
        with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
            await points_ledger_col.insert_many(ledger_docs[i:i + CREDIT_BATCH], ordered=False)
    await _log_master(user, "bulk_award_bonus", "customers", "bulk", reason,
                      {"mode": mode, "value": value, "expires_at": expires_at, "matched": matched,
                       "changed": len(pairs), "total_points": total_points,
                       "file": att.get("filename")}, audit_id=audit_id)
    await _record_snapshot(audit_id, "bulk_award_bonus", changes)
    await mb_credit_receipts_col.insert_one({
        "id": str(uuid.uuid4()), "signature": sig, "attachment_id": att.get("id"),
        "filename": att.get("filename"), "audit_id": audit_id, "changed": len(pairs),
        "matched": matched, "total_points_credited": total_points, "kind": "bulk_bonus",
        "mode": mode, "value": value, "expires_at": expires_at, "reason": reason,
        "created_at": _now_iso(), "created_by": email, "forced": bool(force)})
    return {"ok": True, "applied": True, **plan, "audit_id": audit_id,
            "message": (f"Awarded {total_points:,} bonus pts to {len(pairs):,} customer(s) "
                        f"({'flat ' + str(value) if mode == 'flat' else 'top-up to ' + str(value)}) "
                        f"from '{att.get('filename')}'"
                        + (f", expiring {expires_at[:10]}" if expires_at else ", no expiry")
                        + (f". {not_found} not found" if not_found else "")
                        + (f", {skipped_zero} already at/above target" if skipped_zero else "")
                        + f". Audit {audit_id} — undoable.")}



async def _tool_reverse_duplicate_bonus_credits(filter_reason: str = "", since: str = "",
                                                 window_hours: int = 72, reason: str = "",
                                                 confirm: bool = False, user=None) -> Dict[str, Any]:
    """REMEDIATION (Master Admin). Find customers who received the SAME Master-Brain BONUS credit
    MORE THAN ONCE (accidental re-runs => stacked `$inc`) and reverse the SURPLUS, keeping exactly
    ONE copy each. Groups master_brain bonus ledger rows by (mobile, points, reason); within a
    group, rows created within `window_hours` of the first are treated as duplicates. On apply it
    deducts the excess from points_balance + lifetime_points_earned and writes ONE compensating
    negative adjustment per customer (originals kept for audit). Preview first (confirm=false),
    then confirm=true + reason. Audit-logged, snapshotted, UNDOABLE."""
    err = _require_master(user)
    if err:
        return err
    match: Dict[str, Any] = {"type": "bonus", "reference_type": "master_brain"}
    if filter_reason:
        match["reason"] = filter_reason
    since_iso = since or (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    match["created_at"] = {"$gte": since_iso}
    pipeline = [
        {"$match": match},
        {"$group": {"_id": {"m": "$customer_mobile", "p": "$points", "r": "$reason"},
                    "rows": {"$push": {"created_at": "$created_at"}},
                    "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": 1}}},
    ]
    groups: List[Dict[str, Any]] = []
    with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
        async for g in points_ledger_col.aggregate(pipeline, allowDiskUse=True):
            groups.append(g)

    per_customer: Dict[str, Dict[str, Any]] = {}
    total_excess_points = 0
    total_dupe_rows = 0
    for g in groups:
        m = g["_id"]["m"]
        pts = int(g["_id"]["p"] or 0)
        rows = sorted(g["rows"], key=lambda r: r.get("created_at") or "")
        t0 = _parse_iso(rows[0].get("created_at"))
        dupes = 0
        for r in rows[1:]:
            tr = _parse_iso(r.get("created_at"))
            if (t0 is None or tr is None) or (tr - t0).total_seconds() <= window_hours * 3600:
                dupes += 1
        if dupes <= 0 or pts == 0:
            continue
        ex = pts * dupes
        c = per_customer.setdefault(m, {"excess_points": 0, "dupe_rows": 0})
        c["excess_points"] += ex
        c["dupe_rows"] += dupes
        total_excess_points += ex
        total_dupe_rows += dupes

    # ── Idempotency / over-reversal guard (BUG FIX) ──────────────────────────
    # This tool detects duplicates from the ORIGINAL `bonus` rows but records its reversal as an
    # `adjust` row and never voids the bonus rows — so a REPEAT run re-detected the SAME duplicates
    # and deducted again (the 3× -750 runaway seen on customer 9303632456). Net out the reversals
    # ALREADY applied for each customer and only ever remove the OUTSTANDING surplus (never below 0).
    # Prior reversals are our own master_brain `adjust` rows whose reason mentions "duplicat"
    # (matches both old "Reversal of N duplicates" and new "Reversal of N duplicate bonus credit(s)").
    prior_reversed: Dict[str, int] = {}
    if per_customer:
        with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
            async for r in points_ledger_col.aggregate([
                {"$match": {"customer_mobile": {"$in": list(per_customer.keys())},
                            "type": "adjust", "reference_type": "master_brain",
                            "points": {"$lt": 0},
                            "reason": {"$regex": "duplicat", "$options": "i"}}},
                {"$group": {"_id": "$customer_mobile", "rev": {"$sum": "$points"}}},
            ]):
                prior_reversed[r["_id"]] = -int(r.get("rev") or 0)
    already_reversed_customers = 0
    total_outstanding = 0
    for m, c in per_customer.items():
        already = int(prior_reversed.get(m, 0))
        c["already_reversed"] = already
        c["outstanding"] = max(0, int(c["excess_points"]) - already)
        if c["outstanding"] <= 0:
            already_reversed_customers += 1
        total_outstanding += c["outstanding"]
    effective = {m: c for m, c in per_customer.items() if c["outstanding"] > 0}

    plan = {"action": "reverse_duplicate_bonus_credits",
            "filter_reason": filter_reason or "(all master_brain bonus)",
            "since": since_iso, "window_hours": window_hours,
            "customers_affected": len(effective),
            "duplicate_rows": total_dupe_rows,
            "total_excess_points": total_excess_points,
            "total_points_to_reverse": total_outstanding,
            "already_reversed_customers": already_reversed_customers}
    if not confirm:
        plan["preview"] = True
        plan["sample"] = [{"mobile": m, "excess_points": c["excess_points"],
                           "already_reversed": c["already_reversed"],
                           "outstanding_to_reverse": c["outstanding"],
                           "duplicate_extra_rows": c["dupe_rows"]}
                          for m, c in list(per_customer.items())[:10]]
        if not per_customer:
            plan["note"] = "No duplicate master_brain bonus credits found in this scope."
        elif not effective:
            plan["note"] = (f"Found {len(per_customer)} customer(s) with duplicate bonus credits, but their "
                            f"surplus was ALREADY reversed — nothing outstanding to reverse (idempotent).")
        plan["confirmation_required"] = ("Confirm with the user + capture a reason, then call again with "
                                          "confirm=true. Reverses only the OUTSTANDING surplus (keeps ONE each; "
                                          "never re-reverses what was already corrected).")
        return plan
    if not effective:
        return {"ok": True, "applied": True, **plan,
                "message": ("Nothing outstanding to reverse — the duplicate bonus credits in that scope were "
                            "already corrected (idempotent, no double-deduction).")}
    rerr = _need_reason(reason)
    if rerr:
        return rerr

    cust_map = await _bulk_find_customers(list(effective.keys()))
    upd_ops: List[Any] = []
    ledger_docs: List[Dict[str, Any]] = []
    changes: List[Dict[str, Any]] = []
    reversed_points = 0
    for m, c in effective.items():
        cust = cust_map.get(_last10(m))
        if not cust:
            continue
        ex = int(c["outstanding"])
        if ex <= 0:
            continue
        cid = cust["id"]
        cur = int(cust.get("points_balance") or 0)
        lt = int(cust.get("lifetime_points_earned") or 0)
        upd_ops.append(UpdateOne({"id": cid}, {"$inc": {"points_balance": -ex,
                                                        "lifetime_points_earned": -ex}}))
        ledger_docs.append({"id": str(uuid.uuid4()), "customer_mobile": cust.get("mobile"),
                            "points": -ex, "type": "adjust", "kind": "adjust",
                            "reference_type": "master_brain",
                            "reason": f"Reversal of {c['dupe_rows']} duplicate bonus credit(s) — {reason}",
                            "created_at": _now_iso(), "created_by": user.get("email"), "via": "master_brain"})
        changes.append({"cust_id": cid, "mobile": cust.get("mobile"),
                        "points_before": cur, "points_after": cur - ex,
                        "lifetime_before": lt, "lifetime_after": lt - ex})
        reversed_points += ex

    for i in range(0, len(upd_ops), CREDIT_BATCH):
        with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
            await customers_col.bulk_write(upd_ops[i:i + CREDIT_BATCH], ordered=False)
        _p = (user or {}).get("_mb_progress")
        if _p:
            try: await _p(min(i + CREDIT_BATCH, len(upd_ops)), len(upd_ops), "customers corrected")
            except Exception: pass
    for i in range(0, len(ledger_docs), CREDIT_BATCH):
        with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
            await points_ledger_col.insert_many(ledger_docs[i:i + CREDIT_BATCH], ordered=False)
    audit_id = await _log_master(user, "reverse_duplicate_credits", "customers", "bulk", reason,
                                 {"customers_affected": len(changes), "duplicate_rows": total_dupe_rows,
                                  "total_excess_points": reversed_points, "filter_reason": filter_reason,
                                  "since": since_iso})
    await _record_snapshot(audit_id, "reverse_duplicate_credits", changes)
    return {"ok": True, "applied": True, **plan, "audit_id": audit_id,
            "customers_reversed": len(changes), "points_reversed": reversed_points,
            "message": (f"Reversed duplicate bonus credits: {len(changes)} customers, removed "
                        f"{reversed_points} excess points across {total_dupe_rows} duplicate rows "
                        f"(kept ONE credit each). A correcting adjustment was logged per customer. "
                        f"Audit {audit_id} — this is undoable.")}


# ============================================================
# 6a) LEDGER RECONCILIATION — deterministic per-customer balance repair
#     computed DIRECTLY from points_ledger (bypasses the audit/action log,
#     which on prod is missing events so the snapshot-Undo can't be trusted).
#     Fixes the "top-up ran several times, then a flat adjust was wrongly used
#     to reverse it" corruption: the admin sees the full ledger + candidate
#     balances, confirms the correct value, and it applies audited + undoable.
# ============================================================
RECON_LEDGER_MAX_ROWS = 5000


def _dup_excess_over(rows: List[Dict[str, Any]], window_hours: int) -> int:
    """Points added/removed MORE THAN ONCE by identical, time-clustered ledger rows.
    Groups by (type, points, reason); within a group, rows created within window_hours of the
    first are duplicates. Returns Σ (dupes * points) so it can be netted out of a ledger sum."""
    groups: Dict[Any, List[Dict[str, Any]]] = {}
    for r in rows:
        key = (r.get("type"), int(r.get("points") or 0), (r.get("reason") or "").strip())
        groups.setdefault(key, []).append(r)
    excess = 0
    for (_typ, pts, _rsn), grp in groups.items():
        if len(grp) <= 1 or pts == 0:
            continue
        grp = sorted(grp, key=lambda r: r.get("created_at") or "")
        t0 = _parse_iso(grp[0].get("created_at"))
        dupes = 0
        for r in grp[1:]:
            tr = _parse_iso(r.get("created_at"))
            if (t0 is None or tr is None) or (tr - t0).total_seconds() <= window_hours * 3600:
                dupes += 1
        excess += dupes * pts
    return excess


async def _load_customer_ledger(cust: Dict[str, Any]) -> List[Dict[str, Any]]:
    strs, ints = _mobile_candidates(cust.get("mobile"))
    proj = {"_id": 0, "id": 1, "type": 1, "kind": 1, "points": 1, "reason": 1,
            "reference_type": 1, "bill_number": 1, "created_at": 1, "voided": 1}
    # Query ONLY by the indexed `customer_mobile` (ix_pl_mobile). The previous `$or` with the
    # UNINDEXED `customer_id` + a `voided:{$ne}` negation forced a full 1.5M-doc collection scan
    # per customer (~5s each) — a 10-mobile batch took ~53s and timed out on prod. `voided` is
    # filtered in Python; only ~89 legacy orphan rows lack a mobile (handled by the mobile backfill).
    with pymongo.timeout(60):
        rows = await points_ledger_col.find(
            {"customer_mobile": {"$in": strs + ints}}, proj
        ).sort("created_at", 1).to_list(RECON_LEDGER_MAX_ROWS)
    return [r for r in rows if not r.get("voided")]


async def _bulk_load_ledgers(customers: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Load the non-voided ledger rows for MANY customers in a FEW batched `$in` queries
    (grouped back to each customer by last-10 mobile) instead of one query PER customer.
    The per-customer loop was the source of the batch-reconciler APPLY-phase gateway timeout
    on prod (N sequential ledger reads). Returns {last10_mobile -> [ledger rows, sorted]}."""
    proj = {"_id": 0, "id": 1, "type": 1, "kind": 1, "points": 1, "reason": 1,
            "reference_type": 1, "bill_number": 1, "created_at": 1, "voided": 1,
            "customer_mobile": 1}
    # every stored customer_mobile variant -> the owning customer's last-10 mobile
    cand_to_key: Dict[Any, str] = {}
    for c in customers:
        key = _last10(c.get("mobile"))
        if not key:
            continue
        strs, ints = _mobile_candidates(c.get("mobile"))
        for v in strs + ints:
            cand_to_key[v] = key
    out: Dict[str, List[Dict[str, Any]]] = {}
    cands = list(cand_to_key.keys())
    for i in range(0, len(cands), 1500):
        chunk = cands[i:i + 1500]
        with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
            async for r in points_ledger_col.find({"customer_mobile": {"$in": chunk}}, proj):
                if r.get("voided"):
                    continue
                key = cand_to_key.get(r.get("customer_mobile"))
                if key is not None:
                    out.setdefault(key, []).append(r)
    for key in out:
        out[key].sort(key=lambda r: r.get("created_at") or "")
    return out


def _reconcile_candidates(cust: Dict[str, Any], rows: List[Dict[str, Any]],
                          window_hours: int) -> Dict[str, Any]:
    current = int(cust.get("points_balance") or 0)
    raw_sum = sum(int(r.get("points") or 0) for r in rows)
    dedup_sum = raw_sum - _dup_excess_over(rows, window_hours)
    genuine_rows = [r for r in rows
                    if not (r.get("type") == "adjust" and r.get("reference_type") == "master_brain")]
    genuine_sum = (sum(int(r.get("points") or 0) for r in genuine_rows)
                   - _dup_excess_over(genuine_rows, window_hours))
    return {"current_balance": current, "raw_ledger_sum": raw_sum,
            "dedup_ledger_sum": dedup_sum, "genuine_ledger_sum": genuine_sum,
            "ledger_rows": len(rows), "mb_adjust_rows": len(rows) - len(genuine_rows)}


def _pick_target(cand: Dict[str, Any], strategy: str) -> int:
    s = (strategy or "genuine").lower()
    if s == "raw":
        return cand["raw_ledger_sum"]
    if s == "dedup":
        return cand["dedup_ledger_sum"]
    return cand["genuine_ledger_sum"]


async def _tool_reconcile_ledger_balance(mobile: str = "", strategy: str = "genuine",
                                         target_balance: Optional[int] = None,
                                         expiry_date: str = "", window_hours: int = 72,
                                         floor_zero: bool = True, reason: str = "",
                                         confirm: bool = False, user=None) -> Dict[str, Any]:
    """LEDGER RECONCILER (Master Admin). Recompute ONE customer's correct points balance directly
    from `points_ledger` — repairs corruption (a top-up run several times, then a flat adjust
    wrongly used to reverse it) when the action log is missing events so snapshot-Undo is
    unreliable. Returns the FULL ledger + candidate balances so a human confirms the exact value:
      • raw_ledger_sum     — Σ of every ledger row (as-is)
      • dedup_ledger_sum   — raw minus provable duplicate (identical, time-clustered) rows
      • genuine_ledger_sum — dedup EXCLUDING our own master_brain 'adjust' compensating rows
                             (the botched reversals) — usually the true intended balance.
    Apply sets points_balance to `target_balance` (admin-confirmed; else the `strategy` candidate)
    and writes ONE compensating, audited, UNDOABLE adjust ledger row for the delta."""
    err = _require_master(user)
    if err:
        return err
    cust = await _find_customer(mobile)
    if not cust:
        return {"found": False, "mobile": mobile, "error": "No customer found for that mobile."}
    rows = await _load_customer_ledger(cust)
    cand = _reconcile_candidates(cust, rows, window_hours)
    current = cand["current_balance"]
    tgt = int(target_balance) if target_balance is not None else _pick_target(cand, strategy)
    floored = False
    if floor_zero and tgt < 0:
        tgt, floored = 0, True
    delta = tgt - current

    plan = {"action": "reconcile_ledger_balance", "mobile": cust.get("mobile"),
            "name": cust.get("name"), "strategy": strategy, **cand,
            "target_balance": tgt, "delta": delta, "floored_to_zero": floored}
    if not confirm:
        plan["preview"] = True
        plan["ledger"] = [
            {"date": (r.get("created_at") or "")[:19].replace("T", " "),
             "type": r.get("type") or r.get("kind"), "points": int(r.get("points") or 0),
             "reason": r.get("reason") or "", "bill_number": r.get("bill_number") or "",
             "is_mb_adjust": bool(r.get("type") == "adjust" and r.get("reference_type") == "master_brain")}
            for r in rows[-200:]]
        plan["confirmation_required"] = (
            "Review the ledger + candidate balances, confirm the correct target with the user and a "
            "reason, then call again confirm=true (optionally overriding target_balance).")
        return plan
    rerr = _need_reason(reason)
    if rerr:
        return rerr
    if delta == 0:
        return {"ok": True, "applied": False, **plan,
                "message": f"{cust.get('mobile')} balance ({current}) already matches the target — nothing to change."}
    audit_id = str(uuid.uuid4())
    _exp = None
    if (expiry_date or "").strip() and delta > 0:
        try:
            _ed = datetime.fromisoformat(expiry_date.strip()[:10])
            _exp = _ed.replace(hour=23, minute=59, second=59, tzinfo=timezone.utc).isoformat()
        except Exception:
            return {"error": "expiry_date must be in YYYY-MM-DD format."}
    await customers_col.update_one({"id": cust["id"]}, {"$set": {"points_balance": tgt}})
    await _ledger(cust.get("mobile"), delta, "adjust",
                  f"Ledger reconciliation: balance {current} -> {tgt} ({strategy}) — {reason}",
                  user, extra={"fix_audit_id": audit_id, "expires_at": _exp})
    await _log_master(user, "reconcile_ledger_balance", "customer", cust.get("id"), reason,
                      {"mobile": cust.get("mobile"), "balance_before": current, "balance_after": tgt,
                       "strategy": strategy, "delta": delta, **cand}, audit_id=audit_id)
    await _record_snapshot(audit_id, "reconcile_ledger_balance", [{
        "cust_id": cust["id"], "mobile": cust.get("mobile"),
        "points_before": current, "points_after": tgt}])
    return {"ok": True, "applied": True, "audit_id": audit_id, **plan,
            "message": (f"Reconciled {cust.get('mobile')} from {current} to {tgt} "
                        f"({'+' if delta >= 0 else ''}{delta}) using the '{strategy}' strategy. "
                        f"A compensating ledger entry was logged. Audit {audit_id} — undoable.")}


# ============================================================
# 6a-bulk) BATCH ledger reconciliation — same math, many customers at once
# ============================================================
BULK_RECON_CAP = 3000


async def _tool_reconcile_ledger_bulk(mobiles: List[str] = None, strategy: str = "genuine",
                                      fixed_value: Optional[int] = None, only_raise: bool = False,
                                      expiry_date: str = "", window_hours: int = 72,
                                      floor_zero: bool = True, reason: str = "",
                                      confirm: bool = False, user=None) -> Dict[str, Any]:
    """BATCH LEDGER RECONCILER (Master Admin). Runs the same per-customer ledger recompute as
    `_tool_reconcile_ledger_balance` across MANY mobiles at once. `strategy`:
      genuine/dedup/raw -> recompute the target from each customer's ledger, OR
      'fixed'           -> set every customer to `fixed_value` (e.g. a top-up-to-500 campaign).
    `only_raise=True` never LOWERS a balance (top-up semantics: target = max(current, chosen)).
    `expiry_date` (YYYY-MM-DD) sets the point validity — when a customer is CREDITED (delta>0) the
    compensating ledger row carries this `expires_at` so the restored points expire correctly
    (blank = no expiry). Preview returns a full per-customer table (current -> target + delta);
    apply sets each balance, writes ONE compensating audited ledger row per customer (stamped
    fix_audit_id), snapshots all before/after -> UNDOABLE as a single run. Not-found reported."""
    err = _require_master(user)
    if err:
        return err
    if strategy == "fixed":
        if fixed_value is None:
            return {"error": "Enter the fixed target balance (e.g. 500) for the 'Fixed target' strategy."}
        fixed_value = int(fixed_value)
    expires_at = None
    if (expiry_date or "").strip():
        try:
            _d = datetime.fromisoformat(expiry_date.strip()[:10])
            expires_at = _d.replace(hour=23, minute=59, second=59, tzinfo=timezone.utc).isoformat()
        except Exception:
            return {"error": "expiry_date must be in YYYY-MM-DD format."}
    clean = list(dict.fromkeys(_last10(m) for m in (mobiles or []) if _last10(m)))
    if not clean:
        return {"error": "Paste at least one valid 10-digit mobile number."}
    if len(clean) > BULK_RECON_CAP:
        return {"error": f"{len(clean)} mobiles exceeds the {BULK_RECON_CAP} cap — split the list and run it in parts."}
    cust_map = await _bulk_find_customers(clean)
    matched_custs: List[Dict[str, Any]] = []
    not_found: List[str] = []
    for m in clean:
        c = cust_map.get(m)
        if c:
            matched_custs.append(c)
        else:
            not_found.append(m)
    # Load EVERY matched customer's ledger in a few batched queries (not one-per-customer):
    # the old per-customer loop is what pushed the apply phase past the prod gateway timeout.
    ledger_map = {} if strategy == "fixed" else await _bulk_load_ledgers(matched_custs)
    rows_out: List[Dict[str, Any]] = []
    for c in matched_custs:
        # 'fixed' needs no ledger scan; other strategies recompute from the ledger.
        if strategy == "fixed":
            cand = {"current_balance": int(c.get("points_balance") or 0), "raw_ledger_sum": None,
                    "dedup_ledger_sum": None, "genuine_ledger_sum": None,
                    "ledger_rows": None, "mb_adjust_rows": None}
            base = fixed_value
        else:
            led = ledger_map.get(_last10(c.get("mobile")), [])
            cand = _reconcile_candidates(c, led, window_hours)
            base = _pick_target(cand, strategy)
        cur = cand["current_balance"]
        tgt = max(base, cur) if only_raise else base
        floored = False
        if floor_zero and tgt < 0:
            tgt, floored = 0, True
        rows_out.append({"mobile": c.get("mobile"), "cust_id": c["id"], "name": c.get("name"),
                         **cand, "target_balance": tgt, "delta": tgt - cur,
                         "floored_to_zero": floored})
    to_change = [r for r in rows_out if r["delta"] != 0]
    total_delta = sum(r["delta"] for r in to_change)
    lowered = sum(1 for r in to_change if r["delta"] < 0)
    plan = {"action": "reconcile_ledger_bulk", "strategy": strategy, "window_hours": window_hours,
            "fixed_value": fixed_value if strategy == "fixed" else None, "only_raise": only_raise,
            "expiry_date": expires_at,
            "mobiles_in": len(clean), "matched": len(rows_out), "not_found": len(not_found),
            "to_change": len(to_change), "total_delta": total_delta, "lowered": lowered}
    if not confirm:
        plan["preview"] = True
        plan["sample"] = [{k: r[k] for k in ("mobile", "name", "current_balance", "raw_ledger_sum",
                                             "dedup_ledger_sum", "genuine_ledger_sum",
                                             "target_balance", "delta", "floored_to_zero")}
                          for r in rows_out[:200]]
        plan["not_found_sample"] = not_found[:50]
        return plan
    rerr = _need_reason(reason)
    if rerr:
        return rerr
    if not to_change:
        return {"ok": True, "applied": False, **plan,
                "message": f"Nothing to change — all {len(rows_out)} matched customers already match the '{strategy}' target."}
    audit_id = str(uuid.uuid4())
    email = user.get("email")

    # ── IDEMPOTENT APPLY (fixes the double/triple application on gateway-timeout retries) ──
    # Each customer is flipped wrong -> genuine via an ATOMIC claim: the conditional
    # find_one_and_update only matches WHILE the balance is still NOT the target, so a
    # concurrent second run (or a re-click after a 504) becomes a no-op for anyone already
    # corrected — it can never re-apply. Only the exact call that MOVED a balance writes that
    # customer's ONE compensating ledger row. Run in small concurrent chunks to stay fast.
    async def _claim(r):
        before = await customers_col.find_one_and_update(
            {"id": r["cust_id"], "points_balance": {"$ne": r["target_balance"]}},
            {"$set": {"points_balance": r["target_balance"]}},
            projection={"_id": 0, "points_balance": 1})
        return (r, before)

    claimed: List[Any] = []
    RECON_CLAIM_CHUNK = 50
    for i in range(0, len(to_change), RECON_CLAIM_CHUNK):
        batch = to_change[i:i + RECON_CLAIM_CHUNK]
        with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
            results = await asyncio.gather(*[_claim(r) for r in batch])
        for r, before in results:
            if before is not None:  # this call actually moved the balance -> record it once
                claimed.append((r, int(before.get("points_balance") or 0)))

    if not claimed:
        return {"ok": True, "applied": False, **plan,
                "message": (f"Nothing changed — all {len(to_change)} targeted customer(s) were already at "
                            f"their {('genuine' if strategy == 'genuine' else strategy)} points "
                            f"(already reconciled by a previous run). {len(not_found)} not found.")}

    ledger_docs: List[Dict[str, Any]] = []
    changes: List[Dict[str, Any]] = []
    applied_rows: List[Dict[str, Any]] = []
    applied_delta = 0
    for r, prev in claimed:
        d = r["target_balance"] - prev
        applied_delta += d
        ledger_docs.append({"id": str(uuid.uuid4()), "customer_mobile": r["mobile"],
                            "customer_id": r["cust_id"], "points": d, "type": "adjust",
                            "kind": "adjust", "reference_type": "master_brain",
                            "reason": f"Batch ledger reconciliation: {prev} -> {r['target_balance']} ({strategy}) — {reason}",
                            "created_at": _now_iso(), "created_by": email, "via": "master_brain",
                            "expires_at": (expires_at if d > 0 else None),
                            "fix_audit_id": audit_id})
        changes.append({"cust_id": r["cust_id"], "mobile": r["mobile"],
                        "points_before": prev, "points_after": r["target_balance"]})
        applied_rows.append({"mobile": r["mobile"], "name": r["name"],
                             "previous": prev, "new_balance": r["target_balance"]})
    for i in range(0, len(ledger_docs), CREDIT_BATCH):
        with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
            await points_ledger_col.insert_many(ledger_docs[i:i + CREDIT_BATCH], ordered=False)
    await _log_master(user, "reconcile_ledger_bulk", "customers", "bulk", reason,
                      {"strategy": strategy, "matched": len(rows_out), "changed": len(claimed),
                       "not_found": len(not_found), "total_delta": applied_delta}, audit_id=audit_id)
    await _record_snapshot(audit_id, "reconcile_ledger_bulk", changes)
    return {"ok": True, "applied": True, "audit_id": audit_id, **plan, "changed": len(claimed),
            "applied_rows": applied_rows[:1000],
            "message": (f"Moved {len(claimed)} customer(s) to their {('genuine' if strategy == 'genuine' else strategy)} points "
                        f"(net {'+' if applied_delta >= 0 else ''}{applied_delta} pts"
                        + (f"; credited points expire {expires_at[:10]}" if expires_at else "")
                        + f"). {len(not_found)} not found. Audit {audit_id} — undoable.")}


# ============================================================
# 6b) GENERIC GUARDED BULK FIELD UPDATE on the customers collection
#     (so Master Brain can run a db.customers.updateMany-style fix itself
#      instead of punting to the engineering team)
# ============================================================
BULK_UPDATE_UNDO_CAP = 200000
_PROTECTED_SET_FIELDS = {"_id", "id", "mobile", "customer_mobile"}


def _set_uses_pipeline(set_spec: Dict[str, Any]) -> bool:
    for v in set_spec.values():
        if isinstance(v, str) and v.startswith("$"):
            return True
        if isinstance(v, dict):
            return True
    return False


async def _tool_bulk_update_customers(filter: Dict[str, Any] = None, set: Dict[str, Any] = None,
                                      reason: str = "", confirm: bool = False, user=None) -> Dict[str, Any]:
    """Guarded bulk field update on `customers`. Preview -> confirm -> apply, batched with live
    progress, audit-logged + snapshotted (UNDOABLE). A `set` value may be a literal OR a field
    reference like "$points_balance" (runs as an aggregation-pipeline $set)."""
    err = _require_master(user)
    if err:
        return err
    flt = filter or {}
    set_spec = set or {}
    if not isinstance(flt, dict) or not flt:
        return {"error": "A non-empty `filter` is required — refusing to update the ENTIRE customers "
                         "collection. Add at least one condition (e.g. {\"source\": \"historic_upload\"})."}
    if not isinstance(set_spec, dict) or not set_spec:
        return {"error": "A non-empty `set` object is required (the fields to update)."}
    bad = _PROTECTED_SET_FIELDS.intersection(set_spec.keys())
    if bad:
        return {"error": f"Refusing to modify protected identity field(s): {sorted(bad)}."}

    use_pipeline = _set_uses_pipeline(set_spec)
    update = [{"$set": set_spec}] if use_pipeline else {"$set": set_spec}
    fields = list(set_spec.keys())
    ref_fields = [v[1:] for v in set_spec.values() if isinstance(v, str) and v.startswith("$")]

    with pymongo.timeout(90):
        matched = await customers_col.count_documents(flt)
    proj = {"_id": 0, "mobile": 1, "name": 1}
    for f in fields + ref_fields:
        proj[f] = 1
    with pymongo.timeout(90):
        sample_docs = await customers_col.find(flt, proj).limit(5).to_list(5)
    sample = []
    for d in sample_docs:
        after = {}
        for k, v in set_spec.items():
            if isinstance(v, str) and v.startswith("$"):
                after[k] = d.get(v[1:])
            elif isinstance(v, dict):
                after[k] = "(computed)"
            else:
                after[k] = v
        sample.append({"mobile": d.get("mobile"), "name": d.get("name"),
                       "before": {f: d.get(f) for f in fields}, "after": after})

    plan = {"action": "bulk_update_customers", "collection": "customers",
            "filter_json": json.dumps(flt, default=str), "set_json": json.dumps(set_spec, default=str),
            "matched": matched, "sample": sample, "uses_pipeline": use_pipeline}
    if not confirm:
        plan["preview"] = True
        plan["confirmation_required"] = (
            f"This updates {matched:,} customer document(s), setting {fields}. Audit-logged and UNDOABLE. "
            f"Confirm with the user + a reason, then call again with confirm=true.")
        if matched > BULK_UPDATE_UNDO_CAP:
            plan["warning"] = (f"{matched:,} rows exceed the undo-snapshot cap ({BULK_UPDATE_UNDO_CAP:,}); "
                               f"if applied it will NOT be auto-undoable. Consider narrowing the filter.")
        plan["message"] = (f"Preview: {matched:,} customers match. Fields to set: {fields}. "
                           f"Reply to confirm + give a reason to apply.")
        return plan

    rerr = _need_reason(reason)
    if rerr:
        return rerr
    if matched == 0:
        return {"ok": True, "applied": True, "matched": 0, "modified": 0,
                "message": "No customers matched the filter — nothing to update."}

    undoable = matched <= BULK_UPDATE_UNDO_CAP
    prog = (user or {}).get("_mb_progress")

    # Snapshot the BEFORE values of the changed fields (bounded) so the action can be undone.
    changes: List[Dict[str, Any]] = []
    if undoable:
        snap_proj = {"_id": 0, "id": 1}
        for f in fields:
            snap_proj[f] = 1
        with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
            async for d in customers_col.find(flt, snap_proj):
                changes.append({"cust_id": d.get("id"), "before": {f: d.get(f) for f in fields}})

    # Apply as a SINGLE server-side update_many — MongoDB does it in one pass at any scale
    # (no per-doc fetch, no cross-turn batching), so it either fully applies or errors cleanly;
    # it can never half-apply and be narrated as fabricated "batch progress".
    if prog:
        try: await prog(0, matched, "customers updated")
        except Exception: pass
    with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
        res = await customers_col.update_many(flt, update)
    modified = res.modified_count
    if prog:
        try: await prog(matched, matched, "customers updated")
        except Exception: pass

    audit_id = await _log_master(user, "bulk_field_update", "customers", "bulk", reason,
        {"filter_json": json.dumps(flt, default=str), "set_json": json.dumps(set_spec, default=str),
         "matched": matched, "modified": modified, "fields": fields, "undoable": undoable})
    if undoable and changes:
        await _record_snapshot(audit_id, "bulk_field_update", changes)
    return {"ok": True, "applied": True, "matched": matched, "modified": modified,
            "audit_id": audit_id, "undoable": undoable,
            "message": (f"✅ Updated {modified:,} of {matched:,} matched customer(s) — set {fields}. "
                        f"Audit {audit_id}." + ("" if undoable else " (too large to auto-undo)"))}


async def _reverse_bulk_field_update(changes: List[Dict[str, Any]]) -> int:
    """Undo a bulk_field_update by restoring each doc's snapshotted BEFORE field values."""
    ops = []
    for ch in changes:
        cid = ch.get("cust_id")
        before = ch.get("before") or {}
        if cid and before:
            ops.append(UpdateOne({"id": cid}, {"$set": before}))
    for i in range(0, len(ops), CREDIT_BATCH):
        with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
            await customers_col.bulk_write(ops[i:i + CREDIT_BATCH], ordered=False)
    return len(ops)



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
async def _reverse_changes_bulk(changes: List[Dict[str, Any]], action: str, reason: str,
                                user: Dict[str, Any], job_id: str = None) -> int:
    """Reverse a snapshot's changes efficiently: batched bulk_write ($inc points back /
    $set prior tier) + insert_many compensating ledger. Each batch is wrapped in
    pymongo.timeout so it survives the aggressive prod client timeoutMS."""
    email = user.get("email")
    upd_ops: List[Any] = []
    ledger_docs: List[Dict[str, Any]] = []
    for ch in changes:
        cid = ch.get("cust_id")
        if cid:
            q: Dict[str, Any] = {"id": cid}
        else:
            strs, ints = _mobile_candidates(ch.get("mobile"))
            q = {"mobile": {"$in": strs + ints}}
        upd: Dict[str, Any] = {}
        if ch.get("points_before") is not None:
            delta = int(ch.get("points_before") or 0) - int(ch.get("points_after") or 0)
            inc = {"points_balance": delta}
            if ch.get("lifetime_before") is not None:
                inc["lifetime_points_earned"] = int(ch.get("lifetime_before") or 0) - int(ch.get("lifetime_after") or 0)
            if ch.get("lifetime_redeemed_before") is not None:
                inc["lifetime_points_redeemed"] = int(ch.get("lifetime_redeemed_before") or 0) - int(ch.get("lifetime_redeemed_after") or 0)
            upd["$inc"] = inc
            if ch.get("mobile") and delta:
                ledger_docs.append({"id": str(uuid.uuid4()), "customer_mobile": ch.get("mobile"),
                                    "points": delta, "type": "adjust", "kind": "adjust",
                                    "reference_type": "master_brain",
                                    "reason": f"UNDO {action} — {reason}", "created_at": _now_iso(),
                                    "created_by": email, "via": "master_brain"})
        if "tier_before" in ch:
            upd["$set"] = {"tier": ch.get("tier_before"), "tier_updated_at": _now_iso()}
        if upd:
            upd_ops.append(UpdateOne(q, upd))
    done = 0
    for i in range(0, len(upd_ops), CREDIT_BATCH):
        with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
            await customers_col.bulk_write(upd_ops[i:i + CREDIT_BATCH], ordered=False)
        done += len(upd_ops[i:i + CREDIT_BATCH])
        if job_id:
            await mb_credit_jobs_col.update_one({"id": job_id},
                {"$set": {"processed": done, "heartbeat": _now_iso()}})
    for i in range(0, len(ledger_docs), CREDIT_BATCH):
        with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
            await points_ledger_col.insert_many(ledger_docs[i:i + CREDIT_BATCH], ordered=False)
    return len(upd_ops)


async def _finalize_undo(audit_id: str, act: str, entity: str, reason: str,
                         reversed_count: int, user: Dict[str, Any]) -> str:
    new_audit = await _log_master(user, "undo", entity or "customers", audit_id, reason,
                                  {"undid_action": act, "undid_audit_id": audit_id,
                                   "changes_reversed": reversed_count})
    await audit_logs_col.update_one({"id": audit_id}, {"$set": {
        "undone": True, "undone_at": _now_iso(), "undone_by": user.get("email"),
        "undo_reason": reason, "undo_audit_id": new_audit}})
    await mb_action_snapshots_col.update_one({"audit_id": audit_id}, {"$set": {"undone": True}})
    return new_audit


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
    if act in {"master_action_log", "undo", "send_campaign", "cancel_campaign", "fix_double_redemptions"}:
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

    entity = doc.get("entity") or "customers"
    # Reverse INLINE (efficient batched bulk_write) — fast even for thousands of changes.
    if act == "bulk_field_update":
        reversed_count = await _reverse_bulk_field_update(changes)
    else:
        reversed_count = await _reverse_changes_bulk(changes, act, reason, user)
    # Generic ledger cleanup keyed by audit_id, so any fix that inserted or voided ledger
    # rows is fully rolled back: void the rows it INSERTED, restore the rows it VOIDED.
    try:
        await points_ledger_col.update_many(
            {"fix_audit_id": audit_id, "voided": {"$ne": True}},
            {"$set": {"voided": True, "voided_at": _now_iso(), "voided_by": user.get("email"),
                      "voided_reason": f"Undo of {act} — {reason}"}})
        await points_ledger_col.update_many(
            {"voided_by_audit": audit_id},
            [{"$set": {"voided": False, "points": {"$ifNull": ["$original_points", "$points"]}}},
             {"$unset": ["voided_at", "voided_by", "voided_reason", "voided_by_audit"]}])
    except Exception as e:  # noqa: BLE001
        logger.warning(f"undo ledger cleanup for {audit_id} failed: {e}")
    new_audit = await _finalize_undo(audit_id, act, entity, reason, reversed_count, user)
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
    if at == "cohort" and audience_value:
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
        now = _dt.now(_tz.utc)
        def _ago(days):
            return (now - _td(days=days)).isoformat()
        key, _, arg = (audience_value or "").partition(":")
        key = key.strip().lower()
        base = {"mobile": {"$nin": [None, ""]}}
        if key in {"one_timer", "one_timers", "onetimer", "onetimers"}:
            f = {**base, "visit_count": 1}
            months = int(arg) if arg.strip().isdigit() else None
            if months:
                f["last_visit_at"] = {"$gte": _ago(30 * months)}
            return {"mode": "db", "filter": f,
                    "label": f"one-timers{f' (last {months}mo)' if months else ''}"}, None
        if key == "lapsed":
            return {"mode": "db", "filter": {**base, "last_visit_at": {"$lt": _ago(365)}},
                    "label": "lapsed (12m+)"}, None
        if key == "dormant":
            return {"mode": "db", "filter": {**base, "last_visit_at": {"$gte": _ago(365), "$lt": _ago(182)}},
                    "label": "dormant (6-12m)"}, None
        if key in {"inactive_90", "inactive90", "inactive"}:
            return {"mode": "db", "filter": {**base, "last_visit_at": {"$lt": _ago(90)}},
                    "label": "inactive 90d+"}, None
        if key in {"high_value", "highvalue", "vip"}:
            return {"mode": "db", "filter": {**base, "tier": {"$in": ["Gold", "Platinum", "Elite"]}},
                    "label": "high-value (Gold/Platinum/Elite)"}, None
        return None, (f"Unknown cohort '{audience_value}'. Try one_timers[:months], lapsed, dormant, "
                      f"inactive_90 or high_value.")
    if at == "segment" and audience_value:
        try:
            from routes.segments_routes import compile_tree
            from database import segments_col
            seg = await segments_col.find_one({"id": audience_value}, {"_id": 0})
            if not seg:
                return None, f"Segment '{audience_value}' not found."
            f = await compile_tree(seg.get("tree") or {})
            return {"mode": "db", "filter": f, "label": f"segment:{seg.get('name', audience_value)}"}, None
        except Exception as e:  # noqa: BLE001
            return None, f"Could not resolve segment: {e}"
    return None, (f"Unknown audience_type '{audience_type}'. Use all, tier, city, cohort, segment, "
                  f"report or mobiles.")


async def _is_campaign_cancelled(cid: str) -> bool:
    c = await master_campaigns_col.find_one({"id": cid}, {"_id": 0, "cancel_requested": 1})
    return bool(c and c.get("cancel_requested"))


async def _run_mb_campaign(cid: str) -> None:
    from routes.communications_routes import send_sms_campaign_karix, _render
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
            res = await send_sms_campaign_karix(mobile, text, template_id=camp.get("template_id"),
                                       event_trigger="campaign_bulk",
                                       context={"source": f"master_campaign:{cid}", "campaign_id": cid})
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
        try:
            from database import campaigns_col as _core
            await _core.update_one({"id": cid}, {"$set": {
                "status": "cancelled" if cancelled else "completed", "sent": sent}})
        except Exception:  # noqa: BLE001
            pass
    except Exception as e:  # noqa: BLE001
        await master_campaigns_col.update_one({"id": cid}, {"$set": {
            "status": "failed", "error": str(e), "processed": processed,
            "sent": sent, "failed": failed, "completed_at": _now_iso()}})
        try:
            from database import campaigns_col as _core
            await _core.update_one({"id": cid}, {"$set": {"status": "failed", "sent": sent}})
        except Exception:  # noqa: BLE001
            pass


async def _tool_send_campaign(message: Optional[str] = None, template_id: Optional[str] = None,
                              audience_type: str = "all", audience_value: Optional[str] = None,
                              attachment_id: Optional[str] = None, mobiles: Optional[List[str]] = None,
                              objective: str = "generic", objective_params: Optional[Dict[str, Any]] = None,
                              roi_window: str = "7d", cost: Optional[float] = None,
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
    # Phase 2 — register in the CORE campaigns pipeline so this MB campaign gets unified
    # real ROI + delivery tracking (dataset frozen at t0 = created_at). Never fatal.
    try:
        from routes.campaigns_routes import register_mb_campaign
        await register_mb_campaign(
            cid=cid,
            name=f"[Master Brain] {tpl.get('name') if tpl else (reason[:40] or 'SMS campaign')}",
            spec=spec, count=count, t0=camp["created_at"],
            created_by=(user.get("id") or user.get("email")),
            template_id=template_id, message=(None if tpl else message),
            audience_type=(audience_type or "all"), audience_label=spec.get("label") or "",
            objective=objective or "generic", objective_params=objective_params or {},
            roi_window=roi_window or "7d", cost=cost)
    except Exception as e:  # noqa: BLE001
        logger.warning("MB campaign core-register failed for %s: %s", cid, e)
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


async def _tool_set_customer_tier(tier: str, mobile: Optional[str] = None,
                                  max_lifetime_spend: Optional[float] = None,
                                  min_lifetime_spend: Optional[float] = None,
                                  current_tier: Optional[str] = None,
                                  reason: str = "", confirm: bool = False, user=None) -> Dict[str, Any]:
    """Set a SPECIFIC tier/slab value (even a legacy/custom one) on one customer or a filtered set."""
    err = _require_master(user)
    if err:
        return err
    tier = (tier or "").strip()
    if not tier:
        return {"error": "tier (the slab/value to set) is required, e.g. 'kazo insider'."}
    from routes.loyalty_routes import _active_sorted_tiers
    cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0, "tier_rules": 1}) or {}
    configured = [t["tier"] for t in _active_sorted_tiers(cfg)]
    note = None if tier in configured else (f"'{tier}' is not one of the configured slabs ({configured}); "
                                            f"setting it as an explicit value as requested.")

    if mobile:
        cust = await _find_customer(mobile)
        if not cust:
            return {"found": False, "mobile": mobile, "error": "No customer found."}
        plan = {"action": "set_customer_tier", "scope": "single", "mobile": cust.get("mobile"),
                "current_tier": cust.get("tier"), "new_tier": tier, "awards_bonus": False, "note": note}
        if cust.get("tier") == tier:
            plan["message"] = "Already on that tier — nothing to change."
            return plan
        if not confirm:
            plan["preview"] = True
            return plan
        rerr = _need_reason(reason)
        if rerr:
            return rerr
        await customers_col.update_one({"id": cust["id"]},
                                       {"$set": {"tier": tier, "tier_updated_at": _now_iso()}})
        audit_id = await _log_master(user, "set_customer_tier", "customer", cust.get("id"), reason,
                                     {"mobile": cust.get("mobile"), "from": cust.get("tier"), "to": tier})
        await _record_snapshot(audit_id, "set_customer_tier", [{
            "cust_id": cust["id"], "mobile": cust.get("mobile"),
            "tier_before": cust.get("tier"), "tier_after": tier}])
        return {"ok": True, "applied": True, "audit_id": audit_id, **plan,
                "message": f"Set {cust.get('mobile')} to tier '{tier}' (no bonus points)."}

    # ---- bulk by filter ----
    fil: Dict[str, Any] = {"mobile": {"$nin": [None, ""]}}
    spend: Dict[str, Any] = {}
    if max_lifetime_spend is not None:
        spend["$lte"] = float(max_lifetime_spend)
    if min_lifetime_spend is not None:
        spend["$gte"] = float(min_lifetime_spend)
    if spend:
        fil["lifetime_spend"] = spend
    if current_tier:
        fil["tier"] = current_tier
    if not spend and not current_tier:
        return {"error": "For a bulk tier set, give at least one filter (max_lifetime_spend, "
                         "min_lifetime_spend or current_tier) — refusing to retier ALL customers without a filter. "
                         "Or pass a single mobile."}
    base = {**fil, "tier": {"$ne": tier}}
    count = await customers_col.count_documents(base)
    sample_docs = await customers_col.find(base, {"_id": 0, "mobile": 1, "tier": 1, "lifetime_spend": 1}) \
        .limit(20).to_list(20)
    sample = [{"mobile": d.get("mobile"), "from": d.get("tier"), "to": tier,
               "lifetime_spend": d.get("lifetime_spend")} for d in sample_docs]
    plan = {"action": "set_customer_tier", "scope": "bulk", "new_tier": tier,
            "filter_desc": {"max_lifetime_spend": max_lifetime_spend,
                            "min_lifetime_spend": min_lifetime_spend, "current_tier": current_tier},
            "customers_matched": count, "sample": sample, "awards_bonus": False, "note": note}
    if count == 0:
        plan["message"] = "No customers match that filter (or they're already on the target tier)."
        return plan
    if not confirm:
        plan["preview"] = True
        plan["confirmation_required"] = (f"This sets tier='{tier}' on {count} customers (NO bonus points). "
                                         f"Confirm with the user + a reason, then confirm=true.")
        return plan
    rerr = _need_reason(reason)
    if rerr:
        return rerr
    if count > INLINE_CAP:
        return {"error": f"{count} customers exceeds the inline cap ({INLINE_CAP})."}
    changes: List[Dict[str, Any]] = []
    updated = 0
    last_id = None
    while True:
        q = dict(base)
        if last_id is not None:
            q["_id"] = {"$gt": last_id}
        docs = await customers_col.find(q, {"_id": 1, "id": 1, "mobile": 1, "tier": 1}) \
            .sort("_id", 1).limit(BATCH).to_list(BATCH)
        if not docs:
            break
        ops = []
        for d in docs:
            ops.append(UpdateOne({"_id": d["_id"]}, {"$set": {"tier": tier, "tier_updated_at": _now_iso()}}))
            changes.append({"cust_id": d.get("id"), "mobile": d.get("mobile"),
                            "tier_before": d.get("tier"), "tier_after": tier})
        if ops:
            res = await customers_col.bulk_write(ops, ordered=False)
            updated += res.modified_count
        last_id = docs[-1]["_id"]
        if len(docs) < BATCH:
            break
    audit_id = await _log_master(user, "set_customer_tier_bulk", "customers", "bulk", reason,
                                 {"new_tier": tier, "matched": count, "updated": updated,
                                  "filter": plan["filter_desc"]})
    await _record_snapshot(audit_id, "set_customer_tier_bulk", changes)
    return {"ok": True, "applied": True, "audit_id": audit_id, **plan,
            "customers_updated": updated,
            "message": f"Set {updated} customers to tier '{tier}' (no bonus points). Logged to the action log."}


# ============================================================
# 11) FIX past DOUBLE redemptions (the posAddPoint double-deduct bug)
# ============================================================
_DUP_REDEEM_Q = {"type": "redeem", "reference_type": "transaction",
                 "note": {"$regex": "^Bill "}, "voided": {"$ne": True}}
_LEGIT_REDEEM_NOTES = ["POS OTP redemption", "POS non-OTP redemption"]


async def _scan_double_redemptions(mobile: Optional[str] = None, cap: int = INLINE_CAP + 1) -> List[Dict[str, Any]]:
    """Return CONFIRMED duplicate-redemption ledger rows.

    A row qualifies only if (a) it carries the bug signature (type=redeem,
    reference_type=transaction, note='Bill <no>' — the row the old posAddPoint
    wrote) AND (b) a *legitimate* redeem row (POS OTP / non-OTP) exists for the
    SAME bill — proving the redemption was already counted once, so the bill's
    deduction was a true DOUBLE. This conservative join avoids ever crediting a
    bill that was only deducted once."""
    q = dict(_DUP_REDEEM_Q)
    if mobile:
        strs, ints = _mobile_candidates(mobile)
        q["customer_mobile"] = {"$in": strs + ints}
    rows = await points_ledger_col.find(
        q, {"_id": 0, "id": 1, "points": 1, "note": 1, "customer_id": 1, "customer_mobile": 1}
    ).limit(cap).max_time_ms(20000).to_list(cap)
    if not rows:
        return []
    bills: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        bn = (r.get("note") or "")[5:].strip()  # text after "Bill "
        if bn:
            bills.setdefault(bn, []).append(r)
    legit: set = set()
    bill_list = list(bills.keys())
    for i in range(0, len(bill_list), 1000):
        batch = bill_list[i:i + 1000]
        async for lr in points_ledger_col.find(
                {"type": "redeem", "reference_id": {"$in": batch},
                 "note": {"$in": _LEGIT_REDEEM_NOTES}},
                {"_id": 0, "reference_id": 1}).max_time_ms(30000):
            legit.add(lr.get("reference_id"))
    confirmed: List[Dict[str, Any]] = []
    for bn, rs in bills.items():
        if bn in legit:
            for r in rs:
                r["_bill"] = bn
                confirmed.append(r)
    return confirmed


# Module-level TTL cache for the heavy ledger-sum cross-check (a SECONDARY, informational
# metric). Caching it stops a burst of repeated "negative balance?" questions from each kicking
# off a fresh full-ledger $group on production — the exact load spiral that made the audit time
# out and fall back to the slow LLM loop.
_NEG_LEDGER_CACHE: Dict[str, Any] = {"note": None, "ts": 0.0}
_NEG_LEDGER_TTL = 300.0


async def _neg_ledger_crosscheck() -> str:
    """Return the (cached) ledger-sum negative-balance cross-check note. Tightly capped and
    cached for 5 min so it can never block or pile up under repeated questions."""
    now = _time.time()
    cached = _NEG_LEDGER_CACHE.get("note")
    if cached and (now - _NEG_LEDGER_CACHE.get("ts", 0.0)) < _NEG_LEDGER_TTL:
        return cached
    try:
        lc = await points_ledger_col.aggregate(
            [{"$group": {"_id": "$customer_mobile", "bal": {"$sum": "$points"}}},
             {"$match": {"bal": {"$lt": 0}}}, {"$count": "n"}],
            maxTimeMS=8000, allowDiskUse=True).to_list(1)
        n = lc[0]["n"] if lc else 0
        note = (f"{n} customers have a NEGATIVE ledger-sum (independent cross-check that sums "
                "every points_ledger row per customer).")
    except Exception:  # noqa: BLE001
        note = ("Ledger-sum cross-check not run this time (too large to compute live within the "
                "cap); the authoritative customers.points_balance count above is exact.")
    _NEG_LEDGER_CACHE["note"] = note
    _NEG_LEDGER_CACHE["ts"] = now
    return note


async def _tool_audit_negative_balances(user=None) -> Dict[str, Any]:
    """EXACT, READ-ONLY negative-balance audit. The authoritative count/total/worst come from
    the indexed `customers.points_balance` field in ONE bounded `$facet` aggregation (instant
    even at 1M+ rows). A best-effort ledger-sum cross-check is cached + tightly capped so it can
    NEVER stall the answer (a burst of repeated questions won't each kick off a fresh full-ledger
    $group — the load spiral that caused the production timeouts). If the authoritative compute
    can't finish within the cap we say so HONESTLY — we never return a fake zero."""
    err = _require_master(user)
    if err:
        return err
    field_count = 0
    field_sum = 0
    worst: List[Dict[str, Any]] = []
    computed = False
    try:
        facet = await customers_col.aggregate(
            [{"$match": {"points_balance": {"$lt": 0}}},
             {"$facet": {
                 "stats": [{"$group": {"_id": None, "n": {"$sum": 1},
                                       "total": {"$sum": "$points_balance"}}}],
                 "worst": [{"$sort": {"points_balance": 1}}, {"$limit": 10},
                           {"$project": {"_id": 0, "mobile": 1, "name": 1, "points_balance": 1}}],
             }}],
            maxTimeMS=15000, allowDiskUse=True).to_list(1)
        f = facet[0] if facet else {}
        stats = f.get("stats") or []
        field_count = int(stats[0].get("n") or 0) if stats else 0
        field_sum = int(stats[0].get("total") or 0) if stats else 0
        worst = f.get("worst") or []
        computed = True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"audit_negative_balances authoritative compute failed: {e}")
        computed = False

    # Best-effort, CACHED, tightly-capped ledger-sum cross-check (secondary metric only).
    ledger_note = await _neg_ledger_crosscheck()

    if not computed:
        return {
            "audit": "negative_balances",
            "computed": False,
            "ledger_cross_check": ledger_note,
            "message": ("The negative-balance count couldn't be computed within the time limit on "
                        "this dataset right now (the database is likely under heavy load). Please "
                        "retry in a few seconds — the count comes straight from the indexed "
                        "customers.points_balance field and is normally instant."),
        }
    return {
        "audit": "negative_balances",
        "computed": True,
        "negative_balance_customers": field_count,
        "total_deficit_points": field_sum,
        "worst_customers": worst,
        "source": "customers.points_balance (authoritative, indexed)",
        "ledger_cross_check": ledger_note,
        "reason_hint": ("Negative balances usually come from: redemptions/adjustments exceeding earned "
                        "points, the POS double-deduction bug (run audit_double_redemptions), or "
                        "migration/opening-balance mismatches during historic uploads."),
        "message": (f"{field_count} customers currently have a negative points_balance "
                    f"(total deficit {field_sum} pts)." if field_count
                    else "No customers have a negative points_balance — field balances are clean."),
    }


async def _tool_audit_double_redemptions(mobile: Optional[str] = None, user=None) -> Dict[str, Any]:
    """EXACT, READ-ONLY duplicate-redemption audit (no caps, no sampling). Computes the true
    total of confirmed double-redemption ledger rows, affected customers and double-deducted
    points across the WHOLE dataset via indexed aggregations, so the assistant can answer
    'how many are affected?' precisely. `examples` are illustrative only — never the basis of
    the counts."""
    err = _require_master(user)
    if err:
        return err
    match = dict(_DUP_REDEEM_Q)
    if mobile:
        strs, ints = _mobile_candidates(mobile)
        match["customer_mobile"] = {"$in": strs + ints}
    # Pass 1 — group EVERY bug-signature row by its bill number (exact, uses the
    # (type, reference_type) index for the $match; allowDiskUse for large groups). If the
    # aggregation can't finish within the cap we record that it did NOT complete so we never
    # report a misleading "0 affected / exact" — we tell the user honestly instead.
    p1_ok = True
    try:
        groups = await points_ledger_col.aggregate(
            [{"$match": match},
             {"$addFields": {"_bill": {"$trim": {"input": {"$substrCP": ["$note", 5, 64]}}}}},
             {"$group": {"_id": "$_bill",
                         "bug_rows": {"$sum": 1},
                         "points": {"$sum": {"$abs": "$points"}},
                         "mobiles": {"$addToSet": "$customer_mobile"}}}],
            allowDiskUse=True, maxTimeMS=20000).to_list(None)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"audit_double_redemptions pass-1 did not complete: {e}")
        groups = []
        p1_ok = False
    bills = [g["_id"] for g in groups if g["_id"]]
    # Pass 2 — of those bills, which ALSO have a legitimate POS redeem row (the proof the
    # bill was already counted once, making the bug row a true DOUBLE). Exact, indexed on
    # reference_id, batched. Bounded by a wall-clock budget so it can never run long.
    legit: set = set()
    p2_ok = True
    _t2 = _time.time()
    try:
        for i in range(0, len(bills), 2000):
            if _time.time() - _t2 > 15:
                p2_ok = False
                break
            batch = bills[i:i + 2000]
            async for lr in points_ledger_col.find(
                    {"type": "redeem", "reference_id": {"$in": batch},
                     "note": {"$in": _LEGIT_REDEEM_NOTES}},
                    {"_id": 0, "reference_id": 1}).max_time_ms(8000):
                legit.add(lr.get("reference_id"))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"audit_double_redemptions pass-2 did not complete: {e}")
        p2_ok = False
    if not p1_ok or not p2_ok:
        return {
            "audit": "double_redemptions",
            "scope": "single_customer" if mobile else "all_customers",
            "exact": False,
            "computed": False,
            "message": ("The duplicate-redemption audit couldn't complete an EXACT scan within the "
                        "time limit on this dataset right now (the database is likely under heavy "
                        "load). Please retry in a few seconds, or pass a single customer's mobile "
                        "for an instant exact answer."),
        }
    dup_rows = 0
    dup_points = 0
    custs: set = set()
    examples: List[Dict[str, Any]] = []
    for g in groups:
        if g["_id"] in legit:
            dup_rows += int(g["bug_rows"])
            dup_points += int(g["points"])
            custs.update(m for m in (g.get("mobiles") or []) if m)
            if len(examples) < 10:
                examples.append({"bill": g["_id"], "rows": int(g["bug_rows"]),
                                 "points_double_deducted": int(g["points"])})
    return {
        "audit": "double_redemptions",
        "scope": "single_customer" if mobile else "all_customers",
        "exact": True,
        "duplicate_rows_found": dup_rows,
        "customers_affected": len(custs),
        "points_double_deducted": dup_points,
        "examples": examples,
        "definition": ("A duplicate/double redemption = a points_ledger row with the POS bug "
                       "signature (type=redeem, reference_type=transaction, note='Bill <no>') for a "
                       "bill that ALSO has a legitimate POS OTP/non-OTP redeem row — i.e. the same "
                       "bill's points were deducted twice."),
        "message": ("No double-redemption deductions found"
                    + (f" for {mobile}." if mobile else " across the entire customer base.")
                    if not dup_rows else
                    f"EXACTLY {dup_rows} double-redemption ledger rows across {len(custs)} customers; "
                    f"{dup_points} points were wrongly double-deducted. "
                    "Use the fix_double_redemptions action to credit them back."),
    }


async def _tool_fix_double_redemptions(mobile: Optional[str] = None, reason: str = "",
                                       confirm: bool = False, user=None) -> Dict[str, Any]:
    err = _require_master(user)
    if err:
        return err
    confirmed = await _scan_double_redemptions(mobile)
    over_cap = len(confirmed) > INLINE_CAP
    rows = confirmed[:INLINE_CAP]
    total_points = sum(abs(int(r.get("points") or 0)) for r in rows)
    cust_keys = {(r.get("customer_id") or r.get("customer_mobile")) for r in rows}
    sample = [{"mobile": r.get("customer_mobile"), "bill": r.get("_bill"),
               "points_to_restore": abs(int(r.get("points") or 0))} for r in rows[:10]]
    plan = {"action": "fix_double_redemptions", "scope": "single" if mobile else "bulk",
            "duplicate_rows_found": len(rows), "customers_affected": len(cust_keys),
            "points_to_restore": total_points, "sample": sample,
            "note": "Each row reversed has a confirmed prior OTP/non-OTP redemption for the same "
                    "bill, so the bill's extra deduction is safely credited back."}
    if not rows:
        plan["message"] = ("No double-redemption deductions found"
                           + (f" for {mobile}." if mobile else ".") + " Nothing to fix.")
        return plan
    if over_cap:
        plan["warning"] = (f"More than {INLINE_CAP} duplicate rows exist — this run fixes the first "
                           f"{INLINE_CAP}. Re-run to clear the rest.")
    if not confirm:
        plan["preview"] = True
        plan["confirmation_required"] = ("This CREDITS BACK the wrongly double-deducted points to each "
                                         "customer and VOIDS the duplicate ledger rows. Confirm with the user "
                                         "+ a business reason, then call again with confirm=true.")
        return plan
    rerr = _need_reason(reason)
    if rerr:
        return rerr
    # aggregate the credit per customer
    by_cust: Dict[Any, Dict[str, Any]] = {}
    for r in rows:
        key = r.get("customer_id") or r.get("customer_mobile")
        agg = by_cust.setdefault(key, {"cust_id": r.get("customer_id"),
                                       "mobile": r.get("customer_mobile"), "pts": 0})
        agg["pts"] += abs(int(r.get("points") or 0))
    cust_ops = []
    for agg in by_cust.values():
        if agg["cust_id"]:
            cq: Dict[str, Any] = {"id": agg["cust_id"]}
        else:
            strs, ints = _mobile_candidates(agg["mobile"])
            cq = {"mobile": {"$in": strs + ints}}
        cust_ops.append(UpdateOne(cq, {"$inc": {"points_balance": agg["pts"],
                                                 "lifetime_points_redeemed": -agg["pts"]}}))
    for i in range(0, len(cust_ops), BATCH):
        await customers_col.bulk_write(cust_ops[i:i + BATCH], ordered=False)
    # void the duplicate ledger rows (preserve original points for the audit trail;
    # points=0 so ledger sums no longer count the phantom redemption)
    row_ids = [r.get("id") for r in rows]
    vreason = f"Duplicate redemption auto-corrected by Master Brain — {reason}"
    for i in range(0, len(row_ids), BATCH):
        await points_ledger_col.update_many(
            {"id": {"$in": row_ids[i:i + BATCH]}},
            [{"$set": {"voided": True, "voided_at": _now_iso(), "voided_by": user.get("email"),
                       "voided_reason": vreason,
                       "original_points": {"$ifNull": ["$original_points", "$points"]},
                       "points": 0}}])
    audit_id = await _log_master(user, "fix_double_redemptions", "customers", mobile or "bulk", reason,
                                 {"duplicate_rows_fixed": len(rows), "customers_affected": len(by_cust),
                                  "points_restored": total_points})
    # NOTE: intentionally NO undo snapshot — this is a corrective repair; re-running is
    # idempotent (voided rows are skipped) and a partial auto-undo would re-break balances.
    return {"ok": True, "applied": True, "audit_id": audit_id, **plan,
            "duplicate_rows_fixed": len(rows), "points_restored": total_points,
            "customers_affected": len(by_cust),
            "message": f"Restored {total_points} points to {len(by_cust)} customer(s) and voided "
                       f"{len(rows)} duplicate redemption ledger row(s). Logged to the action log."}


# ============================================================
# DETERMINISTIC DATA-INTEGRITY AUDITS (read-only, exact, no LLM/guesswork)
# ============================================================
async def _tool_audit_missing_redemption_ledger(sample_limit: int = 15, user=None) -> Dict[str, Any]:
    """EXACT, READ-ONLY. Find bills (transactions) that recorded a redemption
    (points_redeemed > 0) but have NO matching `redeem` row in points_ledger, so the
    redemption has no ledger trail. Splits the result by HISTORICAL (bill_date < cutoff —
    audit-gap only, balance is authoritative) vs LIVE (>= cutoff — posAddPoint does not
    deduct, so a bill that never went through the OTP redeem flow means the balance was
    NOT reduced → a real over-balance). Real DB reads only; never a fabricated zero."""
    err = _require_master(user)
    if err:
        return err
    cutoff = await _points_cutoff()
    # Pass 1 — every bill that recorded a redemption (small subset of all bills).
    bills: List[Dict[str, Any]] = []
    try:
        async for tx in transactions_col.find(
                {"points_redeemed": {"$gt": 0}},
                {"_id": 0, "id": 1, "bill_number": 1, "bill_date": 1,
                 "customer_mobile": 1, "points_redeemed": 1}).max_time_ms(25000):
            bills.append(tx)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"audit_missing_redemption_ledger pass-1 incomplete: {e}")
        return {"audit": "missing_redemption_ledger", "computed": False, "exact": False,
                "cutoff_date": cutoff,
                "message": ("Couldn't scan redemption bills within the time limit right now "
                            "(DB likely under load). Please retry in a few seconds.")}
    # Pass 2 — which of those bills ARE covered by a non-voided redeem ledger row,
    # matched by reference_id/bill_number (live) or source_bill_id (historic).
    bill_nos = list({b.get("bill_number") for b in bills if b.get("bill_number")})
    tx_ids = list({b.get("id") for b in bills if b.get("id")})
    covered_bills: set = set()
    covered_srcs: set = set()
    try:
        for i in range(0, len(bill_nos), 5000):
            batch = bill_nos[i:i + 5000]
            async for lr in points_ledger_col.find(
                    {"type": "redeem", "voided": {"$ne": True},
                     "$or": [{"reference_id": {"$in": batch}}, {"bill_number": {"$in": batch}}]},
                    {"_id": 0, "reference_id": 1, "bill_number": 1}).max_time_ms(10000):
                if lr.get("reference_id"):
                    covered_bills.add(lr.get("reference_id"))
                if lr.get("bill_number"):
                    covered_bills.add(lr.get("bill_number"))
        for i in range(0, len(tx_ids), 5000):
            batch = tx_ids[i:i + 5000]
            async for lr in points_ledger_col.find(
                    {"type": "redeem", "voided": {"$ne": True}, "source_bill_id": {"$in": batch}},
                    {"_id": 0, "source_bill_id": 1}).max_time_ms(10000):
                covered_srcs.add(lr.get("source_bill_id"))
    except Exception as e:  # noqa: BLE001
        logger.warning(f"audit_missing_redemption_ledger pass-2 incomplete: {e}")
        return {"audit": "missing_redemption_ledger", "computed": False, "exact": False,
                "cutoff_date": cutoff,
                "message": ("Couldn't cross-check redeem ledger rows within the time limit "
                            "right now. Please retry in a few seconds.")}
    unmatched = [b for b in bills
                 if b.get("bill_number") not in covered_bills and b.get("id") not in covered_srcs]
    # SECOND-PASS SAFETY (mirrors _scan_missing_live_redemptions): the OTP redeem is often
    # keyed to a DIFFERENT bill number than the settlement bill, so an exact-bill match misses
    # it. Also match by (customer, |amount|): a bill is only "missing" if the customer has
    # FEWER non-voided redeem rows for that amount than bills claiming it — so the audit count
    # matches what /fix would actually backfill (no over-reporting).
    missing = unmatched
    if unmatched:
        from collections import Counter, defaultdict
        mobiles = list({b.get("customer_mobile") for b in unmatched if b.get("customer_mobile")})
        have: Dict[str, Counter] = defaultdict(Counter)
        try:
            for i in range(0, len(mobiles), 2000):
                batch = mobiles[i:i + 2000]
                async for lr in points_ledger_col.find(
                        {"type": "redeem", "voided": {"$ne": True}, "customer_mobile": {"$in": batch}},
                        {"_id": 0, "customer_mobile": 1, "points": 1}).max_time_ms(15000):
                    m = lr.get("customer_mobile")
                    amt = abs(int(lr.get("points") or 0))
                    if m and amt:
                        have[m][amt] += 1
        except Exception as e:  # noqa: BLE001
            logger.warning(f"audit_missing_redemption_ledger pass-3 incomplete: {e}")
        missing = []
        used: Dict[str, Counter] = defaultdict(Counter)
        for b in unmatched:
            m = b.get("customer_mobile")
            amt = abs(int(b.get("points_redeemed") or 0))
            if m and amt and used[m][amt] < have.get(m, Counter()).get(amt, 0):
                used[m][amt] += 1  # already ledgered for this customer+amount
                continue
            missing.append(b)

    def _pts(rows):
        return sum(int(r.get("points_redeemed") or 0) for r in rows)

    hist = [b for b in missing if (b.get("bill_date") or "") < cutoff]
    live = [b for b in missing if (b.get("bill_date") or "") >= cutoff]
    sample = [{"mobile": b.get("customer_mobile"), "bill": b.get("bill_number"),
               "bill_date": b.get("bill_date"), "points_redeemed": int(b.get("points_redeemed") or 0),
               "bucket": "historic" if (b.get("bill_date") or "") < cutoff else "live"}
              for b in missing[:max(1, sample_limit)]]
    return {
        "audit": "missing_redemption_ledger", "computed": True, "exact": True,
        "cutoff_date": cutoff,
        "total_bills_with_redemption": len(bills),
        "bills_missing_redeem_ledger": len(missing),
        "customers_affected": len({b.get("customer_mobile") for b in missing if b.get("customer_mobile")}),
        "points_redeemed_without_ledger": _pts(missing),
        "historic_pre_cutoff": {
            "bills": len(hist), "points": _pts(hist),
            "note": "Historical (before cutoff): points_balance is authoritative — this is an "
                    "audit-trail gap only, NOT a balance error."},
        "live_post_cutoff": {
            "bills": len(live), "points": _pts(live),
            "customers": len({b.get("customer_mobile") for b in live if b.get("customer_mobile")}),
            "note": "Live (on/after cutoff): posAddPoint does NOT deduct. If these bills never "
                    "went through the OTP redeem flow, the customer's balance was NOT reduced → "
                    "a real OVER-balance to correct."},
        "sample": sample,
        "message": (f"{len(missing)} of {len(bills)} redemption bills have NO redeem ledger row "
                    f"({_pts(missing)} pts): {len(hist)} historic (audit-gap only) + {len(live)} "
                    f"live (potential over-balance). Cutoff used: {cutoff}."
                    if missing else
                    f"Every redemption bill has a matching redeem ledger row. Clean. Cutoff: {cutoff}."),
    }


async def _tool_audit_duplicate_adjustments(filter_reason: str = "", since: str = "",
                                            user=None) -> Dict[str, Any]:
    """EXACT, READ-ONLY. Find customers who received the SAME point ADJUSTMENT more than
    once — the fingerprint of a bulk adjust job that was run twice. Groups non-voided
    `adjust` ledger rows by (mobile, points, reason); any group with count > 1 has
    `count - 1` surplus rows. Reports surplus rows, customers affected and net surplus
    points (negative surplus = points wrongly deducted twice → owed back on fix)."""
    err = _require_master(user)
    if err:
        return err
    match: Dict[str, Any] = {"type": "adjust", "voided": {"$ne": True}}
    if filter_reason:
        match["reason"] = filter_reason
    if since:
        match["created_at"] = {"$gte": since}
    groups: List[Dict[str, Any]] = []
    try:
        async for g in points_ledger_col.aggregate(
                [{"$match": match},
                 {"$group": {"_id": {"m": "$customer_mobile", "p": "$points", "r": "$reason"},
                             "count": {"$sum": 1}}},
                 {"$match": {"count": {"$gt": 1}}}],
                allowDiskUse=True, maxTimeMS=25000):
            groups.append(g)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"audit_duplicate_adjustments incomplete: {e}")
        return {"audit": "duplicate_adjustments", "computed": False, "exact": False,
                "message": ("Couldn't complete the duplicate-adjustment scan within the time "
                            "limit right now. Please retry in a few seconds.")}
    custs: set = set()
    surplus_rows = 0
    surplus_points = 0
    surplus_negative_points = 0
    sample: List[Dict[str, Any]] = []
    for g in groups:
        extra = int(g["count"]) - 1
        pts = int(g["_id"].get("p") or 0)
        m = g["_id"].get("m")
        if extra <= 0:
            continue
        surplus_rows += extra
        surplus_points += pts * extra
        if pts < 0:
            surplus_negative_points += pts * extra
        if m:
            custs.add(m)
        if len(sample) < 15:
            sample.append({"mobile": m, "points_each": pts, "times": int(g["count"]),
                           "surplus_rows": extra, "reason": g["_id"].get("r")})
    return {
        "audit": "duplicate_adjustments", "computed": True, "exact": True,
        "filter_reason": filter_reason or "(all adjust rows)",
        "since": since or "(all time)",
        "customers_affected": len(custs),
        "surplus_duplicate_rows": surplus_rows,
        "net_surplus_points": surplus_points,
        "surplus_points_wrongly_deducted": abs(surplus_negative_points),
        "sample": sample,
        "definition": ("A duplicate adjustment = >1 identical `adjust` ledger row for the same "
                       "(mobile, points, reason). Surplus = count-1 rows per group."),
        "message": (f"{surplus_rows} surplus duplicate adjustment rows across {len(custs)} "
                    f"customers; net {surplus_points} pts ({abs(surplus_negative_points)} pts were "
                    f"wrongly deducted twice and are owed back)."
                    if surplus_rows else "No duplicate adjustments found in this scope."),
    }


async def _tool_audit_historical_derived_points(user=None) -> Dict[str, Any]:
    """EXACT, READ-ONLY. Quantify COMPUTED/DERIVED points sitting on HISTORICAL data
    (source=historic_upload). Per the canonical rule, historical customers keep ONLY their
    migrated points_balance — no earned/redeemed figures should be derived from spend. This
    reports (a) historic customers whose lifetime_points_earned was derived (>0) and (b)
    non-voided historic `earn`/`bonus` ledger rows — i.e. exactly what would be removed to
    leave points_balance as the sole historical truth."""
    err = _require_master(user)
    if err:
        return err
    cutoff = await _points_cutoff()
    result: Dict[str, Any] = {"audit": "historical_derived_points", "computed": True,
                              "exact": True, "cutoff_date": cutoff}
    try:
        cf = await customers_col.aggregate(
            [{"$match": {"source": "historic_upload", "lifetime_points_earned": {"$gt": 0}}},
             {"$group": {"_id": None, "n": {"$sum": 1},
                         "earned": {"$sum": "$lifetime_points_earned"},
                         "redeemed": {"$sum": "$lifetime_points_redeemed"}}}],
            maxTimeMS=15000, allowDiskUse=True).to_list(1)
        c = cf[0] if cf else {}
        result["historic_customers_with_derived_earned"] = int(c.get("n") or 0)
        result["derived_lifetime_points_earned_total"] = int(c.get("earned") or 0)
        result["derived_lifetime_points_redeemed_total"] = int(c.get("redeemed") or 0)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"historical_derived_points customer facet failed: {e}")
        result["computed"] = False
    try:
        by_type: Dict[str, Dict[str, int]] = {}
        async for g in points_ledger_col.aggregate(
                [{"$match": {"source": "historic_upload", "type": {"$in": ["earn", "bonus"]},
                             "voided": {"$ne": True}}},
                 {"$group": {"_id": "$type", "n": {"$sum": 1}, "pts": {"$sum": "$points"}}}],
                maxTimeMS=15000, allowDiskUse=True):
            by_type[g["_id"]] = {"rows": int(g.get("n") or 0), "points": int(g.get("pts") or 0)}
        result["historic_derived_ledger_rows"] = by_type
        result["historic_derived_ledger_total_rows"] = sum(v["rows"] for v in by_type.values())
        result["historic_derived_ledger_total_points"] = sum(v["points"] for v in by_type.values())
    except Exception as e:  # noqa: BLE001
        logger.warning(f"historical_derived_points ledger facet failed: {e}")
        result["computed"] = False
    result["note"] = ("These are the derived/computed points on historical data. Under the rule "
                      "'historical = balance only', normalize_historical_points would void these "
                      "ledger rows (kept for audit, points->0) and reset the derived lifetime "
                      "fields, leaving points_balance untouched as the sole historical truth.")
    result["message"] = (
        f"Historic customers with derived earned points: "
        f"{result.get('historic_customers_with_derived_earned', '?')} "
        f"(total derived earned {result.get('derived_lifetime_points_earned_total', '?')} pts). "
        f"Historic derived earn/bonus ledger rows: "
        f"{result.get('historic_derived_ledger_total_rows', '?')} "
        f"({result.get('historic_derived_ledger_total_points', '?')} pts). Cutoff: {cutoff}.")
    return result


# ============================================================
# PARTIAL-COMMIT (posAddPoint) audit + repair
# ============================================================
async def _scan_missing_earn_ledger(cutoff: str) -> List[Dict[str, Any]]:
    """Deterministic scan: LIVE POS bills (source=pos_ewards, bill_date >= cutoff) that
    recorded points_earned>0 but have NO non-voided `earn` ledger row — the exact fingerprint
    of a partial commit (bill saved, points never credited/ledgered). Matched by
    reference_id/bill_number."""
    bills: List[Dict[str, Any]] = []
    async for tx in transactions_col.find(
            {"source": "pos_ewards", "points_earned": {"$gt": 0}, "bill_date": {"$gte": cutoff}},
            {"_id": 0, "id": 1, "bill_number": 1, "bill_date": 1, "customer_id": 1,
             "customer_mobile": 1, "points_earned": 1, "commit_status": 1,
             "balance_applied": 1}).max_time_ms(25000):
        bills.append(tx)
    bill_nos = list({b.get("bill_number") for b in bills if b.get("bill_number")})
    tx_ids = list({b.get("id") for b in bills if b.get("id")})
    covered: set = set()
    for i in range(0, len(bill_nos), 5000):
        batch = bill_nos[i:i + 5000]
        async for lr in points_ledger_col.find(
                {"type": "earn", "voided": {"$ne": True},
                 "$or": [{"reference_id": {"$in": batch}}, {"bill_number": {"$in": batch}}]},
                {"_id": 0, "reference_id": 1, "bill_number": 1}).max_time_ms(10000):
            if lr.get("reference_id"):
                covered.add(lr["reference_id"])
            if lr.get("bill_number"):
                covered.add(lr["bill_number"])
    for i in range(0, len(tx_ids), 5000):
        batch = tx_ids[i:i + 5000]
        async for lr in points_ledger_col.find(
                {"type": "earn", "voided": {"$ne": True}, "reference_id": {"$in": batch}},
                {"_id": 0, "reference_id": 1}).max_time_ms(10000):
            covered.add(lr.get("reference_id"))
    return [b for b in bills
            if b.get("bill_number") not in covered and b.get("id") not in covered]


async def _tool_audit_partial_commit_bills(sample_limit: int = 15, user=None) -> Dict[str, Any]:
    """EXACT, READ-ONLY. Find LIVE POS bills (source=pos_ewards, on/after the cutoff) that
    recorded points_earned>0 but have NO matching non-voided `earn` ledger row — the
    fingerprint of a PARTIAL COMMIT (the bill was saved, but a DB timeout interrupted
    crediting so the points were never added to the balance or ledger). These are bills whose
    earned points are currently LOST. Reports how many bills/customers/points are affected so
    repair_partial_commit_bills can heal them. Real DB reads only; never a fabricated zero."""
    err = _require_master(user)
    if err:
        return err
    cutoff = await _points_cutoff()
    try:
        missing = await _scan_missing_earn_ledger(cutoff)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"audit_partial_commit_bills incomplete: {e}")
        return {"audit": "partial_commit_bills", "computed": False, "exact": False,
                "cutoff_date": cutoff,
                "message": ("Couldn't scan for partially-committed bills within the time limit "
                            "right now (DB likely under load). Please retry in a few seconds.")}
    total_pts = sum(int(b.get("points_earned") or 0) for b in missing)
    custs = {b.get("customer_mobile") for b in missing if b.get("customer_mobile")}
    still_pending = sum(1 for b in missing if b.get("commit_status") == "pending")
    sample = [{"mobile": b.get("customer_mobile"), "bill": b.get("bill_number"),
               "bill_date": b.get("bill_date"), "points_earned": int(b.get("points_earned") or 0),
               "commit_status": b.get("commit_status") or "(legacy/none)"}
              for b in missing[:max(1, sample_limit)]]
    return {
        "audit": "partial_commit_bills", "computed": True, "exact": True,
        "cutoff_date": cutoff,
        "bills_missing_earn_ledger": len(missing),
        "still_marked_pending": still_pending,
        "customers_affected": len(custs),
        "points_never_credited": total_pts,
        "sample": sample,
        "definition": ("A partial commit = a live pos_ewards bill with points_earned>0 but no "
                       "non-voided `earn` ledger row. The bill was saved but the balance/ledger "
                       "write was interrupted (DB timeout) → the earned points were never "
                       "credited. repair_partial_commit_bills backfills the earn ledger row and "
                       "credits the missing points."),
        "message": (f"{len(missing)} live bill(s) earned {total_pts} pts that were NEVER credited "
                    f"(no earn ledger row) across {len(custs)} customer(s); {still_pending} are still "
                    f"marked pending. Cutoff: {cutoff}. Run repair_partial_commit_bills to heal them."
                    if missing else
                    f"No partially-committed bills found — every live earn bill has its ledger row. "
                    f"Cutoff: {cutoff}."),
    }


# ============================================================
# DATA HEALTH — daily proactive "Quick Wins" scan.
# Runs the read-only audits OFF the request path (daily scheduler +
# on-demand refresh) and PERSISTS a compact summary to dashboard_kv so
# the Master Brain panel reads it INSTANTLY. Heavy full-collection scans
# run SEQUENTIALLY (never concurrently) to avoid the DB-lock spiral.
# ============================================================
_DATA_HEALTH_DOC_ID = "data_health"
_data_health_lock = asyncio.Lock()
_DH_FIX_ROUTE = "/admin/points-integrity"


def _system_master_user() -> Dict[str, Any]:
    """Synthetic master-admin context for scheduler-run (unauthenticated) audits."""
    return {"id": "system", "email": "scheduler@fundle.io",
            "name": "Data Health Scan", "is_master_admin": True}


def _dh_check(key, title, count, severity, message,
              fix_label=None, extra=None) -> Dict[str, Any]:
    return {"key": key, "title": title, "count": int(count or 0), "severity": severity,
            "message": message, "fix_label": fix_label,
            "fix_route": _DH_FIX_ROUTE if fix_label else None, "extra": extra or {}}


async def run_data_health_scan(triggered_by: str = "scheduler") -> Dict[str, Any]:
    """Run all read-only data-health audits and persist a compact summary to
    dashboard_kv/data_health. NEVER call this inline on a user request — the panel
    only reads the persisted doc via GET /master-brain/data-health."""
    from database import db
    if _data_health_lock.locked():
        cur = await db["dashboard_kv"].find_one({"_id": _DATA_HEALTH_DOC_ID}, {"_id": 0})
        return cur or {"checks": [], "scanning": True}
    async with _data_health_lock:
        await db["dashboard_kv"].update_one(
            {"_id": _DATA_HEALTH_DOC_ID},
            {"$set": {"scanning": True, "triggered_by": triggered_by, "started_at": _now_iso()}},
            upsert=True)
        u = _system_master_user()

        async def _safe(coro):
            try:
                return await coro
            except Exception as e:  # noqa: BLE001
                logger.warning(f"data_health audit failed: {e}")
                return {"computed": False, "error": str(e)}

        # SEQUENTIAL (one heavy scan at a time) to spread DB load.
        neg = await _safe(_tool_audit_negative_balances(user=u))
        partial = await _safe(_tool_audit_partial_commit_bills(user=u))
        dup_redeem = await _safe(_tool_audit_double_redemptions(user=u))
        miss = await _safe(_tool_audit_missing_redemption_ledger(user=u))
        dup_adj = await _safe(_tool_audit_duplicate_adjustments(user=u))
        hist = await _safe(_tool_audit_historical_derived_points(user=u))

        checks: List[Dict[str, Any]] = []

        # 1) Negative balances (authoritative, indexed)
        if neg.get("computed"):
            n = int(neg.get("negative_balance_customers") or 0)
            checks.append(_dh_check(
                "negative_balances", "Negative point balances", n,
                "high" if n else "ok",
                (f"{n:,} customers have a negative balance "
                 f"(total deficit {abs(int(neg.get('total_deficit_points') or 0)):,} pts)."
                 if n else "No negative balances — field balances are clean."),
                fix_label=("Fix negatives" if n else None),
                extra={"total_deficit_points": neg.get("total_deficit_points")}))
        else:
            checks.append(_dh_check("negative_balances", "Negative point balances", 0,
                                    "unknown", "Couldn't compute right now — re-run the scan."))

        # 2) Partial-commit bills (points earned but never credited)
        if partial.get("computed"):
            n = int(partial.get("bills_missing_earn_ledger") or 0)
            checks.append(_dh_check(
                "partial_commit_bills", "Uncredited earn bills", n,
                "high" if n else "ok",
                (f"{n:,} live bill(s) earned {int(partial.get('points_never_credited') or 0):,} pts "
                 f"that were never credited (partial commit)."
                 if n else "Every live earn bill has its ledger row."),
                fix_label=("Repair bills" if n else None),
                extra={"points_never_credited": partial.get("points_never_credited"),
                       "customers_affected": partial.get("customers_affected")}))
        else:
            checks.append(_dh_check("partial_commit_bills", "Uncredited earn bills", 0,
                                    "unknown", "Couldn't compute right now — re-run the scan."))

        # 3) Double redemptions (points deducted twice)
        if dup_redeem.get("exact"):
            n = int(dup_redeem.get("customers_affected") or 0)
            checks.append(_dh_check(
                "double_redemptions", "Double redemptions", n,
                "high" if n else "ok",
                (f"{n:,} customers had {int(dup_redeem.get('duplicate_rows_found') or 0):,} rows "
                 f"double-deduct {int(dup_redeem.get('points_double_deducted') or 0):,} pts."
                 if n else "No double-redemption deductions found."),
                fix_label=("Credit back" if n else None),
                extra={"points_double_deducted": dup_redeem.get("points_double_deducted")}))
        else:
            checks.append(_dh_check("double_redemptions", "Double redemptions", 0,
                                    "unknown", "Couldn't complete an exact scan — re-run the scan."))

        # 4) Missing redemption ledger — LIVE over-balance is the actionable count
        if miss.get("computed"):
            live = (miss.get("live_post_cutoff") or {})
            n = int(live.get("bills") or 0)
            hist_bills = int((miss.get("historic_pre_cutoff") or {}).get("bills") or 0)
            checks.append(_dh_check(
                "missing_redemption_ledger", "Redemptions without a ledger", n,
                "medium" if n else "ok",
                (f"{n:,} LIVE redemption bill(s) have no redeem ledger row "
                 f"(potential over-balance){'; ' + format(hist_bills, ',') + ' historic audit-gap' if hist_bills else ''}."
                 if n else (f"All redemption bills have a ledger row"
                            + (f" ({hist_bills:,} historic audit-gap only)." if hist_bills else "."))),
                fix_label=("Review" if n else None),
                extra={"historic_bills": hist_bills,
                       "live_points": live.get("points")}))
        else:
            checks.append(_dh_check("missing_redemption_ledger", "Redemptions without a ledger", 0,
                                    "unknown", "Couldn't compute right now — re-run the scan."))

        # 5) Duplicate adjustments
        if dup_adj.get("computed"):
            n = int(dup_adj.get("customers_affected") or 0)
            checks.append(_dh_check(
                "duplicate_adjustments", "Duplicate adjustments", n,
                "medium" if n else "ok",
                (f"{n:,} customers have {int(dup_adj.get('surplus_duplicate_rows') or 0):,} surplus "
                 f"duplicate adjustment rows."
                 if n else "No duplicate adjustments found."),
                fix_label=("Review" if n else None),
                extra={"surplus_points_wrongly_deducted": dup_adj.get("surplus_points_wrongly_deducted")}))
        else:
            checks.append(_dh_check("duplicate_adjustments", "Duplicate adjustments", 0,
                                    "unknown", "Couldn't compute right now — re-run the scan."))

        # 6) Historical derived points (informational)
        if hist.get("computed"):
            n = int(hist.get("historic_customers_with_derived_earned") or 0)
            checks.append(_dh_check(
                "historical_derived_points", "Historic derived points", n,
                "low" if n else "ok",
                (f"{n:,} historic customers carry derived earned points "
                 f"({int(hist.get('derived_lifetime_points_earned_total') or 0):,} pts). "
                 f"Per the rule, historic customers keep balance only."
                 if n else "No derived points sitting on historic data."),
                fix_label=("Normalize" if n else None),
                extra={"derived_ledger_rows": hist.get("historic_derived_ledger_total_rows")}))
        else:
            checks.append(_dh_check("historical_derived_points", "Historic derived points", 0,
                                    "unknown", "Couldn't compute right now — re-run the scan."))

        issues = sum(1 for c in checks if c["severity"] in ("high", "medium") and c["count"] > 0)
        summary = {
            "checks": checks,
            "issues": issues,
            "clean": issues == 0,
            "scanning": False,
            "updated_at": _now_iso(),
            "triggered_by": triggered_by,
        }
        await db["dashboard_kv"].update_one(
            {"_id": _DATA_HEALTH_DOC_ID},
            {"$set": summary, "$unset": {"started_at": ""}}, upsert=True)
        summary["_id"] = _DATA_HEALTH_DOC_ID
        summary.pop("_id", None)
        return summary


async def _tool_repair_partial_commit_bills(reason: str = "", confirm: bool = False,
                                            user=None) -> Dict[str, Any]:
    """MUTATION (Master Admin). Heal LIVE POS bills that recorded points_earned>0 but were
    never credited (no `earn` ledger row) — the partial-commit bug. For each such bill it
    writes the missing `earn` ledger row AND credits the earned points to the customer's
    balance (raising lifetime_points_earned), then marks the bill committed. Preview first,
    then confirm=true + reason. Audit-logged, snapshotted, UNDOABLE (undo voids the backfilled
    rows and reverses the credit). Idempotent — a bill already covered by an earn row is skipped."""
    err = _require_master(user)
    if err:
        return err
    cutoff = await _points_cutoff()
    missing = await _scan_missing_earn_ledger(cutoff)
    over_cap = len(missing) > INLINE_CAP
    missing = missing[:INLINE_CAP]
    per_cust: Dict[str, Dict[str, Any]] = {}
    for b in missing:
        m = b.get("customer_mobile")
        if not m:
            continue
        agg = per_cust.setdefault(m, {"pts": 0, "bills": 0})
        agg["pts"] += int(b.get("points_earned") or 0)
        agg["bills"] += 1
    total_pts = sum(a["pts"] for a in per_cust.values())
    plan = {"action": "repair_partial_commit_bills", "cutoff_date": cutoff,
            "live_bills_to_repair": len(missing), "customers_affected": len(per_cust),
            "points_to_credit": total_pts,
            "sample": [{"mobile": m, "points_to_credit": a["pts"], "bills": a["bills"]}
                       for m, a in list(per_cust.items())[:10]]}
    if not missing:
        plan["message"] = "No partially-committed bills found. Nothing to repair."
        return plan
    if over_cap:
        plan["warning"] = (f"More than {INLINE_CAP} bills — this run repairs the first {INLINE_CAP}. "
                           "Re-run for the rest.")
    if not confirm:
        plan["preview"] = True
        plan["confirmation_required"] = ("This CREDITS the earned points that were never applied "
                                         "(writes the missing earn ledger row per bill + raises the "
                                         "balance). Confirm with the user + a reason, then confirm=true.")
        return plan
    rerr = _need_reason(reason)
    if rerr:
        return rerr
    audit_id = str(uuid.uuid4())
    cust_map = await _bulk_find_customers(list(per_cust.keys()))
    ledger_docs: List[Dict[str, Any]] = []
    for b in missing:
        pts = int(b.get("points_earned") or 0)
        if pts <= 0:
            continue
        ledger_docs.append({"id": str(uuid.uuid4()), "customer_id": b.get("customer_id"),
                            "customer_mobile": b.get("customer_mobile"),
                            "points": pts, "type": "earn", "kind": "earn", "ledger_kind": "earn",
                            "reference_type": "transaction", "reference_id": b.get("bill_number"),
                            "source_bill_id": b.get("id"), "bill_number": b.get("bill_number"),
                            "bill_date": b.get("bill_date"),
                            "note": f"Backfilled earn for Bill {b.get('bill_number')} (was never ledgered)",
                            "reason": f"Repair partial-commit earn — {reason}",
                            "created_at": _now_iso(), "created_by": user.get("email"),
                            "via": "master_brain", "fix_audit_id": audit_id})
    upd_ops: List[Any] = []
    changes: List[Dict[str, Any]] = []
    applied_pts = 0
    for m, a in per_cust.items():
        cust = cust_map.get(_last10(m))
        if not cust:
            continue
        cid = cust["id"]
        cur = int(cust.get("points_balance") or 0)
        lte = int(cust.get("lifetime_points_earned") or 0)
        add = int(a["pts"])
        upd_ops.append(UpdateOne({"id": cid}, {"$inc": {"points_balance": add,
                                                        "lifetime_points_earned": add}}))
        changes.append({"cust_id": cid, "mobile": cust.get("mobile"),
                        "points_before": cur, "points_after": cur + add,
                        "lifetime_before": lte, "lifetime_after": lte + add})
        applied_pts += add
    for i in range(0, len(upd_ops), CREDIT_BATCH):
        with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
            await customers_col.bulk_write(upd_ops[i:i + CREDIT_BATCH], ordered=False)
    for i in range(0, len(ledger_docs), CREDIT_BATCH):
        with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
            await points_ledger_col.insert_many(ledger_docs[i:i + CREDIT_BATCH], ordered=False)
    # Mark the healed bills committed so they aren't rescanned.
    healed_bill_nos = [b.get("bill_number") for b in missing if b.get("bill_number")]
    for i in range(0, len(healed_bill_nos), 5000):
        with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
            await transactions_col.update_many(
                {"bill_number": {"$in": healed_bill_nos[i:i + 5000]}},
                {"$set": {"commit_status": "committed", "balance_applied": True,
                          "repaired_by_audit": audit_id, "repaired_at": _now_iso()}})
    await _log_master(user, "repair_partial_commit_bills", "customers", "bulk", reason,
                      {"bills_repaired": len(missing), "customers_affected": len(changes),
                       "points_credited": applied_pts, "cutoff": cutoff}, audit_id=audit_id)
    await _record_snapshot(audit_id, "repair_partial_commit_bills", changes)
    return {"ok": True, "applied": True, "audit_id": audit_id, **plan,
            "points_credited": applied_pts, "customers_corrected": len(changes),
            "message": (f"Repaired {len(missing)} partially-committed bill(s): backfilled the earn "
                        f"ledger rows and credited {applied_pts} pts to {len(changes)} customer(s) whose "
                        f"points were never applied. Audit {audit_id} — undoable.")}


# ============================================================
# LEDGER MOBILE BACKFILL — make every ledger row carry customer_mobile
# ============================================================
# The customer profile (Customer 360) reads the points ledger by customer_mobile.
# Historically the POS earn/redeem ledger rows were written with ONLY customer_id, so a
# redemption correctly reduced the balance but the entry was INVISIBLE on the profile
# (and on any mobile-keyed view: Support Desk redeemed-points, mobile-keyed audits).
# This backfill resolves customer_id -> mobile and stamps customer_mobile on those rows.
async def _tool_backfill_ledger_mobiles(reason: str = "", confirm: bool = False,
                                        mobile: str = "", user=None) -> Dict[str, Any]:
    """READ (preview) / MUTATION (apply). Find points_ledger rows that are MISSING
    customer_mobile but HAVE customer_id, resolve the mobile from the customers master,
    and set customer_mobile on them so every ledger entry shows on the customer profile.
    Optional `mobile` scopes to ONE customer. Preview (confirm=false) -> apply (confirm=true
    + reason). Audit-logged. Safe/idempotent: only fills the missing field, never changes points."""
    err = _require_master(user)
    if err:
        return err
    base_filter: Dict[str, Any] = {
        "$or": [{"customer_mobile": {"$exists": False}}, {"customer_mobile": None},
                {"customer_mobile": ""}],
        "customer_id": {"$exists": True, "$nin": [None, ""]},
    }
    if mobile:
        # scope to a single customer: resolve their id(s) first
        cust = await customers_col.find_one(
            {"mobile": {"$regex": _last10(mobile) + "$"}}, {"_id": 0, "id": 1, "mobile": 1})
        if not cust:
            return {"error": f"No customer found for mobile {mobile}."}
        base_filter["customer_id"] = cust["id"]
    # Collect the distinct customer_ids that need backfilling (bounded scan).
    rows: List[Dict[str, Any]] = []
    with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
        async for r in points_ledger_col.find(
                base_filter, {"_id": 1, "customer_id": 1}).limit(500000):
            rows.append(r)
    total = len(rows)
    cust_ids = list({r.get("customer_id") for r in rows if r.get("customer_id")})
    plan = {"action": "backfill_ledger_mobiles", "ledger_rows_missing_mobile": total,
            "distinct_customers": len(cust_ids), "scope": (mobile or "ALL")}
    if total == 0:
        plan["message"] = "No ledger rows are missing customer_mobile. Nothing to backfill."
        return plan
    if not confirm:
        plan["preview"] = True
        plan["confirmation_required"] = ("This stamps customer_mobile onto the ledger rows that "
                                         "currently only have customer_id, so they appear on the "
                                         "customer profile. It never changes points. Confirm with a reason.")
        return plan
    rerr = _need_reason(reason)
    if rerr:
        return rerr
    # Resolve id -> mobile in batches from the customers master.
    id_to_mobile: Dict[str, str] = {}
    for i in range(0, len(cust_ids), 5000):
        batch = cust_ids[i:i + 5000]
        with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
            async for c in customers_col.find(
                    {"id": {"$in": batch}}, {"_id": 0, "id": 1, "mobile": 1}):
                if c.get("mobile"):
                    id_to_mobile[c["id"]] = c["mobile"]
    # Update all rows for each resolved customer_id in one update_many per id-batch.
    updated = 0
    unresolved_ids = 0
    ops: List[Any] = []
    for cid, mob in id_to_mobile.items():
        q = {"customer_id": cid, "$or": [{"customer_mobile": {"$exists": False}},
                                          {"customer_mobile": None}, {"customer_mobile": ""}]}
        ops.append(UpdateOne(q, {"$set": {"customer_mobile": mob}}))
    unresolved_ids = len([c for c in cust_ids if c not in id_to_mobile])
    for i in range(0, len(ops), CREDIT_BATCH):
        with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
            res = await points_ledger_col.bulk_write(ops[i:i + CREDIT_BATCH], ordered=False)
            updated += (res.modified_count or 0)
    audit_id = str(uuid.uuid4())
    await _log_master(user, "backfill_ledger_mobiles", "points_ledger", "bulk", reason,
                      {"rows_missing": total, "distinct_customers": len(cust_ids),
                       "rows_updated": updated, "unresolved_customers": unresolved_ids,
                       "scope": (mobile or "ALL")}, audit_id=audit_id)
    return {"ok": True, "applied": True, "audit_id": audit_id, **plan,
            "rows_updated": updated, "unresolved_customers": unresolved_ids,
            "message": (f"Backfilled customer_mobile on {updated} ledger row(s) across "
                        f"{len(id_to_mobile)} customer(s). {unresolved_ids} customer_id(s) "
                        f"had no mobile on the master and were skipped.")}



# ============================================================
# DATA-INTEGRITY CORRECTIONS (write-back, preview->confirm, audited, UNDOABLE)
# ============================================================
async def _scan_missing_live_redemptions(cutoff: str, mobile: str = "") -> List[Dict[str, Any]]:
    """Deterministic rescan: LIVE (bill_date >= cutoff) bills with points_redeemed>0 that
    have NO non-voided redeem ledger row. Same logic the audit uses. Optionally scoped to a
    single customer `mobile` (last-10 match) for a targeted single-customer repair."""
    tx_filter: Dict[str, Any] = {"points_redeemed": {"$gt": 0}, "bill_date": {"$gte": cutoff}}
    if mobile:
        tx_filter["customer_mobile"] = {"$regex": _last10(mobile) + "$"}
    bills: List[Dict[str, Any]] = []
    async for tx in transactions_col.find(
            tx_filter,
            {"_id": 0, "id": 1, "bill_number": 1, "bill_date": 1,
             "customer_mobile": 1, "points_redeemed": 1}).max_time_ms(25000):
        bills.append(tx)
    bill_nos = list({b.get("bill_number") for b in bills if b.get("bill_number")})
    tx_ids = list({b.get("id") for b in bills if b.get("id")})
    covered_bills: set = set()
    covered_srcs: set = set()
    for i in range(0, len(bill_nos), 5000):
        batch = bill_nos[i:i + 5000]
        async for lr in points_ledger_col.find(
                {"type": "redeem", "voided": {"$ne": True},
                 "$or": [{"reference_id": {"$in": batch}}, {"bill_number": {"$in": batch}}]},
                {"_id": 0, "reference_id": 1, "bill_number": 1}).max_time_ms(10000):
            if lr.get("reference_id"):
                covered_bills.add(lr["reference_id"])
            if lr.get("bill_number"):
                covered_bills.add(lr["bill_number"])
    for i in range(0, len(tx_ids), 5000):
        batch = tx_ids[i:i + 5000]
        async for lr in points_ledger_col.find(
                {"type": "redeem", "voided": {"$ne": True}, "source_bill_id": {"$in": batch}},
                {"_id": 0, "source_bill_id": 1}).max_time_ms(10000):
            covered_srcs.add(lr.get("source_bill_id"))
    # Bills NOT covered by an exact bill_number / source_bill_id match.
    unmatched = [b for b in bills
                 if b.get("bill_number") not in covered_bills and b.get("id") not in covered_srcs]
    if not unmatched:
        return []
    # SECOND-PASS SAFETY (prevents the double-deduction the earlier repair caused): the OTP
    # redemption is often keyed to a DIFFERENT bill number than the settlement bill, so an
    # exact-bill match misses it and we'd wrongly backfill a duplicate. So we ALSO match by
    # (customer, |amount|): for each customer we count how many non-voided redeem rows already
    # exist per amount vs how many unmatched bills claim that amount, and only backfill the
    # DEFICIT. A customer who already has a redeem row for the same amount is treated as
    # covered even when the bill numbers differ.
    from collections import Counter, defaultdict
    mobiles = list({b.get("customer_mobile") for b in unmatched if b.get("customer_mobile")})
    have: Dict[str, Counter] = defaultdict(Counter)  # mobile -> {amount: count of existing redeem rows}
    for i in range(0, len(mobiles), 2000):
        batch = mobiles[i:i + 2000]
        async for lr in points_ledger_col.find(
                {"type": "redeem", "voided": {"$ne": True}, "customer_mobile": {"$in": batch}},
                {"_id": 0, "customer_mobile": 1, "points": 1}).max_time_ms(15000):
            m = lr.get("customer_mobile")
            amt = abs(int(lr.get("points") or 0))
            if m and amt:
                have[m][amt] += 1
    still_missing: List[Dict[str, Any]] = []
    used: Dict[str, Counter] = defaultdict(Counter)
    for b in unmatched:
        m = b.get("customer_mobile")
        amt = abs(int(b.get("points_redeemed") or 0))
        if not m or not amt:
            still_missing.append(b)
            continue
        if used[m][amt] < have.get(m, Counter()).get(amt, 0):
            used[m][amt] += 1  # an existing redeem row already covers this bill's redemption
            continue
        still_missing.append(b)
    return still_missing


async def _tool_fix_missing_redemption_ledger(reason: str = "", confirm: bool = False,
                                              mobile: str = "", user=None) -> Dict[str, Any]:
    """MUTATION (Master Admin). Correct LIVE (on/after cutoff) bills that recorded a
    redemption but were NEVER deducted (no redeem ledger row) — the customer kept points
    they spent. For each such bill it writes the missing `redeem` ledger row AND deducts the
    points from the balance (raising lifetime_points_redeemed). HISTORICAL bills are left
    untouched (balance is authoritative there). Optional `mobile` scopes the fix to ONE
    customer. Preview first, then confirm=true + reason. Audit-logged, snapshotted, UNDOABLE
    (undo restores balances and voids the backfilled rows)."""
    err = _require_master(user)
    if err:
        return err
    cutoff = await _points_cutoff()
    missing = await _scan_missing_live_redemptions(cutoff, mobile=mobile)
    over_cap = len(missing) > INLINE_CAP
    missing = missing[:INLINE_CAP]
    per_cust: Dict[str, Dict[str, Any]] = {}
    for b in missing:
        m = b.get("customer_mobile")
        if not m:
            continue
        agg = per_cust.setdefault(m, {"pts": 0, "bills": 0})
        agg["pts"] += int(b.get("points_redeemed") or 0)
        agg["bills"] += 1
    total_pts = sum(a["pts"] for a in per_cust.values())
    plan = {"action": "fix_missing_redemption_ledger", "cutoff_date": cutoff,
            "live_bills_to_fix": len(missing), "customers_affected": len(per_cust),
            "points_to_deduct": total_pts,
            "sample": [{"mobile": m, "points_to_deduct": a["pts"], "bills": a["bills"]}
                       for m, a in list(per_cust.items())[:10]]}
    if not missing:
        plan["message"] = "No live redemption bills are missing a ledger row. Nothing to fix."
        return plan
    if over_cap:
        plan["warning"] = (f"More than {INLINE_CAP} bills — this run fixes the first {INLINE_CAP}. "
                           "Re-run for the rest.")
    if not confirm:
        plan["preview"] = True
        plan["confirmation_required"] = ("This DEDUCTS the redeemed points from each customer's balance "
                                         "(they were never debited) and writes the missing redeem ledger "
                                         "row per bill. Confirm with the user + a reason, then confirm=true.")
        return plan
    rerr = _need_reason(reason)
    if rerr:
        return rerr
    audit_id = str(uuid.uuid4())
    cust_map = await _bulk_find_customers(list(per_cust.keys()))
    ledger_docs: List[Dict[str, Any]] = []
    for b in missing:
        ledger_docs.append({"id": str(uuid.uuid4()), "customer_mobile": b.get("customer_mobile"),
                            "points": -int(b.get("points_redeemed") or 0), "type": "redeem",
                            "kind": "redeem", "reference_type": "transaction",
                            "reference_id": b.get("bill_number"), "source_bill_id": b.get("id"),
                            "bill_number": b.get("bill_number"), "bill_date": b.get("bill_date"),
                            "note": "Backfilled missing redemption (was never ledgered)",
                            "reason": f"Backfill missing redemption — {reason}",
                            "created_at": _now_iso(), "created_by": user.get("email"),
                            "via": "master_brain", "fix_audit_id": audit_id})
    upd_ops: List[Any] = []
    changes: List[Dict[str, Any]] = []
    applied_pts = 0
    for m, a in per_cust.items():
        cust = cust_map.get(_last10(m))
        if not cust:
            continue
        cid = cust["id"]
        cur = int(cust.get("points_balance") or 0)
        ltr = int(cust.get("lifetime_points_redeemed") or 0)
        ex = int(a["pts"])
        upd_ops.append(UpdateOne({"id": cid}, {"$inc": {"points_balance": -ex,
                                                        "lifetime_points_redeemed": ex}}))
        changes.append({"cust_id": cid, "mobile": cust.get("mobile"),
                        "points_before": cur, "points_after": cur - ex,
                        "lifetime_redeemed_before": ltr, "lifetime_redeemed_after": ltr + ex})
        applied_pts += ex
    for i in range(0, len(upd_ops), CREDIT_BATCH):
        with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
            await customers_col.bulk_write(upd_ops[i:i + CREDIT_BATCH], ordered=False)
    for i in range(0, len(ledger_docs), CREDIT_BATCH):
        with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
            await points_ledger_col.insert_many(ledger_docs[i:i + CREDIT_BATCH], ordered=False)
    await _log_master(user, "fix_missing_redemption_ledger", "customers", "bulk", reason,
                      {"bills_fixed": len(missing), "customers_affected": len(changes),
                       "points_deducted": applied_pts, "cutoff": cutoff}, audit_id=audit_id)
    await _record_snapshot(audit_id, "fix_missing_redemption_ledger", changes)
    return {"ok": True, "applied": True, "audit_id": audit_id, **plan,
            "points_deducted": applied_pts, "customers_corrected": len(changes),
            "message": (f"Backfilled {len(missing)} missing redemption ledger rows and deducted "
                        f"{applied_pts} points from {len(changes)} customer(s) whose balance was never "
                        f"reduced. Audit {audit_id} — undoable.")}


async def _tool_reverse_duplicate_adjustments(filter_reason: str = "", since: str = "",
                                              reason: str = "", confirm: bool = False,
                                              user=None) -> Dict[str, Any]:
    """MUTATION (Master Admin). Reverse DUPLICATE point adjustments (a bulk adjust job run
    twice). Groups non-voided `adjust` rows by (mobile, points, reason); keeps ONE row per
    group and voids the surplus, correcting each balance by the removed amount (so a
    double-deduction is credited back). Preview first, then confirm=true + reason.
    Audit-logged, snapshotted, UNDOABLE."""
    err = _require_master(user)
    if err:
        return err
    match: Dict[str, Any] = {"type": "adjust", "voided": {"$ne": True}}
    if filter_reason:
        match["reason"] = filter_reason
    if since:
        match["created_at"] = {"$gte": since}
    groups: List[Dict[str, Any]] = []
    try:
        async for g in points_ledger_col.aggregate(
                [{"$match": match},
                 {"$group": {"_id": {"m": "$customer_mobile", "p": "$points", "r": "$reason"},
                             "rows": {"$push": {"id": "$id", "created_at": "$created_at"}},
                             "count": {"$sum": 1}}},
                 {"$match": {"count": {"$gt": 1}}}], allowDiskUse=True, maxTimeMS=25000):
            groups.append(g)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"reverse_duplicate_adjustments scan incomplete: {e}")
        return {"action": "reverse_duplicate_adjustments", "computed": False,
                "message": "Couldn't complete the duplicate-adjustment scan right now. Retry shortly."}
    per_cust: Dict[str, Dict[str, Any]] = {}
    void_ids: List[str] = []
    total_surplus_rows = 0
    total_restore = 0
    for g in groups:
        m = g["_id"].get("m")
        pts = int(g["_id"].get("p") or 0)
        rows = sorted(g["rows"], key=lambda r: r.get("created_at") or "")
        surplus = rows[1:]  # keep the earliest, void the rest
        if not surplus or not m:
            continue
        ex = pts * len(surplus)                # signed sum of the surplus rows
        void_ids.extend([r["id"] for r in surplus if r.get("id")])
        total_surplus_rows += len(surplus)
        c = per_cust.setdefault(m, {"restore": 0, "rows": 0})
        c["restore"] += -ex                    # removing surplus => balance += -ex
        c["rows"] += len(surplus)
        total_restore += -ex
    plan = {"action": "reverse_duplicate_adjustments",
            "filter_reason": filter_reason or "(all adjust rows)", "since": since or "(all time)",
            "customers_affected": len(per_cust), "surplus_rows_to_void": total_surplus_rows,
            "net_balance_correction": total_restore,
            "sample": [{"mobile": m, "balance_correction": c["restore"], "surplus_rows": c["rows"]}
                       for m, c in list(per_cust.items())[:10]]}
    if not per_cust:
        plan["message"] = "No duplicate adjustments found in this scope. Nothing to reverse."
        return plan
    if not confirm:
        plan["preview"] = True
        plan["confirmation_required"] = ("This VOIDS the surplus duplicate adjustment rows (keeps ONE "
                                         "each) and corrects each balance by the removed amount. Confirm "
                                         "with the user + a reason, then confirm=true.")
        return plan
    rerr = _need_reason(reason)
    if rerr:
        return rerr
    audit_id = str(uuid.uuid4())
    cust_map = await _bulk_find_customers(list(per_cust.keys()))
    upd_ops: List[Any] = []
    changes: List[Dict[str, Any]] = []
    applied = 0
    for m, c in per_cust.items():
        cust = cust_map.get(_last10(m))
        if not cust:
            continue
        cid = cust["id"]
        cur = int(cust.get("points_balance") or 0)
        r = int(c["restore"])
        upd_ops.append(UpdateOne({"id": cid}, {"$inc": {"points_balance": r}}))
        changes.append({"cust_id": cid, "mobile": cust.get("mobile"),
                        "points_before": cur, "points_after": cur + r})
        applied += 1
    for i in range(0, len(upd_ops), CREDIT_BATCH):
        with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
            await customers_col.bulk_write(upd_ops[i:i + CREDIT_BATCH], ordered=False)
    vreason = f"Duplicate adjustment reversed by Master Brain — {reason}"
    for i in range(0, len(void_ids), BATCH):
        await points_ledger_col.update_many(
            {"id": {"$in": void_ids[i:i + BATCH]}},
            [{"$set": {"voided": True, "voided_at": _now_iso(), "voided_by": user.get("email"),
                       "voided_reason": vreason, "voided_by_audit": audit_id,
                       "original_points": {"$ifNull": ["$original_points", "$points"]}, "points": 0}}])
    await _log_master(user, "reverse_duplicate_adjustments", "customers", "bulk", reason,
                      {"customers_affected": len(changes), "surplus_rows_voided": total_surplus_rows,
                       "net_balance_correction": total_restore}, audit_id=audit_id)
    await _record_snapshot(audit_id, "reverse_duplicate_adjustments", changes)
    return {"ok": True, "applied": True, "audit_id": audit_id, **plan,
            "customers_corrected": len(changes), "surplus_rows_voided": total_surplus_rows,
            "message": (f"Reversed duplicate adjustments for {len(changes)} customer(s): voided "
                        f"{total_surplus_rows} surplus rows and corrected balances by {total_restore} "
                        f"pts net. Audit {audit_id} — undoable.")}


async def _tool_reverse_tier_upgrade_bonus(start: str = "", end: str = "",
                                           migrated_only: bool = True, mobile: str = "",
                                           reason: str = "", confirm: bool = False,
                                           user=None) -> Dict[str, Any]:
    """MUTATION (Master Admin). Reverse WRONG tier-upgrade bonus points awarded when migrated
    customers were re-tiered from a LEGACY tier onto a KAZO slab by a live bill (their already
    high historic lifetime spend qualified them, so it was NOT a bonus-earning upgrade). Finds
    non-voided `tier_upgrade` bonus ledger rows in an optional [start, end] window (created_at
    ISO date), optionally scoped to migrated (source=historic_upload) customers or one mobile;
    voids them (kept for audit) and deducts the points from balance + lifetime_points_earned.
    Preview first, then confirm=true + reason. Audit-logged, snapshotted, UNDOABLE."""
    err = _require_master(user)
    if err:
        return err
    match: Dict[str, Any] = {"type": "bonus", "ledger_kind": "tier_upgrade", "voided": {"$ne": True}}
    cr: Dict[str, Any] = {}
    if start:
        cr["$gte"] = start
    if end:
        cr["$lte"] = end if len(end) > 10 else end + "T23:59:59"
    if cr:
        match["created_at"] = cr
    if mobile:
        match["customer_mobile"] = {"$regex": _last10(mobile) + "$"}
    rows: List[Dict[str, Any]] = []
    with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
        async for lr in points_ledger_col.find(
                match, {"_id": 0, "id": 1, "customer_mobile": 1, "points": 1,
                        "note": 1, "created_at": 1}):
            rows.append(lr)
    # optionally keep only migrated (historic_upload) customers
    if migrated_only and rows:
        mset = list({r.get("customer_mobile") for r in rows if r.get("customer_mobile")})
        migrated: set = set()
        for i in range(0, len(mset), 5000):
            batch = mset[i:i + 5000]
            async for c in customers_col.find(
                    {"mobile": {"$in": batch}, "source": "historic_upload"},
                    {"_id": 0, "mobile": 1}):
                migrated.add(c["mobile"])
        rows = [r for r in rows if r.get("customer_mobile") in migrated]
    per_cust: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        m = r.get("customer_mobile")
        if not m:
            continue
        agg = per_cust.setdefault(m, {"pts": 0, "rows": 0})
        agg["pts"] += int(r.get("points") or 0)
        agg["rows"] += 1
    total_pts = sum(a["pts"] for a in per_cust.values())
    plan = {"action": "reverse_tier_upgrade_bonus",
            "window": {"start": start or "(all)", "end": end or "(all)"},
            "migrated_only": migrated_only, "scope": (mobile or "ALL"),
            "bonus_rows": len(rows), "customers_affected": len(per_cust),
            "points_to_reverse": total_pts,
            "sample": [{"mobile": m, "points": a["pts"], "rows": a["rows"]}
                       for m, a in list(per_cust.items())[:10]]}
    if not rows:
        plan["message"] = "No tier-upgrade bonus rows match that scope. Nothing to reverse."
        return plan
    if not confirm:
        plan["preview"] = True
        plan["confirmation_required"] = ("This VOIDS the matched tier-upgrade bonus rows and deducts "
                                         "those points from each customer's balance. Confirm with a reason.")
        return plan
    rerr = _need_reason(reason)
    if rerr:
        return rerr
    audit_id = str(uuid.uuid4())
    cust_map = await _bulk_find_customers(list(per_cust.keys()))
    upd_ops: List[Any] = []
    changes: List[Dict[str, Any]] = []
    reversed_pts = 0
    for m, a in per_cust.items():
        cust = cust_map.get(_last10(m))
        if not cust:
            continue
        cid = cust["id"]
        cur = int(cust.get("points_balance") or 0)
        lt = int(cust.get("lifetime_points_earned") or 0)
        ex = int(a["pts"])
        upd_ops.append(UpdateOne({"id": cid}, {"$inc": {"points_balance": -ex,
                                                        "lifetime_points_earned": -ex}}))
        changes.append({"cust_id": cid, "mobile": cust.get("mobile"),
                        "points_before": cur, "points_after": cur - ex,
                        "lifetime_before": lt, "lifetime_after": lt - ex})
        reversed_pts += ex
    for i in range(0, len(upd_ops), CREDIT_BATCH):
        with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
            await customers_col.bulk_write(upd_ops[i:i + CREDIT_BATCH], ordered=False)
    # Void the tier-upgrade rows (kept for audit; undo un-voids via voided_by_audit).
    row_ids = [r["id"] for r in rows if r.get("id")]
    for i in range(0, len(row_ids), CREDIT_BATCH):
        batch = row_ids[i:i + CREDIT_BATCH]
        with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
            await points_ledger_col.update_many(
                {"id": {"$in": batch}},
                [{"$set": {"voided": True, "voided_at": _now_iso(), "voided_by": user.get("email"),
                           "voided_reason": f"Reversed wrong tier-upgrade migration bonus — {reason}",
                           "voided_by_audit": audit_id,
                           "original_points": {"$ifNull": ["$original_points", "$points"]}, "points": 0}}])
    await _log_master(user, "reverse_tier_upgrade_bonus", "customers", "bulk", reason,
                      {"bonus_rows": len(rows), "customers_affected": len(changes),
                       "points_reversed": reversed_pts, "migrated_only": migrated_only}, audit_id=audit_id)
    await _record_snapshot(audit_id, "reverse_tier_upgrade_bonus", changes)
    return {"ok": True, "applied": True, "audit_id": audit_id, **plan,
            "points_reversed": reversed_pts, "customers_corrected": len(changes),
            "message": (f"Reversed {reversed_pts} tier-upgrade bonus points across {len(changes)} "
                        f"customer(s); voided {len(row_ids)} bonus row(s). Audit {audit_id} — undoable.")}



async def _tool_normalize_historical_points(reason: str = "", confirm: bool = False,
                                            user=None) -> Dict[str, Any]:
    """MUTATION (Master Admin). Enforce the rule 'HISTORICAL = balance only'. For migrated
    (source=historic_upload) customers it (1) VOIDS the derived historic `earn`/`bonus`
    ledger rows (kept for audit, points->0) and (2) resets lifetime_points_earned and
    lifetime_points_redeemed to 0 and flags historical_balance_authoritative=true — leaving
    points_balance completely untouched as the sole historical truth. Preview first, then
    confirm=true + reason. Audit-logged, snapshotted, UNDOABLE."""
    err = _require_master(user)
    if err:
        return err
    # Target customers: migrated, with a derived earned/redeemed figure to clear.
    tgt_filter = {"source": "historic_upload",
                  "$or": [{"lifetime_points_earned": {"$gt": 0}},
                          {"lifetime_points_redeemed": {"$gt": 0}}]}
    targets: List[Dict[str, Any]] = []
    async for c in customers_col.find(
            tgt_filter,
            {"_id": 0, "id": 1, "mobile": 1, "points_balance": 1,
             "lifetime_points_earned": 1, "lifetime_points_redeemed": 1}).max_time_ms(25000):
        targets.append(c)
    over_cap = len(targets) > INLINE_CAP
    targets = targets[:INLINE_CAP]
    # Count the derived ledger rows that would be voided.
    ledger_rows = 0
    ledger_points = 0
    try:
        async for g in points_ledger_col.aggregate(
                [{"$match": {"source": "historic_upload", "type": {"$in": ["earn", "bonus"]},
                             "voided": {"$ne": True}}},
                 {"$group": {"_id": None, "n": {"$sum": 1}, "pts": {"$sum": "$points"}}}],
                maxTimeMS=15000, allowDiskUse=True):
            ledger_rows = int(g.get("n") or 0)
            ledger_points = int(g.get("pts") or 0)
    except Exception:  # noqa: BLE001
        pass
    plan = {"action": "normalize_historical_points",
            "historic_customers_to_reset": len(targets),
            "derived_earned_ledger_rows_to_void": ledger_rows,
            "derived_earned_ledger_points": ledger_points,
            "sample": [{"mobile": t.get("mobile"), "points_balance": int(t.get("points_balance") or 0),
                        "lifetime_earned_now": int(t.get("lifetime_points_earned") or 0)}
                       for t in targets[:10]],
            "note": "points_balance is NOT changed — only derived earned/redeemed figures + their "
                    "earn/bonus ledger rows are cleared."}
    if not targets and not ledger_rows:
        plan["message"] = "No derived historical points found. Nothing to normalize."
        return plan
    if over_cap:
        plan["warning"] = (f"More than {INLINE_CAP} historic customers — this run resets the first "
                           f"{INLINE_CAP}. Re-run for the rest.")
    if not confirm:
        plan["preview"] = True
        plan["confirmation_required"] = ("This VOIDS derived historic earn/bonus ledger rows and resets "
                                         "lifetime_points_earned/redeemed to 0 (balance untouched). "
                                         "Confirm with the user + a reason, then confirm=true.")
        return plan
    rerr = _need_reason(reason)
    if rerr:
        return rerr
    audit_id = str(uuid.uuid4())
    # Undo snapshot (bounded) from the targets we already read.
    changes: List[Dict[str, Any]] = []
    for t in targets:
        cur = int(t.get("points_balance") or 0)
        changes.append({"cust_id": t["id"], "mobile": t.get("mobile"),
                        "points_before": cur, "points_after": cur,          # balance unchanged
                        "lifetime_before": int(t.get("lifetime_points_earned") or 0), "lifetime_after": 0,
                        "lifetime_redeemed_before": int(t.get("lifetime_points_redeemed") or 0),
                        "lifetime_redeemed_after": 0})
    # Reset in ONE server-side update_many — completes in a single pass for EVERY matching
    # historic customer at any scale (no per-doc writes, no cross-turn batching to fabricate).
    with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
        reset_res = await customers_col.update_many(tgt_filter, {"$set": {
            "lifetime_points_earned": 0, "lifetime_points_redeemed": 0,
            "historical_balance_authoritative": True}})
    customers_reset = reset_res.modified_count
    # Void the derived historic earn/bonus ledger rows (kept for audit, points->0).
    vreason = f"Historic derived points removed (balance-only rule) — {reason}"
    with pymongo.timeout(CREDIT_JOB_DB_DEADLINE):
        await points_ledger_col.update_many(
            {"source": "historic_upload", "type": {"$in": ["earn", "bonus"]}, "voided": {"$ne": True}},
            [{"$set": {"voided": True, "voided_at": _now_iso(), "voided_by": user.get("email"),
                       "voided_reason": vreason, "voided_by_audit": audit_id,
                       "original_points": {"$ifNull": ["$original_points", "$points"]}, "points": 0}}])
    await _log_master(user, "normalize_historical_points", "customers", "bulk", reason,
                      {"customers_reset": customers_reset, "ledger_rows_voided": ledger_rows,
                       "ledger_points_voided": ledger_points}, audit_id=audit_id)
    if changes:
        await _record_snapshot(audit_id, "normalize_historical_points", changes)
    return {"ok": True, "applied": True, "audit_id": audit_id, **plan,
            "customers_reset": customers_reset,
            "undo_snapshot_rows": len(changes),
            "message": (f"Normalized {customers_reset:,} historic customer(s) in one pass: reset derived "
                        f"lifetime earned/redeemed to 0 and voided {ledger_rows:,} derived earn/bonus "
                        f"ledger rows ({ledger_points:,} pts). Balances untouched. Audit {audit_id}."
                        + ("" if not over_cap else
                           f" (undo covers the first {len(changes):,} of them.)"))}


async def _tool_set_points_cutoff(cutoff_date: str = "", confirm: bool = False,
                                  user=None) -> Dict[str, Any]:
    """MUTATION (Master Admin). Read or set the HISTORICAL→LIVE cutoff date (YYYY-MM-DD).
    Bills before it are historical (balance-only); on/after are live POS (points computed).
    Call with no cutoff_date to just READ the current value. To change it, pass cutoff_date
    with confirm=false to preview, then confirm=true. Audit-logged."""
    err = _require_master(user)
    if err:
        return err
    current = await _points_cutoff()
    if not cutoff_date:
        return {"action": "set_points_cutoff", "current_cutoff": current,
                "message": f"Current historical→live cutoff is {current}. Pass cutoff_date to change it."}
    import re as _re
    if not _re.match(r"^\d{4}-\d{2}-\d{2}$", cutoff_date.strip()):
        return {"error": "cutoff_date must be an ISO date like 2026-06-08."}
    cutoff_date = cutoff_date.strip()
    plan = {"action": "set_points_cutoff", "current_cutoff": current, "new_cutoff": cutoff_date}
    if not confirm:
        plan["preview"] = True
        plan["confirmation_required"] = ("Changing the cutoff changes which bills are historical vs live "
                                         "in ALL audits/reports. Confirm, then call again with confirm=true.")
        return plan
    await loyalty_config_col.update_one({"id": "default"},
                                        {"$set": {"points_cutoff_date": cutoff_date}}, upsert=True)
    audit_id = await _log_master(user, "set_points_cutoff", "loyalty_config", "default",
                                 reason=f"Set cutoff {current} -> {cutoff_date}",
                                 metadata={"from": current, "to": cutoff_date})
    return {"ok": True, "applied": True, "audit_id": audit_id, **plan,
            "message": f"Historical→live cutoff set to {cutoff_date} (was {current})."}


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
        "description": "MUTATION (Master Admin). Correct NEGATIVE points balances to their TRUE value — the "
                       "current balance PLUS points that were wrongly deducted by DUPLICATE redemption rows, "
                       "floored at 0 (never below). It does NOT blanket-reset to 0; a customer with a genuine "
                       "positive balance masked by duplicate redemptions is restored to that positive value. Pass a "
                       "single `mobile` for one customer, or omit it to fix ALL negatives (bulk). confirm=false "
                       "previews per-customer current->true balance + totals; confirm=true + reason applies in safe "
                       "batches. Writes an audited points_ledger 'adjust' row per customer (reversible).",
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
        "name": "credit_points_from_file",
        "description": "MUTATION (Master Admin). Credit a DIFFERENT number of points to EACH mobile listed in an "
                       "UPLOADED CSV/XLSX that has a mobile column AND a per-row points column (e.g. headers 'MOBILE' "
                       "and 'Points to be Credit'). Reads the exact points value from each row and adds it to that "
                       "customer's balance as BONUS points (also increments lifetime_points_earned; tier is "
                       "spend-based so it is NOT changed). USE THIS whenever the file specifies a per-mobile amount. "
                       "(If EVERY number should get the SAME amount, use apply_to_uploaded_report with grant_points "
                       "instead.) ALWAYS confirm=false first to preview (row count, total points, and a sample of "
                       "mobile->points with current balances); then after the user approves + gives a reason, "
                       "confirm=true + reason. Audit-logged, writes a ledger row per customer, and is UNDOABLE. "
                       "IDEMPOTENT: crediting the SAME file twice is BLOCKED (returns already_credited / a warning) "
                       "to prevent double-crediting; only if the user EXPLICITLY wants to credit it AGAIN, pass "
                       "force=true together with confirm=true.",
        "parameters": {"type": "object", "properties": {
            "attachment_id": {"type": "string", "description": "id of the uploaded points file (from the context block)"},
            "reason": {"type": "string"},
            "confirm": {"type": "boolean", "default": False},
            "force": {"type": "boolean", "default": False,
                      "description": "Set true (with confirm=true) ONLY to intentionally credit a file that was already credited before."},
        }}}},
    {"type": "function", "function": {
        "name": "reverse_duplicate_bonus_credits",
        "description": "REMEDIATION (Master Admin). Detect and REVERSE customers who were BONUS-credited the SAME "
                       "amount MORE THAN ONCE via Master Brain (accidental re-runs stacking points), keeping exactly "
                       "ONE credit each. Use this to CLEAN UP double/triple/quadruple crediting. It groups "
                       "master_brain bonus ledger rows by (mobile, points, reason); rows within `window_hours` of the "
                       "first are treated as duplicates. On apply it deducts the excess from balance + "
                       "lifetime_points_earned and logs a correcting adjustment per customer. ALWAYS confirm=false "
                       "first to preview the number of affected customers + total excess points; then confirm=true + "
                       "reason. Scope it with `filter_reason` (the exact credit reason to clean) and/or `since` (ISO "
                       "datetime) to be precise. Audit-logged, snapshotted, UNDOABLE.",
        "parameters": {"type": "object", "properties": {
            "filter_reason": {"type": "string", "description": "Only clean bonus rows with this exact reason (recommended for precision)."},
            "since": {"type": "string", "description": "ISO datetime; only consider credits created at/after this (defaults to last 30 days)."},
            "window_hours": {"type": "integer", "default": 72, "description": "Rows within this many hours of the first are counted as duplicates."},
            "reason": {"type": "string"},
            "confirm": {"type": "boolean", "default": False},
        }}}},
    {"type": "function", "function": {
        "name": "set_customer_tier",
        "description": "MUTATION (Master Admin). Set a SPECIFIC tier/slab value on a customer or a FILTERED set "
                       "of customers — including an arbitrary/legacy slab the spend-bands wouldn't assign (e.g. set "
                       "'kazo insider' on every customer whose lifetime purchase is 0). Use THIS (not retier_customers) "
                       "whenever the user names the exact target slab. Pass a single `mobile`, OR a filter: "
                       "`max_lifetime_spend` (lifetime_spend <= X, e.g. 0), `min_lifetime_spend` (>= X) and/or "
                       "`current_tier` (only customers currently on that tier). A bulk call REQUIRES at least one "
                       "filter (never retiers everyone). NO bonus points. confirm=false previews count + sample "
                       "old->new; confirm=true + reason applies. Audit-logged and UNDOABLE.",
        "parameters": {"type": "object", "properties": {
            "tier": {"type": "string", "description": "The exact tier/slab value to set, e.g. 'kazo insider'"},
            "mobile": {"type": "string", "description": "Optional — a single customer"},
            "max_lifetime_spend": {"type": "number", "description": "Filter: lifetime_spend <= this (e.g. 0)"},
            "min_lifetime_spend": {"type": "number", "description": "Filter: lifetime_spend >= this"},
            "current_tier": {"type": "string", "description": "Filter: only customers currently on this tier"},
            "reason": {"type": "string"},
            "confirm": {"type": "boolean", "default": False},
        }, "required": ["tier"]}}},
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
                       "| 'city' (audience_value=city) | 'cohort' (audience_value=one_timers[:months]|lapsed|dormant|inactive_90|high_value) "
                       "| 'segment' (audience_value=segment_id) | 'report' (the uploaded report's mobiles, optional attachment_id) "
                       "| 'mobiles' (explicit mobiles list). OPTIONALLY set an `objective` so the campaign gets real ROI tracking in the "
                       "Campaign Manager: 'generic' (default — anyone who shops again), 'store' (objective_params={store_codes:[...]}), "
                       "'coupon' (objective_params={coupon_codes:[...]}), 'sku' (objective_params={categories/subcategories/skus:[...]}). "
                       "`roi_window` is the attribution window (72h|3d|5d|7d|14d|30d, default 7d) and `cost` is optional spend for ROI%. "
                       "ALWAYS confirm=false first to preview the recipient count + the message + a sample; then after the user approves + gives a reason, confirm=true + reason. "
                       "Sending runs in the background; audit-logged; track ROI/delivery in the Campaigns tab; cancel via cancel_campaign.",
        "parameters": {"type": "object", "properties": {
            "message": {"type": "string", "description": "Raw SMS text (omit if using template_id)"},
            "template_id": {"type": "string", "description": "Existing SMS template id (omit if using message)"},
            "audience_type": {"type": "string", "enum": ["all", "tier", "city", "cohort", "segment", "report", "mobiles"], "default": "all"},
            "audience_value": {"type": "string", "description": "tier slug / city / cohort key / segment_id depending on audience_type"},
            "attachment_id": {"type": "string", "description": "uploaded report id when audience_type='report'"},
            "mobiles": {"type": "array", "items": {"type": "string"}, "description": "explicit mobiles when audience_type='mobiles'"},
            "objective": {"type": "string", "enum": ["generic", "store", "coupon", "sku"], "default": "generic",
                          "description": "What the campaign drives — defines the ROI breakdown"},
            "objective_params": {"type": "object", "description": "store:{store_codes:[]} · coupon:{coupon_codes:[]} · sku:{categories/subcategories/skus:[]}"},
            "roi_window": {"type": "string", "enum": ["72h", "3d", "5d", "7d", "14d", "30d"], "default": "7d"},
            "cost": {"type": "number", "description": "Optional campaign spend for ROI%"},
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
    {"type": "function", "function": {
        "name": "fix_double_redemptions",
        "description": "MUTATION (Master Admin). REPAIR customers whose points were DOUBLE-DEDUCTED by the old "
                       "redemption bug — where the bill (posAddPoint) deducted the redeemed points a SECOND time "
                       "after the OTP redemption had already deducted them. Finds the duplicate 'redeem' ledger "
                       "rows that have a confirmed prior OTP/non-OTP redemption for the SAME bill, CREDITS BACK the "
                       "wrongly-deducted points to each customer, corrects lifetime_points_redeemed, and voids the "
                       "duplicate ledger rows. Pass a single `mobile` to fix one customer (good for a test), or omit "
                       "it to fix ALL affected customers. ALWAYS call confirm=false first to PREVIEW (rows found, "
                       "customers affected, points to restore, sample); then after the user approves + gives a "
                       "reason, call again confirm=true + reason. Idempotent — already-fixed rows are skipped. "
                       "Audit-logged.",
        "parameters": {"type": "object", "properties": {
            "mobile": {"type": "string", "description": "Optional — fix one customer; omit to fix ALL affected"},
            "reason": {"type": "string"},
            "confirm": {"type": "boolean", "default": False},
        }}}},
    {"type": "function", "function": {
        "name": "fix_missing_redemption_ledger",
        "description": ("MUTATION (Master Admin). Correct LIVE (on/after the cutoff) bills that recorded "
                        "a redemption but were NEVER deducted (no redeem ledger row) — the customer kept "
                        "points they spent. Writes the missing redeem ledger row per bill AND deducts the "
                        "points from the balance (raising lifetime_points_redeemed). HISTORICAL bills are "
                        "left untouched (balance is authoritative). Run the audit_missing_redemption_ledger "
                        "first. ALWAYS confirm=false to preview (bills, customers, points to deduct), then "
                        "confirm=true + reason. Audit-logged and UNDOABLE."),
        "parameters": {"type": "object", "properties": {
            "reason": {"type": "string"},
            "confirm": {"type": "boolean", "default": False},
            "mobile": {"type": "string", "description": "Optional — scope the fix to a SINGLE customer's mobile (e.g. fix only this shopper's missing redemption). Omit to fix all live missing-redemption bills."},
        }}}},
    {"type": "function", "function": {
        "name": "repair_partial_commit_bills",
        "description": ("MUTATION (Master Admin). Heal LIVE POS bills (source=pos_ewards, on/after "
                        "the cutoff) that recorded points_earned>0 but were NEVER credited (no "
                        "`earn` ledger row) — the partial-commit bug where a DB timeout interrupted "
                        "posAddPoint after the bill was saved. Writes the missing earn ledger row "
                        "per bill AND credits the earned points to the customer's balance (raising "
                        "lifetime_points_earned), then marks the bill committed. Run "
                        "audit_partial_commit_bills first. ALWAYS confirm=false to preview (bills, "
                        "customers, points to credit), then confirm=true + reason. Idempotent, "
                        "audit-logged and UNDOABLE."),
        "parameters": {"type": "object", "properties": {
            "reason": {"type": "string"},
            "confirm": {"type": "boolean", "default": False},
        }}}},
    {"type": "function", "function": {
        "name": "reverse_duplicate_adjustments",
        "description": ("MUTATION (Master Admin). Reverse DUPLICATE point adjustments (a bulk adjust job "
                        "run twice). Groups non-voided `adjust` rows by (mobile, points, reason), KEEPS ONE "
                        "each and voids the surplus, correcting each balance by the removed amount (a "
                        "double-deduction is credited back). Run audit_duplicate_adjustments first. Scope "
                        "with filter_reason and/or since. ALWAYS confirm=false to preview, then confirm=true "
                        "+ reason. Audit-logged and UNDOABLE."),
        "parameters": {"type": "object", "properties": {
            "filter_reason": {"type": "string", "description": "Only reverse adjust rows with this exact reason."},
            "since": {"type": "string", "description": "ISO datetime; only rows created at/after this."},
            "reason": {"type": "string"},
            "confirm": {"type": "boolean", "default": False},
        }}}},
    {"type": "function", "function": {
        "name": "normalize_historical_points",
        "description": ("MUTATION (Master Admin). Enforce 'HISTORICAL = balance only'. For migrated "
                        "(source=historic_upload) customers it voids the derived historic earn/bonus ledger "
                        "rows (kept for audit, points->0) and resets lifetime_points_earned/"
                        "lifetime_points_redeemed to 0 with a historical_balance_authoritative flag — "
                        "points_balance is NEVER changed. Use this to remove points that were wrongly "
                        "computed on historical data. Run audit_historical_derived_points first. ALWAYS "
                        "confirm=false to preview, then confirm=true + reason. Audit-logged and UNDOABLE."),
        "parameters": {"type": "object", "properties": {
            "reason": {"type": "string"},
            "confirm": {"type": "boolean", "default": False},
        }}}},
    {"type": "function", "function": {
        "name": "set_points_cutoff",
        "description": ("MUTATION (Master Admin). Read or set the HISTORICAL→LIVE cutoff date (YYYY-MM-DD). "
                        "Bills before it are historical (balance-only); on/after are live POS (points "
                        "computed in real time). Call with NO cutoff_date to just read the current value. "
                        "To change it, pass cutoff_date (confirm=false previews, confirm=true applies). "
                        "Audit-logged."),
        "parameters": {"type": "object", "properties": {
            "cutoff_date": {"type": "string", "description": "ISO date e.g. 2026-06-08. Omit to read current."},
            "confirm": {"type": "boolean", "default": False},
        }}}},
    {"type": "function", "function": {
        "name": "bulk_update_customers",
        "description": ("MUTATION (Master Admin). Bulk-update one or more FIELDS on many customer documents in ONE "
                        "guarded, audited, UNDOABLE operation — this is your `db.customers.updateMany(...)`. Use it "
                        "whenever a fix needs a bulk field update (e.g. reset lifetime_points_earned / "
                        "lifetime_points_redeemed, normalise a tier casing, back-fill a flag). NEVER tell the user to "
                        "ask engineering to run updateMany — YOU run it with this tool. `filter` is a Mongo query "
                        "(REQUIRED, non-empty — refuses to touch the whole collection). `set` maps field->value; a "
                        "value may be a literal OR a field reference like \"$points_balance\" to copy another field "
                        "(field refs run as an aggregation-pipeline $set). ALWAYS confirm=false first to see the "
                        "matched count + a before/after sample, then confirm=true + reason to apply. Protected fields "
                        "_id/id/mobile cannot be changed. Audit-logged and undoable via undo_action."),
        "parameters": {"type": "object", "properties": {
            "filter": {"type": "object", "description": "Mongo query selecting which customers to update (required, non-empty). E.g. {\"source\":\"historic_upload\",\"points_balance\":{\"$gte\":0}}"},
            "set": {"type": "object", "description": "Fields to set. Value = literal or \"$otherField\" reference. E.g. {\"lifetime_points_earned\":\"$points_balance\",\"lifetime_points_redeemed\":0}"},
            "reason": {"type": "string", "description": "Audit reason (required to apply)."},
            "confirm": {"type": "boolean", "default": False, "description": "false = preview; true = apply."}},
         "required": ["filter", "set"]}}},
]

MASTER_TOOL_HANDLERS = {
    "audit_double_redemptions": _tool_audit_double_redemptions,
    "audit_negative_balances": _tool_audit_negative_balances,
    "audit_missing_redemption_ledger": _tool_audit_missing_redemption_ledger,
    "audit_duplicate_adjustments": _tool_audit_duplicate_adjustments,
    "audit_historical_derived_points": _tool_audit_historical_derived_points,
    "audit_partial_commit_bills": _tool_audit_partial_commit_bills,
    "grant_bonus_points": _tool_grant_bonus_points,
    "adjust_points": _tool_adjust_points,
    "fix_negative_balances": _tool_fix_negative_balances,
    "reverse_tier_upgrade_bonus": _tool_reverse_tier_upgrade_bonus,
    "retier_customers": _tool_retier_customers,
    "set_customer_tier": _tool_set_customer_tier,
    "master_action_log": _tool_master_action_log,
    "apply_to_uploaded_report": _tool_apply_to_uploaded_report,
    "credit_points_from_file": _tool_credit_points_from_file,
    "reverse_duplicate_bonus_credits": _tool_reverse_duplicate_bonus_credits,
    "reverse_duplicate_adjustments": _tool_reverse_duplicate_adjustments,
    "fix_missing_redemption_ledger": _tool_fix_missing_redemption_ledger,
    "normalize_historical_points": _tool_normalize_historical_points,
    "repair_partial_commit_bills": _tool_repair_partial_commit_bills,
    "set_points_cutoff": _tool_set_points_cutoff,
    "bulk_update_customers": _tool_bulk_update_customers,
    "undo_action": _tool_undo_action,
    "send_campaign": _tool_send_campaign,
    "list_campaigns": _tool_list_campaigns,
    "cancel_campaign": _tool_cancel_campaign,
    "fix_double_redemptions": _tool_fix_double_redemptions,
}

# READ-ONLY Master tools — safe to expose on analysis/read questions (no mutation). Kept
# separate from the action schemas so the read path can include them without unlocking writes.
MASTER_READ_TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {"type": "function", "function": {
        "name": "audit_negative_balances",
        "description": ("FAST, read-only audit of customers with a NEGATIVE loyalty points balance. "
                        "Returns the authoritative indexed count + total deficit from "
                        "customers.points_balance, the worst cases, and a best-effort ledger-sum "
                        "cross-check. ALWAYS use this for any 'how many / which customers have "
                        "negative balance and why' question — do NOT group the whole ledger yourself."),
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "audit_double_redemptions",
        "description": ("FAST, read-only audit of double/duplicate point redemptions (the POS "
                        "double-deduction bug). Returns how many ledger rows and customers are "
                        "affected and the total points double-deducted. ALWAYS use this for any "
                        "'duplicate-redemption audit / how many are affected' question — do NOT "
                        "write your own ledger aggregations for this. Optional `mobile` scopes to "
                        "one customer."),
        "parameters": {"type": "object", "properties": {
            "mobile": {"type": "string", "description": "Optional 10-digit mobile to scope the audit."}
        }}}},
    {"type": "function", "function": {
        "name": "audit_missing_redemption_ledger",
        "description": ("EXACT, read-only audit of bills that recorded a redemption "
                        "(points_redeemed>0) but have NO matching `redeem` row in the points "
                        "ledger. Splits the result into HISTORICAL (before the cutoff — an "
                        "audit-trail gap only, balance is authoritative) vs LIVE (on/after the "
                        "cutoff — a real over-balance if the bill never went through the OTP "
                        "redeem flow). ALWAYS use this for any 'missing redemption ledger / "
                        "redemptions without a ledger entry' question. Returns exact bill and "
                        "point counts and the cutoff date used."),
        "parameters": {"type": "object", "properties": {
            "sample_limit": {"type": "integer", "default": 15, "description": "How many example bills to include."}
        }}}},
    {"type": "function", "function": {
        "name": "audit_duplicate_adjustments",
        "description": ("EXACT, read-only audit of DUPLICATE point adjustments — the fingerprint "
                        "of a bulk adjust job run twice. Groups non-voided `adjust` ledger rows by "
                        "(mobile, points, reason); any group with count>1 has surplus rows. "
                        "Returns surplus rows, customers affected, net surplus points and the "
                        "points wrongly deducted twice. ALWAYS use this for any 'duplicate "
                        "adjustment / adjust entries done twice' question. Optional filter_reason "
                        "and since (ISO datetime) narrow the scope."),
        "parameters": {"type": "object", "properties": {
            "filter_reason": {"type": "string", "description": "Only consider adjust rows with this exact reason."},
            "since": {"type": "string", "description": "ISO datetime; only rows created at/after this."}
        }}}},
    {"type": "function", "function": {
        "name": "audit_historical_derived_points",
        "description": ("EXACT, read-only audit of COMPUTED/DERIVED points on HISTORICAL data "
                        "(source=historic_upload). Per the canonical rule, historical customers "
                        "keep ONLY their migrated points_balance — no earned/redeemed figures "
                        "should be derived from spend. Returns how many historic customers have a "
                        "derived lifetime_points_earned>0 (and the total), plus the non-voided "
                        "historic earn/bonus ledger rows and points — i.e. exactly what would be "
                        "removed to leave points_balance as the sole historical truth. Use this "
                        "for any 'historical points computed from lifetime spend / derived points "
                        "to remove' question."),
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "audit_partial_commit_bills",
        "description": ("EXACT, read-only audit of PARTIALLY-COMMITTED live POS bills — bills "
                        "(source=pos_ewards, on/after the cutoff) that recorded points_earned>0 "
                        "but have NO non-voided `earn` ledger row, meaning a DB timeout "
                        "interrupted posAddPoint after the bill was saved and the earned points "
                        "were never credited to the balance or ledger. Returns how many bills, "
                        "customers and points were never credited (and how many are still marked "
                        "pending). ALWAYS use this for any 'points earned on a bill but missing "
                        "from the balance/ledger / partial commit / bill saved but no points' "
                        "question. Run repair_partial_commit_bills to heal them."),
        "parameters": {"type": "object", "properties": {
            "sample_limit": {"type": "integer", "default": 15, "description": "How many example bills to include."}
        }}}},
]
