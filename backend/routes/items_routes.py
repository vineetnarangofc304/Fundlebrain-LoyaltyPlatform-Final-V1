"""Item master (SKU + Category) routes."""
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from database import db
from auth import get_current_user, require_roles, log_audit, MANAGEMENT_ROLES, ADMIN_ROLES
import csv
import io
import uuid

router = APIRouter(prefix="/items", tags=["items"])

items_col = db["items"]
categories_col = db["categories"]


# ---------- Categories ----------
@router.get("/categories")
async def list_categories(user: dict = Depends(get_current_user)):
    rows = await categories_col.find({}, {"_id": 0}).sort("name", 1).to_list(500)
    return rows


@router.post("/categories")
async def create_category(payload: dict, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Name required")
    if await categories_col.find_one({"name": name}):
        raise HTTPException(409, "Category exists")
    doc = {
        "id": uuid.uuid4().hex,
        "name": name,
        "code": payload.get("code") or name.upper().replace(" ", "_"),
        "description": payload.get("description"),
        "parent_id": payload.get("parent_id"),
        "is_active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await categories_col.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "create_category", "category", doc["id"], {"name": name})
    return doc


@router.delete("/categories/{cid}")
async def delete_category(cid: str, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    await categories_col.delete_one({"id": cid})
    await log_audit(user, "delete_category", "category", cid)
    return {"success": True}


# ---------- Items / SKUs ----------
@router.get("")
async def list_items(
    q: Optional[str] = None, category: Optional[str] = None, is_active: Optional[bool] = None,
    limit: int = 200, skip: int = 0, user: dict = Depends(get_current_user)
):
    fil = {}
    if q:
        fil["$or"] = [
            {"sku": {"$regex": q, "$options": "i"}},
            {"name": {"$regex": q, "$options": "i"}},
            {"erp_id": {"$regex": q, "$options": "i"}},
        ]
    if category:
        fil["category"] = category
    if is_active is not None:
        fil["is_active"] = is_active
    total = await items_col.count_documents(fil)
    rows = await items_col.find(fil, {"_id": 0}).sort("name", 1).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "items": rows}


@router.post("")
async def create_item(payload: dict, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    sku = (payload.get("sku") or "").strip().upper()
    if not sku:
        raise HTTPException(400, "SKU required")
    if await items_col.find_one({"sku": sku}):
        raise HTTPException(409, "SKU exists")
    doc = {
        "id": uuid.uuid4().hex,
        "sku": sku,
        "name": payload.get("name", ""),
        "category": payload.get("category"),
        "subcategory": payload.get("subcategory"),
        "description": payload.get("description"),
        "erp_id": payload.get("erp_id"),
        "barcode": payload.get("barcode"),
        "mrp": float(payload.get("mrp", 0)),
        "season": payload.get("season"),
        "color": payload.get("color"),
        "size": payload.get("size"),
        "is_active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user["id"],
    }
    await items_col.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "create_item", "item", doc["id"], {"sku": sku})
    return doc


@router.patch("/{iid}")
async def update_item(iid: str, updates: dict, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    if "_id" in updates:
        del updates["_id"]
    if "id" in updates:
        del updates["id"]
    await items_col.update_one({"id": iid}, {"$set": updates})
    await log_audit(user, "update_item", "item", iid, updates)
    return await items_col.find_one({"id": iid}, {"_id": 0})


@router.delete("/{iid}")
async def delete_item(iid: str, user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    await items_col.delete_one({"id": iid})
    await log_audit(user, "delete_item", "item", iid)
    return {"success": True}


@router.post("/bulk-upload")
async def bulk_upload_items(file: UploadFile = File(...), user: dict = Depends(require_roles(*MANAGEMENT_ROLES))):
    content = await file.read()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
    inserted, skipped, errors = 0, 0, []
    for i, row in enumerate(reader, start=2):
        sku = (row.get("sku") or "").strip().upper()
        if not sku:
            errors.append(f"Row {i}: missing sku")
            continue
        if await items_col.find_one({"sku": sku}):
            skipped += 1
            continue
        try:
            doc = {
                "id": uuid.uuid4().hex,
                "sku": sku,
                "name": row.get("name", "").strip(),
                "category": (row.get("category") or "").strip(),
                "subcategory": row.get("subcategory"),
                "description": row.get("description"),
                "erp_id": row.get("erp_id"),
                "barcode": row.get("barcode"),
                "mrp": float(row.get("mrp", 0) or 0),
                "season": row.get("season"),
                "color": row.get("color"),
                "size": row.get("size"),
                "is_active": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "created_by": user["id"],
            }
            await items_col.insert_one(doc)
            inserted += 1
        except Exception as e:
            errors.append(f"Row {i}: {str(e)}")
    await log_audit(user, "bulk_upload_items", "item", None, {"inserted": inserted, "skipped": skipped})
    return {"inserted": inserted, "skipped": skipped, "errors": errors[:20]}


@router.get("/sample-csv")
async def sample_csv(user: dict = Depends(get_current_user)):
    from fastapi.responses import Response
    csv_text = "sku,name,category,subcategory,description,erp_id,barcode,mrp,season,color,size\nK10001,KAZO Sequin Mini Dress,DRESSES,PARTY,Glittering sequin mini perfect for parties,KZ-ERP-10001,890011223344,3990,SS26,Black,M\nK10002,KAZO Wide-Leg Trouser,BOTTOMS,WORK,Premium drapey wide-leg trousers,KZ-ERP-10002,890011223345,2490,AW25,Cream,L\n"
    return Response(content=csv_text, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=items_sample.csv"})
