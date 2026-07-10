"""Iteration 91 - Points Integrity Center: two code fixes + Issue B end-to-end + Issue A/C/D preview.

CODE FIX 1: Tier upgrade bonus in posAddPoint (_apply_bill_credit) - awarded ONLY when
old_tier AND new_tier are both configured KAZO slabs and rank(new) > rank(old). Legacy
tier customers being re-tiered should NOT get a bonus. Kazo->Kazo up-slab still awards.

CODE FIX 2: redemption-repair audit / _scan_missing_live_redemptions multiset fallback:
a bill with points_redeemed>0 whose redemption was already ledgered by a separate redeem
row for the SAME customer + SAME amount but keyed to a DIFFERENT bill_number is NOT
flagged as missing. A genuinely missing redemption IS still detected.

Also verifies:
- Issue B end-to-end preview -> apply -> undo (/api/points-integrity/tier-upgrade-bonus/*)
- /api/points-integrity/repair-runs + /undo/{audit_id}
- Issue A/C/D preview endpoints return the required keys
"""
import asyncio
import os
import uuid
import random
from datetime import datetime, timezone

import httpx
import pytest
from motor.motor_asyncio import AsyncIOMotorClient

API = os.environ.get("API_URL") or "https://kazo-loyalty-ops.preview.emergentagent.com"
MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBN = os.environ.get("DB_NAME", "kazo_fundle_db")
XKEY = "ZFQWql7I3vCH0ckuWmA8zVKDDJWYPBtoQGLruEnRrFI"
MERCH = "KAZO_FUNDLE"
STORE = "K00055"
CRM_EMAIL = "masteradmin@fundle.io"
CRM_PW = "Master@2026"


def _mob():
    # Digits-only Indian mobile 6-9 prefix; use 7300001xxx as per main-agent hint
    return "7300001" + "".join(str(random.randint(0, 9)) for _ in range(3))


def test_points_integrity_full():
    asyncio.run(_run())


async def _run():
    c = AsyncIOMotorClient(MONGO)
    db = c[DBN]
    failures = []

    def check(name, cond, extra=""):
        status = "PASS" if cond else "FAIL"
        print(f"{status} {name} :: {extra}")
        if not cond:
            failures.append(f"{name} :: {extra}")

    async with httpx.AsyncClient(timeout=180) as client:
        # ---- CRM login ----
        lr = await client.post(f"{API}/api/auth/login",
                               json={"email": CRM_EMAIL, "password": CRM_PW})
        check("CRM login 200", lr.status_code == 200, str(lr.status_code)[:200])
        if lr.status_code != 200:
            pytest.fail("Cannot login: " + lr.text[:200])
        tok = lr.json().get("access_token") or lr.json().get("token")
        auth = {"Authorization": f"Bearer {tok}"}
        hdr = {"x-api-key": XKEY, "Content-Type": "application/json"}

        # ═══════════ CODE FIX 1 — tier upgrade bonus guard ═══════════
        # Temporarily bump gold upgrade_bonus so we can verify regression path awards a bonus.
        await db.loyalty_config.update_one(
            {"id": "default", "tier_rules.tier": "gold"},
            {"$set": {"tier_rules.$.upgrade_bonus": 500}}
        )
        try:
            # -- Case A: legacy-tier migrated customer, high lifetime spend. Small bill re-derives kazo tier.
            legacy_mob = _mob()
            await db.customers.delete_many({"mobile": legacy_mob})
            await db.transactions.delete_many({"customer_mobile": legacy_mob})
            await db.points_ledger.delete_many({"customer_mobile": legacy_mob})
            await db.customers.insert_one({
                "id": "TEST_LEGACY_" + uuid.uuid4().hex[:8],
                "mobile": legacy_mob,
                "name": "TEST Legacy Migrated",
                "tier": "Legacy-Platinum",   # NOT a configured KAZO slab
                "lifetime_spend": 80000,     # would derive to platinum on kazo slabs
                "points_balance": 100,
                "lifetime_points_earned": 100,
                "source": "historic_upload",
                "welcome_bonus_given": True,   # skip welcome bonus interference
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            bill_no = "ITER91LEG-" + uuid.uuid4().hex[:6]
            r = await client.post(
                f"{API}/api/pos/posAddPoint",
                json={
                    "merchant_id": MERCH, "customer_key": STORE,
                    "customer": {"mobile": legacy_mob, "name": "TEST Legacy Migrated"},
                    "transaction": {"number": bill_no, "amount": "1000",
                                    "date": "2026-07-15 12:00:00"},
                }, headers=hdr)
            check("legacy posAddPoint 200", r.status_code == 200, str(r.status_code)[:200])
            await asyncio.sleep(1.2)

            # No tier_upgrade ledger row expected
            legacy_upgrade_rows = await db.points_ledger.count_documents(
                {"customer_mobile": legacy_mob, "type": "bonus", "ledger_kind": "tier_upgrade"})
            check("FIX1: legacy-tier gets NO tier_upgrade bonus row",
                  legacy_upgrade_rows == 0, f"rows={legacy_upgrade_rows}")
            cust_after = await db.customers.find_one({"mobile": legacy_mob})
            # The critical assertion is the ledger row absence above. Log balance for context.
            bal = int((cust_after or {}).get("points_balance") or 0)
            print(f"INFO: legacy customer post-bill balance={bal} (initial 100 + normal earn; NO +500 upgrade bonus)")

            # -- Case B (regression): kazo-tier customer legitimately upgrading silver -> gold
            kazo_mob = _mob()
            while kazo_mob == legacy_mob:
                kazo_mob = _mob()
            await db.customers.delete_many({"mobile": kazo_mob})
            await db.transactions.delete_many({"customer_mobile": kazo_mob})
            await db.points_ledger.delete_many({"customer_mobile": kazo_mob})
            await db.customers.insert_one({
                "id": "TEST_KAZO_" + uuid.uuid4().hex[:8],
                "mobile": kazo_mob,
                "name": "TEST Kazo Upgrader",
                "tier": "silver",           # configured kazo tier
                "lifetime_spend": 24000,    # just below gold (25000)
                "points_balance": 0,
                "lifetime_points_earned": 0,
                "source": "live",
                "welcome_bonus_given": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            bill_no2 = "ITER91KAZ-" + uuid.uuid4().hex[:6]
            r2 = await client.post(
                f"{API}/api/pos/posAddPoint",
                json={
                    "merchant_id": MERCH, "customer_key": STORE,
                    "customer": {"mobile": kazo_mob, "name": "TEST Kazo Upgrader"},
                    "transaction": {"number": bill_no2, "amount": "5000",
                                    "date": "2026-07-15 12:00:00"},
                }, headers=hdr)
            check("kazo posAddPoint 200", r2.status_code == 200, str(r2.status_code)[:200])
            await asyncio.sleep(1.2)

            kazo_upgrade_rows = await db.points_ledger.count_documents(
                {"customer_mobile": kazo_mob, "type": "bonus", "ledger_kind": "tier_upgrade"})
            check("FIX1 regression: kazo silver->gold DOES get tier_upgrade bonus row",
                  kazo_upgrade_rows == 1, f"rows={kazo_upgrade_rows}")
            row = await db.points_ledger.find_one(
                {"customer_mobile": kazo_mob, "type": "bonus", "ledger_kind": "tier_upgrade"})
            row_pts = int((row or {}).get("points") or 0)
            check("FIX1 regression: bonus points = 500", row_pts == 500,
                  f"points={row_pts}")
        finally:
            # restore gold upgrade_bonus
            await db.loyalty_config.update_one(
                {"id": "default", "tier_rules.tier": "gold"},
                {"$set": {"tier_rules.$.upgrade_bonus": 0}}
            )
            # cleanup
            await db.customers.delete_many({"mobile": {"$in": [legacy_mob, kazo_mob]}})
            await db.transactions.delete_many({"customer_mobile": {"$in": [legacy_mob, kazo_mob]}})
            await db.points_ledger.delete_many({"customer_mobile": {"$in": [legacy_mob, kazo_mob]}})

        # ═══════════ CODE FIX 2 — redemption-repair no-double-backfill ═══════════
        rep_mob = _mob()
        while rep_mob in (legacy_mob, kazo_mob):
            rep_mob = _mob()
        await db.customers.delete_many({"mobile": rep_mob})
        await db.transactions.delete_many({"customer_mobile": rep_mob})
        await db.points_ledger.delete_many({"customer_mobile": rep_mob})

        await db.customers.insert_one({
            "id": "TEST_REDEMPREP_" + uuid.uuid4().hex[:8],
            "mobile": rep_mob,
            "name": "TEST Redeem Repair",
            "tier": "gold",
            "lifetime_spend": 30000,
            "points_balance": 100,
            "lifetime_points_earned": 3000,
            "source": "live",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        # BILL_A: settlement bill with points_redeemed=1650 (LIVE date after cutoff)
        bill_a = "ITER91BILLA-" + uuid.uuid4().hex[:6]
        await db.transactions.insert_one({
            "id": "TEST_TX_A_" + uuid.uuid4().hex[:8],
            "bill_number": bill_a,
            "bill_date": "2026-07-15",
            "customer_mobile": rep_mob,
            "points_redeemed": 1650,
            "amount": 5000,
            "net_amount": 5000,
        })
        # Separate redeem ledger row keyed to DIFFERENT bill number (same amount, same customer)
        bill_b = "ITER91BILLB-" + uuid.uuid4().hex[:6]
        await db.points_ledger.insert_one({
            "id": "TEST_LR_B_" + uuid.uuid4().hex[:8],
            "customer_mobile": rep_mob,
            "type": "redeem",
            "points": -1650,
            "bill_number": bill_b,
            "reference_id": bill_b,
            "voided": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        # BILL_C: genuinely missing (points_redeemed=999, no ledger row anywhere)
        bill_c = "ITER91BILLC-" + uuid.uuid4().hex[:6]
        await db.transactions.insert_one({
            "id": "TEST_TX_C_" + uuid.uuid4().hex[:8],
            "bill_number": bill_c,
            "bill_date": "2026-07-15",
            "customer_mobile": rep_mob,
            "points_redeemed": 999,
            "amount": 3000,
            "net_amount": 3000,
        })

        # Preview via /redemption-repair/fix (mobile-scoped, uses hardened multiset scanner)
        pr = await client.post(f"{API}/api/master-brain/redemption-repair/fix",
                               json={"confirm": False, "mobile": rep_mob},
                               headers=auth)
        check("redemption-repair fix preview 200", pr.status_code == 200,
              str(pr.status_code)[:200] + " " + pr.text[:200])
        pj = pr.json() if pr.status_code == 200 else {}
        # BILL_A covered by multiset match; BILL_C not covered → exactly 1 missing
        # The response keys may vary; look for the count. Common: 'candidates', 'missing_count'
        # Print for inspection
        print("REDEMPTION FIX PREVIEW KEYS:", list(pj.keys())[:20])
        # Find something that looks like the missing count
        miss_keys = [k for k in pj.keys() if "miss" in k.lower() or "candidate" in k.lower() or "backfill" in k.lower() or "count" in k.lower()]
        print("miss-related keys:", miss_keys, {k: pj.get(k) for k in miss_keys})
        # Whatever the count, we assert:
        # A) BILL_C is in the missing set  B) BILL_A is NOT in the missing set
        # Sample entries look like: {"mobile": "...", "points_to_deduct": N, "bills": count}
        # The definitive check: scoped preview reports exactly 1 missing bill (=BILL_C) and
        # 999 points (BILL_A's 1650 must NOT be flagged because a separate redeem ledger
        # row for the same customer+amount exists — multiset match).
        check("FIX2: preview live_bills_to_fix=1 (BILL_A covered by multiset; only BILL_C missing)",
              pj.get("live_bills_to_fix") == 1,
              f"live_bills_to_fix={pj.get('live_bills_to_fix')}")
        check("FIX2: preview points_to_deduct=999 (only BILL_C, NOT BILL_A's 1650)",
              pj.get("points_to_deduct") == 999,
              f"points_to_deduct={pj.get('points_to_deduct')}")

        # ALSO check the /audit endpoint (as literally specified in the review). The audit
        # does global scan; we check whether our test bills appear in its `sample`.
        au = await client.get(
            f"{API}/api/master-brain/redemption-repair/audit",
            params={"sample_limit": 5000}, headers=auth)
        check("redemption-repair audit 200", au.status_code == 200,
              str(au.status_code)[:200])
        aj = au.json() if au.status_code == 200 else {}
        asample = aj.get("sample") or []
        a_bills = {s.get("bill") for s in asample if isinstance(s, dict)}
        # BILL_A must NOT appear (multiset fallback should cover it if the audit endpoint
        # also uses the hardened scan); BILL_C should appear.
        check("FIX2 (audit): BILL_A NOT in audit sample (multiset match)",
              bill_a not in a_bills, f"bill_A_in_sample={bill_a in a_bills}")
        check("FIX2 (audit): BILL_C IS in audit sample (genuinely missing)",
              bill_c in a_bills, f"bill_C_in_sample={bill_c in a_bills}")

        # cleanup redemption repair test data
        await db.customers.delete_many({"mobile": rep_mob})
        await db.transactions.delete_many({"customer_mobile": rep_mob})
        await db.points_ledger.delete_many({"customer_mobile": rep_mob})

        # ═══════════ Issue B end-to-end via /api/points-integrity/tier-upgrade-bonus/* ═══════════
        b_mob = _mob()
        while b_mob in (legacy_mob, kazo_mob, rep_mob):
            b_mob = _mob()
        await db.customers.delete_many({"mobile": b_mob})
        await db.points_ledger.delete_many({"customer_mobile": b_mob})

        await db.customers.insert_one({
            "id": "TEST_ISSB_" + uuid.uuid4().hex[:8],
            "mobile": b_mob,
            "name": "TEST IssueB Migrated",
            "tier": "gold",
            "lifetime_spend": 30000,
            "points_balance": 1500,
            "lifetime_points_earned": 1500,
            "source": "historic_upload",     # migrated
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        b_ledger_id = "TEST_LR_TU_" + uuid.uuid4().hex[:8]
        await db.points_ledger.insert_one({
            "id": b_ledger_id,
            "customer_mobile": b_mob,
            "type": "bonus",
            "ledger_kind": "tier_upgrade",
            "points": 500,
            "voided": False,
            "created_at": "2026-07-01T10:00:00+00:00",
            "bill_date": "2026-07-01",
        })

        # Preview
        pv = await client.post(
            f"{API}/api/points-integrity/tier-upgrade-bonus/preview",
            json={"start": "2026-06-01", "end": "2026-12-31",
                  "migrated_only": True, "mobile": b_mob},
            headers=auth)
        check("IssueB preview 200", pv.status_code == 200, str(pv.status_code)[:200])
        pvj = pv.json() if pv.status_code == 200 else {}
        print("IssueB preview keys:", list(pvj.keys()))
        # Check numbers
        bonus_rows = pvj.get("bonus_rows") or pvj.get("rows_affected") or pvj.get("row_count")
        cust_aff = pvj.get("customers_affected") or pvj.get("customer_count")
        pts_rev = pvj.get("points_to_reverse") or pvj.get("total_points") or pvj.get("points")
        check("IssueB preview bonus_rows>=1", (bonus_rows or 0) >= 1, f"bonus_rows={bonus_rows} full={pvj}")
        check("IssueB preview customers_affected>=1", (cust_aff or 0) >= 1, f"={cust_aff}")
        check("IssueB preview points_to_reverse==500", pts_rev == 500, f"={pts_rev}")

        # Apply
        ap = await client.post(
            f"{API}/api/points-integrity/tier-upgrade-bonus/apply",
            json={"start": "2026-06-01", "end": "2026-12-31",
                  "migrated_only": True, "mobile": b_mob,
                  "reason": "iter91 automated test - reverse wrong tier upgrade"},
            headers=auth)
        check("IssueB apply 200", ap.status_code == 200,
              str(ap.status_code)[:200] + " " + ap.text[:200])
        aj = ap.json() if ap.status_code == 200 else {}
        audit_id = aj.get("audit_id") or aj.get("id")
        check("IssueB apply returns audit_id", bool(audit_id), f"resp={aj}")

        await asyncio.sleep(0.6)
        # Verify: row voided, balance 1500->1000
        row = await db.points_ledger.find_one({"id": b_ledger_id})
        check("IssueB row voided after apply",
              bool((row or {}).get("voided")), f"voided={(row or {}).get('voided')}")
        cust = await db.customers.find_one({"mobile": b_mob})
        check("IssueB customer balance 1500 -> 1000",
              int((cust or {}).get("points_balance") or 0) == 1000,
              f"balance={(cust or {}).get('points_balance')}")
        check("IssueB lifetime_points_earned decremented",
              int((cust or {}).get("lifetime_points_earned") or 0) == 1000,
              f"lpe={(cust or {}).get('lifetime_points_earned')}")

        # repair-runs listing
        rr = await client.get(f"{API}/api/points-integrity/repair-runs?limit=40", headers=auth)
        check("repair-runs 200", rr.status_code == 200, str(rr.status_code)[:120])
        rrj = rr.json() if rr.status_code == 200 else {}
        run_ids = {r.get("id") for r in (rrj.get("runs") or [])}
        check("repair-runs includes our audit_id",
              audit_id in run_ids if audit_id else False,
              f"present={audit_id in run_ids if audit_id else '?'} count={rrj.get('count')}")

        # Undo
        if audit_id:
            un = await client.post(
                f"{API}/api/points-integrity/undo/{audit_id}",
                json={"reason": "iter91 automated test - undo"}, headers=auth)
            check("IssueB undo 200", un.status_code == 200,
                  str(un.status_code)[:200] + " " + un.text[:200])
            await asyncio.sleep(0.6)
            row2 = await db.points_ledger.find_one({"id": b_ledger_id})
            check("IssueB undo un-voids the ledger row",
                  not bool((row2 or {}).get("voided")),
                  f"voided={(row2 or {}).get('voided')}")
            cust2 = await db.customers.find_one({"mobile": b_mob})
            check("IssueB undo restores balance to 1500",
                  int((cust2 or {}).get("points_balance") or 0) == 1500,
                  f"balance={(cust2 or {}).get('points_balance')}")

        # cleanup issue B
        await db.customers.delete_many({"mobile": b_mob})
        await db.points_ledger.delete_many({"customer_mobile": b_mob})

        # ═══════════ Issue A / C / D preview endpoints ═══════════
        # Issue A
        ia = await client.post(
            f"{API}/api/master-brain/reverse-duplicate-credits/preview",
            json={}, headers=auth)
        check("IssueA preview 200", ia.status_code == 200, str(ia.status_code)[:120])
        iaj = ia.json() if ia.status_code == 200 else {}
        for k in ("customers_affected", "duplicate_rows", "total_excess_points"):
            check(f"IssueA response has '{k}'", k in iaj,
                  f"keys={list(iaj.keys())[:20]}")

        # Issue C
        ic = await client.post(
            f"{API}/api/points-integrity/historic-earn/preview",
            json={}, headers=auth)
        check("IssueC preview 200", ic.status_code == 200,
              str(ic.status_code)[:120] + " " + ic.text[:200])
        icj = ic.json() if ic.status_code == 200 else {}
        for k in ("historic_customers_to_reset", "derived_earned_ledger_rows_to_void"):
            check(f"IssueC response has '{k}'", k in icj,
                  f"keys={list(icj.keys())[:20]}")

        # Issue D
        idr = await client.post(
            f"{API}/api/points-integrity/negative-balances/preview",
            json={}, headers=auth)
        check("IssueD preview 200", idr.status_code == 200,
              str(idr.status_code)[:120] + " " + idr.text[:200])
        idj = idr.json() if idr.status_code == 200 else {}
        for k in ("customers_affected", "points_to_restore"):
            check(f"IssueD response has '{k}'", k in idj,
                  f"keys={list(idj.keys())[:20]}")

    c.close()

    if failures:
        print("\n===== FAILURES =====")
        for f in failures:
            print(" -", f)
        pytest.fail(f"{len(failures)} check(s) failed")
