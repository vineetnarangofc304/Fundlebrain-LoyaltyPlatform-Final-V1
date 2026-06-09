"""Iteration 56 — Historical 'stores' upload accepts the same CSV as the Stores
module (lowercase headers), makes City optional, and uppercases codes.

Regression for: Historical stores upload SKIPPED ALL rows because the mapper
only read TitleCase headers (Name/City) and required City, while the user's file
used the Stores-page format (lowercase code,name,city,...).
"""
import asyncio, sys
sys.path.insert(0, "/app/backend")
from datetime import datetime, timezone
from database import stores_col
from routes.historic_routes import _run_ingest_job, historic_jobs_col, _map_store_row

CODES = ["K91001", "K91002", "K91003"]
CSV = "code,name,city,state\nk91001,Kazo Test One,Pune,MH\nK91002,Kazo Test Two,Delhi,DL\nK91003,Kazo No City,,\n"


def test_mapper_handles_both_casings_and_optional_city():
    # lowercase headers (Stores-page format) — previously skipped
    doc, err = _map_store_row({"code": "k00078", "name": "Kazo Phoenix", "city": "Pune"})
    assert err is None and doc["code"] == "K00078", (doc, err)   # uppercased
    # TitleCase headers (legacy historical format)
    doc, err = _map_store_row({"Store Code": "K00055", "Name": "Kazo Saket", "City": "Delhi"})
    assert err is None and doc["code"] == "K00055"
    # no city → no longer skipped
    doc, err = _map_store_row({"code": "F00028", "name": "Franchise Surat"})
    assert err is None and doc["city"] is None
    # code only → name derived
    doc, err = _map_store_row({"code": "K00033"})
    assert err is None and doc["name"]
    # totally empty → skip
    doc, err = _map_store_row({"foo": "bar"})
    assert doc is None and err


def test_ingest_lowercase_store_csv_upsert():
    async def run():
        await stores_col.delete_many({"code": {"$in": CODES}})
        await historic_jobs_col.update_one({"id": "store_ing"}, {"$set": {
            "id": "store_ing", "dataset": "stores", "filename": "s.csv", "status": "running",
            "queued_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
        await _run_ingest_job("store_ing", "stores", CSV, "upsert", False)
        j = await historic_jobs_col.find_one({"id": "store_ing"}, {"_id": 0})
        rows = await stores_col.find({"code": {"$in": CODES}}).to_list(10)
        assert len(rows) == 3, f"expected 3 stores, got {len(rows)}"
        assert j["skipped"] == 0, f"expected 0 skipped, got {j['skipped']}"
        await stores_col.delete_many({"code": {"$in": CODES}})
        await historic_jobs_col.delete_many({"id": "store_ing"})
    asyncio.run(run())


if __name__ == "__main__":
    test_mapper_handles_both_casings_and_optional_city()
    test_ingest_lowercase_store_csv_upsert()
    print("PASS: store master loads via Historical upload (both header casings, optional city)")
