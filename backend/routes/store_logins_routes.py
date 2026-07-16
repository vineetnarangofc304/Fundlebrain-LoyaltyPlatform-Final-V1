"""Store logins — seed one store-scoped 'store_manager' login per store, keep the credential
retrievable (encrypted at rest with a Fernet key from env), and let a Super Admin download the
full list as CSV. The actual login still authenticates via the existing email + bcrypt flow;
the encrypted copy in `store_credentials` exists ONLY so the plaintext can be re-downloaded."""
import csv
import io
import os
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from cryptography.fernet import Fernet

from database import stores_col, users_col, store_credentials_col
from auth import get_current_user, hash_password, log_audit

router = APIRouter(prefix="/store-logins", tags=["store-logins"])

# Unambiguous alphabet (no 0/O/1/l/I) for readable-but-strong passwords.
_SAFE = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"


def _require_super(user: dict):
    if user.get("role") != "super_admin":
        raise HTTPException(403, "Super Admin access required.")


def _fernet() -> Fernet:
    return Fernet(os.environ["STORE_CRED_KEY"].encode())


def _gen_password(n: int = 10) -> str:
    # Guarantee at least one letter + one digit.
    while True:
        pwd = "".join(secrets.choice(_SAFE) for _ in range(n))
        if any(c.isalpha() for c in pwd) and any(c.isdigit() for c in pwd):
            return pwd


def _login_email(code: str) -> str:
    return f"store.{(code or '').strip().lower()}@kazo.com"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _upsert_credential(store: dict, user_id: str, email: str, pwd: str):
    enc = _fernet().encrypt(pwd.encode()).decode()
    await store_credentials_col.update_one(
        {"store_id": store["id"]},
        {"$set": {"store_id": store["id"], "store_code": store.get("code"),
                  "store_name": store.get("name"), "city": store.get("city"),
                  "login_email": email, "user_id": user_id,
                  "password_enc": enc, "updated_at": _now()},
         "$setOnInsert": {"created_at": _now()}},
        upsert=True,
    )


@router.post("/seed")
async def seed_store_logins(include_inactive: bool = False, user: dict = Depends(get_current_user)):
    """Idempotently create a login for every store. Stores that already have a stored credential are
    left untouched (passwords are NOT rotated). Stores that have a store_manager account but no stored
    credential get a fresh password so the credential is downloadable."""
    _require_super(user)
    q = {} if include_inactive else {"is_active": True}
    stores = await stores_col.find(
        q, {"_id": 0, "id": 1, "code": 1, "name": 1, "city": 1}).sort("code", 1).to_list(5000)
    created, skipped, no_code = 0, 0, 0
    for s in stores:
        code = (s.get("code") or "").strip()
        if not code:
            no_code += 1
            continue
        if await store_credentials_col.find_one({"store_id": s["id"]}, {"_id": 1}):
            skipped += 1
            continue
        gen_email = _login_email(code)
        existing = await users_col.find_one(
            {"$or": [{"store_id": s["id"], "role": "store_manager"}, {"email": gen_email}]},
            {"_id": 0, "id": 1, "email": 1})
        pwd = _gen_password()
        if existing:
            uid, email = existing["id"], existing["email"]
            await users_col.update_one(
                {"id": uid}, {"$set": {"password_hash": hash_password(pwd), "is_active": True}})
        else:
            uid, email = uuid.uuid4().hex, gen_email
            await users_col.insert_one({
                "id": uid, "email": email,
                "name": f"{s.get('name') or code} — Store Login",
                "role": "store_manager", "store_id": s["id"], "phone": None, "region": None,
                "is_active": True, "is_master_admin": False, "is_master_query_admin": False,
                "is_store_login": True, "password_hash": hash_password(pwd),
                "created_at": _now(), "created_by": user["id"]})
        await _upsert_credential(s, uid, email, pwd)
        created += 1
    await log_audit(user, "seed_store_logins", "store_login", None,
                    {"created": created, "skipped": skipped, "no_code": no_code})
    return {"created": created, "skipped_existing": skipped, "missing_code": no_code,
            "total_stores": len(stores),
            "message": (f"Created {created} new store login(s); {skipped} already existed"
                        + (f"; {no_code} store(s) skipped (no code)" if no_code else "") + ".")}


@router.get("")
async def list_store_logins(user: dict = Depends(get_current_user)):
    _require_super(user)
    rows = await store_credentials_col.find(
        {}, {"_id": 0, "password_enc": 0}).sort("store_code", 1).to_list(5000)
    return {"count": len(rows), "logins": rows}


@router.post("/{store_id}/reset")
async def reset_store_login(store_id: str, user: dict = Depends(get_current_user)):
    _require_super(user)
    store = await stores_col.find_one({"id": store_id}, {"_id": 0, "id": 1, "code": 1, "name": 1, "city": 1})
    if not store:
        raise HTTPException(404, "Store not found.")
    cred = await store_credentials_col.find_one({"store_id": store_id}, {"_id": 0})
    email = (cred or {}).get("login_email") or _login_email(store.get("code"))
    existing = await users_col.find_one({"email": email}, {"_id": 0, "id": 1})
    pwd = _gen_password()
    if existing:
        uid = existing["id"]
        await users_col.update_one({"id": uid}, {"$set": {"password_hash": hash_password(pwd), "is_active": True}})
    else:
        uid = uuid.uuid4().hex
        await users_col.insert_one({
            "id": uid, "email": email, "name": f"{store.get('name') or store.get('code')} — Store Login",
            "role": "store_manager", "store_id": store_id, "is_active": True,
            "is_master_admin": False, "is_master_query_admin": False, "is_store_login": True,
            "password_hash": hash_password(pwd), "created_at": _now(), "created_by": user["id"]})
    await _upsert_credential(store, uid, email, pwd)
    await log_audit(user, "reset_store_login", "store_login", store_id, {"login_email": email})
    return {"ok": True, "store_code": store.get("code"), "login_email": email,
            "message": f"Password reset for {store.get('code')} — download the CSV for the new password."}


@router.get("/download")
async def download_store_logins(user: dict = Depends(get_current_user)):
    _require_super(user)
    f = _fernet()
    rows = await store_credentials_col.find({}, {"_id": 0}).sort("store_code", 1).to_list(5000)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Store Code", "Store Name", "City", "Login Email", "Password", "Last Updated"])
    for r in rows:
        try:
            pwd = f.decrypt(r["password_enc"].encode()).decode()
        except Exception:
            pwd = "<decrypt-error>"
        w.writerow([r.get("store_code", ""), r.get("store_name", ""), r.get("city", ""),
                    r.get("login_email", ""), pwd, (r.get("updated_at") or "")[:19].replace("T", " ")])
    await log_audit(user, "download_store_logins", "store_login", None, {"count": len(rows)})
    return Response(
        content=buf.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=kazo_store_logins.csv"})
