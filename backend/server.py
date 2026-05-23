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
from routes.items_routes import router as items_router
from routes.cms_routes import router as cms_router
from routes.analytics_routes import router as analytics_router
from routes.drilldown_routes import router as drilldown_router
from routes.fundlebrain_routes import router as fundlebrain_router
from routes.communications_routes import router as communications_router
from routes.historic_routes import router as historic_router
from routes.pos_ewards_routes import router as pos_ewards_router, bootstrap_pos_defaults
from routes.live_monitor_routes import router as live_monitor_router, admin_router as pos_creds_router, log_router as api_log_detail_router
from routes.segments_routes import router as segments_router
from routes.cohort_library import router as cohort_library_router

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
api_router.include_router(items_router)
api_router.include_router(cms_router)
api_router.include_router(analytics_router)
api_router.include_router(drilldown_router)
api_router.include_router(fundlebrain_router)
api_router.include_router(communications_router)
api_router.include_router(historic_router)
api_router.include_router(pos_ewards_router)
api_router.include_router(live_monitor_router)
api_router.include_router(pos_creds_router)
api_router.include_router(api_log_detail_router)
api_router.include_router(segments_router)
api_router.include_router(cohort_library_router)

app.include_router(api_router)

# CORS — must allow specific origins (NOT '*') because frontend sends credentials.
# Combine explicit env list with a permissive regex covering custom + emergent domains.
_env_origins = [o.strip() for o in os.environ.get('CORS_ORIGINS', '').split(',') if o.strip() and o.strip() != '*']
_default_origins = [
    "https://kazoloyalty.fundlebrain.ai",
    "https://kazo-loyalty-hub.emergent.host",
    "https://pos-ewards-api.preview.emergentagent.com",
    "http://localhost:3000",
]
_allowed_origins = list({*_env_origins, *_default_origins})
_origin_regex = os.environ.get(
    'CORS_ORIGIN_REGEX',
    r"https?://(.*\.)?(fundlebrain\.ai|emergent\.host|emergentagent\.com|localhost(:\d+)?)$",
)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=_allowed_origins,
    allow_origin_regex=_origin_regex,
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

    # Backfill store_id on store-scoped users (security hardening for drilldown scope)
    store_user_map = {
        "store.mumbai@kazo.com": "Mumbai",
        "staff.delhi@kazo.com": "Delhi",
    }
    for email, city in store_user_map.items():
        u = await users_col.find_one({"email": email})
        if u and not u.get("store_id"):
            s = await stores_col.find_one({"city": city, "is_active": True})
            if s:
                await users_col.update_one(
                    {"email": email},
                    {"$set": {"store_id": s["id"]}},
                )
                logger.info(f"Backfilled store_id for {email} -> {s['code']}")

    # Seed all demo / operational users (idempotent — runs on every boot so
    # production deployments with a fresh DB always have working logins).
    demo_users = [
        ("crm@kazo.com", "Priya Sharma", "crm_manager", None),
        ("marketing@kazo.com", "Rohan Kapoor", "marketing_manager", None),
        ("regional.north@kazo.com", "Anjali Verma", "regional_manager", None),
        ("store.mumbai@kazo.com", "Neha Patel", "store_manager", "Mumbai"),
        ("staff.delhi@kazo.com", "Karan Singh", "store_staff", "Delhi"),
        ("support@kazo.com", "Riya Mehra", "support_agent", None),
        ("analytics@kazo.com", "Aditya Rao", "analytics_viewer", None),
        ("executive@kazo.com", "Kavita Iyer", "readonly_executive", None),
        ("it@kazo.com", "Vikram Joshi", "brand_admin", None),
    ]
    for email, name, role, city in demo_users:
        if await users_col.find_one({"email": email}):
            continue
        doc = {
            "id": uuid.uuid4().hex,
            "email": email,
            "name": name,
            "role": role,
            "password_hash": hash_password("Kazo@2026"),
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if city:
            s = await stores_col.find_one({"city": city, "is_active": True})
            if s:
                doc["store_id"] = s["id"]
        await users_col.insert_one(doc)
        logger.info(f"Seeded demo user {email}")

    # Seed loyalty config
    cfg = await loyalty_config_col.find_one({"id": "default"})
    if not cfg:
        doc = dict(DEFAULT_CONFIG)
        doc["updated_at"] = datetime.now(timezone.utc).isoformat()
        await loyalty_config_col.insert_one(doc)
        logger.info("Seeded loyalty config")

    # Seed campaign_metrics (idempotent: derives per-channel funnel rows
    # from existing campaign aggregates so Campaign ROI v2 funnel populates)
    try:
        from seed_campaign_metrics import seed_campaign_metrics
        res = await seed_campaign_metrics()
        if res["rows_inserted"]:
            logger.info(f"Seeded campaign_metrics: {res}")
    except Exception as e:
        logger.warning(f"Could not seed campaign_metrics: {e}")

    # Start weekly executive-digest scheduler (Mon 09:00 IST)
    try:
        from scheduler import start_scheduler
        start_scheduler()
    except Exception as e:
        logger.warning(f"Could not start digest scheduler: {e}")

    # Bootstrap POS defaults (credentials + test customer 966681235 + test coupons)
    try:
        await bootstrap_pos_defaults()
    except Exception as e:
        logger.warning(f"Could not bootstrap POS defaults: {e}")


@app.on_event("shutdown")
async def shutdown():
    try:
        from scheduler import stop_scheduler
        stop_scheduler()
    except Exception:
        pass
    from database import client
    client.close()
