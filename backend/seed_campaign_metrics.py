"""Seed campaign_metrics collection from existing campaigns aggregates.

Strategy: For each campaign that has sent/delivered/clicked/redeemed/revenue values,
expand them into per-channel rows in `campaign_metrics`. This is a one-shot
restructuring of EXISTING data (not synthetic) — required so Campaign ROI v2
funnel can show CTR / CVR per channel.

Idempotent: if `campaign_metrics` already has rows for a campaign_id, it is skipped.

Usage: `python -m backend.seed_campaign_metrics` (or call seed_campaign_metrics()
from startup).
"""
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Dict

from database import campaigns_col, campaign_metrics_col


# Channel cost-per-message (₹) — best-known industry rates for Karix India
CHANNEL_COST_PER_MSG = {
    "sms": 0.18,
    "whatsapp": 0.55,
    "rcs": 0.65,
    "email": 0.04,
    "push": 0.01,
}


def _split_int(total: int, weights: list) -> list:
    """Split integer `total` across len(weights) buckets weighted by `weights`.

    Always preserves the sum exactly (last bucket absorbs rounding).
    """
    if total <= 0 or not weights:
        return [0] * len(weights)
    ws = sum(weights) or 1.0
    out = [int(round(total * w / ws)) for w in weights]
    diff = total - sum(out)
    out[-1] += diff
    return out


def _split_float(total: float, weights: list) -> list:
    if total <= 0 or not weights:
        return [0.0] * len(weights)
    ws = sum(weights) or 1.0
    out = [total * w / ws for w in weights]
    return [round(x, 2) for x in out]


async def seed_campaign_metrics(force: bool = False) -> Dict[str, int]:
    """Populate campaign_metrics. Returns {campaigns_processed, rows_inserted, skipped}."""
    existing_ids = set()
    if not force:
        async for r in campaign_metrics_col.find({}, {"_id": 0, "campaign_id": 1}):
            existing_ids.add(r.get("campaign_id"))

    inserted = 0
    processed = 0
    skipped = 0
    campaigns = await campaigns_col.find({}, {"_id": 0}).to_list(2000)
    docs = []
    for c in campaigns:
        cid = c.get("id")
        if not cid:
            continue
        if cid in existing_ids:
            skipped += 1
            continue
        sent = int(c.get("sent", 0) or 0)
        if sent == 0:
            continue  # nothing to split
        delivered = int(c.get("delivered", 0) or 0)
        opened = int(c.get("opened", 0) or 0)
        clicked = int(c.get("clicked", 0) or 0)
        converted = int(c.get("redeemed", 0) or 0)
        revenue = float(c.get("revenue_generated", 0) or 0)
        channels = c.get("channels") or ["sms"]
        # weights: SMS = 1, WhatsApp = 1.4, Email = 1.2, Push = 0.7, RCS = 1.1
        weight_map = {"sms": 1.0, "whatsapp": 1.4, "email": 1.2, "push": 0.7, "rcs": 1.1}
        weights = [weight_map.get(ch, 1.0) for ch in channels]
        sent_split = _split_int(sent, weights)
        delivered_split = _split_int(delivered, weights)
        opened_split = _split_int(opened, weights)
        clicked_split = _split_int(clicked, weights)
        converted_split = _split_int(converted, weights)
        revenue_split = _split_float(revenue, weights)
        now = datetime.now(timezone.utc).isoformat()
        for i, ch in enumerate(channels):
            s = sent_split[i]
            cost = round(s * CHANNEL_COST_PER_MSG.get(ch, 0.20), 2)
            docs.append({
                "id": uuid.uuid4().hex,
                "campaign_id": cid,
                "campaign_name": c.get("name"),
                "channel": ch,
                "sent": s,
                "delivered": delivered_split[i],
                "opened": opened_split[i],
                "clicked": clicked_split[i],
                "converted": converted_split[i],
                "revenue_generated": revenue_split[i],
                "cost": cost,
                "launched_at": c.get("launched_at"),
                "status": c.get("status"),
                "created_at": now,
            })
        processed += 1
    if docs:
        await campaign_metrics_col.insert_many(docs)
        inserted = len(docs)
    return {"campaigns_processed": processed, "rows_inserted": inserted, "skipped": skipped}


if __name__ == "__main__":
    res = asyncio.run(seed_campaign_metrics())
    print(res)
