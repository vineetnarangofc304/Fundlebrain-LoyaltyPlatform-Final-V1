"""Master Brain — privileged chat that can ACT on the database.

Reuses Fundle Brain's LiteLLM engine (same Emergent proxy + read tools) and
layers the Master Brain ACTION tools on top. Gated to users with
`is_master_admin == True`. Sessions are stored alongside Fundle Brain chats with
`surface="master"` so they stay separate. Every action is audit-logged via the
tools themselves and is visible through the action-log endpoint.
"""
import json
import uuid
import asyncio
import time
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

import litellm
import pymongo
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from database import (
    ai_chats_col, audit_logs_col, mb_action_snapshots_col, master_campaigns_col,
    mb_attachments_col, mb_query_log_col,
)
from auth import get_current_user, log_audit
from models import AIChatRequest
from routes.ai_routes import _build_completion_params, _resolve_model, EMERGENT_LLM_KEY, SYSTEM_PROMPT
from routes.ai_tools import TOOL_SCHEMAS, execute_tool, clear_stats_cache
from routes.master_brain_tools import (
    MASTER_TOOL_SCHEMAS, MASTER_TOOL_HANDLERS, MASTER_READ_TOOL_SCHEMAS,
    _tool_undo_action, _tool_cancel_campaign,
)
from routes import mb_attachments as MBA

router = APIRouter(prefix="/master-brain", tags=["master-brain"])

import logging
logger = logging.getLogger("kazo-fundle.master-brain")

MAX_TOOL_ITERATIONS = 12
# Hard wall-clock cap for the tool-gathering loop. The K8s ingress returns a 502 at ~60s, so
# we MUST finish the loop AND the final synthesis well under that. Loop ≤ this + one ~15s
# synthesis call stays comfortably under 60s. The loop runs on FAST Sonnet so it rarely
# approaches this; it's a safety net, not the common case.
MB_DEADLINE_SECONDS = 26
# Per-tool DB deadline. Master Brain tools run heavy full-collection aggregations; without this
# they inherit the aggressive production Atlas client `timeoutMS` (~10s) and fail with a read
# timeout (users saw "Data Unavailable — System Timeout"). A scoped pymongo.timeout per tool
# call OVERRIDES that so each aggregation can complete, while the outer 26s/46s caps still bound
# the whole run. (Same pattern used by the dashboards' db_deadline and the recon engine.)
MB_TOOL_DB_DEADLINE = 25
# Analysis/read questions get the Fundle read tools PLUS the read-only Master audits (e.g.
# the fast duplicate-redemption audit). The full action set is added only on write intent.
READ_TOOL_SCHEMAS = TOOL_SCHEMAS + MASTER_READ_TOOL_SCHEMAS
ALL_TOOL_SCHEMAS = TOOL_SCHEMAS + MASTER_READ_TOOL_SCHEMAS + MASTER_TOOL_SCHEMAS

# Master Brain = ALL of Fundle Brain (reads/analytics/CSV/agentic behaviour) + an action layer.
# We literally reuse Fundle Brain's full system prompt and append the action protocol so Master
# Brain answers EVERY analytics question exactly like Fundle Brain, then can also execute.
MASTER_ADDENDUM = """

=====================================================================
MASTER BRAIN — ACTION LAYER  (you are *Master Brain*, used ONLY by a Master Admin)
=====================================================================
EVERYTHING ABOVE STILL APPLIES. You are Fundle Brain with extra powers. You MUST answer ANY analytics / data / "where do I see…" / list / export question exactly like Fundle Brain — same READ tools (customer_search, run_aggregation, export_csv, get_data_dictionary, …), same decisiveness, same formatting. NEVER refuse or downgrade a read/analytics request, and never say "I can only do actions". You give REAL, COMPLETE answers with actual numbers — never "timed out", never "I couldn't", never a vague placeholder. If one query is heavy, use a tighter/indexed query (a `$match` + `$count`, a filtered `count_documents`, or a `$limit`ed sample) and still deliver the number.

CRITICAL — READ vs WRITE separation (this is what keeps you fast and reliable):
- When the user is ASKING A QUESTION / requesting analysis, a count, a list, a report, or "where do I see X" (e.g. "how many customers have a negative balance and why?"), answer it using ONLY the READ tools (run_aggregation, customer_search, get_data_dictionary, export_csv, …). Do NOT call ANY action/repair tool (fix_negative_balances, fix_double_redemptions, retier_customers, grant/adjust, send_campaign, …) — not even in "preview" — merely to answer a question. Using a repair tool to "check" data is WRONG and slow.
- BUT when the user EXPLICITLY asks you to DO an action (e.g. "fix the double redemptions for 60000…", "re-tier the zero-spend customers", "grant 100 points to …", "send an SMS to Gold"), you MUST immediately CALL the matching action tool with confirm=false to PREVIEW it. The action tool gathers its OWN data — do NOT say "I don't have the scan result" or ask the user to generate data first; just call the tool. After it returns, show the preview table + count and ask for confirmation + a reason.
- For analysis answers, recommend follow-up actions in PROSE plus the suggested-actions block (the user clicks Execute to run them under the preview→confirm→reason flow).

ON TOP of reads, you have an ACTION layer that WRITES to the live database:
- grant_bonus_points / adjust_points — award or add/deduct points for one customer
- fix_negative_balances — reset negative balances to 0 (single or ALL)
- retier_customers — re-map customers onto the CONFIGURED slabs by spend (no bonus points)
- set_customer_tier — set a SPECIFIC tier/slab value (even a legacy/custom one like "kazo insider") on ONE customer OR a FILTERED set (e.g. all customers with lifetime_spend = 0). USE THIS whenever the user names a target slab to set rather than a spend-based re-map.
- apply_to_uploaded_report — bulk action on every customer in an uploaded CSV/Excel/PDF
- undo_action — REVERSE a prior action by its audit_id (from master_action_log)
- fix_double_redemptions — REPAIR customers double-charged by the old redemption bug: credits back the duplicate point deduction (where the bill deducted points a 2nd time after the OTP redemption), corrects lifetime_points_redeemed, and voids the duplicate ledger rows. Pass a single `mobile` to fix/test one, or omit it to fix everyone affected.
- send_campaign / list_campaigns / cancel_campaign — Karix BULK SMS campaigns
- master_action_log — read the audit trail
- (plus the L1 support write tools: deactivate / reactivate / unsubscribe / resubscribe / reverse a coupon or points redemption)

ATTACHMENTS: users can attach SCREENSHOTS/IMAGES (you can SEE them) and REPORTS (CSV/Excel/PDF). A report's parsed content + an attachment_id arrive in a context block; act on its customers via apply_to_uploaded_report. For a screenshot, read it and use per-customer tools.

WRITE/ACTION protocol — non-negotiable (this is what makes you safe):
1. NEVER mutate on the first turn — call the action tool with confirm=false to PREVIEW (returns exactly what changes + the affected count + a sample).
2. Present the preview as a Markdown table + the count, then ASK "Shall I go ahead and apply this?". Do not proceed on your own.
3. A REASON is MANDATORY. If approved but no reason was given, ask for one. Never invent it.
4. Only after explicit approval AND a reason, call again with confirm=true + reason.
5. After applying, report what changed, the count, and that it was logged to the Master Brain action log (name + reason + timestamp).
6. If the request is AMBIGUOUS for a WRITE (which customers? which slab? how many points?), ASK a short clarifying question and CONFIRM your understanding BEFORE previewing — never guess on a write.
7. If a tool errors (permission / too large / no reason), relay it plainly. If NO existing tool fits, state what IS possible and offer the closest path (e.g. "I can set tier='kazo insider' on every customer with lifetime_spend = 0 via set_customer_tier — shall I preview that?") — do NOT just say "I can't".

REPORT & DASHBOARD NAVIGATION — when the user asks "where can I see X" or the data already lives on a page, ANSWER the number from live tools AND point them to the exact page:
- Live bills: /admin (Live Bill Monitor) · Command Center: /admin/dashboards/command-center
- Dashboards: Sales /admin/dashboards/sales · Customer Analytics /admin/dashboards/customers · Loyalty /admin/dashboards/loyalty · Campaign Performance /admin/dashboards/campaigns · Store Performance /admin/dashboards/stores · RFM & Churn /admin/dashboards/rfm · Cohorts & Segments /admin/dashboards/cohorts · Points Economics /admin/dashboards/points · Campaign ROI /admin/dashboards/campaign-roi · Executive Summary /admin/dashboards/executive-summary · NPS & Feedback /admin/dashboards/nps
- Customer 360: /admin/customers · Segment Builder: /admin/segments · Campaigns: /admin/campaigns · Auto Campaigns: /admin/auto-campaigns · Coupons: /admin/coupons
- Communications: Templates /admin/communications/templates · SMS/Message Log /admin/communications/message-log · Bulk Send Jobs /admin/communications/bulk-jobs · Provider Settings /admin/communications/settings
- Data: Raw Data Reports /admin/raw-reports · Historical Upload /admin/historic-data · Verify Load /admin/verify-load · Data Reconciliation /admin/reconciliation
- Operations: Stores /admin/stores · Item Master /admin/items · API Monitor /admin/api-monitor · POS Credentials /admin/pos-credentials
- Reports: Legacy Reports /admin/legacy-reports · Shopper Bill /admin/reports/shopper-bills · Store KPI /admin/reports/store-kpi · CRM Customer /admin/reports/crm-customers · KPI Trends /admin/reports/kpi-trends · Reports & Exports /admin/reports · Exec Digests /admin/reports/digests · Formula Catalog /admin/formula-catalog · Downloads /admin/downloads
- Config: Loyalty Rules /admin/loyalty · Public Site CMS /admin/cms · User Management /admin/users
- Support: Tickets /admin/tickets · NPS Inbox /admin/nps · Support Desk /admin/support-desk/*

You are Master Brain: as smart as Fundle Brain on reads, plus the authority to execute — always preview, confirm, and log writes.

RECOMMENDED ACTIONS (this is the extra layer over Fundle Brain):
- ALWAYS end an analytical/diagnostic answer with a short prose "**Recommended actions**" bullet list, exactly like Fundle Brain.
- THEN, for every recommendation that YOU can actually carry out with your action tools (set_customer_tier, grant_bonus_points, adjust_points, fix_negative_balances, retier_customers, fix_double_redemptions, apply_to_uploaded_report, send_campaign, cancel_campaign, undo_action), ALSO append ONE machine-readable block so the UI can show a one-click "Execute" button:

```suggested-actions
[
  {"label": "Re-tier 22 zero-spend customers to 'kazo insider'", "description": "Sets tier on every customer with lifetime_spend = 0 (no bonus points).", "tool": "set_customer_tier", "args": {"tier": "kazo insider", "max_lifetime_spend": 0}},
  {"label": "SMS win-back to lapsing Gold customers", "description": "Bulk SMS via Karix to the Gold tier.", "tool": "send_campaign", "args": {"audience_type": "tier", "audience_value": "gold", "message": "We miss you! Enjoy 20% off your next KAZO order."}}
]
```

Rules for the suggested-actions block:
- Emit it ONLY when there is at least one CONCRETE, executable recommendation; otherwise omit the block entirely.
- Each item needs a human "label", a short "description", the exact "tool" name, and "args" derived from the REAL numbers/filters you just analysed. NEVER put confirm or reason in args — clicking Execute always runs a PREVIEW first and then asks the user to confirm + give a reason (full audit trail preserved).
- Max 4 items. The block itself is hidden from the user and rendered as buttons, so your prose recommendations must read fine on their own.
"""

MASTER_SYSTEM_PROMPT = SYSTEM_PROMPT + MASTER_ADDENDUM

# LEAN prompt used for ANALYSIS/READ questions: identical to Fundle Brain (so reads are
# exactly as fast & reliable), plus just the "Recommended actions / suggested-actions"
# layer so the UI can still show one-click Execute buttons. NO heavy action protocol here.
MASTER_READ_ADDENDUM = """

=====================================================================
You are MASTER BRAIN (the Master Admin tool). For THIS analysis/read question, answer EXACTLY
like Fundle Brain — same read tools, same decisiveness, same formatting — and ALWAYS give a
REAL, COMPLETE answer with the actual numbers. Be decisive: reach the answer in as few tool
calls as possible (a single `$match`+`$count` or filtered `count_documents` is enough for a
count). For any DUPLICATE/DOUBLE-REDEMPTION audit ("how many are affected"), call the
`audit_double_redemptions` tool ONCE; for any NEGATIVE-BALANCE question ("how many / which
customers have negative balance and why"), call `audit_negative_balances` ONCE — never
hand-write ledger aggregations for these. These audit tools return EXACT, uncapped totals;
report those exact numbers. NEVER answer from a `examples`/sample list, a capped/partial
result, an estimate, or invented figures — always state the exact totals the tools return.
NEVER reply "timed out", "I couldn't", or a vague placeholder.

After the answer, add a short prose "**Recommended actions**" list. For each recommendation you
could carry out with an action tool (set_customer_tier, grant_bonus_points, adjust_points,
fix_negative_balances, retier_customers, fix_double_redemptions, apply_to_uploaded_report,
send_campaign, cancel_campaign, undo_action), ALSO append ONE machine-readable block so the UI
shows an Execute button:

```suggested-actions
[{"label":"…","description":"…","tool":"…","args":{…}}]
```
Emit the block ONLY if there is a concrete, executable action; map each to one of the tools above
with valid args. Do NOT call any action tool yourself here — the user clicks Execute to run it
under the preview → confirm → reason flow.
"""
MASTER_READ_SYSTEM_PROMPT = SYSTEM_PROMPT + MASTER_READ_ADDENDUM


async def _seeded_history(user: Dict[str, Any], read_only: bool = False) -> List[Dict[str, Any]]:
    prompt = MASTER_READ_SYSTEM_PROMPT if read_only else MASTER_SYSTEM_PROMPT
    msgs: List[Dict[str, Any]] = [{"role": "system", "content": prompt}]
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
    try:
        # Give every tool a generous, per-call DB deadline that OVERRIDES the aggressive
        # production Atlas client `timeoutMS` (~10s) — otherwise heavy analytics aggregations
        # die mid-flight and the model reports a "timeout / data unavailable".
        with pymongo.timeout(MB_TOOL_DB_DEADLINE):
            if handler:
                result = await handler(**(args or {}), user=user)
                # A master ACTION tool may have mutated data — drop cached platform stats so a
                # follow-up KPI question reflects the change immediately.
                clear_stats_cache()
                return result
            # Fall back to the shared Fundle Brain tool registry (reads + L1 writes).
            return await execute_tool(name, args, user=user)
    except TypeError as e:
        return {"error": f"Bad arguments for {name}: {e}"}
    except Exception as e:  # noqa: BLE001
        return {"error": f"Tool {name} failed: {e}"}


_MB_RETRY = 3
_BUDGET_MSG = ("⚠️ **AI usage budget exhausted.** The Universal LLM Key for this workspace has "
               "run out of balance, so I can't run the analysis right now. Please top it up under "
               "**Profile → Universal Key → Add Balance** (or enable auto top-up), then ask me again.")


class _BudgetExceeded(Exception):
    """Emergent Universal Key budget exhausted — not retryable; surfaced as a clear message."""


async def _completion(params: Dict[str, Any]):
    """Call the LLM off the event loop with a small retry for transient proxy/network
    errors (rate-limit / timeout / 5xx / overloaded) so a blip never becomes a hard error.
    A budget-exhausted error is raised as `_BudgetExceeded` so callers can show a clear note."""
    last = None
    for attempt in range(1, _MB_RETRY + 1):
        try:
            return await asyncio.to_thread(litellm.completion, **params)
        except Exception as e:  # noqa: BLE001
            blob = f"{type(e).__name__}: {e}".lower()
            if "budget has been exceeded" in blob or "max budget" in blob:
                raise _BudgetExceeded(str(e))
            last = e
            transient = any(k in blob for k in (
                "timeout", "timed out", "rate", "429", "500", "502", "503", "504",
                "overloaded", "connection", "temporarily", "unavailable", "apierror",
                "internalserver", "service unavailable"))
            if attempt < _MB_RETRY and transient:
                logger.warning(f"MB completion transient error (attempt {attempt}/{_MB_RETRY}): {e}")
                await asyncio.sleep(0.8 * attempt)
                continue
            raise
    raise last  # pragma: no cover


# Words that signal the user wants to CHANGE data (not just read/analyse). Action tools are
# exposed ONLY when this matches (or the user clicked an Execute button) — so analysis/read
# questions behave EXACTLY like Fundle Brain (read tools only) and never spiral into heavy
# action-tool previews that stall on the full customer base.
_ACTION_INTENT_RE = re.compile(
    r"\b(fix|repair|correct|restore|grant|give|award|credit|deduct|debit|remove|adjust|"
    r"set\s+tier|re-?tier|change\s+tier|move\s+to\s+tier|upgrade|downgrade|apply|"
    r"send\s+(an?\s+)?(sms|campaign|message|blast)|launch\s+(a\s+)?campaign|broadcast|"
    r"cancel\s+campaign|undo|revert|reverse|void|merge|de-?dupe|bonus|top\s*-?up|"
    r"add\s+points|zero\s+out|write[\s-]*off|reset|wipe|enroll|enrol|opt[\s-]*out)\b",
    re.IGNORECASE)


def _has_action_intent(text: str) -> bool:
    return bool(_ACTION_INTENT_RE.search(text or ""))


def _compact_trace(trace: List[Dict[str, Any]]) -> str:
    """A short, model-readable summary of the tool results gathered so far — used to
    synthesise a final answer when the full message history can't be replayed."""
    parts = []
    for t in trace[-12:]:
        args = json.dumps(t.get("args", {}), default=str)[:200]
        parts.append(f"- {t.get('tool')}({args}) => {str(t.get('result_preview', ''))[:600]}")
    return "\n".join(parts) or "(no tool results were gathered)"


def _fmt_negative_balances(r: Dict[str, Any]) -> str:
    if r.get("computed") is False:
        msg = r.get("message") or ("Couldn't compute the negative-balance count right now — "
                                   "please retry in a few seconds.")
        cross = r.get("ledger_cross_check") or ""
        return ("### Customers with a negative points balance\n\n" + msg
                + (f"\n\n_{cross}_" if cross else ""))
    n = int(r.get("negative_balance_customers", 0) or 0)
    cross = r.get("ledger_cross_check", "") or ""
    if not n:
        return ("### Customers with a negative points balance\n\n"
                "**None.** No customer currently has a negative `points_balance` — the authoritative, "
                "indexed source of truth shows **0** negative balances, so field balances are clean.\n\n"
                f"_{cross}_")
    lines = ["### Customers with a negative points balance\n",
             f"- **{n} customers** currently have a negative `points_balance` (authoritative field), "
             f"with a combined deficit of **{r.get('total_deficit_points', 0)} points**.",
             f"- {cross}"]
    worst = r.get("worst_customers") or []
    if worst:
        lines.append("\n**Worst-affected customers**\n")
        lines.append("| Mobile | Name | Balance |\n|---|---|---:|")
        for w in worst[:10]:
            lines.append(f"| {w.get('mobile', '')} | {w.get('name') or '—'} | {w.get('points_balance', '')} |")
    lines.append(f"\n**Exact reason / why this happens:** {r.get('reason_hint', '')}")
    return "\n".join(lines)


def _fmt_double_redemptions(r: Dict[str, Any]) -> str:
    if r.get("computed") is False or r.get("exact") is False:
        return ("### Duplicate-redemption audit\n\n"
                + (r.get("message") or "Couldn't complete an exact scan right now — please retry, "
                   "or scope it to a single customer's mobile for an instant exact answer."))
    n = int(r.get("duplicate_rows_found", 0) or 0)
    if not n:
        return ("### Duplicate-redemption audit\n\n**0 affected.** No double-redemption deductions "
                "were found across the entire customer base — the points ledger is clean on this check "
                "(exact count over all history).")
    return ("### Duplicate-redemption audit\n\n"
            f"- **{n}** duplicate ledger rows across **{r.get('customers_affected', 0)}** customers (exact).\n"
            f"- **{r.get('points_double_deducted', 0)} points** were wrongly double-deducted.\n\n"
            "Ask me to *fix the double redemptions* to credit these back (preview → confirm).")


_NEG_BAL_RE = re.compile(r"negative[\s-]+(?:loyalty[\s-]+)?(?:point|points|bal)", re.IGNORECASE)
_DUP_AUDIT_RE = re.compile(r"(duplicate|double)[\s-]*redempt", re.IGNORECASE)


async def _deterministic_audit(question: str, user: Dict[str, Any]) -> tuple[Optional[str], List[Dict[str, Any]]]:
    """Answer the two recurring audit questions DIRECTLY from the DB (no LLM) so they ALWAYS
    return an EXACT, clean answer — instant, free, and immune to LLM budget/timeout limits.
    Each tool call is itself hard-capped so it can never hang the request."""
    q = question or ""
    try:
        if _DUP_AUDIT_RE.search(q):
            from routes.master_brain_tools import _tool_audit_double_redemptions
            r = await asyncio.wait_for(_tool_audit_double_redemptions(user=user), timeout=40)
            return _fmt_double_redemptions(r), [{"tool": "audit_double_redemptions", "args": {},
                                                 "result_preview": str(r)[:500]}]
        if _NEG_BAL_RE.search(q):
            from routes.master_brain_tools import _tool_audit_negative_balances
            r = await asyncio.wait_for(_tool_audit_negative_balances(user=user), timeout=40)
            return _fmt_negative_balances(r), [{"tool": "audit_negative_balances", "args": {},
                                                "result_preview": str(r)[:500]}]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"MB deterministic audit failed: {e}")
    return None, []


async def _final_synthesis(system_content: str, question: str, trace: List[Dict[str, Any]],
                           model: str, provider: str) -> str:
    """Compose the final answer from ONLY the accumulated tool results, on a fresh, small
    message list with a COMPACT system prompt (not the full Master prompt) so the premium
    engine has little to read and replies fast + bounded. No tool-call scaffolding, so it
    can't overflow context or break Anthropic's tool-message ordering rules."""
    msgs = [
        {"role": "system", "content": (
            "You are Master Brain, an elite retail-loyalty & CRM data analyst for KAZO. Compose a "
            "decisive, executive-grade FINAL answer in clean Markdown (use tables for tabular data, "
            "bold the key numbers). Use ONLY the exact figures in the data below — never invent, "
            "estimate, round-guess, or extrapolate from an 'examples'/sample list. Report the exact "
            "total counts the tools returned. Do NOT mention tools.")},
        {"role": "user", "content": (
            (question or "Answer the user's question.")
            + "\n\nData gathered (tool outputs):\n" + _compact_trace(trace)
            + "\n\nGive the best possible final answer now.")},
    ]
    params = _build_completion_params(msgs, model, provider)
    params["max_tokens"] = 2500
    resp = await _completion(params)
    return resp.choices[0].message.content or ""


async def _run_tool_loop(messages: List[Dict[str, Any]], model: str, provider: str,
                         user: Dict[str, Any],
                         tools: Optional[List[Dict[str, Any]]] = None,
                         answer_model: Optional[str] = None,
                         answer_provider: Optional[str] = None,
                         trace_out: Optional[List[Dict[str, Any]]] = None) -> tuple[str, List[Dict[str, Any]]]:
    """Run the model<->tool loop OFF the event loop (litellm.completion is blocking) and
    enforce a wall-clock budget so we ALWAYS return well before the ~60s ingress 502.
    Resilient: an LLM/context/budget error never bubbles up as a hard 500.

    HYBRID engine: `model` is the FAST loop engine that gathers data via tool calls
    (Sonnet 4.6). If `answer_model` is given (Opus 4.7), the user-facing FINAL answer is
    composed by that premium engine from the gathered results — giving Opus-grade depth
    without Opus latency on every tool round (which is what caused the 502 timeouts).
    `tools` selects the schema set (read-only for analysis, full read+action for writes).
    `trace_out`, if passed, is the live trace list the caller can read for partial results
    (used by the outer hard-timeout guard to synthesise from whatever was gathered)."""
    trace: List[Dict[str, Any]] = trace_out if trace_out is not None else []
    tool_schemas = tools if tools is not None else ALL_TOOL_SCHEMAS
    am, ap = (answer_model or model), (answer_provider or provider)
    t0 = time.time()
    # Capture the system prompt + the user's question for the synthesis pass.
    system_content = next((m["content"] for m in messages
                           if m.get("role") == "system" and isinstance(m.get("content"), str)),
                          MASTER_SYSTEM_PROMPT)
    question = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, str):
                question = c
            elif isinstance(c, list):
                question = next((p.get("text", "") for p in c
                                 if isinstance(p, dict) and p.get("type") == "text"), "")
            break

    for _ in range(MAX_TOOL_ITERATIONS):
        if time.time() - t0 > MB_DEADLINE_SECONDS:
            break  # out of time budget -> force a final synthesis below
        params = _build_completion_params(messages, model, provider, tools=tool_schemas)
        try:
            resp = await _completion(params)
        except _BudgetExceeded:
            det, dtr = await _deterministic_audit(question, user)
            return (det, dtr) if det else (_BUDGET_MSG, trace)
        except Exception as e:  # noqa: BLE001 — LLM/context error: stop looping, synthesise
            logger.warning(f"MB tool-loop completion failed ({type(e).__name__}: {e}); "
                           f"falling back to synthesis from {len(trace)} tool result(s)")
            break
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
        # Model produced a direct answer. If no premium answer engine is configured (action
        # path), return it as-is. Otherwise hand the gathered data to the premium engine so
        # the user-facing answer gets Opus-grade depth.
        if not answer_model or answer_model == model:
            return (msg.content or ""), trace
        if msg.content:
            trace.append({"tool": "draft_answer", "args": {}, "result_preview": (msg.content or "")[:2000]})
        break

    # Compose the FINAL answer with the premium engine from gathered results, on a FRESH,
    # small message list (no assistant tool_calls scaffolding — works for Anthropic and can't
    # overflow context).
    try:
        return await _final_synthesis(system_content, question, trace, am, ap), trace
    except _BudgetExceeded:
        det, dtr = await _deterministic_audit(question, user)
        return (det, dtr) if det else (_BUDGET_MSG, trace)
    except Exception as e:  # noqa: BLE001 — last resort: deterministic audit or a clean message
        logger.warning(f"MB final synthesis failed ({type(e).__name__}: {e})")
        det, dtr = await _deterministic_audit(question, user)
        if det:
            return det, dtr
        return ("I couldn't complete this request just now. Please try again, or narrow it "
                "(e.g. a single store, tier, or date range)."), trace


async def require_query_viewer(user: dict = Depends(get_current_user)) -> dict:
    """Master Brain Query Log: any Master Admin sees their OWN queries; a Master Query Admin
    (is_master_query_admin) sees ALL users' queries."""
    if user.get("is_demo"):
        raise HTTPException(403, "Read-only demo accounts cannot view Master Brain query logs.")
    if not (user.get("is_master_admin") or user.get("is_master_query_admin")):
        raise HTTPException(403, "Master Admin access required.")
    return user


_SUGGEST_RE = re.compile(r"```suggested-actions\s*(.*?)```", re.DOTALL | re.IGNORECASE)
# Read-only tools are never offered as an "Execute" button.
_NON_EXECUTABLE = {"master_action_log", "list_campaigns"}


def _extract_suggested_actions(reply: str) -> tuple[str, List[Dict[str, Any]]]:
    """Pull the machine-readable suggested-actions block out of the reply, validate each
    action maps to a real executable Master Brain tool, and return (clean_reply, actions)."""
    actions: List[Dict[str, Any]] = []
    m = _SUGGEST_RE.search(reply or "")
    if not m:
        return reply, actions
    clean = (reply[:m.start()] + reply[m.end():]).strip()
    try:
        parsed = json.loads(m.group(1).strip())
    except Exception:
        return clean, actions
    if not isinstance(parsed, list):
        return clean, actions
    for a in parsed:
        if not isinstance(a, dict):
            continue
        tool = a.get("tool")
        if tool in MASTER_TOOL_HANDLERS and tool not in _NON_EXECUTABLE:
            actions.append({
                "label": str(a.get("label") or tool)[:160],
                "description": str(a.get("description") or "")[:240],
                "tool": tool,
                "args": a.get("args") if isinstance(a.get("args"), dict) else {},
            })
    return clean, actions[:4]


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
    # Mark which rows can still be undone (a reversible snapshot exists and it's not already undone)
    ids = [r.get("id") for r in rows if r.get("id")]
    snap_ids = set()
    if ids:
        snaps = await mb_action_snapshots_col.find(
            {"audit_id": {"$in": ids}, "undone": {"$ne": True}}, {"_id": 0, "audit_id": 1}).to_list(len(ids))
        snap_ids = {s["audit_id"] for s in snaps}
    for r in rows:
        r["undone"] = bool(r.get("undone"))
        r["undoable"] = (r.get("id") in snap_ids) and not r["undone"]
    return {"count": len(rows), "actions": rows}


class UndoIn(BaseModel):
    reason: str = ""


@router.post("/undo/{audit_id}")
async def undo_action(audit_id: str, body: UndoIn, user: dict = Depends(require_master_admin)):
    res = await _tool_undo_action(audit_id, reason=body.reason, confirm=True, user=user)
    if res.get("error"):
        raise HTTPException(400, res["error"])
    return res


@router.get("/campaigns")
async def list_campaigns(limit: int = 50, user: dict = Depends(require_master_admin)):
    rows = await master_campaigns_col.find({}, {"_id": 0, "audience_spec": 0}) \
        .sort("created_at", -1).limit(min(limit, 100)).to_list(100)
    return {"count": len(rows), "campaigns": rows}


class CancelCampaignIn(BaseModel):
    reason: str = ""


@router.post("/campaigns/{campaign_id}/cancel")
async def cancel_campaign(campaign_id: str, body: CancelCampaignIn, user: dict = Depends(require_master_admin)):
    res = await _tool_cancel_campaign(campaign_id, reason=body.reason, confirm=True, user=user)
    if res.get("error"):
        raise HTTPException(400, res["error"])
    return res


@router.get("/datasets")
async def list_datasets(user: dict = Depends(require_master_admin)):
    rows = await mb_attachments_col.find(
        {"user_id": user["id"], "kind": "report"},
        {"_id": 0, "rows": 0, "preview": 0, "extracted_text": 0}
    ).sort("created_at", -1).limit(100).to_list(100)
    return {"count": len(rows), "datasets": rows}


@router.get("/datasets/{dataset_id}")
async def get_dataset(dataset_id: str, q: str = "", page: int = 1, page_size: int = 50,
                      user: dict = Depends(require_master_admin)):
    att = await mb_attachments_col.find_one(
        {"id": dataset_id, "user_id": user["id"], "kind": "report"}, {"_id": 0})
    if not att:
        raise HTTPException(404, "Dataset not found")
    columns = att.get("columns") or []
    all_rows = att.get("rows") or att.get("preview") or []
    needle = (q or "").strip().lower()
    if needle:
        rows = [r for r in all_rows if any(needle in str(v).lower() for v in r.values())]
    else:
        rows = all_rows
    total = len(rows)
    page = max(1, page)
    page_size = max(1, min(page_size, 200))
    start = (page - 1) * page_size
    page_rows = rows[start:start + page_size]
    return {
        "id": att["id"], "filename": att.get("filename"), "report_type": att.get("report_type"),
        "columns": columns, "row_count": att.get("row_count"),
        "rows_stored": len(all_rows), "rows_truncated": att.get("rows_truncated", False),
        "mobiles_detected": len(att.get("mobiles") or []),
        "extracted_text": att.get("extracted_text") if att.get("report_type") == "pdf" else None,
        "total_matched": total, "page": page, "page_size": page_size, "rows": page_rows,
        "created_at": att.get("created_at"),
    }


@router.get("/suggested-prompts")
async def suggested_prompts(user: dict = Depends(require_master_admin)):
    return [
        "Audit our loyalty data health and recommend fixes I can execute.",
        "How many customers are still on legacy Silver/Gold tiers? Re-tier them onto the configured slabs.",
        "Set every customer with lifetime spend = 0 to the 'kazo insider' slab.",
        "Draft and recommend a festive SMS win-back campaign for Gold-tier customers.",
        "Show me my recent campaigns and their delivery status.",
        "Find and fix customers whose points were double-deducted by the redemption bug (preview first).",
        "Show the Master Brain action log, then undo my last action.",
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

    # Read vs write intent decides the prompt + tool set. Analysis/read questions use the
    # LEAN Fundle-Brain prompt + read-only tools (so they're as fast & reliable as Fundle
    # Brain); action tools + the full write protocol are exposed only on real action intent
    # (or when the user clicked Execute on a recommendation).
    wants_action = bool(req.force_action) or _has_action_intent(req.message or "")

    history: List[Dict[str, Any]] = await _seeded_history(user, read_only=not wants_action)
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

    # One-click "Execute" on a recommended action -> force a PREVIEW of that exact tool first.
    fa = req.force_action or None
    if fa and fa.get("tool") in MASTER_TOOL_HANDLERS:
        history.append({"role": "system", "content": (
            f"The user clicked Execute on a recommended action. Call the tool "
            f"`{fa.get('tool')}` with these arguments in PREVIEW mode now (confirm=false): "
            f"{json.dumps(fa.get('args') or {}, default=str)}. Present the preview as a Markdown "
            f"table, then ask the user to confirm and provide a reason before you apply it.")})

    # expose the session to action tools (server-side fallback for uploaded reports)
    user["_mb_session"] = session_id

    # Engine: Master Brain runs on Claude Sonnet 4.6 (same fast, highly-capable engine as
    # Fundle Brain). Opus was burning the AI budget fast AND its latency caused 502 timeouts;
    # Sonnet is ~5x cheaper, faster and reliable. (Override via req.model still works.)
    provider, model = _resolve_model(req.model, default=("anthropic", "claude-sonnet-4-6"))
    tool_set = ALL_TOOL_SCHEMAS if wants_action else READ_TOOL_SCHEMAS
    trace: List[Dict[str, Any]] = []
    reply: Optional[str] = None

    # DETERMINISTIC FAST-PATH: the two recurring, expensive audit questions are answered
    # straight from the DB (no LLM) — always exact, instant, free, and immune to budget/timeout.
    if not wants_action:
        det_reply, det_trace = await _deterministic_audit(req.message, user)
        if det_reply:
            reply, trace = det_reply, det_trace

    if reply is None:
        try:
            # HARD overall wall-clock guarantee: the K8s ingress 502s at ~60s, so we cap the whole
            # run at 46s. If exceeded, we cancel and compose a REAL answer from gathered data.
            try:
                reply, trace = await asyncio.wait_for(
                    _run_tool_loop(history, model, provider, user=user, tools=tool_set,
                                   trace_out=trace),
                    timeout=46)
            except asyncio.TimeoutError:
                logger.warning(f"MB overall 46s cap hit; recovering from {len(trace)} tool result(s)")
                det_reply, det_trace = await _deterministic_audit(req.message, user)
                if det_reply:
                    reply, trace = det_reply, (det_trace or trace)
                else:
                    try:
                        reply = await asyncio.wait_for(
                            _final_synthesis("", req.message, trace, "claude-sonnet-4-6", "anthropic"),
                            timeout=9)
                    except Exception:  # noqa: BLE001
                        reply = ("That query is taking longer than expected on the full dataset. "
                                 "Please narrow it to a single store, tier, or date range and try again.")
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, f"AI error: {str(e)}")

    reply, suggested_actions = _extract_suggested_actions(reply)

    now = datetime.now(timezone.utc).isoformat()
    stored_text = req.message + (f"  ·  📎 {', '.join(a['filename'] for a in att_chips)}" if att_chips else "")
    user_msg = {"role": "user", "content": stored_text, "timestamp": now, "attachments": att_chips}
    bot_msg = {"role": "assistant", "content": reply, "timestamp": now, "tool_trace": trace,
               "suggested_actions": suggested_actions}
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
    # Per-user query log (each user sees their own; a Master Query Admin sees everyone's)
    try:
        await mb_query_log_col.insert_one({
            "id": uuid.uuid4().hex, "user_id": user["id"], "user_email": user.get("email"),
            "user_name": user.get("name"), "session_id": session_id,
            "query": (req.message or "")[:2000], "reply_preview": (reply or "")[:600],
            "tools_used": [t["tool"] for t in trace],
            "attachments": [a["filename"] for a in att_chips], "created_at": now,
        })
    except Exception:
        pass
    return {"session_id": session_id, "reply": reply,
            "tools_used": [t["tool"] for t in trace], "tool_trace": trace,
            "suggested_actions": suggested_actions}


@router.get("/query-log")
async def query_log(days: int = 30, limit: int = 200, user_email: str = "", q: str = "",
                    user: dict = Depends(require_query_viewer)):
    is_global = bool(user.get("is_master_query_admin"))
    fil: Dict[str, Any] = {}
    if days and days > 0:
        fil["created_at"] = {"$gte": (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()}
    if is_global:
        if user_email:
            fil["user_email"] = user_email
    else:
        fil["user_id"] = user["id"]
    if q:
        fil["query"] = {"$regex": re.escape(q), "$options": "i"}
    rows = await mb_query_log_col.find(fil, {"_id": 0}).sort("created_at", -1).limit(min(limit, 500)).to_list(500)
    users: List[str] = []
    if is_global:
        try:
            users = sorted([u for u in await mb_query_log_col.distinct("user_email") if u])
        except Exception:
            users = []
    return {"count": len(rows), "queries": rows, "is_global": is_global, "users": users}
