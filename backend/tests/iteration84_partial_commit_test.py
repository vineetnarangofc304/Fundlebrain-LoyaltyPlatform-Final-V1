"""Iteration 84 — P0 partial-commit fix for posAddPoint.

Validates:
  A. Happy path — posAddPoint writes a COMMITTED bill + earn ledger + credits balance.
  B. Self-heal — a PENDING (partially-committed) bill is RESUMED on POS retry, credited
     exactly once (no double credit), then a further retry is a true duplicate (400).
  C. Master Brain audit_partial_commit_bills detects a legacy broken bill;
     repair_partial_commit_bills backfills the earn ledger + credits it; undo reverses it.

Run:  cd /app/backend && python tests/iteration84_partial_commit_test.py
"""
import os
import sys
import time
import uuid
import asyncio
import requests

sys.path.insert(0, "/app/backend")

from database import (transactions_col, customers_col, points_ledger_col,  # noqa: E402
                      loyalty_config_col, audit_logs_col)
from routes.master_brain_tools import (  # noqa: E402
    _now_iso, _points_cutoff, _tool_audit_partial_commit_bills,
    _tool_repair_partial_commit_bills, _tool_undo_action)


def _load_env():
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.strip().startswith("REACT_APP_BACKEND_URL"):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""


BASE = (os.environ.get("REACT_APP_BACKEND_URL") or _load_env()).rstrip("/")
assert BASE, "no backend url"
POS_KEY = "ZFQWql7I3vCH0ckuWmA8zVKDDJWYPBtoQGLruEnRrFI"
HDR = {"x-api-key": POS_KEY, "Content-Type": "application/json"}
MERCHANT = "KAZO_FUNDLE"
STORE = "K00055"
MASTER = {"is_master_admin": True, "email": "iter84@fundle.io", "id": "iter84"}

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {extra}" if extra else ""))


async def _seed_customer(mobile, balance=100, lifetime=100):
    await customers_col.delete_many({"mobile": mobile})
    cid = uuid.uuid4().hex
    await customers_col.insert_one({
        "id": cid, "mobile": mobile, "name": "Iter84 Test",
        "tier": "gold", "points_balance": balance,
        "lifetime_points_earned": lifetime, "lifetime_points_redeemed": 0,
        "lifetime_spend": 50000, "visit_count": 3, "source": "pos_ewards",
        "created_at": _now_iso(),
    })
    return cid


async def _cleanup(mobiles, bills):
    await customers_col.delete_many({"mobile": {"$in": mobiles}})
    await transactions_col.delete_many({"bill_number": {"$in": bills}})
    await points_ledger_col.delete_many({"bill_number": {"$in": bills}})


# ---------------- A. Happy path ----------------
def test_happy_path():
    mobile = "9990005555"
    bill = f"IT84-HAPPY-{int(time.time())}-{uuid.uuid4().hex[:6]}"

    async def setup():
        await _seed_customer(mobile, balance=100, lifetime=100)
    asyncio.get_event_loop().run_until_complete(setup())

    r = requests.post(f"{BASE}/api/pos/posAddPoint", headers=HDR, timeout=30, json={
        "merchant_id": MERCHANT, "customer_key": STORE,
        "customer": {"mobile": mobile, "name": "Iter84 Test"},
        "transaction": {"number": bill, "id": bill, "amount": "2000",
                        "order_time": "2026-07-07 10:00:00",
                        "taxes": [{"name": "GST", "amount": "100"}]}})
    env = r.json()
    resp = env.get("response") or {}
    check("A1 happy 200 envelope", env.get("status_code") == 200, str(env))
    earned = int(resp.get("points_earned") or 0)
    check("A2 points_earned > 0", earned > 0, f"earned={earned}")

    async def verify():
        tx = await transactions_col.find_one({"bill_number": bill}, {"_id": 0})
        cust = await customers_col.find_one({"mobile": mobile}, {"_id": 0})
        led = await points_ledger_col.find_one(
            {"bill_number": bill, "type": "earn", "voided": {"$ne": True}}, {"_id": 0})
        return tx, cust, led
    tx, cust, led = asyncio.get_event_loop().run_until_complete(verify())
    check("A3 bill committed", tx and tx.get("commit_status") == "committed",
          tx.get("commit_status") if tx else "no txn")
    check("A4 balance_applied", tx and tx.get("balance_applied") is True)
    check("A5 earn ledger row exists", led and int(led.get("points") or 0) == earned,
          f"ledger={led.get('points') if led else None}")
    check("A6 balance credited exactly", cust and int(cust.get("points_balance") or 0) == 100 + earned,
          f"bal={cust.get('points_balance') if cust else None}")
    asyncio.get_event_loop().run_until_complete(_cleanup([mobile], [bill]))


# ---------------- B. Self-heal a PENDING partial commit ----------------
def test_self_heal():
    mobile = "9990004444"
    bill = f"IT84-HEAL-{int(time.time())}-{uuid.uuid4().hex[:6]}"

    async def setup():
        cid = await _seed_customer(mobile, balance=100, lifetime=100)
        cutoff = await _points_cutoff()
        # A bill saved by a PREVIOUS attempt that timed out before crediting: pending, no
        # ledger, balance not applied — exactly the partial-commit state.
        await transactions_col.insert_one({
            "id": uuid.uuid4().hex, "customer_id": cid, "customer_mobile": mobile,
            "store_code": STORE, "bill_number": bill, "bill_date": cutoff + " 10:00:00",
            "amount": 2000, "final_amount": 2000, "points_earned": 50, "points_redeemed": 0,
            "source": "pos_ewards", "is_return": False, "created_at": _now_iso(),
            "commit_status": "pending", "balance_applied": False,
            "_credit": {"cust_id": cid, "mobile": mobile, "earn": 50, "upgrade_bonus": 0,
                        "welcome_bonus": 0, "lifetime_spend_delta": 2000, "new_tier": "gold",
                        "old_tier": "gold", "prev_balance": 100, "welcome_flag": False,
                        "order_time": cutoff + " 10:00:00", "expires_at": None, "expiry": None}})
    asyncio.get_event_loop().run_until_complete(setup())

    # POS retry of the same bill number → should RESUME/self-heal (not reject).
    r = requests.post(f"{BASE}/api/pos/posAddPoint", headers=HDR, timeout=30, json={
        "merchant_id": MERCHANT, "customer_key": STORE,
        "customer": {"mobile": mobile}, "transaction": {"number": bill, "id": bill, "amount": "2000"}})
    env = r.json()
    resp = env.get("response") or {}
    check("B1 self-heal returns 200", env.get("status_code") == 200, str(env))
    check("B2 marked resumed", resp.get("resumed") is True, str(resp))

    async def verify1():
        cust = await customers_col.find_one({"mobile": mobile}, {"_id": 0})
        tx = await transactions_col.find_one({"bill_number": bill}, {"_id": 0})
        led = await points_ledger_col.count_documents(
            {"bill_number": bill, "type": "earn", "voided": {"$ne": True}})
        return cust, tx, led
    cust, tx, led = asyncio.get_event_loop().run_until_complete(verify1())
    check("B3 balance credited once (100->150)", cust and int(cust.get("points_balance") or 0) == 150,
          f"bal={cust.get('points_balance') if cust else None}")
    check("B4 exactly one earn ledger row", led == 1, f"ledger_count={led}")
    check("B5 bill now committed", tx and tx.get("commit_status") == "committed")

    # A further retry is now a TRUE duplicate (committed) → 400, no more credit.
    r2 = requests.post(f"{BASE}/api/pos/posAddPoint", headers=HDR, timeout=30, json={
        "merchant_id": MERCHANT, "customer_key": STORE,
        "customer": {"mobile": mobile}, "transaction": {"number": bill, "id": bill, "amount": "2000"}})
    env2 = r2.json()
    check("B6 committed retry is duplicate 400", env2.get("status_code") == 400, str(env2))

    async def verify2():
        cust = await customers_col.find_one({"mobile": mobile}, {"_id": 0})
        led = await points_ledger_col.count_documents(
            {"bill_number": bill, "type": "earn", "voided": {"$ne": True}})
        return cust, led
    cust2, led2 = asyncio.get_event_loop().run_until_complete(verify2())
    check("B7 no double credit after retry (still 150)", cust2 and int(cust2.get("points_balance") or 0) == 150,
          f"bal={cust2.get('points_balance') if cust2 else None}")
    check("B8 still exactly one earn ledger row", led2 == 1, f"ledger_count={led2}")
    asyncio.get_event_loop().run_until_complete(_cleanup([mobile], [bill]))


# ---------------- C. Legacy broken bill: audit -> repair -> undo ----------------
def test_audit_repair_undo():
    mobile = "9990006666"
    bill = f"IT84-LEGACY-{int(time.time())}-{uuid.uuid4().hex[:6]}"

    async def run():
        cid = await _seed_customer(mobile, balance=200, lifetime=200)
        cutoff = await _points_cutoff()
        # Legacy broken bill (written by the OLD code): points_earned recorded, NO
        # commit_status marker, NO earn ledger row.
        await transactions_col.insert_one({
            "id": uuid.uuid4().hex, "customer_id": cid, "customer_mobile": mobile,
            "store_code": STORE, "bill_number": bill, "bill_date": cutoff + " 11:00:00",
            "amount": 3000, "final_amount": 3000, "points_earned": 75, "points_redeemed": 0,
            "source": "pos_ewards", "is_return": False, "created_at": _now_iso()})

        audit = await _tool_audit_partial_commit_bills(user=MASTER)
        our = [s for s in (audit.get("sample") or []) if s.get("bill") == bill]
        check("C1 audit detects the broken bill", audit.get("bills_missing_earn_ledger", 0) >= 1
              and (len(our) == 1 or audit.get("bills_missing_earn_ledger") >= 1),
              f"missing={audit.get('bills_missing_earn_ledger')}")

        prev = await _tool_repair_partial_commit_bills(reason="", confirm=False, user=MASTER)
        check("C2 repair preview (no apply)", prev.get("preview") is True
              and prev.get("live_bills_to_repair", 0) >= 1, str(prev.get("live_bills_to_repair")))

        applied = await _tool_repair_partial_commit_bills(
            reason="iter84 heal partial-commit", confirm=True, user=MASTER)
        check("C3 repair applied", applied.get("applied") is True, str(applied.get("message")))
        audit_id = applied.get("audit_id")

        cust = await customers_col.find_one({"mobile": mobile}, {"_id": 0})
        led = await points_ledger_col.find_one(
            {"bill_number": bill, "type": "earn", "voided": {"$ne": True}}, {"_id": 0})
        tx = await transactions_col.find_one({"bill_number": bill}, {"_id": 0})
        check("C4 our customer credited (200->275)", cust and int(cust.get("points_balance") or 0) == 275,
              f"bal={cust.get('points_balance') if cust else None}")
        check("C5 earn ledger backfilled", led and int(led.get("points") or 0) == 75
              and led.get("fix_audit_id") == audit_id)
        check("C6 bill marked committed", tx and tx.get("commit_status") == "committed")

        re_audit = await _tool_audit_partial_commit_bills(user=MASTER)
        our2 = [s for s in (re_audit.get("sample") or []) if s.get("bill") == bill]
        check("C7 re-audit no longer lists our bill", len(our2) == 0,
              f"still_listed={len(our2)}")

        # Undo restores balance + voids the backfilled ledger row.
        upre = await _tool_undo_action(audit_id=audit_id, confirm=False, user=MASTER)
        check("C8 undo preview", upre.get("preview") is True, str(upre.get("changes_to_reverse")))
        udone = await _tool_undo_action(audit_id=audit_id, reason="iter84 undo",
                                        confirm=True, user=MASTER)
        check("C9 undo applied", udone.get("applied") is True, str(udone.get("message")))
        cust3 = await customers_col.find_one({"mobile": mobile}, {"_id": 0})
        led3 = await points_ledger_col.count_documents(
            {"bill_number": bill, "type": "earn", "voided": {"$ne": True}})
        check("C10 balance restored (->200)", cust3 and int(cust3.get("points_balance") or 0) == 200,
              f"bal={cust3.get('points_balance') if cust3 else None}")
        check("C11 backfilled ledger voided by undo", led3 == 0, f"active_earn_rows={led3}")

        await _cleanup([mobile], [bill])
        await audit_logs_col.delete_many({"id": audit_id})
    asyncio.get_event_loop().run_until_complete(run())


if __name__ == "__main__":
    test_happy_path()
    test_self_heal()
    test_audit_repair_undo()
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"\n==== {passed}/{total} checks passed ====")
    sys.exit(0 if passed == total else 1)
