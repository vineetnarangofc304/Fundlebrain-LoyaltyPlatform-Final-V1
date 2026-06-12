"""Fundle Brain — "expert on the ingested data" layer.

Pieces:
1. build_data_context() — a live, cached snapshot of WHAT data exists
   (collection counts, bill-date coverage, stores, tiers, loyalty config,
   ingest history, brand KPI digest). Injected as a system message so the
   model knows the shape and span of the warehouse before it answers anything.
2. run_aggregation + get_data_dictionary tools — a guard-railed, read-only
   MongoDB aggregation escape hatch so the model can answer ANY data question,
   not just the canned tool set.
3. export_csv tool — streams an aggregation result to a downloadable CSV file
   (up to 1M rows) so the model can deliver RAW DATA, not just summaries.
"""
import asyncio
import csv as _csvmod
import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from database import db, customers_col, transactions_col, stores_col

logger = logging.getLogger("kazo-fundle.ai_data_expert")

EXPORT_DIR = "/app/backend/exports/ai"
os.makedirs(EXPORT_DIR, exist_ok=True)
MAX_EXPORT_ROWS = 1_000_000

# ---------------------------------------------------------------- context ----
_CTX_CACHE: Dict[str, Any] = {"ts": 0.0, "text": ""}
_CTX_TTL = 600  # 10 minutes

ALLOWED_COLLECTIONS = {
    "transactions", "customers", "stores", "points_ledger", "nps_responses",
    "campaigns", "coupons", "support_tickets", "message_log", "items",
    "coupon_redemptions", "api_logs", "historic_jobs", "segments",
}

_FIELD_NOTES = {
    "transactions": ("One doc per BILL. Key fields: bill_number, bill_date (ISO string, the REAL "
                     "purchase date — R1), customer_mobile (None for anonymous walk-ins — R5: only "
                     "bills WITH mobile are loyalty bills), store_id/store_code/store_name, city, "
                     "net_amount, gross_amount, discount_amount, is_return, points_earned, "
                     "points_redeemed, items[] (ARRAY of {sku,name,category,quantity,total} — use "
                     "$size for per-bill item counts, $unwind for item-level analysis), source "
                     "('historic_upload' for CSV ingest, 'pos' for live POS)."),
    "customers": ("One doc per loyalty customer keyed by 10-digit `mobile` (R4 — the identity). "
                  "visit_count and lifetime_spend are recomputed from bills (R3). "
                  "first_purchase_at = first bill date (R1), home_store_id = store of first bill (R2), "
                  "last_visit_at, tier (silver/gold/platinum), points_balance, "
                  "lifetime_points_earned/redeemed, churn_risk, city."),
    "points_ledger": ("One row per points movement. type: earn/redeem/bonus/adjust, points "
                      "(negative for redeem), bill_date (R1), customer_mobile, expires_at."),
    "stores": "Store master: id, code (K-codes like K00078), name, city, state, zone, region, is_active.",
    "nps_responses": "score 0-10, store_id, customer_mobile, comment, created_at.",
    "message_log": "Outbound SMS/WhatsApp log: channel, to, template, status, provider response, created_at.",
    "historic_jobs": "CSV ingest jobs: dataset, filename, processed/inserted/updated/skipped, status.",
}


async def build_data_context() -> str:
    """Cached (10 min) live snapshot of the warehouse for the system prompt."""
    if time.monotonic() - _CTX_CACHE["ts"] < _CTX_TTL and _CTX_CACHE["text"]:
        return _CTX_CACHE["text"]
    try:
        import asyncio
        counts: Dict[str, int] = {}
        for col in ["transactions", "customers", "stores", "points_ledger",
                    "nps_responses", "campaigns", "coupons", "support_tickets", "items"]:
            counts[col] = await db[col].estimated_document_count()

        # Bill-date coverage (min/max) — cheap via the bill_date index
        first = await transactions_col.find({"bill_date": {"$gt": ""}}, {"_id": 0, "bill_date": 1}) \
            .sort("bill_date", 1).limit(1).to_list(1)
        last = await transactions_col.find({"bill_date": {"$gt": ""}}, {"_id": 0, "bill_date": 1}) \
            .sort("bill_date", -1).limit(1).to_list(1)
        date_min = (first[0]["bill_date"][:10] if first else "n/a")
        date_max = (last[0]["bill_date"][:10] if last else "n/a")

        loyalty_bills = await transactions_col.count_documents(
            {"customer_mobile": {"$nin": [None, ""]}}, maxTimeMS=15000)

        cities = await stores_col.distinct("city", {"is_active": True})
        cities = [c for c in cities if c][:25]

        cfg = await db["loyalty_config"].find_one({}, {"_id": 0}) or {}
        tiers = await db["tier_rules"].find({}, {"_id": 0, "tier": 1, "min_spend": 1}).to_list(10)

        jobs = await db["historic_jobs"].find(
            {"status": "completed"}, {"_id": 0, "dataset": 1, "filename": 1, "processed": 1}
        ).sort("queued_at", -1).limit(6).to_list(6)

        # ---- Brand KPI digest (heavier, all guarded — refreshed every 10 min) ----
        kpi_lines: List[str] = []
        try:
            one_timers = await customers_col.count_documents({"visit_count": 1}, maxTimeMS=15000)
            repeats = await customers_col.count_documents({"visit_count": {"$gte": 2}}, maxTimeMS=15000)
            never = max(counts["customers"] - one_timers - repeats, 0)
            kpi_lines.append(
                f"Customer lifecycle: {one_timers:,} one-timers (visit_count=1), {repeats:,} repeat (2+ visits), "
                f"{never:,} registered with zero purchases.")
        except Exception:
            pass
        try:
            tier_rows = await customers_col.aggregate([
                {"$group": {"_id": "$tier", "n": {"$sum": 1}}}, {"$sort": {"n": -1}},
            ], maxTimeMS=20000).to_list(10)
            if tier_rows:
                kpi_lines.append("Tier split: " + ", ".join(
                    f"{r['_id'] or 'untiered'}={r['n']:,}" for r in tier_rows))
        except Exception:
            pass
        try:
            sums = await transactions_col.aggregate([
                {"$match": {"customer_mobile": {"$nin": [None, ""]}}},
                {"$group": {"_id": None, "net": {"$sum": "$net_amount"}, "bills": {"$sum": 1}}},
            ], maxTimeMS=30000, allowDiskUse=True).to_list(1)
            if sums:
                net = sums[0].get("net") or 0
                bills = sums[0].get("bills") or 1
                kpi_lines.append(
                    f"All-time loyalty revenue ₹{net:,.0f} across {bills:,} bills → ATV ₹{net / max(bills, 1):,.0f}.")
        except Exception:
            pass
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
            top_stores = await transactions_col.aggregate([
                {"$match": {"bill_date": {"$gte": cutoff}, "customer_mobile": {"$nin": [None, ""]}}},
                {"$group": {"_id": "$store_name", "net": {"$sum": "$net_amount"}}},
                {"$sort": {"net": -1}}, {"$limit": 5},
            ], maxTimeMS=20000).to_list(5)
            rows = [r for r in top_stores if r.get("_id")]
            if rows:
                kpi_lines.append("Top stores by revenue (last 90d): " + "; ".join(
                    f"{r['_id']} ₹{r['net']:,.0f}" for r in rows))
        except Exception:
            pass

        lines = [
            "=== LIVE DATA WAREHOUSE SNAPSHOT (auto-refreshed) ===",
            f"Generated: {datetime.now(timezone.utc).isoformat()[:16]}Z",
            f"Collections: " + ", ".join(f"{k}={v:,}" for k, v in counts.items()),
            f"Transactions cover bill dates {date_min} → {date_max}. "
            f"{loyalty_bills:,} of {counts['transactions']:,} bills are loyalty bills (have customer_mobile).",
            f"Active store cities: {', '.join(cities) if cities else 'n/a'}.",
            f"Loyalty config: earn_rate={cfg.get('earn_rate', 'n/a')}, burn_ratio={cfg.get('burn_ratio', 0.25)} "
            f"(1 point = ₹{cfg.get('burn_ratio', 0.25)}).",
            f"Tiers: " + (", ".join(f"{t.get('tier')}≥₹{t.get('min_spend', 0):,}" for t in tiers) if tiers else "silver/gold/platinum"),
        ]
        if kpi_lines:
            lines.append("--- BRAND KPI DIGEST ---")
            lines.extend(kpi_lines)
        if jobs:
            lines.append("Recent completed CSV ingests: " + "; ".join(
                f"{j.get('dataset')}:{j.get('filename', '')[:40]} ({j.get('processed', 0):,} rows)" for j in jobs))
        lines.append(
            "DATA PROVENANCE NOTE: a large share of customers were ingested from a customer-master CSV "
            "(source='historic_upload') WITHOUT bill-level rows — their visit_count / lifetime_spend / "
            "last_visit_at / days_since_last_visit come straight from the master file. Transaction-level "
            "aggregates only cover customers whose bills exist in `transactions`. So when counting or "
            "exporting CUSTOMERS (e.g. one-timers), always query the `customers` collection fields "
            "(visit_count, lifetime_spend, days_since_last_visit) — do NOT join via transactions.")
        lines.append(
            "Canonical rules: R1 bill_date is truth (never ingest time) · R2 home store = first-bill store · "
            "R3 visit_count/lifetime_spend recomputed from bills · R4 mobile = customer identity · "
            "R5 loyalty metrics use bills WITH mobile only · R6 points live on bills + points_ledger.")
        text = "\n".join(lines)
        _CTX_CACHE.update(ts=time.monotonic(), text=text)
        return text
    except Exception as e:
        logger.warning(f"build_data_context failed: {e}")
        return ""


# ----------------------------------------------------------- aggregation ----
_FORBIDDEN_TOKENS = ("$out", "$merge", "$function", "$accumulator", "$where",
                     "$currentOp", "$listSessions", "$unionWith")


def _validate_pipeline(collection: str, pipeline: List[Dict[str, Any]]) -> Optional[str]:
    if collection not in ALLOWED_COLLECTIONS:
        return f"collection must be one of {sorted(ALLOWED_COLLECTIONS)}"
    if not isinstance(pipeline, list) or not pipeline:
        return "pipeline must be a non-empty list of stages"
    if len(pipeline) > 12:
        return "pipeline too long (max 12 stages)"
    blob = json.dumps(pipeline)
    for tok in _FORBIDDEN_TOKENS:
        if f'"{tok}"' in blob:
            return f"stage {tok} is not allowed (read-only access)"
    for st in pipeline:
        if not isinstance(st, dict) or len(st) != 1:
            return "each stage must be a single-key object"
        key = next(iter(st))
        if key == "$lookup":
            frm = st["$lookup"].get("from")
            if frm not in ALLOWED_COLLECTIONS:
                return f"$lookup.from must be one of {sorted(ALLOWED_COLLECTIONS)}"
    return None


async def run_aggregation(collection: str = "", pipeline: Any = None, user=None) -> Dict[str, Any]:
    """Read-only aggregation escape hatch with guardrails."""
    pipeline = pipeline or []
    if isinstance(pipeline, str):
        try:
            pipeline = json.loads(pipeline)
        except Exception:
            return {"error": "pipeline must be valid JSON"}
    err = _validate_pipeline(collection, pipeline)
    if err:
        return {"error": err}
    # force a result cap
    has_limit = any("$limit" in st for st in pipeline)
    if not has_limit:
        pipeline = pipeline + [{"$limit": 100}]
    try:
        rows = await db[collection].aggregate(
            pipeline, allowDiskUse=True, maxTimeMS=30000).to_list(200)
        # strip _id ObjectIds for JSON safety
        for r in rows:
            if "_id" in r and not isinstance(r["_id"], (str, int, float, dict, list, type(None))):
                r["_id"] = str(r["_id"])
        return {"collection": collection, "row_count": len(rows), "rows": rows}
    except Exception as e:
        return {"error": f"aggregation failed: {str(e)[:300]}"}


async def get_data_dictionary(collection: str = "", user=None) -> Dict[str, Any]:
    """Field names + types + notes for an allowlisted collection."""
    if collection not in ALLOWED_COLLECTIONS:
        return {"error": f"collection must be one of {sorted(ALLOWED_COLLECTIONS)}"}
    doc = await db[collection].find_one({}, {"_id": 0}, sort=[("_id", -1)])
    fields = {}
    for k, v in (doc or {}).items():
        t = type(v).__name__
        preview = str(v)[:60] if not isinstance(v, (dict, list)) else t
        fields[k] = {"type": t, "example": preview}
    return {
        "collection": collection,
        "notes": _FIELD_NOTES.get(collection, ""),
        "fields": fields,
        "count": await db[collection].estimated_document_count(),
    }


# ----------------------------------------------------------- CSV export ----
def _csv_cell(v: Any) -> Any:
    if isinstance(v, (dict, list)):
        return json.dumps(v, default=str)
    if v is None:
        return ""
    return v


async def _run_export_job(export_id: str, collection: str,
                          pipeline: List[Dict[str, Any]], max_rows: int) -> None:
    """Background: stream aggregation results into a CSV file on disk."""
    path = os.path.join(EXPORT_DIR, f"{export_id}.csv")
    try:
        cursor = db[collection].aggregate(
            pipeline, allowDiskUse=True, maxTimeMS=300000, batchSize=2000)
        cols: List[str] = []
        buf: List[Dict[str, Any]] = []
        n = 0
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer: Optional[_csvmod.DictWriter] = None

            def _flush_buf():
                nonlocal writer, cols
                seen: List[str] = []
                for r in buf:
                    for k in r:
                        if k not in seen:
                            seen.append(k)
                cols = seen
                writer = _csvmod.DictWriter(f, fieldnames=cols, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(buf)
                buf.clear()

            async for doc in cursor:
                if not isinstance(doc.get("_id"), (str, int, float, type(None))):
                    doc["_id"] = str(doc.get("_id"))
                row = {k: _csv_cell(v) for k, v in doc.items()}
                if writer is None:
                    buf.append(row)
                    if len(buf) >= 500:
                        _flush_buf()
                else:
                    writer.writerow(row)
                n += 1
                if n >= max_rows:
                    break
            if writer is None:
                _flush_buf()
        await db["ai_exports"].update_one({"id": export_id}, {"$set": {
            "status": "ready", "row_count": n, "columns": cols,
            "size_bytes": os.path.getsize(path),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }})
    except Exception as e:
        logger.warning(f"export {export_id} failed: {e}")
        await db["ai_exports"].update_one({"id": export_id}, {"$set": {
            "status": "failed", "error": str(e)[:300]}})


async def export_csv(collection: str = "", pipeline: Any = None,
                     filename: str = "", max_rows: int = MAX_EXPORT_ROWS,
                     user=None) -> Dict[str, Any]:
    """Stream a read-only aggregation to a downloadable CSV (up to 1M rows).

    Returns immediately if the export finishes within ~8s; otherwise the job
    keeps running in the background and the download link returns 202 until
    ready.
    """
    pipeline = pipeline or []
    if isinstance(pipeline, str):
        try:
            pipeline = json.loads(pipeline)
        except Exception:
            return {"error": "pipeline must be valid JSON"}
    err = _validate_pipeline(collection, pipeline)
    if err:
        return {"error": err}
    try:
        max_rows = min(max(int(max_rows), 1), MAX_EXPORT_ROWS)
    except Exception:
        max_rows = MAX_EXPORT_ROWS

    export_id = uuid.uuid4().hex
    safe_name = "".join(ch for ch in (filename or f"{collection}_export")
                        if ch.isalnum() or ch in ("-", "_", " ", ".")).strip() or "export"
    if not safe_name.lower().endswith(".csv"):
        safe_name += ".csv"

    await db["ai_exports"].insert_one({
        "id": export_id, "filename": safe_name, "collection": collection,
        "pipeline": json.dumps(pipeline, default=str)[:4000],
        "status": "preparing", "row_count": 0,
        "created_by": (user or {}).get("email", "fundle-brain"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    task = asyncio.create_task(_run_export_job(export_id, collection, pipeline, max_rows))
    # Give small exports a chance to complete inline (better UX)
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=8.0)
    except asyncio.TimeoutError:
        pass
    doc = await db["ai_exports"].find_one({"id": export_id}, {"_id": 0, "pipeline": 0})
    out = {
        "export_id": export_id,
        "filename": safe_name,
        "status": doc.get("status", "preparing"),
        "row_count": doc.get("row_count", 0),
        "download_url": f"/api/ai/exports/{export_id}",
    }
    if doc.get("status") == "failed":
        out["error"] = doc.get("error", "export failed")
    elif doc.get("status") == "preparing":
        out["note"] = ("Export is still streaming to disk in the background. "
                       "Share the download link — it becomes downloadable within a minute.")
    else:
        out["columns"] = (doc.get("columns") or [])[:15]
    return out


EXPERT_TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "run_aggregation",
            "description": (
                "Run a READ-ONLY MongoDB aggregation pipeline against the live KAZO warehouse. "
                "Use this when no canned tool answers the question — e.g. 'top 10 customers by spend "
                "in Delhi during Oct 2024', 'monthly returns rate by store', 'average days between visits'. "
                "Collections: transactions, customers, stores, points_ledger, nps_responses, campaigns, "
                "coupons, support_tickets, message_log, items, historic_jobs. "
                "bill_date / first_purchase_at / last_visit_at are ISO-8601 STRINGS — compare with string "
                "ranges like {'$gte': '2024-10-01', '$lt': '2024-11-01'}. "
                "For loyalty metrics always add {'customer_mobile': {'$nin': [null, '']}} (R5). "
                "Results are capped at 200 rows — always $group/$sort/$limit server-side. "
                "Forbidden: $out/$merge/$function/$where (read-only)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "collection": {"type": "string", "description": "target collection"},
                    "pipeline": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "MongoDB aggregation stages (max 12)",
                    },
                },
                "required": ["collection", "pipeline"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_data_dictionary",
            "description": ("Get the field names, types, example values, document count and semantic notes "
                            "for a collection. Call this BEFORE run_aggregation if unsure of field names."),
            "parameters": {
                "type": "object",
                "properties": {"collection": {"type": "string"}},
                "required": ["collection"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "export_csv",
            "description": (
                "Export RAW DATA as a downloadable CSV file (streams up to 1,000,000 rows to disk). "
                "Use this whenever the user asks for a list / dump / export / 'CSV of' / 'download' of records "
                "— e.g. 'give me a CSV of all one-timers', 'export gold-tier customers', 'download last month's bills'. "
                "Build a pipeline with $match (the filter) + $project (only the useful columns, _id: 0) — "
                "do NOT add $limit unless the user asked for a top-N. "
                "For customer lists (one-timers, repeat, dormant, tiers) query the `customers` collection "
                "(visit_count, lifetime_spend, days_since_last_visit, tier, mobile, name, city). "
                "Returns a download_url — present it to the user as a Markdown link. NEVER refuse a raw-data request."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "collection": {"type": "string", "description": "source collection"},
                    "pipeline": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "MongoDB aggregation stages: $match + $project (set _id: 0)",
                    },
                    "filename": {"type": "string", "description": "human-friendly file name, e.g. one_timer_customers.csv"},
                    "max_rows": {"type": "integer", "description": "optional row cap (default 1,000,000)"},
                },
                "required": ["collection", "pipeline", "filename"],
            },
        },
    },
]

EXPERT_TOOL_HANDLERS = {
    "run_aggregation": run_aggregation,
    "get_data_dictionary": get_data_dictionary,
    "export_csv": export_csv,
}
