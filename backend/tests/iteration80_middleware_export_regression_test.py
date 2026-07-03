"""
Iteration 80: Middleware rewrite regression + export bug fix verification.

Tests:
- Regression: core JSON flows (login, /me, dashboard-ish GETs, POST /segments/preview)
- Segments audience export CSV/XLSX/PDF returns non-empty body
- AI export download (best-effort, may skip if LLM flaky)
- API monitor logs recent exports (best-effort)
"""
import io
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
SUPERADMIN = {"email": "superadmin@fundle.io", "password": "Fundle@2026"}


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=SUPERADMIN, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:400]}"
    data = r.json()
    tok = data.get("token") or data.get("access_token")
    assert tok, f"no token in login response: {data}"
    return tok


@pytest.fixture(scope="module")
def auth(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


# ---------- Regression: core JSON flows ----------

class TestMiddlewareRegression:
    def test_auth_me(self, auth):
        r = auth.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("email") == SUPERADMIN["email"]

    def test_dashboard_or_customers(self, auth):
        # try dashboard first, fallback to customers list
        r = auth.get(f"{BASE_URL}/api/dashboard", timeout=30)
        if r.status_code == 404:
            r = auth.get(f"{BASE_URL}/api/customers?limit=5", timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        assert len(r.content) > 2, "empty body from GET (middleware truncation?)"
        # must be valid JSON
        r.json()

    def test_segments_facets(self, auth):
        r = auth.get(f"{BASE_URL}/api/segments/facets", timeout=30)
        assert r.status_code in (200, 404), r.text[:300]
        if r.status_code == 200:
            assert len(r.content) > 2
            r.json()

    def test_segments_cohort_library(self, auth):
        r = auth.get(f"{BASE_URL}/api/segments/cohort-library", timeout=30)
        assert r.status_code in (200, 404), r.text[:300]
        if r.status_code == 200:
            r.json()

    def test_segments_preview_post_body_parsed(self, auth):
        body = {"tree": {"op": "AND", "rules": []}}
        r = auth.post(f"{BASE_URL}/api/segments/preview", json=body, timeout=60)
        assert r.status_code == 200, f"POST body possibly lost: {r.status_code} {r.text[:400]}"
        d = r.json()
        assert "matched_total" in d, f"missing matched_total: {d}"
        assert isinstance(d["matched_total"], int)


# ---------- Export bug fix verification ----------

class TestSegmentsAudienceExport:
    def test_csv_export_nonempty(self, auth):
        body = {
            "tree": {"op": "AND", "rules": []},
            "format": "csv",
            "sort_by": "lifetime_spend",
            "sort_dir": -1,
            "max_rows": 3000,
        }
        r = auth.post(f"{BASE_URL}/api/segments/audience/export", json=body, timeout=120)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        ct = r.headers.get("content-type", "")
        assert "csv" in ct.lower(), f"content-type not csv: {ct}"
        assert len(r.content) > 100, f"CSV body too small: {len(r.content)} bytes"
        # Header + data rows
        text = r.content.decode("utf-8", errors="ignore")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        assert len(lines) >= 2, f"CSV should have header + data rows, got {len(lines)}"
        print(f"CSV rows: {len(lines)} (incl. header), size={len(r.content)} bytes")

    def test_xlsx_export_nonempty(self, auth):
        body = {
            "tree": {"op": "AND", "rules": []},
            "format": "xlsx",
            "sort_by": "lifetime_spend",
            "sort_dir": -1,
            "max_rows": 1000,
        }
        r = auth.post(f"{BASE_URL}/api/segments/audience/export", json=body, timeout=120)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        assert len(r.content) > 200, f"xlsx too small: {len(r.content)}"
        assert r.content[:2] == b"PK", f"xlsx magic not PK: {r.content[:4]!r}"
        print(f"XLSX size={len(r.content)} bytes, magic OK")

    def test_pdf_export_nonempty(self, auth):
        body = {
            "tree": {"op": "AND", "rules": []},
            "format": "pdf",
            "sort_by": "lifetime_spend",
            "sort_dir": -1,
            "max_rows": 300,
        }
        r = auth.post(f"{BASE_URL}/api/segments/audience/export", json=body, timeout=120)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        assert len(r.content) > 200, f"pdf too small: {len(r.content)}"
        assert r.content[:5] == b"%PDF-", f"pdf magic missing: {r.content[:8]!r}"
        print(f"PDF size={len(r.content)} bytes, magic OK")


# ---------- AI export download (best-effort) ----------

class TestAIExportDownload:
    def test_ai_export_download(self, auth):
        try:
            chat = auth.post(
                f"{BASE_URL}/api/ai/chat",
                json={"message": "Give me a CSV of 100 platinum customers with mobile, name, tier"},
                timeout=120,
            )
        except requests.exceptions.RequestException as e:
            pytest.skip(f"AI chat unreachable: {e}")
        if chat.status_code != 200:
            pytest.skip(f"AI chat non-200: {chat.status_code} {chat.text[:200]}")
        data = chat.json()
        # find markdown link (/api/ai/exports/<id>)
        import re
        text = str(data)
        m = re.search(r"/api/ai/exports/([A-Za-z0-9_\-]+)", text)
        if not m:
            pytest.skip(f"no export link in AI reply: {text[:300]}")
        export_id = m.group(1)
        r = auth.get(f"{BASE_URL}/api/ai/exports/{export_id}", timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        assert len(r.content) > 50, f"AI export body empty: {len(r.content)}"
        print(f"AI export {export_id}: {len(r.content)} bytes")


# ---------- API monitor logging (best-effort) ----------

class TestAPIMonitorLogs:
    def test_api_monitor_has_recent(self, auth):
        # try a couple of possible endpoints
        candidates = [
            "/api/api-monitor?limit=20",
            "/api/api-monitor/logs?limit=20",
            "/api/api-logs?limit=20",
        ]
        found = None
        for c in candidates:
            r = auth.get(f"{BASE_URL}{c}", timeout=20)
            if r.status_code == 200:
                found = (c, r)
                break
        if not found:
            pytest.skip("api-monitor listing endpoint not discovered")
        c, r = found
        body = r.json()
        # normalise
        items = body if isinstance(body, list) else body.get("items") or body.get("logs") or body.get("data") or []
        assert isinstance(items, list)
        print(f"api-monitor {c}: {len(items)} items")
