"""Master Brain credit_points_from_file — INLINE end-to-end test (iter 81).

Covers:
  1) Preview turn -> tool called, preview returned with per-row sample.
  2) Confirm turn -> tool called with confirm=true, INSTANT result (no queued/background).
  3) Per-row per-customer credit applied: each mobile increases by its OWN amount;
     lifetime_points_earned matches; a bonus ledger row per customer.
  4) Not-found handling; duplicate mobile SUMMED.
  5) Undo restores balances / lifetime.
  6) Regression: no credit_job_status tool exposed; no "queued"/"running in background"
     phrasing in the confirm reply.

Uses throwaway customers 999006000{1..5} inserted directly into Mongo, cleaned up at end.
"""
import io
import os
import re
import sys
import time
import uuid
import asyncio
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

TEST_MOBILES = ["9990060001", "9990060002", "9990060003", "9990060004", "9990060005"]
# points to credit per mobile (all DIFFERENT to prove per-row semantics)
POINTS_MAP = {"9990060001": 111, "9990060002": 222, "9990060003": 333, "9990060004": 444}
# 9990060005 is deliberately NOT inserted -> not-found test
NOT_FOUND_MOBILE = "9990060005"
# 9990060001 appears twice in the file with different values -> must be summed
DUP_EXTRA_POINTS = 50  # so total for 9990060001 = 111 + 50 = 161


# ----- Mongo helpers (sync via pymongo to keep the pytest simple) -----
from pymongo import MongoClient

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "kazo_fundle_db")
_mc = MongoClient(MONGO_URL)
_db = _mc[DB_NAME]
customers = _db["customers"]
points_ledger = _db["points_ledger"]
audit_logs = _db["audit_logs"]
mb_snap = _db["mb_action_snapshots"]
mb_att = _db["mb_attachments"]


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"no token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module", autouse=True)
def seed_and_cleanup():
    # -- seed 4 test customers (5th mobile is intentionally missing) --
    customers.delete_many({"mobile": {"$in": TEST_MOBILES + [int(m) for m in TEST_MOBILES]}})
    points_ledger.delete_many({"customer_mobile": {"$in": TEST_MOBILES}})
    docs = []
    for m in TEST_MOBILES[:4]:
        docs.append({
            "id": f"MBQA_{m}",
            "mobile": m,
            "name": f"QA {m}",
            "points_balance": 1000,
            "lifetime_points_earned": 1000,
            "lifetime_spend": 5000,
            "tier": "kazo insider",
            "is_active": True,
        })
    customers.insert_many(docs)

    yield

    # -- cleanup --
    ids = [f"MBQA_{m}" for m in TEST_MOBILES[:4]]
    customers.delete_many({"id": {"$in": ids}})
    points_ledger.delete_many({"customer_mobile": {"$in": TEST_MOBILES}})
    # audit + snapshots + attachments created by this test run
    aud = list(audit_logs.find({"source": "master_brain",
                                "user_email": LOGIN_EMAIL,
                                "reason": {"$regex": "^QA "}},
                               {"id": 1, "_id": 0}))
    aud_ids = [a["id"] for a in aud]
    if aud_ids:
        audit_logs.delete_many({"id": {"$in": aud_ids}})
        mb_snap.delete_many({"audit_id": {"$in": aud_ids}})
    mb_att.delete_many({"user_id": {"$exists": True}, "filename": "qa_credit.csv"})


def _upload_csv(headers, session_id):
    csv_bytes = (
        "MOBILE,Points to be Credit\n"
        f"{TEST_MOBILES[0]},{POINTS_MAP[TEST_MOBILES[0]]}\n"
        f"{TEST_MOBILES[1]},{POINTS_MAP[TEST_MOBILES[1]]}\n"
        f"{TEST_MOBILES[2]},{POINTS_MAP[TEST_MOBILES[2]]}\n"
        f"{TEST_MOBILES[3]},{POINTS_MAP[TEST_MOBILES[3]]}\n"
        f"{NOT_FOUND_MOBILE},999\n"
        f"{TEST_MOBILES[0]},{DUP_EXTRA_POINTS}\n"   # duplicate mobile must be summed
    ).encode()
    files = {"file": ("qa_credit.csv", io.BytesIO(csv_bytes), "text/csv")}
    data = {"session_id": session_id}
    r = requests.post(f"{BASE_URL}/api/master-brain/upload",
                      headers=headers, files=files, data=data, timeout=30)
    assert r.status_code == 200, f"upload failed: {r.status_code} {r.text}"
    j = r.json()
    assert j.get("kind") == "report"
    assert j.get("points_rows_detected") == 5, f"points rows: {j}"
    return j["id"]


def _chat(headers, session_id, message, attachment_ids=None):
    body = {"session_id": session_id, "message": message,
            "attachment_ids": attachment_ids or []}
    r = requests.post(f"{BASE_URL}/api/master-brain/chat",
                      headers=headers, json=body, timeout=90)
    assert r.status_code == 200, f"chat failed: {r.status_code} {r.text[:500]}"
    return r.json()


# ============================================================
# The single end-to-end scenario
# ============================================================
def test_credit_points_from_file_inline_end_to_end(headers):
    session_id = uuid.uuid4().hex
    attachment_id = _upload_csv(headers, session_id)

    # ---- PREVIEW TURN ----
    t0 = time.time()
    preview = _chat(headers, session_id,
                    "Credit the points in this file to each customer.",
                    attachment_ids=[attachment_id])
    dt_preview = time.time() - t0
    print(f"preview turn: {dt_preview:.1f}s, tools_used={preview.get('tools_used')}")
    tools_used = preview.get("tools_used") or []
    assert "credit_points_from_file" in tools_used, (
        f"AI did not call credit_points_from_file on preview turn. tools_used={tools_used} "
        f"reply={preview.get('reply')[:400]}")
    trace = preview.get("tool_trace") or []
    preview_calls = [t for t in trace if t.get("tool") == "credit_points_from_file"]
    assert preview_calls, "no credit_points_from_file entries in trace"
    first = preview_calls[0]
    print(f"preview trace[0]: {first}")
    assert first.get("args", {}).get("confirm") in (False, None, "false"), \
        f"expected confirm=false on preview, got {first.get('args')}"
    rp0 = str(first.get("result_preview") or "")
    assert "'preview': True" in rp0 or '"preview": true' in rp0.lower(), \
        f"expected preview=True marker in result_preview: {rp0[:400]}"
    # DB must be unchanged after preview
    for m in TEST_MOBILES[:4]:
        c = customers.find_one({"id": f"MBQA_{m}"}, {"_id": 0})
        assert c["points_balance"] == 1000, f"balance changed on preview turn for {m}: {c}"

    # ---- CONFIRM TURN ----
    t0 = time.time()
    confirm = _chat(headers, session_id,
                    "Yes apply it. Reason: QA test credit.",
                    attachment_ids=[])
    dt_confirm = time.time() - t0
    reply = confirm.get("reply") or ""
    print(f"confirm turn: {dt_confirm:.1f}s, tools_used={confirm.get('tools_used')}")
    print(f"confirm reply (first 400): {reply[:400]}")
    tools_used2 = confirm.get("tools_used") or []
    assert "credit_points_from_file" in tools_used2, \
        f"AI did not call the tool on confirm. reply={reply[:400]}"

    # trace: an APPLIED call with confirm=true + reason, returning applied=True + audit_id
    trace2 = confirm.get("tool_trace") or []
    applied_calls = [t for t in trace2 if t.get("tool") == "credit_points_from_file"
                     and "'applied': True" in str(t.get("result_preview") or "")]
    assert applied_calls, f"no applied credit_points_from_file in trace: {trace2}"
    applied = applied_calls[-1]
    print(f"applied trace: {applied}")
    rp = str(applied.get("result_preview") or "")
    assert "'ok': True" in rp
    # extract audit_id from result_preview
    m_aud = re.search(r"'audit_id': '([0-9a-f-]+)'", rp)
    assert m_aud, f"cannot extract audit_id from result_preview: {rp}"
    audit_id = m_aud.group(1)
    # verify audit_log has correct counters
    aud_doc = audit_logs.find_one({"id": audit_id}, {"_id": 0})
    assert aud_doc is not None, f"audit_log {audit_id} not found"
    md = aud_doc.get("metadata") or {}
    assert md.get("matched") == 4, f"audit matched={md.get('matched')} expected 4"
    assert md.get("changed") == 4, f"audit changed={md.get('changed')} expected 4"
    assert md.get("not_found") == 1, f"audit not_found={md.get('not_found')} expected 1"
    expected_total = 111 + 222 + 333 + 444 + DUP_EXTRA_POINTS  # 1160 (999 for not-found excluded)
    assert md.get("total_points_credited") == expected_total, \
        f"audit total_points_credited={md.get('total_points_credited')} expected {expected_total}"

    # REGRESSION: reply text must NOT claim queued/background
    low = reply.lower()
    assert "queued" not in low, f"reply says queued: {reply}"
    assert "background" not in low, f"reply says background: {reply}"
    assert "check status" not in low, f"reply says 'check status': {reply}"
    assert dt_confirm < 45, f"confirm turn took {dt_confirm:.1f}s — too slow for inline claim"

    # ---- DB assertions: per-row deltas applied ----
    expected_delta = {
        TEST_MOBILES[0]: POINTS_MAP[TEST_MOBILES[0]] + DUP_EXTRA_POINTS,  # 161 (summed)
        TEST_MOBILES[1]: POINTS_MAP[TEST_MOBILES[1]],
        TEST_MOBILES[2]: POINTS_MAP[TEST_MOBILES[2]],
        TEST_MOBILES[3]: POINTS_MAP[TEST_MOBILES[3]],
    }
    for m, delta in expected_delta.items():
        c = customers.find_one({"id": f"MBQA_{m}"}, {"_id": 0})
        assert c is not None, f"customer {m} missing after credit"
        assert c["points_balance"] == 1000 + delta, \
            f"balance for {m}: got {c['points_balance']} expected {1000 + delta}"
        assert c["lifetime_points_earned"] == 1000 + delta, \
            f"lifetime for {m}: got {c['lifetime_points_earned']}"
        # a bonus ledger row exists
        led = list(points_ledger.find({"customer_mobile": m, "type": "bonus",
                                       "reference_type": "master_brain",
                                       "reason": {"$regex": "QA test credit"}},
                                      {"_id": 0}))
        assert led, f"no bonus ledger row for {m}"
        # ledger points must equal the credited amount (single row per customer via _credit_pairs)
        assert sum(int(x["points"]) for x in led) == delta, f"ledger sum mismatch for {m}: {led}"

    # Not-found mobile: no customer must have been created
    assert customers.find_one({"mobile": NOT_FOUND_MOBILE}) is None, \
        "not-found mobile was created — must NOT happen"
    assert points_ledger.find_one({"customer_mobile": NOT_FOUND_MOBILE}) is None

    # ---- UNDO ----
    undo_session = uuid.uuid4().hex
    undo_prev = _chat(headers, undo_session,
                      f"Please undo action id {audit_id}. Reason: QA rollback.")
    trace3 = undo_prev.get("tool_trace") or []
    print(f"undo preview tools={undo_prev.get('tools_used')}")
    assert any(t.get("tool") == "undo_action" for t in trace3), \
        f"undo preview did not call undo_action: {undo_prev.get('reply')[:300]}"

    undo_conf = _chat(headers, undo_session, "Yes apply it. Reason: QA rollback.")
    trace4 = undo_conf.get("tool_trace") or []
    applied_undo = [t for t in trace4 if t.get("tool") == "undo_action"
                    and "'applied': True" in str(t.get("result_preview") or "")]
    assert applied_undo, f"no applied undo in trace: reply={undo_conf.get('reply')[:400]}"

    # verify DB fully restored
    for m in TEST_MOBILES[:4]:
        c = customers.find_one({"id": f"MBQA_{m}"}, {"_id": 0})
        assert c["points_balance"] == 1000, f"undo failed to restore {m}: {c['points_balance']}"
        assert c["lifetime_points_earned"] == 1000, \
            f"undo failed to restore lifetime for {m}: {c['lifetime_points_earned']}"


def test_credit_job_status_tool_is_removed():
    """Regression: the removed 'credit_job_status' tool must not appear anywhere in the schemas."""
    from routes.master_brain_tools import MASTER_TOOL_SCHEMAS
    names = [s.get("name") for s in MASTER_TOOL_SCHEMAS]
    assert "credit_job_status" not in names, \
        f"credit_job_status tool must be removed; found in schemas: {names}"
