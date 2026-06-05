"""Shared helper for parsing date-range query parameters consistently across
every dashboard endpoint.

Contract:
  - If `start_date` AND `end_date` are both provided (YYYY-MM-DD), the range is
    interpreted as that explicit window (end inclusive).
  - Otherwise, if `period_days > 0`, the range is the last N days.
  - Otherwise (period_days == 0), the range is "all time" → returns (None, None).

The Mongo aggregation pipelines should branch on the return value:

    start, end = parse_date_range(start_date, end_date, period_days)
    match = {"customer_mobile": {"$nin": [None, ""]}}
    if start:
        match["bill_date"] = {"$gte": start, "$lt": end} if end else {"$gte": start}

This keeps every endpoint's behaviour identical for the same picker selection.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple


def parse_date_range(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    period_days: int = 0,
) -> Tuple[Optional[str], Optional[str]]:
    """Returns (start_iso, end_iso) suitable for Mongo bill_date filters.

    - start_iso is an ISO date-time string for $gte
    - end_iso is an ISO date-time string for $lt (i.e. exclusive end-of-day)
    - Either may be None when no bound is needed.
    """
    # Explicit custom range takes precedence
    if start_date and end_date:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").replace(
                hour=0, minute=0, second=0, tzinfo=timezone.utc
            )
            end = datetime.strptime(end_date, "%Y-%m-%d").replace(
                hour=0, minute=0, second=0, tzinfo=timezone.utc
            ) + timedelta(days=1)
            return (start.isoformat(), end.isoformat())
        except ValueError:
            pass

    # Half-open range: only start
    if start_date:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").replace(
                hour=0, minute=0, second=0, tzinfo=timezone.utc
            )
            return (start.isoformat(), None)
        except ValueError:
            pass

    # Legacy "Last N days" fallback
    if period_days and period_days > 0:
        start = datetime.now(timezone.utc) - timedelta(days=period_days)
        return (start.isoformat(), None)

    # All time
    return (None, None)
