"""Points Integrity — deterministic, LLM-free endpoints powering the ops "Points Integrity
Center" UI. Thin wrappers over the audited/undoable Master-Brain repair tools so admins can
Scan → Reverse each class of points error with a button (no chat required):

  * Issue A — duplicate bonus credits          -> /master-brain/reverse-duplicate-credits/* (existing)
  * Issue B — wrong tier-upgrade migration bonus -> /points-integrity/tier-upgrade-bonus/*
  * Issue C — auto-calculated historic earn      -> /points-integrity/historic-earn/*
  * Issue D — double redemption / negative bal   -> /points-integrity/negative-balances/* + repair-runs undo
  * Issue E — re-tier legacy customers           -> /loyalty/retier/* (existing)
  * Issue F — reconcile a balance from the ledger -> /points-integrity/reconcile-ledger/* (+ /bulk/*)
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from database import audit_logs_col
from routes.master_brain_routes import require_master_admin
from routes.master_brain_tools import (
    _tool_reverse_tier_upgrade_bonus, _tool_normalize_historical_points,
    _tool_fix_negative_balances, _tool_undo_action, _tool_reconcile_ledger_balance,
    _tool_reconcile_ledger_bulk,
)

router = APIRouter(prefix="/points-integrity", tags=["points-integrity"])


# ── Issue B: wrong tier-upgrade migration bonus ────────────────────────────────
class TierBonusIn(BaseModel):
    start: str = ""
    end: str = ""
    migrated_only: bool = True
    mobile: str = ""
    reason: str = ""


@router.post("/tier-upgrade-bonus/preview")
async def tier_bonus_preview(body: TierBonusIn, user: dict = Depends(require_master_admin)):
    res = await _tool_reverse_tier_upgrade_bonus(
        start=body.start.strip(), end=body.end.strip(), migrated_only=body.migrated_only,
        mobile=body.mobile.strip(), confirm=False, user=user)
    if res.get("error"):
        raise HTTPException(400, res["error"])
    return res


@router.post("/tier-upgrade-bonus/apply")
async def tier_bonus_apply(body: TierBonusIn, user: dict = Depends(require_master_admin)):
    if not body.reason.strip():
        raise HTTPException(400, "A reason is required to reverse tier-upgrade bonuses.")
    res = await _tool_reverse_tier_upgrade_bonus(
        start=body.start.strip(), end=body.end.strip(), migrated_only=body.migrated_only,
        mobile=body.mobile.strip(), reason=body.reason.strip(), confirm=True, user=user)
    if res.get("error"):
        raise HTTPException(400, res["error"])
    return res


# ── Issue C: auto-calculated historic earn (balance-only rule) ─────────────────
class HistoricEarnIn(BaseModel):
    reason: str = ""


@router.post("/historic-earn/preview")
async def historic_earn_preview(body: HistoricEarnIn, user: dict = Depends(require_master_admin)):
    res = await _tool_normalize_historical_points(confirm=False, user=user)
    if res.get("error"):
        raise HTTPException(400, res["error"])
    return res


@router.post("/historic-earn/apply")
async def historic_earn_apply(body: HistoricEarnIn, user: dict = Depends(require_master_admin)):
    if not body.reason.strip():
        raise HTTPException(400, "A reason is required to normalize historic points.")
    res = await _tool_normalize_historical_points(reason=body.reason.strip(), confirm=True, user=user)
    if res.get("error"):
        raise HTTPException(400, res["error"])
    return res


# ── Issue D: negative balances ─────────────────────────────────────────────────
class NegBalIn(BaseModel):
    mobile: str = ""
    reason: str = ""


@router.post("/negative-balances/preview")
async def neg_bal_preview(body: NegBalIn, user: dict = Depends(require_master_admin)):
    res = await _tool_fix_negative_balances(mobile=(body.mobile.strip() or None), confirm=False, user=user)
    if res.get("error"):
        raise HTTPException(400, res["error"])
    return res


@router.post("/negative-balances/apply")
async def neg_bal_apply(body: NegBalIn, user: dict = Depends(require_master_admin)):
    if not body.reason.strip():
        raise HTTPException(400, "A reason is required to correct negative balances.")
    res = await _tool_fix_negative_balances(
        mobile=(body.mobile.strip() or None), reason=body.reason.strip(), confirm=True, user=user)
    if res.get("error"):
        raise HTTPException(400, res["error"])
    return res


# ── Issue F: ledger reconciliation (deterministic, bypasses the broken action log) ──
class ReconcileIn(BaseModel):
    mobile: str = ""
    strategy: str = "genuine"
    target_balance: Optional[int] = None
    window_hours: int = 72
    reason: str = ""


@router.post("/reconcile-ledger/preview")
async def reconcile_preview(body: ReconcileIn, user: dict = Depends(require_master_admin)):
    res = await _tool_reconcile_ledger_balance(
        mobile=body.mobile.strip(), strategy=body.strategy, target_balance=body.target_balance,
        window_hours=body.window_hours, confirm=False, user=user)
    if res.get("error"):
        raise HTTPException(400, res["error"])
    return res


@router.post("/reconcile-ledger/apply")
async def reconcile_apply(body: ReconcileIn, user: dict = Depends(require_master_admin)):
    if not body.reason.strip():
        raise HTTPException(400, "A reason is required to reconcile a balance.")
    res = await _tool_reconcile_ledger_balance(
        mobile=body.mobile.strip(), strategy=body.strategy, target_balance=body.target_balance,
        window_hours=body.window_hours, reason=body.reason.strip(), confirm=True, user=user)
    if res.get("error"):
        raise HTTPException(400, res["error"])
    return res


class ReconcileBulkIn(BaseModel):
    mobiles: list[str] = []
    strategy: str = "genuine"
    fixed_value: Optional[int] = None
    only_raise: bool = False
    window_hours: int = 72
    reason: str = ""


@router.post("/reconcile-ledger/bulk/preview")
async def reconcile_bulk_preview(body: ReconcileBulkIn, user: dict = Depends(require_master_admin)):
    res = await _tool_reconcile_ledger_bulk(
        mobiles=body.mobiles, strategy=body.strategy, fixed_value=body.fixed_value,
        only_raise=body.only_raise, window_hours=body.window_hours, confirm=False, user=user)
    if res.get("error"):
        raise HTTPException(400, res["error"])
    return res


@router.post("/reconcile-ledger/bulk/apply")
async def reconcile_bulk_apply(body: ReconcileBulkIn, user: dict = Depends(require_master_admin)):
    if not body.reason.strip():
        raise HTTPException(400, "A reason is required to reconcile balances.")
    res = await _tool_reconcile_ledger_bulk(
        mobiles=body.mobiles, strategy=body.strategy, fixed_value=body.fixed_value,
        only_raise=body.only_raise, window_hours=body.window_hours,
        reason=body.reason.strip(), confirm=True, user=user)
    if res.get("error"):
        raise HTTPException(400, res["error"])
    return res


# ── Recent repair runs + one-click undo (for reversing the bad redemption backfill) ──
_UNDOABLE_ACTIONS = [
    "master_brain.fix_missing_redemption_ledger", "master_brain.reverse_tier_upgrade_bonus",
    "master_brain.normalize_historical_points", "master_brain.reverse_duplicate_bonus_credits",
    "master_brain.reverse_duplicate_adjustments", "master_brain.fix_negative_balances_bulk",
    "master_brain.fix_negative_balance", "master_brain.backfill_ledger_mobiles",
    "master_brain.reconcile_ledger_balance", "master_brain.reconcile_ledger_bulk",
]


@router.get("/repair-runs")
async def repair_runs(limit: int = 40, user: dict = Depends(require_master_admin)):
    """Recent audited repair actions (most recent first) so an admin can UNDO a run — e.g.
    reverse the redemption-repair backfill that created the duplicate deductions."""
    q = {"source": "master_brain", "action": {"$in": _UNDOABLE_ACTIONS}}
    rows = await audit_logs_col.find(
        q, {"_id": 0, "id": 1, "action": 1, "reason": 1, "timestamp": 1,
            "user_email": 1, "metadata": 1, "undone": 1}
    ).sort("timestamp", -1).limit(min(limit, 100)).to_list(min(limit, 100))
    for r in rows:
        r["action"] = (r.get("action") or "").replace("master_brain.", "")
        r["created_at"] = r.get("timestamp")
    return {"runs": rows, "count": len(rows)}


class UndoIn(BaseModel):
    reason: str = ""


@router.post("/undo/{audit_id}")
async def undo_run(audit_id: str, body: UndoIn, user: dict = Depends(require_master_admin)):
    if not body.reason.strip():
        raise HTTPException(400, "A reason is required to undo a repair run.")
    res = await _tool_undo_action(audit_id=audit_id, reason=body.reason.strip(), confirm=True, user=user)
    if res.get("error"):
        raise HTTPException(400, res["error"])
    return res
