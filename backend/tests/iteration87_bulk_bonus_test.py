"""Iteration 87 — Bulk Bonus Points (upload CSV/Excel/PDF → flat / top-up, validity, idempotent).

Validates the new deterministic ops flow:
  POST /api/master-brain/upload                (file → mobiles detected)
  POST /api/master-brain/bulk-bonus/run        (preview + apply; flat & top-up; expiry; dup-block; force)
  POST /api/master-brain/undo/{audit_id}

Run:  cd /app/backend && python tests/iteration87_bulk_bonus_test.py
"""
import io
import sys
import uuid
import random
import asyncio
import requests

sys.path.insert(0, "/app/backend")
from database import customers_col, points_ledger_col, audit_logs_col, mb_credit_receipts_col  # noqa: E402
from routes.master_brain_tools import _now_iso  # noqa: E402


def _env(k):
    for line in open("/app/frontend/.env"):
        if line.startswith(k):
            return line.split("=", 1)[1].strip()
    return ""


BASE = _env("REACT_APP_BACKEND_URL").rstrip("/")
TAG = "it87_" + uuid.uuid4().hex[:6]
_suffix = random.randint(10000, 99999)                 # 5 digits
M = [f"9{_suffix}{i:04d}" for i in range(3)]            # 10-digit mobiles starting with 9
results = []


def check(n, c, extra=""):
    results.append((n, bool(c)))
    print(f"[{'PASS' if c else 'FAIL'}] {n}" + (f" — {extra}" if extra else ""))


async def seed():
    await customers_col.delete_many({"_it87": TAG})
    for i, mob in enumerate(M):
        await customers_col.insert_one({
            "id": uuid.uuid4().hex, "mobile": mob, "name": f"IT87 {i}", "_it87": TAG,
            "source": "pos_ewards", "tier": "gold",
            "points_balance": [100, 300, 700][i],
            "lifetime_points_earned": [100, 300, 700][i], "created_at": _now_iso()})


async def bal(mob):
    c = await customers_col.find_one({"mobile": mob}, {"_id": 0, "points_balance": 1})
    return int((c or {}).get("points_balance") or 0)


async def cleanup(audit_ids):
    await customers_col.delete_many({"_it87": TAG})
    await points_ledger_col.delete_many({"customer_mobile": {"$in": M}})
    for a in audit_ids:
        if a:
            await audit_logs_col.delete_many({"id": a})
    await mb_credit_receipts_col.delete_many({"kind": "bulk_bonus", "reason": {"$regex": TAG}})


def main():
    asyncio.get_event_loop().run_until_complete(seed())
    tok = requests.post(f"{BASE}/api/auth/login", timeout=30,
                        json={"email": "masteradmin@fundle.io", "password": "Master@2026"}).json().get("token")
    h = {"Authorization": f"Bearer {tok}"}
    check("login", bool(tok))

    # upload CSV of mobiles
    csv = "mobile\n" + "\n".join(M) + "\n"
    up = requests.post(f"{BASE}/api/master-brain/upload", headers=h, timeout=60,
                       files={"file": ("bonus.csv", io.BytesIO(csv.encode()), "text/csv")}).json()
    att = up.get("id")
    check("upload detects 3 mobiles", up.get("mobiles_detected") == 3 and bool(att), str(up.get("mobiles_detected")))

    audits = []

    # ---- FLAT +500 with 90-day validity ----
    pv = requests.post(f"{BASE}/api/master-brain/bulk-bonus/run", headers=h, timeout=60,
                       json={"attachment_id": att, "mode": "flat", "value": 500, "expiry_days": 90, "confirm": False}).json()
    check("flat preview: 3 credited, 1500 pts", pv.get("customers_to_credit") == 3 and pv.get("total_points") == 1500, str(pv.get("total_points")))
    check("flat preview has expiry", bool(pv.get("expires_at")))

    ap = requests.post(f"{BASE}/api/master-brain/bulk-bonus/run", headers=h, timeout=60,
                       json={"attachment_id": att, "mode": "flat", "value": 500, "expiry_days": 90, "confirm": True, "reason": f"{TAG} flat award"}).json()
    check("flat applied", ap.get("applied") is True, str(ap.get("message")))
    audits.append(ap.get("audit_id"))
    b = asyncio.get_event_loop().run_until_complete(asyncio.gather(bal(M[0]), bal(M[1]), bal(M[2])))
    check("flat credited each +500", b == [600, 800, 1200], str(b))
    led = asyncio.get_event_loop().run_until_complete(
        points_ledger_col.count_documents({"customer_mobile": {"$in": M}, "type": "bonus", "expires_at": {"$ne": None}, "voided": {"$ne": True}}))
    check("flat wrote 3 bonus rows with expiry", led == 3, str(led))

    # ---- IDEMPOTENCY: same batch again → blocked ----
    dup = requests.post(f"{BASE}/api/master-brain/bulk-bonus/run", headers=h, timeout=60,
                        json={"attachment_id": att, "mode": "flat", "value": 500, "expiry_days": 90, "confirm": True, "reason": f"{TAG} dup"}).json()
    check("duplicate batch blocked (no double-credit)", dup.get("blocked") is True, str(dup.get("message"))[:60])
    b2 = asyncio.get_event_loop().run_until_complete(asyncio.gather(bal(M[0]), bal(M[1]), bal(M[2])))
    check("balances unchanged after blocked dup", b2 == [600, 800, 1200], str(b2))

    # ---- FORCE: award second time ----
    fr = requests.post(f"{BASE}/api/master-brain/bulk-bonus/run", headers=h, timeout=60,
                       json={"attachment_id": att, "mode": "flat", "value": 500, "expiry_days": 90, "confirm": True, "force": True, "reason": f"{TAG} forced second"}).json()
    check("force awards again", fr.get("applied") is True)
    audits.append(fr.get("audit_id"))
    b3 = asyncio.get_event_loop().run_until_complete(asyncio.gather(bal(M[0]), bal(M[1]), bal(M[2])))
    check("force added +500 again", b3 == [1100, 1300, 1700], str(b3))

    # undo the forced award → back to 600/800/1200
    requests.post(f"{BASE}/api/master-brain/undo/{fr.get('audit_id')}", headers=h, timeout=60, json={"reason": f"{TAG} undo forced"}).json()
    b4 = asyncio.get_event_loop().run_until_complete(asyncio.gather(bal(M[0]), bal(M[1]), bal(M[2])))
    check("undo reverses forced award", b4 == [600, 800, 1200], str(b4))

    # ---- TOP-UP to 1000: awards only the difference ----
    # current: 600, 800, 1200 → topup 1000 → +400, +200, +0 (skip)
    tp = requests.post(f"{BASE}/api/master-brain/bulk-bonus/run", headers=h, timeout=60,
                       json={"attachment_id": att, "mode": "topup", "value": 1000, "confirm": False}).json()
    check("topup preview: 2 credited, 600 pts, 1 skipped", tp.get("customers_to_credit") == 2 and tp.get("total_points") == 600 and tp.get("skipped_zero") == 1, f"{tp.get('total_points')}/{tp.get('skipped_zero')}")
    tpa = requests.post(f"{BASE}/api/master-brain/bulk-bonus/run", headers=h, timeout=60,
                        json={"attachment_id": att, "mode": "topup", "value": 1000, "confirm": True, "reason": f"{TAG} topup"}).json()
    check("topup applied", tpa.get("applied") is True)
    audits.append(tpa.get("audit_id"))
    b5 = asyncio.get_event_loop().run_until_complete(asyncio.gather(bal(M[0]), bal(M[1]), bal(M[2])))
    check("topup brings all to >=1000 (1000,1000,1200)", b5 == [1000, 1000, 1200], str(b5))

    asyncio.get_event_loop().run_until_complete(cleanup(audits))
    passed = sum(1 for _, ok in results if ok)
    print(f"\n==== {passed}/{len(results)} checks passed ====")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
