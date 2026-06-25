"""Master Brain — privileged chat that can ACT on the database.

Reuses Fundle Brain's LiteLLM engine (same Emergent proxy + read tools) and
layers the Master Brain ACTION tools on top. Gated to users with
`is_master_admin == True`. Sessions are stored alongside Fundle Brain chats with
`surface="master"` so they stay separate. Every action is audit-logged via the
tools themselves and is visible through the action-log endpoint.
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

import litellm
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form

from database import ai_chats_col, audit_logs_col
from auth import get_current_user, log_audit
from models import AIChatRequest
from routes.ai_routes import _build_completion_params, _resolve_model, EMERGENT_LLM_KEY
from routes.ai_tools import TOOL_SCHEMAS, execute_tool
from routes.master_brain_tools import MASTER_TOOL_SCHEMAS, MASTER_TOOL_HANDLERS
from routes import mb_attachments as MBA

router = APIRouter(prefix="/master-brain", tags=["master-brain"])

MAX_TOOL_ITERATIONS = 12
ALL_TOOL_SCHEMAS = TOOL_SCHEMAS + MASTER_TOOL_SCHEMAS

MASTER_SYSTEM_PROMPT = """You are MASTER BRAIN — the privileged operations agent for KAZO (premium Indian women's fashion brand) powered by Fundle. You are used ONLY by a Master Admin.

You have EVERYTHING Fundle Brain can do (full live MongoDB READ access + raw-data analytics), PLUS an ACTION layer that can WRITE back to the database:
- grant_bonus_points — award points to a customer
- adjust_points — add or deduct points for a customer
- fix_negative_balances — reset negative balances to 0 (single or ALL)
- retier_customers — re-map customers onto the configured slabs (no bonus points), single or bulk
- master_action_log — read the audit trail of actions taken
- apply_to_uploaded_report — take a bulk action (grant/adjust points, fix negatives, re-tier) on every customer listed in an UPLOADED report
(plus the L1 support write tools: deactivate / reactivate / unsubscribe / resubscribe / reverse a coupon or points redemption).

ATTACHMENTS: The user can attach SCREENSHOTS/IMAGES (you can SEE them — read the numbers/text in them) and REPORTS (CSV/Excel/PDF). When a report is attached, its parsed content + an attachment_id appear in a context block; to act on the customers it lists, call apply_to_uploaded_report with that attachment_id (preview first, then confirm + reason). For a screenshot, read it; if the user wants you to act on customers shown in it, extract their mobiles and use the per-customer tools (each still previews + needs a reason).

ACTION PROTOCOL — non-negotiable, this is what makes you safe:
1. NEVER mutate on the first turn. For ANY action, FIRST call the tool with confirm=false to PREVIEW. The preview returns exactly what will change and how many customers are affected.
2. Present the preview clearly (a Markdown table + the affected count) and then ASK the user: "Shall I go ahead and apply this?" Do NOT proceed on your own.
3. A REASON is MANDATORY. If the user approves but gave no reason, ask: "Please give me a reason — I must log it for audit." Never invent a reason.
4. Only after the user (a) explicitly approves AND (b) provides a reason, call the tool again with confirm=true and reason="<their reason>".
5. After applying, REPORT BACK in plain English: what changed, the count, and that it was logged to the Master Brain action log (with their name + reason + timestamp).
6. If a tool returns an error (permission, too large, no reason), relay it plainly and stop — do not retry blindly.

Read/analytics behaviour: identical to Fundle Brain — call the right READ tool before answering numbers; use run_aggregation for arbitrary slices; days=0 means all-time; treat the data-warehouse snapshot (next system message) as ground truth.

Formatting: clean GitHub-flavoured Markdown. Tables for any tabular/comparative data. Bold key figures. Currency in ₹ with Indian digit grouping. Dates in IST. No emojis. Be decisive on reads; be careful and explicit on writes.
"""


async def _seeded_history(user: Dict[str, Any]) -> List[Dict[str, Any]]:
    msgs: List[Dict[str, Any]] = [{"role": "system", "content": MASTER_SYSTEM_PROMPT}]
    try:
        from routes.ai_data_expert import build_data_context
        ctx = await build_data_context()
        if ctx:
            msgs.append({"role": "system", "content": ctx})
    except Exception:
        pass
    return msgs


async def _master_execute_tool(name: str, args: Dict[str, Any], user: Dict[str, Any]) -> Dict[str, Any]:
    handler = MASTER_TOOL_HANDLERS.get(name)
    if handler:
        try:
            return await handler(**(args or {}), user=user)
        except TypeError as e:
            return {"error": f"Bad arguments for {name}: {e}"}
        except Exception as e:  # noqa: BLE001
            return {"error": f"Tool {name} failed: {e}"}
    # Fall back to the shared Fundle Brain tool registry (reads + L1 writes).
    return await execute_tool(name, args, user=user)


async def _run_tool_loop(messages: List[Dict[str, Any]], model: str, provider: str,
                         user: Dict[str, Any]) -> tuple[str, List[Dict[str, Any]]]:
    trace: List[Dict[str, Any]] = []
    for _ in range(MAX_TOOL_ITERATIONS):
        params = _build_completion_params(messages, model, provider, tools=ALL_TOOL_SCHEMAS)
        resp = litellm.completion(**params)
        msg = resp.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None) or []
        if tool_calls:
            messages.append({
                "role": "assistant", "content": msg.content or "",
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in tool_calls
                ],
            })
            for tc in tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    args = {}
                result = await _master_execute_tool(name, args, user=user)
                trace.append({"tool": name, "args": args, "result_preview": str(result)[:500]})
                messages.append({"role": "tool", "tool_call_id": tc.id, "name": name,
                                 "content": json.dumps(result, default=str)[:18000]})
            continue
        return (msg.content or ""), trace
    messages.append({"role": "system", "content": (
        "Tool budget exhausted. Give the best FINAL answer NOW from the results above. Do NOT call more tools.")})
    params = _build_completion_params(messages, model, provider)
    resp = litellm.completion(**params)
    return (resp.choices[0].message.content or ""), trace


async def require_master_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("is_demo"):
        raise HTTPException(403, "Read-only demo accounts cannot use Master Brain.")
    if not user.get("is_master_admin"):
        raise HTTPException(403, "Master Admin access required.")
    return user


@router.get("/sessions")
async def list_sessions(user: dict = Depends(require_master_admin)):
    return await ai_chats_col.find(
        {"user_id": user["id"], "surface": "master"}, {"_id": 0, "messages": 0}
    ).sort("updated_at", -1).limit(50).to_list(50)


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, user: dict = Depends(require_master_admin)):
    s = await ai_chats_col.find_one({"id": session_id, "user_id": user["id"], "surface": "master"}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Session not found")
    return s


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user: dict = Depends(require_master_admin)):
    await ai_chats_col.delete_one({"id": session_id, "user_id": user["id"], "surface": "master"})
    return {"success": True}


@router.get("/action-log")
async def action_log(days: int = 30, limit: int = 100, user: dict = Depends(require_master_admin)):
    fil: Dict[str, Any] = {"source": "master_brain"}
    if days and days > 0:
        from datetime import timedelta
        fil["timestamp"] = {"$gte": (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()}
    rows = await audit_logs_col.find(fil, {"_id": 0}).sort("timestamp", -1).limit(min(limit, 300)).to_list(300)
    return {"count": len(rows), "actions": rows}


@router.get("/suggested-prompts")
async def suggested_prompts(user: dict = Depends(require_master_admin)):
    return [
        "How many customers are still on legacy Silver/Gold tiers? Re-tier them onto the configured slabs (no bonus points).",
        "How many customers have a negative points balance? Fix them to zero.",
        "Grant 500 bonus points to 9876543210 as a service-recovery gesture.",
        "Show me the Master Brain action log for the last 7 days.",
        "Deduct 200 points from 9876543210 (wrong award) and log the reason.",
        "What is the current slab-wise customer count?",
    ]


@router.post("/upload")
async def upload_attachment(
    file: UploadFile = File(...),
    session_id: str = Form(None),
    user: dict = Depends(require_master_admin),
):
    """Upload a screenshot (png/jpg/webp) or report (csv/xlsx/pdf) to attach to a chat turn."""
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty file")
    try:
        summary = await MBA.ingest(raw, file.filename or "upload", user, session_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Could not process file: {e}")
    return summary


@router.post("/chat")
async def chat(req: AIChatRequest, user: dict = Depends(require_master_admin)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "AI key not configured")
    session_id = req.session_id or uuid.uuid4().hex
    existing = await ai_chats_col.find_one(
        {"id": session_id, "user_id": user["id"], "surface": "master"}, {"_id": 0})

    history: List[Dict[str, Any]] = await _seeded_history(user)
    if existing:
        for m in (existing.get("messages") or [])[-12:]:
            if m["role"] in {"user", "assistant"} and m.get("content"):
                history.append({"role": m["role"], "content": m["content"]})

    # ----- attachments (images -> vision, reports -> context) -----
    await MBA.bind_session(req.attachment_ids or [], user, session_id)
    attachments = await MBA.load_for_chat(req.attachment_ids or [], user)
    text = req.message
    image_parts = []
    att_chips = []
    for att in attachments:
        att_chips.append({"id": att["id"], "kind": att.get("kind"), "filename": att.get("filename")})
        if att.get("kind") == "image":
            image_parts.append({"type": "image_url",
                                "image_url": {"url": f"data:{att.get('mime')};base64,{att.get('image_base64')}"}})
        else:
            block = MBA.build_context_block(att)
            if block:
                text += "\n\n" + block

    # Keep the most recent report referenceable across turns (preview -> confirm)
    latest = await MBA.latest_session_report(session_id, user)
    if latest and latest["id"] not in (req.attachment_ids or []):
        text += "\n\n" + MBA.light_report_context(latest)

    if image_parts:
        user_content: Any = [{"type": "text", "text": text}] + image_parts
    else:
        user_content = text
    history.append({"role": "user", "content": user_content})

    # expose the session to action tools (server-side fallback for uploaded reports)
    user["_mb_session"] = session_id

    provider, model = _resolve_model(req.model)
    try:
        reply, trace = await _run_tool_loop(history, model, provider, user=user)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"AI error: {str(e)}")

    now = datetime.now(timezone.utc).isoformat()
    stored_text = req.message + (f"  ·  📎 {', '.join(a['filename'] for a in att_chips)}" if att_chips else "")
    user_msg = {"role": "user", "content": stored_text, "timestamp": now, "attachments": att_chips}
    bot_msg = {"role": "assistant", "content": reply, "timestamp": now, "tool_trace": trace}
    if existing:
        await ai_chats_col.update_one({"id": session_id},
            {"$push": {"messages": {"$each": [user_msg, bot_msg]}}, "$set": {"updated_at": now}})
    else:
        await ai_chats_col.insert_one({
            "id": session_id, "user_id": user["id"], "surface": "master",
            "title": (req.message or att_chips[0]["filename"] if att_chips else req.message)[:60],
            "messages": [user_msg, bot_msg],
            "created_at": now, "updated_at": now, "model": f"{provider}/{model}"})

    await log_audit(user, "master_brain_chat", "master_brain_session", session_id,
                    {"q": req.message[:200], "tools_used": [t["tool"] for t in trace],
                     "attachments": [a["filename"] for a in att_chips]})
    return {"session_id": session_id, "reply": reply,
            "tools_used": [t["tool"] for t in trace], "tool_trace": trace}
