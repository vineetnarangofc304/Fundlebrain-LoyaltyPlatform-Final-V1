"""CSV ↔ Database reconciliation engine.

Lets an admin re-upload an original source CSV (transactions / customers /
items) and produces a row-level reconciliation report against what is
actually in MongoDB:

  • csv_rows / parse_failed / duplicate_keys_in_csv
  • matched / missing_in_db (rows in CSV but absent from DB)
  • amount_mismatches (bill present but net amount differs)
  • extra_in_db (records in DB that are NOT in the CSV)
  • sum-of-amount totals on both sides

Uses the same chunked-upload pattern as the historic loader (10MB chunks via
Mongo so any pod can serve any chunk) and the SAME row mappers, so the key
normalisation (mobile digits, bill number trim) is identical to what ingest
did — a row only counts as "missing" when ingest itself would have keyed it
the same way.
"""
import asyncio
import csv
import io
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth import get_current_user
from database import db, transactions_col, customers_col
from routes._db_timeout import db_deadline
from routes.historic_routes import (
    MAX_FILE_BYTES, _map_customer_row, _map_item_row, _map_transaction_row,
    _norm_mobile, _stitch_and_decode, historic_chunks_col,
)

logger = logging.getLogger("kazo-fundle.recon")

router = APIRouter(prefix="/recon", tags=["recon"], dependencies=[Depends(db_deadline)])

recon_jobs_col = db["recon_jobs"]
recon_mismatch_col = db["recon_mismatches"]

RECON_DATASETS = {"transactions", "customers", "items"}
MISMATCH_DETAIL_CAP = 5000  # rows persisted for CSV download (per job)
SAMPLE_CAP = 200            # rows embedded in the JSON report
STALE_RECON_MINUTES = 8     # a "running" job with no heartbeat for this long is auto-failed
HEARTBEAT_EVERY_BATCHES = 5  # write progress/heartbeat every N batches during DB compare


class ReconInitIn(BaseModel):
    dataset: str
    filename: str
    total_chunks: int
    total_bytes: int = 0
    deep_scan: bool = False  # also scan the WHOLE DB for rows not in the CSV (heavier)


class ReconFinalizeIn(BaseModel):
    job_id: str


@router.post("/init")
async def recon_init(body: ReconInitIn, user: dict = Depends(get_current_user)):
    if user["role"] not in {"super_admin", "brand_admin", "crm_manager"}:
        raise HTTPException(403, "Only admin / CRM roles can run reconciliation")
    if body.dataset not in RECON_DATASETS:
        raise HTTPException(400, f"dataset must be one of {sorted(RECON_DATASETS)}")
    if body.total_chunks < 1 or body.total_chunks > 10_000:
        raise HTTPException(400, "total_chunks out of range")
    if not (body.filename.lower().endswith(".csv") or body.filename.lower().endswith(".xlsx")):
        raise HTTPException(400, "Only .csv and .xlsx files supported")
    if body.total_bytes > MAX_FILE_BYTES:
        raise HTTPException(413, f"File too large (max {MAX_FILE_BYTES // (1024*1024)} MB)")
    job_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": job_id, "kind": "recon", "dataset": body.dataset,
        "filename": body.filename, "status": "uploading",
        "total_chunks": body.total_chunks, "chunks_uploaded": 0,
        "processed": 0, "phase": "uploading", "deep_scan": bool(body.deep_scan),
        "queued_at": now, "queued_by": user["email"], "heartbeat": now,
        "report": None,
    }
    await recon_jobs_col.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.post("/chunk")
async def recon_chunk(
    job_id: str = Form(...),
    chunk_index: int = Form(...),
    chunk: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    job = await recon_jobs_col.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Recon job not found")
    if job.get("status") != "uploading":
        raise HTTPException(400, f"Job is not in uploading state (status={job.get('status')})")
    if chunk_index < 0 or chunk_index >= job.get("total_chunks", 1):
        raise HTTPException(400, "chunk_index out of range")
    data = await chunk.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "Single chunk too large (max 10MB per chunk)")
    result = await historic_chunks_col.update_one(
        {"job_id": job_id, "chunk_index": chunk_index},
        {"$set": {"job_id": job_id, "chunk_index": chunk_index, "data": data, "size": len(data)}},
        upsert=True,
    )
    if result.upserted_id is not None:
        await recon_jobs_col.update_one({"id": job_id}, {"$inc": {"chunks_uploaded": 1}})
    return {"ok": True, "chunk_index": chunk_index}


@router.post("/finalize")
async def recon_finalize(body: ReconFinalizeIn, user: dict = Depends(get_current_user)):
    job = await recon_jobs_col.find_one({"id": body.job_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Recon job not found")
    if job.get("status") != "uploading":
        raise HTTPException(400, f"Job is not in uploading state (status={job.get('status')})")
    expected = job.get("total_chunks", 0)
    found = await historic_chunks_col.count_documents({"job_id": body.job_id})
    if found != expected:
        raise HTTPException(400, f"Chunk count mismatch — expected {expected}, found {found}.")
    await recon_jobs_col.update_one(
        {"id": body.job_id},
        {"$set": {"status": "running", "phase": "parsing",
                  "heartbeat": datetime.now(timezone.utc).isoformat()}})
    asyncio.create_task(_run_recon_job(body.job_id))
    return {"ok": True, "job_id": body.job_id, "status": "running"}


# --------------------------------------------------- stale-job recovery ----
async def _recover_stale_recon_jobs():
    """Auto-fail recon jobs stuck in 'running'/'uploading' with no recent heartbeat.

    The job body runs as an ``asyncio.create_task`` — a pod restart / redeploy
    orphans it, leaving the row 'running' forever (the UI then polls it
    indefinitely). This watchdog, called whenever the jobs list is read, marks
    any such zombie 'failed' so the page clears."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=STALE_RECON_MINUTES)).isoformat()
    res = await recon_jobs_col.update_many(
        {"status": {"$in": ["running", "uploading"]},
         "$and": [
             {"$or": [{"heartbeat": {"$exists": False}}, {"heartbeat": None},
                      {"heartbeat": {"$lt": cutoff}}]},
             {"$or": [{"queued_at": {"$exists": False}}, {"queued_at": {"$lt": cutoff}}]},
         ]},
        {"$set": {"status": "failed",
                  "error": f"Stalled — no progress for over {STALE_RECON_MINUTES} min "
                           "(likely a server restart mid-run). Please re-run.",
                  "finished_at": datetime.now(timezone.utc).isoformat()}})
    if res.modified_count:
        logger.warning(f"recovered {res.modified_count} stale recon job(s) → failed")


@router.get("/jobs")
async def recon_jobs(user: dict = Depends(get_current_user)):
    await _recover_stale_recon_jobs()
    rows = await recon_jobs_col.find({}, {"_id": 0}).sort("queued_at", -1).limit(20).to_list(20)
    return {"jobs": rows}


@router.get("/jobs/{job_id}")
async def recon_job_detail(job_id: str, user: dict = Depends(get_current_user)):
    await _recover_stale_recon_jobs()
    job = await recon_jobs_col.find_one({"id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Recon job not found")
    return job


@router.post("/jobs/{job_id}/cancel")
async def recon_cancel(job_id: str, user: dict = Depends(get_current_user)):
    if user["role"] not in {"super_admin", "brand_admin", "crm_manager"}:
        raise HTTPException(403, "Only admin / CRM roles can cancel reconciliation")
    job = await recon_jobs_col.find_one({"id": job_id}, {"_id": 0, "status": 1})
    if not job:
        raise HTTPException(404, "Recon job not found")
    if job.get("status") not in {"running", "uploading"}:
        raise HTTPException(400, f"Job is not cancellable (status={job.get('status')})")
    await recon_jobs_col.update_one(
        {"id": job_id},
        {"$set": {"status": "failed", "error": f"Cancelled by {user['email']}",
                  "finished_at": datetime.now(timezone.utc).isoformat()}})
    # background task checks this flag at safe points and stops; clean up chunks
    await recon_jobs_col.update_one({"id": job_id}, {"$set": {"cancel_requested": True}})
    await historic_chunks_col.delete_many({"job_id": job_id})
    return {"ok": True, "job_id": job_id, "status": "failed"}


@router.get("/jobs/{job_id}/mismatches.csv")
async def recon_mismatch_csv(job_id: str, user: dict = Depends(get_current_user)):
    job = await recon_jobs_col.find_one({"id": job_id}, {"_id": 0, "id": 1})
    if not job:
        raise HTTPException(404, "Recon job not found")

    async def _gen():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["type", "key", "csv_value", "db_value", "detail"])
        yield buf.getvalue()
        async for m in recon_mismatch_col.find({"job_id": job_id}, {"_id": 0}).sort("type", 1):
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow([m.get("type"), m.get("key"), m.get("csv_value"), m.get("db_value"), m.get("detail")])
            yield buf.getvalue()

    return StreamingResponse(_gen(), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="recon_mismatches_{job_id[:8]}.csv"'})


# ---------------------------------------------------------------- engine ----

async def _fail(job_id: str, reason: str):
    await recon_jobs_col.update_one(
        {"id": job_id},
        {"$set": {"status": "failed", "error": reason,
                  "finished_at": datetime.now(timezone.utc).isoformat()}})


async def _run_recon_job(job_id: str):
    try:
        job = await recon_jobs_col.find_one({"id": job_id}, {"_id": 0})
        if not job:
            return
        dataset = job["dataset"]
        deep_scan = bool(job.get("deep_scan"))
        await _heartbeat(job_id, phase="stitching")
        # stitch chunks
        parts: List[bytes] = []
        async for c in historic_chunks_col.find(
                {"job_id": job_id}, {"_id": 0, "data": 1}).sort("chunk_index", 1):
            parts.append(c["data"])
        if not parts:
            return await _fail(job_id, "No uploaded chunks found")
        try:
            text = await asyncio.to_thread(_stitch_and_decode, parts, job.get("filename", "recon.csv"))
        except Exception as e:
            return await _fail(job_id, f"Could not decode file: {e}")
        parts = None  # free memory

        if await _is_cancelled(job_id):
            return

        if dataset == "transactions":
            report = await _recon_transactions(job_id, text, deep_scan)
        elif dataset == "customers":
            report = await _recon_customers(job_id, text, deep_scan)
        else:
            report = await _recon_items(job_id, text, deep_scan)

        await recon_jobs_col.update_one(
            {"id": job_id},
            {"$set": {"status": "done", "phase": "done", "report": report,
                      "heartbeat": datetime.now(timezone.utc).isoformat(),
                      "finished_at": datetime.now(timezone.utc).isoformat()}})
    except _Cancelled:
        logger.info(f"recon job {job_id} cancelled")
    except Exception as e:
        logger.exception(f"recon job {job_id} crashed")
        await _fail(job_id, str(e)[:500])
    finally:
        await historic_chunks_col.delete_many({"job_id": job_id})


async def _record_mismatches(job_id: str, rows: List[Dict[str, Any]]):
    if rows:
        await recon_mismatch_col.insert_many(
            [{**r, "job_id": job_id} for r in rows], ordered=False)


async def _progress(job_id: str, processed: int, phase: Optional[str] = None):
    upd = {"processed": processed, "heartbeat": datetime.now(timezone.utc).isoformat()}
    if phase:
        upd["phase"] = phase
    await recon_jobs_col.update_one({"id": job_id}, {"$set": upd})


async def _heartbeat(job_id: str, phase: Optional[str] = None):
    upd = {"heartbeat": datetime.now(timezone.utc).isoformat()}
    if phase:
        upd["phase"] = phase
    await recon_jobs_col.update_one({"id": job_id}, {"$set": upd})


async def _is_cancelled(job_id: str) -> bool:
    j = await recon_jobs_col.find_one({"id": job_id}, {"_id": 0, "cancel_requested": 1, "status": 1})
    return bool(j) and (j.get("cancel_requested") or j.get("status") == "failed")


class _Cancelled(Exception):
    pass


def _parse_transactions_csv(text: str):
    """Pure-CPU parse (runs in a worker thread so it never blocks the loop)."""
    reader = csv.DictReader(io.StringIO(text))
    store_cache: Dict[str, Dict[str, Any]] = {}
    csv_map: Dict[str, Dict[str, Any]] = {}      # bill_number -> {net, mobile}
    total_rows = parse_failed = dup_keys = 0
    csv_net_sum = 0.0
    for r in reader:
        total_rows += 1
        doc, err = _map_transaction_row(r, store_cache)
        if err or not doc:
            parse_failed += 1
            continue
        key = doc["bill_number"]
        net = float(doc.get("net_amount") or 0)
        csv_net_sum += net
        if key in csv_map:
            dup_keys += 1
            csv_map[key]["net"] += net   # CSV may carry one row per line item
        else:
            csv_map[key] = {"net": net, "mobile": doc.get("customer_mobile")}
    return csv_map, total_rows, parse_failed, dup_keys, csv_net_sum


async def _recon_transactions(job_id: str, text: str, deep_scan: bool = False) -> Dict[str, Any]:
    await _heartbeat(job_id, phase="parsing")
    csv_map, total_rows, parse_failed, dup_keys, csv_net_sum = await asyncio.to_thread(
        _parse_transactions_csv, text)
    await _progress(job_id, total_rows, phase="comparing")
    if await _is_cancelled(job_id):
        raise _Cancelled()

    # ---- CSV → DB pass (batched $in on the indexed bill_number) ----
    missing, amount_mm, mobile_mm = [], [], []
    matched = 0
    db_net_for_matched = 0.0
    keys = list(csv_map.keys())
    for bi, i in enumerate(range(0, len(keys), 1000)):
        batch = keys[i:i + 1000]
        found: Dict[str, Dict[str, Any]] = {}
        async for t in transactions_col.find(
                {"bill_number": {"$in": batch}},
                {"_id": 0, "bill_number": 1, "net_amount": 1, "customer_mobile": 1}):
            found[t["bill_number"]] = t
        for k in batch:
            cv = csv_map[k]
            t = found.get(k)
            if not t:
                if len(missing) < MISMATCH_DETAIL_CAP:
                    missing.append({"type": "missing_in_db", "key": k,
                                    "csv_value": round(cv["net"], 2), "db_value": None,
                                    "detail": f"mobile={cv.get('mobile') or '-'}"})
                continue
            matched += 1
            db_net = float(t.get("net_amount") or 0)
            db_net_for_matched += db_net
            if abs(db_net - cv["net"]) > 0.01:
                if len(amount_mm) < MISMATCH_DETAIL_CAP:
                    amount_mm.append({"type": "amount_mismatch", "key": k,
                                      "csv_value": round(cv["net"], 2),
                                      "db_value": round(db_net, 2),
                                      "detail": f"diff={round(cv['net'] - db_net, 2)}"})
            csv_mob = _norm_mobile(cv.get("mobile")) or None
            db_mob = _norm_mobile(t.get("customer_mobile")) or None
            if csv_mob != db_mob:
                if len(mobile_mm) < MISMATCH_DETAIL_CAP:
                    mobile_mm.append({"type": "mobile_mismatch", "key": k,
                                      "csv_value": csv_mob, "db_value": db_mob, "detail": ""})
        await asyncio.sleep(0)  # let live POS / dashboards breathe
        if bi % HEARTBEAT_EVERY_BATCHES == 0:
            await _progress(job_id, total_rows + i)
            if await _is_cancelled(job_id):
                raise _Cancelled()

    # ---- DB → CSV pass: bills in DB that are NOT in the CSV (heavy: full scan) ----
    extra_count: Optional[int] = None
    extra_sample: List[Dict[str, Any]] = []
    if deep_scan:
        await _heartbeat(job_id, phase="deep-scan")
        extra_count = 0
        csv_keys = set(csv_map)
        seen = 0
        async for t in transactions_col.find({}, {"_id": 0, "bill_number": 1, "net_amount": 1,
                                                  "source": 1}):
            seen += 1
            bn = t.get("bill_number")
            if bn and bn not in csv_keys:
                extra_count += 1
                if len(extra_sample) < MISMATCH_DETAIL_CAP:
                    extra_sample.append({"type": "extra_in_db", "key": bn,
                                         "csv_value": None,
                                         "db_value": round(float(t.get("net_amount") or 0), 2),
                                         "detail": f"source={t.get('source') or '-'}"})
            if seen % 20000 == 0:
                await asyncio.sleep(0)
                await _heartbeat(job_id)
                if await _is_cancelled(job_id):
                    raise _Cancelled()

    db_stats = await transactions_col.aggregate([
        {"$group": {"_id": None, "n": {"$sum": 1}, "net": {"$sum": "$net_amount"}}}
    ], allowDiskUse=True).to_list(1)
    db_total = (db_stats[0] if db_stats else {})

    detail = (missing + amount_mm + mobile_mm + extra_sample)[:MISMATCH_DETAIL_CAP]
    await _record_mismatches(job_id, detail)

    return {
        "dataset": "transactions",
        "deep_scan": deep_scan,
        "csv": {"rows": total_rows, "parse_failed": parse_failed,
                "unique_bills": len(csv_map), "duplicate_bill_rows": dup_keys,
                "net_sum": round(csv_net_sum, 2)},
        "db": {"total_bills": int(db_total.get("n", 0) or 0),
               "net_sum": round(float(db_total.get("net", 0) or 0), 2)},
        "matched": matched,
        "missing_in_db": len(csv_map) - matched,
        "amount_mismatches": len(amount_mm),
        "mobile_mismatches": len(mobile_mm),
        "extra_in_db": extra_count,
        "matched_db_net_sum": round(db_net_for_matched, 2),
        "samples": {
            "missing_in_db": missing[:SAMPLE_CAP],
            "amount_mismatches": amount_mm[:SAMPLE_CAP],
            "mobile_mismatches": mobile_mm[:SAMPLE_CAP],
            "extra_in_db": extra_sample[:SAMPLE_CAP],
        },
    }


def _parse_customers_csv(text: str):
    reader = csv.DictReader(io.StringIO(text))
    csv_map: Dict[str, Dict[str, Any]] = {}
    total_rows = parse_failed = dup_keys = 0
    for r in reader:
        total_rows += 1
        doc, err = _map_customer_row(r)
        if err or not doc:
            parse_failed += 1
            continue
        mob = doc["mobile"]
        if mob in csv_map:
            dup_keys += 1
        csv_map[mob] = {"lifetime_spend": float(doc.get("lifetime_spend") or 0),
                        "points_balance": int(doc.get("points_balance") or 0)}
    return csv_map, total_rows, parse_failed, dup_keys


async def _recon_customers(job_id: str, text: str, deep_scan: bool = False) -> Dict[str, Any]:
    await _heartbeat(job_id, phase="parsing")
    csv_map, total_rows, parse_failed, dup_keys = await asyncio.to_thread(
        _parse_customers_csv, text)
    await _progress(job_id, total_rows, phase="comparing")
    if await _is_cancelled(job_id):
        raise _Cancelled()

    missing, spend_mm, points_mm = [], [], []
    matched = 0
    keys = list(csv_map.keys())
    for bi, i in enumerate(range(0, len(keys), 1000)):
        batch = keys[i:i + 1000]
        found: Dict[str, Dict[str, Any]] = {}
        async for c in customers_col.find(
                {"mobile": {"$in": batch}},
                {"_id": 0, "mobile": 1, "lifetime_spend": 1, "points_balance": 1}):
            found[c["mobile"]] = c
        for k in batch:
            cv = csv_map[k]
            c = found.get(k)
            if not c:
                if len(missing) < MISMATCH_DETAIL_CAP:
                    missing.append({"type": "missing_in_db", "key": k,
                                    "csv_value": cv["lifetime_spend"], "db_value": None, "detail": ""})
                continue
            matched += 1
            if cv["lifetime_spend"] and abs(float(c.get("lifetime_spend") or 0) - cv["lifetime_spend"]) > 1:
                if len(spend_mm) < MISMATCH_DETAIL_CAP:
                    spend_mm.append({"type": "lifetime_spend_mismatch", "key": k,
                                     "csv_value": round(cv["lifetime_spend"], 2),
                                     "db_value": round(float(c.get("lifetime_spend") or 0), 2),
                                     "detail": "DB recomputes spend from bills (R3) — differences "
                                               "can be legitimate if bills CSV is the source of truth"})
            if cv["points_balance"] and abs(int(c.get("points_balance") or 0) - cv["points_balance"]) > 0:
                if len(points_mm) < MISMATCH_DETAIL_CAP:
                    points_mm.append({"type": "points_balance_mismatch", "key": k,
                                      "csv_value": cv["points_balance"],
                                      "db_value": int(c.get("points_balance") or 0), "detail": ""})
        await asyncio.sleep(0)
        if bi % HEARTBEAT_EVERY_BATCHES == 0:
            await _progress(job_id, total_rows + i)
            if await _is_cancelled(job_id):
                raise _Cancelled()

    extra_count: Optional[int] = None
    extra_sample: List[Dict[str, Any]] = []
    if deep_scan:
        await _heartbeat(job_id, phase="deep-scan")
        extra_count = 0
        csv_keys = set(csv_map)
        seen = 0
        async for c in customers_col.find({"mobile": {"$nin": [None, ""]}},
                                          {"_id": 0, "mobile": 1, "source": 1}):
            seen += 1
            mob = c.get("mobile")
            if mob and mob not in csv_keys:
                extra_count += 1
                if len(extra_sample) < MISMATCH_DETAIL_CAP:
                    extra_sample.append({"type": "extra_in_db", "key": mob, "csv_value": None,
                                         "db_value": None, "detail": f"source={c.get('source') or '-'}"})
            if seen % 20000 == 0:
                await asyncio.sleep(0)
                await _heartbeat(job_id)
                if await _is_cancelled(job_id):
                    raise _Cancelled()

    db_total = await customers_col.count_documents({"mobile": {"$nin": [None, ""]}})
    detail = (missing + spend_mm + points_mm + extra_sample)[:MISMATCH_DETAIL_CAP]
    await _record_mismatches(job_id, detail)

    return {
        "dataset": "customers",
        "deep_scan": deep_scan,
        "csv": {"rows": total_rows, "parse_failed": parse_failed,
                "unique_mobiles": len(csv_map), "duplicate_mobile_rows": dup_keys},
        "db": {"total_customers": db_total},
        "matched": matched,
        "missing_in_db": len(csv_map) - matched,
        "lifetime_spend_mismatches": len(spend_mm),
        "points_balance_mismatches": len(points_mm),
        "extra_in_db": extra_count,
        "samples": {
            "missing_in_db": missing[:SAMPLE_CAP],
            "lifetime_spend_mismatches": spend_mm[:SAMPLE_CAP],
            "points_balance_mismatches": points_mm[:SAMPLE_CAP],
            "extra_in_db": extra_sample[:SAMPLE_CAP],
        },
    }


def _parse_items_csv(text: str):
    reader = csv.DictReader(io.StringIO(text))
    csv_keys: set = set()
    total_rows = parse_failed = dup_keys = 0
    for r in reader:
        total_rows += 1
        doc, err = _map_item_row(r)
        if err or not doc:
            parse_failed += 1
            continue
        key = doc.get("sku") or doc.get("item_code")
        if not key:
            parse_failed += 1
            continue
        if key in csv_keys:
            dup_keys += 1
        csv_keys.add(key)
    return csv_keys, total_rows, parse_failed, dup_keys


async def _recon_items(job_id: str, text: str, deep_scan: bool = False) -> Dict[str, Any]:
    items_col = db["items"]
    await _heartbeat(job_id, phase="parsing")
    csv_keys, total_rows, parse_failed, dup_keys = await asyncio.to_thread(
        _parse_items_csv, text)
    await _progress(job_id, total_rows, phase="comparing")
    if await _is_cancelled(job_id):
        raise _Cancelled()

    missing = []
    matched = 0
    keys = list(csv_keys)
    for bi, i in enumerate(range(0, len(keys), 1000)):
        batch = keys[i:i + 1000]
        found = {d.get("sku") async for d in items_col.find(
            {"sku": {"$in": batch}}, {"_id": 0, "sku": 1})}
        for k in batch:
            if k in found:
                matched += 1
            elif len(missing) < MISMATCH_DETAIL_CAP:
                missing.append({"type": "missing_in_db", "key": k,
                                "csv_value": None, "db_value": None, "detail": ""})
        await asyncio.sleep(0)
        if bi % HEARTBEAT_EVERY_BATCHES == 0:
            await _progress(job_id, total_rows + i)
            if await _is_cancelled(job_id):
                raise _Cancelled()

    extra_count: Optional[int] = None
    extra_sample: List[Dict[str, Any]] = []
    if deep_scan:
        await _heartbeat(job_id, phase="deep-scan")
        extra_count = 0
        async for d in items_col.find({}, {"_id": 0, "sku": 1}):
            sku = d.get("sku")
            if sku and sku not in csv_keys:
                extra_count += 1
                if len(extra_sample) < MISMATCH_DETAIL_CAP:
                    extra_sample.append({"type": "extra_in_db", "key": sku,
                                         "csv_value": None, "db_value": None, "detail": ""})

    db_total = await items_col.count_documents({})
    await _record_mismatches(job_id, (missing + extra_sample)[:MISMATCH_DETAIL_CAP])
    return {
        "dataset": "items",
        "deep_scan": deep_scan,
        "csv": {"rows": total_rows, "parse_failed": parse_failed,
                "unique_skus": len(csv_keys), "duplicate_sku_rows": dup_keys},
        "db": {"total_items": db_total},
        "matched": matched,
        "missing_in_db": len(csv_keys) - matched,
        "extra_in_db": extra_count,
        "samples": {"missing_in_db": missing[:SAMPLE_CAP], "extra_in_db": extra_sample[:SAMPLE_CAP]},
    }
