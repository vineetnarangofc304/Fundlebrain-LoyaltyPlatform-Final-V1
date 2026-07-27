"""Background dashboard cache warmer.

Pre-computes the heaviest default dashboard views (all-time Sales Report,
Command Center, cohort-library ATV context, analytics tabs) so the FIRST
visitor after a deploy/restart never stares at a 10-20 s "Loading…" screen.

Runs as an asyncio task started from server startup (only when enabled):
  - OFF by default (CACHE_WARMER_ENABLED=false) — the _dash_cache
    stale-while-revalidate layer already keeps views served, so proactive
    warming is opt-in to avoid adding steady full-scan load to the DB.
  - when enabled: waits 10 s for the app to bind, mints a short-lived
    super-admin JWT, hits each endpoint via localhost, and repeats every
    WARM_INTERVAL_S (default 30 min). The _dash_cache fresh TTL is >= this
    interval so a warmed view stays served between passes; anything older is
    covered by the stale-while-revalidate layer in _dash_cache.
"""
import asyncio
import logging
import os

import httpx

logger = logging.getLogger("kazo-fundle.cache_warmer")


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# Opt-in: the SWR cache keeps dashboards served without a warmer, so this is OFF
# by default to avoid steady background full-scan load on the shared DB.
CACHE_WARMER_ENABLED = _env_bool("CACHE_WARMER_ENABLED", False)

# Trimmed to just the two cheapest/most-hit default views. Everything else is
# populated on-demand and kept warm by _dash_cache's stale-while-revalidate.
WARM_PATHS = [
    "/api/dashboard/command-center?period=all",
    "/api/dashboard/kpis",
]

# How often to re-warm. Default 30 min; must stay <= the _dash_cache fresh TTL.
WARM_INTERVAL_S = int(os.environ.get("WARM_INTERVAL_S", "1800"))
BASE = "http://localhost:8001"


async def _mint_token() -> str | None:
    from database import users_col
    from auth import create_token
    email = os.environ.get("SUPER_ADMIN_EMAIL", "superadmin@fundle.io").lower()
    u = await users_col.find_one({"email": email}, {"_id": 0, "id": 1, "role": 1, "email": 1})
    if not u:
        return None
    return create_token(u["id"], u["role"], u["email"])


async def warm_loop() -> None:
    if not CACHE_WARMER_ENABLED:
        logger.info("cache warmer disabled (set CACHE_WARMER_ENABLED=true to enable)")
        return
    await asyncio.sleep(10)   # let uvicorn bind + indexes kick off
    logger.info(f"cache warmer enabled — {len(WARM_PATHS)} path(s) every {WARM_INTERVAL_S}s")
    while True:
        try:
            token = await _mint_token()
            if token:
                headers = {"Authorization": f"Bearer {token}"}
                async with httpx.AsyncClient(base_url=BASE, headers=headers,
                                             timeout=180) as client:
                    for path in WARM_PATHS:
                        try:
                            r = await client.get(path)
                            if r.status_code != 200:
                                logger.info(f"warm {path} -> {r.status_code}")
                        except Exception as e:
                            logger.info(f"warm {path} failed: {e}")
                        await asyncio.sleep(2)   # be gentle on the DB
        except Exception as e:
            logger.warning(f"cache warm cycle failed: {e}")
        await asyncio.sleep(WARM_INTERVAL_S)
