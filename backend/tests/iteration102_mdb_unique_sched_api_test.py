"""Iteration 102 — HTTP-level API tests for:
  * Marketing Database (create/list/detail/customers/member filter/delete)
  * Unique coupons (allocate/list/detail/export/delete)
  * Campaign scheduling (create scheduled + unschedule + delete)
  * Provider config bulk (campaign) SMS pipe
"""
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def creds():
    p = Path("/app/memory/test_credentials.md")
    if not p.exists():
        pytest.skip("missing credentials file")
    t = p.read_text(encoding="utf-8")
    e = re.search(r"(?im)^\s*[-*]?\s*Email:\s*`([^`]+)`", t)
    pw = re.search(r"(?im)^\s*[-*]?\s*Password:\s*`([^`]+)`", t)
    if not e or not pw:
        pytest.skip("creds not parseable")
    return {"email": e.group(1), "password": pw.group(1)}


@pytest.fixture(scope="session")
def client(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": creds["email"],
                                          "password": creds["password"], "portal": "crm"}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("token")
    assert tok, "no token in login response"
    assert "kazo_token" in r.cookies, "httpOnly cookie kazo_token not set on login"
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def non_member_mobiles(client):
    """Two 10-digit mobiles guaranteed NOT to exist in the loyalty base.
    (90000008xx are already seeded as 'Perf Customer' records, so probe first.)"""
    import random
    found = []
    for _ in range(25):
        batch = ["9" + "".join(random.choices("0123456789", k=9)) for _ in range(20)]
        r = client.post(f"{API}/marketing-db", json={"name": "TEST_probe", "mobiles": batch}, timeout=90)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        rows = client.get(f"{API}/marketing-db/{d['id']}/customers?member=false&page_size=50",
                          timeout=90).json()["rows"]
        client.delete(f"{API}/marketing-db/{d['id']}", timeout=60)
        found += [x["mobile"] for x in rows]
        if len(found) >= 2:
            break
    assert len(found) >= 2, "could not find 2 non-member probe mobiles"
    return found[:2]


@pytest.fixture(scope="session")
def real_mobile(client):
    r = client.get(f"{API}/customers?limit=1", timeout=90)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    rows = data.get("customers") or data.get("rows") or data.get("items") or (data if isinstance(data, list) else [])
    assert rows, f"no customers returned: {str(data)[:300]}"
    m = rows[0].get("mobile")
    assert m, "customer has no mobile"
    return m


# ───────────────────────── Marketing Database ─────────────────────────
class TestMarketingDb:
    mdb_id = None

    def test_create_dedupes_and_counts_members(self, client, real_mobile, non_member_mobiles):
        a, b = non_member_mobiles
        body = {"name": "TEST_QA Marketing DB", "description": "qa",
                "mobiles_text": f"{real_mobile}, {a}, {b}, {a}"}
        r = client.post(f"{API}/marketing-db", json=body, timeout=120)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        TestMarketingDb.mdb_id = d["id"]
        assert d["total"] == 3, f"dedupe failed: {d}"
        assert d["member_count"] == 1, f"member count wrong: {d}"
        assert d["non_member_count"] == 2, f"non-member count wrong: {d}"
        assert d["member_count"] + d["non_member_count"] == d["total"]
        assert "_id" not in d and "mobiles" not in d

    def test_create_rejects_empty(self, client):
        r = client.post(f"{API}/marketing-db", json={"name": "TEST_bad", "mobiles_text": "abc"}, timeout=60)
        assert r.status_code == 400, r.status_code

    def test_list_contains_dataset(self, client):
        r = client.get(f"{API}/marketing-db", timeout=60)
        assert r.status_code == 200, r.text[:300]
        rows = r.json()["rows"]
        assert any(x["id"] == TestMarketingDb.mdb_id for x in rows)

    def test_detail(self, client):
        r = client.get(f"{API}/marketing-db/{TestMarketingDb.mdb_id}", timeout=60)
        assert r.status_code == 200
        assert r.json()["total"] == 3

    def test_customers_rows_have_is_member(self, client, real_mobile):
        r = client.get(f"{API}/marketing-db/{TestMarketingDb.mdb_id}/customers?page=1&page_size=50", timeout=90)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["total"] == 3 and len(d["rows"]) == 3
        assert all("is_member" in row for row in d["rows"])
        hit = [x for x in d["rows"] if x["mobile"] == real_mobile]
        assert hit and hit[0]["is_member"] is True, d["rows"]

    def test_customers_member_false_filter(self, client, real_mobile):
        r = client.get(f"{API}/marketing-db/{TestMarketingDb.mdb_id}/customers?member=false", timeout=90)
        assert r.status_code == 200
        rows = r.json()["rows"]
        assert rows and all(x["is_member"] is False for x in rows)
        assert real_mobile not in [x["mobile"] for x in rows]

    def test_customers_member_true_filter(self, client, real_mobile):
        r = client.get(f"{API}/marketing-db/{TestMarketingDb.mdb_id}/customers?member=true", timeout=90)
        assert r.status_code == 200
        rows = r.json()["rows"]
        assert real_mobile in [x["mobile"] for x in rows]

    def test_recompute(self, client):
        r = client.post(f"{API}/marketing-db/{TestMarketingDb.mdb_id}/recompute", timeout=90)
        assert r.status_code == 200 and r.json()["ok"] is True

    def test_404_unknown(self, client):
        r = client.get(f"{API}/marketing-db/doesnotexist123", timeout=60)
        assert r.status_code == 404

    def test_zz_delete_and_verify(self, client):
        r = client.delete(f"{API}/marketing-db/{TestMarketingDb.mdb_id}", timeout=60)
        assert r.status_code == 200
        assert client.get(f"{API}/marketing-db/{TestMarketingDb.mdb_id}", timeout=60).status_code == 404


# ───────────────────────── Unique coupons ─────────────────────────
class TestUniqueCoupons:
    batch_id = None
    mobiles = []

    def test_allocate(self, client, non_member_mobiles):
        TestUniqueCoupons.mobiles = sorted(non_member_mobiles)
        body = {"name": "TEST_QA Uniq", "coupon_type": "flat", "discount_value": 100,
                "min_bill_amount": 500, "valid_from": "2026-01-01T00:00:00Z",
                "valid_to": "2026-12-31T00:00:00Z", "prefix": "KAZO",
                "audience": {"source": "mobiles", "mobiles": list(non_member_mobiles)}}
        r = client.post(f"{API}/coupons/unique/allocate", json=body, timeout=120)
        assert r.status_code == 200, r.text[:400]
        b = r.json()
        TestUniqueCoupons.batch_id = b["id"]
        assert b["total"] == 2, b
        assert b["prefix"] == "KAZO" and b["redeemed"] == 0
        assert "_id" not in b

    def test_allocate_empty_audience_rejected(self, client):
        body = {"name": "TEST_bad", "discount_value": 10, "valid_from": "2026-01-01T00:00:00Z",
                "valid_to": "2026-12-31T00:00:00Z",
                "audience": {"source": "mobiles", "mobiles": ["123"]}}
        r = client.post(f"{API}/coupons/unique/allocate", json=body, timeout=60)
        assert r.status_code == 400, r.status_code

    def test_list_batches(self, client):
        r = client.get(f"{API}/coupons/unique/batches", timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert any(x["id"] == TestUniqueCoupons.batch_id for x in r.json()["rows"])

    def test_batch_detail_codes_bound_to_mobiles(self, client):
        r = client.get(f"{API}/coupons/unique/batches/{TestUniqueCoupons.batch_id}", timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["total"] == 2 and d["redeemed"] == 0 and d["allocated"] == 2
        mobiles = sorted(x["mobile"] for x in d["rows"])
        assert mobiles == TestUniqueCoupons.mobiles, mobiles
        assert all(x["status"] == "allocated" for x in d["rows"])
        codes = {x["code"] for x in d["rows"]}
        assert len(codes) == 2 and all(c.startswith("KAZO") for c in codes)

    def test_export_csv(self, client):
        r = client.get(f"{API}/coupons/unique/batches/{TestUniqueCoupons.batch_id}/export", timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert "csv" in r.headers.get("content-type", "")
        lines = r.text.strip().splitlines()
        assert lines[0].startswith("code,mobile,status")
        assert len(lines) == 3, lines

    def test_404_unknown_batch(self, client):
        r = client.get(f"{API}/coupons/unique/batches/nope123", timeout=60)
        assert r.status_code == 404

    def test_zz_delete_batch(self, client):
        r = client.delete(f"{API}/coupons/unique/batches/{TestUniqueCoupons.batch_id}", timeout=60)
        assert r.status_code == 200
        assert client.get(f"{API}/coupons/unique/batches/{TestUniqueCoupons.batch_id}",
                          timeout=60).status_code == 404


# ───────────────────────── Campaign scheduling ─────────────────────────
class TestScheduling:
    camp_id = None

    def test_create_scheduled_campaign(self, client):
        future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        body = {"name": "TEST_QA Sched", "channels": ["sms"], "audience_type": "city",
                "audience_filter": {"city": "Mumbai"}, "status": "scheduled", "schedule_at": future}
        r = client.post(f"{API}/campaigns", json=body, timeout=90)
        assert r.status_code == 200, r.text[:400]
        c = r.json()
        TestScheduling.camp_id = c["id"]
        assert c["status"] == "scheduled"
        assert c.get("schedule_at"), c
        assert not c.get("template_id"), "must be simulated (no template)"

    def test_scheduled_visible_in_list(self, client):
        r = client.get(f"{API}/campaigns?status=scheduled", timeout=90)
        assert r.status_code == 200
        assert any(x["id"] == TestScheduling.camp_id for x in r.json())

    def test_unschedule_reverts_to_draft(self, client):
        r = client.post(f"{API}/campaigns/{TestScheduling.camp_id}/unschedule", timeout=60)
        assert r.status_code == 200, r.text[:300]
        g = client.get(f"{API}/campaigns/{TestScheduling.camp_id}", timeout=60)
        assert g.status_code == 200
        d = g.json()
        camp = d.get("campaign", d)
        assert camp["status"] == "draft", camp
        assert not camp.get("schedule_at"), "schedule_at should be unset"

    def test_unschedule_non_scheduled_rejected(self, client):
        r = client.post(f"{API}/campaigns/{TestScheduling.camp_id}/unschedule", timeout=60)
        assert r.status_code == 400, r.status_code

    def test_zz_delete_campaign(self, client):
        r = client.delete(f"{API}/campaigns/{TestScheduling.camp_id}", timeout=60)
        assert r.status_code == 200
        assert client.get(f"{API}/campaigns/{TestScheduling.camp_id}", timeout=60).status_code == 404


# ───────────────────────── Provider config (bulk pipe) ─────────────────────────
class TestProviderConfig:
    def test_campaign_pipe_config(self, client):
        r = client.get(f"{API}/provider-config", timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("sms_campaign_account") == "fundle_campaign", d.get("sms_campaign_account")
        assert d.get("sms_campaign_sender_id") == "KAZOFN", d.get("sms_campaign_sender_id")
        assert "JsonReceiver" in (d.get("sms_campaign_endpoint") or ""), d.get("sms_campaign_endpoint")
        key = d.get("sms_campaign_api_key") or ""
        assert "\u2022" in key or "*" in key, f"campaign api key not masked: {key}"
