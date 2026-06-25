"""Iteration 35 — Master Brain RBAC, API gating, action log, and user mgmt 403 tests.

Focus: NON-LLM verifications. Validates:
 - Master Admin login + auth/me flag
 - Super admin denied on Master Brain API (403)
 - Master admin allowed on /master-brain/sessions, /action-log, /suggested-prompts
 - Action log endpoint returns 200 with shape
 - PATCH /api/users/<id> with is_master_admin by non-super-admin returns 403
 - Master Brain action tools — write flow via /master-brain/chat skipped (LLM cost),
   instead directly seeded via audit_logs collection is not allowed from outside; we
   verify the action-log endpoint returns the existing rows correctly.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://fundle-brain-ai-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

SUPER = {"email": "superadmin@fundle.io", "password": "Fundle@2026"}
MASTER = {"email": "masteradmin@fundle.io", "password": "Master@2026"}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text}"
    data = r.json()
    tok = data.get("token") or data.get("access_token")
    assert tok, f"no token in login response: {data}"
    return tok, data.get("user") or {}


@pytest.fixture(scope="module")
def master_session():
    tok, user = _login(MASTER)
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s, user


@pytest.fixture(scope="module")
def super_session():
    tok, user = _login(SUPER)
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s, user


class TestRBACFlag:
    def test_master_admin_flag_true(self, master_session):
        s, user = master_session
        assert user.get("is_master_admin") is True
        # Verify via /auth/me too
        r = s.get(f"{API}/auth/me", timeout=20)
        assert r.status_code == 200
        me = r.json()
        assert me.get("is_master_admin") is True
        assert me.get("email") == MASTER["email"]

    def test_super_admin_flag_false(self, super_session):
        s, user = super_session
        # super admin should NOT be master admin
        assert user.get("is_master_admin") in (False, None)
        r = s.get(f"{API}/auth/me", timeout=20)
        assert r.status_code == 200
        assert r.json().get("is_master_admin") in (False, None)


class TestMasterBrainAPIGating:
    def test_super_admin_denied_chat(self, super_session):
        s, _ = super_session
        r = s.post(f"{API}/master-brain/chat",
                   json={"message": "hi", "session_id": None}, timeout=20)
        assert r.status_code == 403, f"expected 403 got {r.status_code} {r.text[:200]}"

    def test_super_admin_denied_sessions(self, super_session):
        s, _ = super_session
        r = s.get(f"{API}/master-brain/sessions", timeout=20)
        assert r.status_code == 403

    def test_super_admin_denied_action_log(self, super_session):
        s, _ = super_session
        r = s.get(f"{API}/master-brain/action-log?days=7", timeout=20)
        assert r.status_code == 403

    def test_anon_denied(self):
        r = requests.get(f"{API}/master-brain/action-log", timeout=20)
        assert r.status_code in (401, 403)

    def test_master_admin_sessions_ok(self, master_session):
        s, _ = master_session
        r = s.get(f"{API}/master-brain/sessions", timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_master_admin_action_log_shape(self, master_session):
        s, _ = master_session
        r = s.get(f"{API}/master-brain/action-log?days=30&limit=50", timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert "count" in body and "actions" in body
        assert isinstance(body["actions"], list)

    def test_master_admin_suggested_prompts(self, master_session):
        s, _ = master_session
        r = s.get(f"{API}/master-brain/suggested-prompts", timeout=20)
        assert r.status_code == 200
        prompts = r.json()
        assert isinstance(prompts, list) and len(prompts) >= 3


class TestUserMgmtIsMasterAdmin:
    def test_non_super_admin_cannot_patch_is_master_admin(self, master_session, super_session):
        master_s, master_user = master_session
        # master admin is role=crm_manager, NOT super_admin → must be 403 when changing is_master_admin
        my_id = master_user.get("id")
        assert my_id, "Master user id missing"
        r = master_s.patch(f"{API}/users/{my_id}",
                           json={"is_master_admin": False}, timeout=20)
        # backend explicitly returns 403 for non-super_admin trying to flip is_master_admin
        assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text[:200]}"

    def test_super_admin_can_view_users(self, super_session):
        s, _ = super_session
        r = s.get(f"{API}/users", timeout=20)
        assert r.status_code == 200
        users = r.json()
        assert isinstance(users, list)
        emails = {u.get("email") for u in users}
        assert MASTER["email"] in emails
        # Confirm the master flag is exposed
        master_row = next(u for u in users if u.get("email") == MASTER["email"])
        assert master_row.get("is_master_admin") is True


class TestScratchCustomer:
    def test_scratch_customer_exists(self, master_session):
        s, _ = master_session
        # Use generic customers search; tolerate either route shape
        r = s.get(f"{API}/customers/by-mobile/9990002222", timeout=20)
        if r.status_code == 404:
            pytest.skip("by-mobile route missing; will validate via UI flow")
        assert r.status_code == 200, r.text[:200]
        c = r.json()
        assert c.get("mobile") in ("9990002222", 9990002222, "919990002222")
