"""Pydantic models for the Kazo Fundle platform."""
from datetime import datetime, timezone, date
from enum import Enum
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field, EmailStr, ConfigDict
import uuid


def utcnow():
    return datetime.now(timezone.utc)


def gen_id():
    return str(uuid.uuid4())


class Role(str, Enum):
    SUPER_ADMIN = "super_admin"
    BRAND_ADMIN = "brand_admin"
    CRM_MANAGER = "crm_manager"
    MARKETING_MANAGER = "marketing_manager"
    REGIONAL_MANAGER = "regional_manager"
    STORE_MANAGER = "store_manager"
    STORE_STAFF = "store_staff"
    SUPPORT_AGENT = "support_agent"
    ANALYTICS_VIEWER = "analytics_viewer"
    READONLY_EXECUTIVE = "readonly_executive"


class LoyaltyTier(str, Enum):
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"
    DIAMOND = "diamond"


# ---------- Users ----------
class UserBase(BaseModel):
    email: EmailStr
    name: str
    role: Role
    phone: Optional[str] = None
    store_id: Optional[str] = None
    region: Optional[str] = None
    is_active: bool = True
    is_master_admin: bool = False
    is_master_query_admin: bool = False


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[Role] = None
    phone: Optional[str] = None
    store_id: Optional[str] = None
    region: Optional[str] = None
    is_active: Optional[bool] = None
    is_master_admin: Optional[bool] = None
    is_master_query_admin: Optional[bool] = None


class User(UserBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=gen_id)
    created_at: datetime = Field(default_factory=utcnow)
    created_by: Optional[str] = None
    last_login_at: Optional[datetime] = None
    last_login_ip: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    portal: Optional[str] = "enterprise"  # enterprise | store | crm


class LoginResponse(BaseModel):
    token: str
    user: User


# ---------- Customers ----------
class CustomerBase(BaseModel):
    mobile: str
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    birthday: Optional[str] = None  # ISO date
    anniversary: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    gender: Optional[str] = None
    preferred_store_id: Optional[str] = None


class CustomerCreate(CustomerBase):
    pass


class Customer(CustomerBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=gen_id)
    tier: LoyaltyTier = LoyaltyTier.SILVER
    points_balance: int = 0
    lifetime_points_earned: int = 0
    lifetime_points_redeemed: int = 0
    lifetime_spend: float = 0.0
    visit_count: int = 0
    last_visit_at: Optional[datetime] = None
    first_purchase_at: Optional[datetime] = None
    churn_risk: str = "low"  # low | medium | high
    favourite_categories: List[str] = []
    nps_score: Optional[int] = None
    created_at: datetime = Field(default_factory=utcnow)


# ---------- Stores ----------
class StoreBase(BaseModel):
    code: str
    name: str
    city: str
    state: str
    region: str
    address: str
    phone: Optional[str] = None
    manager_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_active: bool = True


class StoreCreate(StoreBase):
    pass


class Store(StoreBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=gen_id)
    created_at: datetime = Field(default_factory=utcnow)


# ---------- Transactions ----------
class TransactionItem(BaseModel):
    sku: str
    name: str
    category: str
    quantity: int
    unit_price: float
    total: float


class TransactionBase(BaseModel):
    customer_id: Optional[str] = None
    customer_mobile: Optional[str] = None
    store_id: str
    bill_number: str
    bill_date: datetime
    gross_amount: float
    discount_amount: float = 0.0
    net_amount: float
    items: List[TransactionItem] = []
    payment_mode: str = "card"
    points_earned: int = 0
    points_redeemed: int = 0
    coupon_code: Optional[str] = None


class Transaction(TransactionBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=gen_id)
    created_at: datetime = Field(default_factory=utcnow)


# ---------- Loyalty config ----------
class TierRule(BaseModel):
    """One tier in the loyalty program.

    Tier identity (`tier`) is now a free string so brands can have custom
    tiers beyond bronze/silver/gold/platinum (e.g., Diamond, VIP, Founders).
    """
    tier: str
    name: Optional[str] = None  # Display name; defaults to tier.capitalize() if missing
    min_lifetime_spend: float = 0
    max_lifetime_spend: Optional[float] = None  # Optional ceiling before next tier kicks in
    earn_multiplier: float = 1.0
    welcome_bonus: int = 0
    birthday_bonus: int = 0
    anniversary_bonus: int = 0
    upgrade_bonus: int = 0  # One-time bonus points awarded when a customer is promoted INTO this tier (slab)
    tier_type: str = "standard"  # entry | standard | premium | vip | partner
    is_active: bool = True
    # Per-tier perks
    coupon_discount_pct: float = 0  # Auto-applied coupon discount on every bill (%)
    free_shipping_min_bill: Optional[float] = None  # Min bill at/above which shipping is free
    point_expiry_override_days: Optional[int] = None  # Overrides the global expiry
    visit_threshold: Optional[int] = None  # Alt promotion path — N visits unlock this tier
    color: Optional[str] = None  # Optional hex code for UI badges


class LoyaltyConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = "default"
    # ---- Earn engine ----
    earn_mode: str = "points_per_spend"  # 'points_per_spend' | 'percent_of_spend'
    earn_ratio: float = 1.0  # Points awarded per ₹ when mode=points_per_spend
    percent_of_spend: float = 5.0  # % of bill awarded as points when mode=percent_of_spend
    # ---- Redeem engine ----
    burn_ratio: float = 0.25  # ₹ value of 1 point on redemption
    min_redeem_points: int = 100
    max_redeem_pct_of_bill: float = 50.0  # Cap redemption to N% of bill
    point_expiry_days: int = 365
    # ---- Bonuses ----
    welcome_bonus: int = 100
    birthday_bonus: int = 200
    anniversary_bonus: int = 200
    referral_points_referrer: int = 250
    referral_points_referee: int = 100
    # ---- Tiers ----
    tier_rules: List[TierRule] = []
    tier_reset_cadence: str = "never"  # never | annual | rolling_12m
    tier_reset_anchor_date: str = "01-01"  # MM-DD for annual cadence
    # ---- Multipliers ----
    category_multipliers: Dict[str, float] = Field(default_factory=dict)  # { "category_name": 2.0 }
    store_type_multipliers: Dict[str, float] = Field(default_factory=dict)  # { "online": 1.5 }
    festival_boosters: List[Dict[str, Any]] = Field(default_factory=list)
    # ---- Compliance / restrictions ----
    require_otp_for_redeem: bool = True
    allow_coupon_stacking: bool = False
    min_bill_for_earn: float = 0.0
    block_earn_on_returns: bool = True
    # ---- Meta ----
    updated_at: datetime = Field(default_factory=utcnow)
    updated_by: Optional[str] = None


# ---------- Coupons ----------
class CouponBase(BaseModel):
    code: str
    name: str
    coupon_type: str  # flat | percentage | sku | category | store | city | referral | birthday | anniversary | winback | new_customer | festival | vip
    discount_value: float
    min_bill_amount: float = 0.0
    max_discount: Optional[float] = None
    valid_from: datetime
    valid_to: datetime
    usage_limit: int = 1
    usage_limit_per_customer: int = 1
    target_cohort: Optional[str] = None
    target_tier: Optional[LoyaltyTier] = None
    target_city: Optional[str] = None
    target_category: Optional[str] = None
    target_sku: Optional[str] = None
    require_otp: bool = False
    is_active: bool = True
    description: Optional[str] = None


class CouponCreate(CouponBase):
    pass


class Coupon(CouponBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=gen_id)
    times_used: int = 0
    times_issued: int = 0
    created_at: datetime = Field(default_factory=utcnow)
    created_by: Optional[str] = None


# ---------- Campaigns ----------
class CampaignBase(BaseModel):
    name: str
    description: Optional[str] = None
    channels: List[str]  # whatsapp, sms, email, push
    audience_type: str  # all | tier | city | cohort | custom | segment
    audience_filter: Dict[str, Any] = {}
    message_template: str = ""  # free-text fallback / preview (only used when no template_id)
    template_id: Optional[str] = None  # link to a comms Template for real Karix sends
    coupon_code: Optional[str] = None
    schedule_at: Optional[datetime] = None
    status: str = "draft"  # draft | scheduled | running | completed | cancelled
    send_limit: int = 50000  # safety cap per launch


class CampaignCreate(CampaignBase):
    pass


class Campaign(CampaignBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=gen_id)
    sent: int = 0
    delivered: int = 0
    opened: int = 0
    clicked: int = 0
    redeemed: int = 0
    revenue_generated: float = 0.0
    created_at: datetime = Field(default_factory=utcnow)
    created_by: Optional[str] = None
    launched_at: Optional[datetime] = None
    bulk_job_id: Optional[str] = None  # links to bulk_send_jobs when real send used
    send_mode: Optional[str] = None    # "karix" | "simulated"


# ---------- Points ledger ----------
class PointsLedger(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=gen_id)
    customer_id: str
    type: str  # earn | redeem | bonus | adjust | expire
    points: int
    reference_type: Optional[str] = None  # transaction | campaign | manual
    reference_id: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    created_by: Optional[str] = None


# ---------- API logs ----------
class APILog(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=gen_id)
    endpoint: str
    method: str
    status_code: int
    response_time_ms: int
    customer_mobile: Optional[str] = None
    bill_number: Optional[str] = None
    error_reason: Optional[str] = None
    store_id: Optional[str] = None
    request_payload: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=utcnow)


# ---------- NPS ----------
class NPSResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=gen_id)
    customer_id: Optional[str] = None
    customer_mobile: Optional[str] = None
    store_id: Optional[str] = None
    score: int  # 0-10
    sentiment: str = "neutral"  # promoter | passive | detractor
    feedback: Optional[str] = None
    category: str = "overall"  # overall | store | product | staff | campaign
    created_at: datetime = Field(default_factory=utcnow)


# ---------- Support tickets ----------
class TicketBase(BaseModel):
    customer_id: Optional[str] = None
    customer_mobile: Optional[str] = None
    subject: str
    description: str
    category: str = "general"  # coupon | points | otp | sync | general
    priority: str = "medium"
    store_id: Optional[str] = None


class TicketCreate(TicketBase):
    pass


class Ticket(TicketBase):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=gen_id)
    status: str = "open"  # open | in_progress | resolved | closed | escalated
    assigned_to: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    resolved_at: Optional[datetime] = None
    created_by: Optional[str] = None
    notes: List[Dict[str, Any]] = []


# ---------- AI Chat ----------
class AIMessage(BaseModel):
    role: str  # user | assistant | system
    content: str
    data: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=utcnow)


class AIChatSession(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=gen_id)
    user_id: str
    title: str = "New conversation"
    messages: List[AIMessage] = []
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class AIChatRequest(BaseModel):
    session_id: Optional[str] = None
    message: str
    model: Optional[str] = "gpt-5.2"
    attachment_ids: Optional[List[str]] = None


# ---------- Audit ----------
class AuditLog(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=gen_id)
    user_id: str
    user_email: str
    action: str
    entity: str
    entity_id: Optional[str] = None
    metadata: Dict[str, Any] = {}
    ip: Optional[str] = None
    timestamp: datetime = Field(default_factory=utcnow)
