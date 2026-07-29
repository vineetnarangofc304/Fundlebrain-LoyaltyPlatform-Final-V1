"""Daily Reco (missing-bill) ingestion.

The client receives a daily "Reco" file by email listing bills that never reached
the portal. This module adds ONLY the missing transactions (idempotent, keyed on
bill_number) by reusing the battle-tested historic transaction ingest with
`duplicate_mode="skip"` — so nothing already in the portal is ever touched or
double-counted, and store-linking / customer-backfill / aggregate recompute all
run exactly as they do for a normal historic upload.

Two ways in:
  • Manual upload  — POST /api/reco/upload  (CSV / XLSX)
  • Email auto-pull — POST /api/reco/run-email  and a daily scheduler job
                       (`reco_daily_job`), both reading the mailbox over IMAP
                       using RECO_IMAP_* env config (never hardcoded).
"""
from __future__ import annotations

import os
import ssl
import uuid
import email
import imaplib
import asyncio
import logging
import requests
from datetime import datetime, timezone, timedelta
from email.header import decode_header
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from auth import get_current_user, MANAGEMENT_ROLES
from database import db
from routes.historic_routes import (
    _run_ingest_job, _read_upload_to_csv_text, historic_jobs_col, MAX_FILE_BYTES,
)

logger = logging.getLogger("kazo-fundle.reco")
router = APIRouter(prefix="/reco", tags=["reco"])

reco_runs_col = db["reco_runs"]

ATTACH_EXTS = (".csv", ".xlsx", ".xls")


# ── IMAP config (from env only — no secrets in code) ──────────────────────────
def _imap_config() -> Dict[str, Any]:
    return {
        "host": (os.environ.get("RECO_IMAP_HOST") or "").strip(),
        "port": int(os.environ.get("RECO_IMAP_PORT") or 993),
        "user": (os.environ.get("RECO_IMAP_USER") or "").strip(),
        "password": os.environ.get("RECO_IMAP_PASSWORD") or "",
        "auth": (os.environ.get("RECO_IMAP_AUTH") or "basic").strip().lower(),  # basic | xoauth2
        "oauth_tenant": (os.environ.get("RECO_OAUTH_TENANT_ID") or "").strip(),
        "oauth_client_id": (os.environ.get("RECO_OAUTH_CLIENT_ID") or "").strip(),
        "oauth_client_secret": os.environ.get("RECO_OAUTH_CLIENT_SECRET") or "",
        "folder": (os.environ.get("RECO_IMAP_FOLDER") or "INBOX").strip(),
        "sender": (os.environ.get("RECO_IMAP_SENDER") or "").strip(),
        "subject": (os.environ.get("RECO_IMAP_SUBJECT") or "").strip(),
        "since_days": int(os.environ.get("RECO_IMAP_SINCE_DAYS") or 3),
        "daily_enabled": (os.environ.get("RECO_DAILY_ENABLED") or "").lower() in {"1", "true", "yes", "y"},
        "daily_hour": int(os.environ.get("RECO_DAILY_HOUR") or 6),
        "daily_minute": int(os.environ.get("RECO_DAILY_MINUTE") or 30),
    }


def _is_configured(cfg: Dict[str, Any]) -> bool:
    if not (cfg["host"] and cfg["user"]):
        return False
    if cfg["auth"] == "xoauth2":
        return bool(cfg["oauth_tenant"] and cfg["oauth_client_id"] and cfg["oauth_client_secret"])
    return bool(cfg["password"])


def _config_public(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Config view safe to send to the UI (no secrets)."""
    return {
        "configured": _is_configured(cfg),
        "auth": cfg["auth"],
        "host": cfg["host"] or None,
        "port": cfg["port"],
        "user": cfg["user"] or None,
        "folder": cfg["folder"],
        "sender": cfg["sender"] or None,
        "subject": cfg["subject"] or None,
        "since_days": cfg["since_days"],
        "daily_enabled": cfg["daily_enabled"],
        "daily_time_ist": f"{cfg['daily_hour']:02d}:{cfg['daily_minute']:02d}",
    }


def _m365_access_token(cfg: Dict[str, Any]) -> str:
    """Client-credentials token for IMAP XOAUTH2 against Microsoft 365."""
    url = f"https://login.microsoftonline.com/{cfg['oauth_tenant']}/oauth2/v2.0/token"
    resp = requests.post(url, data={
        "client_id": cfg["oauth_client_id"],
        "client_secret": cfg["oauth_client_secret"],
        "scope": "https://outlook.office365.com/.default",
        "grant_type": "client_credentials",
    }, timeout=30)
    if resp.status_code != 200:
        raise ValueError(f"OAuth2 token request failed ({resp.status_code}): {resp.text[:200]}")
    return resp.json()["access_token"]


def _decode(s: Optional[str]) -> str:
    if not s:
        return ""
    out = []
    for part, enc in decode_header(s):
        if isinstance(part, bytes):
            try:
                out.append(part.decode(enc or "utf-8", "ignore"))
            except Exception:
                out.append(part.decode("utf-8", "ignore"))
        else:
            out.append(part)
    return "".join(out)


def _fetch_latest_reco_blocking(cfg: Dict[str, Any]) -> Tuple[str, bytes]:
    """Connect over IMAP and return (filename, bytes) of the newest Reco attachment.

    Blocking (imaplib) — always call via asyncio.to_thread.
    """
    if not _is_configured(cfg):
        raise ValueError(
            "Email auto-pull is not configured. For basic auth set RECO_IMAP_HOST, "
            "RECO_IMAP_USER and RECO_IMAP_PASSWORD; for Microsoft 365 OAuth2 set "
            "RECO_IMAP_AUTH=xoauth2 with RECO_OAUTH_TENANT_ID / RECO_OAUTH_CLIENT_ID / "
            "RECO_OAUTH_CLIENT_SECRET (plus RECO_IMAP_USER = mailbox address)."
        )
    ctx = ssl.create_default_context()
    imap = imaplib.IMAP4_SSL(cfg["host"], cfg["port"], ssl_context=ctx)
    try:
        if cfg["auth"] == "xoauth2":
            token = _m365_access_token(cfg)
            auth_str = f"user={cfg['user']}\x01auth=Bearer {token}\x01\x01"
            imap.authenticate("XOAUTH2", lambda _: auth_str.encode())
        else:
            imap.login(cfg["user"], cfg["password"])
        imap.select(cfg["folder"], readonly=True)
        since = (datetime.now(timezone.utc) - timedelta(days=max(cfg["since_days"], 1))).strftime("%d-%b-%Y")
        criteria: List[str] = ["SINCE", since]
        if cfg["sender"]:
            criteria += ["FROM", cfg["sender"]]
        if cfg["subject"]:
            criteria += ["SUBJECT", cfg["subject"]]
        typ, data = imap.search(None, *criteria)
        if typ != "OK" or not data or not data[0]:
            raise ValueError(f"No Reco emails found in '{cfg['folder']}' since {since} "
                             f"(sender={cfg['sender'] or 'any'}, subject={cfg['subject'] or 'any'}).")
        ids = data[0].split()
        # newest first
        for msg_id in reversed(ids):
            typ, msg_data = imap.fetch(msg_id, "(RFC822)")
            if typ != "OK" or not msg_data:
                continue
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            for part in msg.walk():
                if part.get_content_maintype() == "multipart":
                    continue
                if not part.get("Content-Disposition"):
                    continue
                fname = _decode(part.get_filename())
                if fname and fname.lower().endswith(ATTACH_EXTS):
                    payload = part.get_payload(decode=True)
                    if payload:
                        return fname, payload
        raise ValueError("Reco email(s) found but none carried a CSV/XLSX attachment.")
    finally:
        try:
            imap.logout()
        except Exception:
            pass


# ── Ingest core (add only missing bills) ──────────────────────────────────────
DUP_REASON = "Duplicate (skip mode)"


async def _create_reco_run(filename: str, source: str, actor: str) -> Tuple[str, str]:
    """Create the job + run records (status running) and return (run_id, job_id)."""
    job_id = uuid.uuid4().hex
    run_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    await historic_jobs_col.insert_one({
        "id": job_id, "dataset": "transactions", "filename": filename,
        "duplicate_mode": "skip", "dry_run": False, "status": "queued",
        "processed": 0, "inserted": 0, "updated": 0, "skipped": 0,
        "errors_count": 0, "errors_sample": [], "queued_at": now,
        "queued_by": actor, "source": "reco",
    })
    await reco_runs_col.insert_one({
        "id": run_id, "job_id": job_id, "source": source, "filename": filename,
        "status": "running", "started_at": now, "actor": actor,
        "added": 0, "skipped_existing": 0, "errors": 0, "error_samples": [],
    })
    return run_id, job_id


async def _do_reco_ingest(run_id: str, job_id: str, csv_text: str) -> Dict[str, Any]:
    """Run the transaction ingest in SKIP mode (only missing bills added) and finalise
    the run — separating expected duplicate-skips from genuine row errors."""
    try:
        await _run_ingest_job(job_id, "transactions", csv_text, "skip", False)
        job = await historic_jobs_col.find_one({"id": job_id}, {"_id": 0}) or {}
        skipped_rows_col = db["historic_skipped_rows"]
        dup = await skipped_rows_col.count_documents({"job_id": job_id, "reason": DUP_REASON})
        total_skipped = int(job.get("skipped", 0) or 0)
        real_errors = max(total_skipped - dup, 0)
        samples = await skipped_rows_col.find(
            {"job_id": job_id, "reason": {"$ne": DUP_REASON}},
            {"_id": 0, "row_number": 1, "reason": 1}).limit(5).to_list(5)
        summary = {
            "status": "done",
            "added": int(job.get("inserted", 0) or 0),
            "skipped_existing": dup,
            "errors": real_errors,
            "error_samples": samples,
            "processed": int(job.get("processed", 0) or 0),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:  # pragma: no cover
        logger.exception("Reco ingest failed")
        summary = {"status": "error", "error": str(e),
                   "finished_at": datetime.now(timezone.utc).isoformat()}
    await reco_runs_col.update_one({"id": run_id}, {"$set": summary})
    return await reco_runs_col.find_one({"id": run_id}, {"_id": 0})


async def _ingest_reco_text(csv_text: str, filename: str, source: str, actor: str) -> Dict[str, Any]:
    """Awaited end-to-end ingest (used by the scheduler)."""
    run_id, job_id = await _create_reco_run(filename, source, actor)
    return await _do_reco_ingest(run_id, job_id, csv_text)


# ── Endpoints ─────────────────────────────────────────────────────────────────
def _require_mgmt(user: dict):
    if user["role"] not in MANAGEMENT_ROLES:
        raise HTTPException(403, "Only admin / CRM / marketing can run Reco ingestion")


@router.get("/status")
async def reco_status(user: dict = Depends(get_current_user)):
    _require_mgmt(user)
    runs = await reco_runs_col.find({}, {"_id": 0}).sort("started_at", -1).to_list(30)
    return {"config": _config_public(_imap_config()), "runs": runs}


@router.post("/upload")
async def reco_upload(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Manually add missing bills from a Reco CSV/XLSX (idempotent — existing bills skipped).
    Ingest runs in the background; poll GET /reco/status for the result."""
    _require_mgmt(user)
    raw = await file.read()
    if len(raw) > MAX_FILE_BYTES:
        raise HTTPException(413, f"File too large (max {MAX_FILE_BYTES // (1024*1024)} MB)")
    try:
        text = _read_upload_to_csv_text(file.filename, raw)
    except Exception as e:
        raise HTTPException(400, f"Could not read file: {e}")
    run_id, job_id = await _create_reco_run(file.filename or "reco.csv", "manual_upload", user["email"])
    asyncio.create_task(_do_reco_ingest(run_id, job_id, text))
    return await reco_runs_col.find_one({"id": run_id}, {"_id": 0})


@router.post("/run-email")
async def reco_run_email(user: dict = Depends(get_current_user)):
    """Pull the latest Reco attachment from the configured mailbox and ingest missing bills.
    Ingest runs in the background; poll GET /reco/status for the result."""
    _require_mgmt(user)
    cfg = _imap_config()
    try:
        fname, raw = await asyncio.to_thread(_fetch_latest_reco_blocking, cfg)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except (imaplib.IMAP4.error, ssl.SSLError, OSError) as e:
        raise HTTPException(502, f"Could not reach the mailbox: {e}")
    text = _read_upload_to_csv_text(fname, raw)
    run_id, job_id = await _create_reco_run(fname, "email_manual", user["email"])
    asyncio.create_task(_do_reco_ingest(run_id, job_id, text))
    return await reco_runs_col.find_one({"id": run_id}, {"_id": 0})


# ── Scheduler entry point (imported by scheduler.py) ──────────────────────────
async def reco_daily_job():
    """Daily: pull the newest Reco file from email and add only the missing bills.
    No-op (logged) unless RECO_DAILY_ENABLED and IMAP config are set."""
    cfg = _imap_config()
    if not cfg["daily_enabled"]:
        logger.info("reco_daily_job skipped — RECO_DAILY_ENABLED is off")
        return
    if not _is_configured(cfg):
        logger.warning("reco_daily_job skipped — IMAP/OAuth config incomplete")
        return
    try:
        fname, raw = await asyncio.to_thread(_fetch_latest_reco_blocking, cfg)
        text = _read_upload_to_csv_text(fname, raw)
        res = await _ingest_reco_text(text, fname, "email_daily", "scheduler")
        logger.info("reco_daily_job ingested %s: added=%s skipped=%s",
                    fname, res.get("added"), res.get("skipped_existing"))
    except Exception:
        logger.exception("reco_daily_job failed")
