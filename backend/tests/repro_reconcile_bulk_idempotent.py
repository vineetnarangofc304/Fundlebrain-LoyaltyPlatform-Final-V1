"""Idempotency / concurrency test for the BATCH ledger reconciler apply phase.

Reproduces the user's bug: the apply times out at the gateway, they click "apply" again,
and the mutation runs 2-3x -> balances/ledger get double-stamped. This fires the apply
endpoint MULTIPLE TIMES CONCURRENTLY and asserts exactly ONE correction per customer
(balance == genuine target, exactly one compensating master_brain adjust row), plus that
a later re-run is a clean no-op.
"""
import asyncio
import os
import uuid
import httpx
from datetime import datetime, timezone, timedelta

from database import customers_col, points_ledger_col, audit_logs_col, mb_action_snapshots_col

API = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip()
MOBILES = ["9997770001", "9997770002", "9997770003"]


def _iso(m):
    return (datetime.now(timezone.utc) - timedelta(minutes=m)).isoformat()


async def seed():
    await customers_col.delete_many({"mobile": {"$in": MOBILES}})
    await points_ledger_col.delete_many({"customer_mobile": {"$in": MOBILES}})
    for mob in MOBILES:
        cid = str(uuid.uuid4())
        await customers_col.insert_one({"id": cid, "mobile": mob, "name": f"IDEMPO {mob[-4:]}",
                                        "points_balance": 875, "lifetime_points_earned": 1250})
        rows = [{"type": "opening", "points": 125, "reference_type": "migration",
                 "reason": "Opening balance", "created_at": _iso(600)}]
        for i in range(3):
            rows.append({"type": "bonus", "points": 375, "reference_type": "bulk_bonus",
                         "reason": "Top up campaign", "created_at": _iso(120 - i)})
        for i in range(3):
            rows.append({"type": "adjust", "points": -750, "reference_type": "master_brain",
                         "reason": "Reversal of 2 duplicates", "created_at": _iso(30 - i)})
        for r in rows:
            r.update({"id": str(uuid.uuid4()), "customer_mobile": mob, "customer_id": cid, "kind": r["type"]})
        await points_ledger_col.insert_many(rows)


async def cleanup():
    await customers_col.delete_many({"mobile": {"$in": MOBILES}})
    await points_ledger_col.delete_many({"customer_mobile": {"$in": MOBILES}})


async def _new_recon_rows():
    """Compensating master_brain adjust rows written by THIS reconciler (have fix_audit_id)."""
    out = {}
    for mob in MOBILES:
        n = await points_ledger_col.count_documents(
            {"customer_mobile": mob, "reference_type": "master_brain",
             "fix_audit_id": {"$exists": True}})
        out[mob] = n
    return out


async def main():
    await seed()
    async with httpx.AsyncClient(base_url=API, timeout=90) as c:
        r = await c.post("/api/auth/login", json={"email": "masteradmin@fundle.io", "password": "Master@2026"})
        tok = r.json().get("token") or r.json().get("access_token")
        H = {"Authorization": f"Bearer {tok}"}
        body = {"mobiles": MOBILES, "strategy": "genuine", "reason": "idempotency concurrency test"}

        # Fire the APPLY 3x CONCURRENTLY (simulates the timeout-retry storm)
        resps = await asyncio.gather(*[
            c.post("/api/points-integrity/reconcile-ledger/bulk/apply", headers=H, json=body)
            for _ in range(3)
        ])
        changed_counts = [rp.json().get("changed", 0) for rp in resps]
        print("CONCURRENT APPLY changed counts:", changed_counts)
        # Exactly ONE run should have changed all 3; the others must be no-ops (0).
        assert sum(changed_counts) == 3, f"expected total 3 changes across concurrent runs, got {changed_counts}"

        # Balances must be EXACTLY 500 (genuine), never double-applied below.
        for mob in MOBILES:
            cu = await customers_col.find_one({"mobile": mob})
            assert int(cu["points_balance"]) == 500, (mob, cu["points_balance"])
        print("  [OK] all balances == 500 after 3 concurrent applies (no double-apply)")

        # Exactly ONE compensating adjust row per customer (not 2 or 3).
        counts = await _new_recon_rows()
        print("  compensating rows per customer:", counts)
        assert all(v == 1 for v in counts.values()), f"expected exactly 1 reversal row each, got {counts}"
        print("  [OK] exactly one compensating ledger row per customer")

        # A fresh sequential re-run must be a clean no-op (already at genuine).
        again = (await c.post("/api/points-integrity/reconcile-ledger/bulk/apply",
                              headers=H, json=body)).json()
        print("  RE-RUN:", {k: again.get(k) for k in ["applied", "changed", "message"]})
        assert again.get("changed", 0) == 0 and again.get("applied") is False, again
        counts2 = await _new_recon_rows()
        assert all(v == 1 for v in counts2.values()), f"re-run created extra rows: {counts2}"
        print("  [OK] re-run is a no-op, no extra rows")

    await cleanup()
    print("\nBATCH RECONCILER IDEMPOTENCY/CONCURRENCY TEST PASSED")


if __name__ == "__main__":
    asyncio.run(main())
