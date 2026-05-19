"""Communications: SMS/WhatsApp/RCS templates + Karix provider integration.

- CRUD templates with channel/event_trigger/variables
- AI template generator (Emergent LLM)
- Real send via Karix Transactional SMS API + Karix WABA + RCS endpoints
- Provider config stored in MongoDB, editable from UI
- Auto-fired on POS transactions + coupon issuance via fire_event()
"""
import uuid
import re
from datetime import datetime, timezone
from typing import Optional, Any, Dict, List
import httpx
from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel

from database import (
    templates_col, provider_config_col, message_log_col, customers_col, stores_col,
)
from auth import get_current_user
from routes.ai_routes import EMERGENT_LLM_KEY, SYSTEM_PROMPT

router = APIRouter(tags=["communications"])

CHANNELS = {"sms", "whatsapp", "rcs"}
EVENTS = {"none", "purchase", "coupon_issued", "points_earned", "tier_upgrade", "birthday",
          "win_back", "abandoned_visit", "campaign_bulk"}


# ---------------- Pydantic models ----------------
class TemplateIn(BaseModel):
    name: str
    channel: str
    event_trigger: str = "none"
    body: str
    variables: List[Dict[str, str]] = []  # [{key, label, example}]
    sender_id: Optional[str] = None        # for SMS (DLT)
    dlt_entity_id: Optional[str] = None
    waba_template_id: Optional[str] = None  # for WhatsApp
    preview_url: bool = False
    status: str = "draft"
    note: Optional[str] = None


class ProviderConfigIn(BaseModel):
    sms_api_key: Optional[str] = None
    sms_endpoint: Optional[str] = None
    sms_sender_id: Optional[str] = None
    sms_dlt_entity_id: Optional[str] = None
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
                event_trigger: Optional[str] = None):
    await message_log_col.insert_one({
        "id": uuid.uuid4().hex,
        "channel": channel,
        "status": status,
        "mobile": mobile,
        "template_id": template_id,
        "event_trigger": event_trigger,
        "payload_summary": {k: (v if k not in {"key", "apikey"} else "•••")
                              for k, v in (payload or {}).items()},
        "response": str(response)[:500] if response else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


async def send_sms_karix(mobile: str, text: str, template_id: Optional[str] = None,
                          event_trigger: Optional[str] = None) -> Dict[str, Any]:
    cfg = await _get_config()
    if not cfg.get("sms_api_key") or not cfg.get("sms_endpoint"):
        await _log("sms", "config_missing", mobile, {}, None, template_id, event_trigger)
        return {"ok": False, "error": "SMS provider not configured"}
    mob = _normalize_mobile(mobile)
    params = {
        "ver": "1.0",
        "key": cfg["sms_api_key"],
        "encrpt": "0",
        "dest": mob,
        "send": cfg.get("sms_sender_id", ""),
        "dlt_entity_id": cfg.get("sms_dlt_entity_id", ""),
        "text": text,
    }
    try:
        async with httpx.AsyncClient(timeout=12.0) as c:
            r = await c.get(cfg["sms_endpoint"], params=params)
        ok = r.status_code == 200
        await _log("sms", "ok" if ok else f"http_{r.status_code}", mob, params,
                    r.text, template_id, event_trigger)
        return {"ok": ok, "status_code": r.status_code, "response": r.text}
    except Exception as e:
        await _log("sms", "exception", mob, params, str(e), template_id, event_trigger)
        return {"ok": False, "error": str(e)}


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
async def get_message_log(channel: Optional[str] = None, limit: int = 100,
                          user: dict = Depends(get_current_user)):
    flt: Dict[str, Any] = {}
    if channel:
        flt["channel"] = channel
    rows = await message_log_col.find(flt, {"_id": 0}).sort("timestamp", -1).limit(min(limit, 500)).to_list(500)
    total = await message_log_col.count_documents(flt)
    return {"rows": rows, "total": total}


# ---------------- Internal: fire_event hook ----------------
async def fire_event(event_trigger: str, mobile: str, params: Dict[str, Any]):
    """Fire all active templates registered for this event_trigger."""
    if not mobile:
        return
    rows = await templates_col.find(
        {"event_trigger": event_trigger, "status": "active"}, {"_id": 0}
    ).to_list(50)
    for t in rows:
        try:
            if t["channel"] == "sms":
                text = _render(t["body"], params)
                await send_sms_karix(mobile, text, template_id=t["id"], event_trigger=event_trigger)
            elif t["channel"] in {"whatsapp", "rcs"} and t.get("waba_template_id"):
                # Convert dict params to ordered list for WABA
                await send_whatsapp_karix(mobile, t["waba_template_id"], params,
                                            template_id=t["id"], event_trigger=event_trigger)
        except Exception as e:
            await _log(t["channel"], "fire_exception", mobile, {}, str(e),
                        t["id"], event_trigger)


# ---------------- Bulk send (for campaigns) ----------------
class BulkSendIn(BaseModel):
    template_id: str
    audience: Dict[str, Any] = {}  # MongoDB filter for customers collection
    dry_run: bool = True
    limit: int = 1000


@router.post("/communications/bulk-send")
async def bulk_send(body: BulkSendIn, user: dict = Depends(get_current_user)):
    if user["role"] not in {"super_admin", "brand_admin", "marketing_manager"}:
        raise HTTPException(403, "Forbidden")
    t = await templates_col.find_one({"id": body.template_id}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Template not found")
    if t.get("status") != "active":
        raise HTTPException(400, "Template must be active to bulk send")

    # Resolve audience (always cap at limit; brand admin must opt-in for live send)
    audience = await customers_col.find(body.audience or {},
                                          {"_id": 0, "id": 1, "name": 1, "mobile": 1, "tier": 1,
                                           "points_balance": 1, "city": 1}
                                          ).limit(min(body.limit, 5000)).to_list(5000)
    if body.dry_run:
        return {"dry_run": True, "audience_size": len(audience),
                 "sample": audience[:3], "would_send_via": t["channel"]}

    sent, failed = 0, 0
    for c in audience:
        params = {
            "name": (c.get("name") or "").split(" ")[0] or "there",
            "tier": c.get("tier", "silver"),
            "points_balance": c.get("points_balance", 0),
            "city": c.get("city", ""),
        }
        if t["channel"] == "sms":
            res = await send_sms_karix(c["mobile"], _render(t["body"], params),
                                         template_id=t["id"], event_trigger="campaign_bulk")
        elif t["channel"] in {"whatsapp", "rcs"} and t.get("waba_template_id"):
            res = await send_whatsapp_karix(c["mobile"], t["waba_template_id"], params,
                                              template_id=t["id"], event_trigger="campaign_bulk")
        else:
            res = {"ok": False, "error": "unsupported"}
        if res.get("ok"):
            sent += 1
        else:
            failed += 1
    return {"dry_run": False, "audience_size": len(audience), "sent": sent, "failed": failed}
