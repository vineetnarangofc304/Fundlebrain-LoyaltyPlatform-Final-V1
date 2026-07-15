"""E2E test of the BATCH ledger reconciler over real HTTP (masteradmin)."""
import asyncio
import os
import uuid
import httpx
from datetime import datetime, timezone, timedelta

from database import customers_col, points_ledger_col, audit_logs_col, mb_action_snapshots_col

API = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2").read().strip()
MOBILES = ["9998880001", "9998880002", "9998880003"]


def _iso(m):
    return (datetime.now(timezone.utc) - timedelta(minutes=m)).isoformat()


async def seed():
    await customers_col.delete_many({"mobile": {"$in": MOBILES}})
    await points_ledger_col.delete_many({"customer_mobile": {"$in": MOBILES}})
    for mob in MOBILES:
        cid = str(uuid.uuid4())
        await customers_col.insert_one({"id": cid, "mobile": mob, "name": f"BATCH {mob[-4:]}",
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


async def cleanup(audit_id=None):
    await customers_col.delete_many({"mobile": {"$in": MOBILES}})
    await points_ledger_col.delete_many({"customer_mobile": {"$in": MOBILES}})
    if audit_id:
        await audit_logs_col.delete_many({"id": audit_id})
        await mb_action_snapshots_col.delete_many({"audit_id": audit_id})


async def main():
    await seed()
    async with httpx.AsyncClient(base_url=API, timeout=60) as c:
        r = await c.post("/api/auth/login", json={"email": "masteradmin@fundle.io", "password": "Master@2026"})
        tok = r.json().get("token") or r.json().get("access_token")
        H = {"Authorization": f"Bearer {tok}"}

        # Preview
        pv = (await c.post("/api/points-integrity/reconcile-ledger/bulk/preview",
                           headers=H, json={"mobiles": MOBILES + ["0000000009"], "strategy": "genuine"})).json()
        print("PREVIEW:", {k: pv.get(k) for k in ["matched", "not_found", "to_change", "total_delta"]})
        assert pv["matched"] == 3 and pv["not_found"] == 1 and pv["to_change"] == 3, pv
        assert pv["total_delta"] == 3 * (500 - 875), pv  # each 875 -> 500 = -375
        assert all(row["target_balance"] == 500 and row["genuine_ledger_sum"] == 500 for row in pv["sample"]), pv["sample"]
        print("  [OK] preview: 3 matched -> target 500 each, 1 not found")

        # Apply
        ap = (await c.post("/api/points-integrity/reconcile-ledger/bulk/apply",
                           headers=H, json={"mobiles": MOBILES, "strategy": "genuine",
                                            "reason": "batch fix botched topup reversal"})).json()
        print("APPLY:", {k: ap.get(k) for k in ["applied", "changed", "total_delta", "audit_id"]})
        audit_id = ap["audit_id"]
        assert ap["applied"] and ap["changed"] == 3, ap
        for mob in MOBILES:
            cu = await customers_col.find_one({"mobile": mob})
            assert int(cu["points_balance"]) == 500, (mob, cu["points_balance"])
        print("  [OK] applied: all 3 balances 875 -> 500")

        # Undo via repair-runs undo endpoint
        ud = (await c.post(f"/api/points-integrity/undo/{audit_id}",
                           headers=H, json={"reason": "revert batch test"})).json()
        print("UNDO:", {k: ud.get(k) for k in ["applied", "message"]})
        assert ud.get("applied"), ud
        for mob in MOBILES:
            cu = await customers_col.find_one({"mobile": mob})
            assert int(cu["points_balance"]) == 875, (mob, cu["points_balance"])
        print("  [OK] undo restored all 3 balances to 875")

    await cleanup(audit_id)
    print("\nBATCH RECONCILER E2E PASSED")


if __name__ == "__main__":
    asyncio.run(main())
