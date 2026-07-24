"""Canonical "amount paid by the customer" — the single sacrosanct revenue figure.

This mirrors the Live Monitor per-bill "Total Paid": the amount the customer
actually paid at the till = post-discount, INCLUDING GST/tax. Every report,
export and dashboard sums THIS so all screens agree on one number.

Definition (in priority order):
  1. ``bill_with_tax``                       — the paid figure the POS sends.
  2. ``(net_amount_before_tax if > 0 else net_amount) + (tax_amount OR tax_gst)``
     — recompute for older / historic bills that don't carry ``bill_with_tax``.
     (net_amount_before_tax is treated as absent when it's 0, so historic rows
     that only carry a net_amount total still resolve correctly.)

Usage:
  * ``paid_amount(doc)`` — Python value, for write paths (posAddPoint, ingest).
  * ``PAID_EXPR``        — Mongo aggregation expression: prefers the denormalized
                           ``amount_paid`` field, else recomputes on the fly (so
                           numbers are correct even before the backfill lands).
  * ``PAID_COMPUTE``     — pure recompute expression (no amount_paid), for backfill.
"""
from typing import Any, Dict


def _f(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def paid_amount(doc: Dict[str, Any]) -> float:
    """Canonical Total Paid for a bill document / POS payload."""
    bwt = _f(doc.get("bill_with_tax"))
    if bwt is not None:
        return round(bwt, 2)
    nbt = _f(doc.get("net_amount_before_tax"))
    if nbt is None or nbt <= 0:
        nbt = _f(doc.get("net_amount")) or 0.0
    tax = _f(doc.get("tax_amount"))
    if tax is None:
        tax = _f(doc.get("tax_gst")) or 0.0
    return round(nbt + tax, 2)


# Pure recompute from source fields — used by the backfill so historic bills also
# get a correct amount_paid. Mirrors paid_amount() exactly.
_NBT = {
    "$let": {
        "vars": {"nbt": {"$ifNull": ["$net_amount_before_tax", 0]}},
        "in": {"$cond": [{"$gt": ["$$nbt", 0]}, "$$nbt", {"$ifNull": ["$net_amount", 0]}]},
    }
}
PAID_COMPUTE: Dict[str, Any] = {
    "$cond": [
        {"$ne": [{"$ifNull": ["$bill_with_tax", None]}, None]},
        {"$ifNull": ["$bill_with_tax", 0]},
        {"$add": [_NBT, {"$ifNull": ["$tax_amount", {"$ifNull": ["$tax_gst", 0]}]}]},
    ]
}

# Report-time expression: prefer the denormalized field, else recompute on the fly.
PAID_EXPR: Dict[str, Any] = {"$ifNull": ["$amount_paid", PAID_COMPUTE]}
