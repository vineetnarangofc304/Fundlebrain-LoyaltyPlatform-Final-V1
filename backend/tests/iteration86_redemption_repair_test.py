"""Iteration 86 — deterministic Missing-Redemption Repair (LLM-free ops interface).

Reproduces the SALONI case (bill recorded points_redeemed but no redeem ledger row → balance
inflated) and validates the new endpoints:
  GET  /api/master-brain/redemption-repair/audit
  POST /api/master-brain/redemption-repair/fix   (preview + apply, optional mobile scope)
  POST /api/master-brain/undo/{audit_id}

Run:  cd /app/backend && python tests/iteration86_redemption_repair_test.py
"""
import sys
import uuid
import asyncio
import requests

sys.path.insert(0, "/app/backend")

from database import customers_col, points_ledger_col, transactions_col, audit_logs_col  # noqa: E402
from routes.master_brain_tools import _now_iso, _points_cutoff  # noqa: E402


def _env(k):
    for line in open("/app/frontend/.env"):
        if line.startswith(k):
            return line.split("=", 1)[1].strip()
    return ""


BASE = _env("REACT_APP_BACKEND_URL").rstrip("/")
MOBILE = "9445333221"
BILL = f"IT86-{uuid.uuid4().hex[:8]}"
results = []


def check(n, c, extra=""):
    results.append((n, bool(c)))
    print(f"[{'PASS' if c else 'FAIL'}] {n}" + (f" — {extra}" if extra else ""))


async def seed():
    cutoff = await _points_cutoff()
    await customers_col.delete_many({"mobile": MOBILE})
    await transactions_col.delete_many({"bill_number": BILL})
    await points_ledger_col.delete_many({"bill_number": BILL})
    cid = uuid.uuid4().hex
    # balance 1910 = inflated (should be 260 after a 1650 redemption that was never ledgered)
    await customers_col.insert_one({
        "id": cid, "mobile": MOBILE, "name": "Iter86 Saloni", "source": "pos_ewards",
        "tier": "platinum", "points_balance": 1910, "lifetime_points_earned": 5000,
        "lifetime_points_redeemed": 0, "created_at": _now_iso()})
    # live bill recording a redemption but with NO redeem ledger row
    await transactions_col.insert_one({
        "id": uuid.uuid4().hex, "customer_id": cid, "customer_mobile": MOBILE,
        "store_code": "K00055", "bill_number": BILL, "bill_date": cutoff + " 10:00:00",
        "amount": 2540, "final_amount": 2540, "points_earned": 254, "points_redeemed": 1650,
        "source": "pos_ewards", "is_return": False, "created_at": _now_iso()})
    return cid


async def verify_after_fix():
    cust = await customers_col.find_one({"mobile": MOBILE}, {"_id": 0})
    led = await points_ledger_col.find_one(
        {"bill_number": BILL, "type": "redeem", "voided": {"$ne": True}}, {"_id": 0})
    return cust, led


async def verify_after_undo():
    return await customers_col.find_one({"mobile": MOBILE}, {"_id": 0})


async def cleanup(audit_id):
    await customers_col.delete_many({"mobile": MOBILE})
    await transactions_col.delete_many({"bill_number": BILL})
    await points_ledger_col.delete_many({"bill_number": BILL})
    if audit_id:
        await audit_logs_col.delete_many({"id": audit_id})


def main():
    asyncio.get_event_loop().run_until_complete(seed())

    tok = requests.post(f"{BASE}/api/auth/login", timeout=30, json={
        "email": "masteradmin@fundle.io", "password": "Master@2026"}).json().get("token")
    check("login as master admin", bool(tok))
    h = {"Authorization": f"Bearer {tok}"}

    # audit
    a = requests.get(f"{BASE}/api/master-brain/redemption-repair/audit",
                     headers=h, timeout=60).json()
    ours = [s for s in (a.get("sample") or []) if s.get("bill") == BILL]
    check("audit detects our missing-redemption bill",
          a.get("computed") and len(ours) == 1
          and ours[0].get("points_redeemed") == 1650, f"live={a.get('live_post_cutoff')}")

    # fix preview scoped to this mobile
    p = requests.post(f"{BASE}/api/master-brain/redemption-repair/fix",
                      headers=h, timeout=60,
                      json={"mobile": MOBILE, "confirm": False}).json()
    check("fix preview (scoped, no apply)", p.get("preview") is True
          and p.get("live_bills_to_fix") == 1 and p.get("points_to_deduct") == 1650, str(p.get("points_to_deduct")))

    # apply
    ap = requests.post(f"{BASE}/api/master-brain/redemption-repair/fix",
                       headers=h, timeout=60,
                       json={"mobile": MOBILE, "confirm": True,
                             "reason": "iter86 backfill Saloni missing redemption"}).json()
    check("fix applied", ap.get("applied") is True, str(ap.get("message")))
    audit_id = ap.get("audit_id")

    cust, led = asyncio.get_event_loop().run_until_complete(verify_after_fix())
    check("balance corrected 1910 -> 260", cust and int(cust.get("points_balance") or 0) == 260,
          f"bal={cust.get('points_balance') if cust else None}")
    check("redeem ledger row written (-1650)", led and int(led.get("points") or 0) == -1650
          and led.get("fix_audit_id") == audit_id)
    check("lifetime_points_redeemed raised to 1650",
          cust and int(cust.get("lifetime_points_redeemed") or 0) == 1650)

    # re-audit clean for our bill
    a2 = requests.get(f"{BASE}/api/master-brain/redemption-repair/audit",
                      headers=h, timeout=60).json()
    ours2 = [s for s in (a2.get("sample") or []) if s.get("bill") == BILL]
    check("re-audit no longer lists our bill", len(ours2) == 0)

    # undo
    u = requests.post(f"{BASE}/api/master-brain/undo/{audit_id}", headers=h, timeout=60,
                      json={"reason": "iter86 undo"}).json()
    check("undo applied", u.get("applied") is True, str(u.get("message")))
    cust3 = asyncio.get_event_loop().run_until_complete(verify_after_undo())
    check("undo restores balance to 1910", cust3 and int(cust3.get("points_balance") or 0) == 1910,
          f"bal={cust3.get('points_balance') if cust3 else None}")

    asyncio.get_event_loop().run_until_complete(cleanup(audit_id))
    passed = sum(1 for _, ok in results if ok)
    print(f"\n==== {passed}/{len(results)} checks passed ====")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
