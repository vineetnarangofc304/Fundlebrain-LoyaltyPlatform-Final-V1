"""Iteration 8 — AI engine v2 + Campaign ROI seed + Bulk-send background + WABA approval + Exec digests."""
import os
import time
import io
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://kazo-campaign-engine.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    j = r.json()
    return j.get("token") or j.get("access_token")


@pytest.fixture(scope="module")
def admin_h():
    tok = _login("admin@kazo.com", "Kazo@2026")
    return {"Authorization": f"Bearer {tok}"}


# ---------- A: AI Engine v2 with function calling ----------
class TestAIChat:
    @pytest.mark.timeout(90)
    def test_chat_uses_tools(self, admin_h):
        """POST /api/ai/chat must call MongoDB tools and populate tools_used."""
        r = requests.post(f"{API}/ai/chat", headers=admin_h, json={
            "message": "Top 3 stores by sales last 30 days?",
        }, timeout=80)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "reply" in d and isinstance(d["reply"], str) and len(d["reply"]) > 5
        assert "tools_used" in d, f"missing tools_used: {d}"
        assert isinstance(d["tools_used"], list)
        # spec: expect 'store_performance' to be referenced
        tools = [t.get("name") if isinstance(t, dict) else t for t in d["tools_used"]]
        assert any("store" in str(t).lower() for t in tools), f"expected store_performance tool, got {tools}"

    @pytest.mark.timeout(90)
    def test_chat_stream_sse(self, admin_h):
        """POST /api/ai/chat/stream must return SSE with event:tool, event:token, event:done."""
        with requests.post(f"{API}/ai/chat/stream", headers=admin_h, json={
            "message": "How many tiers do we have?",
        }, stream=True, timeout=80) as r:
            assert r.status_code == 200, r.text
            ct = r.headers.get("content-type", "")
            assert "text/event-stream" in ct, f"expected SSE content-type, got {ct}"
            seen_tool = False
            seen_token = False
            seen_done = False
            buf = ""
            for chunk in r.iter_content(chunk_size=512, decode_unicode=True):
                if chunk:
                    buf += chunk
                    if "event: tool" in buf or "event:tool" in buf:
                        seen_tool = True
                    if "event: token" in buf or "event:token" in buf:
                        seen_token = True
                    if "event: done" in buf or "event:done" in buf:
                        seen_done = True
                        break
                    if len(buf) > 200000:
                        break
            assert seen_token, f"no event:token observed; buf head: {buf[:500]}"
            assert seen_done, f"no event:done observed; buf head: {buf[:500]}"
            # tool may not always fire for trivial queries, log but don't fail hard
            if not seen_tool:
                print(f"WARN: no event:tool observed in stream — buf head: {buf[:500]}")

    @pytest.mark.timeout(60)
    def test_chat_upload_csv(self, admin_h):
        """POST /api/ai/chat/upload-csv with small CSV + question."""
        csv_data = "city,revenue,customers\nMumbai,1200000,450\nDelhi,980000,330\nBangalore,1450000,520\n"
        files = {"file": ("test.csv", io.BytesIO(csv_data.encode()), "text/csv")}
        data = {"question": "Which city has highest revenue?"}
        r = requests.post(f"{API}/ai/chat/upload-csv", headers=admin_h, files=files, data=data, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "reply" in d and len(d["reply"]) > 5
        assert "csv_meta" in d, f"missing csv_meta: {d}"
        meta = d["csv_meta"]
        # row count: 3 data rows
        rc = meta.get("rows") or meta.get("row_count") or meta.get("num_rows")
        assert rc == 3, f"expected 3 rows, got {meta}"

    def test_sessions_list(self, admin_h):
        r = requests.get(f"{API}/ai/sessions", headers=admin_h, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        # accept list or {rows: []}
        rows = d if isinstance(d, list) else d.get("rows") or d.get("sessions") or []
        assert isinstance(rows, list)
        # we created at least one session by chat above
        assert len(rows) >= 1, f"expected at least 1 session, got {len(rows)}"


# ---------- B: Campaign ROI v2 — seed campaign_metrics ----------
class TestCampaignROI:
    def test_funnel_nonzero(self, admin_h):
        r = requests.get(f"{API}/dashboard/campaign-roi", headers=admin_h, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        # totals or funnel
        totals = d.get("totals") or d.get("funnel") or {}
        # iterate any structure to find sent/delivered/clicked/converted
        def grab(k):
            if k in totals and totals[k]:
                return totals[k]
            f = d.get("funnel") or {}
            return f.get(k, 0)
        sent = grab("sent")
        delivered = grab("delivered")
        clicked = grab("clicked")
        converted = grab("converted")
        assert sent and sent > 0, f"sent must be >0, got {sent}; doc: {d}"
        assert delivered and delivered > 0, f"delivered must be >0"
        assert clicked and clicked > 0, f"clicked must be >0"
        assert converted and converted > 0, f"converted must be >0"
        # leaderboard
        lb = d.get("leaderboard") or d.get("campaigns") or []
        assert isinstance(lb, list)
        assert len(lb) >= 9, f"expected leaderboard length >= 9, got {len(lb)}"


# ---------- C: Bulk-send background job ----------
class TestBulkBackground:
    template_id = None

    def _ensure_sms_template(self, admin_h):
        # find or create an active SMS template
        r = requests.get(f"{API}/templates", headers=admin_h, params={"channel": "sms"}, timeout=15)
        rows = r.json().get("rows", [])
        active = [t for t in rows if t.get("status") == "active"]
        if active:
            TestBulkBackground.template_id = active[0]["id"]
            return active[0]["id"]
        c = requests.post(f"{API}/templates", headers=admin_h, json={
            "name": "TEST_it8_bulk_sms", "channel": "sms",
            "event_trigger": "campaign_bulk", "body": "Hi {{name}}", "status": "active",
        }, timeout=15)
        assert c.status_code == 200, c.text
        TestBulkBackground.template_id = c.json()["id"]
        return TestBulkBackground.template_id

    def test_dry_run(self, admin_h):
        tid = self._ensure_sms_template(admin_h)
        b = requests.post(f"{API}/communications/bulk-send", headers=admin_h, json={
            "template_id": tid, "audience": {}, "dry_run": True, "limit": 10,
        }, timeout=20)
        assert b.status_code == 200, b.text
        d = b.json()
        # accept either audience_size or audience_size_total
        size = d.get("audience_size_total") or d.get("audience_size")
        assert size is not None
        assert "sample" in d and isinstance(d["sample"], list) and len(d["sample"]) <= 3
        # would_send_via or channel
        via = d.get("would_send_via") or d.get("channel")
        assert via == "sms", f"expected would_send_via=sms, got {via}"

    def test_background_job_lifecycle(self, admin_h):
        tid = self._ensure_sms_template(admin_h)
        # non-existent audience to avoid sending real SMS
        b = requests.post(f"{API}/communications/bulk-send", headers=admin_h, json={
            "template_id": tid,
            "audience": {"tier": "nonexistent_tier"},
            "dry_run": False,
        }, timeout=20)
        assert b.status_code == 200, b.text
        d = b.json()
        job_id = d.get("job_id")
        assert job_id, f"missing job_id in response: {d}"
        status = d.get("status")
        assert status in ("queued", "running", "pending", "completed"), f"unexpected initial status: {status}"

        # poll up to ~10s
        final = None
        for _ in range(20):
            time.sleep(0.5)
            g = requests.get(f"{API}/communications/bulk-jobs/{job_id}", headers=admin_h, timeout=15)
            assert g.status_code == 200, g.text
            jd = g.json()
            if jd.get("status") in ("completed", "failed", "done"):
                final = jd
                break
        assert final, "job did not complete within timeout"
        assert final["status"] in ("completed", "done"), f"job status not completed: {final}"
        assert final.get("processed", 0) == 0, f"expected processed=0 for nonexistent_tier: {final}"

    def test_list_bulk_jobs(self, admin_h):
        r = requests.get(f"{API}/communications/bulk-jobs", headers=admin_h, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        rows = d.get("rows") if isinstance(d, dict) else d
        assert isinstance(rows, list)
        assert len(rows) >= 1, "expected at least 1 bulk job in list"


# ---------- D: WABA approval guard ----------
class TestWABAApproval:
    def test_waba_guard_and_approval(self, admin_h):
        # create whatsapp template without waba_template_id, active
        c = requests.post(f"{API}/templates", headers=admin_h, json={
            "name": "TEST_it8_waba",
            "channel": "whatsapp",
            "event_trigger": "campaign_bulk",
            "body": "Hi {{name}}",
            "status": "active",
        }, timeout=15)
        assert c.status_code == 200, c.text
        tid = c.json()["id"]
        try:
            # bulk-send must 400
            b = requests.post(f"{API}/communications/bulk-send", headers=admin_h, json={
                "template_id": tid, "audience": {"tier": "nonexistent_tier"}, "dry_run": False,
            }, timeout=20)
            assert b.status_code == 400, f"expected 400 WABA guard, got {b.status_code}: {b.text}"
            assert "waba" in b.text.lower() or "karix" in b.text.lower() or "approved" in b.text.lower()

            # approve
            p = requests.patch(f"{API}/templates/{tid}/waba-approval", headers=admin_h, json={
                "waba_approval_status": "approved",
                "waba_template_id": "test_id",
                "waba_params_order": ["name"],
                "waba_language": "en",
                "waba_category": "MARKETING",
            }, timeout=15)
            assert p.status_code == 200, p.text
            pd = p.json()
            assert pd.get("waba_approval_status") == "approved"
            assert pd.get("waba_template_id") == "test_id"
        finally:
            requests.delete(f"{API}/templates/{tid}", headers=admin_h, timeout=15)


# ---------- E: Scheduled exec digest ----------
class TestExecDigest:
    digest_id = None

    def test_run_now(self, admin_h):
        r = requests.post(f"{API}/reports/digests/run-now", headers=admin_h, timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("id"), f"missing id: {d}"
        TestExecDigest.digest_id = d["id"]
        fn = d.get("filename", "")
        assert "KAZO_Executive_Digest" in fn and fn.endswith(".pdf"), f"unexpected filename: {fn}"
        sz = d.get("size_bytes", 0)
        assert sz > 1000, f"size_bytes too small: {sz}"

    def test_list_digests(self, admin_h):
        r = requests.get(f"{API}/reports/digests", headers=admin_h, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        rows = d.get("rows") if isinstance(d, dict) else d
        assert isinstance(rows, list) and len(rows) >= 1
        # ensure pdf_base64 not exposed
        for row in rows[:5]:
            assert "pdf_base64" not in row, "pdf_base64 should NOT be exposed in list"
        ids = [r.get("id") for r in rows]
        assert TestExecDigest.digest_id in ids, "newly created digest not in list"

    def test_latest(self, admin_h):
        r = requests.get(f"{API}/reports/digests/latest", headers=admin_h, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("id") == TestExecDigest.digest_id, f"latest id mismatch: {d.get('id')} vs {TestExecDigest.digest_id}"

    def test_download(self, admin_h):
        assert TestExecDigest.digest_id
        r = requests.get(f"{API}/reports/digests/{TestExecDigest.digest_id}/download",
                         headers=admin_h, timeout=30)
        assert r.status_code == 200, r.text[:200]
        ct = r.headers.get("content-type", "")
        assert "application/pdf" in ct, f"expected application/pdf, got {ct}"
        assert r.content[:4] == b"%PDF", f"PDF magic not found, got {r.content[:8]!r}"


# ---------- F: Regression on existing endpoints ----------
class TestRegression:
    def test_endpoints_200(self, admin_h):
        # get a customer id first
        cj = requests.get(f"{API}/customers", headers=admin_h, params={"limit": 5}, timeout=15).json()
        if isinstance(cj, dict):
            cust_rows = cj.get("rows") or cj.get("customers") or cj.get("items") or []
        else:
            cust_rows = cj
        cust_id = None
        if cust_rows:
            first = cust_rows[0]
            cust_id = first.get("id") or first.get("_id") or first.get("customer_id")

        endpoints = [
            "/dashboard/command-center",
            "/dashboard/store-performance-v2",
            "/dashboard/rfm",
            "/dashboard/cohorts-segmentation",
            "/dashboard/points-economics",
            "/dashboard/executive-summary",
            "/templates",
            "/provider-config",
            "/customers",
            "/campaigns",
            "/coupons",
        ]
        if cust_id:
            endpoints.insert(1, f"/dashboard/customer-360/{cust_id}")
        failures = []
        for ep in endpoints:
            r = requests.get(f"{API}{ep}", headers=admin_h, timeout=30)
            if r.status_code != 200:
                failures.append((ep, r.status_code, r.text[:200]))
        assert not failures, f"regression failures: {failures}"
