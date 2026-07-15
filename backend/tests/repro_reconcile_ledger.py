"""Repro/verify the ledger reconciler (_tool_reconcile_ledger_balance).

Seeds a LAXMI-style corruption: opening 125, a top-up +375 run 3x, then a botched flat
reversal -750 run 3x, with a divergent stored balance (875). Verifies the candidate math,
apply (genuine -> 500), and undo restores exactly.
"""
import asyncio
import uuid
from datetime import datetime, timezone, timedelta

from database import customers_col, points_ledger_col, audit_logs_col, mb_action_snapshots_col
from routes.master_brain_tools import _tool_reconcile_ledger_balance, _tool_undo_action

MOBILE = "9998887770"
USER = {"id": "test-master", "email": "test@fundle.io", "name": "Test", "is_master_admin": True}


def _iso(mins_ago):
    return (datetime.now(timezone.utc) - timedelta(minutes=mins_ago)).isoformat()


async def _cleanup():
    await customers_col.delete_many({"mobile": MOBILE})
    await points_ledger_col.delete_many({"customer_mobile": MOBILE})


async def _seed():
    await _cleanup()
    cid = str(uuid.uuid4())
    await customers_col.insert_one({
        "id": cid, "mobile": MOBILE, "name": "TEST LAXMI",
        "points_balance": 875, "lifetime_points_earned": 1250,
    })
    rows = []
    rows.append({"type": "opening", "points": 125, "reference_type": "migration",
                 "reason": "Opening balance", "created_at": _iso(600)})
    for i in range(3):
        rows.append({"type": "bonus", "points": 375, "reference_type": "bulk_bonus",
                     "reason": "Top up campaign", "created_at": _iso(120 - i)})
    for i in range(3):
        rows.append({"type": "adjust", "points": -750, "reference_type": "master_brain",
                     "reason": "Reversal of 2 duplicates", "created_at": _iso(30 - i)})
    for r in rows:
        r.update({"id": str(uuid.uuid4()), "customer_mobile": MOBILE, "customer_id": cid,
                  "kind": r["type"], "created_by": "seed"})
    await points_ledger_col.insert_many(rows)
    return cid


async def main():
    cid = await _seed()
    ok = True

    # 1) Preview (genuine)
    pv = await _tool_reconcile_ledger_balance(mobile=MOBILE, strategy="genuine", confirm=False, user=USER)
    print("PREVIEW:", {k: pv.get(k) for k in
          ["current_balance", "raw_ledger_sum", "dedup_ledger_sum", "genuine_ledger_sum",
           "target_balance", "delta", "ledger_rows", "mb_adjust_rows"]})
    assert pv["current_balance"] == 875, pv
    assert pv["raw_ledger_sum"] == -1000, pv
    assert pv["dedup_ledger_sum"] == -250, pv
    assert pv["genuine_ledger_sum"] == 500, pv
    assert pv["target_balance"] == 500 and pv["delta"] == -375, pv
    assert pv["mb_adjust_rows"] == 3, pv
    assert len(pv.get("ledger") or []) == 7, pv
    print("  [OK] candidate math correct (genuine=500)")

    # 2) Apply reconcile to 500
    ap = await _tool_reconcile_ledger_balance(mobile=MOBILE, strategy="genuine",
                                              reason="fix botched topup reversal", confirm=True, user=USER)
    assert ap.get("applied") and ap.get("audit_id"), ap
    audit_id = ap["audit_id"]
    c = await customers_col.find_one({"id": cid})
    assert int(c["points_balance"]) == 500, c["points_balance"]
    comp = await points_ledger_col.find_one({"fix_audit_id": audit_id})
    assert comp and int(comp["points"]) == -375, comp
    print(f"  [OK] applied: balance 875 -> {c['points_balance']}, compensating row {comp['points']}")

    # 3) Idempotent re-run (genuine now == current 500 -> delta 0)
    pv2 = await _tool_reconcile_ledger_balance(mobile=MOBILE, strategy="genuine", confirm=False, user=USER)
    assert pv2["current_balance"] == 500 and pv2["genuine_ledger_sum"] == 500 and pv2["delta"] == 0, pv2
    print("  [OK] idempotent: second genuine scan shows delta 0")

    # 4) Undo -> restore 875
    ud = await _tool_undo_action(audit_id=audit_id, reason="revert test", confirm=True, user=USER)
    assert ud.get("applied"), ud
    c2 = await customers_col.find_one({"id": cid})
    assert int(c2["points_balance"]) == 875, c2["points_balance"]
    comp2 = await points_ledger_col.find_one({"fix_audit_id": audit_id})
    assert comp2.get("voided") is True, comp2
    print(f"  [OK] undo restored balance to {c2['points_balance']}, compensating row voided")

    # 5) dedup + explicit target override (re-seed for a clean 7-row ledger)
    await _seed()
    pv3 = await _tool_reconcile_ledger_balance(mobile=MOBILE, strategy="dedup", confirm=False, user=USER)
    assert pv3["dedup_ledger_sum"] == -250 and pv3["target_balance"] == 0 and pv3["floored_to_zero"], pv3
    ap3 = await _tool_reconcile_ledger_balance(mobile=MOBILE, target_balance=600,
                                               reason="manual override", confirm=True, user=USER)
    c3 = await customers_col.find_one({"id": MOBILE and (await customers_col.find_one({"mobile": MOBILE}))["id"]})
    assert int(c3["points_balance"]) == 600, c3["points_balance"]
    print("  [OK] dedup candidate=-250; explicit target override -> 600")

    await audit_logs_col.delete_many({"metadata.mobile": MOBILE})
    await mb_action_snapshots_col.delete_many({"audit_id": audit_id})
    await _cleanup()
    print("\nALL RECONCILER TESTS PASSED" if ok else "FAILED")


if __name__ == "__main__":
    asyncio.run(main())
