"""KAZO Fundle Platform - Main FastAPI server."""
from fastapi import FastAPI, APIRouter, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import logging
import time
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from routes.auth_routes import router as auth_router
from routes.users_routes import router as users_router
from routes.dashboard_routes import router as dashboard_router
from routes.customers_routes import router as customers_router
from routes.loyalty_routes import router as loyalty_router
from routes.coupons_routes import router as coupons_router
from routes.campaigns_routes import router as campaigns_router
from routes.ai_routes import router as ai_router
from routes.api_monitor_routes import router as api_monitor_router
from routes.stores_routes import router as stores_router, pos_router
from routes.nps_routes import router as nps_router
from routes.tickets_routes import router as tickets_router
from routes.reports_routes import router as reports_router
from routes.public_routes import router as public_router

app = FastAPI(title="KAZO Fundle Platform", version="1.0.0")
api_router = APIRouter(prefix="/api")


@api_router.get("/")
async def root():
    return {
        "platform": "KAZO Fundle Platform",
        "powered_by": "Fundle",
        "brand": os.environ.get("BRAND_NAME", "Kazo"),
        "status": "operational",
    }


@api_router.get("/health")
async def health():
    return {"status": "ok", "service": "kazo-fundle-api"}


# Mount all routers
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(dashboard_router)
api_router.include_router(customers_router)
api_router.include_router(loyalty_router)
api_router.include_router(coupons_router)
api_router.include_router(campaigns_router)
api_router.include_router(ai_router)
api_router.include_router(api_monitor_router)
api_router.include_router(stores_router)
api_router.include_router(pos_router)
api_router.include_router(nps_router)
api_router.include_router(tickets_router)
api_router.include_router(reports_router)
api_router.include_router(public_router)

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("kazo-fundle")


@app.on_event("startup")
async def startup():
    from database import users_col, stores_col, loyalty_config_col
    from routes.loyalty_routes import DEFAULT_CONFIG
    from auth import hash_password
    from datetime import datetime, timezone
    import uuid

    # Seed super admin if not exists
    super_admin = await users_col.find_one({"email": os.environ.get("SUPER_ADMIN_EMAIL", "superadmin@fundle.io").lower()})
    if not super_admin:
        await users_col.insert_one({
            "id": uuid.uuid4().hex,
            "email": os.environ.get("SUPER_ADMIN_EMAIL", "superadmin@fundle.io").lower(),
            "name": "Fundle Super Admin",
            "role": "super_admin",
            "password_hash": hash_password(os.environ.get("SUPER_ADMIN_PASSWORD", "Fundle@2026")),
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("Seeded super admin")

    # Seed brand admin
    brand_admin = await users_col.find_one({"email": os.environ.get("BRAND_ADMIN_EMAIL", "admin@kazo.com").lower()})
    if not brand_admin:
        await users_col.insert_one({
            "id": uuid.uuid4().hex,
            "email": os.environ.get("BRAND_ADMIN_EMAIL", "admin@kazo.com").lower(),
            "name": "Kazo Brand Admin",
            "role": "brand_admin",
            "password_hash": hash_password(os.environ.get("BRAND_ADMIN_PASSWORD", "Kazo@2026")),
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("Seeded brand admin")

    # Seed loyalty config
    cfg = await loyalty_config_col.find_one({"id": "default"})
    if not cfg:
        doc = dict(DEFAULT_CONFIG)
        doc["updated_at"] = datetime.now(timezone.utc).isoformat()
        await loyalty_config_col.insert_one(doc)
        logger.info("Seeded loyalty config")


@app.on_event("shutdown")
async def shutdown():
    from database import client
    client.close()
