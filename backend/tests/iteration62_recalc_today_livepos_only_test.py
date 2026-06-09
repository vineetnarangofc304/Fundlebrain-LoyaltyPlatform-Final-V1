"""Iteration 62 — RECALC is scoped to TODAY's LIVE-POS bills only.

Client rule: "RECALC should only give points to bills from today that came from
Live POS, based on the rules configured." This test seeds 3 zero-point sale bills:
  A = today (IST)  + source=pos_ewards   -> ELIGIBLE
  B = today (IST)  + source=historic_upload -> EXCLUDED (not live POS)
  C = yesterday    + source=pos_ewards   -> EXCLUDED (not today)
and asserts a dry-run recalc only flags bill A.

Run: pytest -q backend/tests/iteration62_recalc_today_livepos_only_test.py
"""
import os
import sys
import uuid
import asyncio
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

IST = timezone(timedelta(hours=5, minutes=30))


def test_recalc_today_livepos_only():
    asyncio.run(_run())


async def _run():
    from database import db, transactions_col, customers_col
    from routes.live_monitor_routes import recalc_points, RecalcBody

    cfg = await db["loyalty_config"].find_one({"id": "default"}, {"_id": 0}) or {}
    tiers = [t for t in (cfg.get("tier_rules") or []) if t.get("is_active", True)]
    assert tiers, "preview config must have at least one active tier"
    tier_slug = sorted(tiers, key=lambda t: float(t.get("min_lifetime_spend", 0) or 0))[0]["tier"]

    today = datetime.now(IST).strftime("%Y-%m-%d")
    yest = (datetime.now(IST) - timedelta(days=1)).strftime("%Y-%m-%d")
    mobile = f"9788{uuid.uuid4().int % 1000000:06d}"
    cust_id = uuid.uuid4().hex
    base = 50000.0

    await customers_col.insert_one({
        "id": cust_id, "mobile": mobile, "tier": tier_slug,
        "points_balance": 0, "lifetime_points_earned": 0,
        "lifetime_spend": base, "source": "test_iter62",
    })

    def _txn(suffix, when_date, source):
        return {
            "id": uuid.uuid4().hex,
            "bill_number": f"IT62-{suffix}",
            "bill_date": f"{when_date}T11:00:00+05:30",
            "source": source,
            "is_return": False,
            "loyalty_flag": "1",
            "amount": base,
            "loyalty_gross_amount": base,
            "net_amount": base,
            "points_earned": 0,
            "customer_id": cust_id,
            "customer_mobile": mobile,
            "store_id": None,
        }

    bills = {
        "A": _txn("A", today, "pos_ewards"),        # eligible
        "B": _txn("B", today, "historic_upload"),   # wrong source
        "C": _txn("C", yest, "pos_ewards"),         # wrong day
    }
    await transactions_col.insert_many(list(bills.values()))

    user = {"email": "test@iter62", "role": "super_admin"}
    try:
        res = await recalc_points(RecalcBody(dry_run=True), user=user)
        assert res["source"] == "pos_ewards"
        assert res["window"]["start"] == today and res["window"]["end"] == today, res["window"]
        # Only bill A qualifies
        sample_bills = {s["bill_number"] for s in res["samples"]}
        assert res["eligible"] == 1, f"expected 1 eligible (today+pos_ewards), got {res['eligible']}; samples={res['samples']}"
        assert "IT62-A" in sample_bills, sample_bills
        assert "IT62-B" not in sample_bills and "IT62-C" not in sample_bills, sample_bills

        # An explicit historic-date range still NEVER touches historic-source bills.
        res2 = await recalc_points(RecalcBody(dry_run=True, start_date=yest, end_date=today), user=user)
        sample2 = {s["bill_number"] for s in res2["samples"]}
        assert "IT62-B" not in sample2, "historic-source bill must be excluded even with a date range"
        assert "IT62-C" in sample2, "yesterday's LIVE-POS bill should appear when its date is in range"
        print(f"OK: today+pos eligible={res['eligible']}, range(pos-only) bills={sample2}")
    finally:
        await transactions_col.delete_many({"id": {"$in": [b["id"] for b in bills.values()]}})
        await customers_col.delete_one({"id": cust_id})
