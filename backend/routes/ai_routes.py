"""Fundle Brain — AI Chat with true MongoDB function-calling + streaming + CSV upload.

Uses LiteLLM directly through the Emergent integration proxy (same proxy used
internally by `emergentintegrations.LlmChat`) so we get full access to OpenAI-style
tool_calls in the response. Backwards-compatible `/chat` endpoint.
"""
import os
import json
import csv
import io
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, AsyncIterator

import litellm
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from emergentintegrations.llm.utils import get_app_identifier, get_integration_proxy_url

from database import ai_chats_col
from auth import get_current_user, log_audit
from models import AIChatRequest
from routes.ai_tools import TOOL_SCHEMAS, execute_tool

router = APIRouter(prefix="/ai", tags=["ai"])

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
MAX_TOOL_ITERATIONS = 6

SYSTEM_PROMPT = """You are Fundle Brain, the AI analytics assistant AND operations agent for KAZO (premium Indian women's fashion brand) powered by Fundle.

Capabilities:
- You have direct READ access to the live Kazo MongoDB through tools. ALWAYS call the appropriate tool before answering numeric questions.
- You also have WRITE tools for L1 support operations: customer_deactivate, customer_reactivate, unsubscribe_customer, resubscribe_customer, reactivate_coupon_redemption, reactivate_redeem_points. These are role-gated to super_admin/brand_admin/support_agent and every action is audit-logged.

Write-tool protocol — non-negotiable:
1. NEVER call a WRITE tool without the user's explicit intent. If unclear, ASK first ("You want me to deactivate 9876543210, correct?").
2. ALWAYS look up the target first with a READ tool (customer_search, list_redeemed_coupons, list_redeemed_points) to confirm identity and show the user what you're about to act on.
3. Require a REASON string for every write. If the user didn't give one, ask: "What's the reason — I need to log it for audit."
4. After a successful write, confirm in plain English what happened and where the audit entry lives ("Logged to Support Desk Audit Log as `support_desk.customer_deactivate`.").
5. If a write fails with `permission denied`, tell the user their role lacks permission — don't retry.

Data-tool protocol:
- IMPORTANT — When the user asks about "all data", "all-time", "lifetime", "historical", "since launch", "across all years", or doesn't specify a recent window, call tools with `days=0` (the sentinel for "all time" — scans the full 20-year history).
- After receiving tool results, synthesise an executive-friendly answer with ₹ for currency, percent for ratios.
- If the user uploads a CSV, the contents will appear in the user message; reason over those rows directly.
- If a tool with `days=N` returns zero rows, retry once with `days=0` before concluding "data not available".
- NEVER fabricate numbers — if a tool still returns no data after the all-time retry, say "Data not available".
- Be concise, action-oriented, and end with 1–2 recommended actions when appropriate.

Brand voice: Refined, premium fashion editorial. Indian context. No emojis.
"""


# ---------------- LiteLLM through Emergent proxy ----------------
def _build_completion_params(messages: List[Dict[str, Any]], model: str,
                             provider: str, tools: Optional[List[Dict[str, Any]]] = None,
                             stream: bool = False) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "api_key": EMERGENT_LLM_KEY,
    }
    if EMERGENT_LLM_KEY.startswith("sk-emergent-"):
        proxy_url = get_integration_proxy_url()
        params["api_base"] = proxy_url + "/llm"
        params["custom_llm_provider"] = "openai"
        if provider == "gemini":
            params["model"] = f"gemini/{model}"
        else:
            params["model"] = model
        app_id = get_app_identifier()
        if app_id:
            params["extra_headers"] = {"X-App-ID": app_id}
    if tools:
        params["tools"] = tools
        params["tool_choice"] = "auto"
    if stream:
        params["stream"] = True
    return params


def _resolve_model(req_model: Optional[str]) -> tuple[str, str]:
    m = (req_model or "gpt-5.2").lower()
    if "claude" in m:
        return "anthropic", "claude-sonnet-4-5-20250929"
    if "gemini" in m:
        return "gemini", "gemini-2.5-pro"
    return "openai", "gpt-5.2"


async def _run_tool_loop(messages: List[Dict[str, Any]], model: str, provider: str, user: Dict[str, Any] | None = None) -> tuple[str, List[Dict[str, Any]]]:
    """Multi-turn loop: model -> tool_calls -> execute -> append -> repeat until content.

    Returns (final_text, tool_trace). `user` is forwarded to execute_tool for
    role-gated write tools.
    """
    tool_trace: List[Dict[str, Any]] = []
    for _ in range(MAX_TOOL_ITERATIONS):
        params = _build_completion_params(messages, model, provider, tools=TOOL_SCHEMAS)
        resp = litellm.completion(**params)
        choice = resp.choices[0]
        msg = choice.message
        # If model wants to call tools
        tool_calls = getattr(msg, "tool_calls", None) or []
        if tool_calls:
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
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
                result = await execute_tool(name, args, user=user)
                tool_trace.append({"tool": name, "args": args,
                                   "result_preview": str(result)[:500]})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": name,
                    "content": json.dumps(result, default=str)[:18000],
                })
            continue  # let the model see the tool results
        # No tool calls — final answer
        return (msg.content or ""), tool_trace
    # Hit iteration cap
    return ("(Reached tool-call limit. Try rephrasing your question.)", tool_trace)


# ---------------- Session listing ----------------
@router.get("/sessions")
async def list_sessions(user: dict = Depends(get_current_user)):
    rows = await ai_chats_col.find({"user_id": user["id"]}, {"_id": 0, "messages": 0}).sort("updated_at", -1).limit(50).to_list(50)
    return rows


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, user: dict = Depends(get_current_user)):
    s = await ai_chats_col.find_one({"id": session_id, "user_id": user["id"]}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Session not found")
    return s


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user: dict = Depends(get_current_user)):
    await ai_chats_col.delete_one({"id": session_id, "user_id": user["id"]})
    return {"success": True}


# ---------------- Chat (function-calling) ----------------
@router.post("/chat")
async def chat(req: AIChatRequest, user: dict = Depends(get_current_user)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "AI key not configured")

    session_id = req.session_id or uuid.uuid4().hex
    existing = await ai_chats_col.find_one({"id": session_id, "user_id": user["id"]}, {"_id": 0})

    # Build conversation history from stored messages
    history: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if existing:
        for m in (existing.get("messages") or [])[-12:]:
            if m["role"] in {"user", "assistant"} and m.get("content"):
                history.append({"role": m["role"], "content": m["content"]})
    history.append({"role": "user", "content": req.message})

    provider, model = _resolve_model(req.model)
    try:
        reply, trace = await _run_tool_loop(history, model, provider, user=user)
    except Exception as e:
        raise HTTPException(500, f"AI error: {str(e)}")

    now = datetime.now(timezone.utc).isoformat()
    user_msg = {"role": "user", "content": req.message, "timestamp": now}
    bot_msg = {"role": "assistant", "content": reply, "timestamp": now,
                "tool_trace": trace}
    if existing:
        await ai_chats_col.update_one(
            {"id": session_id},
            {"$push": {"messages": {"$each": [user_msg, bot_msg]}}, "$set": {"updated_at": now}}
        )
    else:
        title = req.message[:60]
        await ai_chats_col.insert_one({
            "id": session_id, "user_id": user["id"], "title": title,
            "messages": [user_msg, bot_msg],
            "created_at": now, "updated_at": now,
            "model": f"{provider}/{model}",
        })

    await log_audit(user, "ai_chat", "ai_session", session_id,
                     {"q": req.message[:200], "tools_used": [t["tool"] for t in trace]})
    return {"session_id": session_id, "reply": reply,
            "tools_used": [t["tool"] for t in trace],
            "tool_trace": trace, "data_used": {"tools": trace}}


# ---------------- Streaming chat (SSE) ----------------
@router.post("/chat/stream")
async def chat_stream(req: AIChatRequest, user: dict = Depends(get_current_user)):
    """Server-sent events: tool calls first (as events), then streamed text."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "AI key not configured")
    session_id = req.session_id or uuid.uuid4().hex
    existing = await ai_chats_col.find_one({"id": session_id, "user_id": user["id"]}, {"_id": 0})

    history: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if existing:
        for m in (existing.get("messages") or [])[-12:]:
            if m["role"] in {"user", "assistant"} and m.get("content"):
                history.append({"role": m["role"], "content": m["content"]})
    history.append({"role": "user", "content": req.message})

    provider, model = _resolve_model(req.model)

    async def event_gen() -> AsyncIterator[str]:
        # Phase 1: run tool loop until final text turn
        trace: List[Dict[str, Any]] = []
        try:
            for _ in range(MAX_TOOL_ITERATIONS):
                params = _build_completion_params(history, model, provider, tools=TOOL_SCHEMAS)
                resp = litellm.completion(**params)
                msg = resp.choices[0].message
                tool_calls = getattr(msg, "tool_calls", None) or []
                if not tool_calls:
                    history.append({"role": "assistant", "content": msg.content or ""})
                    break
                history.append({
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
                    yield f"event: tool\ndata: {json.dumps({'tool': name, 'args': args})}\n\n"
                    result = await execute_tool(name, args, user=user)
                    trace.append({"tool": name, "args": args,
                                  "result_preview": str(result)[:300]})
                    history.append({"role": "tool", "tool_call_id": tc.id,
                                    "name": name, "content": json.dumps(result, default=str)[:18000]})
            # Phase 2: stream the final assistant message
            params = _build_completion_params(history, model, provider, stream=True)
            full_text = ""
            stream = litellm.completion(**params)
            for chunk in stream:
                try:
                    delta = chunk.choices[0].delta.content or ""
                except Exception:
                    delta = ""
                if delta:
                    full_text += delta
                    yield f"event: token\ndata: {json.dumps({'t': delta})}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
            return
        # Phase 3: persist
        now = datetime.now(timezone.utc).isoformat()
        user_msg = {"role": "user", "content": req.message, "timestamp": now}
        bot_msg = {"role": "assistant", "content": full_text, "timestamp": now, "tool_trace": trace}
        if existing:
            await ai_chats_col.update_one({"id": session_id},
                {"$push": {"messages": {"$each": [user_msg, bot_msg]}}, "$set": {"updated_at": now}})
        else:
            await ai_chats_col.insert_one({"id": session_id, "user_id": user["id"],
                "title": req.message[:60], "messages": [user_msg, bot_msg],
                "created_at": now, "updated_at": now, "model": f"{provider}/{model}"})
        yield f"event: done\ndata: {json.dumps({'session_id': session_id, 'tools_used': [t['tool'] for t in trace]})}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


# ---------------- CSV narration upload ----------------
@router.post("/chat/upload-csv")
async def chat_upload_csv(
    file: UploadFile = File(...),
    question: str = Form(...),
    session_id: Optional[str] = Form(None),
    model: Optional[str] = Form("gpt-5.2"),
    user: dict = Depends(get_current_user),
):
    """Upload a CSV and ask Fundle Brain to narrate / analyse it."""
    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "AI key not configured")
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Only .csv files supported")
    raw = await file.read()
    if len(raw) > 2_000_000:
        raise HTTPException(413, "CSV too large (max 2 MB)")
    try:
        text = raw.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
    except Exception as e:
        raise HTTPException(400, f"Could not parse CSV: {e}")
    if not rows:
        raise HTTPException(400, "CSV is empty")

    headers = rows[0]
    body_rows = rows[1: 201]  # cap at 200 data rows
    csv_summary = {
        "filename": file.filename,
        "columns": headers,
        "row_count_total": len(rows) - 1,
        "row_count_sampled": len(body_rows),
        "sample": [dict(zip(headers, r)) for r in body_rows[:50]],
    }

    sid = session_id or uuid.uuid4().hex
    existing = await ai_chats_col.find_one({"id": sid, "user_id": user["id"]}, {"_id": 0})
    history: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if existing:
        for m in (existing.get("messages") or [])[-6:]:
            if m["role"] in {"user", "assistant"} and m.get("content"):
                history.append({"role": m["role"], "content": m["content"]})
    history.append({
        "role": "user",
        "content": (
            f"I uploaded a CSV called '{file.filename}'. Question: {question}\n\n"
            f"CSV metadata (showing first {min(50, len(body_rows))} rows):\n"
            f"{json.dumps(csv_summary, default=str)[:14000]}\n\n"
            "Analyse the table and answer. You may also call tools if useful."
        ),
    })
    provider, mdl = _resolve_model(model)
    try:
        reply, trace = await _run_tool_loop(history, mdl, provider, user=user)
    except Exception as e:
        raise HTTPException(500, f"AI error: {str(e)}")

    now = datetime.now(timezone.utc).isoformat()
    user_msg = {"role": "user",
                 "content": f"[CSV: {file.filename} — {len(rows) - 1} rows] {question}",
                 "timestamp": now}
    bot_msg = {"role": "assistant", "content": reply, "timestamp": now, "tool_trace": trace}
    if existing:
        await ai_chats_col.update_one({"id": sid},
            {"$push": {"messages": {"$each": [user_msg, bot_msg]}}, "$set": {"updated_at": now}})
    else:
        await ai_chats_col.insert_one({"id": sid, "user_id": user["id"],
            "title": f"CSV: {file.filename[:40]}", "messages": [user_msg, bot_msg],
            "created_at": now, "updated_at": now, "model": f"{provider}/{mdl}"})
    await log_audit(user, "ai_csv_upload", "ai_session", sid,
                     {"filename": file.filename, "rows": len(rows) - 1})
    return {"session_id": sid, "reply": reply,
            "tools_used": [t["tool"] for t in trace],
            "csv_meta": {"filename": file.filename, "rows": len(rows) - 1, "columns": headers}}


# ---------------- Suggested prompts ----------------
@router.get("/suggested-prompts")
async def suggested_prompts(user: dict = Depends(get_current_user)):
    return [
        "Show me top churning customers this month",
        "Which stores are underperforming in last 30 days?",
        "Which campaign gave the best ROI?",
        "Which customers should get win-back coupons?",
        "Which SKUs drive the most repeat purchases?",
        "Which cities have the strongest loyalty penetration?",
        "What is the breakdown of customers by tier?",
        "How is the NPS trending and what should we do?",
        "Look up customer 9876543210",
        "Summarise SMS dispatch success rate over the last week",
    ]


# Backwards-compat: expose SYSTEM_PROMPT for communications_routes import
__all__ = ["router", "EMERGENT_LLM_KEY", "SYSTEM_PROMPT"]
