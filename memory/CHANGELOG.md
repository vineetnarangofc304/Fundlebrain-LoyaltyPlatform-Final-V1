# CHANGELOG — KAZO Fundle Platform

(PRD.md holds the full problem statement, architecture, data rules and history.
This file appends what was implemented, newest first.)

---

## 2026-06-09 (cont.3) — 🔴→🟢 FIXED recurring "Invalid OTP" on POS redemption (iter 67)

**Root cause (the real "configuration disconnect"):** there were TWO separate POS
redemption implementations writing OTPs to TWO different Mongo collections:
- eWards / x-api-key flow (`pos_ewards_routes.py`) → `pos_otp_sessions`
- legacy `/pos/*` flow (`stores_routes.py` `pos_router`) → `otps`
An OTP issued by one flow could never be verified by the other → permanent "Invalid OTP".
The bare `"Invalid OTP"` string (no period) the client saw is the legacy `stores_routes.py`
message; the eWards one returns `"Invalid OTP."` with diagnostics.

**Verified in preview:** the eWards flow (the one KAZO's POS actually uses with x-api-key)
ALREADY works correctly end-to-end, even with a +91 / leading-0 format mismatch — i.e. the
previous mobile-normalization fix is correct but **was never redeployed to production** (why
the client still saw failures).

**Fix (unification):** `stores_routes.py` legacy `/pos/issue-otp`, `/pos/redeem-points` and
`/pos/validate-customer` now read/write the SAME canonical `pos_otp_sessions` collection
with the same last-10-digit `_norm_mobile`/`_mobile_key` matching and the same
`_otp_failure_reason` diagnostics. Any OTP from either flow now resolves; wrong OTP returns a
precise reason instead of bare "Invalid OTP". Removed dead `otp_col`/`random` usage in
stores_routes.
- Tests: `iteration67_unified_otp_redeem_test.py` (cross-flow A & B + diagnostic) — PASS;
  `iteration66` still PASS.
- **ACTION REQUIRED: client must REDEPLOY to production for any of this to go live.**

---


## 2026-06-09 (cont.2) — 🟢 TIER-DRIVEN earning + full POS flow correctness (iter 60)

Client confirmed the canonical flow: bill → (auto-register if new) → earn by TIER → SMS;
redemption → OTP to the redeeming mobile → validate by mobile+OTP → reduce points live.
Everything reads from the saved DB config (Loyalty Rules / Templates / Provider Settings);
no dummy/fallback at send time (verified loyalty_config id="default", templates by
event+active, provider_config singleton). All preview-verified; needs production redeploy.

### 🔴 ROOT CAUSE of "no points": earn rate was 0
Recalc breakdown on prod reported `19,821 bills compute 0 — earn rate/multiplier is 0`.
The engine was `base × (% of Spend) × tier-MULT`; the client's "% of Spend" = 0, so every
bill × 0 = 0. The client's model is purely tier-driven (per-tier MULT = the rate).
- **Fix:** `_compute_earn_points` — when the Earn Engine rate is blank/0, the per-tier
  multiplier itself IS the % of the bill (mult 2 → 2%, 3 → 3%, 5 → 5%). Global-rate behaviour
  (base × rate × mult) preserved when a rate IS set. Applied to the SHARED function so
  posAddPoint, returns, Recalc, the Earn Simulator (loyalty_routes) and /pos/issue-points
  (stores_routes) are all consistent. Verified ₹5000 → 100/150/250 for mult 2/3/5
  (`tests/iteration60_tier_driven_earn_test.py`, live posAddPoint test).

### Other flow fixes (iter 59-60)
- **Auto-register → registration SMS:** posAddPoint auto-created members silently; now fires
  the front-end "registration" template on first registration.
- **loyalty_flag robustness:** earn unless POS explicitly sends 0/false/no/off (was strict
  "1"/"true" only → truthy values like "Y" wrongly suppressed earning).
- **Earn SMS:** posAddPoint fires both `purchase` and `points_earned` triggers.
- **OTP idempotency:** redeem-OTP verify matches by mobile+otp regardless of verified state;
  a retry returns success (already_redeemed) without double-deducting; atomic claim prevents
  concurrent double-deduct; only an unknown OTP is "Invalid".
- **Sender ID = Provider Settings is authoritative** (a stale per-template sender can no
  longer override it).
- **Recalc upgrade:** dry-run returns a skip breakdown (flag-off / below-min / no-customer /
  zero-rate) + earn config; new `ignore_loyalty_flag` (Force-credit) backfills bills wrongly
  stored as flag-off; UI surfaces the reason + offers Force-credit.
- **earn_skip_reason** written to API Monitor on every 0-point bill.
- **Dates:** POS `order_time` parsed strictly year-first (year-month-date) → stored ISO+IST;
  Live Monitor shows consistent `YYYY-MM-DD HH:MM`; tolerant frontend parser for old bills.

---

## 2026-06-09 (cont.) — 🔴 POS earning/SMS gaps + OTP "Invalid" idempotency (iter 59)

Preview-verified (`tests/iteration59_otp_idempotency_earn_diag_test.py` PASS + curl).
ALL need a production **redeploy** to take effect.

### 🔴 POS OTP "Invalid" at billing counter — ROOT CAUSE = non-idempotent verify
`posRedeemPointOtpCheck` matched the OTP session with `verified:False`. First submit
worked (200 + deduct), but ANY retry/double-submit (POS network retry, cashier re-tap,
slow response) hit the now-`verified:True` session → `400 "Invalid OTP"`. api_logs showed
a 200 immediately followed ~150ms later by a 400 for the same mobile.
- **Fix (`pos_ewards_routes.py`):** match the session by mobile+otp+purpose REGARDLESS of
  verified state; if it was already `redeemed`, return the SAME success (`already_redeemed:true`)
  WITHOUT deducting again; atomically CLAIM the redemption (`find_one_and_update` on
  `redeemed != true`) so concurrent duplicates can never double-deduct; only a genuinely
  unknown OTP is still "Invalid". Same `verified:False` filter dropped from
  `posCustomerOTPCheck` so customer-check retries don't false-fail.

### 🔴 Earning shows 0 for new POS bills — added self-diagnosis (code earns correctly in preview)
Earning math is correct (₹1000 → points in preview). Zero-point bills are caused by
config/payload (earn switch off / min_bill / loyalty_flag / missing `amount`). posAddPoint
now records an **`earn_skip_reason`** in the response AND the API Monitor log whenever a bill
earns 0: `loyalty_flag_off` / `earn_paused` / `zero_base` (no amount/loyalty_gross_amount/
net_amount sent) / `below_min_bill` / `computed_zero`. Lets the user see WHY on production
without server access.

### 🔴 Registration + post-transaction SMS not going
- **Registration was NEVER wired:** `posAddCustomer` fired no event. Now a NEW member fires
  `fire_event("registration", …)`. Added `"registration"` to backend `EVENTS` and to the
  Templates UI event dropdown ("On registration / welcome").
- **Post-transaction:** `posAddPoint` already fired `"purchase"` (works in preview — Karix
  returns "Platform Accepted"). It now ALSO fires `"points_earned"` so the message goes out
  regardless of which trigger the template was saved under.
- Reminder surfaced to user: `fire_event` only fires templates whose **status == "active"**
  (a "draft" template never sends); sender ID / DLT / api-key all read from saved Provider
  Settings (no dummy/fallback used at send time).

### OTP panel time → IST
`SearchRedeemPointsOTP.jsx` + `SearchRedeemCouponOTP.jsx` rendered raw UTC `created_at`.
Now use `fmtDateTime()` (Asia/Kolkata) → shows correct +05:30 India time.

---

## 2026-06-09 (cont.) — Dashboards & reports fixed at production scale

User report (full prod data loaded: ~1.1M customers, ~8.6L+ txns): raw reports all
failing to load, Command Center "all zero" + slow, Sales Dashboard not loading.

### Root cause
- **42 of 45 aggregations** in `dashboard_routes.py`, `analytics_routes.py`,
  `raw_reports_routes.py` lacked `allowDiskUse=True` → at scale a `$group`/`$sort`
  over the 100MB pipeline cap throws → 500 → "failing to load" / silent zeros.
- Command Center fires ~16 concurrent all-time scans capped at **8s `maxTimeMS`**;
  at scale they timed out and `_safe_agg` returned 0 → "all zero + slow".

### Fixes (verified: testing_agent iteration_24 = 40/40 backend + 12/12 dashboards +
5/5 raw reports + Customer 360 + Live Monitor, 100%)
- Added `allowDiskUse=True` to **all 45** aggregations (safe paren-matching pass).
- `_safe_agg`/`_safe_count` `maxTimeMS` 8s → **25s** so all-time scans complete.
- **60s TTL cache** on `/dashboard/command-center` (`_CC_CACHE`) — page auto-refreshes
  every 30s + users navigate in/out, so it's slow at most once a minute. Explicit
  **Refresh** button sends `refresh=1` to bypass the cache (fresh numbers on demand).
- **Removed hardcode**: `burn_ratio` (₹/point liability) now read from `loyalty_config`
  via `_burn_ratio()` (Loyalty Configurator drives it) instead of `= 0.25` literal.
- Swept dashboards/reports for mock/dummy/sample data — none found; all numbers are
  computed live from MongoDB.

### Customer 360 (Raw Customer Data) — earlier in this session
- Server-side **pagination** (Prev/Next, page X/Y) — was showing only the first 100.
- **Points Balance** + **Churn** columns added on-screen (balance was export-only).

### Notes / deferred
- P2 cosmetic: `<span> cannot be a child of <option>` console warning on CommandCenter
  store/city `<select>` — it's the emergent dev-tool's injected x-source spans inside
  `<option>` (preview-only tooling artifact), not our markup. Non-blocking.
- Reviewer note: ensure `loyalty_config` doc is seeded in every env so Liability KPI
  isn't 0; confirm bill_date/customer_mobile indexes exist at prod scale (they do — see
  server.ensure_indexes / iteration46).



### P0 — Historic ingest scheduler no longer hangs/loops on 126MB+ CSVs
File: `backend/routes/historic_routes.py`
- Root cause of "job lies in queue forever": long post-passes (opening-balance ledger,
  points ledger, customer-aggregate recompute, registered-store link, auto-backfill)
  wrote NO heartbeat, so the 3-min stale-recovery watchdog kept re-queueing the still-
  running job → it re-ran the whole file endlessly.
- Added `_beat(job_id)` heartbeat helper; every post-pass now beats per batch.
- Stale-recovery window widened to 8 min + **recovery cap (MAX_RECOVERIES=4)**: a job
  recovered 4× without completing is marked `failed` (chunks cleaned) — hard stop to the
  re-run loop.
- Memory: `process_pending_ingests` now **streams chunks to a temp file on disk** and
  `_run_ingest_job(csv_path=...)` reads the CSV line-by-line (O(1) memory) instead of
  joining the whole file into a ~2-4× in-memory decoded string (OOM risk). xlsx still
  stitched in-memory (small). `_recompute_customer_aggregates` now streams the aggregate
  with `allowDiskUse=True` + batched flushes + heartbeats.
- Regression test: `backend/tests/iteration57_scheduler_streaming_test.py` (PASS).
- NOTE: production already redeployed with this; a redeploy mid-ingest auto-resumes from
  stored chunks (idempotent upserts; no data loss).

### Customer 360 — search hung + detail page blank (FIXED)
- `backend/routes/fundlebrain_routes.py::customer_360_v2` queried transactions/points_ledger
  by `customer_id` — which is NULL on bulk-loaded (historic) bills and is NOT indexed →
  6 collection scans over 8.6L txns → timeout → blank page. Now queries by indexed
  `customer_mobile` (the canonical loyalty identity). NPS kept on customer_id (tiny coll).
- `backend/routes/customers_routes.py::list_customers` replaced unanchored
  `/{q}/i` regex (full COLLSCAN at 1.1M) with **anchored mobile-prefix regex** (uses the
  `{mobile:1}` index) for digit queries, anchored prefix for name/email, bounded count
  (`maxTimeMS`) and search-mode sort by mobile. `award/deduct-points` now persist
  `customer_mobile` on the ledger entry.
- `frontend/.../CustomerDetail.jsx` "View all transactions" drilldown now filters by
  `customer_mobile`.
- Verified: customer 6000535682 (id a26865d9...) shows ₹2980 lifetime, 2 visits, 2 bills.

### Live Monitor (`/admin/live-monitor`)
File: `backend/routes/live_monitor_routes.py`, `frontend/.../LiveMonitorPage.jsx`,
`backend/routes/pos_ewards_routes.py`
- **Default window = Today (IST 00:00→23:59)**; all relative windows (15m…365d) remain.
- **Store cards fixed**: excluded null-store group (was an "Unknown −₹2,957" card from
  returns); revenue = SALES only (returns split into a `returns` count); each card shows
  the store **LOC code** badge resolved from the store master.
- **LOC code** now resolves from the store master in the bills table + cards; live POS
  bills now persist `store_code` natively (pos_ewards txn_doc).
- **Row colour-coding** by bill type with a legend: Repeat=emerald, New=amber,
  Walk-in=rose, Return=orange.
- **KPI definitions**: `Total Purchase` = GROSS SALES (`gross_amount`, returns excluded);
  new `loyalty_revenue` = `Loyalty Purchase` = gross of bills where points were given
  (`points_earned>0`, returns excluded). Total ≥ Loyalty (subset) always holds.

### Validation
- testing_agent iteration_23: 7/7 acceptance criteria + 7/7 backend pytest PASS, no issues.
- Test: `backend/tests/iteration58_customer360_livemon_test.py`.

### Open / next
- Confirm whether Total Purchase = gross sales & Loyalty Purchase = points-given should
  also be applied to Command Center / Sales dashboards (currently only Live Monitor).
- P2: React `<span> in <option>` hydration warning (source NOT in `_date_range_picker.jsx`
  — that uses buttons; needs locating).
- P1 backlog: Gap-analysis Phase 2/3 (Location-wise DLT SMS, OTP audit search, Reward
  Brands, Reward GVs); modularize bloated route files.
