"""Iteration 11 — P1+P2 features:
- Auto-campaigns rules CRUD/preview/run
- Campaign launch (simulated path; karix needs template)
- Items + points_ledger schemas
- Points ledger CSV ingest + AI narrative
"""
import io
import os
import time
import uuid
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://kazo-campaign-engine.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

SUPERADMIN = {"email": "superadmin@fundle.io", "password": "Fundle@2026"}


def _login():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=SUPERADMIN, timeout=20)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"No token in response: {r.json()}"
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# ============================================================
# AUTO-CAMPAIGNS
# ============================================================
def test_auto_campaigns_list_rules():
    s = _login()
    r = s.get(f"{API}/auto-campaigns/rules", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    rules = data["rules"]
    keys = {x["key"] for x in rules}
    expected = {"birthday_today", "birthday_7d", "anniversary_today",
                "winback_60d", "winback_180d", "abandoned_visit_30d"}
    assert expected.issubset(keys), f"Missing rules: {expected - keys}"
    sample = rules[0]
    for f in ("default_enabled", "cooldown_days", "daily_cap"):
        assert f in sample, f"Missing field '{f}' on rule: {sample}"


def test_auto_campaigns_patch_rule_persists():
    s = _login()
    # Create a template to link
    tname = f"TEST_auto_tpl_{uuid.uuid4().hex[:6]}"
    tr = s.post(f"{API}/templates", json={
        "name": tname, "channel": "sms", "body": "Hi {name}!",
        "status": "active", "category": "promo"
    }, timeout=15)
    assert tr.status_code in (200, 201), tr.text
    tpl_id = tr.json()["id"]

    # PATCH rule to enabled + link template
    pr = s.patch(f"{API}/auto-campaigns/rules/birthday_today",
                 json={"enabled": True, "template_id": tpl_id, "daily_cap": 50},
                 timeout=15)
    assert pr.status_code == 200, pr.text
    body = pr.json()
    assert body["enabled"] is True
    assert body["template_id"] == tpl_id
    assert body["daily_cap"] == 50

    # Verify persisted via GET
    gr = s.get(f"{API}/auto-campaigns/rules", timeout=15)
    rule = next(x for x in gr.json()["rules"] if x["key"] == "birthday_today")
    assert rule["enabled"] is True
    assert rule["template_id"] == tpl_id
    assert rule["daily_cap"] == 50


def test_auto_campaigns_preview():
    s = _login()
    r = s.post(f"{API}/auto-campaigns/rules/birthday_today/preview", timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    for f in ("audience_total", "fireable_now", "on_cooldown", "samples"):
        assert f in d, f"Missing field '{f}'"
    assert isinstance(d["samples"], list)


def test_auto_campaigns_dry_run_single():
    s = _login()
    r = s.post(f"{API}/auto-campaigns/rules/birthday_today/run?dry_run=true", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    # Must include dry_run=true and counters
    assert d.get("dry_run") is True or d.get("skipped") == "no_template"
    # If template is linked it should include 'fired' counter
    if "fired" in d:
        assert isinstance(d["fired"], int)


def test_auto_campaigns_run_all_dry():
    s = _login()
    r = s.post(f"{API}/auto-campaigns/run-all?dry_run=true", timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "rules" in d
    assert "total_fired" in d
    assert len(d["rules"]) == 6


def test_auto_campaigns_log():
    s = _login()
    r = s.get(f"{API}/auto-campaigns/log", timeout=15)
    assert r.status_code == 200, r.text
    assert "rows" in r.json()


# ============================================================
# CAMPAIGN LAUNCH (simulated path — no template_id)
# ============================================================
def test_campaign_launch_simulated_mode():
    s = _login()
    # Create a campaign with no template_id (legacy simulated)
    cr = s.post(f"{API}/campaigns", json={
        "name": f"TEST_sim_{uuid.uuid4().hex[:6]}",
        "channels": ["sms"], "channel": "sms",
        "audience_type": "tier",
        "audience_filter": {"tier": "silver"},
        "message": "hi", "status": "draft"
    }, timeout=15)
    assert cr.status_code in (200, 201), cr.text
    cid = cr.json()["id"]

    lr = s.post(f"{API}/campaigns/{cid}/launch", timeout=30)
    assert lr.status_code == 200, lr.text
    d = lr.json()
    assert d.get("mode") == "simulated", f"Expected simulated, got {d}"
    assert "sent" in d


def test_campaign_launch_karix_mode_with_template():
    s = _login()
    # Create active SMS template
    tr = s.post(f"{API}/templates", json={
        "name": f"TEST_karix_{uuid.uuid4().hex[:6]}",
        "channel": "sms", "body": "Hi {name}!",
        "status": "active", "category": "promo"
    }, timeout=15)
    assert tr.status_code in (200, 201), tr.text
    tpl_id = tr.json()["id"]

    cr = s.post(f"{API}/campaigns", json={
        "name": f"TEST_kx_{uuid.uuid4().hex[:6]}",
        "channels": ["sms"], "channel": "sms",
        "audience_type": "tier",
        "audience_filter": {"tier": "silver"},
        "message": "hi", "status": "draft",
        "template_id": tpl_id, "send_limit": 5
    }, timeout=15)
    assert cr.status_code in (200, 201), cr.text
    cid = cr.json()["id"]

    lr = s.post(f"{API}/campaigns/{cid}/launch", timeout=30)
    assert lr.status_code == 200, lr.text
    d = lr.json()
    assert d.get("mode") == "karix", f"Expected karix mode, got {d}"
    bjid = d.get("bulk_job_id")
    assert bjid, f"Missing bulk_job_id: {d}"

    # Verify bulk job exists
    time.sleep(1)
    jr = s.get(f"{API}/communications/bulk-jobs/{bjid}", timeout=15)
    assert jr.status_code == 200, jr.text
    jd = jr.json()
    assert jd.get("campaign_id") == cid
    assert jd.get("channel") == "sms"
    assert "status" in jd


# ============================================================
# SCHEMAS
# ============================================================
def test_items_schema():
    s = _login()
    r = s.get(f"{API}/historic-data/schema/items", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    cols = set(d["recognised_columns"])
    must = {"SKU", "Item Code", "Style Code", "Article", "MRP", "Color", "Size", "Brand", "HSN"}
    assert must.issubset(cols), f"Missing cols: {must - cols}"
    assert len(cols) >= 21, f"Expected 21+ cols, got {len(cols)}"


def test_points_ledger_schema():
    s = _login()
    r = s.get(f"{API}/historic-data/schema/points_ledger", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["required_columns"] == ["Mobile", "Points"]
    sample = d["sample_row"]
    for f in ("Type", "Date", "Bill Number", "Reason"):
        assert f in sample


# ============================================================
# POINTS LEDGER INGEST + AI NARRATIVE
# ============================================================
def test_points_ledger_ingest_and_narrative():
    s = _login()
    csv_body = (
        "Mobile,Type,Points,Date,Bill Number,Reason\n"
        "9876501234,earn,500,01-04-2026,TESTBILL_A,Bill earn test\n"
        "9876501234,redeem,200,02-04-2026,TESTBILL_B,Burn test\n"
        "9876501235,bonus,100,03-04-2026,TESTBILL_C,Bonus test\n"
    )
    files = {"file": ("test_ledger.csv", csv_body, "text/csv")}
    data = {"dataset": "points_ledger", "duplicate_mode": "upsert", "dry_run": "false"}
    r = s.post(f"{API}/historic-data/ingest", files=files, data=data, timeout=30)
    assert r.status_code == 200, r.text
    job_id = r.json()["id"]
    assert job_id

    # Poll for completion (narrative gen may take 30s+ for LLM call)
    done = False
    for _ in range(60):
        gr = s.get(f"{API}/historic-data/jobs/{job_id}", timeout=30)
        assert gr.status_code == 200
        st = gr.json().get("status")
        if st in ("completed", "previewed", "failed"):
            done = True
            assert st == "completed", f"Job ended with status={st}: {gr.json()}"
            break
        time.sleep(2)
    assert done, "Job did not complete within 120s"

    # POST narrative regeneration
    nr = s.post(f"{API}/historic-data/jobs/{job_id}/narrative", timeout=60)
    assert nr.status_code == 200, nr.text
    n = nr.json()
    assert n.get("source") in ("fundle_brain_gpt5", "template_fallback"), n
    assert "snapshot" in n
    snap = n["snapshot"]
    for f in ("customers_loyalty", "transactions_loyalty", "loyalty_net_sales",
              "points_outstanding", "tier_mix"):
        assert f in snap, f"Missing snapshot field '{f}'"
    assert len(n["narrative"]) > 100, f"Narrative too short: {len(n['narrative'])}"

    # GET narrative
    gr = s.get(f"{API}/historic-data/jobs/{job_id}/narrative", timeout=15)
    assert gr.status_code == 200
    assert gr.json()["source"] in ("fundle_brain_gpt5", "template_fallback")
