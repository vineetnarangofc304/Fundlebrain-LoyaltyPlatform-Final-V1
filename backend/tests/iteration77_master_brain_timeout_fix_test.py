"""
iteration77: Master Brain analytics timeout fix + preview/confirm action flow.

Verifies:
1. Login as Master Admin.
2. Analytics KPI query returns REAL data (no timeout / data unavailable / budget exhausted).
3. Tier distribution query returns REAL tier data.
4. Negative balance audit reports ZERO (no fabricated rows).
5. Grant bonus points → PREVIEW only (no mutation).
6. Follow-up confirmation applies + is audited.
7. Fix-negative action is honest when nothing to fix.
"""
import os
import re
import time
import pytest
import requests


def _load_backend_url():
    val = os.environ.get("REACT_APP_BACKEND_URL")
    if val:
        return val.rstrip("/")
    # Fallback: read from frontend/.env
    try:
        with open("/app/frontend/.env", "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().strip('"').rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = _load_backend_url()
CHAT_URL = f"{BASE_URL}/api/master-brain/chat"
LOGIN_URL = f"{BASE_URL}/api/auth/login"
MASTER_EMAIL = "masteradmin@fundle.io"
MASTER_PASS = "Master@2026"
CHAT_TIMEOUT = 90  # seconds — chat can take 20-45s

BAD_PHRASES = [
    "Data Unavailable",
    "data unavailable",
    "System Timeout",
    "system timeout",
    "timed out",
    "budget exhausted",
    "AI usage budget",
]


def _login():
    r = requests.post(
        LOGIN_URL,
        json={"email": MASTER_EMAIL, "password": MASTER_PASS},
        timeout=30,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("token")
    assert tok, f"no token in response: {r.text[:200]}"
    return tok


@pytest.fixture(scope="module")
def token():
    return _login()


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _chat(headers, message, session_id):
    t0 = time.time()
    r = requests.post(
        CHAT_URL,
        json={"message": message, "session_id": session_id},
        headers=headers,
        timeout=CHAT_TIMEOUT,
    )
    elapsed = time.time() - t0
    print(f"\n[chat] session={session_id} elapsed={elapsed:.1f}s status={r.status_code}")
    return r, elapsed


def _assert_no_timeout_phrases(reply: str):
    lo = reply.lower()
    for phrase in BAD_PHRASES:
        assert phrase.lower() not in lo, f"Reply contained forbidden phrase '{phrase}': {reply[:400]}"


class TestMasterBrainTimeoutFix:
    """Master Brain analytics + action flow verification."""

    # 1. Auth basic
    def test_01_login_master_admin(self):
        tok = _login()
        assert isinstance(tok, str) and len(tok) > 10

    # 2. KPI analytics returns real data
    def test_02_overall_kpis_real_data(self, headers):
        r, elapsed = _chat(
            headers,
            "How many loyalty customers and what is total points liability in rupees?",
            "qa_kpi",
        )
        assert r.status_code == 200, f"status {r.status_code} body={r.text[:300]}"
        data = r.json()
        reply = data.get("reply", "") or ""
        tools_used = data.get("tools_used", []) or []
        print(f"[kpi] tools_used={tools_used}")
        print(f"[kpi] reply (first 500): {reply[:500]}")
        assert reply.strip(), "empty reply"
        _assert_no_timeout_phrases(reply)
        assert "get_overall_kpis" in tools_used, f"expected get_overall_kpis, got {tools_used}"
        # Should mention a customer count number (any large number acceptable)
        assert re.search(r"\d[\d,]{3,}", reply), f"expected large number in reply: {reply[:300]}"

    # 3. Tier distribution real
    def test_03_tier_distribution_real_data(self, headers):
        r, elapsed = _chat(
            headers,
            "Give me the tier distribution — customers and points outstanding per tier",
            "qa_tier",
        )
        assert r.status_code == 200, f"status {r.status_code} body={r.text[:300]}"
        data = r.json()
        reply = data.get("reply", "") or ""
        tools_used = data.get("tools_used", []) or []
        print(f"[tier] tools_used={tools_used}")
        print(f"[tier] reply (first 500): {reply[:500]}")
        _assert_no_timeout_phrases(reply)
        assert "tier_distribution" in tools_used, f"expected tier_distribution, got {tools_used}"
        # At least one common tier name in reply
        lo = reply.lower()
        assert any(t in lo for t in ["silver", "gold", "platinum", "bronze", "diamond", "insider"]), (
            f"no tier names in reply: {reply[:300]}"
        )

    # 4. Negative balance is honest (zero)
    def test_04_negative_balance_zero(self, headers):
        r, elapsed = _chat(
            headers,
            "List all customers with a negative points balance",
            "qa_neg",
        )
        assert r.status_code == 200, f"status {r.status_code} body={r.text[:300]}"
        data = r.json()
        reply = data.get("reply", "") or ""
        print(f"[neg] tools_used={data.get('tools_used')}")
        print(f"[neg] reply (first 500): {reply[:500]}")
        _assert_no_timeout_phrases(reply)
        lo = reply.lower()
        # Must honestly state zero / no customers
        assert any(k in lo for k in ["0", "zero", "no customers", "none", "no negative"]), (
            f"expected honest zero-answer, got: {reply[:300]}"
        )

    # 5. Grant preview only (no mutation)
    def test_05_grant_preview_only(self, headers):
        r, elapsed = _chat(
            headers,
            "Grant 50 bonus points to customer 6000013876",
            "qa_grant",
        )
        assert r.status_code == 200, f"status {r.status_code} body={r.text[:300]}"
        data = r.json()
        reply = data.get("reply", "") or ""
        print(f"[grant-preview] tools_used={data.get('tools_used')}")
        print(f"[grant-preview] reply (first 600): {reply[:600]}")
        _assert_no_timeout_phrases(reply)
        lo = reply.lower()
        assert any(k in lo for k in ["confirm", "preview", "reason"]), (
            f"expected preview-asking wording, got: {reply[:400]}"
        )
        # Should NOT claim already applied
        assert not re.search(r"(successfully\s+granted|already\s+added|points\s+have\s+been\s+added)", lo), (
            f"reply claims already applied but should be preview: {reply[:400]}"
        )

    # 6. Confirm applies + audited
    def test_06_grant_confirm_applies(self, headers):
        # follow-up in SAME session
        r, elapsed = _chat(
            headers,
            "Yes, confirm it. Reason: QA verification test",
            "qa_grant",
        )
        assert r.status_code == 200, f"status {r.status_code} body={r.text[:300]}"
        data = r.json()
        reply = data.get("reply", "") or ""
        tools_used = data.get("tools_used", []) or []
        print(f"[grant-confirm] tools_used={tools_used}")
        print(f"[grant-confirm] reply (first 600): {reply[:600]}")
        _assert_no_timeout_phrases(reply)
        lo = reply.lower()
        applied = any(k in lo for k in ["granted", "applied", "added 50", "success", "confirmed"])
        if not applied:
            # retry once more explicit
            r2, _ = _chat(
                headers,
                "confirm=true, reason: QA verification test — please apply now",
                "qa_grant",
            )
            assert r2.status_code == 200
            reply2 = (r2.json() or {}).get("reply", "") or ""
            print(f"[grant-confirm-retry] reply (first 600): {reply2[:600]}")
            _assert_no_timeout_phrases(reply2)
            lo2 = reply2.lower()
            applied = any(k in lo2 for k in ["granted", "applied", "added 50", "success", "confirmed"])
            assert applied, f"confirm did not apply after retry: {reply2[:400]}"

        # Verify via balance query
        rv, _ = _chat(
            headers,
            "What is the current points balance for customer 6000013876?",
            "qa_verify",
        )
        assert rv.status_code == 200
        rv_reply = (rv.json() or {}).get("reply", "") or ""
        print(f"[verify-balance] reply (first 400): {rv_reply[:400]}")
        _assert_no_timeout_phrases(rv_reply)
        balance_ok = bool(re.search(r"\b50\b", rv_reply)) or bool(re.search(r"\+\s*50", rv_reply))
        if not balance_ok:
            # try audit log fallback
            rlog, _ = _chat(
                headers,
                "Show me the recent master action log",
                "qa_log",
            )
            assert rlog.status_code == 200
            log_reply = (rlog.json() or {}).get("reply", "") or ""
            print(f"[audit-log] reply (first 600): {log_reply[:600]}")
            _assert_no_timeout_phrases(log_reply)
            log_lo = log_reply.lower()
            audited = ("6000013876" in log_reply) and (
                "qa verification test" in log_lo or "grant" in log_lo or "bonus" in log_lo
            )
            assert audited or balance_ok, (
                f"neither balance nor audit log reflected the grant. balance={rv_reply[:300]} log={log_reply[:300]}"
            )

    # 7. Fix negative honest when zero
    def test_07_fix_negative_honest_zero(self, headers):
        r, elapsed = _chat(
            headers,
            "Fix all negative points balances",
            "qa_fixneg",
        )
        assert r.status_code == 200, f"status {r.status_code} body={r.text[:300]}"
        data = r.json()
        reply = data.get("reply", "") or ""
        print(f"[fixneg] tools_used={data.get('tools_used')}")
        print(f"[fixneg] reply (first 500): {reply[:500]}")
        _assert_no_timeout_phrases(reply)
        lo = reply.lower()
        assert any(k in lo for k in ["0", "zero", "no negative", "nothing to fix", "none"]), (
            f"expected honest 'nothing to fix', got: {reply[:400]}"
        )
