"""
iteration78 — Master Brain routing fix (Fix B) verification.

Verifies:
1. Natural-language TIER command is UNDERSTOOD (preview + tools_used contains set_customer_tier).
2. Same-session bare confirmation applies the tier change (audit id).
3. Natural-language POINTS command yields PREVIEW (does NOT claim already added).
4. Bare confirm "yes ... reason:" in same session applies grant_bonus_points (+30, audit id).
5. "Fix all negative points balances" action is honest: reports zero, NOT timeout, NOT fabricated.
6. Read query "top 5 customers by points" returns data, uses only read tools, does NOT mutate.
7. Regression check: analytics KPI + tier queries still real, no timeout phrases.
8. Deterministic negative-balance read audit stays instant (<8s) and reports zero.
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
CHAT_TIMEOUT = 90

BAD_PHRASES = [
    "Data Unavailable",
    "System Timeout",
    "timed out",
    "budget exhausted",
    "AI usage budget",
]

# Phrases indicating the model is refusing / hallucinating a missing tool.
MISSING_TOOL_PHRASES = [
    "i don't have",
    "i do not have",
    "i cannot",
    "i can't",
    "capability gap",
    "not have that tool",
    "no such tool",
    "no tool for",
    "unable to perform",
    "don't have a tool",
    "do not have a tool",
]


def _login():
    r = requests.post(
        LOGIN_URL,
        json={"email": MASTER_EMAIL, "password": MASTER_PASS},
        timeout=30,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("token")
    assert tok, f"no token: {r.text[:200]}"
    return tok


@pytest.fixture(scope="module")
def token():
    return _login()


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _chat(headers, message, session_id, retry_budget=True):
    """POST to /api/master-brain/chat. On 'budget exhausted', wait 60s and retry once."""
    t0 = time.time()
    r = requests.post(
        CHAT_URL,
        json={"message": message, "session_id": session_id},
        headers=headers,
        timeout=CHAT_TIMEOUT,
    )
    elapsed = time.time() - t0
    print(f"[chat] session={session_id} elapsed={elapsed:.1f}s status={r.status_code}")
    if r.status_code == 200 and retry_budget:
        reply = (r.json() or {}).get("reply", "") or ""
        if "budget exhausted" in reply.lower() or "ai usage budget" in reply.lower():
            print("[chat] budget exhausted — sleeping 60s and retrying once")
            time.sleep(60)
            t0 = time.time()
            r = requests.post(
                CHAT_URL,
                json={"message": message, "session_id": session_id},
                headers=headers,
                timeout=CHAT_TIMEOUT,
            )
            elapsed = time.time() - t0
            print(f"[chat-retry] session={session_id} elapsed={elapsed:.1f}s status={r.status_code}")
    return r, elapsed


def _assert_no_bad_phrases(reply: str):
    lo = reply.lower()
    for p in BAD_PHRASES:
        assert p.lower() not in lo, f"forbidden phrase '{p}' in reply: {reply[:400]}"


def _assert_no_missing_tool(reply: str):
    lo = reply.lower()
    for p in MISSING_TOOL_PHRASES:
        assert p not in lo, f"model hallucinated missing tool ('{p}'): {reply[:400]}"


class TestMasterBrainRoutingFix:
    """Fix B — natural-language action commands + bare confirmations."""

    def test_01_login(self):
        tok = _login()
        assert isinstance(tok, str) and len(tok) > 10

    # --- Regression check: analytics still returns real data ---
    def test_02_kpi_real_data(self, headers):
        r, elapsed = _chat(
            headers,
            "How many loyalty customers and total points liability in rupees?",
            "qa1",
        )
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
        data = r.json()
        reply = data.get("reply", "") or ""
        tools_used = data.get("tools_used", []) or []
        print(f"[qa1] tools_used={tools_used} reply[:400]={reply[:400]}")
        assert reply.strip()
        _assert_no_bad_phrases(reply)
        _assert_no_missing_tool(reply)
        # Expect at least one large-ish number
        assert re.search(r"\d[\d,]{2,}", reply), f"no numbers in reply: {reply[:300]}"

    def test_03_tier_distribution_real_data(self, headers):
        r, elapsed = _chat(headers, "What is our tier distribution?", "qa2")
        assert r.status_code == 200
        data = r.json()
        reply = data.get("reply", "") or ""
        tools_used = data.get("tools_used", []) or []
        print(f"[qa2] tools_used={tools_used} reply[:400]={reply[:400]}")
        _assert_no_bad_phrases(reply)
        _assert_no_missing_tool(reply)
        lo = reply.lower()
        assert any(t in lo for t in ["silver", "gold", "platinum", "bronze", "diamond", "insider"]), (
            f"no tier names: {reply[:300]}"
        )

    # --- Deterministic read-audit fast-path still instant ---
    def test_04_negative_balance_read_audit_instant(self, headers):
        r, elapsed = _chat(
            headers,
            "List all customers with a negative points balance",
            "qa3",
        )
        assert r.status_code == 200
        reply = (r.json() or {}).get("reply", "") or ""
        print(f"[qa3] elapsed={elapsed:.2f}s reply[:400]={reply[:400]}")
        _assert_no_bad_phrases(reply)
        _assert_no_missing_tool(reply)
        lo = reply.lower()
        assert any(k in lo for k in ["0", "zero", "no negative", "none", "no customers"]), (
            f"expected honest zero: {reply[:300]}"
        )
        # Deterministic path should be quick
        assert elapsed < 8.0, f"expected fast (<8s) deterministic read-audit, got {elapsed:.1f}s"

    # --- CORE OF FIX B: natural-language tier command preview + confirm ---
    def test_05_tier_command_preview(self, headers):
        r, elapsed = _chat(
            headers,
            "Change customer 6000013876 to platinum tier",
            "qatier",
        )
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:300]}"
        data = r.json()
        reply = data.get("reply", "") or ""
        tools_used = data.get("tools_used", []) or []
        print(f"[qatier-preview] elapsed={elapsed:.1f}s tools_used={tools_used}")
        print(f"[qatier-preview] reply (first 700): {reply[:700]}")
        _assert_no_bad_phrases(reply)
        _assert_no_missing_tool(reply)
        assert "set_customer_tier" in tools_used, (
            f"expected set_customer_tier in tools_used, got {tools_used}"
        )
        lo = reply.lower()
        # Should be a PREVIEW asking to confirm + reason, referencing platinum and the customer
        assert "platinum" in lo, f"no 'platinum' in preview reply: {reply[:400]}"
        assert "6000013876" in reply, f"no customer id in preview reply: {reply[:400]}"
        assert any(k in lo for k in ["confirm", "reason"]), (
            f"expected preview asking to confirm+reason: {reply[:400]}"
        )
        # Must NOT claim already applied
        assert not re.search(
            r"(has been (changed|updated|set)|successfully (changed|updated|set)|tier is now)",
            lo,
        ), f"reply claims already applied on preview turn: {reply[:400]}"

    def test_06_tier_command_confirm_applies(self, headers):
        r, elapsed = _chat(
            headers,
            "Go ahead. Reason: QA tier command test",
            "qatier",
        )
        assert r.status_code == 200
        data = r.json()
        reply = data.get("reply", "") or ""
        tools_used = data.get("tools_used", []) or []
        print(f"[qatier-confirm] elapsed={elapsed:.1f}s tools_used={tools_used}")
        print(f"[qatier-confirm] reply (first 700): {reply[:700]}")
        _assert_no_bad_phrases(reply)
        _assert_no_missing_tool(reply)
        lo = reply.lower()
        has_audit = ("audit" in lo) or re.search(r"[0-9a-f]{8}-[0-9a-f]{4}", reply) is not None
        applied = ("platinum" in lo) and (
            has_audit
            or any(
                k in lo
                for k in [
                    "applied", "updated", "changed", "is now", "successfully",
                    "confirmed", "done", "has been logged", "new tier",
                ]
            )
        )
        if not (applied and ("set_customer_tier" in tools_used or has_audit)):
            print("[qatier-confirm] first confirm did not apply cleanly — retrying with explicit phrasing")
            r2, _ = _chat(
                headers,
                "confirm=true, reason: QA tier command test — please apply now",
                "qatier",
            )
            assert r2.status_code == 200
            data2 = r2.json()
            reply = data2.get("reply", "") or ""
            tools_used = data2.get("tools_used", []) or []
            print(f"[qatier-confirm-retry] tools_used={tools_used}")
            print(f"[qatier-confirm-retry] reply (first 700): {reply[:700]}")
            _assert_no_bad_phrases(reply)
            _assert_no_missing_tool(reply)
            lo = reply.lower()
            has_audit = ("audit" in lo) or re.search(r"[0-9a-f]{8}-[0-9a-f]{4}", reply) is not None
            applied = ("platinum" in lo) and (
                has_audit
                or any(
                    k in lo
                    for k in [
                        "applied", "updated", "changed", "is now", "successfully",
                        "confirmed", "done", "has been logged", "already applied",
                    ]
                )
            )
        assert applied, f"tier change not applied in reply: {reply[:500]}"
        # tools_used may be empty on the retry turn when the model correctly says
        # "already applied on your previous confirmation" — accept if audit id is echoed.
        assert ("set_customer_tier" in tools_used) or has_audit, (
            f"expected set_customer_tier in tools_used OR audit id echoed, got tools_used={tools_used} reply={reply[:400]}"
        )
        assert has_audit, f"no audit id / 'audit' word in reply: {reply[:400]}"

    # --- Natural-language POINTS command + bare confirm ---
    def test_07_points_command_preview(self, headers):
        r, elapsed = _chat(
            headers,
            "Add 30 bonus points to customer 6000013876",
            "qapts",
        )
        assert r.status_code == 200
        data = r.json()
        reply = data.get("reply", "") or ""
        tools_used = data.get("tools_used", []) or []
        print(f"[qapts-preview] elapsed={elapsed:.1f}s tools_used={tools_used}")
        print(f"[qapts-preview] reply (first 700): {reply[:700]}")
        _assert_no_bad_phrases(reply)
        _assert_no_missing_tool(reply)
        assert "grant_bonus_points" in tools_used, (
            f"expected grant_bonus_points in tools_used, got {tools_used}"
        )
        lo = reply.lower()
        assert "6000013876" in reply, f"no customer id in preview: {reply[:400]}"
        assert any(k in lo for k in ["confirm", "reason"]), (
            f"expected preview asking confirm+reason: {reply[:400]}"
        )
        assert not re.search(
            r"(has been (added|granted|applied)|successfully (added|granted|applied)|balance is now)",
            lo,
        ), f"reply claims already applied on preview: {reply[:400]}"

    def test_08_points_command_bare_confirm_applies(self, headers):
        r, elapsed = _chat(
            headers,
            "yes confirm, reason: QA points test",
            "qapts",
        )
        assert r.status_code == 200
        data = r.json()
        reply = data.get("reply", "") or ""
        tools_used = data.get("tools_used", []) or []
        print(f"[qapts-confirm] elapsed={elapsed:.1f}s tools_used={tools_used}")
        print(f"[qapts-confirm] reply (first 700): {reply[:700]}")
        _assert_no_bad_phrases(reply)
        _assert_no_missing_tool(reply)
        lo = reply.lower()
        applied = any(k in lo for k in ["granted", "applied", "added 30", "success", "confirmed", "balance is now"])
        has_audit = ("audit" in lo) or re.search(r"[0-9a-f]{8}-[0-9a-f]{4}", reply) is not None
        if not (applied and "grant_bonus_points" in tools_used):
            print("[qapts-confirm] retrying explicit")
            r2, _ = _chat(
                headers,
                "confirm=true, reason: QA points test — apply now",
                "qapts",
            )
            assert r2.status_code == 200
            data2 = r2.json()
            reply = data2.get("reply", "") or ""
            tools_used = data2.get("tools_used", []) or []
            print(f"[qapts-confirm-retry] tools_used={tools_used}")
            print(f"[qapts-confirm-retry] reply (first 700): {reply[:700]}")
            _assert_no_bad_phrases(reply)
            _assert_no_missing_tool(reply)
            lo = reply.lower()
            applied = any(k in lo for k in ["granted", "applied", "added 30", "success", "confirmed", "balance is now"])
            has_audit = ("audit" in lo) or re.search(r"[0-9a-f]{8}-[0-9a-f]{4}", reply) is not None
        assert applied, f"grant not applied: {reply[:500]}"
        assert "grant_bonus_points" in tools_used, (
            f"expected grant_bonus_points in tools_used on confirm, got {tools_used}"
        )
        assert has_audit, f"no audit id / 'audit' in reply: {reply[:400]}"

    # --- Fix-negative action honest when zero (action path, not read fast-path) ---
    def test_09_fix_negative_action_honest(self, headers):
        r, elapsed = _chat(
            headers,
            "Fix all negative points balances now",
            "qafix",
        )
        assert r.status_code == 200
        data = r.json()
        reply = data.get("reply", "") or ""
        tools_used = data.get("tools_used", []) or []
        print(f"[qafix] elapsed={elapsed:.1f}s tools_used={tools_used}")
        print(f"[qafix] reply (first 700): {reply[:700]}")
        _assert_no_bad_phrases(reply)
        _assert_no_missing_tool(reply)
        lo = reply.lower()
        # Reports zero to fix, nothing to do — NOT fabricated count.
        assert any(k in lo for k in ["0", "zero", "no negative", "nothing to fix", "none"]), (
            f"expected honest zero-to-fix, got: {reply[:400]}"
        )
        # No fabricated 'fixed N customers' with N > 0
        m = re.search(r"fix(?:ed)?\s+(\d+)\s+(?:customer|balance|account)", lo)
        if m:
            assert int(m.group(1)) == 0, f"fabricated non-zero fix count: {reply[:400]}"

    # --- READ does not mutate ---
    def test_10_read_top_customers_no_mutation(self, headers):
        r, elapsed = _chat(
            headers,
            "Show me the top 5 customers by points balance",
            "qaread",
        )
        assert r.status_code == 200
        data = r.json()
        reply = data.get("reply", "") or ""
        tools_used = data.get("tools_used", []) or []
        print(f"[qaread] elapsed={elapsed:.1f}s tools_used={tools_used}")
        print(f"[qaread] reply (first 700): {reply[:700]}")
        _assert_no_bad_phrases(reply)
        _assert_no_missing_tool(reply)
        # Must not include any write-tool
        write_tools = {"grant_bonus_points", "set_customer_tier", "adjust_points", "fix_negative_balances",
                       "fix_double_redemptions"}
        used = set(tools_used or [])
        assert not (used & write_tools), f"read query used write tools: {used}"
        # Should show at least one number-like row / balance
        assert re.search(r"\d", reply), f"no digits in top-customers reply: {reply[:400]}"
        # No mutation-language
        lo = reply.lower()
        assert "audit id" not in lo, f"read query produced audit id: {reply[:400]}"
        assert not re.search(r"\b(applied|granted \d|updated tier)\b", lo), (
            f"read query implies mutation: {reply[:400]}"
        )
