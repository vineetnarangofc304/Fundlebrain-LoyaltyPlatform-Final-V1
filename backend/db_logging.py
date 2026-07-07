"""Dedicated, isolated background writer for the API Monitor (`api_logs`).

WHY THIS EXISTS (production P0 fix)
-----------------------------------
POS + admin API logging used to fire an UNBOUNDED
`asyncio.create_task(api_logs_col.insert_one(...))` per request on the SHARED
Motor client. On production `api_logs` holds millions of rows and each insert
touches multiple indexes, so under live store traffic these background inserts
saturated the single shared connection pool. A live `posAddPoint` bill could
then no longer check out a socket within the Atlas client `timeoutMS` and died
with `NetworkTimeout: ... read operation timed out` (HTTP 500 → the till hangs
on "Working on it…"). Master Brain reads stalled for the same reason.

FIX
---
Route ALL best-effort `api_logs` writes through a BOUNDED queue drained by a
few workers on a SEPARATE, small Motor client. Consequences:
  * Logging can NEVER again steal connections from foreground POS / dashboard /
    Master-Brain reads — it lives on its own tiny pool.
  * A traffic burst just fills the queue; overflow is DROPPED (a lost monitor
    row is acceptable — a blocked till is not).
  * Batched `insert_many` cuts round-trips under load.
"""
import os
import asyncio
import logging
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger("kazo-fundle.db-logging")

_MONGO_URL = os.environ["MONGO_URL"]
_DB_NAME = os.environ["DB_NAME"]

# Small, ISOLATED pool used ONLY for best-effort log writes. Kept deliberately
# tiny so a slow api_logs insert can never consume the main request pool.
_log_client = AsyncIOMotorClient(
    _MONGO_URL,
    maxPoolSize=8,
    minPoolSize=0,
    serverSelectionTimeoutMS=5000,
)
_log_col = _log_client[_DB_NAME]["api_logs"]

_QUEUE_MAX = 5000
_BATCH_MAX = 50
_queue: asyncio.Queue | None = None      # created on start() (bound to the running loop)
_workers: list = []
_dropped = 0


def submit_log(doc: dict) -> None:
    """Non-blocking, best-effort enqueue of one `api_logs` row.

    Never raises and never blocks the request. Silently drops on overflow —
    losing a monitor row is acceptable; delaying a live bill is not."""
    global _dropped
    q = _queue
    if q is None:
        return
    try:
        q.put_nowait(doc)
    except asyncio.QueueFull:
        _dropped += 1
        if _dropped % 500 == 1:
            logger.warning(
                f"api_logs write queue full — dropped {_dropped} monitor rows so far "
                "(logging is best-effort; live traffic is unaffected)")


async def _worker() -> None:
    assert _queue is not None
    while True:
        doc = await _queue.get()
        batch = [doc]
        try:
            for _ in range(_BATCH_MAX - 1):
                batch.append(_queue.get_nowait())
        except asyncio.QueueEmpty:
            pass
        try:
            if len(batch) == 1:
                await _log_col.insert_one(batch[0])
            else:
                await _log_col.insert_many(batch, ordered=False)
        except Exception as e:  # noqa: BLE001 — best-effort; never crash the worker
            logger.debug(f"api_logs background insert failed ({len(batch)} rows): {e}")
        finally:
            for _ in batch:
                _queue.task_done()


def start_log_writer(num_workers: int = 2) -> None:
    """Start the background writer. Idempotent; call once on app startup."""
    global _queue, _workers
    if _queue is not None:
        return
    _queue = asyncio.Queue(maxsize=_QUEUE_MAX)
    _workers = [asyncio.create_task(_worker()) for _ in range(max(1, num_workers))]
    logger.info(f"api_logs background writer started ({len(_workers)} workers, dedicated pool)")
