"""KAZO Fundle Platform - Main FastAPI server."""
from fastapi import FastAPI, APIRouter, Request
from fastapi.responses import JSONResponse, Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.datastructures import Headers
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
import pymongo

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from db_logging import submit_log, start_log_writer

from routes.auth_routes import router as auth_router
from routes.users_routes import router as users_router
from routes.dashboard_routes import router as dashboard_router
from routes.customers_routes import router as customers_router
from routes.loyalty_routes import router as loyalty_router
from routes.coupons_routes import router as coupons_router
from routes.campaigns_routes import router as campaigns_router
from routes.marketing_db_routes import router as marketing_db_router
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
from routes.drilldown_routes import router as drilldown_router, export_router as drilldown_export_router
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
from routes.shopper_report_routes import router as shopper_report_router, export_router as shopper_report_export_router
from routes.reports_kpi_routes import router as kpi_reports_router, export_router as kpi_reports_export_router
from routes.kpi_matrix_routes import router as kpi_matrix_router, export_router as kpi_matrix_export_router
from routes.bops_reports_routes import router as bops_reports_router, export_router as bops_reports_export_router
from routes.points_integrity_routes import router as points_integrity_router
from routes.store_logins_routes import router as store_logins_router
from routes.exports_routes import router as exports_router
from routes.demo_routes import router as demo_router
from routes.watch_routes import router as watch_router
from routes.reel_routes import router as reel_router
from routes.reco_routes import router as reco_router
from routes.master_brain_routes import router as master_brain_router

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
api_router.include_router(marketing_db_router)
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
api_router.include_router(drilldown_export_router)
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
api_router.include_router(shopper_report_router)
api_router.include_router(shopper_report_export_router)
api_router.include_router(kpi_reports_router)
api_router.include_router(kpi_reports_export_router)
api_router.include_router(kpi_matrix_router)
api_router.include_router(kpi_matrix_export_router)
api_router.include_router(bops_reports_router)
api_router.include_router(bops_reports_export_router)
api_router.include_router(points_integrity_router)
api_router.include_router(store_logins_router)
api_router.include_router(exports_router)
api_router.include_router(recon_router)
api_router.include_router(demo_router)
api_router.include_router(watch_router)
api_router.include_router(reel_router)
api_router.include_router(reco_router)
api_router.include_router(master_brain_router)

app.include_router(api_router)


# ---------------------------------------------------------------------------
# Global unhandled-exception handler.
# Starlette's default 500 returns a PLAIN-TEXT body ("Internal Server Error"),
# which a JSON client (e.g. the eWards .NET POS) cannot parse → it raises
# "The data does not represent a valid JSON token." This handler guarantees a
# JSON body on every unhandled error: for POS routes it returns the eWards
# envelope (HTTP 200 + {status_code, response}) so the till shows a clean
# message instead of crashing; for all other routes it returns {detail} JSON.
# The real traceback is logged to both the server log and the API Monitor.
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    import traceback as _tb
    tb = _tb.format_exc()
    path = request.url.path
    logging.getLogger("kazo-fundle").error("Unhandled error on %s %s: %s\n%s",
                                            request.method, path, exc, tb)
    is_pos = path.startswith("/api/pos")
    if is_pos:
        # Record in the API Monitor so admins can self-diagnose the real cause.
        try:
            submit_log({
                "id": uuid.uuid4().hex,
                "endpoint": path,
                "method": request.method,
                "status_code": 500,
                "response_time_ms": 0,
                "error_reason": f"unhandled_exception: {type(exc).__name__}: {exc}",
                "traceback": tb[-4000:],
                "source": "pos_ewards",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            pass
        # eWards contract: HTTP 200 with the error surfaced inside the envelope.
        return JSONResponse(
            status_code=200,
            content={"status_code": 500,
                     "response": {"message": "Internal error while processing the request. "
                                             "Please retry; if it persists contact Fundle support."}},
        )
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


# CORS — must allow specific origins (NOT '*') because frontend sends credentials.
# Combine explicit env list with a permissive regex covering custom + emergent domains.
_env_origins = [o.strip() for o in os.environ.get('CORS_ORIGINS', '').split(',') if o.strip() and o.strip() != '*']
_default_origins = [
    "https://kazoloyalty.fundlebrain.ai",
    "https://kazo-loyalty-hub.emergent.host",
    "https://kazo-loyalty-hub-2.preview.emergentagent.com",
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
# Generous per-request DB deadline for the LIVE POS billing path. It OVERRIDES the
# aggressive production Atlas client timeoutMS (~10s) via pymongo CSOT, so when the
# cluster is momentarily slow under peak store load a live bill WAITS a little instead
# of dying with `NetworkTimeout: read operation timed out` (the till "Working on it…"
# hang). Master Brain already does the same for its bulk ops.
POS_DB_DEADLINE_SEC = float(os.environ.get("POS_DB_DEADLINE_SEC", "30"))
_LOG_STREAMING_HINTS = ("text/csv", "application/pdf", "spreadsheetml",
                        "octet-stream", "application/zip", "text/event-stream")


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


class APILogMiddleware:
    """Pure-ASGI request/response logger for the API monitor.

    Implemented as a raw ASGI middleware (NOT BaseHTTPMiddleware) on purpose.
    BaseHTTPMiddleware buffers the request in a _CachedRequest and then replays the
    buffered `http.request` message to the response's listen_for_disconnect(); for
    StreamingResponse / FileResponse that raises
    `RuntimeError: Unexpected message received: http.request` and truncates the streamed
    body to EMPTY — which made every CSV / XLSX / PDF export (segments audience export,
    recon mismatch CSV, AI exports) come back 0 bytes / "Internal Server Error". A
    pure-ASGI middleware wraps receive/send without ever touching the disconnect channel,
    so streaming downloads pass straight through."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "")
        # LIVE POS billing path: wrap the whole request in a generous pymongo CSOT deadline
        # so slow-but-alive Atlas responses under peak load delay a bill instead of failing
        # it with NetworkTimeout. (POS is skip-logged anyway; it self-logs via _log_api.)
        if method != "OPTIONS" and path.startswith("/api/pos/"):
            with pymongo.timeout(POS_DB_DEADLINE_SEC):
                await self.app(scope, receive, send)
            return
        if (
            method == "OPTIONS"
            or not path.startswith("/api/")
            or any(path.startswith(p) for p in _LOG_SKIP_PREFIXES)
        ):
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        req_chunks: list = []
        req_len = 0

        async def recv_wrapper():
            nonlocal req_len
            message = await receive()
            if message.get("type") == "http.request":
                body = message.get("body", b"")
                if body and req_len <= _LOG_MAX_BYTES:
                    req_chunks.append(body)
                    req_len += len(body)
            return message

        state = {"status": 500, "streaming": False, "content_type": "", "resp_len": 0}
        resp_chunks: list = []

        async def send_wrapper(message):
            mtype = message.get("type")
            if mtype == "http.response.start":
                state["status"] = message.get("status", 200)
                headers = Headers(raw=message.get("headers", []))
                state["content_type"] = headers.get("content-type", "").lower()
                state["streaming"] = any(h in state["content_type"] for h in _LOG_STREAMING_HINTS)
            elif mtype == "http.response.body" and not state["streaming"]:
                body = message.get("body", b"")
                if body and state["resp_len"] <= _LOG_MAX_BYTES:
                    resp_chunks.append(body)
                    state["resp_len"] += len(body)
            await send(message)

        _req = Request(scope)  # header/cookie access only (no receive consumed)
        actor_email = _decode_actor_email(_req)
        actor_ip = scope["client"][0] if scope.get("client") else None

        try:
            await self.app(scope, recv_wrapper, send_wrapper)
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            submit_log({
                "id": uuid.uuid4().hex, "endpoint": path, "method": method,
                "status_code": 500, "response_time_ms": elapsed_ms,
                "customer_mobile": None, "bill_number": None, "store_id": None,
                "error_reason": f"{type(e).__name__}: {str(e)[:300]}",
                "request_payload": _decode_body(b"".join(req_chunks)),
                "response_payload": None, "api_key_label": actor_email,
                "actor_ip": actor_ip, "source": "internal",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            raise

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        if state["streaming"]:
            response_body_decoded = {"_streamed": True, "content_type": state["content_type"]}
        else:
            response_body_decoded = _decode_body(b"".join(resp_chunks))

        error_reason = None
        if state["status"] >= 400 and isinstance(response_body_decoded, dict):
            d = response_body_decoded.get("detail")
            if d:
                error_reason = str(d)[:300]

        submit_log({
            "id": uuid.uuid4().hex, "endpoint": path, "method": method,
            "status_code": state["status"], "response_time_ms": elapsed_ms,
            "customer_mobile": None, "bill_number": None, "store_id": None,
            "error_reason": error_reason,
            "request_payload": _decode_body(b"".join(req_chunks)),
            "response_payload": response_body_decoded, "api_key_label": actor_email,
            "actor_ip": actor_ip, "source": "internal",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


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
        # COVERING index for the system-wide ATV / loyalty-sum aggregate
        # (cohort-library build_context + any $sum net_amount over all loyalty bills).
        # The $match {customer_mobile: {$nin: [None, ""]}} + $group {net: $sum net_amount,
        # bills: $sum 1} was doing an IXSCAN then FETCHing every matched doc (~766K rows /
        # ~788MB) just to read net_amount, blowing past the 30s Mongo op timeout under
        # cache-warmer + dashboard load and 500-ing the endpoint. With net_amount in the
        # index the aggregate is fully covered (PROJECTION_COVERED, no FETCH) — verified via
        # explain. Purely additive; no query or behaviour change.
        (transactions_col, [("customer_mobile", 1), ("net_amount", 1)], {"name": "ix_txn_mobile_net"}),
        (transactions_col, [("is_return", 1)], {"name": "ix_txn_is_return"}),
        # points_redeemed (partial, >0 only) — the missing-redemption audit/repair scans
        # "bills that recorded a redemption". Without this it COLLSCANs 1.5M+ transactions and
        # times out (Master Brain "can't do it"); the partial index is tiny (only redemption bills).
        (transactions_col, [("points_redeemed", 1), ("bill_date", 1)],
         {"name": "ix_txn_redeemed_partial", "partialFilterExpression": {"points_redeemed": {"$gt": 0}}}),
        # transaction_id powers the SKU line-item attach ($or with bill_number).
        # Without it that post-pass does a COLLSCAN per bill (O(n²)) and never
        # finishes on a 1M-line file — pegging the DB and 500-ing dashboards.
        (transactions_col, [("transaction_id", 1)], {"name": "ix_txn_transaction_id"}),
        # id — the app's business PK. returnOrder, live-monitor recalc and every
        # drill-down query transactions by {id}; without this each is a COLLSCAN
        # of ~750K bills. IXSCAN makes it ~1ms.
        (transactions_col, [("id", 1)], {"name": "ix_txn_id"}),
        # customers — segmentation / analytics dimensions
        # id — the app's business PK. CRITICAL for the LIVE posAddPoint path:
        # _apply_bill_credit credits the balance via update_one({"id": cust_id}),
        # which WITHOUT this COLLSCANs ~940K customers on EVERY bill (15-30s under
        # 100+ concurrent stores -> request timeout -> the store's bill is LOST).
        # An IXSCAN makes it ~1ms. Also speeds every other {id} customer lookup
        # (returnOrder, customer detail, live monitor, Master Brain tools).
        (customers_col, [("id", 1)], {"name": "ix_cust_id"}),
        (customers_col, [("tier", 1)], {"name": "ix_cust_tier"}),
        (customers_col, [("home_store_id", 1)], {"name": "ix_cust_home_store"}),
        (customers_col, [("last_visit_at", -1)], {"name": "ix_cust_last_visit"}),
        (customers_col, [("first_purchase_at", 1)], {"name": "ix_cust_first_purchase"}),
        (customers_col, [("lifetime_spend", -1)], {"name": "ix_cust_lifetime_spend"}),
        (customers_col, [("city", 1)], {"name": "ix_cust_city"}),
        (customers_col, [("created_at", -1)], {"name": "ix_cust_created"}),
        (customers_col, [("visit_count", -1)], {"name": "ix_cust_visit_count"}),
        # points_balance — negative-balance / liability scans (Master Brain "customers with
        # negative points" question COLLSCANs 9L+ customers and times out without this).
        (customers_col, [("points_balance", 1)], {"name": "ix_cust_points_balance"}),
        # ingest_job_id — the customer post-pass (opening-balance ledger) finds all
        # rows loaded by a job; without this it COLLSCANs 1M+ customers each load.
        (customers_col, [("ingest_job_id", 1)], {"name": "ix_cust_ingest_job"}),
        # points ledger — economics / expiry
        (points_ledger_col, [("customer_mobile", 1)], {"name": "ix_pl_mobile"}),
        # (customer_mobile, created_at desc) — the Customer-360 detail view reads a
        # customer's last 30 ledger rows via find({customer_mobile}).sort(created_at,-1).
        # With only the mobile index, a heavy customer's rows were pulled then SORTED in
        # memory (slow). This compound serves the sorted-limit as an index-only walk (~1ms).
        (points_ledger_col, [("customer_mobile", 1), ("created_at", -1)], {"name": "ix_pl_mobile_created"}),
        (points_ledger_col, [("type", 1), ("expires_at", 1)], {"name": "ix_pl_type_expiry"}),
        # (type, reference_type) — Master Brain double-redemption repair scan filters on
        # type=redeem + reference_type=transaction; without this it COLLSCANs the full ledger.
        (points_ledger_col, [("type", 1), ("reference_type", 1)], {"name": "ix_pl_type_reftype"}),
        # bill_number — the LIVE posAddPoint credit path upserts the earn/bonus ledger rows
        # keyed on (bill_number, ledger_kind, type). Without this every upsert COLLSCANs the
        # multi-million-row ledger, making posAddPoint take 15-30s and time out. This makes each
        # upsert an index hit (~1ms). Also powers the partial-commit audit's bill_number lookup.
        (points_ledger_col, [("bill_number", 1), ("ledger_kind", 1), ("type", 1)], {"name": "ix_pl_billnumber_kind"}),
        # reference_id — the repair's legit-sibling lookup joins ledger rows by bill number.
        (points_ledger_col, [("reference_id", 1)], {"name": "ix_pl_reference_id"}),
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
    # Campaign Manager add-ons: unique coupon codes must be globally unique (POS looks up by code);
    # plus lookup indexes for unique coupons + marketing databases + coupon batches.
    try:
        await db["unique_coupons"].create_index([("code", 1)], unique=True, name="uniq_unique_coupon_code")
        await db["unique_coupons"].create_index([("batch_id", 1)], name="ix_unique_batch")
        await db["unique_coupons"].create_index([("mobile", 1)], name="ix_unique_mobile")
        await db["coupon_batches"].create_index([("id", 1)], unique=True, name="uniq_coupon_batch_id")
        await db["marketing_databases"].create_index([("id", 1)], unique=True, name="uniq_marketing_db_id")
        created += 5
    except Exception as e:
        logger.warning(f"campaign add-on index warn: {e}")
    logger.info(f"ensure_indexes complete — {created} indexes ensured")



async def _backfill_amount_paid(batch: int = 20000):
    """Fill the canonical `amount_paid` on every transaction missing it, in batches,
    on the deadline-free client. Idempotent — safe to run on every boot; it stops as
    soon as no un-backfilled bills remain. Lets ALL reports agree on the Total Paid
    figure even for historic bills loaded before the field existed."""
    from database import transactions_col
    from routes._money import PAID_COMPUTE
    total = 0
    try:
        while True:
            ids = await transactions_col.find(
                {"amount_paid": {"$exists": False}}, {"_id": 1}
            ).limit(batch).to_list(batch)
            if not ids:
                break
            id_list = [d["_id"] for d in ids]
            with pymongo.timeout(120):
                await transactions_col.update_many(
                    {"_id": {"$in": id_list}},
                    [{"$set": {"amount_paid": PAID_COMPUTE}}],
                )
            total += len(id_list)
            await asyncio.sleep(0.2)  # yield to the request loop between batches
        if total:
            logger.info(f"amount_paid backfill complete — {total} bills updated")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"amount_paid backfill stopped early ({total} done): {e}")



async def _seed_and_bootstrap():
    """ALL DB seeding / bootstrapping — run as a BACKGROUND task (never inline in the
    lifespan startup) so a transient Atlas 'no primary' (failover/maintenance) at deploy
    time can NEVER block or crash startup. The process must come up and answer /health
    immediately for the Kubernetes readiness probe, or the whole deployment times out and
    is killed. Every step is best-effort and never re-raises."""
    from database import users_col, stores_col, loyalty_config_col
    from routes.loyalty_routes import DEFAULT_CONFIG
    from auth import hash_password
    from datetime import datetime, timezone
    import uuid

    # Wait (with backoff) for a reachable/writable DB before seeding. Never raises —
    # if the DB is briefly unavailable at boot we simply retry; the app is already live.
    for attempt in range(1, 61):
        try:
            await users_col.find_one({}, {"_id": 1})
            break
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[seed] DB not reachable yet (attempt {attempt}): {e}")
            await asyncio.sleep(5)
    else:
        logger.error("[seed] DB never became reachable — seeding skipped this boot")
        return

    try:
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

        # Seed / ensure Master Brain accounts (idempotent; also backfills the flags on existing rows)
        mb_accounts = [
            ("masteradmin@fundle.io", "Master Admin", "crm_manager", "Master@2026",
             {"is_master_admin": True}),
            ("vineetnarangofc@fundle.io", "Vineet Narang", "crm_manager", "Vineet@2026",
             {"is_master_admin": True, "is_master_query_admin": True}),
        ]
        for email, name, role, pwd, flags in mb_accounts:
            existing_mb = await users_col.find_one({"email": email})
            if not existing_mb:
                await users_col.insert_one({
                    "id": uuid.uuid4().hex, "email": email, "name": name, "role": role,
                    "password_hash": hash_password(pwd), "is_active": True,
                    "created_at": datetime.now(timezone.utc).isoformat(), **flags,
                })
                logger.info(f"Seeded Master Brain account {email}")
            else:
                patch = {k: v for k, v in flags.items() if not existing_mb.get(k)}
                if patch:
                    await users_col.update_one({"email": email}, {"$set": patch})
                    logger.info(f"Backfilled flags for {email}: {patch}")

        # Seed loyalty config
        cfg = await loyalty_config_col.find_one({"id": "default"})
        if not cfg:
            doc = dict(DEFAULT_CONFIG)
            doc["updated_at"] = datetime.now(timezone.utc).isoformat()
            await loyalty_config_col.insert_one(doc)
            logger.info("Seeded loyalty config")
    except Exception as e:  # noqa: BLE001
        logger.error(f"[seed] core seeding error (continuing): {e}")

    # Seed campaign_metrics (idempotent)
    try:
        from seed_campaign_metrics import seed_campaign_metrics
        res = await seed_campaign_metrics()
        if res["rows_inserted"]:
            logger.info(f"Seeded campaign_metrics: {res}")
    except Exception as e:
        logger.warning(f"Could not seed campaign_metrics: {e}")

    # Bootstrap POS defaults (credentials + test customer + test coupons)
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

    # One-time seed of the DLT-approved "KAZO End of Season Sale" promotional SMS template so the
    # user can launch a real, deliverable campaign immediately after deploy. Idempotent + one-time
    # (a `seed_flags` marker) so if the user later edits/deletes it, it is NOT recreated on restart.
    try:
        from database import templates_col, db as _db
        seed_flags = _db["seed_flags"]
        already = await seed_flags.find_one({"_id": "kazo_eoss_template"})
        if not already:
            now_iso = datetime.now(timezone.utc).isoformat()
            await templates_col.insert_one({
                "id": uuid.uuid4().hex,
                "name": "KAZO End of Season Sale",
                "channel": "sms",
                "event_trigger": "campaign_bulk",
                "body": ("KAZO End of Season Sale is LIVE! Get up to 50% OFF on your favorite "
                         "styles. Shop now and refresh your wardrobe. T&C Apply."),
                "variables": [],
                "sender_id": "KAZOFN",
                "dlt_entity_id": "1101409540000012086",
                "dlt_template_id": "1107178315446496099",
                "dlt_tm_id": None,
                "waba_template_id": None, "waba_params_order": [], "waba_language": "en",
                "waba_category": None, "waba_approval_status": "pending", "waba_approval_note": None,
                "preview_url": False, "status": "active",
                "note": "DLT-approved promotional template (seeded). Body must match DLT content verbatim.",
                "created_at": now_iso, "updated_at": now_iso, "created_by": "system-seed",
            })
            await seed_flags.insert_one({"_id": "kazo_eoss_template", "seeded_at": now_iso})
            logger.info("Seeded DLT-approved 'KAZO End of Season Sale' SMS template")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Could not seed EOSS template: {e}")



@app.on_event("startup")
async def startup():
    from database import users_col, stores_col, loyalty_config_col
    from routes.loyalty_routes import DEFAULT_CONFIG
    from auth import hash_password
    from datetime import datetime, timezone
    import uuid

    # Start the isolated, bounded api_logs background writer FIRST so every log
    # write from here on runs off the main request pool (prevents the production
    # posAddPoint NetworkTimeout caused by logging saturating the shared pool).
    try:
        start_log_writer()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Could not start api_logs background writer: {e}")

    # Best-effort init of object storage for the Downloads Center exports.
    try:
        from routes.exports_routes import _init_storage
        await asyncio.to_thread(_init_storage)
        logger.info("Object storage initialized for exports")
    except Exception as e:  # noqa: BLE001
        logger.warning("Object storage init deferred: %s", e)

    # Seed super admin if not exists
    # ── DB seeding / bootstrapping is DEFERRED to a resilient background task ──
    # (see _seed_and_bootstrap). It must NEVER run inline here: a transient Atlas
    # 'no primary' at deploy time would block the lifespan for 120s and then EXIT
    # the process, so the readiness probe (/health) never passes and the whole
    # deployment is killed. Start the scheduler first (registering jobs does not
    # touch the DB), then kick seeding off in the background.
    try:
        from scheduler import start_scheduler
        start_scheduler()
    except Exception as e:
        logger.warning(f"Could not start digest scheduler: {e}")

    try:
        asyncio.create_task(_seed_and_bootstrap())
    except Exception as e:
        logger.warning(f"Could not schedule seed/bootstrap: {e}")

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

    # Keep the heavy ALL-TIME analytics rollups fresh in a background task
    # (off the request path, on a client with the 30s CSOT disabled) so the
    # "All time" views never run a full-collection scan on a request and 500.
    # Persisted in Mongo, so it also survives the frequent redeploys.
    try:
        from routes.analytics_routes import rollup_loop
        asyncio.create_task(rollup_loop())
    except Exception as e:
        logger.warning(f"Could not schedule analytics rollup loop: {e}")

    # Warm the RFM population breakpoints once at startup (then refreshed every
    # 30 min by the scheduler). Persisted to a shared Mongo doc so the Customer-360
    # detail view NEVER blocks on the ~1.5-3s whole-base quintile scan — it just
    # reads the tiny persisted doc. Without this, a cold/expired per-pod cache made
    # the "View" drilldown "take ages".
    try:
        from routes.fundlebrain_routes import refresh_rfm_breakpoints
        asyncio.create_task(refresh_rfm_breakpoints())
    except Exception as e:
        logger.warning(f"Could not warm RFM breakpoints: {e}")

    # Backfill the canonical `amount_paid` (customer's TOTAL PAID, incl. GST) onto every
    # transaction that doesn't have it yet, so ALL reports/exports/dashboards agree on the
    # same figure even for historic bills. Batched + deadline-free so it can't stall a
    # request or hit the 30s CSOT; idempotent (only fills missing docs).
    try:
        asyncio.create_task(_backfill_amount_paid())
    except Exception as e:
        logger.warning(f"Could not start amount_paid backfill: {e}")

    # First-boot Data Health scan: on a FRESH deployment (no persisted scan yet) run the
    # proactive audit once, deferred so it never competes with startup/backfill. Thereafter
    # the daily 07:30 scheduler + the persisted doc keep it fresh (no rescan on restarts).
    async def _first_boot_health_scan():
        try:
            await asyncio.sleep(180)
            from database import db as _db
            existing = await _db["dashboard_kv"].find_one({"_id": "data_health"}, {"_id": 1})
            if existing:
                return
            from routes.master_brain_tools import run_data_health_scan
            await run_data_health_scan(triggered_by="startup")
        except Exception as e:
            logger.warning(f"First-boot data-health scan failed: {e}")
    try:
        asyncio.create_task(_first_boot_health_scan())
    except Exception as e:
        logger.warning(f"Could not schedule first-boot data-health scan: {e}")


@app.on_event("shutdown")
async def shutdown():
    try:
        from scheduler import stop_scheduler
        stop_scheduler()
    except Exception:
        pass
    from database import client
    client.close()
