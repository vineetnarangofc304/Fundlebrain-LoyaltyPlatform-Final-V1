"""eWards-Compatible POS Integration API for KAZO.

Mirrors the exact JSON contract documented in `eWards POS Integration x FBTS (kazo).pdf`
so the KAZO POS team can swap base URL + x-api-key + merchant_id + customer_key and
have everything work against Fundle.

Endpoints (all POST):
  /api/pos/posCustomerCheck            — lookup customer by mobile
  /api/pos/posCustomerCheckRequest     — send OTP for customer-check
  /api/pos/resendOtPcustomercheck      — resend customer-check OTP
  /api/pos/posCustomerOTPCheck         — verify customer-check OTP
  /api/pos/posAddCustomer              — add / update member
  /api/pos/posRedeemPointRequest       — initiate point redemption (OTP or non-OTP)
  /api/pos/resendOtPosRedeemPointRequest — resend redemption OTP
  /api/pos/posRedeemPointOtpCheck      — verify redemption OTP & deduct points
  /api/pos/posAddPoint                 — bill settlement (the big one)
  /api/pos/posCouponDetails            — verify coupon code
  /api/pos/posRedeemCoupon             — redeem coupon code
  /api/pos/returnOrder                 — return bill (reverse points + spend)
  /api/pos/requestWalletRedemptionURL  — wallet redemption request (stub-friendly)
  /api/pos/getWalletRedemptionStatus   — wallet redemption status

Auth: ALL endpoints require:
  - Header  `x-api-key` matching pos_credentials.api_key   (the real secret)
  - Body    `merchant_id` matching pos_credentials.merchant_id
  - Body    `customer_key` — the per-outlet STORE CODE. The (merchant_id + customer_key)
            combo identifies the store on every bill; an unseen combo auto-creates a new
            store master row. customer_key is NOT a secret and is not rejected on mismatch.

Logging: every request + response captured in `api_logs` for Live Monitor.
"""
from __future__ import annotations
import os
import re
import uuid
import random
import secrets
import logging
import time
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, Header, HTTPException, Request

from database import (
    db, customers_col, transactions_col, stores_col, points_ledger_col,
    coupons_col, coupon_redemptions_col, api_logs_col, loyalty_config_col,
)

router = APIRouter(prefix="/pos", tags=["pos-ewards"])
logger = logging.getLogger("kazo-fundle.pos-ewards")


def _swallow_task_exc(task: "asyncio.Task") -> None:
    try:
        exc = task.exception()
        if exc:
            logger.warning(f"Background comms task failed: {exc}")
    except Exception:
        pass


def _fire_and_forget(coro) -> None:
    """Run a best-effort coroutine (comms) in the background so a slow SMS/WhatsApp
    provider never blocks the POS API response. Critical for live POS throughput."""
    try:
        task = asyncio.create_task(coro)
        task.add_done_callback(_swallow_task_exc)
    except RuntimeError:
        # No running event loop — should not happen under uvicorn.
        pass


# Dedicated collections
pos_credentials_col = db["pos_credentials"]
pos_otp_col = db["pos_otp_sessions"]
pos_wallet_col = db["pos_wallet_requests"]

OTP_TTL_SECONDS = 600  # 10 minutes
TEST_MODE_RETURN_OTP = os.environ.get("POS_RETURN_OTP_IN_RESPONSE", "true").lower() == "true"

# ---- Test-OTP bypass (for Postman / QA / integration testing) -------
# When ALLOW_TEST_OTP is true, the universal TEST_OTP value bypasses the
# random-OTP session lookup so POS integrators can exercise the full
# customer-check + redemption flows from Postman without provisioning a
# live SMS gateway. All other security checks (credentials, customer
# exists, sufficient balance) still apply.
#
# To harden a real production environment, set ALLOW_TEST_OTP=false
# in backend/.env and the bypass disappears.
ALLOW_TEST_OTP = os.environ.get("ALLOW_TEST_OTP", "true").lower() == "true"
TEST_OTP = os.environ.get("TEST_OTP", "123456")

# ---- Strict store validation ----------------------------------------
# When true (default), a bill whose (merchant_id + customer_key) store code is
# NOT already provisioned in the store master is REJECTED with a 400 instead of
# silently auto-creating a new store. This enforces canonical store integrity:
# only configured outlets can post bills. Every rejection is logged in the API
# Monitor so admins can see which unknown store codes are being attempted.
# Set STRICT_STORE_VALIDATION=false to restore the legacy auto-create behaviour.
STRICT_STORE_VALIDATION = os.environ.get("STRICT_STORE_VALIDATION", "true").lower() == "true"

DEFAULT_MERCHANT_ID = "KAZO_FUNDLE"
DEFAULT_CUSTOMER_KEY = "KAZO_MASTER_OUTLET"


# ---------------- Helpers ----------------
def _norm_mobile(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 12 and digits.startswith("91"):
        return digits[2:]
    return digits


def _is_valid_indian_mobile(value: Any) -> bool:
    """Valid Indian mobile = exactly 10 digits starting 6/7/8/9 (after stripping +91).
    Points/loyalty are granted ONLY to valid Indian mobiles; an invalid/missing mobile is a
    NON-LOYALTY 'Lost Customer' — its bill is still recorded (for purchase analytics) but
    earns no points and triggers no SMS."""
    m = _norm_mobile(value)
    return len(m) == 10 and m[0] in "6789"


def _map_pos_items(raw_items):
    """Normalise POS line items into the stored transaction items[] shape (reused by the
    normal earn path and the Lost-Customer record)."""
    items = []
    for it in (raw_items or []):
        items.append({
            "sku": str(it.get("id") or it.get("sku") or ""),
            "name": str(it.get("name") or ""),
            "category": str(it.get("category") or ""),
            "category_id": str(it.get("category_id") or ""),
            "quantity": _parse_int(it.get("quantity")),
            "unit_price": _parse_float(it.get("rate")),
            "total": _parse_float(it.get("subtotal") or it.get("rate")),
            "discount": _parse_float(it.get("discount")),
            "hsn_code": it.get("hsn_code"),
            "bar_code": it.get("bar_code"),
        })
    return items



def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# KAZO operates in IST. A POS-supplied bill date with NO timezone is treated as IST.
IST_TZ = timezone(timedelta(hours=5, minutes=30))


def _normalize_order_time(value: Any) -> str:
    """Normalise a POS-supplied bill date/time into an ISO-8601 string so it renders
    (and sorts / filters) correctly everywhere. The real eWards POS may send dates as
    'DD-MM-YYYY HH:MM:SS', 'YYYY-MM-DD HH:MM:SS', 'DD/MM/YYYY', epoch seconds/ms, etc.
    Stored raw these show as 'Invalid Date'. Rules: explicit timezone is preserved; a
    naive value is tagged IST (+05:30); blank / unparseable falls back to now() so a
    bad date never blocks a bill."""
    if value is None or str(value).strip() == "":
        return _now_iso()
    s = str(value).strip()
    if re.fullmatch(r"\d{10}", s):           # epoch seconds
        return datetime.fromtimestamp(int(s), tz=IST_TZ).isoformat()
    if re.fullmatch(r"\d{13}", s):           # epoch milliseconds
        return datetime.fromtimestamp(int(s) / 1000, tz=IST_TZ).isoformat()
    try:
        from dateutil import parser as _dtp
        # The POS always sends year-month-date (e.g. "2026-06-09 18:03:30"). Parse
        # year-first and NEVER day-first so 2026-06-09 is unambiguously 09 June 2026.
        dt = _dtp.parse(s, yearfirst=True, dayfirst=False)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST_TZ)
        return dt.isoformat()
    except Exception:
        logger.warning(f"Unparseable POS order_time '{s}' — defaulting to now()")
        return _now_iso()


def _ok(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"status_code": 200, "response": payload}


def _err(status: int, message: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    body = {"message": message}
    if extra:
        body.update(extra)
    return {"status_code": status, "response": body}


async def _log_api(*, endpoint: str, method: str, status: int, ms: int,
                    customer_mobile: Optional[str] = None,
                    bill_number: Optional[str] = None,
                    store_id: Optional[str] = None,
                    error: Optional[str] = None,
                    payload: Optional[dict] = None,
                    response: Optional[dict] = None,
                    api_key_label: Optional[str] = None,
                    actor_ip: Optional[str] = None):
    """Log a POS API call with full request + response for Live Monitor."""
    await api_logs_col.insert_one({
        "id": uuid.uuid4().hex,
        "endpoint": endpoint,
        "method": method,
        "status_code": status,
        "response_time_ms": ms,
        "customer_mobile": customer_mobile,
        "bill_number": bill_number,
        "store_id": store_id,
        "error_reason": error,
        "request_payload": payload,
        "response_payload": response,
        "api_key_label": api_key_label,
        "actor_ip": actor_ip,
        "source": "pos_ewards",
        "timestamp": _now_iso(),
    })


async def _validate_creds(x_api_key: Optional[str], merchant_id: Optional[str],
                           customer_key: Optional[str]):
    """Validate x-api-key + merchant_id + customer_key against pos_credentials.

    Returns a precise 403 reason so the integrating POS team can self-diagnose
    which check failed without exposing the real credential values.
    """
    if not x_api_key:
        raise HTTPException(403, "Missing x-api-key header")
    # Reject keys with stray whitespace / tabs / newlines — common copy-paste hazard
    if x_api_key != x_api_key.strip():
        raise HTTPException(403, "x-api-key contains leading/trailing whitespace — please trim")
    cred = await pos_credentials_col.find_one(
        {"api_key": x_api_key, "is_active": True}, {"_id": 0}
    )
    if not cred:
        # Distinguish "key not found" vs "key inactive" for clarity
        inactive = await pos_credentials_col.find_one({"api_key": x_api_key}, {"_id": 0})
        if inactive:
            raise HTTPException(403, "x-api-key is inactive — contact KAZO admin to reactivate or rotate")
        raise HTTPException(403, "Invalid x-api-key — not recognised in this environment")
    if merchant_id and cred.get("merchant_id") != merchant_id:
        raise HTTPException(
            403,
            f"merchant_id mismatch — expected '{cred.get('merchant_id')}', received '{merchant_id}'",
        )
    # NOTE: customer_key is NOT validated as a secret. Per the KAZO POS contract it is
    # the per-outlet STORE CODE — the (merchant_id + customer_key) combo identifies the
    # store on every bill (see _get_or_create_store_from_payload). The real authentication
    # secret is the 32-char x-api-key (+ merchant_id). customer_key therefore varies per
    # outlet and must not be rejected when it differs from the master credential's value.
    return cred


def _derive_tier(lifetime_spend: float, cfg: Optional[Dict[str, Any]] = None) -> str:
    """Assign a tier from the CONFIGURED Tier Rules based on the customer's cumulative
    lifetime spend (the running sum of all their bills). The customer sits in the highest
    tier whose `min_lifetime_spend` threshold they have reached. Fully config-driven — no
    hardcoded thresholds and no hardcoded tier names. Returns "" (untiered) only when no
    tiers are configured (never fabricates a tier the brand hasn't defined)."""
    rules = [t for t in ((cfg or {}).get("tier_rules") or []) if t.get("is_active", True)]
    if not rules:
        return ""
    rules = sorted(rules, key=lambda t: _parse_float(t.get("min_lifetime_spend", 0)))
    chosen = rules[0]
    for t in rules:
        if lifetime_spend >= _parse_float(t.get("min_lifetime_spend", 0)):
            chosen = t
        else:
            break
    return chosen.get("tier") or rules[0].get("tier") or ""


def _parse_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (ValueError, TypeError, AttributeError):
        return default


def _parse_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "").strip())
    except (ValueError, TypeError, AttributeError):
        return default


def _gst_from_taxes(taxes: Any) -> float:
    """Sum of tax line-items named 'GST' from the POS `taxes` array.
       KAZO rule: Tax = taxes.amount (against name = 'GST')."""
    if not isinstance(taxes, list):
        return 0.0
    total = 0.0
    for t in taxes:
        if isinstance(t, dict) and str(t.get("name", "")).strip().upper() == "GST":
            total += _parse_float(t.get("amount"))
    return total


def _compute_earn_points(base: float, cfg: Dict[str, Any], multiplier: float = 1.0) -> int:
    """Points earned for a loyalty `base` amount.

    Two ways to configure earning from the Loyalty Rules editor:

    1) Global rate + tier multiplier (when an Earn Engine rate IS set):
         points_per_spend : base × earn_ratio   × tier_multiplier
         percent_of_spend : base × (percent/100) × tier_multiplier

    2) TIER-DRIVEN (when the Earn Engine rate is left blank / 0):
         The per-tier multiplier itself IS the % of the bill for that tier
         (e.g. Kazo Insider mult 2 -> 2% of bill, Trendsetter 3 -> 3%, Style Icon 5 -> 5%).
         Lets earning be driven purely by Tier Rules with nothing in the Earn Engine.
    """
    if base <= 0:
        return 0
    mode = (cfg.get("earn_mode") or "points_per_spend").strip()
    if mode == "percent_of_spend":
        rate = _parse_float(cfg.get("percent_of_spend", 0)) / 100.0
    else:
        rate = _parse_float(cfg.get("earn_ratio", 0))
    if rate > 0:
        return int(round(base * rate * (multiplier or 1.0)))
    # Tier-driven: no global earn rate configured -> the tier multiplier is the
    # percent-of-spend for that tier (mult 2 -> 2% of bill, etc.).
    tier_pct = (multiplier or 0) / 100.0
    return int(round(base * tier_pct))


def _loyalty_paused(cfg: Dict[str, Any], kind: str, when_iso: Optional[str] = None) -> tuple:
    """Is earning / burning currently suspended?

    `kind` is 'earn' or 'burn'. Returns (paused: bool, reason: str).
    Suspended when EITHER the master switch (earn_enabled / burn_enabled) is off,
    OR the relevant date (bill date for earn, today for burn) falls inside an active
    pause window (earn_burn_pauses) flagged to pause this kind.
    """
    if cfg.get(f"{kind}_enabled", True) is False:
        return True, f"{kind.capitalize()} is currently turned OFF in Loyalty Rules"
    day = (when_iso or _now_iso())[:10]
    for w in (cfg.get("earn_burn_pauses") or []):
        if not w.get("active", True):
            continue
        if not w.get(f"pause_{kind}", False):
            continue
        start = (w.get("start_date") or "")[:10]
        end = (w.get("end_date") or "")[:10]
        if start and end and start <= day <= end:
            label = w.get("label") or "scheduled pause"
            return True, f"{kind.capitalize()} paused — {label} ({start} to {end})"
    return False, ""


def _expiry_iso(when: Optional[str], days: int) -> str:
    """Expiry timestamp = transaction time + `days`. Live POS points expire 1 year
    (point_expiry_days) from the bill/transaction date."""
    try:
        base = datetime.fromisoformat(str(when).replace("Z", "+00:00"))
    except Exception:
        base = datetime.now(timezone.utc)
    return (base + timedelta(days=int(days or 365))).isoformat()


async def _get_or_create_store_from_payload(payload: Dict[str, Any], cred: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Resolve the store for a bill.

    CANONICAL RULE (KAZO): the (merchant_id + customer_key) combo from the POS payload
    identifies the store — `customer_key` IS the store code. Resolution order:
      1. Match a store already provisioned for this exact (merchant_id, customer_key) combo.
      2. Else link to an existing store whose `code` already equals customer_key
         (seeded / historic stores) and backfill the combo onto it.
      3. Else (STRICT_STORE_VALIDATION=true, default) REJECT the bill with a 400 —
         the outlet is not provisioned. When STRICT_STORE_VALIDATION=false, auto-create
         a brand-new store with code=customer_key (legacy behaviour).

    Legacy fallback (only when the payload carries NO customer_key): resolve from
    transaction.outlet / store_code / the credential's linked store_id.
    """
    txn = payload.get("transaction") or {}
    merchant_id = (payload.get("merchant_id") or cred.get("merchant_id") or "").strip()
    customer_key = str(payload.get("customer_key") or "").strip()

    # ---- Primary path: (merchant_id + customer_key) combo decides the store ----
    if customer_key:
        combo_match = await stores_col.find_one(
            {"pos_merchant_id": merchant_id, "pos_customer_key": customer_key}, {"_id": 0}
        )
        if combo_match:
            return combo_match
        # Link to an existing store whose code already equals the customer_key and
        # backfill the POS combo so subsequent bills match path 1 directly.
        # Try an exact match first (index-backed), then a case-insensitive match so
        # a casing difference between the store master and the POS payload (e.g.
        # "k00078" vs "K00078") never rejects an otherwise-valid bill.
        code_match = await stores_col.find_one({"code": customer_key}, {"_id": 0})
        if not code_match:
            code_match = await stores_col.find_one(
                {"code": {"$regex": f"^{re.escape(customer_key)}$", "$options": "i"}}, {"_id": 0})
        if code_match:
            await stores_col.update_one(
                {"id": code_match["id"]},
                {"$set": {"pos_merchant_id": merchant_id, "pos_customer_key": customer_key}},
            )
            code_match["pos_merchant_id"] = merchant_id
            code_match["pos_customer_key"] = customer_key
            return code_match
        # No store provisioned for this (merchant_id + customer_key) combo.
        if STRICT_STORE_VALIDATION:
            raise HTTPException(
                400,
                f"Unknown store code '{customer_key}'"
                + (f" for merchant_id '{merchant_id}'" if merchant_id else "")
                + " — this outlet is not provisioned in the KAZO store master. "
                "Add the store (Operations › Stores) before sending bills.",
            )
        # Non-strict (legacy) fallback: auto-create a new store master row for this
        # combo (details filled in manually later).
        outlet_name = txn.get("outlet") if isinstance(txn.get("outlet"), str) else None
        sid = uuid.uuid4().hex
        doc = {
            "id": sid,
            "code": customer_key,
            "name": outlet_name or customer_key,
            "city": "",
            "state": "",
            "region": "",
            "address": outlet_name or "",
            "is_active": True,
            "source": "pos_auto_customer_key",
            "pos_merchant_id": merchant_id,
            "pos_customer_key": customer_key,
            "created_at": _now_iso(),
        }
        await stores_col.insert_one(doc)
        doc.pop("_id", None)
        logger.info(
            f"Auto-created store from POS combo merchant_id={merchant_id} "
            f"customer_key={customer_key} (store_id={sid})"
        )
        return doc

    # ---- Legacy fallback: outlet name / store_code / cred.store_id ----
    outlet_name = txn.get("outlet") if isinstance(txn.get("outlet"), str) else None
    store_code = txn.get("store_code") if isinstance(txn.get("store_code"), str) else None
    if isinstance(txn.get("channel"), list) and txn["channel"]:
        outlet_name = outlet_name or (txn["channel"][0] or {}).get("name")
    if not outlet_name and not store_code and cred.get("store_id"):
        linked = await stores_col.find_one({"id": cred["store_id"]}, {"_id": 0})
        if linked:
            return linked
        if STRICT_STORE_VALIDATION:
            raise HTTPException(
                400,
                "Store could not be identified — no customer_key (store code) was sent "
                "and the credential is not linked to a provisioned store.",
            )
        return None
    fil = {}
    if store_code:
        fil["code"] = store_code
    elif outlet_name:
        fil["name"] = outlet_name
    if not fil:
        if STRICT_STORE_VALIDATION:
            raise HTTPException(
                400,
                "Store could not be identified — the bill carried no customer_key "
                "(store code), outlet name or store_code.",
            )
        return None
    existing = await stores_col.find_one(fil, {"_id": 0})
    if existing:
        return existing
    if STRICT_STORE_VALIDATION:
        ident = store_code or outlet_name or ""
        raise HTTPException(
            400,
            f"Unknown store '{ident}' — not found in the KAZO store master. "
            "Provision the store (Operations › Stores) before sending bills.",
        )
    # Non-strict (legacy) fallback: auto-create.
    sid = uuid.uuid4().hex
    doc = {
        "id": sid,
        "code": store_code or f"K{re.sub(r'[^A-Z0-9]+', '', (outlet_name or '').upper())[:8]}",
        "name": outlet_name or store_code or "KAZO Outlet",
        "city": "",
        "state": "",
        "region": "",
        "address": outlet_name or "",
        "is_active": True,
        "source": "pos_auto",
        "created_at": _now_iso(),
    }
    await stores_col.insert_one(doc)
    doc.pop("_id", None)
    return doc


# ---------------- Endpoint 1 — Customer Check ----------------
@router.post("/posCustomerCheck")
async def pos_customer_check(payload: Dict[str, Any], request: Request,
                              x_api_key: Optional[str] = Header(None, alias="x-api-key")):
    t0 = time.time()
    endpoint = "/api/pos/posCustomerCheck"
    try:
        cred = await _validate_creds(x_api_key, payload.get("merchant_id"), payload.get("customer_key"))
    except HTTPException as e:
        body = {"message": e.detail}
        await _log_api(endpoint=endpoint, method="POST", status=e.status_code,
                       ms=int((time.time() - t0) * 1000), error=e.detail,
                       payload=payload, response=body, actor_ip=request.client.host if request.client else None)
        raise

    mobile = _norm_mobile(payload.get("customer_mobile"))
    bill_amount = _parse_float(payload.get("bill_amount"))
    if not mobile:
        resp = _err(400, "Customer mobile is required")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                       error="missing customer_mobile", payload=payload, response=resp,
                       api_key_label=cred.get("label"))
        return resp

    cust = await customers_col.find_one({"mobile": mobile}, {"_id": 0})
    if not cust:
        resp = _err(400, "This number is not registered in your database")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                       error="not registered", payload=payload, response=resp,
                       api_key_label=cred.get("label"))
        return resp

    cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0}) or {}
    burn_ratio = cfg.get("burn_ratio", 0.25)
    min_redeem = cfg.get("min_redeem_points", 100)
    points_balance = int(cust.get("points_balance") or 0)
    redeemable_points = min(points_balance, int(bill_amount / burn_ratio)) if burn_ratio else 0
    if redeemable_points < min_redeem:
        redeemable_points = 0
    redeemable_value = round(redeemable_points * burn_ratio, 2)

    # Active coupons for this customer (assigned or open)
    now = datetime.now(timezone.utc)
    coupon_q = {
        "is_active": True,
        "valid_from": {"$lte": now.isoformat()},
        "valid_to": {"$gte": now.isoformat()},
    }
    coupons = await coupons_col.find(coupon_q, {"_id": 0}).sort("created_at", -1).limit(10).to_list(10)
    # Filter by tier if set
    cust_tier = cust.get("tier", "silver")
    rewards = []
    for c in coupons:
        if c.get("target_tier") and c["target_tier"] != cust_tier:
            continue
        rewards.append({
            "id": c.get("id"),
            "name": c.get("name"),
            "reward_code": c.get("code"),
        })

    details = {
        "name": cust.get("name") or "",
        "mobile": int(mobile) if mobile.isdigit() else mobile,
        "email": cust.get("email") or "",
        "gender": cust.get("gender") or "",
        "dob": cust.get("birthday") or "",
        "city": cust.get("city") or "",
        "state": cust.get("state") or "",
        "address": cust.get("address") or "",
        "region": cust.get("region") or "",
        "pincode": cust.get("pincode") or "",
        "marital": cust.get("marital") or "",
        "anniversary_date": cust.get("anniversary") or "0000-00-00",
        "current_points": points_balance,
        "tier": cust_tier,
    }

    resp = _ok({
        "details": details,
        "rewards": rewards,
        "redeemable_points": redeemable_points,
        "redeemable_points_value": redeemable_value,
        "website_link": "",
    })
    await _log_api(endpoint=endpoint, method="POST", status=200,
                   ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                   payload=payload, response=resp, api_key_label=cred.get("label"),
                   actor_ip=request.client.host if request.client else None)
    return resp


# ---------------- Endpoint 2 — Customer Check OTP Request ----------------
async def _create_otp(*, purpose: str, mobile: str, payload: Dict[str, Any], cred_label: str) -> Dict[str, Any]:
    otp = f"{random.randint(100000, 999999)}"
    otp_id = random.randint(100000, 999999)
    await pos_otp_col.insert_one({
        "otp_id": otp_id,
        "otp": otp,
        "mobile": mobile,
        "purpose": purpose,
        "verified": False,
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=OTP_TTL_SECONDS)).isoformat(),
        "created_at": _now_iso(),
        "cred_label": cred_label,
        "payload_snapshot": payload,
    })
    # Dispatch the OTP over SMS via any active 'otp'-trigger template (best-effort —
    # never block OTP creation if the gateway/template is missing). The template body
    # uses the {{otp}} variable, which is rendered here.
    try:
        from routes.communications_routes import fire_event
        _fire_and_forget(fire_event("otp", mobile, {"otp": otp, "purpose": purpose}))
    except Exception as e:
        logger.warning(f"OTP SMS dispatch failed for {mobile}: {e}")
    return {"otp": otp, "otp_id": otp_id}


@router.post("/posCustomerCheckRequest")
async def pos_customer_check_request(payload: Dict[str, Any], request: Request,
                                       x_api_key: Optional[str] = Header(None, alias="x-api-key")):
    t0 = time.time()
    endpoint = "/api/pos/posCustomerCheckRequest"
    try:
        cred = await _validate_creds(x_api_key, payload.get("merchant_id"), payload.get("customer_key"))
    except HTTPException as e:
        body = {"message": e.detail}
        await _log_api(endpoint=endpoint, method="POST", status=e.status_code,
                       ms=int((time.time() - t0) * 1000), error=e.detail,
                       payload=payload, response=body)
        raise

    mobile = _norm_mobile(payload.get("customer_mobile"))
    if not mobile:
        resp = _err(400, "Customer mobile is required")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), payload=payload, response=resp,
                       api_key_label=cred.get("label"))
        return resp

    cust = await customers_col.find_one({"mobile": mobile}, {"_id": 0})
    if not cust:
        resp = _err(400, "This number is not registered in your database")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                       payload=payload, response=resp, api_key_label=cred.get("label"))
        return resp

    otp_data = await _create_otp(purpose="customer_check", mobile=mobile, payload=payload,
                                  cred_label=cred.get("label", ""))
    body: Dict[str, Any] = {
        "message": "An OTP has been sent on your mobile",
        "authentication": True,
        "otp_id": otp_data["otp_id"],
    }
    if TEST_MODE_RETURN_OTP:
        body["otp_demo"] = otp_data["otp"]  # test/dev only
    resp = _ok(body)
    await _log_api(endpoint=endpoint, method="POST", status=200,
                   ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                   payload=payload, response=resp, api_key_label=cred.get("label"))
    return resp


# ---------------- Endpoint 3 — Resend OTP (customer check) ----------------
@router.post("/resendOtPcustomercheck")
async def resend_otp_customer_check(payload: Dict[str, Any], request: Request,
                                      x_api_key: Optional[str] = Header(None, alias="x-api-key")):
    t0 = time.time()
    endpoint = "/api/pos/resendOtPcustomercheck"
    try:
        cred = await _validate_creds(x_api_key, payload.get("merchant_id"), payload.get("customer_key"))
    except HTTPException as e:
        await _log_api(endpoint=endpoint, method="POST", status=e.status_code,
                       ms=int((time.time() - t0) * 1000), error=e.detail,
                       payload=payload, response={"message": e.detail})
        raise

    otp_id = _parse_int(payload.get("otp_id"))
    if not otp_id:
        resp = _err(400, "otp_id is required")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), payload=payload, response=resp)
        return resp
    session = await pos_otp_col.find_one({"otp_id": otp_id}, {"_id": 0})
    if not session:
        resp = _err(400, "OTP session not found")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), payload=payload, response=resp)
        return resp
    new_otp = f"{random.randint(100000, 999999)}"
    await pos_otp_col.update_one(
        {"otp_id": otp_id},
        {"$set": {"otp": new_otp,
                  "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=OTP_TTL_SECONDS)).isoformat()}},
    )
    msg = f"{new_otp} is your OTP. Valid for the next 10 minutes."
    body = {"message": "Resend OTP successfully", "otp_message": msg}
    if TEST_MODE_RETURN_OTP:
        body["otp"] = new_otp
    resp = _ok(body)
    await _log_api(endpoint=endpoint, method="POST", status=200,
                   ms=int((time.time() - t0) * 1000), customer_mobile=session.get("mobile"),
                   payload=payload, response=resp, api_key_label=cred.get("label"))
    return resp


# ---------------- Endpoint 4 — Customer Check OTP Verification ----------------
@router.post("/posCustomerOTPCheck")
async def pos_customer_otp_check(payload: Dict[str, Any], request: Request,
                                   x_api_key: Optional[str] = Header(None, alias="x-api-key")):
    t0 = time.time()
    endpoint = "/api/pos/posCustomerOTPCheck"
    try:
        cred = await _validate_creds(x_api_key, payload.get("merchant_id"), payload.get("customer_key"))
    except HTTPException as e:
        await _log_api(endpoint=endpoint, method="POST", status=e.status_code,
                       ms=int((time.time() - t0) * 1000), error=e.detail,
                       payload=payload, response={"message": e.detail})
        raise

    mobile = _norm_mobile(payload.get("customer_mobile"))
    otp = str(payload.get("otp") or "").strip()
    if not mobile or not otp:
        resp = _err(400, "customer_mobile and otp required")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), payload=payload, response=resp)
        return resp

    session = await pos_otp_col.find_one({
        "mobile": mobile, "otp": otp, "purpose": "customer_check",
    }, {"_id": 0})
    test_bypass = ALLOW_TEST_OTP and otp == TEST_OTP
    if not session and not test_bypass:
        resp = _err(400, "Invalid OTP")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                       error="invalid OTP", payload=payload, response=resp,
                       api_key_label=cred.get("label"))
        return resp
    # Check expiry (test bypass skips expiry — there is no session)
    if session and session.get("expires_at") and session["expires_at"] < _now_iso():
        resp = _err(400, "OTP expired")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                       error="OTP expired", payload=payload, response=resp,
                       api_key_label=cred.get("label"))
        return resp
    if session:
        await pos_otp_col.update_one({"otp_id": session["otp_id"]}, {"$set": {"verified": True, "verified_at": _now_iso()}})
    audit_label = (cred.get("label") or "") + (" [TEST_OTP_BYPASS]" if test_bypass else "")

    # Return same shape as posCustomerCheck
    cust = await customers_col.find_one({"mobile": mobile}, {"_id": 0})
    if not cust:
        resp = _err(400, "This number is not registered in your database")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                       payload=payload, response=resp)
        return resp
    cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0}) or {}
    burn_ratio = cfg.get("burn_ratio", 0.25)
    points_balance = int(cust.get("points_balance") or 0)
    bill_amount = _parse_float(payload.get("bill_amount"))
    redeemable_points = min(points_balance, int(bill_amount / burn_ratio)) if burn_ratio else 0
    redeemable_value = round(redeemable_points * burn_ratio, 2)
    coupons = await coupons_col.find({"is_active": True}, {"_id": 0}).sort("created_at", -1).limit(10).to_list(10)
    rewards = [{"id": c.get("id"), "name": c.get("name"), "reward_code": c.get("code")} for c in coupons]
    resp = _ok({
        "details": {
            "name": cust.get("name") or "",
            "mobile": int(mobile) if mobile.isdigit() else mobile,
            "email": cust.get("email") or "",
            "gender": cust.get("gender") or "",
            "dob": cust.get("birthday") or "",
            "city": cust.get("city") or "",
            "state": cust.get("state") or "",
            "current_points": points_balance,
            "tier": cust.get("tier", "silver"),
        },
        "rewards": rewards,
        "redeemable_points": redeemable_points,
        "redeemable_points_value": redeemable_value,
        "website_link": "",
    })
    await _log_api(endpoint=endpoint, method="POST", status=200,
                   ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                   payload=payload, response=resp, api_key_label=audit_label)
    return resp


# ---------------- Endpoint 5 — Add Member / Update Customer ----------------
@router.post("/posAddCustomer")
async def pos_add_customer(payload: Dict[str, Any], request: Request,
                            x_api_key: Optional[str] = Header(None, alias="x-api-key")):
    t0 = time.time()
    endpoint = "/api/pos/posAddCustomer"
    try:
        cred = await _validate_creds(x_api_key, payload.get("merchant_id"), payload.get("customer_key"))
    except HTTPException as e:
        await _log_api(endpoint=endpoint, method="POST", status=e.status_code,
                       ms=int((time.time() - t0) * 1000), error=e.detail,
                       payload=payload, response={"message": e.detail})
        raise

    c = payload.get("customer") or {}
    mobile = _norm_mobile(c.get("mobile"))
    name = (c.get("name") or "").strip()
    if not name or not _is_valid_indian_mobile(mobile):
        resp = _err(400, "A valid Indian mobile number (10 digits, starts 6-9) and a name are required")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                       error="invalid_mobile_or_name",
                       payload=payload, response=resp, api_key_label=cred.get("label"))
        return resp

    existing = await customers_col.find_one({"mobile": mobile}, {"_id": 0})
    update = {
        "name": name,
        "email": c.get("email") or (existing.get("email") if existing else None),
        "address": c.get("address") or (existing.get("address") if existing else None),
        "city": c.get("city") or (existing.get("city") if existing else None),
        "state": c.get("state") or (existing.get("state") if existing else None),
        "gender": c.get("gender") or (existing.get("gender") if existing else None),
        "birthday": (c.get("dob") or (existing.get("birthday") if existing else None)) or None,
        "anniversary": (c.get("doa") or (existing.get("anniversary") if existing else None)) or None,
        "marital": c.get("marital") or (existing.get("marital") if existing else None),
        "source": "pos_ewards",
        "updated_at": _now_iso(),
    }
    if existing:
        await customers_col.update_one({"mobile": mobile}, {"$set": update})
        resp = _ok({"message": "Profile updated successfully"})
    else:
        cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0}) or {}
        welcome_bonus_points = int(_parse_float(cfg.get("welcome_bonus", 0)) or 0)
        update.update({
            "id": uuid.uuid4().hex,
            "mobile": mobile,
            "tier": _derive_tier(0, cfg) or "",
            "points_balance": welcome_bonus_points,
            "lifetime_points_earned": welcome_bonus_points,
            "lifetime_points_redeemed": 0,
            "lifetime_spend": 0,
            "visit_count": 0,
            "welcome_bonus_given": welcome_bonus_points > 0,
            "created_at": _now_iso(),
        })
        await customers_col.insert_one(update)
        # Welcome bonus — single GLOBAL bonus, credited ONCE when the customer joins.
        if welcome_bonus_points > 0:
            await points_ledger_col.insert_one({
                "id": uuid.uuid4().hex,
                "customer_id": update["id"],
                "customer_mobile": mobile,
                "type": "bonus",
                "points": welcome_bonus_points,
                "reference_type": "welcome",
                "reference_id": None,
                "note": "Welcome bonus (joined programme)",
                "expires_at": _expiry_iso(_now_iso(), int(cfg.get("point_expiry_days", 365) or 365)),
                "created_at": _now_iso(),
            })
        resp = _ok({"message": "Member successfully registered"})
        # Welcome / registration SMS (best-effort, non-blocking — only on first
        # registration). Fires every active template registered for the
        # "registration" event_trigger; reads sender ID / DLT / api key from the
        # configured Provider Settings (no dummy/fallback values).
        try:
            from routes.communications_routes import fire_event
            _fire_and_forget(fire_event("registration", mobile, {
                "name": name.split(" ")[0] or "there",
                "mobile": mobile,
            }))
        except Exception:
            pass

    await _log_api(endpoint=endpoint, method="POST", status=200,
                   ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                   payload=payload, response=resp, api_key_label=cred.get("label"))
    return resp


# ---------------- Endpoint 6 — Redeem Point Request (OTP or non-OTP) ----------------
@router.post("/posRedeemPointRequest")
async def pos_redeem_point_request(payload: Dict[str, Any], request: Request,
                                     x_api_key: Optional[str] = Header(None, alias="x-api-key")):
    t0 = time.time()
    endpoint = "/api/pos/posRedeemPointRequest"
    try:
        cred = await _validate_creds(x_api_key, payload.get("merchant_id"), payload.get("customer_key"))
    except HTTPException as e:
        await _log_api(endpoint=endpoint, method="POST", status=e.status_code,
                       ms=int((time.time() - t0) * 1000), error=e.detail,
                       payload=payload, response={"message": e.detail})
        raise

    mobile = _norm_mobile(payload.get("customer_mobile"))
    points_requested = _parse_int(payload.get("points"))
    txn = payload.get("transaction") or {}
    bill_number = (txn.get("number") or txn.get("id") or "").strip()
    if not mobile or points_requested <= 0:
        resp = _err(400, "Required fields are missing")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                       bill_number=bill_number, payload=payload, response=resp,
                       api_key_label=cred.get("label"))
        return resp

    cust = await customers_col.find_one({"mobile": mobile}, {"_id": 0})
    if not cust:
        resp = _err(400, "This number is not registered in your database")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                       bill_number=bill_number, payload=payload, response=resp,
                       api_key_label=cred.get("label"))
        return resp
    balance = int(cust.get("points_balance") or 0)
    if balance < points_requested:
        resp = _err(400, "Customer does not have Sufficient Balance to Redeem")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                       bill_number=bill_number, error="insufficient balance",
                       payload=payload, response=resp, api_key_label=cred.get("label"))
        return resp

    cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0}) or {}
    burn_paused, burn_reason = _loyalty_paused(cfg, "burn")
    if burn_paused:
        resp = _err(400, f"Point redemption is currently unavailable. {burn_reason}.")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                       bill_number=bill_number, error="burn paused",
                       payload=payload, response=resp, api_key_label=cred.get("label"))
        return resp
    burn_ratio = cfg.get("burn_ratio", 0.25)
    require_otp = bool(cfg.get("require_otp_for_redeem", True))
    points_value = round(points_requested * burn_ratio, 2)

    if require_otp:
        otp_data = await _create_otp(purpose="redeem_points", mobile=mobile, payload=payload,
                                      cred_label=cred.get("label", ""))
        body = {
            "points_value": str(points_requested),
            "points_monetary_value": str(points_value),
            "applicable_on": "Full bill",
            "authentication": True,
            "redeem_id": otp_data["otp_id"],
        }
        if TEST_MODE_RETURN_OTP:
            body["otp_demo"] = otp_data["otp"]
        resp = _ok(body)
        await _log_api(endpoint=endpoint, method="POST", status=200,
                       ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                       bill_number=bill_number, payload=payload, response=resp,
                       api_key_label=cred.get("label"))
        return resp
    else:
        # Non-OTP: deduct immediately
        await customers_col.update_one(
            {"id": cust["id"]},
            {"$inc": {"points_balance": -points_requested,
                       "lifetime_points_redeemed": points_requested}},
        )
        await points_ledger_col.insert_one({
            "id": uuid.uuid4().hex,
            "customer_id": cust["id"],
            "type": "redeem",
            "points": -points_requested,
            "reference_type": "transaction",
            "reference_id": bill_number,
            "note": "POS non-OTP redemption",
            "created_at": _now_iso(),
        })
        body = {
            "points_value": str(points_requested),
            "points_monetary_value": str(points_value),
            "authentication": False,
        }
        resp = _ok(body)
        await _log_api(endpoint=endpoint, method="POST", status=200,
                       ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                       bill_number=bill_number, payload=payload, response=resp,
                       api_key_label=cred.get("label"))
        return resp


# ---------------- Endpoint 7 — Resend OTP (for redeem) ----------------
@router.post("/resendOtPosRedeemPointRequest")
async def resend_otp_redeem(payload: Dict[str, Any], request: Request,
                              x_api_key: Optional[str] = Header(None, alias="x-api-key")):
    t0 = time.time()
    endpoint = "/api/pos/resendOtPosRedeemPointRequest"
    try:
        cred = await _validate_creds(x_api_key, payload.get("merchant_id"), payload.get("customer_key"))
    except HTTPException as e:
        await _log_api(endpoint=endpoint, method="POST", status=e.status_code,
                       ms=int((time.time() - t0) * 1000), error=e.detail,
                       payload=payload, response={"message": e.detail})
        raise

    otp_id = _parse_int(payload.get("otp_id"))
    session = await pos_otp_col.find_one({"otp_id": otp_id, "purpose": "redeem_points"}, {"_id": 0})
    if not session:
        resp = _err(400, "OTP session not found")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), payload=payload, response=resp)
        return resp
    new_otp = f"{random.randint(100000, 999999)}"
    await pos_otp_col.update_one(
        {"otp_id": otp_id},
        {"$set": {"otp": new_otp,
                   "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=OTP_TTL_SECONDS)).isoformat()}},
    )
    msg = f"{new_otp} is your OTP to redeem points. Valid for 10 minutes."
    body = {"message": "Resend OTP successfully", "otp_message": msg}
    if TEST_MODE_RETURN_OTP:
        body["otp"] = new_otp
    resp = _ok(body)
    await _log_api(endpoint=endpoint, method="POST", status=200,
                   ms=int((time.time() - t0) * 1000), customer_mobile=session.get("mobile"),
                   payload=payload, response=resp, api_key_label=cred.get("label"))
    return resp


# ---------------- Endpoint 8 — Redeem Point OTP Check ----------------
@router.post("/posRedeemPointOtpCheck")
async def pos_redeem_point_otp_check(payload: Dict[str, Any], request: Request,
                                       x_api_key: Optional[str] = Header(None, alias="x-api-key")):
    t0 = time.time()
    endpoint = "/api/pos/posRedeemPointOtpCheck"
    try:
        cred = await _validate_creds(x_api_key, payload.get("merchant_id"), payload.get("customer_key"))
    except HTTPException as e:
        await _log_api(endpoint=endpoint, method="POST", status=e.status_code,
                       ms=int((time.time() - t0) * 1000), error=e.detail,
                       payload=payload, response={"message": e.detail})
        raise

    mobile = _norm_mobile(payload.get("customer_mobile"))
    otp = str(payload.get("otp") or "").strip()
    points_requested = _parse_int(payload.get("points"))
    txn = payload.get("transaction") or {}
    bill_number = (txn.get("number") or txn.get("id") or "").strip()

    cust = await customers_col.find_one({"mobile": mobile}, {"_id": 0})
    if not cust:
        resp = _err(400, "This number is not registered in your database")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                       bill_number=bill_number, payload=payload, response=resp)
        return resp

    cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0}) or {}
    burn_ratio = cfg.get("burn_ratio", 0.25)
    require_otp = bool(cfg.get("require_otp_for_redeem", True))

    # SECURITY: OTP is mandatory when redemption requires OTP. Empty OTP is a tamper attempt.
    if require_otp and not otp:
        resp = _err(400, "OTP is required to verify this redemption")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                       bill_number=bill_number, error="missing OTP",
                       payload=payload, response=resp, api_key_label=cred.get("label"))
        return resp

    session = None
    test_bypass = ALLOW_TEST_OTP and otp == TEST_OTP
    if otp and not test_bypass:
        # Match the OTP session for this mobile+otp REGARDLESS of verified state, so a
        # legitimate POS retry / double-submit (network retry, cashier re-tap, slow
        # response) is handled idempotently instead of failing as "Invalid OTP" — the
        # 2nd call would otherwise miss a now-verified session. Only a genuinely-unknown
        # OTP value is treated as Invalid.
        session = await pos_otp_col.find_one({
            "mobile": mobile, "otp": otp, "purpose": "redeem_points",
        }, {"_id": 0})
        if not session:
            resp = _err(400, "Invalid OTP.")
            await _log_api(endpoint=endpoint, method="POST", status=400,
                           ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                           bill_number=bill_number, error="invalid OTP",
                           payload=payload, response=resp, api_key_label=cred.get("label"))
            return resp

        # IDEMPOTENCY: this OTP's redemption already completed (POS retry / double-tap).
        # Return the SAME success WITHOUT deducting points again.
        if session.get("redeemed"):
            resp = _ok({
                "points_value": str(session.get("redeemed_points", points_requested)),
                "points_monetary_value": str(session.get(
                    "redeemed_value", round(points_requested * burn_ratio, 2))),
                "already_redeemed": True,
            })
            await _log_api(endpoint=endpoint, method="POST", status=200,
                           ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                           bill_number=bill_number, error="idempotent retry (already redeemed)",
                           payload=payload, response=resp, api_key_label=cred.get("label"))
            return resp

        if session.get("expires_at", "") < _now_iso():
            resp = _err(400, "OTP expired. Please request a new one.")
            await _log_api(endpoint=endpoint, method="POST", status=400,
                           ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                           bill_number=bill_number, error="OTP expired",
                           payload=payload, response=resp, api_key_label=cred.get("label"))
            return resp

        # SECURITY: parameter-tampering defense — points must equal the value the OTP was issued for
        snapshot = session.get("payload_snapshot") or {}
        original_points = _parse_int(snapshot.get("points"))
        if original_points and original_points != points_requested:
            resp = _err(400,
                         f"Redemption amount mismatch — OTP was issued for {original_points} "
                         f"points but the request is for {points_requested} points. "
                         f"Please re-initiate the redemption with the correct amount.")
            await _log_api(endpoint=endpoint, method="POST", status=400,
                           ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                           bill_number=bill_number,
                           error=f"points tamper: otp={original_points} req={points_requested}",
                           payload=payload, response=resp, api_key_label=cred.get("label"))
            return resp

        # Bill-number tampering defense (when both sides have a bill)
        orig_bill = ((snapshot.get("transaction") or {}).get("number")
                       or (snapshot.get("transaction") or {}).get("id") or "").strip()
        if orig_bill and bill_number and orig_bill != bill_number:
            resp = _err(400,
                         "Bill number mismatch — OTP was issued for a different transaction.")
            await _log_api(endpoint=endpoint, method="POST", status=400,
                           ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                           bill_number=bill_number,
                           error=f"bill tamper: otp={orig_bill} req={bill_number}",
                           payload=payload, response=resp, api_key_label=cred.get("label"))
            return resp

    if int(cust.get("points_balance") or 0) < points_requested:
        resp = _err(400, "Customer does not have Sufficient Balance to Redeem")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                       bill_number=bill_number, error="insufficient balance",
                       payload=payload, response=resp, api_key_label=cred.get("label"))
        return resp

    points_value = round(points_requested * burn_ratio, 2)

    # Atomically CLAIM the redemption for a real OTP session so two concurrent
    # duplicate submissions can never both deduct points. The winner sets
    # redeemed=True; any loser falls into the idempotent-success path below.
    if session is not None:
        claimed = await pos_otp_col.find_one_and_update(
            {"otp_id": session["otp_id"], "redeemed": {"$ne": True}},
            {"$set": {"verified": True, "verified_at": _now_iso(), "redeemed": True,
                       "redeemed_points": points_requested, "redeemed_value": points_value}},
        )
        if not claimed:
            resp = _ok({
                "points_value": str(points_requested),
                "points_monetary_value": str(points_value),
                "already_redeemed": True,
            })
            await _log_api(endpoint=endpoint, method="POST", status=200,
                           ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                           bill_number=bill_number, error="idempotent race (already redeemed)",
                           payload=payload, response=resp, api_key_label=cred.get("label"))
            return resp

    await customers_col.update_one(
        {"id": cust["id"]},
        {"$inc": {"points_balance": -points_requested,
                   "lifetime_points_redeemed": points_requested}},
    )
    await points_ledger_col.insert_one({
        "id": uuid.uuid4().hex,
        "customer_id": cust["id"],
        "type": "redeem",
        "points": -points_requested,
        "reference_type": "transaction",
        "reference_id": bill_number,
        "note": "POS OTP redemption",
        "created_at": _now_iso(),
    })
    resp = _ok({
        "points_value": str(points_requested),
        "points_monetary_value": str(points_value),
    })
    await _log_api(endpoint=endpoint, method="POST", status=200,
                   ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                   bill_number=bill_number, payload=payload, response=resp,
                   api_key_label=cred.get("label"))
    return resp


# ---------------- Endpoint 9 — Bill Settlement (THE BIG ONE) ----------------
@router.post("/posAddPoint")
async def pos_add_point(payload: Dict[str, Any], request: Request,
                         x_api_key: Optional[str] = Header(None, alias="x-api-key")):
    t0 = time.time()
    endpoint = "/api/pos/posAddPoint"
    try:
        cred = await _validate_creds(x_api_key, payload.get("merchant_id"), payload.get("customer_key"))
    except HTTPException as e:
        await _log_api(endpoint=endpoint, method="POST", status=e.status_code,
                       ms=int((time.time() - t0) * 1000), error=e.detail,
                       payload=payload, response={"message": e.detail})
        raise

    c = payload.get("customer") or {}
    txn = payload.get("transaction") or {}
    raw_mobile = c.get("mobile")
    mobile = _norm_mobile(raw_mobile)
    bill_number = (txn.get("number") or txn.get("id") or "").strip()
    if not bill_number:
        resp = _err(400, "Required fields are missing")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                       bill_number=bill_number, error="missing bill number",
                       payload=payload, response=resp, api_key_label=cred.get("label"))
        return resp

    # Duplicate bill check
    if await transactions_col.find_one({"bill_number": bill_number}, {"_id": 0, "id": 1}):
        resp = _err(400, "Same bill number cannot be accepted which has been entered earlier for the same customer key")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                       bill_number=bill_number, error="duplicate bill",
                       payload=payload, response=resp, api_key_label=cred.get("label"))
        return resp

    # Resolve store — STRICT: reject bills for unprovisioned store codes
    try:
        store = await _get_or_create_store_from_payload(payload, cred)
    except HTTPException as e:
        resp = _err(e.status_code, e.detail)
        await _log_api(endpoint=endpoint, method="POST", status=e.status_code,
                       ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                       bill_number=bill_number, error=e.detail,
                       payload=payload, response=resp, api_key_label=cred.get("label"))
        return resp
    store_id = store["id"] if store else None
    store_name = store.get("name") if store else None
    store_code = store.get("code") if store else None

    # Amounts — KAZO canonical: `amount` is the PRE-TAX loyalty base; GST comes from the
    # taxes[] array. Bill Amount (with tax) = amount + GST. Computed up-front so a
    # NON-LOYALTY "Lost Customer" bill (invalid/no mobile) is still recorded with its
    # purchase value for analytics — just without earning any points.
    amount = _parse_float(txn.get("amount"))
    tax_gst = _gst_from_taxes(txn.get("taxes"))
    bill_with_tax = amount + tax_gst
    # Back-compat for older payloads that send gross/net explicitly
    gross = _parse_float(txn.get("gross_amount")) or bill_with_tax
    net = _parse_float(txn.get("net_amount")) or amount
    final_amount = amount or net
    discount = _parse_float(txn.get("discount"))
    # loyalty_flag: earn UNLESS the POS explicitly disables it.
    loyalty_flag = str(txn.get("loyalty_flag", "1")).strip().lower() not in {"0", "false", "no", "n", "off"}
    # Points are earned on `amount` (pre-tax). Fall back to loyalty_gross_amount/net for
    # legacy payloads that don't send `amount`.
    loyalty_base = amount or _parse_float(txn.get("loyalty_gross_amount")) or net
    order_time = _normalize_order_time(txn.get("order_time"))
    items = _map_pos_items(txn.get("items") or [])
    payment_mode = "unknown"
    pm_list = txn.get("payment_mode")
    if isinstance(pm_list, list) and pm_list:
        payment_mode = (pm_list[0] or {}).get("name") or "unknown"

    # --- VALID INDIAN MOBILE GATE (canonical) ---
    # Points/loyalty are granted ONLY to a VALID Indian mobile (10 digits starting 6-9).
    # A bill with an invalid / missing mobile is a NON-LOYALTY "Lost Customer": recorded
    # for purchase analytics, but NO points, NO loyalty account, NO SMS. Shown distinctly
    # on the Live Monitor + Lost-Customer KPI cards.
    if not _is_valid_indian_mobile(mobile):
        lost_reason = ("invalid_or_missing_mobile — not a valid Indian mobile "
                       "(need 10 digits starting 6-9); recorded as Lost Customer, no points")
        lost_txn = {
            "id": uuid.uuid4().hex,
            "customer_id": None,
            "customer_mobile": None,
            "customer_name": (c.get("name") or "").strip() or None,
            "raw_mobile": str(raw_mobile or "").strip() or None,
            "store_id": store_id, "store_name": store_name, "store_code": store_code,
            "bill_number": bill_number,
            "transaction_id": str(txn.get("id") or bill_number),
            "bill_date": order_time,
            "gross_amount": gross, "discount_amount": discount, "net_amount": net,
            "final_amount": final_amount, "amount": amount,
            "tax_amount": tax_gst, "bill_with_tax": bill_with_tax,
            "loyalty_gross_amount": loyalty_base,
            "items": items, "taxes": txn.get("taxes") or [], "charges": txn.get("charges") or [],
            "payment_mode": payment_mode, "channel": txn.get("channel"),
            "cashier_name": txn.get("cashier_name"),
            "points_earned": 0, "points_redeemed": 0,
            "loyalty_flag": loyalty_flag,
            "is_lost_customer": True,
            "loyalty_customer": False,
            "earn_skip_reason": lost_reason,
            "is_return": False,
            "source": "pos_ewards",
            "created_at": _now_iso(),
        }
        await transactions_col.insert_one(lost_txn)
        resp = _ok({"message": "Bill recorded (no loyalty — invalid or missing mobile)",
                    "order_id": lost_txn["id"], "points_earned": 0, "lost_customer": True,
                    "earn_skip_reason": lost_reason})
        await _log_api(endpoint=endpoint, method="POST", status=200,
                       ms=int((time.time() - t0) * 1000), customer_mobile=None,
                       bill_number=bill_number, store_id=store_id,
                       error="lost_customer_invalid_mobile",
                       payload=payload, response=resp, api_key_label=cred.get("label"))
        return resp

    # Upsert customer (valid Indian mobile only)
    cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0}) or {}
    existing = await customers_col.find_one({"mobile": mobile}, {"_id": 0})
    customer_doc_update = {
        "name": (c.get("name") or "").strip() or (existing.get("name") if existing else ""),
        "email": c.get("email") or (existing.get("email") if existing else None),
        "city": c.get("city") or (existing.get("city") if existing else None),
        "state": c.get("state") or (existing.get("state") if existing else None),
        "birthday": c.get("dob") or (existing.get("birthday") if existing else None),
        "anniversary": c.get("doa") or (existing.get("anniversary") if existing else None),
        "source": existing.get("source") if existing else "pos_ewards",
        "updated_at": _now_iso(),
    }
    if not existing:
        customer_doc_update.update({
            "id": uuid.uuid4().hex,
            "mobile": mobile,
            "tier": _derive_tier(0, cfg) or "",
            "points_balance": 0,
            "lifetime_points_earned": 0,
            "lifetime_points_redeemed": 0,
            "lifetime_spend": 0,
            "visit_count": 0,
            "first_purchase_at": _now_iso(),
            "created_at": _now_iso(),
        })
        await customers_col.insert_one(customer_doc_update)
        cust = customer_doc_update
        is_new_customer = True
    else:
        await customers_col.update_one({"mobile": mobile}, {"$set": customer_doc_update})
        cust = {**existing, **customer_doc_update}
        is_new_customer = False

    # Loyalty engine (cfg already loaded above)
    min_bill_for_earn = _parse_float(cfg.get("min_bill_for_earn", 0))
    # Client rule: add this bill to the customer's ACCUMULATED Total Billing, decide the
    # tier from the configured purchase ranges on that NEW total, THEN earn points at that
    # (post-bill) tier's multiplier.
    new_lifetime_spend = float(cust.get("lifetime_spend") or 0) + final_amount
    new_tier = _derive_tier(new_lifetime_spend, cfg)
    multiplier = 1.0
    for tr in cfg.get("tier_rules", []) or []:
        if tr.get("tier") == new_tier:
            multiplier = tr.get("earn_multiplier", 1.0)
            break

    points_earned = 0
    earn_skip_reason = None
    earn_paused, earn_pause_reason = _loyalty_paused(cfg, "earn", order_time)
    if not loyalty_flag:
        earn_skip_reason = "loyalty_flag_off — POS sent loyalty_flag != 1"
    elif earn_paused:
        earn_skip_reason = f"earn_paused — {earn_pause_reason}"
    elif loyalty_base <= 0:
        earn_skip_reason = ("zero_base — POS bill 'amount' is 0 / not sent "
                            "(no amount, loyalty_gross_amount or net_amount)")
    elif loyalty_base < min_bill_for_earn:
        earn_skip_reason = (f"below_min_bill — base {loyalty_base:.0f} < "
                            f"min_bill_for_earn {min_bill_for_earn:.0f}")
    else:
        points_earned = _compute_earn_points(loyalty_base, cfg, multiplier)
        if points_earned <= 0:
            earn_skip_reason = ("computed_zero — both the Earn Engine rate AND this "
                                "tier's multiplier are 0; set a tier multiplier (e.g. 2) "
                                "or an Earn Engine rate in Loyalty Rules")

    redemption = txn.get("redemption") or {}
    points_redeemed = _parse_int(redemption.get("redeemed_points"))
    coupon_code = (redemption.get("reward_id") or txn.get("coupon_code") or "").strip() or None

    # items[] and payment_mode were mapped up-front (shared with the Lost-Customer path).
    txn_id = uuid.uuid4().hex
    txn_doc = {
        "id": txn_id,
        "customer_id": cust["id"],
        "customer_mobile": mobile,
        "customer_name": cust.get("name"),
        "store_id": store_id,
        "store_name": store_name,
        "store_code": store_code,
        "bill_number": bill_number,
        "transaction_id": str(txn.get("id") or bill_number),
        "bill_date": order_time,
        "gross_amount": gross,
        "discount_amount": discount,
        "net_amount": net,
        "final_amount": final_amount,
        "amount": amount,
        "tax_amount": tax_gst,
        "bill_with_tax": bill_with_tax,
        "loyalty_gross_amount": loyalty_base,
        "loyalty_tax_amount": _parse_float(txn.get("loyalty_tax_amount")) or tax_gst,
        "loyalty_charge_amount": _parse_float(txn.get("loyalty_charge_amount")),
        "items": items,
        "taxes": txn.get("taxes") or [],
        "charges": txn.get("charges") or [],
        "payment_mode": payment_mode,
        "channel": txn.get("channel"),
        "cashier_name": txn.get("cashier_name"),
        "points_earned": points_earned,
        "points_redeemed": points_redeemed,
        "redemption_value": _parse_float(redemption.get("redeemed_amount")),
        "coupon_code": coupon_code,
        "loyalty_flag": loyalty_flag,
        "earn_pause_reason": earn_pause_reason or None,
        "is_return": False,
        "source": "pos_ewards",
        "created_at": _now_iso(),
    }
    await transactions_col.insert_one(txn_doc)

    # Customer aggregates (new_lifetime_spend + new_tier already computed above, pre-earn)
    new_visit_count = int(cust.get("visit_count") or 0) + 1
    old_tier = (cust.get("tier") or "silver")

    # Slab-wise tier-upgrade bonus — awarded ONCE when a customer crosses UP into a
    # higher tier (slab). Each tier defines its own `upgrade_bonus` in the loyalty config.
    upgrade_bonus_points = 0
    if new_tier != old_tier:
        ranked = sorted((cfg.get("tier_rules") or []), key=lambda x: x.get("min_lifetime_spend", 0))
        rank = {t.get("tier"): i for i, t in enumerate(ranked)}
        if rank.get(new_tier, 0) > rank.get(old_tier, 0):
            nt = next((t for t in ranked if t.get("tier") == new_tier), None)
            upgrade_bonus_points = int((nt or {}).get("upgrade_bonus", 0) or 0)

    # Welcome bonus — single GLOBAL bonus, credited ONCE when a customer first joins the
    # programme (here, their first bill created the customer). Never re-awarded on tier/slab moves.
    welcome_bonus_points = 0
    if is_new_customer and not cust.get("welcome_bonus_given"):
        welcome_bonus_points = int(_parse_float(cfg.get("welcome_bonus", 0)) or 0)

    new_balance = (int(cust.get("points_balance") or 0) + points_earned
                   + upgrade_bonus_points + welcome_bonus_points - points_redeemed)
    cust_set = {
        "points_balance": new_balance,
        "lifetime_spend": new_lifetime_spend,
        "visit_count": new_visit_count,
        "last_visit_at": _now_iso(),
        "tier": new_tier,
    }
    if welcome_bonus_points > 0:
        cust_set["welcome_bonus_given"] = True
    await customers_col.update_one(
        {"id": cust["id"]},
        {"$set": cust_set,
         "$inc": {
            "lifetime_points_earned": points_earned + upgrade_bonus_points + welcome_bonus_points,
            "lifetime_points_redeemed": points_redeemed,
        }},
    )

    # Ledger entries — live POS points expire `point_expiry_days` (default 365)
    # from the bill/transaction date.
    earn_expiry = _expiry_iso(order_time, int(cfg.get("point_expiry_days", 365) or 365))
    if points_earned > 0:
        await points_ledger_col.insert_one({
            "id": uuid.uuid4().hex,
            "customer_id": cust["id"],
            "customer_mobile": mobile,
            "type": "earn",
            "points": points_earned,
            "reference_type": "transaction",
            "reference_id": txn_id,
            "note": f"Bill {bill_number}",
            "expires_at": earn_expiry,
            "created_at": _now_iso(),
        })
    if upgrade_bonus_points > 0:
        await points_ledger_col.insert_one({
            "id": uuid.uuid4().hex,
            "customer_id": cust["id"],
            "customer_mobile": mobile,
            "type": "bonus",
            "points": upgrade_bonus_points,
            "reference_type": "tier_upgrade",
            "reference_id": txn_id,
            "note": f"Tier upgrade bonus: {old_tier} → {new_tier}",
            "expires_at": earn_expiry,
            "created_at": _now_iso(),
        })
    if welcome_bonus_points > 0:
        await points_ledger_col.insert_one({
            "id": uuid.uuid4().hex,
            "customer_id": cust["id"],
            "customer_mobile": mobile,
            "type": "bonus",
            "points": welcome_bonus_points,
            "reference_type": "welcome",
            "reference_id": txn_id,
            "note": "Welcome bonus (joined programme)",
            "expires_at": earn_expiry,
            "created_at": _now_iso(),
        })
    if points_redeemed > 0:
        # If a separate redeem call already happened, this is a no-op redemption from
        # the transaction itself (kept for ledger completeness).
        await points_ledger_col.insert_one({
            "id": uuid.uuid4().hex,
            "customer_id": cust["id"],
            "customer_mobile": mobile,
            "type": "redeem",
            "points": -points_redeemed,
            "reference_type": "transaction",
            "reference_id": txn_id,
            "note": f"Bill {bill_number}",
            "created_at": _now_iso(),
        })

    # Coupon redemption record
    if coupon_code:
        c = await coupons_col.find_one({"code": coupon_code}, {"_id": 0})
        if c:
            await coupons_col.update_one({"id": c["id"]}, {"$inc": {"times_used": 1}})
            await coupon_redemptions_col.insert_one({
                "id": uuid.uuid4().hex,
                "coupon_id": c["id"],
                "coupon_code": coupon_code,
                "customer_id": cust["id"],
                "customer_mobile": mobile,
                "store_id": store_id,
                "bill_number": bill_number,
                "transaction_id": txn_id,
                "discount_amount": _parse_float(redemption.get("redeemed_amount")),
                "created_at": _now_iso(),
            })

    resp_body = {"message": "Transaction details captured by Fundle successfully",
                 "order_id": txn_id, "points_earned": points_earned,
                 "new_balance": new_balance, "new_tier": new_tier}
    # Surface WHY a bill earned 0 points so it is visible in the API Monitor
    # (lets admins self-diagnose a misconfigured earn switch / min-bill / payload
    # without server access).
    if points_earned <= 0 and earn_skip_reason:
        resp_body["earn_skip_reason"] = earn_skip_reason
    resp = _ok(resp_body)

    # Fire transactional comms (best-effort, non-blocking — never delays POS response).
    # BOTH the "purchase" and "points_earned" triggers fire so the post-transaction
    # message goes out regardless of which event the template was configured under.
    # Sender ID / DLT entity / API key all come from the saved Provider Settings.
    try:
        from routes.communications_routes import fire_event
        comms_params = {
            "name": (cust.get("name") or "").split(" ")[0] or "there",
            "amount": f"{final_amount:,.0f}",
            "bill_no": bill_number,
            "store_name": store_name or "",
            "points_earned": points_earned,
            "points_balance": new_balance,
            "tier": new_tier,
        }
        # Auto-registration welcome SMS — only when THIS bill created the customer.
        # Uses the front-end-configured "registration" template + sender (no fallback).
        if is_new_customer:
            _fire_and_forget(fire_event("registration", mobile, {
                "name": (cust.get("name") or "").split(" ")[0] or "there",
                "mobile": mobile,
            }))
        _fire_and_forget(fire_event("purchase", mobile, comms_params))
        if points_earned > 0:
            _fire_and_forget(fire_event("points_earned", mobile, comms_params))
    except Exception:
        pass

    await _log_api(endpoint=endpoint, method="POST", status=200,
                   ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                   bill_number=bill_number, store_id=store_id,
                   error=(earn_skip_reason if points_earned <= 0 else None),
                   payload=payload, response=resp, api_key_label=cred.get("label"),
                   actor_ip=request.client.host if request.client else None)
    return resp


# ---------------- Endpoint 10 — Verify Coupon ----------------
@router.post("/posCouponDetails")
async def pos_coupon_details(payload: Dict[str, Any], request: Request,
                              x_api_key: Optional[str] = Header(None, alias="x-api-key")):
    t0 = time.time()
    endpoint = "/api/pos/posCouponDetails"
    try:
        cred = await _validate_creds(x_api_key, payload.get("merchant_id"), payload.get("customer_key"))
    except HTTPException as e:
        await _log_api(endpoint=endpoint, method="POST", status=e.status_code,
                       ms=int((time.time() - t0) * 1000), error=e.detail,
                       payload=payload, response={"message": e.detail})
        raise

    code = str(payload.get("coupon_code") or "").strip().upper()
    bill_amount = _parse_float(payload.get("bill_amount"))
    if not code:
        resp = _err(400, "Invalid code")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), payload=payload, response=resp)
        return resp

    c = await coupons_col.find_one({"code": code}, {"_id": 0})
    if not c:
        resp = _err(400, "Invalid code")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), payload=payload, response=resp,
                       api_key_label=cred.get("label"))
        return resp

    now_iso = _now_iso()
    if c.get("valid_to") and c["valid_to"] < now_iso:
        resp = _err(400, "Coupon Expired")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), payload=payload, response=resp,
                       api_key_label=cred.get("label"))
        return resp
    if c.get("valid_from") and c["valid_from"] > now_iso:
        resp = _err(400, "Coupon Code not applicable at this time")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), payload=payload, response=resp,
                       api_key_label=cred.get("label"))
        return resp
    if c.get("usage_limit") and c.get("times_used", 0) >= c["usage_limit"]:
        resp = _err(400, "Maximum Redemption Limit set for this Coupon has been exhausted.")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), payload=payload, response=resp,
                       api_key_label=cred.get("label"))
        return resp
    if c.get("min_bill_amount") and bill_amount < c["min_bill_amount"]:
        resp = _err(400, f"Minimum Bill Required to redeem this Code is {c['min_bill_amount']}")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), payload=payload, response=resp,
                       api_key_label=cred.get("label"))
        return resp

    discount_type = "percent" if c.get("coupon_type") == "percentage" else "Flat monetary"
    discount_value = c.get("discount_value")
    if c.get("coupon_type") == "percentage":
        applicable = bill_amount * discount_value / 100
        if c.get("max_discount"):
            applicable = min(applicable, c["max_discount"])
    else:
        applicable = discount_value

    resp = _ok({
        "coupon_name": c.get("name"),
        "coupon_code": c.get("code"),
        "discount_on": "bill",
        "discount_type": discount_type,
        "discount_value": str(discount_value),
        "applicable_discount_amount": str(round(applicable, 2)),
        "comment": c.get("description") or "",
        "special_offer": False,
        "offer_instruction": c.get("description") or "",
        "discount_code": c.get("code"),
    })
    await _log_api(endpoint=endpoint, method="POST", status=200,
                   ms=int((time.time() - t0) * 1000), payload=payload, response=resp,
                   api_key_label=cred.get("label"))
    return resp


# ---------------- Endpoint 11 — Redeem Coupon ----------------
@router.post("/posRedeemCoupon")
async def pos_redeem_coupon(payload: Dict[str, Any], request: Request,
                             x_api_key: Optional[str] = Header(None, alias="x-api-key")):
    t0 = time.time()
    endpoint = "/api/pos/posRedeemCoupon"
    try:
        cred = await _validate_creds(x_api_key, payload.get("merchant_id"), payload.get("customer_key"))
    except HTTPException as e:
        await _log_api(endpoint=endpoint, method="POST", status=e.status_code,
                       ms=int((time.time() - t0) * 1000), error=e.detail,
                       payload=payload, response={"message": e.detail})
        raise

    # Reuse verify logic
    code = str(payload.get("coupon_code") or "").strip().upper()
    bill_amount = _parse_float(payload.get("bill_amount"))
    mobile = _norm_mobile(payload.get("customer_mobile"))
    txn = payload.get("transaction") or {}
    bill_number = (txn.get("number") or txn.get("id") or "").strip()

    c = await coupons_col.find_one({"code": code}, {"_id": 0})
    if not c:
        resp = _err(400, "Invalid code")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                       bill_number=bill_number, payload=payload, response=resp,
                       api_key_label=cred.get("label"))
        return resp
    now_iso = _now_iso()
    if c.get("valid_to") and c["valid_to"] < now_iso:
        resp = _err(400, "Coupon Expired")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                       bill_number=bill_number, payload=payload, response=resp,
                       api_key_label=cred.get("label"))
        return resp
    if c.get("usage_limit") and c.get("times_used", 0) >= c["usage_limit"]:
        resp = _err(400, "Maximum Redemption Limit set for this Coupon has been exhausted.")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                       bill_number=bill_number, payload=payload, response=resp,
                       api_key_label=cred.get("label"))
        return resp
    if c.get("min_bill_amount") and bill_amount < c["min_bill_amount"]:
        resp = _err(400, f"Minimum Bill Required to redeem this Code is {c['min_bill_amount']}")
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                       bill_number=bill_number, payload=payload, response=resp,
                       api_key_label=cred.get("label"))
        return resp

    discount_type = "percent" if c.get("coupon_type") == "percentage" else "Flat monetary"
    discount_value = c.get("discount_value")
    if c.get("coupon_type") == "percentage":
        applicable = bill_amount * discount_value / 100
        if c.get("max_discount"):
            applicable = min(applicable, c["max_discount"])
    else:
        applicable = discount_value

    await coupons_col.update_one({"id": c["id"]}, {"$inc": {"times_used": 1}})
    await coupon_redemptions_col.insert_one({
        "id": uuid.uuid4().hex,
        "coupon_id": c["id"],
        "coupon_code": code,
        "customer_mobile": mobile,
        "bill_number": bill_number,
        "discount_amount": round(applicable, 2),
        "source": "pos_ewards",
        "created_at": _now_iso(),
    })

    resp = _ok({
        "message": "Coupon successfully redeemed.",
        "discount_on": "bill",
        "discount_type": discount_type,
        "discount_value": str(discount_value),
        "applicable_discount_amount": str(round(applicable, 2)),
        "offer_instruction": c.get("description") or "",
        "discount_code": c.get("code"),
    })
    await _log_api(endpoint=endpoint, method="POST", status=200,
                   ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                   bill_number=bill_number, payload=payload, response=resp,
                   api_key_label=cred.get("label"))
    return resp


# ---------------- Endpoint 12 — Return Order ----------------
@router.post("/returnOrder")
async def return_order(payload: Dict[str, Any], request: Request,
                        x_api_key: Optional[str] = Header(None, alias="x-api-key")):
    t0 = time.time()
    endpoint = "/api/pos/returnOrder"
    try:
        cred = await _validate_creds(x_api_key, payload.get("merchant_id"), payload.get("customer_key"))
    except HTTPException as e:
        await _log_api(endpoint=endpoint, method="POST", status=e.status_code,
                       ms=int((time.time() - t0) * 1000), error=e.detail,
                       payload=payload, response={"message": e.detail})
        raise

    mobile = _norm_mobile(payload.get("mobile"))
    txn = payload.get("transaction") or {}
    orig_bill = (txn.get("number") or txn.get("BILL_GUID") or "").strip()
    # Mobile is the canonical loyalty identifier. The original bill number is no
    # longer a hard requirement — the POS may issue a return before the original
    # bill has synced to Fundle, so we never reject solely on a missing/unknown bill.
    if not mobile:
        resp = _err(400, "Required fields are missing (mobile is required for a loyalty return)", {"order_id": 0})
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                       bill_number=orig_bill, payload=payload, response=resp,
                       api_key_label=cred.get("label"))
        return resp

    # Best-effort lookup of the original bill — used only to enrich the return with
    # the original store/customer link. Its absence does NOT block the return.
    original = None
    if orig_bill:
        original = await transactions_col.find_one({"bill_number": orig_bill}, {"_id": 0})

    # Resolve the customer by mobile (canonical). Fall back to the original bill's
    # customer when the mobile master hasn't been populated yet.
    cust = await customers_col.find_one({"mobile": mobile}, {"_id": 0})
    if not cust and mobile.isdigit():
        cust = await customers_col.find_one({"mobile": int(mobile)}, {"_id": 0})
    if not cust and original and original.get("customer_id"):
        cust = await customers_col.find_one({"id": original["customer_id"]}, {"_id": 0})
    if not cust:
        resp = _err(400,
                     f"No loyalty customer found for mobile ******{mobile[-4:]}. "
                     f"Cannot process a loyalty return for an unregistered customer.",
                     {"order_id": 0})
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                       bill_number=orig_bill, error="customer not found",
                       payload=payload, response=resp, api_key_label=cred.get("label"))
        return resp
    customer_id = cust["id"]

    return_amount = _parse_float(txn.get("return_amount"))  # negative figure
    return_net = _parse_float(txn.get("return_net_amount"))
    return_gross = _parse_float(txn.get("return_loyalty_gross_amount") or txn.get("return_gross_amount"))

    cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0}) or {}
    # Reverse the same points the bill would have earned for this gross — honour the
    # configured earn mode (points_per_spend / percent_of_spend) so it stays symmetric.
    points_to_reverse = abs(_compute_earn_points(abs(return_gross), cfg, 1.0))

    # Reverse customer aggregates
    await customers_col.update_one(
        {"id": customer_id},
        {"$inc": {
            "points_balance": -points_to_reverse,
            "lifetime_points_earned": -points_to_reverse,
            "lifetime_spend": -abs(return_amount or return_net or return_gross),
        }},
    )

    return_id = uuid.uuid4().hex
    await transactions_col.insert_one({
        "id": return_id,
        "customer_id": customer_id,
        "customer_mobile": mobile,
        "store_id": (original or {}).get("store_id"),
        "store_name": (original or {}).get("store_name"),
        "bill_number": f"RET-{orig_bill or 'NOBILL'}-{uuid.uuid4().hex[:6]}",
        "original_bill_number": orig_bill or None,
        "bill_date": _now_iso(),
        "gross_amount": return_gross,
        "net_amount": return_net,
        "final_amount": return_amount,
        "points_earned": -points_to_reverse,
        "points_redeemed": 0,
        "is_return": True,
        "return_marker": "Return",
        "source": "pos_ewards",
        "created_at": _now_iso(),
    })
    await points_ledger_col.insert_one({
        "id": uuid.uuid4().hex,
        "customer_id": customer_id,
        "type": "adjust",
        "points": -points_to_reverse,
        "reference_type": "return",
        "reference_id": return_id,
        "note": f"Return of bill {orig_bill}" if orig_bill else "Return (no original bill ref)",
        "created_at": _now_iso(),
    })
    resp = _ok({"message": "Transaction details captured by Fundle successfully",
                "order_id": return_id})
    await _log_api(endpoint=endpoint, method="POST", status=200,
                   ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                   bill_number=orig_bill, store_id=(original or {}).get("store_id"),
                   payload=payload, response=resp, api_key_label=cred.get("label"))
    return resp


# ---------------- Endpoint 13 — Request Wallet Redemption ----------------
@router.post("/requestWalletRedemptionURL")
async def request_wallet_redemption(payload: Dict[str, Any], request: Request,
                                       x_api_key: Optional[str] = Header(None, alias="x-api-key")):
    t0 = time.time()
    endpoint = "/api/pos/requestWalletRedemptionURL"
    try:
        cred = await _validate_creds(x_api_key, payload.get("merchant_id"), payload.get("customer_key"))
    except HTTPException as e:
        body = {"errorCode": str(e.status_code), "ReturnMessage": e.detail}
        await _log_api(endpoint=endpoint, method="POST", status=e.status_code,
                       ms=int((time.time() - t0) * 1000), payload=payload, response=body)
        raise

    mobile = _norm_mobile(payload.get("mobileNo"))
    bill_guid = payload.get("billGUID")
    bill_value = _parse_float(payload.get("billValue"))
    proposed = _parse_float(payload.get("proposedDebitAmount"))
    cust = await customers_col.find_one({"mobile": mobile}, {"_id": 0})
    if not cust:
        body = {"errorCode": "800",
                "ReturnMessage": "Mobile number does not exist in your database"}
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                       payload=payload, response=body, api_key_label=cred.get("label"))
        return body

    cfg = await loyalty_config_col.find_one({"id": "default"}, {"_id": 0}) or {}
    burn_ratio = cfg.get("burn_ratio", 0.25)
    available_value = int(cust.get("points_balance") or 0) * burn_ratio
    if proposed > available_value:
        body = {"errorCode": "400",
                "ReturnMessage": f"You have insufficient balance to process this redemption. Current balance is {available_value:.2f}."}
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                       payload=payload, response=body, api_key_label=cred.get("label"))
        return body

    tx_id = uuid.uuid4().hex
    await pos_wallet_col.insert_one({
        "transaction_id": tx_id,
        "customer_mobile": mobile,
        "bill_guid": bill_guid,
        "bill_value": bill_value,
        "proposed_debit_amount": proposed,
        "status": "pending",
        "created_at": _now_iso(),
    })
    body = {"errorCode": "200",
            "ReturnMessage": "Request sent to customer successfully.",
            "transaction_id": tx_id}
    await _log_api(endpoint=endpoint, method="POST", status=200,
                   ms=int((time.time() - t0) * 1000), customer_mobile=mobile,
                   payload=payload, response=body, api_key_label=cred.get("label"))
    return body


@router.post("/getWalletRedemptionStatus")
async def get_wallet_redemption_status(payload: Dict[str, Any], request: Request,
                                          x_api_key: Optional[str] = Header(None, alias="x-api-key")):
    t0 = time.time()
    endpoint = "/api/pos/getWalletRedemptionStatus"
    try:
        cred = await _validate_creds(x_api_key, payload.get("merchant_id"), payload.get("customer_key"))
    except HTTPException as e:
        body = {"errorCode": str(e.status_code), "ReturnMessage": e.detail}
        await _log_api(endpoint=endpoint, method="POST", status=e.status_code,
                       ms=int((time.time() - t0) * 1000), payload=payload, response=body)
        raise

    tx_id = payload.get("transaction_id")
    rec = await pos_wallet_col.find_one({"transaction_id": tx_id}, {"_id": 0})
    if not rec:
        body = {"errorCode": "300", "ReturnMessage": "Transaction ID not found"}
        await _log_api(endpoint=endpoint, method="POST", status=400,
                       ms=int((time.time() - t0) * 1000), payload=payload, response=body,
                       api_key_label=cred.get("label"))
        return body
    if rec["status"] == "pending":
        body = {"errorCode": "400", "ReturnMessage": "Redemption is still pending from customer's end"}
    elif rec["status"] == "success":
        body = {"errorCode": "200", "ReturnMessage": "Value of 'proposedDebitAmount' successfully redeemed from customer's wallet."}
    else:
        body = {"errorCode": "700", "ReturnMessage": "Redemption cannot be processed right now."}
    await _log_api(endpoint=endpoint, method="POST", status=200,
                   ms=int((time.time() - t0) * 1000), customer_mobile=rec.get("customer_mobile"),
                   payload=payload, response=body, api_key_label=cred.get("label"))
    return body


# ---------------- Credentials management (admin-only via live_monitor_routes::admin_router) ----------------
# (The full CRUD endpoints live under /api/admin/pos-credentials with super_admin+brand_admin RBAC.)


# ---------------- Bootstrap default creds + test customer ----------------
async def bootstrap_pos_defaults():
    """Ensure at least one active POS credential exists + create test customer 966681235."""
    # 1. Default credentials
    if not await pos_credentials_col.find_one({"label": "kazo_default", "is_active": True}):
        api_key = secrets.token_urlsafe(32)
        await pos_credentials_col.insert_one({
            "id": uuid.uuid4().hex,
            "label": "kazo_default",
            "merchant_id": DEFAULT_MERCHANT_ID,
            "customer_key": DEFAULT_CUSTOMER_KEY,
            "api_key": api_key,
            "is_active": True,
            "created_at": _now_iso(),
            "note": "Auto-generated on first boot. Rotate from Admin UI.",
        })
        logger.info(f"Bootstrapped default POS credentials (api_key starts with {api_key[:8]}...)")

    # 2. Test customer 9266681235 (KAZO designated test number — 10-digit Indian)
    test_mobiles = ["9266681235", "966681235"]  # both seeded; primary is the 10-digit
    for test_mobile in test_mobiles:
        existing = await customers_col.find_one({"mobile": test_mobile}, {"_id": 0})
        if not existing:
            now = _now_iso()
            await customers_col.insert_one({
                "id": uuid.uuid4().hex,
                "mobile": test_mobile,
                "name": "KAZO Test Customer",
                "email": "testpos@kazo.com",
                "city": "Mumbai",
                "state": "Maharashtra",
                "tier": "gold",
                "points_balance": 5000,
                "lifetime_points_earned": 5000,
                "lifetime_points_redeemed": 0,
                "lifetime_spend": 50000,
                "visit_count": 12,
                "first_purchase_at": now,
                "last_visit_at": now,
                "source": "pos_test_seed",
                "created_at": now,
            })
            logger.info(f"Bootstrapped POS test customer {test_mobile} with 5000 points")
        elif (existing.get("points_balance") or 0) < 1000:
            # Top up if previously seeded customer drifted
            await customers_col.update_one(
                {"mobile": test_mobile},
                {"$set": {"points_balance": 5000, "tier": "gold"}, "$inc": {"lifetime_points_earned": 5000}},
            )

    # 3. Test coupons for the test customer (system-wide coupons; will surface in posCustomerCheck)
    test_coupons = [
        {"code": "POSTEST10", "name": "POS Test Flat ₹100",
         "coupon_type": "flat", "discount_value": 100,
         "min_bill_amount": 500, "description": "Test coupon — flat ₹100 off"},
        {"code": "POSTEST20PCT", "name": "POS Test 20% Off",
         "coupon_type": "percentage", "discount_value": 20,
         "min_bill_amount": 1000, "max_discount": 1000,
         "description": "Test coupon — 20% off max ₹1000"},
        {"code": "POSTESTVIP", "name": "POS Test VIP ₹500",
         "coupon_type": "flat", "discount_value": 500,
         "min_bill_amount": 2000, "description": "Test VIP coupon — flat ₹500"},
    ]
    now_iso = _now_iso()
    valid_from = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    valid_to = (datetime.now(timezone.utc) + timedelta(days=365)).isoformat()
    for c in test_coupons:
        if not await coupons_col.find_one({"code": c["code"]}):
            await coupons_col.insert_one({
                **c,
                "id": uuid.uuid4().hex,
                "valid_from": valid_from,
                "valid_to": valid_to,
                "usage_limit": 100000,
                "usage_limit_per_customer": 100,
                "require_otp": False,
                "is_active": True,
                "times_used": 0,
                "times_issued": 0,
                "source": "pos_test_seed",
                "created_at": now_iso,
            })

    # 4. Index for chunk lookup speed (idempotent)
    try:
        await api_logs_col.create_index([("timestamp", -1)])
        await api_logs_col.create_index([("endpoint", 1), ("timestamp", -1)])
        await transactions_col.create_index([("bill_date", -1)])
        await transactions_col.create_index([("bill_number", 1)], unique=False)
    except Exception:
        pass
