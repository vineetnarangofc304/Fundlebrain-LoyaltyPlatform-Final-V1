"""Scheduled Executive Digest.

Generates a weekly PDF executive summary every Monday 9 AM IST and stores it
in MongoDB GridFS-style: small binary in `digest_reports` (cap to ~500 KB).
Frontend can list / download via `/api/reports/digests` and `/api/reports/digests/latest`.

No email transport is configured by default (user opted to keep PDFs in-app and
download from /reports/digests). Email can be wired in later via Resend/SMTP.
"""
import io
import uuid
import base64
import logging
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from database import db, users_col

logger = logging.getLogger("kazo-fundle.scheduler")

digest_reports_col = db["digest_reports"]
_scheduler: Optional[AsyncIOScheduler] = None


async def _build_and_store_digest(period_days: int = 7,
                                    triggered_by: str = "scheduler") -> dict:
    """Render the weekly PDF and persist to MongoDB."""
    from routes.fundlebrain_routes import _build_executive_summary_pdf_bytes
    # Use the brand admin as the "user" context (since digest is brand-wide)
    admin = await users_col.find_one(
        {"role": {"$in": ["brand_admin", "super_admin"]}},
        {"_id": 0, "id": 1, "email": 1, "role": 1, "store_id": 1},
    )
    if not admin:
        raise RuntimeError("No brand_admin/super_admin user found for digest context")

    pdf_buf: io.BytesIO = await _build_executive_summary_pdf_bytes(period_days, admin)
    pdf_bytes = pdf_buf.getvalue()
    if len(pdf_bytes) > 800_000:  # 800 KB safety cap
        raise RuntimeError(f"Digest PDF too large ({len(pdf_bytes)} bytes)")

    now = datetime.now(timezone.utc)
    doc = {
        "id": uuid.uuid4().hex,
        "period_days": period_days,
        "generated_at": now.isoformat(),
        "filename": f"KAZO_Executive_Digest_{now.strftime('%Y%m%d_%H%M')}.pdf",
        "size_bytes": len(pdf_bytes),
        "triggered_by": triggered_by,
        "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
    }
    await digest_reports_col.insert_one(doc)
    logger.info(f"Stored digest {doc['filename']} ({doc['size_bytes']} bytes, trigger={triggered_by})")
    # Return safe view (no _id, no base64)
    return {k: v for k, v in doc.items() if k not in ("_id", "pdf_base64")}


def start_scheduler():
    """Spin up the AsyncIOScheduler at FastAPI startup.

    Cron: every Monday at 09:00 Asia/Kolkata (IST).
    """
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    sched = AsyncIOScheduler(timezone="Asia/Kolkata")
    sched.add_job(_build_and_store_digest,
                   CronTrigger(day_of_week="mon", hour=9, minute=0, timezone="Asia/Kolkata"),
                   id="weekly_exec_digest",
                   replace_existing=True,
                   misfire_grace_time=3600,
                   kwargs={"period_days": 7, "triggered_by": "weekly_cron"})

    # Historic-data ingest worker — picks up pending CSV ingest jobs every 15s.
    # Resilient to pod restarts: jobs stay in MongoDB until completed.
    from routes.historic_routes import process_pending_ingests
    sched.add_job(process_pending_ingests,
                   IntervalTrigger(seconds=15),
                   id="historic_ingest_worker",
                   replace_existing=True,
                   max_instances=1,
                   coalesce=True,
                   misfire_grace_time=30)

    # Auto-Campaigns daily worker — fires birthday / win-back / abandoned-visit
    # rules every day at 10:00 IST (after KAZO opens).
    from routes.auto_campaigns_routes import run_all_auto_campaigns
    sched.add_job(run_all_auto_campaigns,
                   CronTrigger(hour=10, minute=0, timezone="Asia/Kolkata"),
                   id="auto_campaigns_daily",
                   replace_existing=True,
                   max_instances=1,
                   coalesce=True,
                   misfire_grace_time=3600)

    sched.start()
    _scheduler = sched
    logger.info("Started exec digest scheduler — next Mon 09:00 IST | historic ingest worker every 15s | auto-campaigns daily 10:00 IST")
    return sched


def stop_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
