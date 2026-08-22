import asyncio
import uuid
from datetime import datetime, timezone, timedelta

from database import customers_col, db, campaigns_col
from routes.marketing_db_routes import _create as mdb_create, _member_stats, marketing_db_col
from routes.coupons_routes import (allocate_unique, UniqueAllocateIn, UniqueAudience,
                                    unique_coupons_col, coupon_batches_col)
from routes.pos_ewards_routes import _lookup_pos_coupon
from routes.campaigns_routes import run_due_campaigns

USER = {"id": "qa", "email": "qa@test", "role": "super_admin"}


async def go():
    # ---- Marketing DB member stats ----
    reals = [c["mobile"] async for c in customers_col.find({}, {"_id": 0, "mobile": 1}).limit(2)]
    fakes = []
    n = 100
    while len(fakes) < 2 and n < 100000:
        cand = f"90000{n:05d}"[-10:]
        if not await customers_col.find_one({"mobile": cand}, {"_id": 1}):
            fakes.append(cand)
        n += 1
    print("reals:", reals, "fakes(non-members):", fakes)
    mdb = await mdb_create("QA Marketing DB", "test", None, reals + fakes + [reals[0]], "paste", USER)
    print("MDB created:", mdb["total"], "members:", mdb["member_count"], "non:", mdb["non_member_count"])
    assert mdb["total"] == 2 + len(fakes), "dedupe/total wrong"
    assert mdb["member_count"] == 2, "member count wrong"
    assert mdb["non_member_count"] == len(fakes), "non-member count wrong"
    assert mdb["member_count"] + mdb["non_member_count"] == mdb["total"]

    # ---- Unique coupon allocation to the marketing DB ----
    body = UniqueAllocateIn(
        name="QA Unique Offer", coupon_type="percentage", discount_value=20,
        min_bill_amount=1000, max_discount=500,
        valid_from=datetime.now(timezone.utc) - timedelta(days=1),
        valid_to=datetime.now(timezone.utc) + timedelta(days=30),
        prefix="qa!test", audience=UniqueAudience(source="marketing_db", marketing_db_id=mdb["id"]))
    batch = await allocate_unique(body, USER)
    print("Batch:", batch["total"], "prefix:", batch["prefix"])
    assert batch["total"] == mdb["total"]
    assert batch["prefix"] == "QATEST", "prefix sanitize failed"
    codes = [uc async for uc in unique_coupons_col.find({"batch_id": batch["id"]}, {"_id": 0})]
    assert len({c["code"] for c in codes}) == mdb["total"], "codes not unique"
    member_uc = next(c for c in codes if c["mobile"] == reals[0])
    code = member_uc["code"]

    # ---- POS mobile-bound lookup ----
    c_ok, u_ok, e_ok = await _lookup_pos_coupon(code, reals[0])
    print("correct-mobile lookup:", "OK" if (c_ok and not e_ok) else e_ok)
    assert c_ok and not e_ok, "correct mobile should resolve"
    assert c_ok["discount_value"] == 20 and c_ok["coupon_type"] == "percentage"

    c_bad, u_bad, e_bad = await _lookup_pos_coupon(code, "9999999999")
    print("wrong-mobile lookup:", e_bad)
    assert e_bad and "not valid for this mobile" in e_bad, "wrong mobile must be rejected"

    # simulate redemption -> mark redeemed, then re-lookup must reject
    await unique_coupons_col.update_one({"code": code}, {"$set": {"status": "redeemed"}})
    c_re, u_re, e_re = await _lookup_pos_coupon(code, reals[0])
    print("already-redeemed lookup:", e_re)
    assert e_re and "exhausted" in e_re.lower(), "redeemed coupon must be rejected"

    # ---- Scheduling: past-due scheduled campaign auto-fires ----
    cid = uuid.uuid4().hex
    past = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    await campaigns_col.insert_one({
        "id": cid, "name": "QA Scheduled", "channels": ["sms"], "audience_type": "city",
        "audience_filter": {"city": "Mumbai"}, "objective": "generic", "roi_window": "7d",
        "send_limit": 50, "message_template": "hi", "status": "scheduled", "schedule_at": past,
        "created_at": datetime.now(timezone.utc).isoformat(), "sent": 0, "delivered": 0,
        "redeemed": 0, "revenue_generated": 0.0})
    await run_due_campaigns()
    after = await campaigns_col.find_one({"id": cid}, {"_id": 0, "status": 1, "dataset_size": 1})
    print("scheduled campaign status after runner:", after.get("status"), "dataset:", after.get("dataset_size"))
    assert after["status"] in ("completed", "running"), "scheduled campaign did not auto-fire"

    print("ALL PASS")

    # cleanup
    await marketing_db_col.delete_one({"id": mdb["id"]})
    await unique_coupons_col.delete_many({"batch_id": batch["id"]})
    await coupon_batches_col.delete_one({"id": batch["id"]})
    await campaigns_col.delete_one({"id": cid})
    await db["campaign_datasets"].delete_one({"campaign_id": cid})
    print("cleaned up")


if __name__ == "__main__":
    asyncio.run(go())
