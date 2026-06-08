"""Auth routes: login, logout, me, change password."""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Request, Response
from database import users_col
from models import LoginRequest, LoginResponse, User
from auth import verify_password, create_token, get_current_user, log_audit, ALL_DASHBOARD_ROLES

router = APIRouter(prefix="/auth", tags=["auth"])

# Portal access policy.
# CRM portal == the admin/analytics dashboard → every dashboard-capable role may enter.
# Store portal == in-store ops → store roles + admins.
_CRM_PORTAL_ROLES = {r.value for r in ALL_DASHBOARD_ROLES}
_STORE_PORTAL_ROLES = {"store_manager", "store_staff", "super_admin", "brand_admin"}


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, request: Request, response: Response):
    user = await users_col.find_one({"email": req.email.lower()}, {"_id": 0})
    if not user or not verify_password(req.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account is deactivated")

    # Portal-based role gating: store portal = store ops, crm portal = admin dashboard
    role = user["role"]
    if req.portal == "store" and role not in _STORE_PORTAL_ROLES:
        raise HTTPException(status_code=403, detail="This account cannot access the Store portal")
    if req.portal == "crm" and role not in _CRM_PORTAL_ROLES:
        raise HTTPException(status_code=403, detail="This account cannot access the CRM portal")

    token = create_token(user["id"], user["role"], user["email"])
    ip = request.client.host if request.client else None
    await users_col.update_one(
        {"id": user["id"]},
        {"$set": {"last_login_at": datetime.now(timezone.utc).isoformat(), "last_login_ip": ip}},
    )
    await log_audit(user, "login", "auth", user["id"], {"portal": req.portal}, ip)

    response.set_cookie(
        key="kazo_token", value=token, httponly=True, samesite="lax",
        max_age=60 * 60 * 12, secure=False
    )
    user.pop("password_hash", None)
    return {"token": token, "user": user}


@router.post("/logout")
async def logout(response: Response, user: dict = Depends(get_current_user)):
    response.delete_cookie("kazo_token")
    await log_audit(user, "logout", "auth", user["id"])
    return {"success": True}


@router.get("/me", response_model=User)
async def me(user: dict = Depends(get_current_user)):
    return user
