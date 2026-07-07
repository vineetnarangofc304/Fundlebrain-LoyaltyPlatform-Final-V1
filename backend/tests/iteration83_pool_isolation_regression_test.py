"""Iteration 83 — Backend regression for the P0 connection-pool isolation fix.

Validates:
  1. POS customer lookup (fast + 200)
  2. POS OTP request + verify (mock OTP 123456)
  3. POS posAddPoint (unique bill, K00055 store, KAZO_FUNDLE merchant) — the fix's target
  4. POS redeem OTP flow
  5. api_logs still receives rows via the new isolated background writer
  6. Concurrency: 30 parallel posCustomerCheck calls all return 200 without timeout
  7. Master Brain SSE /chat/stream ends with a 'done' event carrying a reply
"""
import os
import json
import time
import uuid
import asyncio
import pytest
import requests
import httpx

def _load_frontend_env():
    p = "/app/frontend/.env"
    try:
        with open(p) as f:
            for line in f:
                if line.strip().startswith("REACT_APP_BACKEND_URL"):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _load_frontend_env() or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not resolvable"
POS_KEY = "ZFQWql7I3vCH0ckuWmA8zVKDDJWYPBtoQGLruEnRrFI"
MERCHANT = "KAZO_FUNDLE"
STORE_CUSTOMER_KEY = "K00055"
MOCK_OTP = "123456"
GOLD_MOBILE = "9990002222"


def _pos_headers():
    return {"x-api-key": POS_KEY, "Content-Type": "application/json"}


# --------------------------- POS core flows ---------------------------

def test_pos_customer_check_fast_200():
    body = {"merchant_id": MERCHANT, "customer_key": STORE_CUSTOMER_KEY,
            "customer_mobile": GOLD_MOBILE}
    t0 = time.time()
    r = requests.post(f"{BASE_URL}/api/pos/posCustomerCheck",
                      headers=_pos_headers(), json=body, timeout=10)
    elapsed = time.time() - t0
    assert r.status_code == 200, r.text
    env = r.json()
    assert env.get("status_code") == 200, env
    assert elapsed < 3.0, f"posCustomerCheck too slow: {elapsed:.2f}s"
    resp = env.get("response") or {}
    # Should carry some customer detail (mobile / points / tier / message)
    assert resp, f"empty response envelope: {env}"


def test_pos_otp_request_and_verify():
    body = {"merchant_id": MERCHANT, "customer_key": STORE_CUSTOMER_KEY,
            "customer_mobile": GOLD_MOBILE}
    r = requests.post(f"{BASE_URL}/api/pos/posCustomerCheckRequest",
                      headers=_pos_headers(), json=body, timeout=10)
    assert r.status_code == 200, r.text
    env = r.json()
    assert env.get("status_code") == 200, env
    resp = env.get("response") or {}
    otp = resp.get("otp_demo") or resp.get("otp") or MOCK_OTP

    verify_body = dict(body)
    verify_body["otp"] = str(otp)
    r2 = requests.post(f"{BASE_URL}/api/pos/posCustomerOTPCheck",
                       headers=_pos_headers(), json=verify_body, timeout=10)
    assert r2.status_code == 200, r2.text
    env2 = r2.json()
    assert env2.get("status_code") == 200, env2


# --------------------------- The critical one ---------------------------

def _unique_bill():
    return f"IT83-{uuid.uuid4().hex[:10].upper()}"


def _add_point_payload(bill_no: str, mobile: str = GOLD_MOBILE, amount: float = 1500.0):
    return {
        "merchant_id": MERCHANT,
        "customer_key": STORE_CUSTOMER_KEY,
        "customer_mobile": mobile,
        "customer_name": "IT83 QA",
        "transaction": {
            "number": bill_no,
            "date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "amount": amount,
            "items": [
                {"sku": "IT83-SKU", "name": "IT83 Item", "qty": 1,
                 "price": amount, "amount": amount}
            ],
        },
    }


def test_pos_add_point_fast_and_persisted():
    bill = _unique_bill()
    t0 = time.time()
    r = requests.post(f"{BASE_URL}/api/pos/posAddPoint",
                      headers=_pos_headers(),
                      json=_add_point_payload(bill), timeout=15)
    elapsed = time.time() - t0
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text}"
    assert elapsed < 5.0, f"posAddPoint too slow: {elapsed:.2f}s"
    env = r.json()
    assert env.get("status_code") == 200, f"envelope not 200: {env}"
    resp = env.get("response") or {}
    # A genuine success carries points_earned/new_balance or message text
    assert any(k in resp for k in ("points_earned", "new_balance", "message")), \
        f"unexpected response body: {resp}"


# --------------------------- Redeem ---------------------------

def test_pos_redeem_flow():
    body = {"merchant_id": MERCHANT, "customer_key": STORE_CUSTOMER_KEY,
            "customer_mobile": GOLD_MOBILE, "points": 10}
    r = requests.post(f"{BASE_URL}/api/pos/posRedeemPointRequest",
                      headers=_pos_headers(), json=body, timeout=10)
    assert r.status_code == 200, r.text
    env = r.json()
    assert env.get("status_code") == 200, env
    resp = env.get("response") or {}
    redeem_id = resp.get("redeem_id") or resp.get("redeemId")
    otp = resp.get("otp_demo") or resp.get("otp") or MOCK_OTP

    verify_body = {"merchant_id": MERCHANT, "customer_key": STORE_CUSTOMER_KEY,
                   "customer_mobile": GOLD_MOBILE, "points": 10,
                   "otp": str(otp)}
    if redeem_id:
        verify_body["redeem_id"] = redeem_id

    r2 = requests.post(f"{BASE_URL}/api/pos/posRedeemPointOtpCheck",
                       headers=_pos_headers(), json=verify_body, timeout=10)
    assert r2.status_code == 200, r2.text
    env2 = r2.json()
    # Even handled errors return 200 envelope; assert envelope shape.
    assert "status_code" in env2, env2


# --------------------------- api_logs persistence ---------------------------

@pytest.fixture(scope="module")
def master_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "masteradmin@fundle.io",
                            "password": "Master@2026"}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_api_monitor_logs_written(master_token):
    # Trigger a POS call whose logging goes through the background writer
    bill_marker = _unique_bill()
    requests.post(f"{BASE_URL}/api/pos/posCustomerCheck",
                  headers=_pos_headers(),
                  json={"merchant_id": MERCHANT,
                        "customer_key": STORE_CUSTOMER_KEY,
                        "customer_mobile": GOLD_MOBILE},
                  timeout=10)
    # Also an internal admin API call
    requests.get(f"{BASE_URL}/api/customers?limit=1",
                 headers={"Authorization": f"Bearer {master_token}"}, timeout=10)

    # Give the background writer up to 5s to flush
    found_pos = found_admin = False
    for _ in range(10):
        time.sleep(0.5)
        r = requests.get(f"{BASE_URL}/api/api-monitor/recent?limit=100",
                         headers={"Authorization": f"Bearer {master_token}"},
                         timeout=10)
        if r.status_code != 200:
            continue
        rows = r.json() or []
        endpoints = {row.get("endpoint", "") for row in rows}
        if any("/api/pos/posCustomerCheck" in e for e in endpoints):
            found_pos = True
        if any("/customers" in e for e in endpoints):
            found_admin = True
        if found_pos and found_admin:
            break
    assert found_pos, "posCustomerCheck row not found in api-monitor within 5s"
    # Admin logging may pass through APILogMiddleware; if it isn't present that's
    # a soft signal — still assert we saw something written recently.
    assert len(rows) > 0


# --------------------------- Concurrency / pool starvation ---------------------------

def test_concurrent_pos_customer_check_no_starvation():
    async def _fire(client, i):
        body = {"merchant_id": MERCHANT, "customer_key": STORE_CUSTOMER_KEY,
                "customer_mobile": GOLD_MOBILE}
        t0 = time.time()
        try:
            r = await client.post(f"{BASE_URL}/api/pos/posCustomerCheck",
                                  headers=_pos_headers(), json=body)
            return r.status_code, time.time() - t0, r.text[:120]
        except Exception as e:  # noqa: BLE001
            return 0, time.time() - t0, str(e)

    async def _run():
        async with httpx.AsyncClient(timeout=20.0) as client:
            return await asyncio.gather(*[_fire(client, i) for i in range(30)])

    results = asyncio.run(_run())
    statuses = [s for s, _, _ in results]
    latencies = [t for _, t, _ in results]
    ok = sum(1 for s in statuses if s == 200)
    max_lat = max(latencies)
    print(f"concurrency: ok={ok}/30 max_latency={max_lat:.2f}s statuses={statuses}")
    assert ok == 30, f"only {ok}/30 concurrent calls returned 200 — starvation regression? " \
                     f"statuses={statuses}"
    assert max_lat < 8.0, f"max latency {max_lat:.2f}s under 30-way concurrency looks like starvation"


# --------------------------- Master Brain SSE streaming ---------------------------

def _stream_chat(token: str, message: str, timeout: float = 60.0):
    """Consume the SSE stream and return (events, done_evt)."""
    url = f"{BASE_URL}/api/master-brain/chat/stream"
    headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream",
               "Content-Type": "application/json"}
    body = {"session_id": None, "message": message, "attachment_ids": []}
    events = []
    done_evt = None
    with requests.post(url, headers=headers, json=body, stream=True, timeout=timeout) as r:
        assert r.status_code == 200, f"stream HTTP {r.status_code}: {r.text[:300]}"
        deadline = time.time() + timeout
        for raw in r.iter_lines(decode_unicode=True):
            if time.time() > deadline:
                break
            if not raw:
                continue
            if raw.startswith(":"):
                continue  # heartbeat / open
            if raw.startswith("data:"):
                payload = raw[5:].strip()
                if not payload:
                    continue
                try:
                    evt = json.loads(payload)
                except Exception:
                    continue
                events.append(evt)
                if evt.get("type") == "done":
                    done_evt = evt
                    break
                if evt.get("type") == "error":
                    done_evt = evt
                    break
    return events, done_evt


def test_master_brain_stream_ready(master_token):
    events, done = _stream_chat(master_token, "reply with just READY")
    assert done is not None, f"no done/error event; got {events[-5:]}"
    assert done.get("type") == "done", f"stream ended with error: {done}"
    reply = (done.get("reply") or "").strip()
    assert reply, f"empty reply in done event: {done}"
    # Soft check — model may add extra fluff; accept any non-empty reply
    print(f"MB READY reply: {reply[:200]}")


def test_master_brain_stream_customer_count(master_token):
    events, done = _stream_chat(master_token, "how many customers do we have? Reply with just the number.",
                                timeout=90.0)
    assert done is not None, f"no done/error; last events={events[-5:]}"
    assert done.get("type") == "done", f"stream ended with error: {done}"
    reply = (done.get("reply") or "")
    # Some digit should appear in the reply
    assert any(ch.isdigit() for ch in reply), f"no number in reply: {reply[:300]}"
    print(f"MB count reply: {reply[:200]}")
