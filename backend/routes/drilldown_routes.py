"""Universal drill-down endpoint + AI insight strip (1-hour cached).

Used by every dashboard so any KPI tile can open a paginated detail view.
"""
import csv
import io
import json
import hashlib
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from database import (
    customers_col, transactions_col, stores_col, campaigns_col, coupons_col,
    coupon_redemptions_col, points_ledger_col, nps_col, tickets_col, api_logs_col,
    audit_logs_col, users_col, db,
)
from auth import get_current_user
from routes.ai_routes import EMERGENT_LLM_KEY, SYSTEM_PROMPT

router = APIRouter(prefix="/dashboard", tags=["drilldown"])


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
    """Restrict store-bound roles to their store only."""
    if user["role"] in {"store_manager", "store_staff"} and user.get("store_id"):
        if collection == "transactions":
            query.setdefault("store_id", user["store_id"])
        if collection == "support_tickets":
            query.setdefault("store_id", user["store_id"])
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


class CSVDrillRequest(DrillRequest):
    columns: List[str] = []  # ordered column keys; empty = use first row keys


@router.post("/drilldown/csv")
async def drilldown_csv(req: CSVDrillRequest, user: dict = Depends(get_current_user)):
    if req.collection not in COLLECTION_MAP:
        raise HTTPException(400, "Collection not drillable")
    if not _can_access(user, req.collection):
        raise HTTPException(403, "Forbidden")

    col = COLLECTION_MAP[req.collection]
    flt = _store_scope(user, dict(req.filter or {}), req.collection)
    project = {"_id": 0}
    if req.project:
        for k, v in req.project.items():
            project[k] = v

    # Hard cap CSV export at 10,000 rows
    cur = col.find(flt, project)
    if req.sort:
        cur = cur.sort(req.sort)
    rows = await cur.limit(10000).to_list(10000)
    rows = [_scrub(r) for r in rows]

    cols = req.columns or (list(rows[0].keys()) if rows else [])
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
    buf.seek(0)
    fname = f"{req.collection}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
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


async def _generate_insight(dashboard_key: str, kpis_payload: Dict[str, Any]) -> str:
    """Generate a 2-3 sentence AI insight based on the dashboard payload."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "AI key not configured")

    from emergentintegrations.llm.chat import LlmChat, UserMessage

    prompt = (
        f"Dashboard: {dashboard_key}\n\n"
        f"Real-time KPIs from KAZO MongoDB:\n"
        f"{json.dumps(kpis_payload, indent=2, default=str)}\n\n"
        f"Write ONE crisp executive insight (max 2 sentences, ~40 words) using ONLY the numbers above. "
        f"Highlight the most material trend or concern, and suggest ONE clear next action. "
        f"Do NOT use bullet points, headings, or markdown. Plain prose only. Use ₹ for currency."
    )
    llm = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"insight-{dashboard_key}-{int(time.time())}",
        system_message=SYSTEM_PROMPT,
    ).with_model("openai", "gpt-5.2")
    reply = await llm.send_message(UserMessage(text=prompt))
    return reply.strip()


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
            "insight": cached["text"],
            "cached": True,
            "generated_at": cached["generated_at"],
            "expires_in_seconds": int(_INSIGHT_TTL_SECONDS - (now - cached["ts"])),
        }
    try:
        text = await _generate_insight(req.dashboard_key, req.payload)
    except Exception as e:
        raise HTTPException(500, f"Insight generation failed: {str(e)}")

    _INSIGHT_CACHE[key] = {
        "text": text,
        "ts": now,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return {
        "insight": text,
        "cached": False,
        "generated_at": _INSIGHT_CACHE[key]["generated_at"],
        "expires_in_seconds": _INSIGHT_TTL_SECONDS,
    }
