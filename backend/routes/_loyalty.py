"""Shared loyalty-data filters used across every dashboard.

KAZO rules — locked-in:
  R1  bill_date is the chronological source of truth (not created_at)
  R2  customer's home_store_id = store of their earliest bill
  R3  one-timer = 1 unique bill; repeat = 2+ unique bills
  R4  customer_mobile is the unique customer identity
  R5  loyalty data = bills WITH customer_mobile. Bills without mobile are
      non-loyalty / lost-opportunity walk-ins and are EXCLUDED by default
      from every main dashboard.
  R6  points are tracked as earn / redeem / bonus / expired ledger entries.

Every transaction-level aggregation in dashboards MUST be wrapped with
LOYALTY_TX_MATCH unless the endpoint is explicitly serving the
Non-Loyalty Insights view.
"""
from __future__ import annotations
from typing import Any, Dict, Optional


# Transactions with an attached customer_mobile (i.e. loyalty data).
# customer_mobile is normalised at ingest to either a non-empty digit string or None.
LOYALTY_TX_MATCH: Dict[str, Any] = {
    "customer_mobile": {"$nin": [None, ""]},
}

# Inverse — bills WITHOUT a mobile (anonymous walk-ins / lost opportunities).
NON_LOYALTY_TX_MATCH: Dict[str, Any] = {
    "$or": [
        {"customer_mobile": None},
        {"customer_mobile": ""},
        {"customer_mobile": {"$exists": False}},
    ],
}


def loyalty_match(extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Compose the loyalty-only filter with additional clauses.

    Usage:
        match = loyalty_match({"bill_date": {"$gte": start}, "store_id": sid})
        pipeline = [{"$match": match}, ...]
    """
    base = dict(LOYALTY_TX_MATCH)
    if extra:
        base.update(extra)
    return base


def non_loyalty_match(extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Compose the non-loyalty (lost-opportunity) filter with additional clauses."""
    base = dict(NON_LOYALTY_TX_MATCH)
    if extra:
        # Preserve the $or — merge other top-level keys
        for k, v in extra.items():
            if k == "$or":
                # Caller knows what they're doing
                base["$or"] = v
            else:
                base[k] = v
    return base
