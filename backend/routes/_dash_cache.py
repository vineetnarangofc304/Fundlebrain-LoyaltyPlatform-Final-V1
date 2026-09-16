"""Tiny in-process TTL cache for heavy dashboard/report aggregations.

Production-scale aggregations (distinct-visitor groups over millions of bills)
have an irreducible cost of several seconds. Dashboards re-fetch on every
mount/filter flip, so a short TTL cache makes every repeat view instant while
keeping data at most CACHE_TTL seconds stale (data only changes via ingest
jobs or live POS traffic anyway).

Usage:
    @router.get("/rfm")
    @dash_cache("rfm")
    async def rfm_dashboard(...): ...

The decorator builds the key from all scalar kwargs (and Pydantic bodies via
model_dump_json), skipping non-serialisable ones like the auth `user` dict.
"""
import asyncio
import functools
import hashlib
import inspect
import time
import typing
from typing import Any, Optional

_STORE: dict = {}
# Fresh window. Raised to 30 min so a cached view stays served between warm
# passes (and without a warmer at all — it's now opt-in). Freshness beyond this
# is handled by the stale-while-revalidate layer below, which serves the last
# value instantly and refreshes in the background.
DEFAULT_TTL = 1800   # seconds — "fresh" window
STALE_TTL = 7200     # seconds — serve-stale-while-revalidate window
_REFRESHING: set = set()   # keys with an in-flight background refresh


def cache_get(key: str, ttl: int = DEFAULT_TTL) -> Optional[Any]:
    hit = _STORE.get(key)
    if not hit:
        return None
    ts, val = hit
    if time.monotonic() - ts > ttl:
        return None   # stale — keep entry for SWR (evicted past STALE_TTL)
    return val


def cache_get_stale(key: str) -> Optional[Any]:
    """Return a stale-but-usable value (younger than STALE_TTL), else None."""
    hit = _STORE.get(key)
    if not hit:
        return None
    ts, val = hit
    if time.monotonic() - ts > STALE_TTL:
        _STORE.pop(key, None)
        return None
    return val


def cache_set(key: str, val: Any) -> None:
    if len(_STORE) > 300:   # bounded — dashboards only, keys are filter combos
        _STORE.clear()
    _STORE[key] = (time.monotonic(), val)


def cache_clear() -> None:
    _STORE.clear()


# ── Persistent L2 (Mongo) ────────────────────────────────────────────────────
# The in-process cache above is wiped on every process restart and is per-pod, so
# right after a redeploy (or on any freshly-scaled pod) the FIRST viewer runs the
# heavy full-collection aggregation on the request path — which, at production
# scale, can exceed the request timeout and leave the dashboard stuck on
# "Loading…". A tiny Mongo-backed L2 fixes this: once ANY pod has computed a view,
# the value is persisted and every cold pod / restart serves it instantly and
# revalidates in the background. Never blocks or raises — pure availability layer.
_L2_MAX_AGE = 24 * 3600.0   # serve a persisted value up to 24h old while revalidating


def _l2_id(key: str) -> str:
    return "dc:" + hashlib.sha1(key.encode("utf-8")).hexdigest()


async def _l2_get(key: str):
    """Return (value, age_seconds) if a persisted value < _L2_MAX_AGE exists, else None."""
    try:
        from database import db
        doc = await db["dash_cache_l2"].find_one({"_id": _l2_id(key)})
    except Exception:
        return None
    if not doc:
        return None
    age = time.time() - doc.get("computed_at", 0)
    if age > _L2_MAX_AGE:
        return None
    return doc.get("value"), age


async def _l2_set(key: str, value: Any) -> None:
    try:
        from database import db
        await db["dash_cache_l2"].replace_one(
            {"_id": _l2_id(key)},
            {"_id": _l2_id(key), "value": value, "computed_at": time.time()},
            upsert=True,
        )
    except Exception:
        pass


def _schedule_refresh(key: str, fn, args, kwargs) -> None:
    if key in _REFRESHING:
        return
    _REFRESHING.add(key)

    async def _refresh():
        try:
            val = await fn(*args, **kwargs)
            cache_set(key, val)
            await _l2_set(key, val)
        except Exception:
            pass
        finally:
            _REFRESHING.discard(key)

    asyncio.create_task(_refresh())


def dash_cache(prefix: str, ttl: int = DEFAULT_TTL):
    def deco(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            parts = []
            for k, v in sorted(kwargs.items()):
                if isinstance(v, (str, int, float, bool, type(None))):
                    parts.append(f"{k}={v}")
                elif hasattr(v, "model_dump_json"):
                    parts.append(f"{k}={v.model_dump_json()}")
            key = prefix + "|" + "|".join(parts)
            hit = cache_get(key, ttl)
            if hit is not None:
                return hit
            # L1 stale-while-revalidate: serve the last in-process value instantly.
            stale = cache_get_stale(key)
            if stale is not None:
                _schedule_refresh(key, fn, args, kwargs)
                return stale
            # L1 fully cold (fresh pod / after a restart or redeploy). Fall back to
            # the PERSISTENT L2 (Mongo) so a cold pod never runs the heavy
            # full-collection scan on the request path — the #1 cause of dashboards
            # hanging on "Loading…" at production scale. Serve the persisted value
            # instantly and revalidate in the background if past the fresh TTL.
            l2 = await _l2_get(key)
            if l2 is not None:
                val, age = l2
                cache_set(key, val)
                if age > ttl:
                    _schedule_refresh(key, fn, args, kwargs)
                return val
            # Nothing cached anywhere: compute once on the request path and persist
            # to both layers so every subsequent (and every future cold-pod) view is instant.
            result = await fn(*args, **kwargs)
            cache_set(key, result)
            await _l2_set(key, result)
            return result
        # CRITICAL: FastAPI reads the VISIBLE signature to decide query vs body
        # binding, and resolves string annotations against the WRAPPER's module
        # globals (where the endpoint's Pydantic models don't exist). Copy the
        # signature WITH annotations already resolved from the original fn,
        # otherwise body models degrade to query params → 422.
        sig = inspect.signature(fn)
        try:
            hints = typing.get_type_hints(fn)
            sig = sig.replace(parameters=[
                p.replace(annotation=hints.get(name, p.annotation))
                for name, p in sig.parameters.items()
            ])
        except Exception:
            pass
        wrapper.__signature__ = sig
        return wrapper
    return deco
