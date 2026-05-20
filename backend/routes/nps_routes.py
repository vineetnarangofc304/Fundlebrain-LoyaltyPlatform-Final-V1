"""NPS and feedback."""
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from database import nps_col, stores_col
from auth import get_current_user
import uuid

router = APIRouter(prefix="/nps", tags=["nps"])


def _sentiment(score: int) -> str:
    if score >= 9:
        return "promoter"
    if score >= 7:
        return "passive"
    return "detractor"


def _norm_days(period_days: Optional[int]) -> int:
    """`period_days <= 0` => 'all time' (20-year window)."""
    if period_days is None or period_days <= 0:
        return 365 * 20
    return period_days


@router.post("")
async def submit_nps(body: dict, user: dict = Depends(get_current_user)):
    score = int(body.get("score", -1))
    if score < 0 or score > 10:
        raise HTTPException(400, "Score must be 0-10")
    doc = {
        "id": uuid.uuid4().hex,
        "customer_id": body.get("customer_id"),
        "customer_mobile": body.get("customer_mobile"),
        "store_id": body.get("store_id"),
        "score": score,
        "sentiment": _sentiment(score),
        "feedback": body.get("feedback"),
        "category": body.get("category", "overall"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await nps_col.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/summary")
async def nps_summary(period_days: int = 60, user: dict = Depends(get_current_user)):
    period_days = _norm_days(period_days)
    start = (datetime.now(timezone.utc) - timedelta(days=period_days)).isoformat()
    pipe = [
        {"$match": {"created_at": {"$gte": start}}},
        {"$group": {
            "_id": None,
            "promoters": {"$sum": {"$cond": [{"$gte": ["$score", 9]}, 1, 0]}},
            "passives": {"$sum": {"$cond": [{"$and": [{"$gte": ["$score", 7]}, {"$lte": ["$score", 8]}]}, 1, 0]}},
            "detractors": {"$sum": {"$cond": [{"$lte": ["$score", 6]}, 1, 0]}},
            "total": {"$sum": 1},
            "avg": {"$avg": "$score"},
        }}
    ]
    r = await nps_col.aggregate(pipe).to_list(1)
    if not r:
        return {"score": None, "total": 0, "promoters": 0, "passives": 0, "detractors": 0, "avg_score": None}
    d = r[0]
    nps = round(((d["promoters"] - d["detractors"]) / d["total"]) * 100) if d["total"] else None
    return {
        "score": nps,
        "total": d["total"],
        "promoters": d["promoters"],
        "passives": d["passives"],
        "detractors": d["detractors"],
        "avg_score": round(d["avg"], 2),
    }


@router.get("/by-store")
async def nps_by_store(period_days: int = 60, user: dict = Depends(get_current_user)):
    period_days = _norm_days(period_days)
    start = (datetime.now(timezone.utc) - timedelta(days=period_days)).isoformat()
    pipe = [
        {"$match": {"created_at": {"$gte": start}, "store_id": {"$ne": None}}},
        {"$group": {
            "_id": "$store_id",
            "promoters": {"$sum": {"$cond": [{"$gte": ["$score", 9]}, 1, 0]}},
            "detractors": {"$sum": {"$cond": [{"$lte": ["$score", 6]}, 1, 0]}},
            "total": {"$sum": 1},
            "avg": {"$avg": "$score"},
        }},
        {"$sort": {"total": -1}},
    ]
    rows = await nps_col.aggregate(pipe).to_list(100)
    store_ids = [r["_id"] for r in rows]
    stores = {s["id"]: s async for s in stores_col.find({"id": {"$in": store_ids}}, {"_id": 0})}
    out = []
    for r in rows:
        s = stores.get(r["_id"], {})
        nps = round(((r["promoters"] - r["detractors"]) / r["total"]) * 100) if r["total"] else None
        out.append({
            "store_id": r["_id"],
            "store_name": s.get("name", "—"),
            "city": s.get("city", "—"),
            "nps": nps,
            "total": r["total"],
            "promoters": r["promoters"],
            "detractors": r["detractors"],
            "avg_score": round(r["avg"], 2),
        })
    return out


@router.get("/recent")
async def recent_nps(limit: int = 50, user: dict = Depends(get_current_user)):
    return await nps_col.find({}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
