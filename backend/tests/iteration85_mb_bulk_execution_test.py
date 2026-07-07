"""Iteration 85 — Master Brain reliable bulk execution (no partial/fabricated results).

Root cause fixed: bulk mutation tools fetched docs + updated per-batch and, in the LLM
streaming path, were capped at the 90s read deadline → half-applied at scale → the model then
fabricated "1,200 / 6,169" batch progress. Fix: mutations now (a) run as a SINGLE server-side
update_many that completes the whole matched set in one call and returns the REAL count, and
(b) get the full 600s DB budget in the streaming loop.

Validates normalize_historical_points + bulk_update_customers reset the ENTIRE seeded set in
one call, report the real modified count, and are undoable.

Run:  cd /app/backend && python tests/iteration85_mb_bulk_execution_test.py
"""
import sys
import uuid
import asyncio

sys.path.insert(0, "/app/backend")

from database import customers_col, points_ledger_col, audit_logs_col  # noqa: E402
from routes.master_brain_tools import (  # noqa: E402
    _now_iso, _tool_normalize_historical_points, _tool_bulk_update_customers,
    _tool_undo_action)

MASTER = {"is_master_admin": True, "email": "iter85@fundle.io", "id": "iter85"}
TAG = "iter85_" + uuid.uuid4().hex[:8]
N = 120
results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {extra}" if extra else ""))


async def run():
    # --- seed N historic_upload customers with phantom derived lifetime points + ledger rows ---
    docs, ledger = [], []
    for i in range(N):
        cid = uuid.uuid4().hex
        mob = f"8{TAG[-6:]}{i:04d}"[:12]
        docs.append({"id": cid, "mobile": mob, "name": f"Hist {i}", "source": "historic_upload",
                     "_iter85": TAG, "tier": "gold", "points_balance": 2759,
                     "lifetime_points_earned": 2510, "lifetime_points_redeemed": 500,
                     "created_at": _now_iso()})
        ledger.append({"id": uuid.uuid4().hex, "customer_id": cid, "customer_mobile": mob,
                       "source": "historic_upload", "type": "earn", "points": 2510,
                       "_iter85": TAG, "created_at": _now_iso()})
    await customers_col.insert_many(docs)
    await points_ledger_col.insert_many(ledger)

    # --- preview ---
    prev = await _tool_normalize_historical_points(reason="", confirm=False, user=MASTER)
    check("N1 preview flagged", prev.get("preview") is True
          and prev.get("historic_customers_to_reset", 0) >= N,
          f"to_reset={prev.get('historic_customers_to_reset')}")

    # --- apply (single update_many, whole set in one call) ---
    applied = await _tool_normalize_historical_points(
        reason="iter85 enforce historic balance-only", confirm=True, user=MASTER)
    check("N2 applied", applied.get("applied") is True, str(applied.get("message")))
    audit_id = applied.get("audit_id")

    # Every one of OUR seeded customers must be reset (balance untouched).
    remaining = await customers_col.count_documents(
        {"_iter85": TAG, "$or": [{"lifetime_points_earned": {"$gt": 0}},
                                 {"lifetime_points_redeemed": {"$gt": 0}}]})
    reset_ok = await customers_col.count_documents(
        {"_iter85": TAG, "lifetime_points_earned": 0, "lifetime_points_redeemed": 0,
         "historical_balance_authoritative": True, "points_balance": 2759})
    check("N3 ALL seeded reset in one call (0 remaining)", remaining == 0, f"remaining={remaining}")
    check("N4 balances untouched + flagged", reset_ok == N, f"reset_ok={reset_ok}/{N}")
    check("N5 real count returned (>=N)", int(applied.get("customers_reset") or 0) >= N,
          f"customers_reset={applied.get('customers_reset')}")
    voided = await points_ledger_col.count_documents(
        {"_iter85": TAG, "voided": True, "points": 0})
    check("N6 derived ledger rows voided", voided == N, f"voided={voided}/{N}")

    # --- undo restores the derived lifetime values ---
    udone = await _tool_undo_action(audit_id=audit_id, reason="iter85 undo", confirm=True, user=MASTER)
    check("N7 undo applied", udone.get("applied") is True, str(udone.get("message")))
    restored = await customers_col.count_documents(
        {"_iter85": TAG, "lifetime_points_earned": 2510, "lifetime_points_redeemed": 500})
    check("N8 lifetime values restored by undo", restored == N, f"restored={restored}/{N}")

    # --- bulk_update_customers single update_many on our tagged set ---
    bprev = await _tool_bulk_update_customers(
        filter={"_iter85": TAG}, set={"tier": "silver"}, reason="", confirm=False, user=MASTER)
    check("B1 bulk preview matched", bprev.get("preview") is True and bprev.get("matched") == N,
          f"matched={bprev.get('matched')}")
    bdone = await _tool_bulk_update_customers(
        filter={"_iter85": TAG}, set={"tier": "silver"}, reason="iter85 bulk", confirm=True, user=MASTER)
    check("B2 bulk applied all in one call", bdone.get("applied") is True
          and int(bdone.get("modified") or 0) == N, f"modified={bdone.get('modified')}")
    silver = await customers_col.count_documents({"_iter85": TAG, "tier": "silver"})
    check("B3 all rows updated", silver == N, f"silver={silver}/{N}")

    # --- cleanup ---
    await customers_col.delete_many({"_iter85": TAG})
    await points_ledger_col.delete_many({"_iter85": TAG})
    for aid in [audit_id, bdone.get("audit_id")]:
        if aid:
            await audit_logs_col.delete_many({"id": aid})


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(run())
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"\n==== {passed}/{total} checks passed ====")
    sys.exit(0 if passed == total else 1)
