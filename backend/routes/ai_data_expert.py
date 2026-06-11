"""Fundle Brain — "expert on the ingested data" layer.

Two pieces:
1. build_data_context() — a live, cached snapshot of WHAT data exists
   (collection counts, bill-date coverage, stores, tiers, loyalty config,
   ingest history). Injected as a system message so the model knows the shape
   and span of the warehouse before it answers anything.
2. run_aggregation + get_data_dictionary tools — a guard-railed, read-only
   MongoDB aggregation escape hatch so the model can answer ANY data question,
   not just the canned tool set.
"""
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database import db, customers_col, transactions_col, stores_col

logger = logging.getLogger("kazo-fundle.ai_data_expert")

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
                     "points_redeemed, items[] (sku,name,category,quantity,total), source "
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
        if jobs:
            lines.append("Recent completed CSV ingests: " + "; ".join(
                f"{j.get('dataset')}:{j.get('filename', '')[:40]} ({j.get('processed', 0):,} rows)" for j in jobs))
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


async def get_data_dictionary(args: Dict[str, Any], user=None) -> Dict[str, Any]:
    """Field names + types + notes for an allowlisted collection."""
    collection = args.get("collection", "")
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
]

EXPERT_TOOL_HANDLERS = {
    "run_aggregation": run_aggregation,
    "get_data_dictionary": get_data_dictionary,
}
