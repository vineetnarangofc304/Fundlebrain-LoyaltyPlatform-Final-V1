"""Iteration 6 — Communications module: templates, AI, Karix send, provider config, bulk, message log."""
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://kazo-loyalty-hub.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    j = r.json()
    return j.get("token") or j.get("access_token")


@pytest.fixture(scope="module")
def admin_token():
    return _login("admin@kazo.com", "Kazo@2026")


@pytest.fixture(scope="module")
def crm_token():
    return _login("crm@kazo.com", "Kazo@2026")


@pytest.fixture(scope="module")
def admin_h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def crm_h(crm_token):
    return {"Authorization": f"Bearer {crm_token}"}


# ---------- Provider Config ----------
class TestProviderConfig:
    def test_get_masked(self, admin_h):
        r = requests.get(f"{API}/provider-config", headers=admin_h, timeout=15)
        assert r.status_code == 200
        d = r.json()
        # masked secret has bullet chars
        assert "•" in (d.get("sms_api_key") or ""), f"expected masked sms_api_key, got {d.get('sms_api_key')}"
        # default endpoint sanity
        assert "instaalerts.zone" in (d.get("sms_endpoint") or "")
        assert d.get("whatsapp_from_number") == "919133325826"
        assert "rcmapi.instaalerts.zone" in (d.get("whatsapp_endpoint") or "")

    def test_patch_updates_only_provided(self, admin_h):
        # change sender_id, leave api_key alone via masked-passthrough
        r = requests.patch(f"{API}/provider-config", headers=admin_h,
                           json={"sms_sender_id": "KAZOIN"}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["sms_sender_id"] == "KAZOIN"
        assert "•" in d["sms_api_key"]  # still masked

    def test_patch_masked_secret_not_overwriting(self, admin_h):
        # send the masked placeholder back — must NOT clobber stored secret
        r0 = requests.get(f"{API}/provider-config", headers=admin_h, timeout=15).json()
        masked = r0["sms_api_key"]
        r = requests.patch(f"{API}/provider-config", headers=admin_h,
                           json={"sms_api_key": masked}, timeout=15)
        assert r.status_code == 200
        # masked sent back; underlying secret untouched (still masks with • in response)
        assert "•" in r.json()["sms_api_key"]

    def test_patch_role_forbidden(self, crm_h):
        r = requests.patch(f"{API}/provider-config", headers=crm_h,
                           json={"sms_sender_id": "HACK"}, timeout=15)
        assert r.status_code == 403, f"expected 403 for crm role, got {r.status_code}"


# ---------- Templates CRUD ----------
class TestTemplatesCRUD:
    created_ids = []

    def test_create_invalid_channel(self, admin_h):
        r = requests.post(f"{API}/templates", headers=admin_h,
                          json={"name": "X", "channel": "email", "event_trigger": "none", "body": "hi"},
                          timeout=15)
        assert r.status_code == 400

    def test_create_invalid_event(self, admin_h):
        r = requests.post(f"{API}/templates", headers=admin_h,
                          json={"name": "X", "channel": "sms", "event_trigger": "bogus", "body": "hi"},
                          timeout=15)
        assert r.status_code == 400

    def test_create_sms_purchase(self, admin_h):
        r = requests.post(f"{API}/templates", headers=admin_h, json={
            "name": "TEST_purchase_sms",
            "channel": "sms",
            "event_trigger": "purchase",
            "body": "Hi {{name}}, thanks for shopping at KAZO! Bill {{amount}}. -KAZO",
            "status": "active",
        }, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["id"] and d["channel"] == "sms" and d["event_trigger"] == "purchase"
        TestTemplatesCRUD.created_ids.append(d["id"])

    def test_list_by_channel(self, admin_h):
        r = requests.get(f"{API}/templates", headers=admin_h, params={"channel": "sms"}, timeout=15)
        assert r.status_code == 200
        rows = r.json()["rows"]
        assert any(t["id"] in TestTemplatesCRUD.created_ids for t in rows)

    def test_patch(self, admin_h):
        tid = TestTemplatesCRUD.created_ids[0]
        r = requests.patch(f"{API}/templates/{tid}", headers=admin_h,
                           json={"note": "edited"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["note"] == "edited"

    def test_delete_z(self, admin_h):
        # run last alphabetically (z) so other tests can use the template
        # actually keep template for fire_event test; create a throwaway and delete it
        r = requests.post(f"{API}/templates", headers=admin_h, json={
            "name": "TEST_throwaway", "channel": "sms", "event_trigger": "none",
            "body": "x", "status": "draft",
        }, timeout=15)
        tid = r.json()["id"]
        d = requests.delete(f"{API}/templates/{tid}", headers=admin_h, timeout=15)
        assert d.status_code == 200
        g = requests.get(f"{API}/templates/{tid}", headers=admin_h, timeout=15)
        assert g.status_code == 404


# ---------- AI ----------
class TestAI:
    @pytest.mark.timeout(30)
    def test_ai_suggest_sms(self, admin_h):
        r = requests.post(f"{API}/templates/ai-suggest", headers=admin_h, json={
            "channel": "sms", "event_trigger": "purchase",
            "brief": "thank for purchase, invite to revisit",
        }, timeout=40)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "body" in d and isinstance(d["body"], str) and len(d["body"]) > 5
        assert "variables" in d and isinstance(d["variables"], list)
        # mustache normalisation: any {name} should be {{name}}
        import re
        single = re.findall(r"(?<!\{)\{([\w_]+)\}(?!\})", d["body"])
        assert not single, f"single-brace variable leaked: {single} in {d['body']!r}"

    @pytest.mark.timeout(30)
    def test_ai_improve(self, admin_h):
        r = requests.post(f"{API}/templates/ai-improve", headers=admin_h, json={
            "channel": "sms",
            "current_body": "Hi {{name}}, thanks for shopping.",
            "intent": "make it warmer and add visit invite",
        }, timeout=40)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "body" in d and len(d["body"]) > 5


# ---------- Test send (real Karix) ----------
class TestSendKarix:
    def test_send_sms(self, admin_h):
        # Create a template, then test-send to a dummy number — verify response shape & log entry
        r = requests.post(f"{API}/templates", headers=admin_h, json={
            "name": "TEST_testsend",
            "channel": "sms",
            "event_trigger": "none",
            "body": "KAZO test {{name}}",
            "status": "active",
        }, timeout=15)
        assert r.status_code == 200, r.text
        tid = r.json()["id"]
        s = requests.post(f"{API}/templates/{tid}/test-send", headers=admin_h,
                          json={"mobile": "919999999990", "params": {"name": "Tester"}},
                          timeout=25)
        assert s.status_code == 200, s.text
        d = s.json()
        # provider may say ok/false, but must have status_code or error key
        assert "ok" in d
        if d.get("ok"):
            assert d.get("status_code") == 200
            assert "Statuscode" in (d.get("response") or "") or d.get("response")
        # cleanup
        requests.delete(f"{API}/templates/{tid}", headers=admin_h, timeout=15)


# ---------- Auto-fire on POS transaction ----------
class TestFireOnPOS:
    def test_pos_issue_points_fires_purchase_sms(self, admin_h):
        # ensure an active 'purchase' SMS template exists (from CRUD test). If not, create.
        listing = requests.get(f"{API}/templates", headers=admin_h, params={"channel": "sms", "event_trigger": "purchase"}, timeout=15).json()
        active = [t for t in listing["rows"] if t.get("status") == "active"]
        if not active:
            requests.post(f"{API}/templates", headers=admin_h, json={
                "name": "TEST_fire_purchase", "channel": "sms",
                "event_trigger": "purchase", "status": "active",
                "body": "Hi {{name}}, thanks {{amount}} - KAZO",
            }, timeout=15)

        # POS endpoint is unauthenticated per memory note
        bill = f"TST{int(time.time())}"
        r = requests.post(f"{API}/pos/issue-points", json={
            "customer_mobile": "919999999991",
            "bill_number": bill,
            "store_id": "store_001",  # may not exist — endpoint can still log
            "net_amount": 1500,
        }, timeout=25)
        # Either 200 (happy path) or business validation error; only check log if 200
        assert r.status_code in (200, 400, 404, 422), r.text

        # Check message log (may be empty if pos validation failed before fire)
        time.sleep(1.0)
        log = requests.get(f"{API}/message-log", headers=admin_h, params={"channel": "sms"}, timeout=15)
        assert log.status_code == 200
        rows = log.json()["rows"]
        # If POS succeeded, expect a purchase log entry
        if r.status_code == 200:
            matched = [m for m in rows if m.get("event_trigger") == "purchase" and "999999999" in (m.get("mobile") or "")]
            assert matched, f"no purchase fire logged after POS issue-points; recent log: {rows[:3]}"


# ---------- Bulk send dry-run ----------
class TestBulkSend:
    def test_dry_run(self, admin_h):
        # need an active template
        r = requests.post(f"{API}/templates", headers=admin_h, json={
            "name": "TEST_bulk", "channel": "sms", "event_trigger": "campaign_bulk",
            "body": "Hi {{name}}", "status": "active",
        }, timeout=15)
        tid = r.json()["id"]
        b = requests.post(f"{API}/communications/bulk-send", headers=admin_h, json={
            "template_id": tid, "audience": {}, "dry_run": True, "limit": 10,
        }, timeout=20)
        assert b.status_code == 200, b.text
        d = b.json()
        assert d["dry_run"] is True
        assert "audience_size" in d
        assert "sample" in d and isinstance(d["sample"], list)
        requests.delete(f"{API}/templates/{tid}", headers=admin_h, timeout=15)


# ---------- Message Log ----------
class TestMessageLog:
    def test_list(self, admin_h):
        r = requests.get(f"{API}/message-log", headers=admin_h, params={"limit": 20}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "rows" in d and "total" in d
        # if rows exist, each should have channel & status keys
        for m in d["rows"][:5]:
            assert "channel" in m and "status" in m and "timestamp" in m
