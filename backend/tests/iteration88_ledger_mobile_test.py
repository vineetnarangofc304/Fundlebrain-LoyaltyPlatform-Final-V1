"""Iteration 88 — ensure EVERY point change writes a ledger row carrying customer_mobile
so redemptions/earnings are visible on the customer profile (Customer 360).

Covers:
- POS OTP redeem (posRedeemPointRequest -> posRedeemPointOtpCheck) writes redeem ledger w/ customer_mobile
- POS non-OTP redeem writes redeem ledger w/ customer_mobile
- customer_360_v2 shows the redemption in the ledger
- ledger-mobile backfill fixes legacy rows that only had customer_id
"""
import asyncio
import os
import uuid
import httpx
from motor.motor_asyncio import AsyncIOMotorClient

API = os.environ.get("API_URL") or "https://kazo-loyalty-hub-2.preview.emergentagent.com"
MONGO = os.environ["MONGO_URL"]
DBN = os.environ["DB_NAME"]
XKEY = "ZFQWql7I3vCH0ckuWmA8zVKDDJWYPBtoQGLruEnRrFI"
MERCH = "KAZO_FUNDLE"
STORE = "K00055"
TEST_OTP = "123456"

MOBILE = "8880001111"
CRM_EMAIL = "masteradmin@fundle.io"
CRM_PW = "Master@2026"

results = []
def check(name, cond, extra=""):
    results.append((name, cond, extra))
    print(("PASS" if cond else "FAIL"), name, extra)


async def main():
    c = AsyncIOMotorClient(MONGO); db = c[DBN]
    cust_id = "TEST_LEDGER_MOB_" + uuid.uuid4().hex[:8]
    # clean & seed a fresh customer with balance
    await db.customers.delete_many({"mobile": MOBILE})
    await db.points_ledger.delete_many({"customer_mobile": MOBILE})
    await db.points_ledger.delete_many({"customer_id": cust_id})
    await db.transactions.delete_many({"customer_mobile": MOBILE})
    await db.customers.insert_one({
        "id": cust_id, "mobile": MOBILE, "name": "Ledger Test",
        "tier": "gold", "points_balance": 5000, "lifetime_points_earned": 5000,
        "lifetime_points_redeemed": 0, "lifetime_spend": 60000, "visit_count": 5,
        "created_at": "2026-07-01T00:00:00+00:00", "first_purchase_at": "2026-01-01T00:00:00+00:00",
    })

    async with httpx.AsyncClient(timeout=60) as client:
        hdr = {"x-api-key": XKEY, "Content-Type": "application/json"}
        # ---- 1) OTP redeem flow ----
        bill1 = "LEDGTEST-" + uuid.uuid4().hex[:6]
        req = {"merchant_id": MERCH, "customer_key": STORE, "customer_mobile": MOBILE,
               "points": "200", "transaction": {"number": bill1, "amount": "2000"}}
        r1 = await client.post(f"{API}/api/pos/posRedeemPointRequest", json=req, headers=hdr)
        check("posRedeemPointRequest 200", r1.status_code == 200, str(r1.status_code))
        # verify with mock OTP bypass
        ver = {"merchant_id": MERCH, "customer_key": STORE, "customer_mobile": MOBILE,
               "otp": TEST_OTP, "points": "0", "transaction": {"number": bill1, "amount": "2000"}}
        r2 = await client.post(f"{API}/api/pos/posRedeemPointOtpCheck", json=ver, headers=hdr)
        check("posRedeemPointOtpCheck 200", r2.status_code == 200, str(r2.status_code)[:120])
        led1 = await db.points_ledger.find_one({"type": "redeem", "reference_id": bill1})
        check("OTP redeem ledger row exists", bool(led1), "")
        check("OTP redeem ledger has customer_mobile", (led1 or {}).get("customer_mobile") == MOBILE,
              str((led1 or {}).get("customer_mobile")))

        # ---- 2) profile (customer_360_v2) shows the redemption ----
        # login CRM
        lr = await client.post(f"{API}/api/auth/login", json={"email": CRM_EMAIL, "password": CRM_PW})
        tok = lr.json().get("access_token") or lr.json().get("token")
        auth = {"Authorization": f"Bearer {tok}"}
        p = await client.get(f"{API}/api/dashboard/customer-360/{cust_id}", headers=auth)
        pledger = p.json().get("points_ledger", []) if p.status_code == 200 else []
        has_redeem = any(x.get("type") == "redeem" and x.get("reference_id") == bill1 for x in pledger)
        check("customer_360 profile shows redemption", has_redeem,
              f"status={p.status_code} ledger_rows={len(pledger)}")

        # ---- 3) non-OTP redeem writes ledger w/ mobile ----
        # flip config to non-OTP temporarily
        prev = await db.loyalty_config.find_one({"id": "default"}, {"_id": 0, "require_otp_for_redeem": 1})
        await db.loyalty_config.update_one({"id": "default"}, {"$set": {"require_otp_for_redeem": False}})
        bill2 = "LEDGTEST2-" + uuid.uuid4().hex[:6]
        req2 = {"merchant_id": MERCH, "customer_key": STORE, "customer_mobile": MOBILE,
                "points": "100", "transaction": {"number": bill2, "amount": "1000"}}
        r3 = await client.post(f"{API}/api/pos/posRedeemPointRequest", json=req2, headers=hdr)
        check("non-OTP redeem 200", r3.status_code == 200, str(r3.status_code))
        led2 = await db.points_ledger.find_one({"type": "redeem", "reference_id": bill2})
        check("non-OTP redeem ledger has customer_mobile", (led2 or {}).get("customer_mobile") == MOBILE,
              str((led2 or {}).get("customer_mobile")))
        # restore config
        await db.loyalty_config.update_one({"id": "default"},
            {"$set": {"require_otp_for_redeem": bool((prev or {}).get("require_otp_for_redeem", True))}})

        # ---- 4) backfill legacy rows lacking customer_mobile ----
        legacy_id = uuid.uuid4().hex
        await db.points_ledger.insert_one({
            "id": legacy_id, "customer_id": cust_id, "type": "redeem",
            "points": -50, "reference_type": "transaction", "reference_id": "LEGACY-BILL",
            "note": "legacy row w/o mobile", "created_at": "2026-06-20T00:00:00+00:00",
        })
        aud = await client.get(f"{API}/api/master-brain/ledger-mobile-backfill/audit?mobile={MOBILE}", headers=auth)
        audj = aud.json()
        check("backfill audit finds >=1 missing", (audj.get("ledger_rows_missing_mobile") or 0) >= 1,
              str(audj.get("ledger_rows_missing_mobile")))
        fx = await client.post(f"{API}/api/master-brain/ledger-mobile-backfill/fix",
                               json={"confirm": True, "reason": "iter88 test backfill", "mobile": MOBILE}, headers=auth)
        fxj = fx.json()
        check("backfill apply ok", fxj.get("ok") is True and (fxj.get("rows_updated") or 0) >= 1,
              str(fxj.get("rows_updated")))
        led3 = await db.points_ledger.find_one({"id": legacy_id})
        check("legacy row now has customer_mobile", (led3 or {}).get("customer_mobile") == MOBILE,
              str((led3 or {}).get("customer_mobile")))

    # cleanup
    await db.customers.delete_many({"mobile": MOBILE})
    await db.points_ledger.delete_many({"$or": [{"customer_mobile": MOBILE}, {"customer_id": cust_id}]})
    await db.transactions.delete_many({"customer_mobile": MOBILE})
    c.close()

    npass = sum(1 for _, ok, _ in results if ok)
    print(f"\n==== {npass}/{len(results)} PASS ====")
    return npass == len(results)


if __name__ == "__main__":
    ok = asyncio.run(main())
    raise SystemExit(0 if ok else 1)
