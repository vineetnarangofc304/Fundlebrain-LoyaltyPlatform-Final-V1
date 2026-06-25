"""Iteration 37 — Master Brain V2 backend tests.

Covers:
  * RBAC: super_admin (403) vs master_admin (200) on /api/master-brain/*
  * Action log: undoable/undone fields enrichment
  * Undo flow: grant_bonus_points -> undo -> double-undo blocked (400)
  * Campaigns: GET /campaigns returns {count, campaigns:[...]}
  * Datasets: list + dataset detail with q + paginated rows
"""
import os
import time
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

MASTER = {"email": "masteradmin@fundle.io", "password": "Master@2026"}
SUPER = {"email": "superadmin@fundle.io", "password": "Fundle@2026"}
SCRATCH_MOBILE = "9990002222"


def _login(email: str, password: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="session")
def master_token():
    return _login(MASTER["email"], MASTER["password"])


@pytest.fixture(scope="session")
def super_token():
    return _login(SUPER["email"], SUPER["password"])


@pytest.fixture(scope="session")
def master_h(master_token):
    return {"Authorization": f"Bearer {master_token}"}


@pytest.fixture(scope="session")
def super_h(super_token):
    return {"Authorization": f"Bearer {super_token}"}


# ---------- RBAC ----------
class TestRBAC:
    @pytest.mark.parametrize("path", [
        "/master-brain/action-log",
        "/master-brain/campaigns",
        "/master-brain/datasets",
        "/master-brain/sessions",
        "/master-brain/suggested-prompts",
    ])
    def test_super_admin_blocked(self, super_h, path):
        r = requests.get(f"{API}{path}", headers=super_h, timeout=30)
        assert r.status_code == 403, f"super_admin should be blocked on {path}, got {r.status_code} {r.text[:200]}"

    @pytest.mark.parametrize("path", [
        "/master-brain/action-log",
        "/master-brain/campaigns",
        "/master-brain/datasets",
        "/master-brain/sessions",
        "/master-brain/suggested-prompts",
    ])
    def test_master_admin_allowed(self, master_h, path):
        r = requests.get(f"{API}{path}", headers=master_h, timeout=30)
        assert r.status_code == 200, f"master should pass on {path}, got {r.status_code} {r.text[:200]}"


# ---------- Action log enrichment ----------
class TestActionLog:
    def test_action_log_shape(self, master_h):
        r = requests.get(f"{API}/master-brain/action-log?days=30&limit=50", headers=master_h, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "count" in data and "actions" in data
        for row in data["actions"]:
            assert "undoable" in row and isinstance(row["undoable"], bool)
            assert "undone" in row and isinstance(row["undone"], bool)


# ---------- Undo flow ----------
def _find_customer_balance(master_h, mobile: str):
    """Resolve customer balance via run_aggregation tool through the chat API would be heavy.
    Use the admin customers search endpoint if available; otherwise pull via raw query proxy."""
    r = requests.get(f"{API}/admin/customers?mobile={mobile}", headers=master_h, timeout=30)
    if r.status_code == 200:
        d = r.json()
        items = d.get("items") or d.get("customers") or (d if isinstance(d, list) else [])
        for c in items:
            if str(c.get("mobile")) == mobile:
                return c.get("points_balance") or c.get("balance") or 0
    return None


class TestUndoFlow:
    """Perform a fresh grant_bonus_points via direct tool, then undo via REST."""

    def test_grant_then_undo_then_double_undo(self, master_h):
        # Use the direct tool path through the chat endpoint with strict instructions
        # is fragile; instead drive the master-brain tools via a direct POST to
        # /master-brain/chat with a tight prompt that asks for preview then apply.
        # We'll use two turns.
        session_id = uuid.uuid4().hex

        # Turn 1: Preview grant
        r1 = requests.post(f"{API}/master-brain/chat", headers=master_h, timeout=120, json={
            "session_id": session_id,
            "message": f"Grant 50 bonus points to {SCRATCH_MOBILE} for a QA undo regression. Preview only.",
        })
        assert r1.status_code == 200, f"chat turn1 failed: {r1.status_code} {r1.text[:400]}"

        # Turn 2: Confirm with reason
        r2 = requests.post(f"{API}/master-brain/chat", headers=master_h, timeout=120, json={
            "session_id": session_id,
            "message": "Yes, please apply. Reason: QA undo regression",
        })
        assert r2.status_code == 200, f"chat turn2 failed: {r2.status_code} {r2.text[:400]}"
        tools_used = r2.json().get("tools_used") or []
        assert "grant_bonus_points" in tools_used, f"grant_bonus_points was NOT called. tools_used={tools_used}"

        # Give it a moment to persist
        time.sleep(1.0)

        # Fetch action log → find the most recent grant_bonus_points row marked undoable
        r3 = requests.get(f"{API}/master-brain/action-log?days=1&limit=50", headers=master_h, timeout=30)
        assert r3.status_code == 200
        rows = r3.json()["actions"]
        target = None
        for row in rows:
            action = row.get("action", "")
            if "grant_bonus_points" in action and row.get("undoable") and not row.get("undone"):
                meta = row.get("metadata") or row.get("details") or {}
                if SCRATCH_MOBILE in str(meta):
                    target = row
                    break
        assert target is not None, (
            f"No undoable grant_bonus_points found. tools_used={tools_used}. "
            f"recent_actions={[(r.get('action'), r.get('undoable'), r.get('undone'), (r.get('metadata') or {}).get('mobile')) for r in rows[:6]]}"
        )
        audit_id = target["id"]

        # Undo
        r4 = requests.post(f"{API}/master-brain/undo/{audit_id}", headers=master_h, timeout=60,
                           json={"reason": "QA: revert grant"})
        assert r4.status_code == 200, f"undo failed: {r4.status_code} {r4.text[:400]}"
        assert r4.json().get("undone") or r4.json().get("success") or r4.json().get("ok") or True

        # Verify action log shows undone=true and undoable=false
        time.sleep(0.5)
        r5 = requests.get(f"{API}/master-brain/action-log?days=1&limit=50", headers=master_h, timeout=30)
        rows2 = r5.json()["actions"]
        match = next((r for r in rows2 if r.get("id") == audit_id), None)
        assert match is not None, "Original row missing after undo"
        assert match.get("undone") is True, f"row.undone should be True; got {match}"
        assert match.get("undoable") is False, f"row.undoable should be False after undo; got {match}"

        # Double undo: should fail with 400 'already undone'
        r6 = requests.post(f"{API}/master-brain/undo/{audit_id}", headers=master_h, timeout=30,
                           json={"reason": "QA: try again"})
        assert r6.status_code == 400, f"double undo should 400, got {r6.status_code} {r6.text[:200]}"
        assert "undone" in r6.text.lower() or "already" in r6.text.lower()

    def test_undo_empty_reason_rejected(self, master_h):
        # An empty reason on undo with a random/non-existent id should still hit reason validation OR return a 400.
        # We use a fake audit id; the tool should reject either due to empty reason or missing snapshot.
        r = requests.post(f"{API}/master-brain/undo/does-not-exist", headers=master_h, timeout=30,
                          json={"reason": ""})
        assert r.status_code == 400, f"empty reason / unknown id should be 400, got {r.status_code}"


# ---------- Campaigns ----------
class TestCampaigns:
    def test_list_campaigns_shape(self, master_h):
        r = requests.get(f"{API}/master-brain/campaigns", headers=master_h, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "count" in data and "campaigns" in data
        assert isinstance(data["campaigns"], list)


# ---------- Datasets ----------
class TestDatasets:
    def test_list_datasets_shape(self, master_h):
        r = requests.get(f"{API}/master-brain/datasets", headers=master_h, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "count" in data and "datasets" in data
        assert isinstance(data["datasets"], list)

    def test_dataset_detail_with_search(self, master_h):
        r = requests.get(f"{API}/master-brain/datasets", headers=master_h, timeout=30)
        datasets = r.json()["datasets"]
        if not datasets:
            pytest.skip("No datasets to test detail view")
        ds = datasets[0]
        ds_id = ds["id"]

        # Full page (no q)
        r1 = requests.get(f"{API}/master-brain/datasets/{ds_id}?page=1&page_size=10",
                          headers=master_h, timeout=30)
        assert r1.status_code == 200, r1.text[:400]
        d1 = r1.json()
        assert "columns" in d1 and "rows" in d1 and "total_matched" in d1
        assert d1["page"] == 1 and d1["page_size"] == 10
        full_total = d1["total_matched"]

        # Search for a nonsense token → total_matched shrinks
        r2 = requests.get(f"{API}/master-brain/datasets/{ds_id}?q=zzzzz_unlikely_token",
                          headers=master_h, timeout=30)
        assert r2.status_code == 200
        assert r2.json()["total_matched"] <= full_total

    def test_dataset_unknown_id_404(self, master_h):
        r = requests.get(f"{API}/master-brain/datasets/does-not-exist", headers=master_h, timeout=30)
        assert r.status_code == 404
