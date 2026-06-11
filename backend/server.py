"""KAZO Fundle Platform - Main FastAPI server."""
from fastapi import FastAPI, APIRouter, Request
from fastapi.responses import JSONResponse, Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import os
import logging
import time
import json
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Optional
from pathlib import Path

import jwt as _jwt

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from routes.auth_routes import router as auth_router
from routes.users_routes import router as users_router
from routes.dashboard_routes import router as dashboard_router
from routes.customers_routes import router as customers_router
from routes.loyalty_routes import router as loyalty_router
from routes.coupons_routes import router as coupons_router
from routes.campaigns_routes import router as campaigns_router
from routes.ai_routes import router as ai_router
from routes.api_monitor_routes import router as api_monitor_router
from routes.stores_routes import router as stores_router, pos_router
from routes.nps_routes import router as nps_router
from routes.tickets_routes import router as tickets_router
from routes.reports_routes import router as reports_router
from routes.public_routes import router as public_router
from routes.items_routes import router as items_router
from routes.cms_routes import router as cms_router
from routes.analytics_routes import router as analytics_router
from routes.drilldown_routes import router as drilldown_router
from routes.fundlebrain_routes import router as fundlebrain_router
from routes.communications_routes import router as communications_router
from routes.historic_routes import router as historic_router
from routes.recon_routes import router as recon_router
from routes.pos_ewards_routes import router as pos_ewards_router, bootstrap_pos_defaults
from routes.live_monitor_routes import router as live_monitor_router, admin_router as pos_creds_router, log_router as api_log_detail_router
from routes.segments_routes import router as segments_router
from routes.cohort_library import router as cohort_library_router
from routes.auto_campaigns_routes import router as auto_campaigns_router
from routes.raw_reports_routes import router as raw_reports_router
from routes.support_desk_routes import router as support_desk_router
from routes.legacy_reports_routes import router as legacy_reports_router
from routes.demo_routes import router as demo_router

app = FastAPI(title="KAZO Fundle Platform", version="1.0.0")
api_router = APIRouter(prefix="/api")


@api_router.get("/")
async def root():
    return {
        "platform": "KAZO Fundle Platform",
        "powered_by": "Fundle",
        "brand": os.environ.get("BRAND_NAME", "Kazo"),
        "status": "operational",
    }


@api_router.get("/health")
async def health():
    return {"status": "ok", "service": "kazo-fundle-api"}


# Mount all routers
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(dashboard_router)
api_router.include_router(customers_router)
api_router.include_router(loyalty_router)
api_router.include_router(coupons_router)
api_router.include_router(campaigns_router)
api_router.include_router(ai_router)
api_router.include_router(api_monitor_router)
api_router.include_router(stores_router)
api_router.include_router(pos_router)
api_router.include_router(nps_router)
api_router.include_router(tickets_router)
api_router.include_router(reports_router)
api_router.include_router(public_router)
api_router.include_router(items_router)
api_router.include_router(cms_router)
api_router.include_router(analytics_router)
api_router.include_router(drilldown_router)
api_router.include_router(fundlebrain_router)
api_router.include_router(communications_router)
api_router.include_router(historic_router)
api_router.include_router(pos_ewards_router)
api_router.include_router(live_monitor_router)
api_router.include_router(pos_creds_router)
api_router.include_router(api_log_detail_router)
api_router.include_router(segments_router)
api_router.include_router(cohort_library_router)
api_router.include_router(auto_campaigns_router)
api_router.include_router(raw_reports_router)
api_router.include_router(support_desk_router)
api_router.include_router(legacy_reports_router)
api_router.include_router(recon_router)
api_router.include_router(demo_router)

app.include_router(api_router)

# CORS — must allow specific origins (NOT '*') because frontend sends credentials.
# Combine explicit env list with a permissive regex covering custom + emergent domains.
_env_origins = [o.strip() for o in os.environ.get('CORS_ORIGINS', '').split(',') if o.strip() and o.strip() != '*']
_default_origins = [
    "https://kazoloyalty.fundlebrain.ai",
    "https://kazo-loyalty-hub.emergent.host",
    "https://kazo-data-platform.preview.emergentagent.com",
    "http://localhost:3000",
]
_allowed_origins = list({*_env_origins, *_default_origins})
_origin_regex = os.environ.get(
    'CORS_ORIGIN_REGEX',
    r"https?://(.*\.)?(fundlebrain\.ai|emergent\.host|emergentagent\.com|localhost(:\d+)?)$",
)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=_allowed_origins,
    allow_origin_regex=_origin_regex,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────────────────────────────
#  API Logging Middleware
#  ----------------------------------------------------------------------
#  Captures every /api/* request (request + response payload, status,
#  duration, actor) into the `api_logs` collection so the Live API
#  Monitor shows full traffic — not just POS calls.
#
#  Skipped:
#    /api/pos/*          — self-logs with richer fields (api_key_label,
#                          customer_mobile, bill_number) via _log_api()
#    /api/api-monitor/*  — would create a feedback loop (monitor polls
#                          itself every 5s)
#    /api/live-monitor/* — 3-second auto-refresh, would flood logs
#    /api/auth/me        — token refresh ping
#    /api/health, /api/  — health checks
#    OPTIONS             — CORS preflight (no useful info)
#
#  Truncation: request and response payloads capped at 50KB each.
#  Streaming responses (CSV/XLSX/PDF exports, octet-stream) are NOT
#  consumed so downloads still stream correctly to the client.
#
#  Failures in logging itself NEVER affect the request — wrapped in
#  asyncio.create_task + try/except so client always gets its response.
# ──────────────────────────────────────────────────────────────────────
_LOG_SKIP_PREFIXES = (
    "/api/pos/",
    "/api/api-monitor",
    "/api/live-monitor",
    "/api/auth/me",
    "/api/health",
)
_LOG_MAX_BYTES = 50_000
_LOG_STREAMING_HINTS = ("text/csv", "application/pdf", "spreadsheetml",
                        "octet-stream", "application/zip")


def _decode_actor_email(request: Request) -> Optional[str]:
    """Best-effort decode of the JWT to get the actor's email. Never raises."""
    token = request.cookies.get("kazo_token")
    if not token:
        auth_h = request.headers.get("authorization", "")
        if auth_h.lower().startswith("bearer "):
            token = auth_h[7:]
    if not token:
        return None
    try:
        payload = _jwt.decode(
            token,
            os.environ["JWT_SECRET"],
            algorithms=[os.environ.get("JWT_ALGORITHM", "HS256")],
        )
        return payload.get("email") or payload.get("sub")
    except Exception:
        return None


def _decode_body(raw: bytes):
    """Try JSON first, then plain text. Returns truncation marker if too large."""
    if not raw:
        return None
    if len(raw) > _LOG_MAX_BYTES:
        return {"_truncated": True, "size_bytes": len(raw)}
    try:
        return json.loads(raw)
    except Exception:
        try:
            return raw.decode("utf-8", errors="replace")
        except Exception:
            return {"_binary": True, "size_bytes": len(raw)}


async def _persist_api_log(doc: dict):
    """Fire-and-forget insert. Wrapped in try/except so logging failure
    never crashes the request."""
    try:
        from database import api_logs_col
        await api_logs_col.insert_one(doc)
    except Exception as e:
        logging.getLogger("kazo-fundle").debug(f"api_logs insert failed: {e}")


class APILogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method

        # Fast-path: skip non-API, OPTIONS, and noisy/self-logging routes
        if (
            method == "OPTIONS"
            or not path.startswith("/api/")
            or any(path.startswith(p) for p in _LOG_SKIP_PREFIXES)
        ):
            return await call_next(request)

        # Capture request body (and re-inject so downstream can still read it)
        raw_req = b""
        try:
            raw_req = await request.body()
            if raw_req:
                async def _receive():
                    return {"type": "http.request", "body": raw_req, "more_body": False}
                request._receive = _receive
        except Exception:
            raw_req = b""

        start = time.perf_counter()
        actor_email = _decode_actor_email(request)
        actor_ip = request.client.host if request.client else None
        error_reason: Optional[str] = None
        response: Optional[Response] = None

        try:
            response = await call_next(request)
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            error_reason = f"{type(e).__name__}: {str(e)[:300]}"
            asyncio.create_task(_persist_api_log({
                "id": uuid.uuid4().hex,
                "endpoint": path,
                "method": method,
                "status_code": 500,
                "response_time_ms": elapsed_ms,
                "customer_mobile": None,
                "bill_number": None,
                "store_id": None,
                "error_reason": error_reason,
                "request_payload": _decode_body(raw_req),
                "response_payload": None,
                "api_key_label": actor_email,
                "actor_ip": actor_ip,
                "source": "internal",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }))
            raise

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        # Capture response body — but skip streaming downloads to avoid
        # blowing memory on large CSV/XLSX exports.
        content_type = response.headers.get("content-type", "").lower()
        is_streaming = any(h in content_type for h in _LOG_STREAMING_HINTS)

        response_body_decoded = None
        if is_streaming:
            response_body_decoded = {
                "_streamed": True,
                "content_type": content_type,
            }
        else:
            try:
                chunks = []
                async for chunk in response.body_iterator:
                    chunks.append(chunk)
                full = b"".join(chunks)
                response_body_decoded = _decode_body(full)
                # Re-emit response so the client still receives the body
                response = Response(
                    content=full,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )
            except Exception as e:
                error_reason = f"log_response_read_failed: {type(e).__name__}"

        if response.status_code >= 400 and not error_reason:
            # surface the response's `detail` field as the error_reason for grid display
            if isinstance(response_body_decoded, dict):
                d = response_body_decoded.get("detail")
                if d:
                    error_reason = str(d)[:300]

        asyncio.create_task(_persist_api_log({
            "id": uuid.uuid4().hex,
            "endpoint": path,
            "method": method,
            "status_code": response.status_code,
            "response_time_ms": elapsed_ms,
            "customer_mobile": None,
            "bill_number": None,
            "store_id": None,
            "error_reason": error_reason,
            "request_payload": _decode_body(raw_req),
            "response_payload": response_body_decoded,
            "api_key_label": actor_email,
            "actor_ip": actor_ip,
            "source": "internal",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }))

        return response


app.add_middleware(APILogMiddleware)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("kazo-fundle")


async def ensure_indexes():
    """Create all hot-path indexes (idempotent, safe to re-run).

    Without these, every dashboard aggregation collection-scans the
    transactions / customers / points_ledger collections (1M+ docs each after
    the historic load) and the skip-mode CRM ingest does an unindexed
    find_one({mobile}) per row — i.e. dashboards "take a million years" / never
    open. Runs as a background task on startup so it never delays readiness.
    """
    from database import (
        transactions_col, customers_col, points_ledger_col,
        coupon_redemptions_col, nps_col, db,
    )
    plans = [
        # transactions — the hot dashboard dimensions (bill_date / bill_number
        # already indexed by bootstrap_pos_defaults)
        (transactions_col, [("store_id", 1), ("bill_date", -1)], {"name": "ix_txn_store_billdate"}),
        (transactions_col, [("customer_mobile", 1), ("bill_date", -1)], {"name": "ix_txn_mobile_billdate"}),
        (transactions_col, [("is_return", 1)], {"name": "ix_txn_is_return"}),
        # transaction_id powers the SKU line-item attach ($or with bill_number).
        # Without it that post-pass does a COLLSCAN per bill (O(n²)) and never
        # finishes on a 1M-line file — pegging the DB and 500-ing dashboards.
        (transactions_col, [("transaction_id", 1)], {"name": "ix_txn_transaction_id"}),
        # customers — segmentation / analytics dimensions
        (customers_col, [("tier", 1)], {"name": "ix_cust_tier"}),
        (customers_col, [("home_store_id", 1)], {"name": "ix_cust_home_store"}),
        (customers_col, [("last_visit_at", -1)], {"name": "ix_cust_last_visit"}),
        (customers_col, [("first_purchase_at", 1)], {"name": "ix_cust_first_purchase"}),
        (customers_col, [("lifetime_spend", -1)], {"name": "ix_cust_lifetime_spend"}),
        (customers_col, [("city", 1)], {"name": "ix_cust_city"}),
        (customers_col, [("created_at", -1)], {"name": "ix_cust_created"}),
        (customers_col, [("visit_count", -1)], {"name": "ix_cust_visit_count"}),
        # ingest_job_id — the customer post-pass (opening-balance ledger) finds all
        # rows loaded by a job; without this it COLLSCANs 1M+ customers each load.
        (customers_col, [("ingest_job_id", 1)], {"name": "ix_cust_ingest_job"}),
        # points ledger — economics / expiry
        (points_ledger_col, [("customer_mobile", 1)], {"name": "ix_pl_mobile"}),
        (points_ledger_col, [("type", 1), ("expires_at", 1)], {"name": "ix_pl_type_expiry"}),
        (points_ledger_col, [("created_at", -1)], {"name": "ix_pl_created"}),
        (points_ledger_col, [("source_bill_id", 1)], {"name": "ix_pl_bill"}),
        # opening-balance post-pass upserts keyed on (customer_mobile, reference_type);
        # this makes each of the ~1M upserts an index hit instead of a scan.
        (points_ledger_col, [("customer_mobile", 1), ("reference_type", 1)], {"name": "ix_pl_mobile_reftype"}),
        # small collections
        (coupon_redemptions_col, [("created_at", -1)], {"name": "ix_cr_created"}),
        (nps_col, [("created_at", -1)], {"name": "ix_nps_created"}),
        # ledger bill_date — KPI / loyalty-dashboard point-flow windows filter on it
        (points_ledger_col, [("bill_date", -1)], {"name": "ix_pl_bill_date"}),
        # message_log — communications history is sorted/filtered by created_at
        (db["message_log"], [("created_at", -1)], {"name": "ix_msg_created"}),
        # transactions city — city rollups group on it when store master is missing
        (transactions_col, [("city", 1)], {"name": "ix_txn_city"}),
        (transactions_col, [("store_name", 1)], {"name": "ix_txn_store_name"}),
        # api_logs — Command Center computes API health via count_documents on
        # timestamp (+status_code). Without this it COLLSCANs every logged API
        # call (millions of rows) and the count hangs under load. Compound covers
        # both the total-in-window and the failed-in-window counts.
        (db["api_logs"], [("timestamp", -1), ("status_code", 1)], {"name": "ix_apilog_ts_status"}),
        # chunk lookups for large historic uploads
        (db["historic_chunks"], [("job_id", 1), ("chunk_index", 1)], {"name": "ix_chunk_job_idx"}),
        (db["historic_ingest_jobs"], [("status", 1), ("queued_at", 1)], {"name": "ix_job_status_queued"}),
    ]
    created = 0
    for col, keys, opts in plans:
        try:
            await col.create_index(keys, **opts)
            created += 1
        except Exception as e:
            logger.warning(f"index {opts.get('name')} warn: {e}")
    # customers.mobile uniqueness constraint (partial: only string mobiles).
    try:
        await customers_col.create_index(
            [("mobile", 1)], unique=True,
            partialFilterExpression={"mobile": {"$type": "string"}},
            name="uniq_customer_mobile",
        )
        created += 1
    except Exception as e:
        logger.warning(f"unique mobile index warn: {e}")
    # CRITICAL PERF: a PARTIAL index canNOT serve a bare {mobile: <val>} equality
    # query — Mongo falls back to a COLLSCAN, so every customer UPSERT scanned the
    # WHOLE collection (~1k ops/s, getting worse as it grows → the multi-lakh CRM
    # load crawled "500 by 500"). A plain non-unique index on mobile lets the
    # upsert existence-check use an IXSCAN (~20k ops/s, 20x faster). Uniqueness is
    # still enforced by uniq_customer_mobile above; this exists purely for lookups.
    try:
        await customers_col.create_index([("mobile", 1)], name="ix_cust_mobile_lookup")
        created += 1
    except Exception as e:
        logger.warning(f"mobile lookup index warn: {e}")
    logger.info(f"ensure_indexes complete — {created} indexes ensured")



@app.on_event("startup")
async def startup():
    from database import users_col, stores_col, loyalty_config_col
    from routes.loyalty_routes import DEFAULT_CONFIG
    from auth import hash_password
    from datetime import datetime, timezone
    import uuid

    # Seed super admin if not exists
    super_admin = await users_col.find_one({"email": os.environ.get("SUPER_ADMIN_EMAIL", "superadmin@fundle.io").lower()})
    if not super_admin:
        await users_col.insert_one({
            "id": uuid.uuid4().hex,
            "email": os.environ.get("SUPER_ADMIN_EMAIL", "superadmin@fundle.io").lower(),
            "name": "Fundle Super Admin",
            "role": "super_admin",
            "password_hash": hash_password(os.environ.get("SUPER_ADMIN_PASSWORD", "Fundle@2026")),
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("Seeded super admin")

    # Seed brand admin
    brand_admin = await users_col.find_one({"email": os.environ.get("BRAND_ADMIN_EMAIL", "admin@kazo.com").lower()})
    if not brand_admin:
        await users_col.insert_one({
            "id": uuid.uuid4().hex,
            "email": os.environ.get("BRAND_ADMIN_EMAIL", "admin@kazo.com").lower(),
            "name": "Kazo Brand Admin",
            "role": "brand_admin",
            "password_hash": hash_password(os.environ.get("BRAND_ADMIN_PASSWORD", "Kazo@2026")),
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("Seeded brand admin")

    # Backfill store_id on store-scoped users (security hardening for drilldown scope)
    store_user_map = {
        "store.mumbai@kazo.com": "Mumbai",
        "staff.delhi@kazo.com": "Delhi",
    }
    for email, city in store_user_map.items():
        u = await users_col.find_one({"email": email})
        if u and not u.get("store_id"):
            s = await stores_col.find_one({"city": city, "is_active": True})
            if s:
                await users_col.update_one(
                    {"email": email},
                    {"$set": {"store_id": s["id"]}},
                )
                logger.info(f"Backfilled store_id for {email} -> {s['code']}")

    # Seed all demo / operational users (idempotent — runs on every boot so
    # production deployments with a fresh DB always have working logins).
    demo_users = [
        ("crm@kazo.com", "Priya Sharma", "crm_manager", None),
        ("marketing@kazo.com", "Rohan Kapoor", "marketing_manager", None),
        ("regional.north@kazo.com", "Anjali Verma", "regional_manager", None),
        ("store.mumbai@kazo.com", "Neha Patel", "store_manager", "Mumbai"),
        ("staff.delhi@kazo.com", "Karan Singh", "store_staff", "Delhi"),
        ("support@kazo.com", "Riya Mehra", "support_agent", None),
        ("analytics@kazo.com", "Aditya Rao", "analytics_viewer", None),
        ("executive@kazo.com", "Kavita Iyer", "readonly_executive", None),
        ("it@kazo.com", "Vikram Joshi", "brand_admin", None),
    ]
    for email, name, role, city in demo_users:
        if await users_col.find_one({"email": email}):
            continue
        doc = {
            "id": uuid.uuid4().hex,
            "email": email,
            "name": name,
            "role": role,
            "password_hash": hash_password("Kazo@2026"),
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if city:
            s = await stores_col.find_one({"city": city, "is_active": True})
            if s:
                doc["store_id"] = s["id"]
        await users_col.insert_one(doc)
        logger.info(f"Seeded demo user {email}")

    # Seed loyalty config
    cfg = await loyalty_config_col.find_one({"id": "default"})
    if not cfg:
        doc = dict(DEFAULT_CONFIG)
        doc["updated_at"] = datetime.now(timezone.utc).isoformat()
        await loyalty_config_col.insert_one(doc)
        logger.info("Seeded loyalty config")

    # Seed campaign_metrics (idempotent: derives per-channel funnel rows
    # from existing campaign aggregates so Campaign ROI v2 funnel populates)
    try:
        from seed_campaign_metrics import seed_campaign_metrics
        res = await seed_campaign_metrics()
        if res["rows_inserted"]:
            logger.info(f"Seeded campaign_metrics: {res}")
    except Exception as e:
        logger.warning(f"Could not seed campaign_metrics: {e}")

    # Start weekly executive-digest scheduler (Mon 09:00 IST)
    try:
        from scheduler import start_scheduler
        start_scheduler()
    except Exception as e:
        logger.warning(f"Could not start digest scheduler: {e}")

    # Bootstrap POS defaults (credentials + test customer 966681235 + test coupons)
    try:
        await bootstrap_pos_defaults()
    except Exception as e:
        logger.warning(f"Could not bootstrap POS defaults: {e}")

    # Ensure the read-only demo account exists (powers the public /demo guided tour)
    try:
        from routes.demo_routes import ensure_demo_user
        await ensure_demo_user()
    except Exception as e:
        logger.warning(f"Could not ensure demo user: {e}")

    # Build hot-path indexes in the background so dashboards over 1M+ rows stay
    # fast. Non-blocking: the app starts serving immediately while Mongo builds.
    try:
        asyncio.create_task(ensure_indexes())
    except Exception as e:
        logger.warning(f"Could not schedule ensure_indexes: {e}")

    # Keep the heaviest default dashboard views permanently warm so first
    # loads never hang for 10-20 s on production-scale aggregations.
    try:
        from routes._cache_warmer import warm_loop
        asyncio.create_task(warm_loop())
    except Exception as e:
        logger.warning(f"Could not schedule cache warmer: {e}")


@app.on_event("shutdown")
async def shutdown():
    try:
        from scheduler import stop_scheduler
        stop_scheduler()
    except Exception:
        pass
    from database import client
    client.close()
