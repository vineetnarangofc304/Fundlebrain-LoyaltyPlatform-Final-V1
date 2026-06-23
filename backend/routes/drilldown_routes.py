"""Universal drill-down endpoint + AI insight strip (1-hour cached).

Used by every dashboard so any KPI tile can open a paginated detail view.
"""
import csv
import io
import json
import hashlib
import time
import pymongo
from datetime import datetime, timezone, timedelta
from typing import Optional, Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel

from database import (
    customers_col, transactions_col, stores_col, campaigns_col, coupons_col,
    coupon_redemptions_col, points_ledger_col, nps_col, tickets_col, api_logs_col,
    audit_logs_col, users_col, db,
)
from auth import get_current_user
from routes.ai_routes import EMERGENT_LLM_KEY, SYSTEM_PROMPT

from routes._db_timeout import db_deadline

router = APIRouter(prefix="/dashboard", tags=["drilldown"], dependencies=[Depends(db_deadline)])
# CSV export must NOT run under the 45s heavy-query deadline (large exports take longer),
# and must NOT use StreamingResponse on a POST — Starlette's BaseHTTPMiddleware breaks
# streaming POST responses ("Unexpected message received: http.request"), which silently
# truncated the download to 0 bytes. So exports live on a deadline-free router and return
# a fully-materialized Response.
export_router = APIRouter(prefix="/dashboard", tags=["drilldown"])

# Max rows for the in-memory drilldown CSV. For the FULL customer database use the
# dedicated CRM Customer Report (streaming GET export).
CSV_EXPORT_CAP = 50000


# ----- Whitelist of drillable collections -----
COLLECTION_MAP: Dict[str, Any] = {
    "customers": customers_col,
    "transactions": transactions_col,
    "stores": stores_col,
    "campaigns": campaigns_col,
    "coupons": coupons_col,
    "coupon_redemptions": coupon_redemptions_col,
    "points_ledger": points_ledger_col,
    "nps_responses": nps_col,
    "support_tickets": tickets_col,
    "api_logs": api_logs_col,
    "users": users_col,
    "audit_logs": audit_logs_col,
    "items": db["items"],
}

# Roles that may drill each collection
COLLECTION_ROLES: Dict[str, set] = {
    "users": {"super_admin", "brand_admin"},
    "audit_logs": {"super_admin", "brand_admin"},
    "api_logs": {"super_admin", "brand_admin", "crm_manager"},
}
# Default: any authenticated dashboard role


# Sensitive fields to scrub from drilldown rows
SCRUB_FIELDS = {"password_hash", "otp", "password"}


def _scrub(row: dict) -> dict:
    return {k: v for k, v in row.items() if k not in SCRUB_FIELDS}


def _can_access(user: dict, collection: str) -> bool:
    allowed = COLLECTION_ROLES.get(collection)
    if not allowed:
        return True
    return user["role"] in allowed


def _store_scope(user: dict, query: dict, collection: str) -> dict:
    """Restrict store-bound roles to their store only.

    Hardening: if the user holds a store-scoped role but has no store_id on
    their profile, deny the request rather than leaking cross-store data.
    """
    if user["role"] in {"store_manager", "store_staff"}:
        sid = user.get("store_id")
        if not sid:
            raise HTTPException(403, "Store-scoped role requires store_id on user profile")
        if collection in {"transactions", "support_tickets", "api_logs", "nps_responses"}:
            query.setdefault("store_id", sid)
        if collection == "customers":
            # Limit to customers who shop primarily at this store
            query.setdefault("preferred_store_id", sid)
    return query


class DrillRequest(BaseModel):
    collection: str
    filter: Dict[str, Any] = {}
    sort: Optional[List[List[Any]]] = None  # [["field", -1], ...]
    project: Optional[Dict[str, int]] = None
    page: int = 1
    page_size: int = 50


@router.post("/drilldown")
async def drilldown(req: DrillRequest, user: dict = Depends(get_current_user)):
    if req.collection not in COLLECTION_MAP:
        raise HTTPException(400, f"Collection '{req.collection}' is not drillable")
    if not _can_access(user, req.collection):
        raise HTTPException(403, "Forbidden for your role")

    col = COLLECTION_MAP[req.collection]
    flt = _store_scope(user, dict(req.filter or {}), req.collection)
    project = {"_id": 0}
    if req.project:
        for k, v in req.project.items():
            project[k] = v

    page = max(1, req.page)
    page_size = max(1, min(req.page_size, 200))
    skip = (page - 1) * page_size

    total = await col.count_documents(flt)
    cur = col.find(flt, project)
    if req.sort:
        cur = cur.sort(req.sort)
    rows = await cur.skip(skip).limit(page_size).to_list(page_size)
    rows = [_scrub(r) for r in rows]

    return {
        "collection": req.collection,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
        "rows": rows,
    }


class CSVDrillRequest(BaseModel):
    collection: str
    filter: Dict[str, Any] = {}
    sort: Optional[List[List[Any]]] = None
    project: Optional[Dict[str, int]] = None
    columns: List[str] = []  # ordered column keys; empty = use first row keys


@export_router.get("/drilldown/csv")
async def drilldown_csv(
    collection: str,
    filter: str = "{}",
    sort: Optional[str] = None,
    columns: str = "[]",
    user: dict = Depends(get_current_user),
):
    # GET (not POST) on purpose: Starlette's BaseHTTPMiddleware breaks streaming/large
    # responses on POSTs that carry a body ("Unexpected message received: http.request").
    # Object params (filter/sort/columns) are passed as JSON-encoded query strings.
    try:
        filter_obj = json.loads(filter or "{}")
        sort_obj = json.loads(sort) if sort else None
        columns_list = json.loads(columns or "[]")
    except Exception:
        raise HTTPException(400, "Invalid filter/sort/columns JSON")

    if collection not in COLLECTION_MAP:
        raise HTTPException(400, "Collection not drillable")
    if not _can_access(user, collection):
        raise HTTPException(403, "Forbidden")

    col = COLLECTION_MAP[collection]
    flt = _store_scope(user, dict(filter_obj or {}), collection)
    # Only fetch the requested columns — keeps memory low so we can export far more rows.
    project = {"_id": 0}
    for c in columns_list:
        project[c] = 1

    cur = col.find(flt, project)
    if sort_obj:
        cur = cur.sort([tuple(s) for s in sort_obj])
    cur = cur.allow_disk_use(True).limit(CSV_EXPORT_CAP)
    with pymongo.timeout(120):
        rows = await cur.to_list(CSV_EXPORT_CAP)
    rows = [_scrub(r) for r in rows]

    cols = columns_list or (list(rows[0].keys()) if rows else [])
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(cols)
    for r in rows:
        out = []
        for c in cols:
            v = r.get(c)
            if isinstance(v, (dict, list)):
                v = json.dumps(v, default=str)
            elif isinstance(v, datetime):
                v = v.isoformat()
            out.append("" if v is None else v)
        writer.writerow(out)
    fname = f"{collection}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ---------------- AI insight strip (cached 1 hour) ----------------
_INSIGHT_CACHE: Dict[str, Dict[str, Any]] = {}
_INSIGHT_TTL_SECONDS = 3600


def _cache_key(dashboard_key: str, payload_hash: str) -> str:
    return f"{dashboard_key}::{payload_hash}"


async def _generate_insight(dashboard_key: str, kpis_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a structured AI Intelligence Report based on the dashboard payload.

    Returns: {
        "headline": str,            # one-line punchline
        "summary": str,             # 2-3 sentence executive summary
        "drivers": [str, …],        # 3 key drivers (positive or negative)
        "recommendations": [str, …] # 2-3 concrete next actions
    }
    """
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "AI key not configured")

    from emergentintegrations.llm.chat import LlmChat, UserMessage

    prompt = (
        f"Dashboard: {dashboard_key}\n\n"
        f"Real-time KPIs from KAZO MongoDB:\n"
        f"{json.dumps(kpis_payload, indent=2, default=str)}\n\n"
        "Produce a CONCISE executive Intelligence Report as a strict JSON object with these keys:\n"
        '  "headline": one punchy sentence (max 14 words)\n'
        '  "summary": 2-3 sentences of executive context using ONLY the numbers above\n'
        '  "drivers": array of exactly 3 short strings describing what is driving the numbers (mix of positive + negative)\n'
        '  "recommendations": array of 2-3 concrete next actions for a KAZO retail leader\n\n'
        "Use ₹ for currency. NO markdown, NO code fences. Output JSON object ONLY."
    )
    llm = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"insight-{dashboard_key}-{int(time.time())}",
        system_message=SYSTEM_PROMPT,
    ).with_model("openai", "gpt-5.2")
    reply = await llm.send_message(UserMessage(text=prompt))
    raw = (reply or "").strip()
    # Strip ```json fences if model adds them
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    try:
        parsed = json.loads(raw)
    except Exception:
        # Fallback: wrap text into summary
        parsed = {
            "headline": raw[:120],
            "summary": raw,
            "drivers": [],
            "recommendations": [],
        }
    # Coerce shape
    return {
        "headline": str(parsed.get("headline", "")).strip(),
        "summary": str(parsed.get("summary", "")).strip(),
        "drivers": [str(x).strip() for x in (parsed.get("drivers") or [])][:5],
        "recommendations": [str(x).strip() for x in (parsed.get("recommendations") or [])][:5],
    }


class InsightRequest(BaseModel):
    dashboard_key: str
    payload: Dict[str, Any]
    force: bool = False


@router.post("/insight")
async def ai_insight(req: InsightRequest, user: dict = Depends(get_current_user)):
    payload_hash = hashlib.sha256(
        json.dumps(req.payload, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]
    key = _cache_key(req.dashboard_key, payload_hash)
    now = time.time()
    cached = _INSIGHT_CACHE.get(key)
    if cached and not req.force and (now - cached["ts"]) < _INSIGHT_TTL_SECONDS:
        return {
            "report": cached["report"],
            "cached": True,
            "generated_at": cached["generated_at"],
            "expires_in_seconds": int(_INSIGHT_TTL_SECONDS - (now - cached["ts"])),
        }
    try:
        report = await _generate_insight(req.dashboard_key, req.payload)
    except Exception as e:
        raise HTTPException(500, f"Insight generation failed: {str(e)}")

    _INSIGHT_CACHE[key] = {
        "report": report,
        "ts": now,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return {
        "report": report,
        "cached": False,
        "generated_at": _INSIGHT_CACHE[key]["generated_at"],
        "expires_in_seconds": _INSIGHT_TTL_SECONDS,
    }
