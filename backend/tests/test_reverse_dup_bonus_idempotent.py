"""
Pytest for reverse_duplicate_bonus_credits idempotency + undo (customer 9303632456 regression).
Invokes the REAL production handler (routes.master_brain_tools) against MongoDB.
Seeds throwaway customers (mobiles 9700000101 / 9700000102 / 9700000103) then cleans up.
"""
import os
import sys
import uuid
import asyncio
from datetime import datetime, timezone, timedelta

import pytest
from dotenv import load_dotenv

# Ensure backend on path (repo test conftest may not be in scope)
sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from routes.master_brain_tools import (  # noqa: E402
    _tool_reverse_duplicate_bonus_credits as REV,
    _tool_undo_action as UNDO,
)

NOW = datetime.now(timezone.utc)
MOBS = ("9700000101", "9700000102", "9700000103")


def _iso(dt):
    return dt.isoformat()


@pytest.fixture(scope="module")
def loop():
    lp = asyncio.new_event_loop()
    yield lp
    lp.close()


@pytest.fixture(scope="module")
def db(loop):
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    yield client[os.environ["DB_NAME"]]
    client.close()


@pytest.fixture(scope="module")
def user(loop, db):
    async def _get():
        u = await db.users.find_one({"email": "masteradmin@fundle.io"}, {"_id": 0})
        assert u, "masteradmin@fundle.io not found — seed required"
        return {"id": u.get("id"), "email": u.get("email"),
                "role": u.get("role"), "is_master_admin": True}
    return loop.run_until_complete(_get())


async def _seed(db, mob, n_bonus, prior_reversals=0, reason="TEST_Top-up campaign"):
    await db.customers.delete_many({"mobile": mob})
    await db.points_ledger.delete_many({"customer_mobile": mob})
    cid = uuid.uuid4().hex
    bonus_total = 375 * n_bonus
    bal_now = 125 + bonus_total - prior_reversals * 750
    await db.customers.insert_one({
        "id": cid, "mobile": mob, "name": "TEST_DupBonus",
        "points_balance": bal_now,
        "lifetime_points_earned": 125 + bonus_total,
        "lifetime_points_redeemed": 0, "tier": "silver",
        "created_at": _iso(NOW),
    })
    rows = [{"id": uuid.uuid4().hex, "customer_mobile": mob, "customer_id": cid,
             "points": 125, "type": "bonus", "reference_type": "master_brain",
             "reason": "TEST_Opening",
             "created_at": _iso(NOW - timedelta(days=40))}]
    for i in range(n_bonus):
        rows.append({"id": uuid.uuid4().hex, "customer_mobile": mob, "customer_id": cid,
                     "points": 375, "type": "bonus", "reference_type": "master_brain",
                     "reason": reason,
                     "created_at": _iso(NOW - timedelta(days=5, minutes=i))})
    for j in range(prior_reversals):
        rows.append({"id": uuid.uuid4().hex, "customer_mobile": mob, "customer_id": cid,
                     "points": -750, "type": "adjust", "reference_type": "master_brain",
                     "reason": "Reversal of 2 duplicates — earlier",
                     "created_at": _iso(NOW - timedelta(days=3, minutes=j))})
    await db.points_ledger.insert_many(rows)
    return cid


async def _bal(db, mob):
    d = await db.customers.find_one({"mobile": mob})
    return (int(d["points_balance"]), int(d["lifetime_points_earned"]))


@pytest.fixture(scope="module", autouse=True)
def cleanup(loop, db):
    yield
    async def _rm():
        for m in MOBS:
            await db.customers.delete_many({"mobile": m})
            await db.points_ledger.delete_many({"customer_mobile": m})
    loop.run_until_complete(_rm())


# --- Tests -----------------------------------------------------------------

def test_A_idempotency_and_repeat_run_noop(loop, db, user):
    """Case A: 3 duplicate top-ups. Run1 removes (N-1)*375=750 exactly; run2/run3 = no-op."""
    async def _run():
        mob = "9700000101"
        await _seed(db, mob, n_bonus=3)
        b0 = await _bal(db, mob)          # expect (125+1125, 125+1125)=(1250,1250)
        assert b0 == (1250, 1250), b0

        r1 = await REV(filter_reason="TEST_Top-up campaign", confirm=True,
                       reason="TEST_fix dupes", user=user)
        assert r1.get("applied") is True
        assert r1.get("points_reversed") == 750
        assert r1.get("total_points_to_reverse") == 750

        b1 = await _bal(db, mob)
        assert b1 == (b0[0] - 750, b0[1] - 750), b1  # balance AND lifetime drop by 750

        # 2nd run — must be idempotent no-op
        r2 = await REV(filter_reason="TEST_Top-up campaign", confirm=True,
                       reason="TEST_second run", user=user)
        assert r2.get("customers_reversed", 0) == 0 or "outstanding" in (r2.get("message") or "").lower()
        b2 = await _bal(db, mob)
        assert b2 == b1, f"REGRESSION: 2nd run changed balance {b1} -> {b2}"

        # 3rd run — still idempotent
        r3 = await REV(filter_reason="TEST_Top-up campaign", confirm=True,
                       reason="TEST_third run", user=user)
        b3 = await _bal(db, mob)
        assert b3 == b1, f"REGRESSION: 3rd run changed balance {b1} -> {b3}"
    loop.run_until_complete(_run())


def test_B_already_over_reversed_is_skipped(loop, db, user):
    """Case B: customer already over-reversed (like 9303632456). Tool must skip -> no drop."""
    async def _run():
        mob = "9700000102"
        await _seed(db, mob, n_bonus=3, prior_reversals=2)  # surplus 750, already reversed 1500
        b0 = await _bal(db, mob)
        r = await REV(filter_reason="TEST_Top-up campaign", confirm=True,
                      reason="TEST_should skip", user=user)
        # No net apply for this customer; should be no-op or applied with 0
        assert r.get("customers_reversed", 0) == 0
        b1 = await _bal(db, mob)
        assert b1 == b0, f"REGRESSION: over-reversed customer got deducted more: {b0} -> {b1}"
    loop.run_until_complete(_run())


def test_C_preview_shape(loop, db, user):
    """Preview (confirm=false) must expose total_excess_points, total_points_to_reverse,
    already_reversed_customers, and a sample with per-customer excess_points/already_reversed/outstanding."""
    async def _run():
        mob = "9700000103"
        await _seed(db, mob, n_bonus=3)
        p = await REV(filter_reason="TEST_Top-up campaign", confirm=False, user=user)
        for k in ("total_excess_points", "total_points_to_reverse",
                  "already_reversed_customers", "sample"):
            assert k in p, f"preview missing key {k}: {list(p.keys())}"
        assert p["total_excess_points"] >= 750
        assert p["total_points_to_reverse"] >= 750
        assert isinstance(p["sample"], list) and p["sample"], "sample empty"
        entry = next((s for s in p["sample"] if s.get("mobile") == mob), p["sample"][0])
        for k in ("excess_points", "already_reversed", "outstanding_to_reverse"):
            assert k in entry, f"sample entry missing {k}: {entry}"
        # cleanup this customer's ledger doesn't matter — module cleanup handles it
    loop.run_until_complete(_run())


def test_D_undo_restores_balance(loop, db, user):
    """After a confirmed reversal, undo restores the customer's prior balance + lifetime."""
    async def _run():
        mob = "9700000101"  # re-seed fresh
        await _seed(db, mob, n_bonus=3)
        b_before = await _bal(db, mob)
        r = await REV(filter_reason="TEST_Top-up campaign", confirm=True,
                      reason="TEST_for undo", user=user)
        audit_id = r.get("audit_id")
        assert audit_id, r
        b_after = await _bal(db, mob)
        assert b_after == (b_before[0] - 750, b_before[1] - 750)

        u = await UNDO(audit_id=audit_id, confirm=True, reason="TEST_undo it", user=user)
        assert not u.get("error"), u
        b_undone = await _bal(db, mob)
        assert b_undone == b_before, f"UNDO regression: {b_before} vs {b_undone}"
    loop.run_until_complete(_run())
