"""Persistent rollups for heavy, all-time dashboard aggregations.

Why this exists
---------------
The "All time" analytics views scan the full transactions collection
(~750K+ loyalty bills). On the shared Atlas cluster that scan can exceed the
30s client operation timeout baked into MONGO_URL (``timeoutMS``). When it runs
synchronously on a request path (which happens on every cold cache — i.e. after
each redeploy, since the in-process ``_dash_cache`` is wiped on restart) it
500s, and because it never finishes within 30s it 500s *every* time.

Fix
---
Compute these heavy metrics in a BACKGROUND task on a dedicated Mongo client
whose CSOT is disabled (so the scan can take as long as it needs), and persist
the result in the ``dashboard_rollups`` collection. Request handlers then read
the tiny rollup doc and return instantly. If the rollup is not ready yet they
fall back to the live query (i.e. today's behaviour), so nothing breaks — the
rollup is a pure performance/availability layer, never a correctness gate.

Because the rollup is persisted in Mongo it also survives restarts, so the
frequent redeploys no longer cause a cold all-time scan on the request path.
"""
import os
import time
import logging

from motor.motor_asyncio import AsyncIOMotorClient

from database import db

logger = logging.getLogger("kazo-fundle.rollups")

# Persistent store. Tiny docs ({_id, value, computed_at}); read/written on the
# normal (fast, CSOT-capped) client since these ops are sub-millisecond.
rollups_col = db["dashboard_rollups"]

# Dedicated client for the heavy BACKGROUND computations only. timeoutMS=None
# overrides the 30s CSOT from MONGO_URL so a multi-second full-collection scan
# can complete instead of being killed at 30s. Small pool (only the rollup loop
# uses it). Falls back to the shared db handle if it cannot be constructed.
try:
    _long_client = AsyncIOMotorClient(
        os.environ["MONGO_URL"], timeoutMS=None, maxPoolSize=4, minPoolSize=0,
    )
    _long_db = _long_client[os.environ["DB_NAME"]]
except Exception as e:  # pragma: no cover - defensive; never block startup
    logger.warning(f"long-timeout rollup client init failed, using default db: {e}")
    _long_db = db


def long_col(name: str):
    """Collection handle on the CSOT-disabled client. Background computes ONLY."""
    return _long_db[name]


async def read_rollup(key: str, max_age_s: float = 6 * 3600.0):
    """Return the cached value if present and younger than ``max_age_s``, else None.

    Never raises — on any error it returns None so callers cleanly fall back to
    the live query.
    """
    try:
        doc = await rollups_col.find_one({"_id": key})
    except Exception as e:
        logger.warning(f"rollup read {key} failed: {e}")
        return None
    if not doc:
        return None
    if time.time() - doc.get("computed_at", 0) > max_age_s:
        return None
    return doc.get("value")


async def write_rollup(key: str, value) -> None:
    """Upsert a rollup value. Best-effort — never raises."""
    try:
        await rollups_col.replace_one(
            {"_id": key},
            {"_id": key, "value": value, "computed_at": time.time()},
            upsert=True,
        )
    except Exception as e:
        logger.warning(f"rollup write {key} failed: {e}")
