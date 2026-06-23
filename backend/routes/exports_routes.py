"""Downloads Center — async report exports.

Every report export is registered here. The frontend POSTs to /exports/request with the
SAME query params the export endpoint expects, plus the row total it already knows
(`known_total`). Small results (<= SMALL_THRESHOLD) are generated inline and returned as a
ready download immediately; larger ones are generated in a background task. The generated
CSV is produced by internally calling the EXISTING (GET) export endpoint and is uploaded to
Emergent object storage. Records live in `report_exports` and are hidden after 7 days.
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

import httpx
import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from auth import get_current_user
from database import db

logger = logging.getLogger("kazo-fundle.exports")

router = APIRouter(prefix="/exports", tags=["exports"])
exports_col = db["report_exports"]

STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = "kazo-loyalty"
RETENTION_DAYS = 7
SMALL_THRESHOLD = 5000           # rows; at/below this an export downloads instantly
INTERNAL_BASE = "http://localhost:8001/api"

# report_type -> internal GET export endpoint + display metadata
REGISTRY: Dict[str, Dict[str, Any]] = {
    "drilldown":     {"label": "Drill-down",            "path": "/dashboard/drilldown/csv",       "filename": "drilldown"},
    "store_kpi":     {"label": "Store KPI Report",      "path": "/kpi-reports/store-kpi/export",  "filename": "store_kpi"},
    "crm_customers": {"label": "CRM Customer Report",   "path": "/kpi-reports/crm-customers/export", "filename": "crm_customers"},
    "shopper_bills": {"label": "Shopper Bill Report",   "path": "/shopper-report/export",         "filename": "shopper_bills"},
    "kpi_trends":    {"label": "KPI Trends",            "path": "/kpi-reports/trend/export",      "filename": "kpi_trends"},
    "live_monitor":  {"label": "Live Bill Monitor",     "path": "/live-monitor/export",           "filename": "live_monitor"},
}

# ── object storage (sync requests wrapped in threads) ─────────────────────────
_storage_key: Optional[str] = None


def _init_storage() -> str:
    global _storage_key
    if _storage_key:
        return _storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def _put_object(path: str, data: bytes, content_type: str = "text/csv") -> dict:
    global _storage_key
    key = _init_storage()
    url = f"{STORAGE_URL}/objects/{path}"
    resp = requests.put(url, headers={"X-Storage-Key": key, "Content-Type": content_type}, data=data, timeout=600)
    if resp.status_code == 403:  # stale key — refresh once
        _storage_key = None
        key = _init_storage()
        resp = requests.put(url, headers={"X-Storage-Key": key, "Content-Type": content_type}, data=data, timeout=600)
    resp.raise_for_status()
    return resp.json()


def _get_object(path: str):
    global _storage_key
    key = _init_storage()
    url = f"{STORAGE_URL}/objects/{path}"
    resp = requests.get(url, headers={"X-Storage-Key": key}, timeout=120)
    if resp.status_code == 403:
        _storage_key = None
        key = _init_storage()
        resp = requests.get(url, headers={"X-Storage-Key": key}, timeout=120)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "text/csv")


# ── generation (reuse existing GET export endpoints over loopback) ────────────
async def _fetch_csv(report_type: str, params: Dict[str, Any], auth_header: str) -> bytes:
    entry = REGISTRY[report_type]
    url = f"{INTERNAL_BASE}{entry['path']}"
    clean = {k: v for k, v in (params or {}).items() if v not in (None, "", "all")}
    async with httpx.AsyncClient(timeout=httpx.Timeout(900.0)) as client:
        resp = await client.get(url, params=clean, headers={"Authorization": auth_header})
        resp.raise_for_status()
        return resp.content


async def _store_csv(export_id: str, report_type: str, data: bytes) -> dict:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    fname = f"{REGISTRY[report_type]['filename']}_{ts}.csv"
    path = f"{APP_NAME}/exports/{export_id}.csv"
    await asyncio.to_thread(_put_object, path, data, "text/csv")
    row_count = max(0, data.count(b"\n") - 1)
    return {"storage_path": path, "filename": fname, "file_size": len(data), "row_count": row_count}


async def _run_job(export_id: str, report_type: str, params: Dict[str, Any], auth_header: str):
    try:
        data = await _fetch_csv(report_type, params, auth_header)
        meta = await _store_csv(export_id, report_type, data)
        await exports_col.update_one({"id": export_id}, {"$set": {
            "status": "ready", "completed_at": _now_iso(), **meta,
        }})
        logger.info("export %s ready (%s rows, %s bytes)", export_id, meta["row_count"], meta["file_size"])
    except Exception as e:  # noqa: BLE001
        logger.exception("export %s failed", export_id)
        await exports_col.update_one({"id": export_id}, {"$set": {
            "status": "failed", "error": str(e)[:300], "completed_at": _now_iso(),
        }})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _public(doc: dict) -> dict:
    return {
        "id": doc["id"],
        "report_type": doc.get("report_type"),
        "label": doc.get("label"),
        "status": doc.get("status"),
        "params": doc.get("params") or {},
        "filename": doc.get("filename"),
        "row_count": doc.get("row_count"),
        "file_size": doc.get("file_size"),
        "error": doc.get("error"),
        "requested_by_name": doc.get("requested_by_name"),
        "created_at": doc.get("created_at"),
        "completed_at": doc.get("completed_at"),
        "expires_at": doc.get("expires_at"),
    }


# ── API ───────────────────────────────────────────────────────────────────────
class ExportRequest(BaseModel):
    report_type: str
    params: Dict[str, Any] = {}
    label: Optional[str] = None
    known_total: Optional[int] = None


@router.post("/request")
async def request_export(req: ExportRequest, request: Request, user: dict = Depends(get_current_user)):
    if req.report_type not in REGISTRY:
        raise HTTPException(400, f"Unknown report_type '{req.report_type}'")
    auth_header = request.headers.get("authorization")
    if not auth_header:
        raise HTTPException(401, "Missing authorization")

    now = datetime.now(timezone.utc)
    export_id = str(uuid.uuid4())
    label = req.label or REGISTRY[req.report_type]["label"]
    doc = {
        "id": export_id,
        "report_type": req.report_type,
        "label": label,
        "params": req.params or {},
        "known_total": req.known_total,
        "status": "processing",
        "requested_by": user.get("id") or user.get("email"),
        "requested_by_name": user.get("name") or user.get("email") or "—",
        "is_deleted": False,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(days=RETENTION_DAYS)).isoformat(),
    }
    await exports_col.insert_one(dict(doc))

    is_small = req.known_total is not None and req.known_total <= SMALL_THRESHOLD
    if is_small:
        # Generate inline so the browser can download immediately.
        try:
            data = await _fetch_csv(req.report_type, req.params, auth_header)
            meta = await _store_csv(export_id, req.report_type, data)
            await exports_col.update_one({"id": export_id}, {"$set": {
                "status": "ready", "completed_at": _now_iso(), **meta,
            }})
            return {"mode": "instant", "status": "ready", "export_id": export_id}
        except Exception as e:  # noqa: BLE001
            logger.exception("instant export failed")
            await exports_col.update_one({"id": export_id}, {"$set": {
                "status": "failed", "error": str(e)[:300], "completed_at": _now_iso(),
            }})
            raise HTTPException(502, "Export generation failed")

    # Large export — run in the background, surface in the Downloads Center.
    asyncio.create_task(_run_job(export_id, req.report_type, req.params, auth_header))
    return {"mode": "async", "status": "processing", "export_id": export_id}


@router.get("")
async def list_exports(user: dict = Depends(get_current_user)):
    now_iso = _now_iso()
    cur = (exports_col.find({"is_deleted": {"$ne": True}, "expires_at": {"$gt": now_iso}})
           .sort("created_at", -1).limit(100))
    rows = [_public(d) async for d in cur]
    return {"exports": rows, "retention_days": RETENTION_DAYS}


@router.get("/{export_id}/download")
async def download_export(export_id: str, user: dict = Depends(get_current_user)):
    doc = await exports_col.find_one({"id": export_id, "is_deleted": {"$ne": True}})
    if not doc:
        raise HTTPException(404, "Export not found")
    if doc.get("status") != "ready" or not doc.get("storage_path"):
        raise HTTPException(409, "Export is not ready")
    data, ctype = await asyncio.to_thread(_get_object, doc["storage_path"])
    fname = doc.get("filename") or f"{export_id}.csv"
    return Response(content=data, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.delete("/{export_id}")
async def delete_export(export_id: str, user: dict = Depends(get_current_user)):
    res = await exports_col.update_one({"id": export_id}, {"$set": {"is_deleted": True}})
    if not res.matched_count:
        raise HTTPException(404, "Export not found")
    return {"status": "deleted"}
