"""Iteration 103 — P0 fixes on Campaign Manager + Communications Templates.

Bug 1: GET /api/templates returns {rows,total} -> wizard dropdown source has active SMS templates
Bug 2: Marketing-DB campaigns send to ALL numbers (members + non-members)
Bug 3: Templates test-send routes promotional (campaign_bulk) SMS via the bulk 'campaign' pipe
Regression: audience-preview for 'all' / needs_filter guard / simulated launch
"""
import os
import re
import time
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
if not BASE:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
API = f"{BASE}/api"

FAKE_A = "9990001111"
FAKE_B = "9990003333"
FAKE_C = "9990004444"
FAKE_TEST_SEND = "9999999999"
MEMBER_FAKE = "9990002222"   # scratch test customer already in the loyalty base


@pytest.fixture(scope="session")
def creds():
    p = Path("/app/memory/test_credentials.md")
    if not p.exists():
        pytest.skip("missing test_credentials.md")
    c = p.read_text(encoding="utf-8")
    e = re.search(r"(?im)^-\s*Email:\s*`([^`]+)`", c)
    pw = re.search(r"(?im)^-\s*Password:\s*`([^`]+)`", c)
    if not e or not pw:
        pytest.skip("no creds parsed")
    return {"email": e.group(1), "password": pw.group(1)}


@pytest.fixture(scope="session")
def client(creds):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", json={"email": creds["email"], "password": creds["password"]},
               timeout=60)
    if r.status_code != 200:
        pytest.fail(f"login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token in login response: {r.json().keys()}"
    s.headers.update({"Authorization": f"Bearer {tok}"})
    # httpOnly cookie check (playbook)
    assert any(c.name == "kazo_token" for c in r.cookies), f"cookies: {r.cookies.keys()}"
    return s


# ── shared state across ordered tests ──
STATE = {}


# ═════════════ Bug 1 — templates list shape ═════════════
class TestBug1TemplatesListShape:
    def test_templates_envelope(self, client):
        r = client.get(f"{API}/templates", timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert isinstance(d, dict) and "rows" in d and "total" in d, f"bad shape: {type(d)}"
        assert isinstance(d["rows"], list)
        assert d["total"] == len(d["rows"])
        for row in d["rows"]:
            assert "_id" not in row

    def test_active_sms_templates_exist(self, client):
        r = client.get(f"{API}/templates", params={"channel": "sms"}, timeout=60)
        assert r.status_code == 200
        rows = r.json()["rows"]
        active = [t for t in rows if t.get("status") == "active"]
        assert len(active) > 0, "no active SMS templates -> wizard dropdown would be empty"
        STATE["active_sms"] = active
        bulk = [t for t in active if t.get("event_trigger") == "campaign_bulk"]
        STATE["bulk_tpl"] = bulk[0] if bulk else None
        print(f"active sms={len(active)} campaign_bulk active={len(bulk)}")


# ═════════════ Bug 3 — test-send pipe routing ═════════════
class TestBug3TestSendRouting:
    def test_campaign_bulk_template_autoroutes_campaign(self, client):
        t = STATE.get("bulk_tpl")
        if not t:
            # create one (TEST_ prefixed) so the assertion is still meaningful
            r = client.post(f"{API}/templates", json={
                "name": "TEST_bulk_i103", "channel": "sms", "event_trigger": "campaign_bulk",
                "body": "TEST promo {{name}}", "status": "active"}, timeout=60)
            assert r.status_code == 200, r.text[:300]
            t = r.json()
            STATE["created_tpl_id"] = t["id"]
            STATE["bulk_tpl"] = t
        r = client.post(f"{API}/templates/{t['id']}/test-send",
                        json={"mobile": FAKE_TEST_SEND, "params": {"name": "QA"}}, timeout=120)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("pipe") == "campaign", f"expected pipe=campaign got {d}"
        assert d.get("ok") is True, f"send not ok: {d}"

    def test_forced_via_campaign_on_transactional_template(self, client):
        r = client.get(f"{API}/templates", params={"channel": "sms"}, timeout=60)
        txn = [t for t in r.json()["rows"]
               if t.get("status") == "active" and t.get("event_trigger") != "campaign_bulk"]
        if not txn:
            pytest.skip("no active transactional sms template")
        t = txn[0]
        STATE["txn_tpl"] = t
        r2 = client.post(f"{API}/templates/{t['id']}/test-send",
                         json={"mobile": FAKE_TEST_SEND, "via": "campaign"}, timeout=120)
        assert r2.status_code == 200, r2.text[:300]
        d = r2.json()
        assert d.get("pipe") == "campaign", f"forced via=campaign ignored: {d}"
        assert d.get("ok") is True, d

    def test_purchase_template_defaults_transactional(self, client):
        r = client.get(f"{API}/templates", params={"channel": "sms", "event_trigger": "purchase"},
                       timeout=60)
        rows = [t for t in r.json()["rows"] if t.get("status") == "active"]
        if not rows:
            pytest.skip("no active purchase sms template")
        r2 = client.post(f"{API}/templates/{rows[0]['id']}/test-send",
                         json={"mobile": FAKE_TEST_SEND}, timeout=120)
        assert r2.status_code == 200, r2.text[:300]
        d = r2.json()
        assert d.get("pipe") == "transactional", f"expected transactional got {d}"

    def test_invalid_template_404(self, client):
        r = client.post(f"{API}/templates/nope_i103/test-send",
                        json={"mobile": FAKE_TEST_SEND}, timeout=60)
        assert r.status_code == 404


# ═════════════ Bug 2 — Marketing DB sends to ALL ═════════════
class TestBug2MarketingDbAll:
    def test_create_marketing_db(self, client):
        # 1 scratch MEMBER (fake number already in the base) + 3 fake non-members. We deliberately
        # avoid real customer mobiles because the launch fires REAL Karix SMS.
        r = client.get(f"{API}/customers", params={"q": MEMBER_FAKE, "limit": 2}, timeout=90)
        members = []
        if r.status_code == 200:
            items = r.json().get("items") or []
            members = [c["mobile"] for c in items if c.get("mobile") == MEMBER_FAKE]
        assert members, f"scratch member {MEMBER_FAKE} not found in base — member personalisation " \
                        f"leg of Bug 2 cannot be verified"
        mobiles = members + [FAKE_A, FAKE_B, FAKE_C]
        r = client.post(f"{API}/marketing-db", json={
            "name": "TEST_I103_MDB", "description": "QA iteration 103",
            "mobiles": mobiles}, timeout=120)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert "_id" not in d
        STATE["mdb"] = d
        STATE["mdb_expected"] = len(set(mobiles))
        print(f"mdb total={d.get('total')} members={d.get('member_count')} "
              f"non_members={d.get('non_member_count')}")
        assert d["total"] == len(set(mobiles))
        assert d["non_member_count"] >= 3
        assert d["member_count"] >= 1, "scratch member not counted as member"

    def test_audience_preview_counts_all(self, client):
        mdb = STATE["mdb"]
        r = client.post(f"{API}/campaigns/audience-preview", json={
            "audience_type": "marketing_db",
            "audience_filter": {"marketing_db_id": mdb["id"]}}, timeout=90)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["total_audience"] == STATE["mdb_expected"], \
            f"expected {STATE['mdb_expected']} got {d['total_audience']} (non-members dropped?)"
        nm = [s for s in d["sample"] if s.get("tier") == "non-member"]
        assert nm, f"no non-member flagged in sample: {d['sample']}"
        mem = [s for s in d["sample"] if s.get("mobile") == MEMBER_FAKE]
        assert mem and mem[0].get("tier") != "non-member", f"member mis-flagged: {mem}"
        assert d.get("non_member_count") is not None

    def test_audience_preview_missing_mdb_id(self, client):
        r = client.post(f"{API}/campaigns/audience-preview",
                        json={"audience_type": "marketing_db", "audience_filter": {}}, timeout=60)
        assert r.status_code == 200
        assert r.json().get("needs_filter") is True
        assert r.json().get("total_audience") == 0

    def test_launch_sends_to_all(self, client):
        tpl = STATE.get("bulk_tpl")
        assert tpl, "no campaign_bulk template available"
        mdb = STATE["mdb"]
        r = client.post(f"{API}/campaigns", json={
            "name": "TEST_I103_LAUNCH", "channels": ["sms"], "audience_type": "marketing_db",
            "audience_filter": {"marketing_db_id": mdb["id"]},
            "template_id": tpl["id"], "message_template": "", "send_limit": 20}, timeout=90)
        assert r.status_code == 200, r.text[:400]
        camp = r.json()
        STATE["campaign_id"] = camp["id"]
        r2 = client.post(f"{API}/campaigns/{camp['id']}/launch", timeout=180)
        assert r2.status_code == 200, r2.text[:400]
        d = r2.json()
        print("launch:", d)
        assert d.get("audience") == STATE["mdb_expected"], \
            f"launch audience {d.get('audience')} != {STATE['mdb_expected']}"
        job_id = d.get("bulk_job_id") or d.get("job_id")
        assert job_id, f"no bulk_job_id in launch response: {d}"
        STATE["job_id"] = job_id

    def test_bulk_job_processed_all(self, client):
        job_id = STATE.get("job_id")
        assert job_id
        job = None
        for _ in range(30):
            r = client.get(f"{API}/communications/bulk-jobs/{job_id}", timeout=60)
            assert r.status_code == 200, r.text[:300]
            job = r.json()
            if job.get("status") in ("completed", "failed"):
                break
            time.sleep(4)
        print("job:", {k: job.get(k) for k in
                       ("status", "processed", "sent", "failed", "audience_size_total", "error")})
        assert job.get("status") == "completed", f"job not completed: {job}"
        assert job.get("processed") == STATE["mdb_expected"], \
            f"processed {job.get('processed')} != {STATE['mdb_expected']}"
        assert job.get("failed") == 0, f"failed={job.get('failed')}"
        assert job.get("sent") == STATE["mdb_expected"]

    def test_non_member_got_campaign_pipe_sms(self, client):
        r = client.get(f"{API}/message-log", params={"mobile": FAKE_A, "limit": 20}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        rows = data.get("rows") if isinstance(data, dict) else data
        assert rows, f"no message log rows for non-member {FAKE_A}"
        recent = rows[0]
        print("msglog:", {k: recent.get(k) for k in
                          ("channel", "status", "event_trigger", "payload_summary", "created_at")})
        ps = recent.get("payload_summary") or {}
        assert ps.get("pipe") == "campaign", f"pipe != campaign: {ps}"
        assert ps.get("account") == "fundle_campaign", f"account != fundle_campaign: {ps}"
        assert recent.get("status") == "ok", f"send status: {recent.get('status')}"

    def test_campaign_delivery_endpoint(self, client):
        cid = STATE.get("campaign_id")
        r = client.get(f"{API}/campaigns/{cid}/delivery", timeout=90)
        assert r.status_code == 200, r.text[:300]
        print("delivery:", str(r.json())[:400])


# ═════════════ Regression ═════════════
class TestRegression:
    def test_preview_all(self, client):
        r = client.post(f"{API}/campaigns/audience-preview",
                        json={"audience_type": "all", "audience_filter": {}}, timeout=120)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["total_audience"] > 100, d["total_audience"]
        assert len(d["sample"]) > 0

    @pytest.mark.parametrize("at", ["tier", "city", "cohort", "segment"])
    def test_needs_filter_guard(self, client, at):
        r = client.post(f"{API}/campaigns/audience-preview",
                        json={"audience_type": at, "audience_filter": {}}, timeout=90)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("needs_filter") is True and d.get("total_audience") == 0, d

    def test_simulated_launch_no_template(self, client):
        # pick a tier that actually exists in this base (tier names are config-driven)
        rc = client.get(f"{API}/customers", params={"limit": 1}, timeout=120)
        tier = ((rc.json().get("items") or [{}])[0] or {}).get("tier") if rc.status_code == 200 else None
        assert tier, "could not resolve a live tier name from /api/customers"
        r = client.post(f"{API}/campaigns", json={
            "name": "TEST_I103_SIM", "channels": ["sms"], "audience_type": "tier",
            "audience_filter": {"tier": tier}, "message_template": "Hi {{name}}",
            "send_limit": 10}, timeout=90)
        assert r.status_code == 200, r.text[:300]
        cid = r.json()["id"]
        STATE["sim_campaign_id"] = cid
        r2 = client.post(f"{API}/campaigns/{cid}/launch", timeout=180)
        assert r2.status_code == 200, r2.text[:400]
        d = r2.json()
        print("sim launch:", d)
        assert d.get("send_mode") in (None, "simulated") or "sent" in d
        r3 = client.get(f"{API}/campaigns/{cid}", timeout=60)
        assert r3.status_code == 200
        c = r3.json()
        assert c["status"] in ("running", "completed")
        assert c.get("sent", 0) > 0, f"simulated metrics not generated: {c}"

    def test_double_launch_rejected(self, client):
        cid = STATE.get("sim_campaign_id")
        r = client.post(f"{API}/campaigns/{cid}/launch", timeout=90)
        assert r.status_code == 400, r.status_code


# ═════════════ Auth playbook checks ═════════════
class TestAuthPlaybook:
    def test_bad_password_401(self, creds):
        s = requests.Session()
        r = s.post(f"{API}/auth/login",
                   json={"email": creds["email"], "password": "definitely-wrong-i103"}, timeout=60)
        assert r.status_code in (401, 423, 429), r.status_code

    def test_unauthenticated_blocked(self):
        r = requests.get(f"{API}/campaigns", timeout=60)
        assert r.status_code in (401, 403), r.status_code


# ═════════════ Cleanup ═════════════
def test_zz_cleanup(client):
    for cid in (STATE.get("campaign_id"), STATE.get("sim_campaign_id")):
        if cid:
            client.delete(f"{API}/campaigns/{cid}", timeout=60)
    if STATE.get("created_tpl_id"):
        client.delete(f"{API}/templates/{STATE['created_tpl_id']}", timeout=60)
    print("cleanup done (marketing db TEST_I103_MDB left for inspection)")
