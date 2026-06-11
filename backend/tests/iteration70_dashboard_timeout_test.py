"""Iteration 70 — Dashboard aggregation timeout fix (production MaxTimeMSExpired).

Production Atlas uses an aggressive `timeoutMS` (e.g. 10s). The customer-dashboard ran 9
sequential full-scan aggregations on customers and blew past it (pymongo ExecutionTimeout /
MaxTimeMSExpired), 500-ing the endpoint. Fixes:
  1. The 7 heavy bucketing aggregations are collapsed into ONE $facet (single scan).
  2. A `db_deadline` dependency wraps analytics/dashboard requests in pymongo.timeout(45),
     overriding the aggressive client timeoutMS for these heavy endpoints (verified to
     propagate through Motor).

Run: pytest -q backend/tests/iteration70_dashboard_timeout_test.py
"""
import os
import asyncio
import httpx
import pymongo
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ExecutionTimeout
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

BASE = "http://localhost:8001/api"


def test_pymongo_timeout_overrides_client_timeoutms():
    """The mechanism behind the production fix: pymongo.timeout() overrides an aggressive
    client timeoutMS and propagates through Motor so heavy aggregations can complete."""
    async def _run():
        pipe = [{"$group": {"_id": "$churn_risk", "count": {"$sum": 1}}}]
        # Baseline result from a normal client.
        normal = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        expected = await normal["customers"].aggregate(pipe, allowDiskUse=True).to_list(10)
        # Simulate production: an aggressive 1ms client timeout. WITHOUT the override this
        # is liable to time out; WITH pymongo.timeout() it must reliably complete and match.
        tight = AsyncIOMotorClient(os.environ["MONGO_URL"], timeoutMS=1)[os.environ["DB_NAME"]]
        with pymongo.timeout(30):
            rows = await tight["customers"].aggregate(pipe, allowDiskUse=True).to_list(10)
        assert len(rows) == len(expected), (rows, expected)
    asyncio.run(_run())


def test_customer_dashboard_facet_structure_and_consistency():
    """The $facet rewrite returns the same shape and internally-consistent buckets."""
    async def _run():
        async with httpx.AsyncClient(timeout=60.0) as cli:
            login = await cli.post(f"{BASE}/auth/login",
                                   json={"email": "superadmin@fundle.io", "password": "Fundle@2026"})
            token = login.json()["token"]
            h = {"Authorization": f"Bearer {token}"}
            r = await cli.get(f"{BASE}/analytics/customer-dashboard", headers=h)
            assert r.status_code == 200, r.text
            d = r.json()
            for k in ["churn_distribution", "city_distribution", "health_distribution",
                      "lifecycle_split", "new_customer_trend", "one_timer_recency_distribution",
                      "recency_distribution", "top_customers", "visit_frequency"]:
                assert k in d, f"missing key {k}"
            # health buckets are exactly the canonical 5, in order
            assert [b["bucket"] for b in d["health_distribution"]] == \
                ["Healthy", "Slipping", "At Risk", "Lost", "Never transacted"]
            # recency buckets are the canonical 6
            assert [b["bucket"] for b in d["recency_distribution"]] == \
                ["0-7d", "8-30d", "31-90d", "91-180d", "181-365d", "365d+"]
            # consistency: "Never transacted" (null last_visit) == lifecycle zero_bill count,
            # and recency total (non-null last_visit) == health(total) - never-transacted.
            never = next(b["count"] for b in d["health_distribution"] if b["bucket"] == "Never transacted")
            health_total = sum(b["count"] for b in d["health_distribution"])
            recency_total = sum(b["count"] for b in d["recency_distribution"])
            assert never == d["lifecycle_split"]["zero_bill"]["count"], (never, d["lifecycle_split"])
            assert recency_total == health_total - never, (recency_total, health_total, never)
    asyncio.run(_run())
