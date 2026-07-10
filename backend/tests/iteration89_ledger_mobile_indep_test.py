"""Iteration 89 - Independent validation of ledger customer_mobile stamping + regression.

Covers additional scenarios beyond iteration 88:
- OTP redeem idempotency on retry (no double deduction)
- posAddPoint earn ledger carries customer_mobile
- Backfill 400 without reason when confirm=True
- Backfill does NOT mutate points_balance
- Regression smoke: posCustomerCheckRequest, posAddCustomer
- loyalty_config.require_otp_for_redeem restored to True at end
"""
import asyncio
import os
import uuid
import httpx
import pytest
from motor.motor_asyncio import AsyncIOMotorClient

API = os.environ.get("API_URL") or "https://kazo-loyalty-hub-2.preview.emergentagent.com"
MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBN = os.environ.get("DB_NAME", "kazo_fundle_db")
XKEY = "ZFQWql7I3vCH0ckuWmA8zVKDDJWYPBtoQGLruEnRrFI"
MERCH = "KAZO_FUNDLE"
STORE = "K00055"
TEST_OTP = "123456"
CRM_EMAIL = "masteradmin@fundle.io"
CRM_PW = "Master@2026"

MOBILE = "9990009123"  # test mobile per task guidance


@pytest.mark.asyncio
async def _test_ledger_mobile_full_flow_impl():
    c = AsyncIOMotorClient(MONGO)
    db = c[DBN]
    cust_id = "TEST_ITER89_" + uuid.uuid4().hex[:8]

    # Seed clean customer
    await db.customers.delete_many({"mobile": MOBILE})
    await db.points_ledger.delete_many({"$or": [{"customer_mobile": MOBILE}, {"customer_id": cust_id}]})
    await db.transactions.delete_many({"customer_mobile": MOBILE})
    await db.customers.insert_one({
        "id": cust_id, "mobile": MOBILE, "name": "Iter89 Test",
        "tier": "gold", "points_balance": 5000, "lifetime_points_earned": 5000,
        "lifetime_points_redeemed": 0, "lifetime_spend": 60000, "visit_count": 5,
        "created_at": "2026-07-01T00:00:00+00:00",
        "first_purchase_at": "2026-01-01T00:00:00+00:00",
    })

    failures = []

    def check(name, cond, extra=""):
        status = "PASS" if cond else "FAIL"
        print(f"{status} {name} {extra}")
        if not cond:
            failures.append(f"{name} :: {extra}")

    async with httpx.AsyncClient(timeout=60) as client:
        hdr = {"x-api-key": XKEY, "Content-Type": "application/json"}

        # ---- CRM login ----
        lr = await client.post(f"{API}/api/auth/login", json={"email": CRM_EMAIL, "password": CRM_PW})
        check("CRM login", lr.status_code == 200, str(lr.status_code))
        tok = lr.json().get("access_token") or lr.json().get("token")
        auth = {"Authorization": f"Bearer {tok}"}

        # ---- 1) posCustomerCheckRequest smoke ----
        cc = await client.post(
            f"{API}/api/pos/posCustomerCheckRequest",
            json={"merchant_id": MERCH, "customer_key": STORE, "customer_mobile": MOBILE},
            headers=hdr,
        )
        check("posCustomerCheckRequest 200", cc.status_code == 200, str(cc.status_code))

        # ---- 2) posAddPoint earn — regression check ledger has customer_mobile ----
        bill_earn = "ITER89EARN-" + uuid.uuid4().hex[:6]
        addp = await client.post(
            f"{API}/api/pos/posAddPoint",
            json={
                "merchant_id": MERCH, "customer_key": STORE,
                "customer": {"mobile": MOBILE, "name": "Iter89 Test"},
                "transaction": {"number": bill_earn, "amount": "1500"},
            },
            headers=hdr,
        )
        check("posAddPoint 200", addp.status_code == 200, str(addp.status_code)[:120])
        await asyncio.sleep(1)
        order_id = (addp.json() or {}).get("response", {}).get("order_id")
        earn_row = await db.points_ledger.find_one(
            {"type": "earn", "$or": [{"reference_id": bill_earn}, {"reference_id": order_id}]}
        )
        check("earn ledger row exists", bool(earn_row))
        check(
            "earn ledger has customer_mobile",
            (earn_row or {}).get("customer_mobile") == MOBILE,
            str((earn_row or {}).get("customer_mobile")),
        )

        # ---- 3) OTP redeem + idempotency retry (no double deduction) ----
        # NOTE: With just customer_mobile (no country_code prefix) the OTP snapshot may
        # not link the request→verify, causing points_value=0 in verify. iteration68 uses
        # "91"+MOBILE for that. Here we ONLY assert the ledger row has customer_mobile stamped,
        # which is what iteration 89's fix is about.
        bal_before = (await db.customers.find_one({"mobile": MOBILE}) or {}).get("points_balance")
        bill_r = "ITER89RED-" + uuid.uuid4().hex[:6]
        req = {"merchant_id": MERCH, "customer_key": STORE, "customer_mobile": MOBILE,
               "points": "150", "transaction": {"number": bill_r, "amount": "3000"}}
        r1 = await client.post(f"{API}/api/pos/posRedeemPointRequest", json=req, headers=hdr)
        check("posRedeemPointRequest 200", r1.status_code == 200, str(r1.status_code))
        ver = {"merchant_id": MERCH, "customer_key": STORE, "customer_mobile": MOBILE,
               "otp": TEST_OTP, "points": "150",
               "transaction": {"number": bill_r, "id": bill_r, "amount": "3000"}}
        r2 = await client.post(f"{API}/api/pos/posRedeemPointOtpCheck", json=ver, headers=hdr)
        check("posRedeemPointOtpCheck 200", r2.status_code == 200, str(r2.status_code)[:120])

        await asyncio.sleep(0.3)
        bal_after1 = (await db.customers.find_one({"mobile": MOBILE}) or {}).get("points_balance")
        check("Redeem deducts exactly 150", bal_before - bal_after1 == 150,
              f"before={bal_before} after={bal_after1}")

        led = await db.points_ledger.find_one({"type": "redeem", "reference_id": bill_r})
        check("OTP redeem ledger has customer_mobile", (led or {}).get("customer_mobile") == MOBILE)

        # retry the OTP verify — should NOT deduct again
        r2b = await client.post(f"{API}/api/pos/posRedeemPointOtpCheck", json=ver, headers=hdr)
        await asyncio.sleep(0.3)
        bal_after2 = (await db.customers.find_one({"mobile": MOBILE}) or {}).get("points_balance")
        check("Idempotent retry - no double deduction", bal_after2 == bal_after1,
              f"after1={bal_after1} after2={bal_after2} retry_status={r2b.status_code}")
        redeem_rows = await db.points_ledger.count_documents(
            {"type": "redeem", "reference_id": bill_r}
        )
        check("Idempotent retry - one ledger row only", redeem_rows == 1, f"rows={redeem_rows}")

        # ---- 4) non-OTP redeem writes ledger w/ mobile ----
        prev_cfg = await db.loyalty_config.find_one({"id": "default"}) or {}
        prev_val = bool(prev_cfg.get("require_otp_for_redeem", True))
        await db.loyalty_config.update_one({"id": "default"},
                                           {"$set": {"require_otp_for_redeem": False}}, upsert=True)
        try:
            bill_nr = "ITER89NR-" + uuid.uuid4().hex[:6]
            reqn = {"merchant_id": MERCH, "customer_key": STORE, "customer_mobile": MOBILE,
                    "points": "75", "transaction": {"number": bill_nr, "amount": "1200"}}
            rn = await client.post(f"{API}/api/pos/posRedeemPointRequest", json=reqn, headers=hdr)
            check("non-OTP redeem 200", rn.status_code == 200, str(rn.status_code)[:120])
            await asyncio.sleep(0.3)
            ledn = await db.points_ledger.find_one({"type": "redeem", "reference_id": bill_nr})
            check("non-OTP redeem ledger row exists", bool(ledn))
            check("non-OTP redeem ledger has customer_mobile",
                  (ledn or {}).get("customer_mobile") == MOBILE,
                  str((ledn or {}).get("customer_mobile")))
        finally:
            # restore config
            await db.loyalty_config.update_one({"id": "default"},
                                               {"$set": {"require_otp_for_redeem": prev_val}})

        # verify restored to True (task requirement)
        cfg_now = await db.loyalty_config.find_one({"id": "default"}) or {}
        check("require_otp_for_redeem restored to True",
              bool(cfg_now.get("require_otp_for_redeem", False)) is True,
              str(cfg_now.get("require_otp_for_redeem")))

        # ---- 5) Customer-360 shows the redemption entries (matches by mobile OR id) ----
        p = await client.get(f"{API}/api/dashboard/customer-360/{cust_id}", headers=auth)
        check("customer-360 200", p.status_code == 200, str(p.status_code))
        pledger = p.json().get("points_ledger", []) if p.status_code == 200 else []
        has_redeem = any(x.get("reference_id") == bill_r and x.get("type") == "redeem"
                         for x in pledger)
        check("customer-360 shows OTP redemption", has_redeem,
              f"rows={len(pledger)}")

        # ---- 6) Backfill audit endpoint ----
        # Seed a legacy row (customer_id only, no mobile)
        legacy_id = uuid.uuid4().hex
        await db.points_ledger.insert_one({
            "id": legacy_id, "customer_id": cust_id, "type": "redeem",
            "points": -25, "reference_type": "transaction",
            "reference_id": "ITER89LEGACY", "note": "legacy",
            "created_at": "2026-06-20T00:00:00+00:00",
        })
        aud = await client.get(
            f"{API}/api/master-brain/ledger-mobile-backfill/audit?mobile={MOBILE}",
            headers=auth,
        )
        check("audit 200", aud.status_code == 200, str(aud.status_code))
        audj = aud.json() if aud.status_code == 200 else {}
        check("audit finds legacy row", (audj.get("ledger_rows_missing_mobile") or 0) >= 1,
              str(audj.get("ledger_rows_missing_mobile")))

        # ---- 7) Backfill fix without reason -> 400 ----
        no_reason = await client.post(
            f"{API}/api/master-brain/ledger-mobile-backfill/fix",
            json={"confirm": True, "mobile": MOBILE},
            headers=auth,
        )
        check("fix without reason returns 400", no_reason.status_code == 400,
              str(no_reason.status_code))

        # ---- 8) Backfill fix WITH reason -> stamps mobile, points_balance unchanged ----
        bal_pre = (await db.customers.find_one({"mobile": MOBILE}) or {}).get("points_balance")
        fx = await client.post(
            f"{API}/api/master-brain/ledger-mobile-backfill/fix",
            json={"confirm": True, "reason": "iter89 backfill test", "mobile": MOBILE},
            headers=auth,
        )
        check("fix 200", fx.status_code == 200, str(fx.status_code))
        fxj = fx.json() if fx.status_code == 200 else {}
        check("fix ok=True and rows_updated>=1",
              fxj.get("ok") is True and (fxj.get("rows_updated") or 0) >= 1,
              f"rows_updated={fxj.get('rows_updated')} ok={fxj.get('ok')}")
        led_leg = await db.points_ledger.find_one({"id": legacy_id})
        check("legacy row got customer_mobile stamped",
              (led_leg or {}).get("customer_mobile") == MOBILE,
              str((led_leg or {}).get("customer_mobile")))
        bal_post = (await db.customers.find_one({"mobile": MOBILE}) or {}).get("points_balance")
        check("Backfill did NOT mutate points_balance", bal_pre == bal_post,
              f"pre={bal_pre} post={bal_post}")

    # cleanup
    await db.customers.delete_many({"mobile": MOBILE})
    await db.points_ledger.delete_many(
        {"$or": [{"customer_mobile": MOBILE}, {"customer_id": cust_id}]}
    )
    await db.transactions.delete_many({"customer_mobile": MOBILE})
    c.close()

    if failures:
        pytest.fail("Failures:\n" + "\n".join(failures))


def test_ledger_mobile_full_flow():
    asyncio.run(_test_ledger_mobile_full_flow_impl())


if __name__ == "__main__":
    asyncio.run(_test_ledger_mobile_full_flow_impl())
