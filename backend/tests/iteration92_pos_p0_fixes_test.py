"""Iteration 92 — Three P0 backend fixes verification.

FIX 1: Store KPI new_or_existing stamping on live POS bills + backfill endpoints.
FIX 2: posRedeemPointRequest non-OTP per-bill idempotency guard (no double deduction).
FIX 3: Points earned on PRE-TAX amount for BOTH POS payload styles via _earn_base.

Run:  cd /app/backend && python tests/iteration92_pos_p0_fixes_test.py
"""
import os
import sys
import time
import uuid
import random
import asyncio
import copy
import requests

sys.path.insert(0, "/app/backend")

from database import (transactions_col, customers_col, points_ledger_col,   # noqa: E402
                      loyalty_config_col)


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
SUPER = {"email": "superadmin@fundle.io", "password": "Fundle@2026"}

results = []
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)


def check(name, cond, extra=""):
    ok = bool(cond)
    results.append((name, ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {extra}" if extra else ""))


def _run(coro):
    return loop.run_until_complete(coro)


def _rand_mobile():
    return f"7{random.randint(100000000, 999999999)}"


def _login(email, password):
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": email, "password": password, "portal": "crm"}, timeout=15)
    r.raise_for_status()
    return r.json()["token"]


def _get_cfg(tok):
    r = requests.get(f"{BASE}/api/loyalty/config",
                     headers={"Authorization": f"Bearer {tok}"}, timeout=15)
    r.raise_for_status()
    return r.json()


def _put_cfg(tok, cfg):
    cfg = {k: v for k, v in cfg.items() if k != "_id"}
    r = requests.put(f"{BASE}/api/loyalty/config", json=cfg,
                     headers={"Authorization": f"Bearer {tok}"}, timeout=20)
    r.raise_for_status()
    return r.json()


def _pos_add(mobile, bill, amount, net_amount=None, gst=0, order_time=None):
    txn = {"number": bill, "id": bill, "amount": str(amount),
           "order_time": order_time or "2026-07-07 10:00:00"}
    if net_amount is not None:
        txn["net_amount"] = str(net_amount)
    if gst:
        txn["taxes"] = [{"name": "GST", "amount": str(gst)}]
    return requests.post(f"{BASE}/api/pos/posAddPoint", headers=HDR, timeout=30, json={
        "merchant_id": MERCHANT, "customer_key": STORE,
        "customer": {"mobile": mobile, "name": "Iter92"},
        "transaction": txn}).json()


def _pos_redeem(mobile, bill, points):
    return requests.post(f"{BASE}/api/pos/posRedeemPointRequest",
                         headers=HDR, timeout=30, json={
        "merchant_id": MERCHANT, "customer_key": STORE,
        "customer_mobile": mobile,
        "points": str(points),
        "transaction": {"number": bill, "id": bill, "amount": "1000",
                        "order_time": "2026-07-08 11:00:00"}}).json()


# ─────────────────────────── FIX 1: new_or_existing ───────────────────────────
def test_fix1_new_existing():
    print("\n─── FIX 1: new_or_existing on live POS bills + backfill ───")
    mobile = _rand_mobile()
    bill1 = f"IT92-F1A-{uuid.uuid4().hex[:8]}"
    bill2 = f"IT92-F1B-{uuid.uuid4().hex[:8]}"

    # Ensure a clean slate for this mobile
    _run(customers_col.delete_many({"mobile": mobile}))
    _run(transactions_col.delete_many({"customer_mobile": mobile}))
    _run(points_ledger_col.delete_many({"customer_mobile": mobile}))

    # Bill 1 — brand-new customer
    env1 = _pos_add(mobile, bill1, 3000, order_time="2026-07-01 10:00:00")
    check("F1.A1 first bill 200", env1.get("status_code") == 200, str(env1))
    tx1 = _run(transactions_col.find_one({"bill_number": bill1}, {"_id": 0}))
    check("F1.A2 txn1 has new_or_existing='new'",
          tx1 and tx1.get("new_or_existing") == "new",
          f"got={tx1.get('new_or_existing') if tx1 else None}")

    # Bill 2 — same mobile
    env2 = _pos_add(mobile, bill2, 4000, order_time="2026-07-02 10:00:00")
    check("F1.B1 second bill 200", env2.get("status_code") == 200, str(env2))
    tx2 = _run(transactions_col.find_one({"bill_number": bill2}, {"_id": 0}))
    check("F1.B2 txn2 has new_or_existing='existing'",
          tx2 and tx2.get("new_or_existing") == "existing",
          f"got={tx2.get('new_or_existing') if tx2 else None}")

    # Backfill audit (global) and scoped backfill
    tok = _login(SUPER["email"], SUPER["password"])
    HDRT = {"Authorization": f"Bearer {tok}"}
    audit1 = requests.get(f"{BASE}/api/kpi-reports/new-or-existing/audit",
                          headers=HDRT, timeout=60).json()
    check("F1.C1 audit has required keys",
          all(k in audit1 for k in ("total_mapped", "new", "existing",
                                     "missing", "breakdown")),
          str(list(audit1.keys())))

    # Deliberately corrupt: unset new_or_existing on bill2 to prove backfill fixes it.
    _run(transactions_col.update_one({"bill_number": bill2},
                                     {"$unset": {"new_or_existing": ""}}))
    audit_missing_before = requests.get(
        f"{BASE}/api/kpi-reports/new-or-existing/audit", headers=HDRT, timeout=60).json()
    # (Note: this is the GLOBAL audit — we can't easily assert diff, but backfill scoped is what matters.)

    # Scoped backfill for just this mobile
    bf = requests.post(f"{BASE}/api/kpi-reports/new-or-existing/backfill",
                       json={"mobile": mobile}, headers=HDRT, timeout=60).json()
    check("F1.D1 backfill ok=true", bf.get("ok") is True, str(bf))
    check("F1.D2 backfill new>=1 & existing>=1",
          int(bf.get("new") or 0) >= 1 and int(bf.get("existing") or 0) >= 1, str(bf))
    check("F1.D3 backfill mobiles_scanned>=1",
          int(bf.get("mobiles_scanned") or 0) >= 1, str(bf))

    # Re-verify tx docs
    tx1b = _run(transactions_col.find_one({"bill_number": bill1}, {"_id": 0}))
    tx2b = _run(transactions_col.find_one({"bill_number": bill2}, {"_id": 0}))
    check("F1.D4 after backfill bill1='new'",
          tx1b and tx1b.get("new_or_existing") == "new",
          f"got={tx1b.get('new_or_existing') if tx1b else None}")
    check("F1.D5 after backfill bill2='existing'",
          tx2b and tx2b.get("new_or_existing") == "existing",
          f"got={tx2b.get('new_or_existing') if tx2b else None}")

    # Cleanup
    _run(customers_col.delete_many({"mobile": mobile}))
    _run(transactions_col.delete_many(
        {"bill_number": {"$in": [bill1, bill2]}}))
    _run(points_ledger_col.delete_many(
        {"bill_number": {"$in": [bill1, bill2]}}))


# ─────────────────────────── FIX 2: non-OTP redeem idempotency ────────────────
def test_fix2_redeem_idempotency():
    print("\n─── FIX 2: posRedeemPointRequest non-OTP idempotency guard ───")
    tok = _login(SUPER["email"], SUPER["password"])
    HDRT = {"Authorization": f"Bearer {tok}"}
    orig_cfg = _get_cfg(tok)

    # Force non-OTP mode (preserve everything else)
    new_cfg = copy.deepcopy(orig_cfg)
    new_cfg["require_otp_for_redeem"] = False
    _put_cfg(tok, new_cfg)

    mobile = _rand_mobile()
    earn_bill = f"IT92-F2E-{uuid.uuid4().hex[:8]}"
    redeem_bill = f"IT92-F2R-{uuid.uuid4().hex[:8]}"

    _run(customers_col.delete_many({"mobile": mobile}))

    # Seed customer with a large balance (bypass earn maths).
    cid = uuid.uuid4().hex
    _run(customers_col.insert_one({
        "id": cid, "mobile": mobile, "name": "Iter92 F2",
        "tier": "gold", "points_balance": 1000,
        "lifetime_points_earned": 1000, "lifetime_points_redeemed": 0,
        "lifetime_spend": 50000, "visit_count": 3, "source": "pos_ewards",
        "created_at": "2026-07-01T00:00:00Z",
    }))

    # First redeem for redeem_bill
    r1 = _pos_redeem(mobile, redeem_bill, 200)
    check("F2.A1 first redeem 200", r1.get("status_code") == 200, str(r1))
    resp1 = r1.get("response") or {}
    check("F2.A2 first redeem NOT already_redeemed",
          resp1.get("already_redeemed") is not True, str(resp1))
    cust1 = _run(customers_col.find_one({"mobile": mobile}, {"_id": 0}))
    check("F2.A3 balance reduced 1000->800",
          int(cust1.get("points_balance") or 0) == 800,
          f"bal={cust1.get('points_balance')}")
    led_count1 = _run(points_ledger_col.count_documents(
        {"bill_number": redeem_bill, "type": "redeem",
         "voided": {"$ne": True}}))
    check("F2.A4 exactly ONE redeem ledger row",
          led_count1 == 1, f"ledger_count={led_count1}")

    # Retry SAME bill + same points
    r2 = _pos_redeem(mobile, redeem_bill, 200)
    check("F2.B1 retry returns 200", r2.get("status_code") == 200, str(r2))
    resp2 = r2.get("response") or {}
    check("F2.B2 retry has already_redeemed:true",
          resp2.get("already_redeemed") is True, str(resp2))
    cust2 = _run(customers_col.find_one({"mobile": mobile}, {"_id": 0}))
    check("F2.B3 balance unchanged (still 800)",
          int(cust2.get("points_balance") or 0) == 800,
          f"bal={cust2.get('points_balance')}")
    led_count2 = _run(points_ledger_col.count_documents(
        {"bill_number": redeem_bill, "type": "redeem",
         "voided": {"$ne": True}}))
    check("F2.B4 still exactly ONE redeem ledger row",
          led_count2 == 1, f"ledger_count={led_count2}")

    # Cleanup
    _run(customers_col.delete_many({"mobile": mobile}))
    _run(transactions_col.delete_many({"customer_mobile": mobile}))
    _run(points_ledger_col.delete_many({"bill_number": redeem_bill}))

    # Restore require_otp_for_redeem
    restore = copy.deepcopy(orig_cfg)
    _put_cfg(tok, restore)
    cfg_after = _get_cfg(tok)
    check("F2.Z1 require_otp_for_redeem restored",
          bool(cfg_after.get("require_otp_for_redeem")) ==
          bool(orig_cfg.get("require_otp_for_redeem", True)),
          f"got={cfg_after.get('require_otp_for_redeem')}")


# ─────────────────────────── FIX 3: pre-tax earn base ─────────────────────────
def test_fix3_pretax_earn():
    print("\n─── FIX 3: Points earn on PRE-TAX amount (both payload styles) ───")
    tok = _login(SUPER["email"], SUPER["password"])
    orig_cfg = _get_cfg(tok)

    # Force config: percent_of_spend=5, min_bill_for_earn=500,
    # earn_amount_includes_tax='auto', loyalty flag active.
    cfg = copy.deepcopy(orig_cfg)
    cfg["earn_mode"] = "percent_of_spend"
    cfg["percent_of_spend"] = 5.0
    cfg["min_bill_for_earn"] = 500.0
    cfg["earn_amount_includes_tax"] = "auto"
    # Ensure any tier multiplier for gold present (else tier-driven path)
    _put_cfg(tok, cfg)

    def _earn(env):
        return int(((env or {}).get("response") or {}).get("points_earned") or 0)

    # (a) DEFAULT/auto: amount pre-tax=5000, GST=900 (no net_amount) → base=5000
    mobile_a = _rand_mobile()
    bill_a = f"IT92-F3A-{uuid.uuid4().hex[:8]}"
    _run(customers_col.delete_many({"mobile": mobile_a}))
    env_a = _pos_add(mobile_a, bill_a, amount=5000, gst=900)
    e_a = _earn(env_a)
    tx_a = _run(transactions_col.find_one({"bill_number": bill_a}, {"_id": 0}))
    lg_a = float(tx_a.get("loyalty_gross_amount") or 0) if tx_a else 0
    check("F3.A1 pre-tax auto: earn>0", e_a > 0, f"earned={e_a}")
    check("F3.A2 pre-tax auto: loyalty_gross_amount==5000",
          abs(lg_a - 5000) < 0.5, f"lg={lg_a}")
    # 5% of 5000 = 250 (mult=1 typical); allow tier mult >=1
    check("F3.A3 earn matches 5%*5000*mult (>=250, not 295=5%*5900)",
          e_a >= 250 and e_a != 295, f"earned={e_a}")

    # (b) TAX-INCLUSIVE auto-detect: amount=5900, net_amount=5000, GST=900 → base=5000
    mobile_b = _rand_mobile()
    bill_b = f"IT92-F3B-{uuid.uuid4().hex[:8]}"
    _run(customers_col.delete_many({"mobile": mobile_b}))
    env_b = _pos_add(mobile_b, bill_b, amount=5900, net_amount=5000, gst=900)
    e_b = _earn(env_b)
    tx_b = _run(transactions_col.find_one({"bill_number": bill_b}, {"_id": 0}))
    lg_b = float(tx_b.get("loyalty_gross_amount") or 0) if tx_b else 0
    check("F3.B1 tax-incl auto: loyalty_gross_amount==5000 (not 5900)",
          abs(lg_b - 5000) < 0.5, f"lg={lg_b}")
    check("F3.B2 tax-incl auto: earn same as case A (base 5000)",
          e_b == e_a, f"earned={e_b} vs A={e_a}")

    # (c) FORCE inclusive: cfg=inclusive, amount=5900, GST=900 → base=5000
    cfg_incl = copy.deepcopy(cfg)
    cfg_incl["earn_amount_includes_tax"] = "inclusive"
    _put_cfg(tok, cfg_incl)
    mobile_c = _rand_mobile()
    bill_c = f"IT92-F3C-{uuid.uuid4().hex[:8]}"
    _run(customers_col.delete_many({"mobile": mobile_c}))
    env_c = _pos_add(mobile_c, bill_c, amount=5900, gst=900)  # no net_amount
    tx_c = _run(transactions_col.find_one({"bill_number": bill_c}, {"_id": 0}))
    lg_c = float(tx_c.get("loyalty_gross_amount") or 0) if tx_c else 0
    e_c = _earn(env_c)
    check("F3.C1 force inclusive: loyalty_gross_amount==5000",
          abs(lg_c - 5000) < 0.5, f"lg={lg_c}")
    check("F3.C2 force inclusive: earn == pre-tax case",
          e_c == e_a, f"earned={e_c} vs A={e_a}")

    # (d) FORCE exclusive: cfg=exclusive, amount=5000 (no GST) → base=5000
    cfg_excl = copy.deepcopy(cfg)
    cfg_excl["earn_amount_includes_tax"] = "exclusive"
    _put_cfg(tok, cfg_excl)
    mobile_d = _rand_mobile()
    bill_d = f"IT92-F3D-{uuid.uuid4().hex[:8]}"
    _run(customers_col.delete_many({"mobile": mobile_d}))
    env_d = _pos_add(mobile_d, bill_d, amount=5000)
    tx_d = _run(transactions_col.find_one({"bill_number": bill_d}, {"_id": 0}))
    lg_d = float(tx_d.get("loyalty_gross_amount") or 0) if tx_d else 0
    e_d = _earn(env_d)
    check("F3.D1 force exclusive: loyalty_gross_amount==5000",
          abs(lg_d - 5000) < 0.5, f"lg={lg_d}")
    check("F3.D2 force exclusive: earn == pre-tax case",
          e_d == e_a, f"earned={e_d} vs A={e_a}")

    # Cleanup
    for m, b in [(mobile_a, bill_a), (mobile_b, bill_b),
                 (mobile_c, bill_c), (mobile_d, bill_d)]:
        _run(customers_col.delete_many({"mobile": m}))
        _run(transactions_col.delete_many({"bill_number": b}))
        _run(points_ledger_col.delete_many({"bill_number": b}))

    # Reset earn_amount_includes_tax to auto (as per instructions)
    restore = copy.deepcopy(orig_cfg)
    restore["earn_amount_includes_tax"] = "auto"
    _put_cfg(tok, restore)
    cfg_final = _get_cfg(tok)
    check("F3.Z1 earn_amount_includes_tax reset to auto",
          str(cfg_final.get("earn_amount_includes_tax", "")).lower() == "auto",
          f"got={cfg_final.get('earn_amount_includes_tax')}")


if __name__ == "__main__":
    try:
        test_fix1_new_existing()
    except Exception as e:
        check("FIX1 exception", False, str(e))
    try:
        test_fix2_redeem_idempotency()
    except Exception as e:
        check("FIX2 exception", False, str(e))
    try:
        test_fix3_pretax_earn()
    except Exception as e:
        check("FIX3 exception", False, str(e))

    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"\n==== {passed}/{total} checks passed ====")
    fails = [n for n, ok in results if not ok]
    if fails:
        print("FAILED:", fails)
    sys.exit(0 if passed == total else 1)
