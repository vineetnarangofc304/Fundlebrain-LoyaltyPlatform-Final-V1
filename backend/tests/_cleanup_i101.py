"""Cleanup helper for iteration 101 QA artefacts (test campaigns + datasets + blacklist)."""
import asyncio
import sys
sys.path.insert(0, "/app/backend")
from database import campaigns_col, db  # noqa: E402

datasets = db["campaign_datasets"]
blacklist = db["sms_blacklist"]
dlr_stats = db["dlr_mobile_stats"]


async def main():
    ids = [c["id"] async for c in campaigns_col.find({"name": {"$regex": "^TEST_QA"}}, {"id": 1})]
    print("campaigns:", ids)
    if ids:
        print("datasets removed:", (await datasets.delete_many({"campaign_id": {"$in": ids}})).deleted_count)
        print("campaigns removed:", (await campaigns_col.delete_many({"id": {"$in": ids}})).deleted_count)
    mobs = ["9812345670", "9877000555", "9877000556", "9877000557"]
    print("blacklist removed:", (await blacklist.delete_many({"mobile": {"$in": mobs}})).deleted_count)
    print("dlr stats removed:", (await dlr_stats.delete_many({"mobile": {"$in": mobs}})).deleted_count)


asyncio.run(main())
