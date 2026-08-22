"""Iteration 101 — Campaign Manager Phases 2/3/4 backend regression.

Covers:
  - POST /api/campaigns/audience-preview          (wizard live audience count)
  - Blacklist CRUD  (POST/GET/DELETE /api/campaigns/blacklist)
  - Auto-blacklist engine via GET /api/communications/dlr/karix (3 successive failures)
  - SIMULATED campaign lifecycle: create -> launch -> delivery -> roi -> cleanup
SAFETY: only SIMULATED campaigns (no template_id) are launched; throwaway mobiles only.
"""
import os
import time
import pytest
import requests


def _read_env(key):
    v = os.environ.get(key)
    if v:
        return v
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
    return None


BASE_URL = _read_env("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN_EMAIL = "superadmin@fundle.io"
ADMIN_PASSWORD = "Fundle@2026"

MANUAL_MOBILE = "9812345670"
AUTO_MOBILE = "9877000555"


@pytest.fixture(scope="module")
def auth():
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"no token in {r.json()}"
    return {"Authorization": f"Bearer {tok}"}


# ─────────────────────── Audience preview (wizard) ───────────────────────
def test_audience_preview_all(auth):
    r = requests.post(f"{API}/campaigns/audience-preview",
                      json={"audience_type": "all", "audience_filter": {}},
                      headers=auth, timeout=120)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert isinstance(d.get("total_audience"), int), d
    assert d["total_audience"] > 1000, f"expected large audience, got {d['total_audience']}"
    assert isinstance(d.get("sample"), list) and len(d["sample"]) > 0, d
    assert "blacklisted_total" in d and isinstance(d["blacklisted_total"], int), d
    for row in d["sample"]:
        assert "_id" not in row


def test_audience_preview_city_filter(auth):
    r = requests.post(f"{API}/campaigns/audience-preview",
                      json={"audience_type": "city", "audience_filter": {"city": "Mumbai"}},
                      headers=auth, timeout=120)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d["total_audience"] > 0, d
    # city filter must be narrower than "all"
    allr = requests.post(f"{API}/campaigns/audience-preview",
                         json={"audience_type": "all", "audience_filter": {}},
                         headers=auth, timeout=120).json()
    assert d["total_audience"] < allr["total_audience"], (d, allr["total_audience"])


# ─────────────────────── Blacklist CRUD ───────────────────────
def test_blacklist_crud(auth):
    # cleanup any leftovers
    requests.delete(f"{API}/campaigns/blacklist/{MANUAL_MOBILE}", headers=auth, timeout=30)

    r = requests.post(f"{API}/campaigns/blacklist",
                      json={"mobile": MANUAL_MOBILE, "reason": "qa"}, headers=auth, timeout=30)
    assert r.status_code == 200, r.text[:300]
    assert r.json().get("ok") is True

    r = requests.get(f"{API}/campaigns/blacklist", headers=auth, timeout=30)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    for k in ("total", "auto", "manual", "rows"):
        assert k in d, d
    assert d["total"] == d["auto"] + d["manual"]
    row = next((x for x in d["rows"] if x["mobile"] == MANUAL_MOBILE), None)
    assert row, f"{MANUAL_MOBILE} not in blacklist rows"
    assert row["source"] == "manual" and row["reason"] == "qa"
    assert "_id" not in row

    # search filter
    r = requests.get(f"{API}/campaigns/blacklist?q={MANUAL_MOBILE}", headers=auth, timeout=30)
    assert r.status_code == 200
    assert any(x["mobile"] == MANUAL_MOBILE for x in r.json()["rows"])

    r = requests.delete(f"{API}/campaigns/blacklist/{MANUAL_MOBILE}", headers=auth, timeout=30)
    assert r.status_code == 200, r.text[:300]
    assert r.json().get("removed") == 1, r.json()

    r = requests.get(f"{API}/campaigns/blacklist?q={MANUAL_MOBILE}", headers=auth, timeout=30)
    assert not any(x["mobile"] == MANUAL_MOBILE for x in r.json()["rows"])


def test_blacklist_invalid_mobile_rejected(auth):
    r = requests.post(f"{API}/campaigns/blacklist", json={"mobile": "123", "reason": "qa"},
                      headers=auth, timeout=30)
    assert r.status_code == 400, f"expected 400, got {r.status_code} {r.text[:200]}"


# ─────────────────────── Auto-blacklist engine (Phase 4) ───────────────────────
def test_auto_blacklist_after_three_failures(auth):
    # start clean (also resets the consecutive-failure counter)
    requests.delete(f"{API}/campaigns/blacklist/{AUTO_MOBILE}", headers=auth, timeout=30)
    try:
        results = []
        for i in range(3):
            r = requests.get(f"{API}/communications/dlr/karix",
                             params={"dest": AUTO_MOBILE, "status": "UNDELIV"}, timeout=30)
            assert r.status_code == 200, f"dlr #{i+1}: {r.status_code} {r.text[:200]}"
            results.append(r.json())
        assert results[0].get("auto_blacklisted") is False, results[0]
        assert results[1].get("auto_blacklisted") is False, results[1]
        assert results[2].get("auto_blacklisted") is True, results[2]

        r = requests.get(f"{API}/campaigns/blacklist?q={AUTO_MOBILE}", headers=auth, timeout=30)
        row = next((x for x in r.json()["rows"] if x["mobile"] == AUTO_MOBILE), None)
        assert row, f"auto-blacklisted mobile missing: {r.text[:300]}"
        assert row["source"] == "auto_dlr", row
    finally:
        requests.delete(f"{API}/campaigns/blacklist/{AUTO_MOBILE}", headers=auth, timeout=30)


def test_delivered_resets_failure_counter(auth):
    mob = "9877000556"
    requests.delete(f"{API}/campaigns/blacklist/{mob}", headers=auth, timeout=30)
    try:
        for _ in range(2):
            requests.get(f"{API}/communications/dlr/karix",
                         params={"dest": mob, "status": "UNDELIV"}, timeout=30)
        requests.get(f"{API}/communications/dlr/karix",
                     params={"dest": mob, "status": "DELIVRD"}, timeout=30)
        r = requests.get(f"{API}/communications/dlr/karix",
                         params={"dest": mob, "status": "UNDELIV"}, timeout=30)
        assert r.json().get("auto_blacklisted") is False, \
            f"counter not reset by delivered status: {r.json()}"
        bl = requests.get(f"{API}/campaigns/blacklist?q={mob}", headers=auth, timeout=30).json()
        assert not any(x["mobile"] == mob for x in bl["rows"]), bl
    finally:
        requests.delete(f"{API}/campaigns/blacklist/{mob}", headers=auth, timeout=30)


# ─────────────────────── SIMULATED campaign lifecycle ───────────────────────
@pytest.fixture(scope="module")
def sim_campaign(auth):
    payload = {
        "name": "TEST_QA_sim_campaign_i101",
        "channels": ["sms"],
        "audience_type": "city",
        "audience_filter": {"city": "Mumbai"},
        "objective": "generic",
        "roi_window": "7d",
        "send_limit": 100,
        "message_template": "hi",
        "cost": 500,
    }
    r = requests.post(f"{API}/campaigns", json=payload, headers=auth, timeout=60)
    assert r.status_code in (200, 201), f"create failed: {r.status_code} {r.text[:400]}"
    c = r.json()
    assert c.get("id"), c
    assert c.get("template_id") in (None, "", []), f"template linked! unsafe: {c}"
    yield c
    requests.delete(f"{API}/campaigns/{c['id']}", headers=auth, timeout=60)


def test_simulated_campaign_created_and_persisted(auth, sim_campaign):
    r = requests.get(f"{API}/campaigns/{sim_campaign['id']}", headers=auth, timeout=30)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d["name"] == "TEST_QA_sim_campaign_i101"
    assert d["channels"] == ["sms"]
    assert d["audience_filter"]["city"] == "Mumbai"
    assert d["status"] in ("draft", "scheduled"), d.get("status")
    assert "_id" not in d


def test_launch_simulated(auth, sim_campaign):
    r = requests.post(f"{API}/campaigns/{sim_campaign['id']}/launch", headers=auth, timeout=180)
    assert r.status_code == 200, r.text[:400]
    d = r.json()
    assert d.get("mode") == "simulated", f"UNSAFE / wrong mode: {d}"


def test_delivery_report(auth, sim_campaign):
    time.sleep(2)
    r = requests.get(f"{API}/campaigns/{sim_campaign['id']}/delivery", headers=auth, timeout=120)
    assert r.status_code == 200, r.text[:400]
    d = r.json()
    assert "total" in d and isinstance(d["total"], int), d
    assert "delivery_rate_pct" in d, d
    assert isinstance(d.get("webhook_url"), str) and "dlr/karix" in d["webhook_url"], d


def test_roi_report(auth, sim_campaign):
    r = requests.get(f"{API}/campaigns/{sim_campaign['id']}/roi?window=7d",
                     headers=auth, timeout=180)
    assert r.status_code == 200, r.text[:400]
    d = r.json()
    assert isinstance(d.get("dataset_size"), int) and d["dataset_size"] > 0, d
    uni = d.get("universal") or {}
    assert "converters" in uni, d
    assert "roi_pct" in uni, d


def test_campaign_appears_in_list(auth, sim_campaign):
    r = requests.get(f"{API}/campaigns", headers=auth, timeout=60)
    assert r.status_code == 200
    assert any(c["id"] == sim_campaign["id"] for c in r.json())
