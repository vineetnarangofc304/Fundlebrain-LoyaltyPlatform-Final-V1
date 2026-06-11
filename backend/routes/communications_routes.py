"""Communications: SMS/WhatsApp/RCS templates + Karix provider integration.

- CRUD templates with channel/event_trigger/variables
- AI template generator (Emergent LLM)
- Real send via Karix Transactional SMS API + Karix WABA + RCS endpoints
- Provider config stored in MongoDB, editable from UI
- Auto-fired on POS transactions + coupon issuance via fire_event()
"""
import uuid
import re
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Any, Dict, List
import httpx
from fastapi import APIRouter, Depends, HTTPException, Body, BackgroundTasks
from pydantic import BaseModel

from database import (
    templates_col, provider_config_col, message_log_col, customers_col, stores_col, db,
)
from auth import get_current_user

# Bulk-send job state collection
bulk_jobs_col = db["bulk_send_jobs"]
from routes.ai_routes import EMERGENT_LLM_KEY, SYSTEM_PROMPT

logger = logging.getLogger("kazo-fundle.communications")

router = APIRouter(tags=["communications"])

CHANNELS = {"sms", "whatsapp", "rcs"}
EVENTS = {"none", "otp", "registration", "purchase", "coupon_issued", "points_earned",
          "tier_upgrade", "birthday", "win_back", "abandoned_visit", "campaign_bulk"}


# ---------------- Pydantic models ----------------
class TemplateIn(BaseModel):
    name: str
    channel: str
    event_trigger: str = "none"
    body: str
    variables: List[Dict[str, str]] = []  # [{key, label, example}]
    sender_id: Optional[str] = None        # for SMS (DLT)
    dlt_entity_id: Optional[str] = None
    dlt_template_id: Optional[str] = None  # DLT Content Template ID (REQUIRED for Indian SMS delivery)
    dlt_tm_id: Optional[str] = None        # DLT Telemarketer / chain ID (only for aggregator/multi-chain accounts)
    waba_template_id: Optional[str] = None  # for WhatsApp
    waba_params_order: List[str] = []       # ordered list of variable keys for WABA positional params
    waba_language: Optional[str] = "en"
    waba_category: Optional[str] = None     # MARKETING | UTILITY | AUTHENTICATION
    waba_approval_status: str = "pending"   # pending | approved | rejected (set by admin)
    waba_approval_note: Optional[str] = None
    preview_url: bool = False
    status: str = "draft"
    note: Optional[str] = None


class ProviderConfigIn(BaseModel):
    sms_api_key: Optional[str] = None
    sms_endpoint: Optional[str] = None
    sms_sender_id: Optional[str] = None
    sms_dlt_entity_id: Optional[str] = None
    sms_dlt_template_id: Optional[str] = None  # global fallback DLT content template id
    sms_dlt_tm_id: Optional[str] = None        # global DLT telemarketer / chain id (optional)
    whatsapp_endpoint: Optional[str] = None
    whatsapp_from_number: Optional[str] = None
    whatsapp_api_key: Optional[str] = None
    whatsapp_version: Optional[str] = None
    rcs_endpoint: Optional[str] = None
    rcs_api_key: Optional[str] = None
    rcs_from_number: Optional[str] = None


DEFAULT_CONFIG = {
    "sms_api_key": "8iRt9ytmxeyMgtpdMdOpMw==",
    "sms_endpoint": "https://pod2-japi.instaalerts.zone/httpapi/QueryStringReceiver",
    "sms_sender_id": "KAZOIN",
    "sms_dlt_entity_id": "",
    "sms_dlt_template_id": "",
    "sms_dlt_tm_id": "",
    "whatsapp_endpoint": "https://rcmapi.instaalerts.zone/services/rcm/sendMessage",
    "whatsapp_from_number": "919133325826",
    "whatsapp_api_key": "",
    "whatsapp_version": "v1.0.9",
    "rcs_endpoint": "https://rcmapi.instaalerts.zone/services/rcm/sendMessage",
    "rcs_api_key": "",
    "rcs_from_number": "",
}


async def _get_config() -> Dict[str, Any]:
    cfg = await provider_config_col.find_one({"_id": "singleton"}, {"_id": 0})
    if not cfg:
        cfg = dict(DEFAULT_CONFIG)
        await provider_config_col.insert_one({**cfg, "_id": "singleton"})
    return cfg


def _mask_secret(val: Optional[str]) -> Optional[str]:
    if not val:
        return val
    if len(val) <= 4:
        return "•" * len(val)
    return val[:3] + "•" * (len(val) - 6) + val[-3:]


def _normalize_mobile(mobile: str) -> str:
    """Karix expects 91XXXXXXXXXX (no +)."""
    digits = re.sub(r"\D", "", mobile or "")
    if digits.startswith("91") and len(digits) == 12:
        return digits
    if len(digits) == 10:
        return f"91{digits}"
    return digits


# ---------------- Template CRUD ----------------
@router.get("/templates")
async def list_templates(channel: Optional[str] = None, event_trigger: Optional[str] = None,
                          user: dict = Depends(get_current_user)):
    flt: Dict[str, Any] = {}
    if channel:
        flt["channel"] = channel
    if event_trigger:
        flt["event_trigger"] = event_trigger
    rows = await templates_col.find(flt, {"_id": 0}).sort("updated_at", -1).to_list(500)
    return {"rows": rows, "total": len(rows)}


@router.post("/templates")
async def create_template(body: TemplateIn, user: dict = Depends(get_current_user)):
    if body.channel not in CHANNELS:
        raise HTTPException(400, f"channel must be one of {sorted(CHANNELS)}")
    if body.event_trigger not in EVENTS:
        raise HTTPException(400, f"event_trigger must be one of {sorted(EVENTS)}")
    doc = body.model_dump()
    now = datetime.now(timezone.utc).isoformat()
    doc.update({
        "id": uuid.uuid4().hex,
        "created_at": now,
        "updated_at": now,
        "created_by": user["email"],
    })
    await templates_col.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/templates/{tid}")
async def get_template(tid: str, user: dict = Depends(get_current_user)):
    t = await templates_col.find_one({"id": tid}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Template not found")
    return t


@router.patch("/templates/{tid}")
async def update_template(tid: str, body: Dict[str, Any] = Body(...),
                           user: dict = Depends(get_current_user)):
    t = await templates_col.find_one({"id": tid})
    if not t:
        raise HTTPException(404, "Template not found")
    body.pop("id", None)
    body.pop("created_at", None)
    body.pop("created_by", None)
    if "channel" in body and body["channel"] not in CHANNELS:
        raise HTTPException(400, "Invalid channel")
    if "event_trigger" in body and body["event_trigger"] not in EVENTS:
        raise HTTPException(400, "Invalid event_trigger")
    body["updated_at"] = datetime.now(timezone.utc).isoformat()
    body["updated_by"] = user["email"]
    await templates_col.update_one({"id": tid}, {"$set": body})
    return await templates_col.find_one({"id": tid}, {"_id": 0})


@router.delete("/templates/{tid}")
async def delete_template(tid: str, user: dict = Depends(get_current_user)):
    res = await templates_col.delete_one({"id": tid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Template not found")
    return {"deleted": True}


# ---------------- AI suggestion ----------------
class AISuggestIn(BaseModel):
    channel: str
    event_trigger: str = "none"
    brief: str
    tone: Optional[str] = "premium and concise"
    max_chars: Optional[int] = None  # SMS limit cue


@router.post("/templates/ai-suggest")
async def ai_suggest(body: AISuggestIn, user: dict = Depends(get_current_user)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "AI key not configured")
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    import time
    import json

    char_hint = {"sms": 160, "whatsapp": 1024, "rcs": 2048}.get(body.channel, 160)
    if body.max_chars:
        char_hint = body.max_chars

    prompt = (
        f"You are a copywriter for KAZO (premium Indian women's fashion).\n\n"
        f"Channel: {body.channel.upper()}\n"
        f"Event trigger: {body.event_trigger}\n"
        f"Brief: {body.brief}\n"
        f"Tone: {body.tone}\n\n"
        f"Write a {body.channel.upper()} message body. Constraints:\n"
        f"  - Max {char_hint} characters\n"
        f"  - Use these mustache variables where natural: {{name}}, {{amount}}, {{bill_no}}, "
        f"{{store_name}}, {{coupon_code}}, {{points_earned}}, {{points_balance}}, {{tier}}\n"
        f"  - For SMS: end with '-KAZO' or include sender brand\n"
        f"  - No emojis\n"
        f"  - Tasteful, editorial, never gimmicky\n\n"
        f"Output strict JSON: {{\"body\": <string>, \"variables\": [{{\"key\": \"name\", \"label\": "
        f"\"Customer name\", \"example\": \"Priya\"}}, ...], \"rationale\": <1-sentence>}}.\n"
        f"Only include variables actually used in the body."
    )
    llm = LlmChat(api_key=EMERGENT_LLM_KEY,
                   session_id=f"tmpl-{body.channel}-{int(time.time())}",
                   system_message=SYSTEM_PROMPT).with_model("openai", "gpt-5.2")
    reply = (await llm.send_message(UserMessage(text=prompt))).strip()
    if reply.startswith("```"):
        reply = reply.strip("`")
        if reply.lower().startswith("json"):
            reply = reply[4:].strip()
    try:
        parsed = json.loads(reply)
    except Exception:
        parsed = {"body": reply, "variables": [], "rationale": ""}
    # Normalize single-braced {name} to mustache {{name}} (LLM sometimes drops one)
    if parsed.get("body"):
        parsed["body"] = re.sub(r"(?<!\{)\{([\w_]+)\}(?!\})", r"{{\1}}", parsed["body"])
    return parsed


class AIImproveIn(BaseModel):
    channel: str
    current_body: str
    intent: Optional[str] = "make crisper, more conversion-focused"


@router.post("/templates/ai-improve")
async def ai_improve(body: AIImproveIn, user: dict = Depends(get_current_user)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "AI key not configured")
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    import time
    import json

    prompt = (
        f"You are a copywriter for KAZO (premium Indian women's fashion).\n"
        f"Channel: {body.channel.upper()}\n"
        f"Current message:\n{body.current_body}\n\n"
        f"Improve it. Goal: {body.intent}. Preserve mustache variables ({{name}}, {{amount}}, "
        f"{{store_name}}, etc.). No emojis. Output strict JSON: "
        f"{{\"body\": <improved>, \"rationale\": <1-sentence>}}"
    )
    llm = LlmChat(api_key=EMERGENT_LLM_KEY,
                   session_id=f"tmpl-imp-{int(time.time())}",
                   system_message=SYSTEM_PROMPT).with_model("openai", "gpt-5.2")
    reply = (await llm.send_message(UserMessage(text=prompt))).strip()
    if reply.startswith("```"):
        reply = reply.strip("`")
        if reply.lower().startswith("json"):
            reply = reply[4:].strip()
    try:
        parsed = json.loads(reply)
    except Exception:
        parsed = {"body": reply, "rationale": ""}
    if parsed.get("body"):
        parsed["body"] = re.sub(r"(?<!\{)\{([\w_]+)\}(?!\})", r"{{\1}}", parsed["body"])
    return parsed


# ---------------- Send service ----------------
def _render(body: str, params: Dict[str, Any]) -> str:
    """Replace {{key}} mustache variables with values."""
    def sub(m):
        key = m.group(1).strip()
        return str(params.get(key, m.group(0)))
    return re.sub(r"\{\{\s*([\w_]+)\s*\}\}", sub, body or "")


async def _log(channel: str, status: str, mobile: str, payload: Dict[str, Any],
                response: Any, template_id: Optional[str] = None,
                event_trigger: Optional[str] = None,
                context: Optional[Dict[str, Any]] = None):
    ctx = context or {}
    await message_log_col.insert_one({
        "id": uuid.uuid4().hex,
        "channel": channel,
        "status": status,
        "mobile": mobile,
        "template_id": template_id,
        "event_trigger": event_trigger,
        "bill_number": ctx.get("bill_number"),
        "trigger_source": ctx.get("source"),
        "sender_id": (payload or {}).get("send"),
        "dlt_template_id": (payload or {}).get("dlt_template_id"),
        "payload_summary": {k: (v if k not in {"key", "apikey"} else "•••")
                              for k, v in (payload or {}).items()},
        "response": str(response)[:500] if response else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


async def send_sms_karix(mobile: str, text: str, template_id: Optional[str] = None,
                          event_trigger: Optional[str] = None,
                          context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = await _get_config()
    if not cfg.get("sms_api_key") or not cfg.get("sms_endpoint"):
        await _log("sms", "config_missing", mobile, {}, None, template_id, event_trigger, context)
        return {"ok": False, "error": "SMS provider not configured"}
    # Sender ID + DLT Entity ID — read from what the admin configured on the Communication
    # screens (Provider Settings + the per-template fields). Global Provider Settings is
    # authoritative for Sender ID / Entity ID; the per-template values take priority when set.
    # NOTE: the KAZO Karix QueryStringReceiver account uses ONLY dlt_entity_id (no content
    # template id is sent on this endpoint).
    sender = (cfg.get("sms_sender_id") or "").strip()
    dlt_entity = (cfg.get("sms_dlt_entity_id") or "").strip()
    if template_id:
        tpl = await templates_col.find_one(
            {"id": template_id},
            {"_id": 0, "sender_id": 1, "dlt_entity_id": 1})
        if tpl:
            if not sender and tpl.get("sender_id"):
                sender = tpl["sender_id"]
            if not dlt_entity and tpl.get("dlt_entity_id"):
                dlt_entity = str(tpl["dlt_entity_id"]).strip()
    mob = _normalize_mobile(mobile)
    # Karix QueryStringReceiver — EXACT parameter set per the KAZO Karix account spec:
    #   ver, key, encrpt, dest, send, dlt_entity_id, text
    # (dlt_template_id / dlt_tm_id are intentionally NOT sent on this endpoint.)
    params = {
        "ver": "1.0",
        "key": cfg["sms_api_key"],
        "encrpt": "0",
        "dest": mob,
        "send": sender,
        "dlt_entity_id": dlt_entity,
        "text": text,
    }
    # Outbound to Karix can intermittently ConnectTimeout when the deployment egresses via a
    # POOL of IPs and only SOME are whitelisted at Karix — a fresh connection may pick a
    # whitelisted IP. So we RETRY connect-level failures (SAFE: the connection was never
    # established, so Karix never received the request — no duplicate-SMS risk). We do NOT
    # retry read-level timeouts (where the request may already have been delivered).
    last_err = None
    attempts = 4
    for attempt in range(1, attempts + 1):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=8.0)) as c:
                r = await c.get(cfg["sms_endpoint"], params=params)
            ok = r.status_code == 200
            status = "ok" if ok else f"http_{r.status_code}"
            # Always record what Karix returned (some non-200 bodies are empty) so the Message
            # Log shows the real accept/reject + reason.
            resp_text = r.text or f"HTTP {r.status_code} (empty body)"
            if attempt > 1:
                resp_text = f"{resp_text} · delivered on attempt {attempt}/{attempts}"
            await _log("sms", status, mob, params, resp_text, template_id, event_trigger, context)
            return {"ok": ok, "status_code": r.status_code, "response": r.text,
                    "attempts": attempt, "dlt_entity_id": dlt_entity or None}
        except (httpx.ConnectTimeout, httpx.ConnectError) as e:
            last_err = e
            if attempt < attempts:
                await asyncio.sleep(0.6 * attempt)  # brief backoff before re-connecting
            continue
        except Exception as e:
            last_err = e
            break
    # Capture the exception TYPE + endpoint so the Message Log is diagnostic even for
    # timeouts / connection errors whose str(e) is empty (e.g. egress blocked, bad URL).
    err = f"{type(last_err).__name__}: {last_err}".strip().rstrip(":").strip() or type(last_err).__name__
    err = f"{err} — gateway: {cfg.get('sms_endpoint')} (after {attempts} attempts)"
    await _log("sms", "exception", mob, params, err, template_id, event_trigger, context)
    return {"ok": False, "error": err}


async def send_whatsapp_karix(mobile: str, template_id_external: str,
                                parameter_values: Dict[str, str],
                                template_id: Optional[str] = None,
                                event_trigger: Optional[str] = None) -> Dict[str, Any]:
    cfg = await _get_config()
    if not cfg.get("whatsapp_endpoint") or not cfg.get("whatsapp_from_number"):
        await _log("whatsapp", "config_missing", mobile, {}, None, template_id, event_trigger)
        return {"ok": False, "error": "WhatsApp provider not configured"}
    mob = _normalize_mobile(mobile)
    payload = {
        "message": {
            "channel": "WABA",
            "content": {
                "preview_url": False,
                "type": "TEMPLATE",
                "template": {
                    "templateId": template_id_external,
                    "parameterValues": parameter_values or {},
                },
            },
            "recipient": {
                "to": mob,
                "recipient_type": "individual",
                "reference": {"cust_ref": f"kazo-{uuid.uuid4().hex[:8]}"},
            },
            "sender": {"from": cfg["whatsapp_from_number"]},
            "preferences": {"webHookDNId": "1001"},
        },
        "metaData": {"version": cfg.get("whatsapp_version", "v1.0.9")},
    }
    headers = {"Content-Type": "application/json"}
    if cfg.get("whatsapp_api_key"):
        headers["Authentication"] = cfg["whatsapp_api_key"]
    try:
        async with httpx.AsyncClient(timeout=12.0) as c:
            r = await c.post(cfg["whatsapp_endpoint"], json=payload, headers=headers)
        ok = r.status_code in (200, 201, 202)
        await _log("whatsapp", "ok" if ok else f"http_{r.status_code}", mob, payload,
                    r.text, template_id, event_trigger)
        return {"ok": ok, "status_code": r.status_code, "response": r.text}
    except Exception as e:
        await _log("whatsapp", "exception", mob, payload, str(e), template_id, event_trigger)
        return {"ok": False, "error": str(e)}


# ---------------- Public send endpoints ----------------
class TestSendIn(BaseModel):
    mobile: str
    params: Dict[str, Any] = {}


@router.post("/templates/{tid}/test-send")
async def test_send(tid: str, body: TestSendIn, user: dict = Depends(get_current_user)):
    t = await templates_col.find_one({"id": tid}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Template not found")
    if t["channel"] == "sms":
        text = _render(t["body"], body.params)
        return await send_sms_karix(body.mobile, text, template_id=tid,
                                      event_trigger=t.get("event_trigger"))
    if t["channel"] == "whatsapp":
        if not t.get("waba_template_id"):
            raise HTTPException(400, "WhatsApp template requires waba_template_id (the Karix-approved template id)")
        return await send_whatsapp_karix(body.mobile, t["waba_template_id"],
                                          body.params, template_id=tid,
                                          event_trigger=t.get("event_trigger"))
    if t["channel"] == "rcs":
        # RCS uses same Karix endpoint as WABA but rich content; for now we test via WABA-style call
        if not t.get("waba_template_id"):
            raise HTTPException(400, "RCS template requires templateId")
        return await send_whatsapp_karix(body.mobile, t["waba_template_id"],
                                          body.params, template_id=tid,
                                          event_trigger=t.get("event_trigger"))
    raise HTTPException(400, "Unsupported channel")


# ---------------- Provider config ----------------
@router.get("/provider-config")
async def get_provider_config(user: dict = Depends(get_current_user)):
    cfg = await _get_config()
    masked = {**cfg,
               "sms_api_key": _mask_secret(cfg.get("sms_api_key")),
               "whatsapp_api_key": _mask_secret(cfg.get("whatsapp_api_key")),
               "rcs_api_key": _mask_secret(cfg.get("rcs_api_key"))}
    return masked


@router.patch("/provider-config")
async def update_provider_config(body: ProviderConfigIn, user: dict = Depends(get_current_user)):
    if user["role"] not in {"super_admin", "brand_admin"}:
        raise HTTPException(403, "Only brand_admin / super_admin can change provider config")
    cur = await _get_config()
    update = {k: v for k, v in body.model_dump().items() if v is not None and v != ""}
    # Don't overwrite secret with the masked placeholder coming back from UI
    for secret_key in ("sms_api_key", "whatsapp_api_key", "rcs_api_key"):
        if secret_key in update and "•" in update[secret_key]:
            update.pop(secret_key)
    if not update:
        return await get_provider_config(user)
    await provider_config_col.update_one({"_id": "singleton"}, {"$set": update})
    return {**cur, **update,
             "sms_api_key": _mask_secret({**cur, **update}.get("sms_api_key")),
             "whatsapp_api_key": _mask_secret({**cur, **update}.get("whatsapp_api_key")),
             "rcs_api_key": _mask_secret({**cur, **update}.get("rcs_api_key"))}


# ---------------- Message log ----------------
@router.get("/message-log")
async def get_message_log(channel: Optional[str] = None, status: Optional[str] = None,
                          mobile: Optional[str] = None, event_trigger: Optional[str] = None,
                          limit: int = 100, user: dict = Depends(get_current_user)):
    flt: Dict[str, Any] = {}
    if channel:
        flt["channel"] = channel
    if status:
        flt["status"] = status
    if event_trigger:
        flt["event_trigger"] = event_trigger
    if mobile:
        digits = re.sub(r"\D", "", mobile)
        if digits:
            flt["mobile"] = {"$regex": f"{digits}$"}  # match by trailing digits (ignores 91 prefix)
    rows = await message_log_col.find(flt, {"_id": 0}).sort("timestamp", -1).limit(min(limit, 500)).to_list(500)
    total = await message_log_col.count_documents(flt)
    return {"rows": rows, "total": total}


@router.get("/provider-connectivity")
async def provider_connectivity(user: dict = Depends(get_current_user)):
    """Outbound-egress diagnostic — run this ON the deployment to see exactly what it can
    reach. Returns the deployment's egress (public) IP + connectivity to a control host and
    to the configured SMS gateway. Lets us separate a blanket egress block (control also
    fails) from a host-specific block (only the SMS gateway fails)."""
    import time as _time
    cfg = await _get_config()
    endpoint = cfg.get("sms_endpoint") or "https://pod2-japi.instaalerts.zone/httpapi/QueryStringReceiver"
    out: Dict[str, Any] = {"egress_ip": None, "sms_endpoint": endpoint, "checks": []}

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as c:
        try:
            r = await c.get("https://api.ipify.org")
            out["egress_ip"] = r.text.strip()
        except Exception as e:
            out["egress_ip"] = f"ERROR: {type(e).__name__}: {e}"

        targets = [
            ("control_internet", "https://api.ipify.org", None),
            ("control_google", "https://www.google.com", None),
            ("sms_gateway", endpoint, {"ping": "1"}),
        ]
        for label, url, params in targets:
            t0 = _time.time()
            try:
                rr = await c.get(url, params=params)
                out["checks"].append({"target": label, "url": url, "ok": True,
                                       "http_status": rr.status_code,
                                       "ms": int((_time.time() - t0) * 1000)})
            except Exception as e:
                out["checks"].append({"target": label, "url": url, "ok": False,
                                       "error": f"{type(e).__name__}: {e}",
                                       "ms": int((_time.time() - t0) * 1000)})

    control_ok = any(ck["ok"] for ck in out["checks"] if ck["target"].startswith("control"))
    gateway_ok = any(ck["ok"] for ck in out["checks"] if ck["target"] == "sms_gateway")
    if gateway_ok:
        out["verdict"] = "SMS gateway reachable from this deployment."
    elif control_ok:
        out["verdict"] = ("General internet egress works, but the SMS gateway host is NOT "
                          "reachable — host/IP-specific block (Karix IP filter on this pod, or "
                          "a route to this host). Give your production egress IP to Karix, or "
                          "ask Emergent Support to allow this destination host.")
    else:
        out["verdict"] = ("No outbound internet egress at all from this deployment — blanket "
                          "egress block. Contact Emergent Support to enable outbound HTTPS egress.")
    return out



# ---------------- Internal: fire_event hook ----------------
async def fire_event(event_trigger: str, mobile: str, params: Dict[str, Any]):
    """Fire all active templates registered for this event_trigger.

    Best-effort and fully exception-safe: callers may run this as a fire-and-forget
    background task, so it must never raise (a slow/failed provider is logged, not raised).
    """
    if not mobile:
        return
    try:
        rows = await templates_col.find(
            {"event_trigger": event_trigger, "status": "active"}, {"_id": 0}
        ).to_list(50)
    except Exception as e:
        logger.warning(f"fire_event template lookup failed for '{event_trigger}': {e}")
        return
    for t in rows:
        try:
            ctx = {"bill_number": params.get("bill_no") or params.get("bill_number"),
                   "source": f"event:{event_trigger}"}
            if t["channel"] == "sms":
                text = _render(t["body"], params)
                await send_sms_karix(mobile, text, template_id=t["id"],
                                     event_trigger=event_trigger, context=ctx)
            elif t["channel"] in {"whatsapp", "rcs"} and t.get("waba_template_id"):
                # Only fire WABA templates that have been approved
                if t.get("waba_approval_status") != "approved":
                    await _log(t["channel"], "skipped_unapproved", mobile, {}, None,
                                t["id"], event_trigger, ctx)
                    continue
                wa_params = _waba_positional_params(t, params)
                await send_whatsapp_karix(mobile, t["waba_template_id"], wa_params,
                                            template_id=t["id"], event_trigger=event_trigger)
        except Exception as e:
            await _log(t["channel"], "fire_exception", mobile, {}, str(e),
                        t["id"], event_trigger)


# ---------------- WABA approval workflow ----------------
WABA_STATUSES = {"pending", "approved", "rejected"}


class WABAApprovalIn(BaseModel):
    waba_approval_status: str
    waba_template_id: Optional[str] = None
    waba_params_order: Optional[List[str]] = None
    waba_language: Optional[str] = None
    waba_category: Optional[str] = None
    waba_approval_note: Optional[str] = None


@router.patch("/templates/{tid}/waba-approval")
async def set_waba_approval(tid: str, body: WABAApprovalIn,
                              user: dict = Depends(get_current_user)):
    if user["role"] not in {"super_admin", "brand_admin", "marketing_manager"}:
        raise HTTPException(403, "Only marketing_manager / brand_admin / super_admin can set WABA approval")
    t = await templates_col.find_one({"id": tid})
    if not t:
        raise HTTPException(404, "Template not found")
    if t.get("channel") not in {"whatsapp", "rcs"}:
        raise HTTPException(400, "WABA approval only applies to whatsapp / rcs templates")
    if body.waba_approval_status not in WABA_STATUSES:
        raise HTTPException(400, f"Status must be one of {sorted(WABA_STATUSES)}")
    update: Dict[str, Any] = {"waba_approval_status": body.waba_approval_status,
                              "waba_approval_at": datetime.now(timezone.utc).isoformat(),
                              "waba_approval_by": user["email"]}
    for f in ("waba_template_id", "waba_params_order", "waba_language",
              "waba_category", "waba_approval_note"):
        v = getattr(body, f, None)
        if v is not None:
            update[f] = v
    await templates_col.update_one({"id": tid}, {"$set": update})
    return await templates_col.find_one({"id": tid}, {"_id": 0})


# ---------------- Bulk send (FastAPI BackgroundTasks) ----------------
class BulkSendIn(BaseModel):
    template_id: str
    audience: Dict[str, Any] = {}  # MongoDB filter for customers collection
    dry_run: bool = True
    limit: int = 1000


def _params_for_customer(c: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": (c.get("name") or "").split(" ")[0] or "there",
        "tier": c.get("tier", "silver"),
        "points_balance": c.get("points_balance", 0),
        "city": c.get("city", ""),
    }


def _waba_positional_params(template: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, str]:
    """Build positional WABA params {"1": ..., "2": ...} based on waba_params_order."""
    order = template.get("waba_params_order") or []
    if not order:
        # fall back to mapping each declared variable in order
        order = [v.get("key") for v in (template.get("variables") or []) if v.get("key")]
    return {str(i + 1): str(params.get(k, "")) for i, k in enumerate(order)}


async def _run_bulk_send_job(job_id: str, template_id: str, audience_filter: Dict[str, Any],
                                limit: int):
    """Background worker: pulls audience, dispatches messages, updates job state."""
    started = datetime.now(timezone.utc).isoformat()
    await bulk_jobs_col.update_one(
        {"id": job_id},
        {"$set": {"status": "running", "started_at": started}},
    )
    try:
        t = await templates_col.find_one({"id": template_id}, {"_id": 0})
        if not t:
            raise RuntimeError("Template missing")
        cursor = customers_col.find(audience_filter or {},
            {"_id": 0, "id": 1, "name": 1, "mobile": 1, "tier": 1,
              "points_balance": 1, "city": 1}).limit(min(limit, 50000))
        sent, failed, processed = 0, 0, 0
        async for c in cursor:
            processed += 1
            params = _params_for_customer(c)
            try:
                if t["channel"] == "sms":
                    res = await send_sms_karix(c["mobile"], _render(t["body"], params),
                                                 template_id=t["id"], event_trigger="campaign_bulk")
                elif t["channel"] in {"whatsapp", "rcs"} and t.get("waba_template_id"):
                    res = await send_whatsapp_karix(c["mobile"], t["waba_template_id"],
                                                     _waba_positional_params(t, params),
                                                     template_id=t["id"],
                                                     event_trigger="campaign_bulk")
                else:
                    res = {"ok": False, "error": "unsupported"}
                if res.get("ok"):
                    sent += 1
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                await _log(t["channel"], "bulk_exception", c.get("mobile", ""), {},
                            str(e), t["id"], "campaign_bulk")
            # Heartbeat every 25 processed
            if processed % 25 == 0:
                await bulk_jobs_col.update_one({"id": job_id},
                    {"$set": {"processed": processed, "sent": sent, "failed": failed}})
        await bulk_jobs_col.update_one(
            {"id": job_id},
            {"$set": {"status": "completed",
                       "completed_at": datetime.now(timezone.utc).isoformat(),
                       "processed": processed, "sent": sent, "failed": failed}},
        )
    except Exception as e:
        await bulk_jobs_col.update_one(
            {"id": job_id},
            {"$set": {"status": "failed", "error": str(e),
                       "completed_at": datetime.now(timezone.utc).isoformat()}},
        )


@router.post("/communications/bulk-send")
async def bulk_send(body: BulkSendIn, background_tasks: BackgroundTasks,
                     user: dict = Depends(get_current_user)):
    if user["role"] not in {"super_admin", "brand_admin", "marketing_manager"}:
        raise HTTPException(403, "Forbidden")
    t = await templates_col.find_one({"id": body.template_id}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Template not found")
    if t.get("status") != "active":
        raise HTTPException(400, "Template must be active to bulk send")
    if t["channel"] in {"whatsapp", "rcs"}:
        if not t.get("waba_template_id"):
            raise HTTPException(400, "WhatsApp/RCS template requires a Karix-approved waba_template_id")
        if t.get("waba_approval_status") != "approved":
            raise HTTPException(400, "Template WABA approval status must be 'approved' before bulk send")

    # Resolve audience size for preview (cap at min(limit, 5000) for dry-run preview)
    preview_cap = min(body.limit, 5000)
    audience = await customers_col.find(
        body.audience or {},
        {"_id": 0, "id": 1, "name": 1, "mobile": 1, "tier": 1,
         "points_balance": 1, "city": 1}
    ).limit(preview_cap).to_list(preview_cap)
    audience_size = await customers_col.count_documents(body.audience or {})

    if body.dry_run:
        return {"dry_run": True, "audience_size_total": audience_size,
                "audience_size_capped": min(audience_size, body.limit),
                "sample": audience[:3], "would_send_via": t["channel"]}

    # Enqueue background job
    job_id = uuid.uuid4().hex
    job_doc = {
        "id": job_id,
        "template_id": body.template_id,
        "template_name": t.get("name"),
        "channel": t["channel"],
        "audience_filter": body.audience,
        "audience_size_total": audience_size,
        "limit": body.limit,
        "status": "queued",
        "processed": 0, "sent": 0, "failed": 0,
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "queued_by": user["email"],
    }
    await bulk_jobs_col.insert_one(job_doc)
    background_tasks.add_task(_run_bulk_send_job, job_id, body.template_id,
                               body.audience, body.limit)
    job_doc.pop("_id", None)
    return {"dry_run": False, "job_id": job_id, "status": "queued",
             "audience_size_total": audience_size,
             "limit": body.limit, "job": job_doc}


@router.get("/communications/bulk-jobs")
async def list_bulk_jobs(limit: int = 50, user: dict = Depends(get_current_user)):
    rows = await bulk_jobs_col.find({}, {"_id": 0}).sort("queued_at", -1).limit(min(limit, 100)).to_list(100)
    return {"rows": rows, "total": len(rows)}


@router.get("/communications/bulk-jobs/{job_id}")
async def get_bulk_job(job_id: str, user: dict = Depends(get_current_user)):
    j = await bulk_jobs_col.find_one({"id": job_id}, {"_id": 0})
    if not j:
        raise HTTPException(404, "Job not found")
    return j
