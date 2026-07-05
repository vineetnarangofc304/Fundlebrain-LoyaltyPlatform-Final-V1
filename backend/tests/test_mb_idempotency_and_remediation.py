"""Master Brain incident-fix regression tests (iter 82).

Covers the 3 production-incident fixes:
  1) IDEMPOTENCY: re-crediting the SAME file (same mobiles+points signature) within
     30 days is BLOCKED (ALREADY_CREDITED), balance does NOT double.
  2) FORCE OVERRIDE: explicit force=true re-credit is allowed and balances stack.
  3) reverse_duplicate_bonus_credits: seeded duplicate ledger + inflated balance
     is reversed to single-credit value, negative 'adjust' ledger row exists,
     undo restores.
  4) ANTI-FABRICATION: analysis question about over-credited customers MUST be
     backed by a tool call (or admit no data), not a fabricated report.
  5) REGRESSION: no credit_job_status tool, no 'queued/background' phrasing on
     normal single credit, per-row amounts applied.
"""
import io
import os
import re
import time
import uuid
import pytest
import requests


def _load_frontend_env():
    p = "/app/frontend/.env"
    if os.path.exists(p):
        for line in open(p):
            if line.startswith("REACT_APP_BACKEND_URL"):
                v = line.split("=", 1)[1].strip().strip('"').strip("'")
                os.environ.setdefault("REACT_APP_BACKEND_URL", v)


_load_frontend_env()
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
LOGIN_EMAIL = "masteradmin@fundle.io"
LOGIN_PASSWORD = "Master@2026"

# throwaway test mobiles (different range from iter81 so no cross-collision)
IDEMP_MOBILES = ["9990080001", "9990080002", "9990080003"]
IDEMP_POINTS = {"9990080001": 29, "9990080002": 33, "9990080003": 41}

# Remediation test: one customer whose ledger already has 4 duplicate bonus rows
REMED_MOBILE = "9990080011"
REMED_UNIT = 29           # each duplicate row credits 29
REMED_DUPES = 4           # 4 identical rows (bug scenario)
REMED_INFLATED = 29 * 4   # 116 (balance inflated as if $inc ran 4x)
REMED_REASON = "bonus top up campaign TEST82"

# ---- Mongo helpers ----
from pymongo import MongoClient

def _load_backend_env():
    p = "/app/backend/.env"
    if os.path.exists(p):
        for line in open(p):
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_backend_env()
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
_mc = MongoClient(MONGO_URL)
_db = _mc[DB_NAME]
customers = _db["customers"]
points_ledger = _db["points_ledger"]
audit_logs = _db["audit_logs"]
mb_snap = _db["mb_action_snapshots"]
mb_att = _db["mb_attachments"]
mb_receipts = _db["mb_credit_receipts"]

ALL_TEST_MOBILES = IDEMP_MOBILES + [REMED_MOBILE]


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    j = r.json()
    tok = j.get("token") or j.get("access_token")
    assert tok, f"no token: {j}"
    return tok


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module", autouse=True)
def seed_and_cleanup():
    # ---- pre-clean any stale state ----
    customers.delete_many({"mobile": {"$in": ALL_TEST_MOBILES}})
    points_ledger.delete_many({"customer_mobile": {"$in": ALL_TEST_MOBILES}})
    mb_receipts.delete_many({"filename": "qa82_credit.csv"})
    # ---- seed idempotency customers (base 100) ----
    docs = [{
        "id": f"MBQA82_{m}", "mobile": m, "name": f"QA82 {m}",
        "points_balance": 100, "lifetime_points_earned": 100,
        "lifetime_spend": 5000, "tier": "kazo insider", "is_active": True,
    } for m in IDEMP_MOBILES]
    # ---- seed remediation customer with INFLATED balance (116) simulating the bug ----
    docs.append({
        "id": f"MBQA82_{REMED_MOBILE}", "mobile": REMED_MOBILE, "name": f"QA82 {REMED_MOBILE}",
        # baseline 0 + 4x 29 = 116 (inflated); one legitimate credit should leave 29.
        "points_balance": REMED_INFLATED, "lifetime_points_earned": REMED_INFLATED,
        "lifetime_spend": 3000, "tier": "kazo insider", "is_active": True,
    })
    customers.insert_many(docs)

    # ---- seed the 4 duplicate bonus ledger rows for REMED_MOBILE ----
    from datetime import datetime, timezone, timedelta
    base_t = datetime.now(timezone.utc) - timedelta(hours=2)
    ledger_docs = []
    for i in range(REMED_DUPES):
        ledger_docs.append({
            "id": str(uuid.uuid4()),
            "customer_mobile": REMED_MOBILE,
            "points": REMED_UNIT,
            "type": "bonus", "kind": "bonus",
            "reference_type": "master_brain",
            "via": "master_brain",
            "reason": REMED_REASON,
            "created_at": (base_t + timedelta(minutes=i * 2)).isoformat(),
            "created_by": LOGIN_EMAIL,
        })
    points_ledger.insert_many(ledger_docs)

    yield

    # ---- teardown ----
    ids = [f"MBQA82_{m}" for m in ALL_TEST_MOBILES]
    customers.delete_many({"id": {"$in": ids}})
    points_ledger.delete_many({"customer_mobile": {"$in": ALL_TEST_MOBILES}})
    mb_receipts.delete_many({"filename": "qa82_credit.csv"})
    # audits/snapshots from this session
    aud = list(audit_logs.find(
        {"source": "master_brain", "user_email": LOGIN_EMAIL,
         "reason": {"$regex": "QA82"}}, {"id": 1, "_id": 0}))
    aud_ids = [a["id"] for a in aud]
    if aud_ids:
        audit_logs.delete_many({"id": {"$in": aud_ids}})
        mb_snap.delete_many({"audit_id": {"$in": aud_ids}})
    mb_att.delete_many({"filename": "qa82_credit.csv"})


# ---------- helpers ----------
def _chat(headers, session_id, message, attachment_ids=None, timeout=120):
    body = {"session_id": session_id, "message": message,
            "attachment_ids": attachment_ids or []}
    r = requests.post(f"{BASE_URL}/api/master-brain/chat",
                      headers=headers, json=body, timeout=timeout)
    assert r.status_code == 200, f"chat failed {r.status_code}: {r.text[:400]}"
    return r.json()


def _upload_idemp_csv(headers, session_id):
    lines = ["MOBILE,Points to be Credit"]
    for m in IDEMP_MOBILES:
        lines.append(f"{m},{IDEMP_POINTS[m]}")
    csv_bytes = ("\n".join(lines) + "\n").encode()
    files = {"file": ("qa82_credit.csv", io.BytesIO(csv_bytes), "text/csv")}
    data = {"session_id": session_id}
    r = requests.post(f"{BASE_URL}/api/master-brain/upload",
                      headers=headers, files=files, data=data, timeout=30)
    assert r.status_code == 200, f"upload failed: {r.status_code} {r.text[:400]}"
    j = r.json()
    assert j.get("kind") == "report", j
    assert j.get("points_rows_detected") == len(IDEMP_MOBILES), j
    return j["id"]


def _tool_calls(chat_response, tool_name):
    """Return trace entries where tool == tool_name."""
    return [t for t in (chat_response.get("tool_trace") or [])
            if t.get("tool") == tool_name]


# ============================================================
# 1) IDEMPOTENCY + 2) FORCE OVERRIDE (single scenario, share state)
# ============================================================
def test_idempotency_and_force_override(headers):
    session_id = uuid.uuid4().hex
    att_id_1 = _upload_idemp_csv(headers, session_id)

    # ---- preview (turn 1) ----
    prev = _chat(headers, session_id,
                 "Please credit the points in this attached file.",
                 attachment_ids=[att_id_1])
    assert "credit_points_from_file" in (prev.get("tools_used") or []), \
        f"tool not called on preview. tools={prev.get('tools_used')} reply={prev.get('reply')[:300]}"
    pv_calls = _tool_calls(prev, "credit_points_from_file")
    assert pv_calls and str(pv_calls[0].get("result_preview") or "").lower().find("preview") >= 0

    # ---- confirm (turn 2) — first legitimate credit ----
    conf = _chat(headers, session_id,
                 "Yes, apply it. Reason: QA82 first credit.")
    tu2 = conf.get("tools_used") or []
    assert "credit_points_from_file" in tu2, \
        f"tool not called on confirm. reply={conf.get('reply')[:300]}"
    applied_calls = [t for t in _tool_calls(conf, "credit_points_from_file")
                     if "'applied': True" in str(t.get("result_preview") or "")]
    assert applied_calls, f"no applied call in trace: {conf.get('tool_trace')}"
    rp = str(applied_calls[-1].get("result_preview") or "")
    m_aud = re.search(r"'audit_id': '([0-9a-f-]+)'", rp)
    assert m_aud, f"audit_id missing from applied result: {rp[:400]}"
    audit_id_1 = m_aud.group(1)

    # DB: each customer went 100 -> 100+their_points
    for m in IDEMP_MOBILES:
        c = customers.find_one({"id": f"MBQA82_{m}"}, {"_id": 0})
        exp = 100 + IDEMP_POINTS[m]
        assert c["points_balance"] == exp, f"first credit failed {m}: got {c['points_balance']} expected {exp}"

    # ---- turn 3: ask to credit the SAME FILE again — MUST be blocked ----
    # Upload the same-content file again (different attachment id, same signature)
    att_id_2 = _upload_idemp_csv(headers, session_id)
    blocked = _chat(headers, session_id,
                    "Actually please credit that same file again to those customers.",
                    attachment_ids=[att_id_2])
    reply2 = (blocked.get("reply") or "")
    print(f"blocked reply (first 400): {reply2[:400]}")
    trace_b = blocked.get("tool_trace") or []
    # The tool may be called; if called with confirm=true it MUST return ALREADY_CREDITED.
    already_blocked = False
    for t in trace_b:
        if t.get("tool") != "credit_points_from_file":
            continue
        rp = str(t.get("result_preview") or "")
        if "ALREADY_CREDITED" in rp or "'blocked': True" in rp or "already credited" in rp.lower():
            already_blocked = True
            break
    # AI may also just refuse without calling with confirm=true — that's fine too, so long
    # as balances didn't move. The DB check below is the source of truth.
    for m in IDEMP_MOBILES:
        c = customers.find_one({"id": f"MBQA82_{m}"}, {"_id": 0})
        exp = 100 + IDEMP_POINTS[m]
        assert c["points_balance"] == exp, \
            f"IDEMPOTENCY BROKEN — balance changed on re-credit for {m}: {c['points_balance']} (expected {exp})"
    print(f"idempotency: tool-level blocked={already_blocked}, DB balance unchanged ✓")

    # ---- turn 4: FORCE override — user explicitly says force ----
    forced = _chat(headers, session_id,
                   "Yes, credit it again — force it. Reason: QA82 intentional second credit.",
                   attachment_ids=[att_id_2])
    tuf = forced.get("tools_used") or []
    print(f"force turn tools={tuf} reply={(forced.get('reply') or '')[:300]}")
    # Model must have retried the tool call with force=true resulting in applied=True.
    forced_applied = [t for t in _tool_calls(forced, "credit_points_from_file")
                      if "'applied': True" in str(t.get("result_preview") or "")]
    # DB: balance should now be 100 + 2*points
    force_worked_db = all(
        customers.find_one({"id": f"MBQA82_{m}"}, {"_id": 0})["points_balance"] == 100 + 2 * IDEMP_POINTS[m]
        for m in IDEMP_MOBILES
    )
    assert forced_applied or force_worked_db, (
        "FORCE OVERRIDE FAILED — AI did not force-credit a second time. "
        f"tools_used={tuf} reply={(forced.get('reply') or '')[:400]}")
    if not force_worked_db:
        # If tool called but DB didn't move, that's a bug in force=true
        raise AssertionError("force credit tool ran but DB balance didn't stack — force=true broken")
    print("force override: applied ✓")


# ============================================================
# 3) REMEDIATION — reverse_duplicate_bonus_credits
# ============================================================
def test_reverse_duplicate_bonus_credits_and_undo(headers):
    # sanity: seed state is correct
    c = customers.find_one({"id": f"MBQA82_{REMED_MOBILE}"}, {"_id": 0})
    assert c["points_balance"] == REMED_INFLATED
    assert c["lifetime_points_earned"] == REMED_INFLATED
    assert points_ledger.count_documents(
        {"customer_mobile": REMED_MOBILE, "type": "bonus",
         "reason": REMED_REASON}) == REMED_DUPES

    session_id = uuid.uuid4().hex

    # ---- Preview turn ----
    prev = _chat(headers, session_id,
                 f'Please reverse the duplicate bonus credits with reason "{REMED_REASON}".')
    tu = prev.get("tools_used") or []
    assert "reverse_duplicate_bonus_credits" in tu, \
        f"tool not called on preview. tools={tu} reply={(prev.get('reply') or '')[:400]}"
    pv_calls = _tool_calls(prev, "reverse_duplicate_bonus_credits")
    assert pv_calls, "no reverse_duplicate_bonus_credits in trace"
    rp0 = str(pv_calls[0].get("result_preview") or "")
    # Preview must show REAL numbers derived from the aggregation (customers_affected=1, dupe_rows=3)
    assert "'customers_affected': 1" in rp0, f"preview should show 1 customer affected: {rp0[:400]}"
    assert "'duplicate_rows': 3" in rp0, f"preview should show 3 duplicate rows: {rp0[:400]}"
    # excess points = 3 * 29 = 87
    assert "'total_excess_points': 87" in rp0, f"preview excess points wrong: {rp0[:400]}"

    # ---- Confirm turn ----
    conf = _chat(headers, session_id,
                 "Yes, apply the reversal. Reason: QA82 clean up duplicates.")
    tu2 = conf.get("tools_used") or []
    assert "reverse_duplicate_bonus_credits" in tu2, \
        f"tool not called on confirm. reply={(conf.get('reply') or '')[:400]}"
    applied = [t for t in _tool_calls(conf, "reverse_duplicate_bonus_credits")
               if "'applied': True" in str(t.get("result_preview") or "")]
    assert applied, f"no applied reverse in trace: {conf.get('tool_trace')}"
    rpA = str(applied[-1].get("result_preview") or "")
    m_aud = re.search(r"'audit_id': '([0-9a-f-]+)'", rpA)
    assert m_aud, f"no audit_id in applied result: {rpA[:400]}"
    audit_id = m_aud.group(1)

    # ---- DB checks: balance dropped from 116 -> 29 ----
    c = customers.find_one({"id": f"MBQA82_{REMED_MOBILE}"}, {"_id": 0})
    assert c["points_balance"] == REMED_UNIT, \
        f"balance after reversal expected {REMED_UNIT} got {c['points_balance']}"
    assert c["lifetime_points_earned"] == REMED_UNIT, \
        f"lifetime after reversal expected {REMED_UNIT} got {c['lifetime_points_earned']}"

    # Original 4 bonus rows must still exist (never deleted)
    assert points_ledger.count_documents(
        {"customer_mobile": REMED_MOBILE, "type": "bonus",
         "reason": REMED_REASON}) == REMED_DUPES

    # A negative adjust ledger row was written
    adj = list(points_ledger.find(
        {"customer_mobile": REMED_MOBILE, "type": "adjust",
         "reference_type": "master_brain"},
        {"_id": 0}))
    assert adj, "no compensating adjust ledger row"
    assert sum(int(a["points"]) for a in adj) == -(REMED_UNIT * (REMED_DUPES - 1)), \
        f"adjust total should be -{REMED_UNIT * (REMED_DUPES - 1)}: {adj}"

    # ---- UNDO the reversal ----
    undo_session = uuid.uuid4().hex
    up = _chat(headers, undo_session,
               f"Please undo action id {audit_id}. Reason: QA82 undo reversal.")
    assert "undo_action" in (up.get("tools_used") or []), \
        f"undo preview did not call undo_action: {(up.get('reply') or '')[:300]}"

    uc = _chat(headers, undo_session, "Yes apply it. Reason: QA82 undo reversal.")
    applied_undo = [t for t in _tool_calls(uc, "undo_action")
                    if "'applied': True" in str(t.get("result_preview") or "")]
    assert applied_undo, f"no applied undo in trace: {(uc.get('reply') or '')[:400]}"

    # After undo, balance restored to 116
    c = customers.find_one({"id": f"MBQA82_{REMED_MOBILE}"}, {"_id": 0})
    assert c["points_balance"] == REMED_INFLATED, \
        f"undo did not restore balance: got {c['points_balance']} expected {REMED_INFLATED}"
    assert c["lifetime_points_earned"] == REMED_INFLATED


# ============================================================
# 4) ANTI-FABRICATION
# ============================================================
def test_anti_fabrication_over_credited_question(headers):
    """AI must NOT invent a customer-count/table when asked about over-credited customers.
    It must call a tool (aggregation / reverse_duplicate_bonus_credits preview) or admit no data."""
    session_id = uuid.uuid4().hex
    resp = _chat(headers, session_id,
                 "How many customers were over-credited or double-credited "
                 "by master brain in the last 30 days? Give me the count.",
                 timeout=120)
    reply = (resp.get("reply") or "")
    tools = resp.get("tools_used") or []
    print(f"anti-fab tools={tools}")
    print(f"anti-fab reply (first 500): {reply[:500]}")

    accepted_tools = {"reverse_duplicate_bonus_credits", "run_aggregation",
                      "master_action_log", "action_log", "list_master_actions"}
    called_ok = any(t in accepted_tools for t in tools)

    low = reply.lower()
    # Known fabricated numbers from the incident report — must NOT appear.
    fabricated_markers = ["34 customers", "27 over", "27 over-credited",
                          "11,576", "11576"]
    has_fab_marker = any(mk in low for mk in fabricated_markers)
    assert not has_fab_marker, f"AI produced fabricated incident-report numbers: {reply[:600]}"

    # It's OK if the AI honestly says it needs to query / no data / calls a tool.
    admits = any(k in low for k in ["i don't have", "i do not have", "no records", "let me query",
                                     "need to query", "no data", "will query", "run a query",
                                     "checking", "let me check", "no duplicate"])
    assert called_ok or admits, (
        "Anti-fabrication guard failed: AI answered without calling a data tool "
        f"and without admitting lack of data. tools={tools} reply={reply[:400]}")


# ============================================================
# 5) REGRESSION guards
# ============================================================
def test_credit_job_status_tool_absent():
    from routes.master_brain_tools import MASTER_TOOL_SCHEMAS
    def _name(s):
        return s.get("name") or (s.get("function") or {}).get("name")
    names = [_name(s) for s in MASTER_TOOL_SCHEMAS]
    assert "credit_job_status" not in names
    # New tools must be present
    assert "reverse_duplicate_bonus_credits" in names
    assert "credit_points_from_file" in names


def test_credit_points_from_file_schema_has_force():
    """Schema must expose a `force` boolean parameter."""
    from routes.master_brain_tools import MASTER_TOOL_SCHEMAS
    def _name(s):
        return s.get("name") or (s.get("function") or {}).get("name")
    schema = next(s for s in MASTER_TOOL_SCHEMAS if _name(s) == "credit_points_from_file")
    fn = schema.get("function") or schema
    params = (fn.get("parameters") or fn.get("input_schema") or {}).get("properties", {})
    assert "force" in params, f"force param missing from schema: {list(params.keys())}"
    assert params["force"].get("type") == "boolean"
