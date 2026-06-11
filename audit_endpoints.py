"""Comprehensive audit of every dashboard/report endpoint — status, latency, key values."""
import requests, time, json, sys

BASE = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].strip().split("\n")[0]
tok = requests.post(f"{BASE}/api/auth/login", json={"email": "superadmin@fundle.io", "password": "Fundle@2026"}).json()["token"]
H = {"Authorization": f"Bearer {tok}"}

GETS = [
    # Command Center / dashboard_routes
    ("dashboard/kpis", {"period": "all"}),
    ("dashboard/command-center", {"period": "all", "refresh": "true"}),
    ("dashboard/sales-trend", {"period": "all"}),
    ("dashboard/store-performance", {"period": "all"}),
    ("dashboard/category-mix", {"period": "all"}),
    ("dashboard/tier-distribution", {}),
    ("dashboard/top-skus", {"period": "all"}),
    ("dashboard/filter-options", {}),
    ("dashboard/city-performance", {"period": "all"}),
    # fundlebrain dashboards
    ("dashboard/executive-summary", {"period_days": 0}),
    ("dashboard/store-performance-v2", {"period_days": 0}),
    ("dashboard/rfm", {"period_days": 0}),
    ("dashboard/cohorts-segmentation", {"period_days": 0}),
    ("dashboard/points-economics", {"period_days": 0}),
    ("dashboard/campaign-roi", {"period_days": 0}),
    # analytics dashboards
    ("analytics/sales-dashboard", {"period_days": 0}),
    ("analytics/customer-dashboard", {"period_days": 0}),
    ("analytics/campaign-dashboard", {"period_days": 0}),
    ("analytics/loyalty-dashboard", {"period_days": 0}),
    ("analytics/nps-dashboard", {"period_days": 0}),
    ("analytics/store-dashboard", {"period_days": 0}),
    # nps
    ("nps/summary", {}),
    ("nps/by-store", {}),
    ("nps/recent", {}),
    # legacy reports
    ("legacy-reports/customer-data", {"page": 1, "page_size": 10}),
    ("legacy-reports/transaction-data", {"page": 1, "page_size": 10}),
    ("legacy-reports/repeat-customers", {"page": 1, "page_size": 10}),
    ("legacy-reports/top-customers", {"page": 1, "page_size": 10}),
    ("legacy-reports/fraud-report", {"page": 1, "page_size": 10}),
    ("legacy-reports/pending-bills", {"page": 1, "page_size": 10}),
    ("legacy-reports/feedback-data", {"page": 1, "page_size": 10}),
    ("legacy-reports/missed-calls", {"page": 1, "page_size": 10}),
    ("legacy-reports/location-wise-customers", {"page": 1, "page_size": 10}),
    ("legacy-reports/expiry-points", {"page": 1, "page_size": 10}),
    ("legacy-reports/active-coupons", {"page": 1, "page_size": 10}),
    # reports & exports
    ("reports/transactions", {"limit": 10}),
    ("reports/audit-logs", {"limit": 10}),
    ("reports/digests", {}),
]
POSTS = [
    ("raw-reports/customer-data", {"page": 1, "page_size": 10}),
    ("raw-reports/transaction-data", {"page": 1, "page_size": 10}),
    ("raw-reports/repeat-purchases", {"page": 1, "page_size": 10}),
    ("raw-reports/earn-redeem", {"page": 1, "page_size": 10}),
    ("raw-reports/customers-by-visit", {"page": 1, "page_size": 10}),
]


def summarize(d, depth=0):
    if isinstance(d, dict):
        keys = list(d.keys())[:14]
        out = {}
        for k in keys:
            v = d[k]
            if isinstance(v, (int, float, str, bool)) or v is None:
                out[k] = v
            elif isinstance(v, list):
                out[k] = f"list[{len(v)}]" + (f" e.g. {json.dumps(v[0], default=str)[:120]}" if v and depth < 1 else "")
            elif isinstance(v, dict) and depth < 1:
                out[k] = summarize(v, depth + 1)
            else:
                out[k] = type(v).__name__
        return out
    if isinstance(d, list):
        return f"list[{len(d)}]" + (f" e.g. {json.dumps(d[0], default=str)[:150]}" if d else "")
    return d


results = []
for path, params in GETS:
    t0 = time.time()
    try:
        r = requests.get(f"{BASE}/api/{path}", params=params, headers=H, timeout=60)
        ms = int((time.time() - t0) * 1000)
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:200]
        results.append((path, params, r.status_code, ms, summarize(body)))
    except Exception as e:
        results.append((path, params, "ERR", int((time.time() - t0) * 1000), str(e)[:200]))

for path, body in POSTS:
    t0 = time.time()
    try:
        r = requests.post(f"{BASE}/api/{path}", json=body, headers=H, timeout=60)
        ms = int((time.time() - t0) * 1000)
        b = r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:200]
        results.append((f"POST {path}", body, r.status_code, ms, summarize(b)))
    except Exception as e:
        results.append((f"POST {path}", body, "ERR", int((time.time() - t0) * 1000), str(e)[:200]))

for path, params, code, ms, summary in results:
    flag = "✅" if code == 200 else "❌"
    print(f"{flag} [{code}] {ms:>5}ms  {path} {params}")
    print(f"      {json.dumps(summary, default=str)[:600]}")
    print()
