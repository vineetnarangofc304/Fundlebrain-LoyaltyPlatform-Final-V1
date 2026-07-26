"""MongoDB connection singleton."""
import os
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReadPreference
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

_mongo_url = os.environ["MONGO_URL"]
_db_name = os.environ["DB_NAME"]

# readPreference=primaryPreferred is CRITICAL for availability on the shared Atlas
# cluster: it repeatedly loses its PRIMARY for short windows (elections / node
# maintenance → topology ReplicaSetNoPrimary). With the default PRIMARY preference,
# every read during that window waits the full ~30s serverSelection timeout and then
# 500s with `ServerSelectionTimeoutError: No replica set members match "Primary()"`
# — which is exactly what surfaces on the POS as "Loyalty is not Active". With
# primaryPreferred, reads transparently fall back to a healthy SECONDARY when there
# is no primary (so posCustomerCheck / dashboards keep working). This can NEVER cause
# a read-after-write inconsistency: when a primary IS up, primaryPreferred always
# reads from it; only when there is NO primary do reads use a secondary, and in that
# state writes cannot commit anyway. retryReads/retryWrites ride out a single blip.
_COMMON_KW = dict(
    read_preference=ReadPreference.PRIMARY_PREFERRED,
    retryReads=True,
    retryWrites=True,
)

# Main request pool. Explicit sizing so a live POS bill / dashboard read always
# has warm sockets available. Best-effort api_logs WRITES run on a separate tiny
# pool (see db_logging.py) so background logging can never starve this pool —
# that starvation is what caused the production `NetworkTimeout: read operation
# timed out` 500s on posAddPoint.
client = AsyncIOMotorClient(_mongo_url, maxPoolSize=100, minPoolSize=10, **_COMMON_KW)
db = client[_db_name]

# ── Dedicated POS / loyalty critical-path pool ─────────────────────────────────
# The eWards till (posCustomerCheck / posAddPoint / posRedeem / OTP / coupon) is
# revenue-critical and must NEVER be starved of connections by heavy admin
# analytics. Heavy report aggregations that scan the 1.5M-row transactions/ledger
# collections can hold sockets on the shared `client` pool for tens of seconds;
# when the till then tries to bill, it waits for a free socket, blows the 30s POS
# CSOT and surfaces "Loyalty is not Active: Internal error" on the POS.
# Give the POS its OWN client (same Atlas DB, separate sockets) so analytics load
# on `client` can never block a live bill. Same isolation pattern already used for
# api_logs writes (_log_client) and background rollups (_long_client).
_pos_client = AsyncIOMotorClient(_mongo_url, maxPoolSize=30, minPoolSize=5, **_COMMON_KW)
pos_db = _pos_client[_db_name]

pos_customers_col = pos_db["customers"]
pos_transactions_col = pos_db["transactions"]
pos_points_ledger_col = pos_db["points_ledger"]
pos_stores_col = pos_db["stores"]
pos_loyalty_config_col = pos_db["loyalty_config"]
pos_coupons_col = pos_db["coupons"]
pos_coupon_redemptions_col = pos_db["coupon_redemptions"]


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
mb_query_log_col = db["mb_query_log"]
mb_credit_jobs_col = db["mb_credit_jobs"]
mb_credit_receipts_col = db["mb_credit_receipts"]
store_credentials_col = db["store_credentials"]
