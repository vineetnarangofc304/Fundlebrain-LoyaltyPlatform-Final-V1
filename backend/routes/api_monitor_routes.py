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


@router.get("/db-info")
async def db_info(user: dict = Depends(get_current_user)):
    """Connected MongoDB server version + host. Run this on the DEPLOYED app
    (GET /api/api-monitor/db-info) to read the exact PRODUCTION Atlas version."""
    from database import db
    out = {"db_name": getattr(db, "name", None)}
    try:
        info = await db.client.admin.command("buildInfo")
        out["mongodb_version"] = info.get("version")
        out["git_version"] = info.get("gitVersion")
        out["modules"] = info.get("modules")
    except Exception as e:  # noqa: BLE001
        out["buildInfo_error"] = str(e)
    try:
        hi = await db.client.admin.command("hello")
        host = hi.get("me") or (hi.get("hosts") or [None])[0]
        out["host"] = host
        out["replica_set"] = hi.get("setName")
        out["is_atlas"] = bool(host and "mongodb.net" in host)
    except Exception as e:  # noqa: BLE001
        out["hello_error"] = str(e)
    return out


@router.get("/log-writer-health")
async def log_writer_health(user: dict = Depends(get_current_user)):
    """Health of the isolated background api_logs writer (queue depth, rows
    inserted/dropped/failed). Lets operators confirm on production that logging
    is keeping up and never blocking live POS traffic."""
    from db_logging import stats
    return stats()


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


@router.get("/by-store")
async def by_store(window_hours: int = 24, search: str = "", user: dict = Depends(get_current_user)):
    """Store-wise POS API health so operators can see EXACTLY which outlet is failing.
    Groups POS api_logs by store code (customer_key), over the given window, returning per
    store: total hits, failures, DB timeouts, error rate, avg/max latency and last seen.
    Sorted worst-first (most failures)."""
    from database import stores_col
    now = datetime.now(timezone.utc)
    start = (now - timedelta(hours=max(1, window_hours))).isoformat()
    pipe = [
        {"$match": {"timestamp": {"$gte": start}, "source": "pos_ewards"}},
        {"$group": {
            "_id": {"$ifNull": ["$store_code", "$request_payload.customer_key"]},
            "total": {"$sum": 1},
            "failed": {"$sum": {"$cond": [{"$gte": ["$status_code", 400]}, 1, 0]}},
            "timeouts": {"$sum": {"$cond": [
                {"$regexMatch": {"input": {"$ifNull": ["$error_reason", ""]},
                                 "regex": "NetworkTimeout|timed out|timeout", "options": "i"}}, 1, 0]}},
            "avg_response": {"$avg": "$response_time_ms"},
            "max_response": {"$max": "$response_time_ms"},
            "last_seen": {"$max": "$timestamp"},
        }},
        {"$match": {"_id": {"$nin": [None, ""]}}},
        {"$sort": {"failed": -1, "timeouts": -1, "total": -1}},
        {"$limit": 300},
    ]
    rows = await api_logs_col.aggregate(pipe, allowDiskUse=True, maxTimeMS=20000).to_list(300)
    codes = [r["_id"] for r in rows if r.get("_id")]
    name_map: dict = {}
    if codes:
        async for s in stores_col.find({"code": {"$in": codes}}, {"_id": 0, "code": 1, "name": 1, "city": 1}):
            name_map[s.get("code")] = s
    out = []
    for r in rows:
        code = r["_id"]
        s = name_map.get(code, {})
        total = r["total"] or 0
        failed = r["failed"] or 0
        out.append({
            "store_code": code,
            "store_name": s.get("name") or "—",
            "city": s.get("city") or "",
            "total": total,
            "failed": failed,
            "timeouts": r.get("timeouts", 0),
            "error_rate_pct": round(failed / total * 100, 2) if total else 0,
            "avg_response_ms": round(r.get("avg_response") or 0, 1),
            "max_response_ms": r.get("max_response") or 0,
            "last_seen": r.get("last_seen"),
        })
    if search:
        q = search.strip().lower()
        out = [o for o in out
               if q in (o["store_code"] or "").lower() or q in (o["store_name"] or "").lower()]
    return {"window_hours": window_hours, "stores": out, "count": len(out)}


@router.get("/errors")
async def errors(limit: int = 50, user: dict = Depends(get_current_user)):
    rows = await api_logs_col.find({"status_code": {"$gte": 400}}, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    return rows
