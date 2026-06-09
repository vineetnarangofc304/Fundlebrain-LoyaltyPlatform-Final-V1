"""Iteration 52 — POS x-api-key 'Set key' (set a SPECIFIC key, not a random rotate).

Verifies:
  - POST /api/admin/pos-credentials/{id}/set-key updates the active credential's api_key.
  - /api/pos/* then authenticates against the new key.
  - A different/old key is rejected with 403.
"""
import os
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE:
    with open("/app/frontend/.env") as f:
        for ln in f:
            if ln.startswith("REACT_APP_BACKEND_URL"):
                BASE = ln.strip().split("=", 1)[1]
API = f"{BASE}/api"
NEW_KEY = "SETKEYTEST_" + "x" * 24  # >=16 chars, unique to this test


def _login():
    r = requests.post(f"{API}/auth/login", json={"email": "superadmin@fundle.io", "password": "Fundle@2026"})
    r.raise_for_status()
    return r.json()["token"]


def test_set_specific_pos_key_and_auth():
    tok = _login()
    h = {"Authorization": f"Bearer {tok}"}
    creds = requests.get(f"{API}/admin/pos-credentials", headers=h).json()["credentials"]
    assert creds, "no pos credentials to test against"
    cred = next((c for c in creds if c.get("is_active")), creds[0])
    cid, merchant, ckey = cred["id"], cred["merchant_id"], cred.get("customer_key")
    original_key = cred["api_key"]

    try:
        # set a specific key
        r = requests.post(f"{API}/admin/pos-credentials/{cid}/set-key", headers=h, json={"api_key": NEW_KEY})
        assert r.status_code == 200, r.text
        assert r.json()["api_key"] == NEW_KEY
        assert r.json()["is_active"] is True

        # POS call WITH new key → auth passes (200 at the gateway; business body may say 'not registered')
        r2 = requests.post(f"{API}/pos/posCustomerCheck", headers={"x-api-key": NEW_KEY},
                           json={"merchant_id": merchant, "customer_key": ckey,
                                 "customer_mobile": "9000000000", "country_code": "91"})
        assert r2.status_code == 200, f"auth should pass with new key: {r2.status_code} {r2.text}"

        # POS call with a clearly-wrong key → 403
        r3 = requests.post(f"{API}/pos/posCustomerCheck", headers={"x-api-key": "definitely-not-the-key-zzz"},
                           json={"merchant_id": merchant, "customer_key": ckey,
                                 "customer_mobile": "9000000000", "country_code": "91"})
        assert r3.status_code == 403, f"wrong key must be rejected: {r3.status_code}"

        # too-short key rejected
        r4 = requests.post(f"{API}/admin/pos-credentials/{cid}/set-key", headers=h, json={"api_key": "short"})
        assert r4.status_code == 400
        print("PASS: set-key applies a specific x-api-key and POS auth honours it.")
    finally:
        # restore original key so we don't disrupt the env
        requests.post(f"{API}/admin/pos-credentials/{cid}/set-key", headers=h, json={"api_key": original_key})


if __name__ == "__main__":
    test_set_specific_pos_key_and_auth()
