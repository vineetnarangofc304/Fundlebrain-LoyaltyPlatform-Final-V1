"""Live API monitor."""
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Depends
from database import api_logs_col
from auth import get_current_user

router = APIRouter(prefix="/api-monitor", tags=["api-monitor"])


@router.get("/recent")
async def recent_calls(limit: int = 100, user: dict = Depends(get_current_user)):
    rows = await api_logs_col.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    return rows


@router.get("/health")
async def health(user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    start = (now - timedelta(minutes=60)).isoformat()
    start24 = (now - timedelta(hours=24)).isoformat()

    pipe = [
        {"$match": {"timestamp": {"$gte": start24}}},
        {"$group": {
            "_id": "$endpoint",
            "total": {"$sum": 1},
            "failed": {"$sum": {"$cond": [{"$gte": ["$status_code", 400]}, 1, 0]}},
            "avg_response": {"$avg": "$response_time_ms"},
        }},
        {"$sort": {"total": -1}},
    ]
    by_endpoint = await api_logs_col.aggregate(pipe).to_list(50)

    total_24h = await api_logs_col.count_documents({"timestamp": {"$gte": start24}})
    failed_24h = await api_logs_col.count_documents({"timestamp": {"$gte": start24}, "status_code": {"$gte": 400}})
    total_1h = await api_logs_col.count_documents({"timestamp": {"$gte": start}})
    failed_1h = await api_logs_col.count_documents({"timestamp": {"$gte": start}, "status_code": {"$gte": 400}})

    uptime_24h = ((total_24h - failed_24h) / total_24h * 100) if total_24h else 100
    uptime_1h = ((total_1h - failed_1h) / total_1h * 100) if total_1h else 100

    return {
        "uptime_24h_pct": round(uptime_24h, 2),
        "uptime_1h_pct": round(uptime_1h, 2),
        "total_24h": total_24h,
        "failed_24h": failed_24h,
        "total_1h": total_1h,
        "failed_1h": failed_1h,
        "by_endpoint": [
            {"endpoint": r["_id"], "total": r["total"], "failed": r["failed"],
             "avg_response_ms": round(r["avg_response"], 1) if r["avg_response"] else 0,
             "health_pct": round(((r["total"] - r["failed"]) / r["total"] * 100) if r["total"] else 100, 2)}
            for r in by_endpoint
        ],
    }


@router.get("/errors")
async def errors(limit: int = 50, user: dict = Depends(get_current_user)):
    rows = await api_logs_col.find({"status_code": {"$gte": 400}}, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    return rows
