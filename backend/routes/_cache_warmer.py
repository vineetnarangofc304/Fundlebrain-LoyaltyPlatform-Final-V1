"""Background dashboard cache warmer.

Pre-computes the heaviest default dashboard views (all-time Sales Report,
Command Center, cohort-library ATV context, analytics tabs) so the FIRST
visitor after a deploy/restart never stares at a 10-20 s "Loading…" screen.

Runs as an asyncio task started from server startup:
  - waits 10 s for the app to bind
  - mints a short-lived super-admin JWT and hits each endpoint via localhost
  - repeats every WARM_INTERVAL_S (< the 300 s fresh TTL) so the default
    views are permanently warm; non-default filter combos are covered by the
    stale-while-revalidate layer in _dash_cache.
"""
import asyncio
import logging
import os

import httpx

logger = logging.getLogger("kazo-fundle.cache_warmer")

WARM_PATHS = [
    "/api/dashboard/command-center?period=all",
    "/api/dashboard/kpis",
    "/api/dashboard/sales-trend?period=all",
    "/api/analytics/sales-dashboard?period_days=0",
    "/api/segments/cohort-library/",
    "/api/analytics/customer-dashboard",
    "/api/analytics/loyalty-dashboard",
    "/api/analytics/store-dashboard",
]
WARM_INTERVAL_S = 240
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
    await asyncio.sleep(10)   # let uvicorn bind + indexes kick off
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
