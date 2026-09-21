"""Data-quality maintenance: churn-risk scoring + default-city derivation.

Two long-standing production data gaps surfaced by the client:

1. **Churn risk always reads 0 high-risk.** ``customers.churn_risk`` is a stored
   field that was only ever set to the default ``"low"`` at signup (or randomly in
   seed data) — *nothing recomputed it from behaviour*. So every real ingested
   customer stayed ``"low"`` and the "high-risk churn" metric was 0. We recompute
   it from purchase recency (days since ``last_visit_at``):
       <=90d → low · 91-180d → medium · >180d → high · never purchased → unscored

2. **~9.8 lakh customers have a blank city.** A customer's *default city* is the
   city of the store of their FIRST bill (their home store, ``home_store_id``) —
   and it never changes even if they later buy elsewhere. We fill any blank city
   from that home store's city (deriving ``home_store_id`` from the earliest bill
   for the residual that never got it).

Both run in the BACKGROUND on the CSOT-disabled ``long_col`` client (so a
multi-lakh update on production is never killed by the 30s request timeout), are
idempotent (safe to re-run), and are scheduled daily. Admin-only trigger + status
endpoints are provided for on-demand runs.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from auth import get_current_user
from routes._rollups import long_col, rollups_col

logger = logging.getLogger("kazo-fundle.data_quality")
router = APIRouter()

_STATUS_KEY = "data_quality_status"
_STATUS: Dict[str, Any] = {"state": "idle"}
_MIN_RERUN_GAP_S = 12 * 3600.0   # startup run is skipped if a run finished < 12h ago


def _require_admin(user: dict) -> None:
    if (user or {}).get("role") not in ("super_admin", "brand_admin"):
        raise HTTPException(403, "Admin only")


_BLANK = [{"city": None}, {"city": ""}, {"city": {"$exists": False}}]
_NO_HOME = [{"home_store_id": None}, {"home_store_id": ""}, {"home_store_id": {"$exists": False}}]
_NO_STORE = {"$in": [None, ""]}


def _norm_store(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v or "").strip()).upper()


async def backfill_transaction_store_id() -> Dict[str, Any]:
    """Attribute migrated bills to their real store.

    93%+ of migrated (`historic_upload`) bills have `store_id = null` but DO carry
    `store_name` / `store_code`. The Store KPI report groups by `store_id`, so those
    bills collapse into one "Unmapped" bucket instead of showing under their store.
    We resolve each distinct (store_code, store_name) combo among null-store bills to
    a store in the master (normalised match, code first then name) and bulk-set
    `store_id`. Idempotent; only fills null store_id. Unresolved combos are reported
    so the operator can see which store codes/names are missing from the master.
    """
    txns = long_col("transactions")
    stores = long_col("stores")
    by_code: Dict[str, str] = {}
    by_name: Dict[str, str] = {}
    async for s in stores.find({}, {"_id": 0, "id": 1, "code": 1, "name": 1}):
        if not s.get("id"):
            continue
        if s.get("code"):
            by_code[_norm_store(s["code"])] = s["id"]
        if s.get("name"):
            by_name[_norm_store(s["name"])] = s["id"]

    combos = await txns.aggregate([
        {"$match": {"store_id": _NO_STORE}},
        {"$group": {"_id": {"code": "$store_code", "name": "$store_name"}, "n": {"$sum": 1}}},
    ], allowDiskUse=True).to_list(10000)

    filled = 0
    unresolved: List[Dict[str, Any]] = []
    for c in combos:
        code = c["_id"].get("code")
        name = c["_id"].get("name")
        sid = by_code.get(_norm_store(code)) if code else None
        if not sid and name:
            sid = by_name.get(_norm_store(name))
        if sid:
            r = await txns.update_many(
                {"store_id": _NO_STORE, "store_code": code, "store_name": name},
                {"$set": {"store_id": sid}},
            )
            filled += r.modified_count
        else:
            unresolved.append({"code": code, "name": name, "bills": c["n"]})

    return {"distinct_combos": len(combos), "bills_mapped": filled,
            "unresolved_combos": len(unresolved),
            "unresolved_top": sorted(unresolved, key=lambda x: -x["bills"])[:20]}


async def recompute_churn_risk() -> Dict[str, Any]:
    """Recompute churn_risk for every loyalty customer from purchase recency.

    Single server-side aggregation-pipeline update (no client loop). Runs on the
    CSOT-disabled client so a multi-lakh update completes instead of being killed.
    """
    now = datetime.now(timezone.utc)
    c90 = (now - timedelta(days=90)).isoformat()
    c180 = (now - timedelta(days=180)).isoformat()
    cust = long_col("customers")
    res = await cust.update_many(
        {"mobile": {"$nin": [None, ""]}},
        [{"$set": {"churn_risk": {"$switch": {"branches": [
            {"case": {"$in": [{"$ifNull": ["$last_visit_at", None]}, [None, ""]]}, "then": "unscored"},
            {"case": {"$gte": ["$last_visit_at", c90]}, "then": "low"},
            {"case": {"$gte": ["$last_visit_at", c180]}, "then": "medium"},
        ], "default": "high"}}}}],
    )
    return {"matched": res.matched_count, "modified": res.modified_count,
            "cutoff_90d": c90[:10], "cutoff_180d": c180[:10]}


async def _store_city_map() -> Dict[str, str]:
    smap: Dict[str, str] = {}
    async for s in long_col("stores").find({}, {"_id": 0, "id": 1, "city": 1}):
        if s.get("id") and s.get("city"):
            smap[s["id"]] = s["city"]
    return smap


async def backfill_default_city() -> Dict[str, Any]:
    """Fill any blank customer city from their home store's city.

    Step 1 — customers that already have home_store_id: set city = that store's city.
    Step 2 — residual (blank city AND no home_store_id): derive home_store_id from the
             earliest bill's store, then set both home_store_id and city.
    Only ever fills BLANK cities — an existing non-blank city is never overwritten.
    """
    cust = long_col("customers")
    smap = await _store_city_map()

    filled = 0
    for sid, city in smap.items():
        r = await cust.update_many(
            {"home_store_id": sid, "$or": _BLANK},
            {"$set": {"city": city}},
        )
        filled += r.modified_count

    # Step 2 — derive the home store for the residual from their earliest bill.
    txns = long_col("transactions")
    mobiles: List[str] = [
        c["mobile"] async for c in cust.find(
            {"mobile": {"$nin": [None, ""]}, "$and": [{"$or": _BLANK}, {"$or": _NO_HOME}]},
            {"_id": 0, "mobile": 1},
        )
    ]
    derived = 0
    CHUNK = 500
    for i in range(0, len(mobiles), CHUNK):
        chunk = mobiles[i:i + CHUNK]
        agg = txns.aggregate([
            {"$match": {"customer_mobile": {"$in": chunk}, "store_id": {"$nin": [None, ""]}}},
            {"$sort": {"bill_date": 1}},
            {"$group": {"_id": "$customer_mobile", "store_id": {"$first": "$store_id"}}},
        ], allowDiskUse=True)
        async for row in agg:
            sid = row.get("store_id")
            if not sid:
                continue
            upd: Dict[str, Any] = {"home_store_id": sid}
            city = smap.get(sid)
            if city:
                upd["city"] = city
            await cust.update_one({"mobile": row["_id"]}, {"$set": upd})
            derived += 1

    return {"stores_mapped": len(smap),
            "city_filled_from_home_store": filled,
            "home_store_derived_from_first_bill": derived,
            "residual_no_home_store": len(mobiles)}


async def run_data_quality_maintenance(reason: str = "manual", force: bool = False) -> Dict[str, Any]:
    """Run both maintenance passes sequentially, off the request path. Idempotent.

    Skips (unless force) when a run finished within the last 12h so pod restarts
    don't re-trigger a full multi-lakh pass every time.
    """
    if _STATUS.get("state") == "running":
        return {"skipped": True, "reason": "already running"}
    if not force:
        try:
            doc = await rollups_col.find_one({"_id": _STATUS_KEY})
            if doc and time.time() - float(doc.get("computed_at", 0)) < _MIN_RERUN_GAP_S:
                return {"skipped": True, "reason": "ran recently", "last": doc.get("value")}
        except Exception:
            pass

    _STATUS.update({"state": "running", "reason": reason,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "store_id": None, "churn": None, "city": None, "error": None})
    try:
        _STATUS["store_id"] = await backfill_transaction_store_id()
        _STATUS["city"] = await backfill_default_city()
        _STATUS["churn"] = await recompute_churn_risk()
        _STATUS.update({"state": "done", "finished_at": datetime.now(timezone.utc).isoformat()})
        try:
            await rollups_col.replace_one(
                {"_id": _STATUS_KEY},
                {"_id": _STATUS_KEY, "value": dict(_STATUS), "computed_at": time.time()},
                upsert=True,
            )
        except Exception:
            pass
    except Exception as e:
        _STATUS.update({"state": "error", "error": str(e)})
        logger.warning("data-quality maintenance failed: %s", e)
    logger.info("data-quality maintenance (%s): %s", reason, _STATUS)
    return dict(_STATUS)


async def deferred_startup_run() -> None:
    """First-boot run, deferred so it never blocks startup. Skipped if a run
    finished within the last 12h (see run_data_quality_maintenance)."""
    await asyncio.sleep(240)
    try:
        await run_data_quality_maintenance(reason="startup")
    except Exception as e:
        logger.warning("data-quality startup run failed: %s", e)


# ── Admin endpoints ──────────────────────────────────────────────────────────
@router.post("/data-quality/run")
async def dq_run(force: bool = True, user=Depends(get_current_user)):
    """Trigger churn recompute + city backfill in the background. Poll /status."""
    _require_admin(user)
    asyncio.create_task(run_data_quality_maintenance(reason="manual", force=force))
    return {"started": True, "status_url": "/api/data-quality/status"}


@router.get("/data-quality/status")
async def dq_status(user=Depends(get_current_user)):
    _require_admin(user)
    return _STATUS
