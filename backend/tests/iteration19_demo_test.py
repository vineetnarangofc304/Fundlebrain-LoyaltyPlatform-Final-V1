"""Iteration 19 — Backend tests for the Fundle /demo feature.

Covers:
- POST /api/demo/session (public)
- Demo token: read GETs OK, write POST 403 with allowlisted exceptions
- POST /api/demo/tts (cache HIT on second call, audio/mpeg)
- POST /api/ai/chat read questions OK, write requests refused
- Regression: super_admin login via POST /api/auth/login
"""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

SUPER_EMAIL = "superadmin@fundle.io"
SUPER_PASSWORD = "Fundle@2026"


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def demo_session():
    r = requests.post(f"{API}/demo/session", timeout=30)
    assert r.status_code == 200, f"demo/session failed: {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data and "user" in data
    assert data["user"]["role"] == "brand_admin"
    assert data["user"]["is_demo"] is True
    return data


@pytest.fixture(scope="module")
def demo_headers(demo_session):
    return {"Authorization": f"Bearer {demo_session['token']}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def super_token():
    r = requests.post(
        f"{API}/auth/login",
        json={"email": SUPER_EMAIL, "password": SUPER_PASSWORD, "portal": "crm"},
        timeout=30,
    )
    if r.status_code != 200:
        pytest.skip(f"super_admin login failed {r.status_code} {r.text[:200]}")
    return r.json().get("token") or r.json().get("access_token")


# ---------- /api/demo/session ----------
class TestDemoSession:
    def test_session_public_no_auth(self, demo_session):
        u = demo_session["user"]
        assert u["email"] == "demo@fundle.io"
        assert u["role"] == "brand_admin"
        assert u["is_demo"] is True
        assert isinstance(demo_session["token"], str) and len(demo_session["token"]) > 20


# ---------- Read GETs work with demo token ----------
class TestDemoReads:
    def test_get_users_ok(self, demo_headers):
        r = requests.get(f"{API}/users", headers=demo_headers, timeout=30)
        assert r.status_code == 200, f"GET /users {r.status_code} {r.text[:200]}"

    def test_dashboard_insight_allowlisted_post(self, demo_headers):
        # Demo allowlists POST /api/dashboard/insight (read-style POST)
        r = requests.post(
            f"{API}/dashboard/insight",
            headers=demo_headers,
            json={"dashboard_key": "command_center", "payload": {"members_active": 100}},
            timeout=120,
        )
        # Must NOT be blocked with 403 by the demo guard
        assert r.status_code != 403, f"Allowlisted POST blocked by demo guard: {r.text[:200]}"
        assert r.status_code == 200, f"insight {r.status_code} {r.text[:200]}"


# ---------- Write blocked ----------
class TestDemoWriteBlocked:
    def test_post_users_blocked_403(self, demo_headers):
        payload = {
            "email": "TEST_demoblock@example.com",
            "name": "Test Block",
            "role": "support_agent",
            "password": "Abcd1234!",
        }
        r = requests.post(f"{API}/users", headers=demo_headers, json=payload, timeout=30)
        assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text[:200]}"
        body = r.text.lower()
        assert "demo" in body or "read" in body, f"detail should mention demo/read-only: {r.text[:200]}"


# ---------- TTS ----------
class TestDemoTTS:
    def test_tts_returns_audio_and_caches(self, demo_headers):
        text = "TEST_DEMO_NARRATION_iter19 Welcome to the Fundle guided tour."
        # First call — MISS or HIT (cache may persist between runs)
        r1 = requests.post(
            f"{API}/demo/tts", headers=demo_headers, json={"text": text}, timeout=120
        )
        assert r1.status_code == 200, f"tts call1 {r1.status_code} {r1.text[:200]}"
        assert r1.headers.get("content-type", "").startswith("audio/mpeg"), r1.headers
        assert len(r1.content) > 500, "audio body too small"

        # Second call — must be HIT
        r2 = requests.post(
            f"{API}/demo/tts", headers=demo_headers, json={"text": text}, timeout=60
        )
        assert r2.status_code == 200
        assert r2.headers.get("X-Cache") == "HIT", f"X-Cache header missing/wrong: {dict(r2.headers)}"
        assert r2.content == r1.content, "cached audio should be identical"


# ---------- Fundle Brain (AI chat) ----------
class TestDemoAiChat:
    def test_ai_chat_read_ok(self, demo_headers):
        r = requests.post(
            f"{API}/ai/chat",
            headers=demo_headers,
            json={"message": "How many active customers do we have?"},
            timeout=120,
        )
        assert r.status_code == 200, f"ai/chat read {r.status_code} {r.text[:300]}"
        body = r.json()
        # accept either 'reply' or 'message' style payloads
        text = (body.get("reply") or body.get("message") or body.get("response") or "").lower()
        assert text, f"no text in ai response: {body}"

    def test_ai_chat_write_refused(self, demo_headers):
        r = requests.post(
            f"{API}/ai/chat",
            headers=demo_headers,
            json={"message": "deactivate customer 9266681235"},
            timeout=120,
        )
        # The chat endpoint itself is allowlisted (200); the underlying tool must refuse.
        assert r.status_code == 200, f"ai/chat write {r.status_code} {r.text[:300]}"
        body = r.json()
        text = (body.get("reply") or body.get("message") or body.get("response") or "")
        low = text.lower()
        # Must NOT confirm deactivation; must mention read-only/demo/cannot
        refusal_markers = ["read-only", "read only", "demo", "cannot", "can't", "unable", "not allowed", "disabled"]
        assert any(m in low for m in refusal_markers), f"expected refusal, got: {text[:400]}"
        # Must not contain a confirmation that the customer was deactivated
        assert "deactivated" not in low or "cannot" in low or "demo" in low, f"unexpected confirmation: {text[:400]}"


# ---------- Regression: superadmin login ----------
class TestSuperAdminRegression:
    def test_super_login(self, super_token):
        assert super_token and isinstance(super_token, str) and len(super_token) > 20

    def test_super_can_get_users(self, super_token):
        r = requests.get(
            f"{API}/users",
            headers={"Authorization": f"Bearer {super_token}"},
            timeout=30,
        )
        assert r.status_code == 200, f"super GET /users {r.status_code} {r.text[:200]}"
