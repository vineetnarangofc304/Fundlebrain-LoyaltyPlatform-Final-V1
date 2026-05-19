"""JWT authentication, password hashing, role-based access control."""
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, List
import bcrypt
import jwt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from database import users_col, audit_logs_col
from models import Role

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRY_HOURS = int(os.environ.get("JWT_EXPIRY_HOURS", "12"))

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_token(user_id: str, role: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(
    request: Request,
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> dict:
    token = None
    if creds:
        token = creds.credentials
    else:
        cookie_token = request.cookies.get("kazo_token")
        if cookie_token:
            token = cookie_token
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(token)
    user = await users_col.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.get("is_active", True):
        raise HTTPException(status_code=403, detail="User inactive")
    return user


def require_roles(*roles: Role):
    allowed = {r.value if isinstance(r, Role) else r for r in roles}

    async def checker(user: dict = Depends(get_current_user)):
        if user["role"] not in allowed:
            raise HTTPException(status_code=403, detail=f"Requires roles: {', '.join(allowed)}")
        return user

    return checker


# Convenient role groups
ADMIN_ROLES = [Role.SUPER_ADMIN, Role.BRAND_ADMIN]
MANAGEMENT_ROLES = [Role.SUPER_ADMIN, Role.BRAND_ADMIN, Role.CRM_MANAGER, Role.MARKETING_MANAGER, Role.REGIONAL_MANAGER]
ALL_DASHBOARD_ROLES = [
    Role.SUPER_ADMIN, Role.BRAND_ADMIN, Role.CRM_MANAGER, Role.MARKETING_MANAGER,
    Role.REGIONAL_MANAGER, Role.STORE_MANAGER, Role.ANALYTICS_VIEWER, Role.READONLY_EXECUTIVE,
    Role.SUPPORT_AGENT
]


async def log_audit(user: dict, action: str, entity: str, entity_id: Optional[str] = None, metadata: dict = None, ip: Optional[str] = None):
    doc = {
        "id": __import__("uuid").uuid4().hex,
        "user_id": user["id"],
        "user_email": user["email"],
        "action": action,
        "entity": entity,
        "entity_id": entity_id,
        "metadata": metadata or {},
        "ip": ip,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await audit_logs_col.insert_one(doc)
