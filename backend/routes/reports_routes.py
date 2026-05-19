"""Report builder + audit logs + transactions."""
from datetime import datetime, timezone, timedelta
from typing import Optional
import base64
import csv
import io
from fastapi import APIRouter, Depends, Response, HTTPException, Query
from fastapi.responses import StreamingResponse
from database import transactions_col, audit_logs_col, customers_col, stores_col, db
from auth import get_current_user

router = APIRouter(prefix="/reports", tags=["reports"])
digest_reports_col = db["digest_reports"]


# ---------------- Scheduled executive digest ----------------
@router.get("/digests")
async def list_digests(limit: int = 30, user: dict = Depends(get_current_user)):
    rows = await digest_reports_col.find(
        {}, {"_id": 0, "pdf_base64": 0}
    ).sort("generated_at", -1).limit(min(limit, 60)).to_list(60)
    return {"rows": rows, "total": len(rows)}


@router.get("/digests/latest")
async def latest_digest(user: dict = Depends(get_current_user)):
    d = await digest_reports_col.find_one({}, {"_id": 0, "pdf_base64": 0},
                                            sort=[("generated_at", -1)])
    if not d:
        raise HTTPException(404, "No digest generated yet — first run will be Monday 09:00 IST or trigger via /reports/digests/run-now")
    return d


@router.get("/digests/{digest_id}/download")
async def download_digest(digest_id: str, user: dict = Depends(get_current_user)):
    d = await digest_reports_col.find_one({"id": digest_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Digest not found")
    pdf_bytes = base64.b64decode(d["pdf_base64"])
    return StreamingResponse(
        io.BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{d["filename"]}"'},
    )


@router.post("/digests/run-now")
async def run_digest_now(period_days: int = 7, user: dict = Depends(get_current_user)):
    if user["role"] not in {"super_admin", "brand_admin"}:
        raise HTTPException(403, "Only brand_admin / super_admin can trigger digest")
    from scheduler import _build_and_store_digest
    res = await _build_and_store_digest(period_days=period_days,
                                          triggered_by=f"manual:{user['email']}")
    return res


@router.get("/transactions")
async def transactions_report(
    period_days: int = 30, store_id: Optional[str] = None,
    customer_id: Optional[str] = None, limit: int = 500, skip: int = 0,
    user: dict = Depends(get_current_user)
):
    start = (datetime.now(timezone.utc) - timedelta(days=period_days)).isoformat()
    fil = {"bill_date": {"$gte": start}}
    if store_id:
        fil["store_id"] = store_id
    if customer_id:
        fil["customer_id"] = customer_id
    total = await transactions_col.count_documents(fil)
    items = await transactions_col.find(fil, {"_id": 0}).sort("bill_date", -1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "items": items}


@router.get("/transactions/export")
async def export_transactions(period_days: int = 30, store_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    start = (datetime.now(timezone.utc) - timedelta(days=period_days)).isoformat()
    fil = {"bill_date": {"$gte": start}}
    if store_id:
        fil["store_id"] = store_id
    items = await transactions_col.find(fil, {"_id": 0}).sort("bill_date", -1).limit(50000).to_list(50000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["bill_number", "bill_date", "customer_mobile", "store_id", "gross_amount", "discount_amount", "net_amount", "points_earned", "payment_mode", "coupon_code"])
    for t in items:
        writer.writerow([t.get("bill_number"), t.get("bill_date"), t.get("customer_mobile"), t.get("store_id"),
                         t.get("gross_amount"), t.get("discount_amount"), t.get("net_amount"),
                         t.get("points_earned"), t.get("payment_mode"), t.get("coupon_code")])
    return Response(content=output.getvalue(), media_type="text/csv", headers={
        "Content-Disposition": f"attachment; filename=transactions_{period_days}d.csv"
    })


@router.get("/customers/export")
async def export_customers(tier: Optional[str] = None, city: Optional[str] = None, user: dict = Depends(get_current_user)):
    fil = {}
    if tier:
        fil["tier"] = tier
    if city:
        fil["city"] = city
    items = await customers_col.find(fil, {"_id": 0}).limit(100000).to_list(100000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["mobile", "name", "email", "city", "tier", "points_balance", "lifetime_spend", "visit_count", "last_visit_at", "churn_risk"])
    for c in items:
        writer.writerow([c.get("mobile"), c.get("name"), c.get("email"), c.get("city"), c.get("tier"),
                         c.get("points_balance"), c.get("lifetime_spend"), c.get("visit_count"),
                         c.get("last_visit_at"), c.get("churn_risk")])
    return Response(content=output.getvalue(), media_type="text/csv", headers={
        "Content-Disposition": "attachment; filename=customers.csv"
    })


@router.get("/audit-logs")
async def audit_logs(limit: int = 200, action: Optional[str] = None, user: dict = Depends(get_current_user)):
    fil = {}
    if action:
        fil["action"] = action
    return await audit_logs_col.find(fil, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)


# Custom report builder
@router.post("/custom")
async def run_custom_report(body: dict, user: dict = Depends(get_current_user)):
    """body: {entity: 'transactions'|'customers', metrics: [...], dimensions: [...], filters: {...}, period_days: 30}"""
    entity = body.get("entity", "transactions")
    period_days = int(body.get("period_days", 30))
    dim = body.get("dimensions", [])  # e.g. ['store_id', 'category']
    metrics = body.get("metrics", ["count", "sum_net"])
    fil = body.get("filters", {}) or {}

    if entity == "transactions":
        start = (datetime.now(timezone.utc) - timedelta(days=period_days)).isoformat()
        match = {"bill_date": {"$gte": start}}
        match.update(fil)
        group_id = {d: f"${d}" for d in dim} if dim else None
        group_stage = {"_id": group_id}
        if "count" in metrics:
            group_stage["count"] = {"$sum": 1}
        if "sum_net" in metrics:
            group_stage["sum_net"] = {"$sum": "$net_amount"}
        if "sum_gross" in metrics:
            group_stage["sum_gross"] = {"$sum": "$gross_amount"}
        if "avg_net" in metrics:
            group_stage["avg_net"] = {"$avg": "$net_amount"}
        if "unique_customers" in metrics:
            group_stage["unique_customers"] = {"$addToSet": "$customer_id"}
        pipe = [{"$match": match}, {"$group": group_stage}, {"$sort": {"sum_net": -1} if "sum_net" in metrics else {"count": -1}}, {"$limit": 500}]
        rows = await transactions_col.aggregate(pipe).to_list(500)
        for r in rows:
            if "unique_customers" in r:
                r["unique_customers"] = len(r["unique_customers"])
        return {"rows": rows}
    elif entity == "customers":
        group_id = {d: f"${d}" for d in dim} if dim else None
        group_stage = {"_id": group_id, "count": {"$sum": 1}, "sum_spend": {"$sum": "$lifetime_spend"}, "points_balance": {"$sum": "$points_balance"}}
        pipe = [{"$match": fil}, {"$group": group_stage}, {"$sort": {"sum_spend": -1}}, {"$limit": 500}]
        rows = await customers_col.aggregate(pipe).to_list(500)
        return {"rows": rows}
    return {"rows": []}
