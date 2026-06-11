"""
Iteration 72 - Perf fixes (segments cohort-library, sales dashboard cache warmer) + AI Brain upgrades.

Covers:
- Auth login
- Segments cohort-library (cold/warm timings) + counts endpoint
- Sales dashboard + dashboard/sales-trend warmed
- Command center + KPIs
- AI chat: CSV export tool + markdown table
- AI exports download endpoint
- AI suggested-prompts
- Regression: analytics dashboards & cohort preview
"""

import os
import time
import json
import pytest
import requests

def _load_url():
    u = os.environ.get("REACT_APP_BACKEND_URL")
    if not u:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        u = line.split("=", 1)[1].strip()
                        break
        except FileNotFoundError:
            pass
    assert u, "REACT_APP_BACKEND_URL not set"
    return u.rstrip("/")

BASE_URL = _load_url()
ADMIN_EMAIL = "superadmin@fundle.io"
ADMIN_PASSWORD = "Fundle@2026"


@pytest.fixture(scope="session")
def token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    assert "token" in data, f"Missing token key: {list(data.keys())}"
    assert "user" in data
    return data["token"]


@pytest.fixture(scope="session")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------------- Auth ----------------
class TestAuth:
    def test_login_returns_token(self, token):
        assert isinstance(token, str) and len(token) > 10


# ---------------- Segments Cohort Library P0 ----------------
class TestCohortLibrary:
    def test_cohort_library_cold_and_warm(self, auth_headers):
        t1 = time.time()
        r1 = requests.get(f"{BASE_URL}/api/segments/cohort-library/", headers=auth_headers, timeout=30)
        d1 = time.time() - t1
        assert r1.status_code == 200, f"cold {r1.status_code}: {r1.text[:200]}"
        body = r1.json()
        assert "context" in body and "categories" in body
        assert "atv" in body["context"]
        assert isinstance(body["categories"], list) and len(body["categories"]) > 0
        # has cohorts somewhere
        any_cohorts = any(len(c.get("cohorts", [])) > 0 for c in body["categories"])
        assert any_cohorts, "no cohorts in categories"
        print(f"cohort-library cold {d1:.2f}s")
        assert d1 < 15, f"cold too slow: {d1:.2f}s"

        t2 = time.time()
        r2 = requests.get(f"{BASE_URL}/api/segments/cohort-library/", headers=auth_headers, timeout=15)
        d2 = time.time() - t2
        assert r2.status_code == 200
        print(f"cohort-library warm {d2:.2f}s")
        assert d2 < 2.0, f"warm too slow: {d2:.2f}s"

    def test_cohort_library_counts(self, auth_headers):
        payload = {"cohort_ids": ["loyal_members", "one_timer", "repeat", "tier_gold"]}
        t1 = time.time()
        r1 = requests.post(
            f"{BASE_URL}/api/segments/cohort-library/counts",
            headers=auth_headers,
            json=payload,
            timeout=60,
        )
        d1 = time.time() - t1
        assert r1.status_code == 200, f"counts {r1.status_code}: {r1.text[:200]}"
        body = r1.json()
        # accept either {counts:{...}} or {...}
        counts = body.get("counts", body)
        assert isinstance(counts, dict)
        # check at least loyal_members and one_timer have plausible values
        # values can be either int or {count: int}
        def val(x):
            if isinstance(x, dict):
                return x.get("count", x.get("value", 0))
            return x
        lm = val(counts.get("loyal_members", 0))
        ot = val(counts.get("one_timer", 0))
        print(f"counts loyal_members={lm} one_timer={ot}")
        assert lm > 100000, f"loyal_members count low: {lm}"
        assert ot > 100000, f"one_timer count low: {ot}"
        print(f"counts cold {d1:.2f}s")

        t2 = time.time()
        r2 = requests.post(
            f"{BASE_URL}/api/segments/cohort-library/counts",
            headers=auth_headers,
            json=payload,
            timeout=15,
        )
        d2 = time.time() - t2
        assert r2.status_code == 200
        print(f"counts warm {d2:.2f}s")
        assert d2 < 2.0, f"warm counts too slow: {d2:.2f}s"

    def test_cohort_preview_one_timer(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/segments/cohort-library/one_timer/preview",
            headers=auth_headers,
            json={},
            timeout=60,
        )
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        body = r.json()
        # accept matched/count/total fields
        count = body.get("matched_total") or body.get("matched") or body.get("count") or body.get("total") or body.get("matched_count")
        assert count and count > 100000, f"one_timer preview count low: {body}"


# ---------------- Sales Dashboard P0 ----------------
class TestSalesDashboard:
    def test_sales_dashboard_warm(self, auth_headers):
        t1 = time.time()
        r = requests.get(
            f"{BASE_URL}/api/analytics/sales-dashboard?period_days=0",
            headers=auth_headers,
            timeout=30,
        )
        d = time.time() - t1
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        print(f"sales-dashboard {d:.2f}s")
        assert d < 20, f"too slow: {d:.2f}s"

    def test_sales_trend_warm(self, auth_headers):
        t1 = time.time()
        r = requests.get(
            f"{BASE_URL}/api/dashboard/sales-trend?period=all",
            headers=auth_headers,
            timeout=30,
        )
        d = time.time() - t1
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        print(f"sales-trend {d:.2f}s")
        assert d < 20

    def test_command_center(self, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/dashboard/command-center?period=all",
            headers=auth_headers,
            timeout=30,
        )
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        body = r.json()
        assert body, "empty body"

    def test_kpis(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/dashboard/kpis", headers=auth_headers, timeout=30)
        assert r.status_code == 200
        assert r.json(), "empty body"


# ---------------- AI Brain ----------------
class TestAIBrain:
    def test_suggested_prompts(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/ai/suggested-prompts", headers=auth_headers, timeout=15)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        body = r.json()
        # body may be list or {prompts:[...]}
        prompts = body if isinstance(body, list) else body.get("prompts") or body.get("data") or []
        text_blob = json.dumps(prompts).lower()
        assert "csv" in text_blob or "export" in text_blob, f"no csv/export prompt: {text_blob[:300]}"

    def test_export_nonexistent(self, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/ai/exports/nonexistent-id-xyz",
            headers=auth_headers,
            timeout=15,
        )
        assert r.status_code == 404

    def test_ai_chat_csv_export(self, auth_headers):
        payload = {"message": "give me a csv of all one timers", "model": "gpt-5.5"}
        r = requests.post(
            f"{BASE_URL}/api/ai/chat",
            headers=auth_headers,
            json=payload,
            timeout=180,
        )
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        body = r.json()
        reply = body.get("reply") or body.get("message") or body.get("content") or ""
        tools = body.get("tools_used") or body.get("tools") or []
        if isinstance(tools, list):
            tool_names = [t if isinstance(t, str) else t.get("name", "") for t in tools]
        else:
            tool_names = [str(tools)]
        print(f"tools_used={tool_names}")
        print(f"reply preview: {reply[:300]}")
        assert "export_csv" in " ".join(tool_names).lower(), f"export_csv not in tools: {tool_names}"
        assert "/api/ai/exports/" in reply, f"no export link in reply: {reply[:300]}"

        # parse export id
        import re
        m = re.search(r"/api/ai/exports/([A-Za-z0-9_\-]+)", reply)
        assert m, "could not parse export id"
        export_id = m.group(1)
        print(f"export_id={export_id}")

        # download check (range header to avoid 52MB)
        dl = requests.get(
            f"{BASE_URL}/api/ai/exports/{export_id}",
            headers={**auth_headers, "Range": "bytes=0-4096"},
            timeout=60,
            stream=True,
        )
        assert dl.status_code in (200, 206), f"download status {dl.status_code}: {dl.text[:200]}"
        ct = dl.headers.get("content-type", "").lower()
        assert "csv" in ct or "text" in ct, f"unexpected content-type: {ct}"
        first = dl.raw.read(2048) if hasattr(dl, "raw") else dl.content[:2048]
        if isinstance(first, bytes):
            first = first.decode("utf-8", errors="ignore")
        print(f"csv head: {first[:200]}")
        assert "," in first, "csv head has no commas"

    def test_ai_chat_markdown_table(self, auth_headers):
        payload = {
            "message": "What is the breakdown of customers by tier? Show as a table",
            "model": "claude-sonnet-4-6",
        }
        r = requests.post(
            f"{BASE_URL}/api/ai/chat",
            headers=auth_headers,
            json=payload,
            timeout=180,
        )
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        body = r.json()
        reply = body.get("reply") or body.get("message") or body.get("content") or ""
        tools = body.get("tools_used") or body.get("tools") or []
        print(f"reply preview: {reply[:400]}")
        print(f"tools={tools}")
        assert "|" in reply, "no markdown table pipe chars"
        assert tools, "no tool used"


# ---------------- Regression analytics ----------------
class TestRegression:
    @pytest.mark.parametrize("path", [
        "/api/analytics/customer-dashboard",
        "/api/analytics/loyalty-dashboard",
        "/api/analytics/store-dashboard",
        "/api/dashboard/store-performance",
        "/api/dashboard/category-mix",
        "/api/dashboard/top-skus",
    ])
    def test_regression_dashboards(self, auth_headers, path):
        r = requests.get(f"{BASE_URL}{path}", headers=auth_headers, timeout=30)
        assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:200]}"
