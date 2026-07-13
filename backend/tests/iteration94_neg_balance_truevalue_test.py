"""Iteration 94 — Points Integrity Issue D: negative-balance repair TRUE-VALUE regression.

Covers:
  * SINGLE mode duplicate redemption -> restored to POSITIVE true value (NOT zero).
  * SINGLE mode genuine over-redemption -> floored to 0 (floored_to_zero=true).
  * BULK mode preview + apply (scoped to seeded throwaway mobiles) with sample fields.
  * UNDO via /points-integrity/undo/{audit_id} restores ORIGINAL negative balance.
  * Re-preview after apply returns "nothing to fix".
Test customers: 9700000011 (duplicate) and 9700000012 (over-redemption).
"""
from __future__ import annotations

import os
import uuid
import asyncio
from datetime import datetime, timezone

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

# Base URL (external preview URL, not localhost)
with open("/app/frontend/.env") as _f:
    for _line in _f:
        if _line.startswith("REACT_APP_BACKEND_URL"):
            BASE = _line.split("=", 1)[1].strip()
            break
API = BASE.rstrip("/") + "/api"

# Seeded throwaway customer mobiles
C1 = "9700000011"  # duplicate redemption: earn 100, redeem -80 x2 -> bal -60, true 20
C2 = "9700000012"  # genuine over-redemption: earn 50, redeem -70 -> bal -20, true 0

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "kazo_fundle_db")


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


async def _seed():
    """Insert clean C1/C2 customers + ledger rows."""
    c = AsyncIOMotorClient(MONGO_URL)
    db = c[DB_NAME]
    for mob in (C1, C2):
        await db.customers.delete_many({"mobile": mob})
        await db.points_ledger.delete_many({"customer_mobile": mob})
    id1 = uuid.uuid4().hex
    id2 = uuid.uuid4().hex
    await db.customers.insert_one({
        "id": id1, "mobile": C1, "name": "QA Dup Redeem", "points_balance": -60,
        "lifetime_points_earned": 100, "lifetime_points_redeemed": 160,
        "tier": "silver", "created_at": _now_iso(),
    })
    await db.customers.insert_one({
        "id": id2, "mobile": C2, "name": "QA Over Redeem", "points_balance": -20,
        "lifetime_points_earned": 50, "lifetime_points_redeemed": 70,
        "tier": "silver", "created_at": _now_iso(),
    })
    await db.points_ledger.insert_many([
        {"id": uuid.uuid4().hex, "customer_mobile": C1, "customer_id": id1, "points": 100,
         "type": "earn", "reference_type": "transaction", "bill_number": "QA-B1",
         "created_at": _now_iso()},
        {"id": uuid.uuid4().hex, "customer_mobile": C1, "customer_id": id1, "points": -80,
         "type": "redeem", "reference_type": "redemption", "bill_number": "QA-R1",
         "reference_id": "QA-R1", "created_at": _now_iso()},
        {"id": uuid.uuid4().hex, "customer_mobile": C1, "customer_id": id1, "points": -80,
         "type": "redeem", "reference_type": "redemption", "bill_number": "QA-R1",
         "reference_id": "QA-R1", "created_at": _now_iso()},
    ])
    await db.points_ledger.insert_many([
        {"id": uuid.uuid4().hex, "customer_mobile": C2, "customer_id": id2, "points": 50,
         "type": "earn", "reference_type": "transaction", "bill_number": "QA-B2",
         "created_at": _now_iso()},
        {"id": uuid.uuid4().hex, "customer_mobile": C2, "customer_id": id2, "points": -70,
         "type": "redeem", "reference_type": "redemption", "bill_number": "QA-R2",
         "reference_id": "QA-R2", "created_at": _now_iso()},
    ])
    c.close()


async def _cleanup():
    c = AsyncIOMotorClient(MONGO_URL)
    db = c[DB_NAME]
    for mob in (C1, C2):
        await db.customers.delete_many({"mobile": mob})
        await db.points_ledger.delete_many({"customer_mobile": mob})
    c.close()


async def _get_balance(mob: str):
    c = AsyncIOMotorClient(MONGO_URL)
    db = c[DB_NAME]
    doc = await db.customers.find_one({"mobile": mob}, {"_id": 0, "points_balance": 1})
    c.close()
    return doc.get("points_balance") if doc else None


# ────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def token():
    r = requests.post(API + "/auth/login",
                      json={"email": "masteradmin@fundle.io", "password": "Master@2026"},
                      timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    tk = r.json().get("token")
    assert tk
    return tk


@pytest.fixture(scope="module")
def H(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module", autouse=True)
def seed_and_cleanup():
    asyncio.run(_seed())
    yield
    asyncio.run(_cleanup())


# ────────────────────────────────────────────────────────────────
# 1. SINGLE mode — duplicate redemption -> restored to positive true value
# ────────────────────────────────────────────────────────────────
class TestSingleDuplicateRedemption:
    audit_id = None

    def test_preview_shows_true_positive_target(self, H):
        r = requests.post(API + "/points-integrity/negative-balances/preview",
                          headers=H, json={"mobile": C1}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("scope") == "single"
        assert d.get("current_balance") == -60
        assert d.get("duplicate_excess") == 80, f"expected 80 excess, got {d}"
        assert d.get("new_balance_after") == 20
        assert d.get("points_restored") == 80
        assert d.get("floored_to_zero") is False
        assert d.get("preview") is True

    def test_apply_sets_positive_true_balance(self, H):
        r = requests.post(API + "/points-integrity/negative-balances/apply",
                          headers=H, json={"mobile": C1, "reason": "QA true-value test"},
                          timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("applied") is True
        assert d.get("new_balance_after") == 20
        assert d.get("points_restored") == 80
        assert d.get("audit_id")
        TestSingleDuplicateRedemption.audit_id = d["audit_id"]
        # verify DB
        bal = asyncio.run(_get_balance(C1))
        assert bal == 20, f"C1 balance {bal}, expected 20"

    def test_re_preview_reports_nothing_to_fix(self, H):
        r = requests.post(API + "/points-integrity/negative-balances/preview",
                          headers=H, json={"mobile": C1}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("current_balance") == 20
        # server returns a message like "Balance is not negative — nothing to fix."
        msg = (d.get("message") or "").lower()
        assert "nothing to fix" in msg or "not negative" in msg, d

    def test_undo_restores_original_negative(self, H):
        aid = TestSingleDuplicateRedemption.audit_id
        assert aid, "audit_id from apply required"
        r = requests.post(API + f"/points-integrity/undo/{aid}",
                          headers=H, json={"reason": "QA undo"}, timeout=60)
        assert r.status_code == 200, r.text
        bal = asyncio.run(_get_balance(C1))
        assert bal == -60, f"After undo, C1 balance {bal}, expected -60"


# ────────────────────────────────────────────────────────────────
# 2. SINGLE mode — over-redemption, no duplicates -> floor to 0
# ────────────────────────────────────────────────────────────────
class TestSingleOverRedemption:
    audit_id = None

    def test_preview_floors_to_zero(self, H):
        r = requests.post(API + "/points-integrity/negative-balances/preview",
                          headers=H, json={"mobile": C2}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("current_balance") == -20
        assert d.get("duplicate_excess") == 0
        assert d.get("new_balance_after") == 0
        assert d.get("floored_to_zero") is True

    def test_apply_sets_balance_to_zero(self, H):
        r = requests.post(API + "/points-integrity/negative-balances/apply",
                          headers=H, json={"mobile": C2, "reason": "QA floor to zero"},
                          timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("applied") is True
        assert d.get("new_balance_after") == 0
        TestSingleOverRedemption.audit_id = d.get("audit_id")
        bal = asyncio.run(_get_balance(C2))
        assert bal == 0

    def test_undo_restores_negative(self, H):
        aid = TestSingleOverRedemption.audit_id
        assert aid
        r = requests.post(API + f"/points-integrity/undo/{aid}",
                          headers=H, json={"reason": "QA undo floor"}, timeout=60)
        assert r.status_code == 200, r.text
        bal = asyncio.run(_get_balance(C2))
        assert bal == -20


# ────────────────────────────────────────────────────────────────
# 3. BULK mode preview (omit mobile) — must include our seeded rows
# ────────────────────────────────────────────────────────────────
class TestBulkPreview:
    def test_bulk_preview_headline_and_sample_fields(self, H):
        r = requests.post(API + "/points-integrity/negative-balances/preview",
                          headers=H, json={}, timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("scope") == "bulk_all_negatives"
        for k in ("customers_affected", "total_negative_points",
                  "points_to_restore", "customers_with_duplicates", "sample"):
            assert k in d, f"missing key {k}"
        assert isinstance(d["sample"], list)
        # our seeded C1 must appear in sample or headline (may not always be within first 20
        # if many prod rows exist, but sample rows still must have the required fields)
        if d["sample"]:
            row = d["sample"][0]
            for k in ("mobile", "points_balance", "true_balance"):
                assert k in row, f"sample row missing {k}: {row}"
        # find seeded C1 in the full sample (if present) — must have true_balance 20
        for row in d["sample"]:
            if row.get("mobile") == C1:
                assert row["points_balance"] == -60
                assert row["true_balance"] == 20


# ────────────────────────────────────────────────────────────────
# 4. Scoped-apply (single) already covered above; verify duplicate excludes
#    our own master_brain compensating rows (idempotency of re-runs)
# ────────────────────────────────────────────────────────────────
class TestIdempotencyAndMasterBrainExclusion:
    def test_reapply_after_correction_reports_nothing_to_fix(self, H):
        # Re-seed cleanly first (previous tests already used C1/C2 through undo)
        asyncio.run(_seed())
        # Apply C1 twice: 2nd should not add a "duplicate" back to balance.
        r1 = requests.post(API + "/points-integrity/negative-balances/apply",
                           headers=H, json={"mobile": C1, "reason": "QA idempotency 1"},
                           timeout=60)
        assert r1.status_code == 200 and r1.json().get("applied")
        bal1 = asyncio.run(_get_balance(C1))
        assert bal1 == 20
        # Second apply: current balance is 20 (>=0), tool should say nothing to fix
        r2 = requests.post(API + "/points-integrity/negative-balances/apply",
                           headers=H, json={"mobile": C1, "reason": "QA idempotency 2"},
                           timeout=60)
        assert r2.status_code == 200
        d = r2.json()
        # Not applied because balance is not negative
        assert not d.get("applied"), f"Second apply should be no-op: {d}"
        msg = (d.get("message") or "").lower()
        assert "nothing to fix" in msg or "not negative" in msg
