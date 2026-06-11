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
import inspect
import time
import typing
from typing import Any, Optional

_STORE: dict = {}
DEFAULT_TTL = 300   # seconds — "fresh" window
STALE_TTL = 3600    # seconds — serve-stale-while-revalidate window
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
            # Stale-while-revalidate: serve the last value instantly and
            # refresh in the background (heavy aggregations never block a view
            # that has been seen before — even after the fresh TTL expires).
            stale = cache_get_stale(key)
            if stale is not None:
                if key not in _REFRESHING:
                    _REFRESHING.add(key)

                    async def _refresh():
                        try:
                            cache_set(key, await fn(*args, **kwargs))
                        except Exception:
                            pass
                        finally:
                            _REFRESHING.discard(key)

                    asyncio.create_task(_refresh())
                return stale
            result = await fn(*args, **kwargs)
            cache_set(key, result)
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
