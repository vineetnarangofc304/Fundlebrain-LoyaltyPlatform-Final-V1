"""Per-request MongoDB deadline override for heavy dashboard / analytics endpoints.

Production connects to Atlas with an aggressive client-side timeout baked into the
connection string (e.g. `timeoutMS=10000`). That 10s applies to EVERY operation, which is
fine for transactional/POS calls but too short for the large dashboard aggregations on the
production-scale dataset — they were failing with `MaxTimeMSExpired` (pymongo
`ExecutionTimeout`) and 500-ing the dashboards.

`pymongo.timeout()` overrides the client `timeoutMS` for the duration of the block, and it
propagates correctly through Motor (verified). We expose it as a FastAPI dependency so it can
be attached to the analytics / dashboard routers, giving those (and only those) endpoints a
generous deadline without touching every query site. The ceiling stays under the typical
ingress/proxy timeout so a genuinely-stuck query still returns rather than hanging.
"""
import pymongo
from fastapi import Depends

# Generous enough for full-collection aggregations on millions of rows, but below the
# ingress timeout so a runaway query fails fast instead of hanging the request.
HEAVY_QUERY_DEADLINE_SECONDS = 45


async def db_deadline():
    """Dependency: run the request's DB operations under a longer deadline than the
    aggressive production `timeoutMS`, so large dashboard aggregations don't MaxTimeMSExpired."""
    with pymongo.timeout(HEAVY_QUERY_DEADLINE_SECONDS):
        yield
