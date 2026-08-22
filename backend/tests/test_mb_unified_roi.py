import asyncio
import uuid
from datetime import datetime, timezone

from database import campaigns_col, db
from routes.campaigns_routes import register_mb_campaign, campaign_datasets_col
from routes.blacklist_util import blacklist_col, dlr_stats_col


async def go():
    cid = uuid.uuid4().hex
    bad = "9800000009"
    good1, good2 = "9800000001", "9800000002"
    # blacklist one number → it must be excluded from the frozen dataset
    await blacklist_col.update_one({"mobile": bad},
        {"$set": {"mobile": bad, "source": "manual", "reason": "test"}}, upsert=True)
    t0 = datetime.now(timezone.utc).isoformat()
    spec = {"mode": "mobiles", "mobiles": [good1, good2, bad], "label": "explicit list"}
    frozen = await register_mb_campaign(
        cid=cid, name="[Master Brain] QA", spec=spec, count=3, t0=t0,
        created_by="qa@test", template_id=None, message="hi {{name}}",
        audience_type="mobiles", audience_label="explicit list",
        objective="store", objective_params={"store_codes": ["K00055"]},
        roi_window="3d", cost=1000)

    core = await campaigns_col.find_one({"id": cid}, {"_id": 0})
    ds = await campaign_datasets_col.find_one({"campaign_id": cid}, {"_id": 0})
    print("frozen size:", frozen)
    print("core exists:", bool(core), "| source:", core.get("source"), "| objective:", core.get("objective"),
          "| roi_window:", core.get("roi_window"), "| cost:", core.get("cost"), "| status:", core.get("status"))
    print("dataset mobiles:", ds.get("mobiles"))
    assert core and core.get("source") == "master_brain", "core campaign not registered"
    assert core.get("objective") == "store" and core.get("cost") == 1000
    assert bad not in (ds.get("mobiles") or []), "blacklisted number leaked into dataset"
    assert set(ds.get("mobiles")) == {good1, good2}, "dataset mobiles wrong"
    print("PASS: MB campaign unified into core pipeline; blacklisted number excluded from frozen dataset")

    # cleanup
    await campaigns_col.delete_one({"id": cid})
    await campaign_datasets_col.delete_one({"campaign_id": cid})
    await blacklist_col.delete_one({"mobile": bad})
    await dlr_stats_col.delete_one({"mobile": bad})
    print("cleaned up")


if __name__ == "__main__":
    asyncio.run(go())
