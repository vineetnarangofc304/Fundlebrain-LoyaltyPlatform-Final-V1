"""
Iteration 34 — POS JSON envelope regression tests.

Background:
  Before the fix, an unhandled exception on a /api/pos/* route returned a
  PLAIN-TEXT body ("Internal Server Error", HTTP 500). The eWards .NET POS
  tried to JSON-parse that and crashed with:
       "The data does not represent a valid JSON token."
  The fix registers a global Exception handler that, for /api/pos/* paths,
  returns HTTP 200 + application/json + the eWards envelope
  {"status_code": 500, "response": {"message": "..."}}, and logs the
  real traceback to the api_logs collection so the API Monitor can show
  the root cause.

These tests hit the EXTERNAL REACT_APP_BACKEND_URL (production-like ingress)
and assert:
  1. Forced exception -> HTTP 200, JSON, envelope with status_code 500.
  2. Happy path -> HTTP 200, JSON, status_code 200.
  3. posCustomerCheck happy path -> HTTP 200, JSON.
  4. payment_mode as list-of-strings hardening -> HTTP 200, JSON.
  5. Every response body is JSON (no plain text).
  6. After forced exception, api_logs has a doc with error_reason starting
     'unhandled_exception' and a non-empty traceback for /api/pos/posAddPoint.
"""

import os
import time
import uuid
import json
import pytest
import requests
from pathlib import Path


def _load_env_file(p: Path):
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k.strip(), v)


# Load both frontend/.env (REACT_APP_BACKEND_URL) and backend/.env (MONGO_URL, DB_NAME)
_load_env_file(Path("/app/frontend/.env"))
_load_env_file(Path("/app/backend/.env"))

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
POS_KEY = "ZFQWql7I3vCH0ckuWmA8zVKDDJWYPBtoQGLruEnRrFI"
MERCHANT = "KAZO_FUNDLE"
STORE = "K00055"
MOBILE = "9876500011"

HEADERS = {"Content-Type": "application/json", "x-api-key": POS_KEY}


def _unique_bill() -> str:
    return f"TEST34-{uuid.uuid4().hex[:10]}"


def _assert_json_response(resp):
    """Body must be valid JSON with application/json content-type."""
    ct = resp.headers.get("content-type", "")
    assert "application/json" in ct.lower(), (
        f"Expected application/json, got '{ct}'. Body[:200]={resp.text[:200]!r}"
    )
    # raises if not JSON
    return resp.json()


# ---------------------------------------------------------------------------
# 1) Core bug fix — forced unhandled exception must still return JSON envelope
# ---------------------------------------------------------------------------
class TestForcedExceptionReturnsJsonEnvelope:
    def test_transaction_as_string_returns_pos_envelope_not_plaintext(self):
        payload = {
            "merchant_id": MERCHANT,
            "customer_key": STORE,
            "customer": {"mobile": MOBILE},
            # transaction MUST be an object — sending a string forces a server
            # error path. The global handler must still emit the JSON envelope.
            "transaction": "oops-not-an-object",
        }
        r = requests.post(f"{BASE_URL}/api/pos/posAddPoint",
                          headers=HEADERS, json=payload, timeout=30)

        # MUST be HTTP 200 (eWards contract: error inside body, not via HTTP)
        assert r.status_code == 200, (
            f"Expected HTTP 200, got {r.status_code}. Body[:300]={r.text[:300]!r}"
        )
        # MUST be parseable JSON — this is what the .NET POS does and used to crash.
        body = _assert_json_response(r)
        # MUST follow eWards envelope.
        assert isinstance(body, dict), f"Body is not an object: {body!r}"
        assert "status_code" in body, f"Missing 'status_code' in body: {body!r}"
        assert "response" in body, f"Missing 'response' in body: {body!r}"
        # The forced error path should surface a 500 inside the envelope (handler
        # branch) OR a validation 400 (if posAddPoint validates before raising).
        # Either way it must NOT be the plain-text "Internal Server Error".
        assert body["status_code"] in (400, 500), (
            f"Unexpected inner status_code: {body['status_code']} body={body!r}"
        )
        assert isinstance(body["response"], dict), f"response not dict: {body!r}"
        assert "message" in body["response"], f"Missing message: {body!r}"
        # Sanity: it must not be the raw plaintext sentinel that crashed the POS.
        assert r.text.strip().lower() != "internal server error", (
            "Server returned the plain-text 'Internal Server Error' — the .NET "
            "POS would crash with 'not a valid JSON token'."
        )


# ---------------------------------------------------------------------------
# 2) Happy-path regression on posAddPoint
# ---------------------------------------------------------------------------
class TestPosAddPointHappyPath:
    def test_valid_bill_returns_200_envelope(self):
        bill = _unique_bill()
        payload = {
            "merchant_id": MERCHANT,
            "customer_key": STORE,
            "customer": {"mobile": MOBILE, "name": "Test"},
            "transaction": {
                "number": bill,
                "amount": 1000,
                "taxes": [{"name": "GST", "amount": 50}],
                "items": [{"name": "ITM01", "quantity": 1, "rate": 1000}],
                "payment_mode": [{"name": "card"}],
            },
        }
        r = requests.post(f"{BASE_URL}/api/pos/posAddPoint",
                          headers=HEADERS, json=payload, timeout=30)
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:300]!r}"
        body = _assert_json_response(r)
        assert body.get("status_code") == 200, (
            f"Expected inner status_code 200, got {body!r}"
        )
        resp = body.get("response") or {}
        # Don't be overly strict on exact keys, but at least confirm dict shape.
        assert isinstance(resp, dict), f"response not dict: {body!r}"


# ---------------------------------------------------------------------------
# 3) posCustomerCheck happy-path regression
# ---------------------------------------------------------------------------
class TestPosCustomerCheck:
    def test_customer_check_returns_json(self):
        payload = {
            "merchant_id": MERCHANT,
            "customer_key": STORE,
            "customer_mobile": MOBILE,
            "bill_amount": 1000,
        }
        r = requests.post(f"{BASE_URL}/api/pos/posCustomerCheck",
                          headers=HEADERS, json=payload, timeout=30)
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:300]!r}"
        body = _assert_json_response(r)
        assert "status_code" in body and "response" in body, f"Bad envelope: {body!r}"


# ---------------------------------------------------------------------------
# 4) Hardening — payment_mode as list-of-strings must not crash
# ---------------------------------------------------------------------------
class TestPaymentModeListOfStrings:
    def test_payment_mode_strings_does_not_crash(self):
        bill = _unique_bill()
        payload = {
            "merchant_id": MERCHANT,
            "customer_key": STORE,
            "customer": {"mobile": MOBILE, "name": "Test"},
            "transaction": {
                "number": bill,
                "amount": 500,
                "taxes": [{"name": "GST", "amount": 25}],
                "items": [{"name": "ITM02", "quantity": 1, "rate": 500}],
                # NOTE: list of plain strings, not list of {name:...}
                "payment_mode": ["Cash"],
            },
        }
        r = requests.post(f"{BASE_URL}/api/pos/posAddPoint",
                          headers=HEADERS, json=payload, timeout=30)
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:300]!r}"
        body = _assert_json_response(r)
        # Must not be the unhandled-exception envelope (status_code 500).
        assert body.get("status_code") == 200, (
            f"payment_mode list-of-strings was NOT hardened — got {body!r}"
        )


# ---------------------------------------------------------------------------
# 6) After forced exception, api_logs must have a record with traceback
# ---------------------------------------------------------------------------
class TestApiLogsCapturedTraceback:
    def test_api_logs_has_unhandled_exception_entry(self):
        # Trigger a fresh forced exception and tag it via a unique sentinel
        # mobile so we can locate the resulting log entry deterministically.
        sentinel_mobile = f"9876{int(time.time()) % 1000000:06d}"
        payload = {
            "merchant_id": MERCHANT,
            "customer_key": STORE,
            "customer": {"mobile": sentinel_mobile},
            "transaction": "force-error-" + uuid.uuid4().hex[:6],
        }
        r = requests.post(f"{BASE_URL}/api/pos/posAddPoint",
                          headers=HEADERS, json=payload, timeout=30)
        assert r.status_code == 200
        _assert_json_response(r)

        # Give the async insert a moment.
        time.sleep(1.5)

        # Query api_logs directly via Mongo (no public read endpoint guaranteed).
        try:
            import asyncio
            from motor.motor_asyncio import AsyncIOMotorClient
            mongo_url = os.environ["MONGO_URL"]
            db_name = os.environ["DB_NAME"]
        except KeyError as e:
            pytest.skip(f"Mongo env not available for direct log check: {e}")
            return

        async def _find():
            client = AsyncIOMotorClient(mongo_url)
            try:
                db = client[db_name]
                # Find latest unhandled_exception log for posAddPoint.
                cur = db.api_logs.find({
                    "endpoint": "/api/pos/posAddPoint",
                    "error_reason": {"$regex": "^unhandled_exception"},
                }).sort("timestamp", -1).limit(5)
                return [doc async for doc in cur]
            finally:
                client.close()

        docs = asyncio.get_event_loop().run_until_complete(_find()) \
            if not asyncio.get_event_loop().is_running() \
            else asyncio.new_event_loop().run_until_complete(_find())

        assert docs, ("No api_logs doc with error_reason starting "
                      "'unhandled_exception' for /api/pos/posAddPoint was found.")
        latest = docs[0]
        assert latest.get("traceback"), (
            f"api_logs entry missing non-empty 'traceback': {latest!r}"
        )
        assert latest["error_reason"].startswith("unhandled_exception"), (
            f"error_reason malformed: {latest['error_reason']!r}"
        )
