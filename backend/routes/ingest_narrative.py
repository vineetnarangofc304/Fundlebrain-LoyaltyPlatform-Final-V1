"""Post-Ingest AI Auto-Narrative.

When a historic data CSV ingest job completes, this module asks Fundle Brain
(GPT-5.2 via Emergent LLM Key) to produce a 1-page narrative covering:
  - What dataset was loaded and how many rows landed
  - Before / after state of the key collections
  - Notable shifts in tier mix, AOV, recency, points liability
  - Any reconciliation flags (mismatch between CSV and DB sums)
  - Recommended next actions (e.g. "review the 412 stores auto-created")

The narrative is stored on the job doc as `ai_narrative` so the
Reconciliation page (and a future email transport) can surface it.

Triggered from `_run_ingest_job` after status=completed and reconciliation
write — guarded by try/except so it never fails the parent ingest.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

from database import (
    customers_col, transactions_col, stores_col, db,
)

logger = logging.getLogger("kazo-fundle.ingest_narrative")

historic_jobs_col = db["historic_ingest_jobs"]
items_col = db["items"]


async def _snapshot() -> Dict[str, Any]:
    """Cheap DB-state snapshot — counts + a couple of key sums."""
    customers_total = await customers_col.count_documents({})
    customers_loyalty = await customers_col.count_documents({"mobile": {"$nin": [None, ""]}})
    txn_total = await transactions_col.count_documents({})
    txn_loyalty = await transactions_col.count_documents({"customer_mobile": {"$nin": [None, ""]}})
    stores_total = await stores_col.count_documents({})
    items_total = await items_col.count_documents({})

    # Net sales + points liability (loyalty only)
    sums = await transactions_col.aggregate([
        {"$match": {"customer_mobile": {"$nin": [None, ""]}}},
        {"$group": {"_id": None, "net": {"$sum": "$net_amount"},
                     "earned": {"$sum": "$points_earned"},
                     "redeemed": {"$sum": "$points_redeemed"}}},
    ]).to_list(1)
    net = (sums[0]["net"] if sums else 0) or 0
    earned = (sums[0]["earned"] if sums else 0) or 0
    redeemed = (sums[0]["redeemed"] if sums else 0) or 0

    # Tier distribution
    tier_agg = await customers_col.aggregate([
        {"$match": {"mobile": {"$nin": [None, ""]}}},
        {"$group": {"_id": "$tier", "n": {"$sum": 1}}},
    ]).to_list(20)
    tiers = {r["_id"] or "untiered": r["n"] for r in tier_agg}

    return {
        "customers_total": customers_total,
        "customers_loyalty": customers_loyalty,
        "transactions_total": txn_total,
        "transactions_loyalty": txn_loyalty,
        "stores_total": stores_total,
        "items_total": items_total,
        "loyalty_net_sales": round(float(net), 2),
        "points_earned_total": int(earned),
        "points_redeemed_total": int(redeemed),
        "points_outstanding": int(earned - redeemed),
        "tier_mix": tiers,
    }


async def _ai_narrative(prompt: str) -> str:
    """Call Fundle Brain (Emergent LLM Key) to produce the narrative.

    Falls back to a deterministic templated summary if the LLM call fails or
    no key is available — we never want a missing AI key to leave the
    user without a report.
    """
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return ""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage  # type: ignore
        llm = LlmChat(api_key=key, session_id=f"ingest-narr-{datetime.now(timezone.utc).timestamp()}",
                       system_message=(
                           "You are Fundle Brain, KAZO's loyalty data analyst. "
                           "Write a CRISP 1-page narrative for the brand manager about a CSV "
                           "ingest that just completed. Use plain English, no markdown headers. "
                           "Lead with the bottom-line outcome. Include 3 specific numbers from "
                           "the data provided. End with 2 concrete recommended actions."
                       )).with_model("openai", "gpt-5")
        resp = await llm.send_message(UserMessage(text=prompt))
        return (resp or "").strip()
    except Exception as e:
        logger.warning(f"AI narrative failed, falling back to template: {e}")
        return ""


def _template_narrative(job: Dict[str, Any], snap: Dict[str, Any]) -> str:
    dataset = job.get("dataset", "data")
    inserted = job.get("inserted", 0)
    updated = job.get("updated", 0)
    skipped = job.get("skipped", 0)
    total = job.get("total_rows") or (inserted + updated + skipped)
    recon = job.get("reconciliation") or {}
    recon_status = "matched" if recon.get("match") else (recon.get("status") or "pending")
    stores_new = job.get("stores_auto_created", 0)
    tier_mix = ", ".join(f"{t}: {n}" for t, n in snap.get("tier_mix", {}).items())
    return (
        f"Historic {dataset} ingest completed. "
        f"{inserted:,} new rows inserted, {updated:,} updated, {skipped:,} skipped "
        f"out of {total:,} total CSV rows. Reconciliation: {recon_status}. "
        f"Current loyalty base now stands at {snap['customers_loyalty']:,} customers "
        f"({snap['customers_total']:,} including walk-ins), {snap['transactions_loyalty']:,} loyalty bills, "
        f"₹{snap['loyalty_net_sales']:,.0f} lifetime net sales. "
        f"Points outstanding: {snap['points_outstanding']:,} (earned {snap['points_earned_total']:,} - "
        f"redeemed {snap['points_redeemed_total']:,}). "
        f"Tier mix — {tier_mix}. "
        f"{stores_new} new stores auto-created from outlet labels. "
        f"\n\nRecommended next steps: (1) Review the data on Command Center with 'All time' "
        f"period to validate KPIs against your source system. "
        f"(2) Run /admin/reconciliation to confirm CSV vs DB sums match exactly."
    )


async def build_and_store_narrative(job_id: str) -> Dict[str, Any]:
    """Public entry-point. Reads the job doc, builds narrative, persists it.

    Idempotent — safe to re-run on the same job (overwrites narrative).
    Returns the narrative dict (also stored on the job).
    """
    job = await historic_jobs_col.find_one({"id": job_id}, {"_id": 0})
    if not job:
        return {"error": "job_not_found"}
    if job.get("status") not in {"completed", "previewed"}:
        return {"error": f"job_status_{job.get('status')}"}

    snap = await _snapshot()

    # Compact JSON-ish prompt the LLM can chew on
    prompt = (
        f"INGEST JOB SUMMARY:\n"
        f"  Dataset: {job.get('dataset')}\n"
        f"  Status: {job.get('status')}\n"
        f"  CSV rows: {job.get('total_rows')}\n"
        f"  Inserted: {job.get('inserted')}  Updated: {job.get('updated')}  Skipped: {job.get('skipped')}\n"
        f"  Stores auto-created: {job.get('stores_auto_created', 0)}\n"
        f"  Reconciliation: {job.get('reconciliation') or 'n/a'}\n"
        f"\nCURRENT DB STATE (after ingest):\n"
        f"  Customers total: {snap['customers_total']:,} (loyalty {snap['customers_loyalty']:,})\n"
        f"  Transactions total: {snap['transactions_total']:,} (loyalty {snap['transactions_loyalty']:,})\n"
        f"  Stores: {snap['stores_total']:,}  Items: {snap['items_total']:,}\n"
        f"  Loyalty net sales: ₹{snap['loyalty_net_sales']:,.0f}\n"
        f"  Points earned total: {snap['points_earned_total']:,}\n"
        f"  Points redeemed total: {snap['points_redeemed_total']:,}\n"
        f"  Points outstanding: {snap['points_outstanding']:,}\n"
        f"  Tier mix: {snap.get('tier_mix')}\n"
    )

    ai_text = await _ai_narrative(prompt)
    used_ai = bool(ai_text)
    if not ai_text:
        ai_text = _template_narrative(job, snap)

    narrative = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "narrative": ai_text,
        "source": "fundle_brain_gpt5" if used_ai else "template_fallback",
        "snapshot": snap,
    }
    await historic_jobs_col.update_one(
        {"id": job_id},
        {"$set": {"ai_narrative": narrative}},
    )
    return narrative
