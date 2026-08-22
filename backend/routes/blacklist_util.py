"""SMS/WhatsApp delivery blacklist (Campaign Manager — Phase 4).

Auto-populated after BLACKLIST_THRESHOLD successive delivery-report (DLR) failures for a
mobile, and used to EXCLUDE those numbers from every future campaign dataset + bulk send.

- record_dlr_status(mobile, status): called from the DLR ingest. Keeps a per-mobile
  consecutive-failure counter (reset on 'delivered'); auto-blacklists at the threshold.
- blacklisted_set() / is_blacklisted() / filter_blacklisted(): exclude blacklisted numbers.
- add_to_blacklist / remove_from_blacklist / list_blacklist: manual management from the UI.
"""
import re
from datetime import datetime, timezone
from typing import List, Tuple, Optional

from pymongo import ReturnDocument
from database import db

blacklist_col = db["sms_blacklist"]
dlr_stats_col = db["dlr_mobile_stats"]

FAILURE_STATUSES = {"undelivered", "failed", "rejected", "expired"}
BLACKLIST_THRESHOLD = 3


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def norm10(mobile) -> str:
    """Last-10 digits (India), matching how message_log stores / looks up mobiles."""
    digits = re.sub(r"\D", "", str(mobile or ""))
    return digits[-10:] if len(digits) >= 10 else digits


async def is_blacklisted(mobile) -> bool:
    m = norm10(mobile)
    if not m:
        return False
    return bool(await blacklist_col.find_one({"mobile": m}, {"_id": 1}))


async def blacklisted_set() -> set:
    rows = await blacklist_col.distinct("mobile")
    return set(rows or [])


def filter_blacklisted(mobiles: List[str], bl: set) -> Tuple[List[str], int]:
    """Return (kept, removed_count) given a pre-fetched blacklist set."""
    kept, removed = [], 0
    for m in mobiles:
        if norm10(m) in bl:
            removed += 1
        else:
            kept.append(m)
    return kept, removed


async def add_to_blacklist(mobile, reason: str = "manual", source: str = "manual",
                           by: Optional[str] = None) -> bool:
    m = norm10(mobile)
    if not m or len(m) < 10:
        return False
    await blacklist_col.update_one(
        {"mobile": m},
        {"$setOnInsert": {"mobile": m, "blacklisted_at": _now_iso()},
         "$set": {"reason": reason, "source": source, "added_by": by, "updated_at": _now_iso()}},
        upsert=True)
    return True


async def remove_from_blacklist(mobile) -> int:
    m = norm10(mobile)
    res = await blacklist_col.delete_one({"mobile": m})
    # reset the failure counter so a stale count can't immediately re-blacklist it
    await dlr_stats_col.update_one({"mobile": m}, {"$set": {"consecutive_failures": 0}})
    return res.deleted_count


async def record_dlr_status(mobile, status: str) -> Optional[dict]:
    """Track per-mobile delivery outcome; auto-blacklist at the threshold. Never raises."""
    m = norm10(mobile)
    if not m or len(m) < 10:
        return None
    now = _now_iso()
    if status == "delivered":
        await dlr_stats_col.update_one(
            {"mobile": m},
            {"$set": {"consecutive_failures": 0, "last_status": status, "last_dlr_at": now},
             "$inc": {"total_delivered": 1},
             "$setOnInsert": {"mobile": m, "first_seen": now}},
            upsert=True)
        return None
    if status in FAILURE_STATUSES:
        doc = await dlr_stats_col.find_one_and_update(
            {"mobile": m},
            {"$inc": {"consecutive_failures": 1, "total_failed": 1},
             "$set": {"last_status": status, "last_dlr_at": now},
             "$setOnInsert": {"mobile": m, "first_seen": now}},
            upsert=True, return_document=ReturnDocument.AFTER)
        cf = int((doc or {}).get("consecutive_failures", 0))
        if cf >= BLACKLIST_THRESHOLD:
            await blacklist_col.update_one(
                {"mobile": m},
                {"$setOnInsert": {"mobile": m, "blacklisted_at": now},
                 "$set": {"reason": f"{cf} successive delivery failures (last: {status})",
                          "source": "auto_dlr", "consecutive_failures": cf, "updated_at": now}},
                upsert=True)
            return {"blacklisted": True, "mobile": m, "consecutive_failures": cf}
    return None


async def list_blacklist(limit: int = 500, q: Optional[str] = None) -> dict:
    fil = {}
    if q:
        needle = norm10(q) or re.sub(r"\D", "", str(q))
        if needle:
            fil["mobile"] = {"$regex": re.escape(needle)}
    rows = await blacklist_col.find(fil, {"_id": 0}).sort("blacklisted_at", -1).limit(min(limit, 5000)).to_list(5000)
    total = await blacklist_col.count_documents({})
    auto = await blacklist_col.count_documents({"source": "auto_dlr"})
    return {"rows": rows, "total": total, "auto": auto, "manual": total - auto, "showing": len(rows)}
