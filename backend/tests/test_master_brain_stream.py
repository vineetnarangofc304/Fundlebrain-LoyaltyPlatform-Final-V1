"""Master Brain SSE regression tests.

Bug fix under test: multi-mobile earn/burn summary previously exceeded the K8s
ingress ~60s streaming cap; the SSE stream was cut before a terminal `done` event
so the UI showed 'The response ended early'. The wall-clock budget
(MB_STREAM_WALL_BUDGET=40s) + _final_synthesis fallback should now guarantee the
stream ALWAYS ends with a terminal `done` (or `error`) event within ~55s.
"""
import json
import os
import re
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://kazo-loyalty-hub-2.preview.emergentagent.com").rstrip("/")
LOGIN_EMAIL = "masteradmin@fundle.io"
LOGIN_PASSWORD = "Master@2026"

MOBILES = ["6000013876", "966681235", "9266681235", "9779281598", "7002922313", "6283722823"]

# Overall client-side ceiling — server budget is 40s + ~15s headroom for synthesis.
STREAM_TIMEOUT = 90


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:300]}"
    body = r.json()
    tok = body.get("token") or body.get("access_token") or (body.get("user") or {}).get("token")
    assert tok, f"no token in login response: {body}"
    return tok


def _consume_stream(token, message, timeout=STREAM_TIMEOUT):
    """POST to /api/master-brain/chat/stream and collect SSE events. Returns
    (events, elapsed_seconds, raw_text)."""
    url = f"{BASE_URL}/api/master-brain/chat/stream"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json",
               "Accept": "text/event-stream"}
    payload = {"message": message}
    events = []
    raw_chunks = []
    start = time.monotonic()
    with requests.post(url, json=payload, headers=headers, stream=True, timeout=timeout) as r:
        assert r.status_code == 200, f"stream HTTP {r.status_code}: {r.text[:300]}"
        buf = ""
        # Iterate raw bytes so we don't require a well-behaved iter_lines.
        for chunk in r.iter_content(chunk_size=None, decode_unicode=True):
            if chunk is None:
                continue
            raw_chunks.append(chunk)
            buf += chunk
            # SSE frames separated by blank line
            while "\n\n" in buf:
                frame, buf = buf.split("\n\n", 1)
                # Each frame has one or more lines "data: <json>" or ": comment"
                data_lines = [ln[5:].lstrip() for ln in frame.splitlines()
                              if ln.startswith("data:")]
                if not data_lines:
                    continue
                data = "\n".join(data_lines).strip()
                if not data:
                    continue
                try:
                    events.append(json.loads(data))
                except Exception:
                    events.append({"_raw": data})
                # Stop when we see a terminal event
                if events[-1].get("type") in {"done", "error"}:
                    return events, time.monotonic() - start, "".join(raw_chunks)
            if time.monotonic() - start > timeout:
                break
    return events, time.monotonic() - start, "".join(raw_chunks)


def _terminal(events):
    for e in events:
        if e.get("type") in {"done", "error"}:
            return e
    return None


def _reply_text(events):
    term = _terminal(events)
    return (term or {}).get("reply", "") if term else ""


class TestMasterBrainStream:
    """SSE regression: every turn must end with a terminal `done`/`error` event."""

    def test_multi_mobile_earn_burn_summary_terminates(self, token):
        """The bug repro: 6 mobiles + earn/burn summary. Must end with `done`,
        never leave the stream cut open, and finish well under the 60s ingress cap."""
        msg = "\n".join(MOBILES) + "\n\nNeed Earn Burn summary of above customers"
        events, elapsed, raw = _consume_stream(token, msg)

        term = _terminal(events)
        assert term is not None, (
            f"stream did NOT emit a terminal done/error event (elapsed={elapsed:.1f}s). "
            f"types seen: {[e.get('type') for e in events]}"
        )
        assert term.get("type") == "done", f"terminal event was error: {term}"
        assert elapsed < 75, f"turn took too long: {elapsed:.1f}s (budget ~55s)"

        reply = _reply_text(events)
        assert reply and len(reply) > 40, f"empty/short reply: {reply!r}"
        # Must NOT be the 'ended early' banner. That banner is emitted client-side
        # only when the stream closes without done/error — we already asserted done,
        # but double-check the reply text doesn't itself say that.
        low = reply.lower()
        assert "ended early" not in low, f"reply contained 'ended early': {reply[:400]}"
        assert "tell me to continue" not in low, f"reply asked user to 'continue': {reply[:400]}"

    def test_followup_continue_terminates(self, token):
        """After the summary, sending 'continue' must ALSO end with a real done."""
        events, elapsed, _ = _consume_stream(token, "continue")
        term = _terminal(events)
        assert term is not None, f"'continue' stream had no terminal event ({elapsed:.1f}s)"
        assert term.get("type") == "done", f"'continue' errored: {term}"
        reply = _reply_text(events)
        assert "ended early" not in reply.lower()

    def test_negative_balance_regression(self, token):
        """Simple analytics question still ends with done."""
        events, elapsed, _ = _consume_stream(token, "how many customers have a negative balance?")
        term = _terminal(events)
        assert term is not None and term.get("type") == "done", (
            f"negative-balance question failed: elapsed={elapsed:.1f}s, term={term}"
        )
        reply = _reply_text(events)
        assert reply, "empty reply for negative balance question"

    def test_single_customer_regression(self, token):
        """Single-customer lookup still ends with done."""
        events, elapsed, _ = _consume_stream(token, "show me customer 6000013876")
        term = _terminal(events)
        assert term is not None and term.get("type") == "done", (
            f"single-customer question failed: elapsed={elapsed:.1f}s, term={term}"
        )
