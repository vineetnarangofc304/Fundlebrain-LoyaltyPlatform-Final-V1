"""MongoDB connection singleton."""
import os
from motor.motor_asyncio import AsyncIOMotorClient
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

_mongo_url = os.environ["MONGO_URL"]
_db_name = os.environ["DB_NAME"]

client = AsyncIOMotorClient(_mongo_url)
db = client[_db_name]


def get_db():
    return db


# Collections
users_col = db["users"]
customers_col = db["customers"]
transactions_col = db["transactions"]
stores_col = db["stores"]
loyalty_config_col = db["loyalty_config"]
coupons_col = db["coupons"]
coupon_redemptions_col = db["coupon_redemptions"]
campaigns_col = db["campaigns"]
campaign_metrics_col = db["campaign_metrics"]
points_ledger_col = db["points_ledger"]
audit_logs_col = db["audit_logs"]
api_logs_col = db["api_logs"]
nps_col = db["nps_responses"]
tickets_col = db["support_tickets"]
ai_chats_col = db["ai_chats"]
sessions_col = db["sessions"]
otp_col = db["otps"]
notifications_col = db["notifications"]
templates_col = db["communication_templates"]
provider_config_col = db["provider_config"]
message_log_col = db["message_log"]
mb_attachments_col = db["mb_attachments"]
mb_action_snapshots_col = db["mb_action_snapshots"]
master_campaigns_col = db["master_campaigns"]
