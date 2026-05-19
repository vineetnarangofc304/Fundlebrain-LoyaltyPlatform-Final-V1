"""User management: Super Admin creates Brand Admins, Brand Admin creates other users."""
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from database import users_col
from models import UserCreate, UserUpdate, User, Role
from auth import (
    get_current_user, hash_password, log_audit, require_roles,
    ADMIN_ROLES,
)

router = APIRouter(prefix="/users", tags=["users"])


def _can_create(creator_role: str, target_role: str) -> bool:
    if creator_role == "super_admin":
        return True  # super admin can create any
    if creator_role == "brand_admin":
        return target_role not in ("super_admin",)
    return False


@router.get("", response_model=List[User])
async def list_users(
    role: Optional[str] = None,
    store_id: Optional[str] = None,
    is_active: Optional[bool] = None,
    user: dict = Depends(require_roles(*ADMIN_ROLES)),
):
    q = {}
    if role:
        q["role"] = role
    if store_id:
        q["store_id"] = store_id
    if is_active is not None:
        q["is_active"] = is_active
    users = await users_col.find(q, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(1000)
    return users


@router.post("", response_model=User)
async def create_user(payload: UserCreate, request: Request, user: dict = Depends(get_current_user)):
    if not _can_create(user["role"], payload.role.value):
        raise HTTPException(status_code=403, detail="You cannot create this role")
    existing = await users_col.find_one({"email": payload.email.lower()})
    if existing:
        raise HTTPException(status_code=409, detail="Email already exists")
    doc = payload.model_dump()
    doc["email"] = doc["email"].lower()
    doc["role"] = payload.role.value
    doc["password_hash"] = hash_password(doc.pop("password"))
    doc["id"] = __import__("uuid").uuid4().hex
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    doc["created_by"] = user["id"]
    doc["is_active"] = True
    await users_col.insert_one(doc)
    await log_audit(user, "create_user", "user", doc["id"], {"role": doc["role"], "email": doc["email"]})
    doc.pop("password_hash", None)
    doc.pop("_id", None)
    return doc


@router.patch("/{user_id}", response_model=User)
async def update_user(user_id: str, payload: UserUpdate, user: dict = Depends(require_roles(*ADMIN_ROLES))):
    target = await users_col.find_one({"id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if user["role"] == "brand_admin" and target["role"] == "super_admin":
        raise HTTPException(status_code=403, detail="Cannot modify super admin")
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if "role" in updates and hasattr(updates["role"], "value"):
        updates["role"] = updates["role"].value
    if updates:
        await users_col.update_one({"id": user_id}, {"$set": updates})
        await log_audit(user, "update_user", "user", user_id, updates)
    fresh = await users_col.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    return fresh


@router.post("/{user_id}/reset-password")
async def reset_password(user_id: str, new_password: str, user: dict = Depends(require_roles(*ADMIN_ROLES))):
    target = await users_col.find_one({"id": user_id}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    await users_col.update_one({"id": user_id}, {"$set": {"password_hash": hash_password(new_password)}})
    await log_audit(user, "reset_password", "user", user_id)
    return {"success": True}


@router.delete("/{user_id}")
async def delete_user(user_id: str, user: dict = Depends(require_roles(Role.SUPER_ADMIN, Role.BRAND_ADMIN))):
    target = await users_col.find_one({"id": user_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target["role"] == "super_admin":
        raise HTTPException(status_code=403, detail="Cannot delete super admin")
    await users_col.update_one({"id": user_id}, {"$set": {"is_active": False}})
    await log_audit(user, "deactivate_user", "user", user_id)
    return {"success": True}


@router.get("/roles")
async def list_roles(user: dict = Depends(get_current_user)):
    return [
        {"value": r.value, "label": r.value.replace("_", " ").title()}
        for r in Role
    ]
