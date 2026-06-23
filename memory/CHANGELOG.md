# CHANGELOG — KAZO Fundle Platform

(PRD.md holds the full problem statement, architecture, data rules and history.
This file appends what was implemented, newest first.)

---

## 2026-06-23 — Fix: "CSV export failed" on customer drill-down (iter 32, 3/3 PASS)

⚠️ Redeploy required for production.
- **Root cause:** `POST /api/dashboard/drilldown/csv` broke under Starlette's `BaseHTTPMiddleware`
  — a streaming/large response on a POST that carries a body raises
  `RuntimeError: Unexpected message received: http.request`, sending HTTP 200 then 0 bytes,
  which the UI surfaced as "CSV export failed". (A plain `Response` on POST hit the same path.)
- **Fix:** converted the drill-down CSV export to **GET** (`/api/dashboard/drilldown/csv`) with
  JSON-encoded query params (collection/filter/sort/columns), on a deadline-free `export_router`,
  with column projection + `allowDiskUse(True)` and a 50,000-row cap. Frontend `DrillDownModal.jsx`
  now calls `api.get(..., {responseType:'blob'})`. Verified: GET 200 text/csv, 50k rows in ~0.5s.
- **Full-DB export hardened:** CRM Customer Report export (`GET /api/kpi-reports/crm-customers/export`)
  now uses `allowDiskUse(True)`, a minimal column projection, and cap raised to 2,000,000 — streamed
  the full 800k-row base (~112MB) in ~25s. This is the tool for exporting the entire customer database.
- Added a note in the drill-down modal (when total > 50k) pointing users to the CRM Customer Report
  for the full list.

---

## 2026-06-22 — Live Monitor default + 4 reports from client Excel/CSV formats (iter 31, frontend 6/6 PASS)

⚠️ Redeploy required for production. All verified (testing_agent iteration_31 frontend 100%; backend curl-verified).

- **Login landing + nav order** — Live Bill Monitor is now the `/admin` index route (login lands here)
  and the FIRST item in the DASHBOARDS sidebar group; Command Center is second (now at
  `/admin/dashboards/command-center`). (`App.js`, `AdminLayout.jsx`)
- **New backend module `reports_kpi_routes.py`** (`/api/kpi-reports/*`, db_deadline + deadline-free
  export router):
  - `GET /store-kpi` (+ `/store-kpi/export`) — per-store KPIs grouped by store_id: Overall Sales,
    Discount, Net-before-tax, Tax, Fresh/Return bills & value, New/Repeat txns & ATV, Mapped/Unmapped
    txns, Overall/New/Existing customer counts (distinct via $addToSet), Overall ATV. Optional YoY
    `compare=true` (prior 1–2 years, growth%). Store identity backfilled from the stores master when
    bills lack denormalized fields.
  - `GET /crm-customers` (+ `/export`) — customer master (mobile, name, city/state, tier, card_validity,
    points balance/redeemed, total billing, visits, days-since-visit, last/first visit, DOB/DOA) with
    filters (search, city/state, tier, card validity, recency, min/max visits/points, min billing),
    sorting, pagination, streamed CSV export.
  - `GET /crm-summary` — tier mix, recency buckets, top cities, totals (for the report charts).
  - `GET /trend` — sales/discount/bills/returns/new/repeat/customers bucketed day/week/month.
  - `GET /filter-options` — zones, cities, store_classes, tiers, card_validities, states.
- **New frontend reports** (under REPORTS sidebar group), all with sortable columns, rich filters,
  show/hide **column picker**, charts, and CSV export — built on a shared `reportkit.jsx`
  (`useColumns` + `ColumnPicker` + `ReportTable`):
  - `StoreKPIReport.jsx` (`/admin/reports/store-kpi`) — KPI tiles, Top-10 sales bar, New-vs-Repeat
    stacked bar, YoY toggle that surfaces growth columns.
  - `CRMCustomerReport.jsx` (`/admin/reports/crm-customers`) — KPI tiles, tier donut, recency bar,
    top-cities bar, paginated table (~800k customers).
  - `KPITrends.jsx` (`/admin/reports/kpi-trends`) — daily/weekly/monthly Sales area, Bills-vs-Returns
    bar, New/Repeat/Customers line; client-side CSV export.
- **Shopper Bill Report** — added a **Store Class** column + the shared column show/hide picker.
- Source reference files mapped: MARCH KPI / Store_wise_KPI → Store KPI; CRM_Report.csv → CRM report;
  Weekly_KPI → KPI Trends; "sale report …may" lifecycle/class → Shopper Bill Report recency + Store Class.

---

## 2026-06-22 — Kazo_Dashboard_Changes DOCX: 7 dashboard fixes (iter 30, frontend 7/7 PASS)

Client DOCX listed 7 changes. All implemented + verified (testing_agent iteration_30 = 100%
frontend; backend curl-verified). ⚠️ Redeploy required for production.
- **#1 Live Monitor Export CSV** — new `lm-export` button in the header streams the
  cockpit bills (honours current filters/window) via `GET /api/live-monitor/export`
  (endpoint already existed; only the button was missing). `LiveMonitorPage.jsx`.
- **#2 Store name shown twice** — production store master was bulk-uploaded more than once
  (two docs per physical store, different ids/codes, same NAME). De-duplicated the Live
  Monitor store dropdown by name (`storeOptions` useMemo).
- **#3 Customer 360 jump-search was broken** — `jumpToCustomer` read `r.data.customers`,
  but `/customers` returns `{total, items}` → always "No customer found". Fixed to read
  `r.data.items`. Now navigates without clicking Back. `CustomerDetail.jsx`.
- **#4 "View transactions" showed same gross on every bill** — ROOT CAUSE: historic ingest
  mapped `gross_amount` from the `"Total Billing Lifetime"` column, a customer-level running
  total repeated on every bill row. Removed that column from the per-bill `bill_amount`
  mapping (`historic_routes.py`). Read-time fix for existing data: rewrote the Customer 360
  drilldown columns to drop the buggy Gross column and show per-bill **Net (pre-tax) / Tax /
  Discount / Bill Amount (= net+tax) / Net** instead. `CustomerDetail.jsx`.
- **#5a Visit count 11 vs 12** — the stored `visit_count` counted RETURN bills too and could
  be stale. Customer 360 (`customer_360_v2`) now computes **Visits = purchase (non-return)
  bills live**, plus `returns` + `net_bill_cuts`; `rfm.frequency` uses it too. Shopper Bill
  Report `total_visits` now uses the same live sale-bill count (`_visit_map` adds `sale`).
  The two reports now agree (verified 14 visits / 9 net cuts for mobile 966681235).
- **#5b Recency Dormant/Lapsed returned no rows** — the Shopper Report's default 30-day
  date window intersected to zero for those buckets (their bills are old). Frontend now drops
  the date range when recency ∈ {dormant, lapsed} (hint shown). Also added a post-enrich
  re-validation (`_recency_bucket`) so the index-backed pre-filter (which uses the sometimes
  stale `customers.last_visit_at`) can no longer surface a mislabelled row (no "Active" under
  "Lapsed"). Bonus UX: a specific search (`q`) also ignores the date range so a mobile's bills
  are always found.
- **#6 Lifetime Purchase = Net WITH tax, EXCL discount** (user choice: everywhere) — Customer
  360 "Lifetime Spend" KPI + RFM Monetary now use `lifetime.paid` (= net_before_tax + tax,
  discount excluded). Shopper Report `lifetime_purchase` already used this. Verified ₹5,000
  (not ₹6,000 gross) for mobile 966681235.
- **#7 Support Desk → Update Mobile Number** — new page `support_desk/UpdateMobile.jsx`
  (nav `nav-sd-mobile`, route `/admin/support-desk/update-mobile`): search a customer by
  current mobile → enter new mobile + reason → `POST /api/support-desk/update-mobile`
  fully re-keys all history (bills/points/coupons/OTP/messages/NPS/tickets) to the new number
  while preserving the old number on the record; result panel shows rows-rekeyed per
  collection. Backend was already built & tested.

---

## 2026-06-17 — Exact 2-decimal amounts + IST date consistency (iter 73)

Two user-reported issues fixed (live retail data — exactness matters):
- **Rounding → exact 2 decimals.** `lib/format.js`: new **`fmtMoney2()`** (Indian commas, always
  2 dp, **no Cr/L/K compaction**, "—" for empty, sign-aware) now used in EVERY report / table /
  detail / drill-down / Live-Monitor amount cell. `fmtINRFull` (tooltips) → 2 dp. `fmtINR` (kept
  for dashboard KPI tiles, **compaction retained per user choice 1b**) → K tier bumped to 2 dp.
  Converted ~23 files (legacy_reports/*, raw_reports/*, Reports, ShopperBillReport,
  _TransactionDrill, _customer_drawer, CustomerDetail, Customer360, ItemMaster, Reconciliation,
  LiveMonitor inline `Math.round().toLocaleString()` cells, CampaignManager, LoyaltyConfigurator,
  StoreOps). Verified: 248/248 amounts exact 2-dp on Shopper report; tiles still compact.
- **Off-by-one date (IST vs UTC).** Root cause: dashboard renders `bill_date` in IST while the AI
  Brain / reports string-sliced the raw (often UTC) value → bills 00:00–05:30 IST showed the
  previous day. Fix (read-time only, no data migration): added **`fmtDateISO()`** (IST, keeps
  YYYY-MM-DD) + reused `fmtDateTimeISO`; replaced raw `.slice(0,10/16)` in legacy report date
  columns. Shopper report backend now renders date/time in IST (`_to_ist_parts` + `$dateToString`
  tz `Asia/Kolkata`; naive treated as IST to match the frontend parser). AI Brain system prompt +
  data dictionary instructed to ALWAYS format/group dates with `timezone:"Asia/Kolkata"`.
- **Verified:** pytest iter73 8/8; testing_agent **iteration_29 frontend 100%** (no crashes, exact
  2-dp everywhere, tiles compact, IST dates confirmed). ⚠️ Redeploy required for production.
- Backlog note: `/admin/raw-reports` (RawReportsPage) slow to settle (>25s) — perf follow-up.

---

## 2026-06-17 — NEW: Shopper Bill Report (bill-level report) under REPORTS (iter 73)

Client asked for a bill-level report of everyone who shopped in a date range, with 22
columns and "all possible filters + sorting + date range". Built as a dedicated page
(`/admin/reports/shopper-bills`, nav `nav-shopper-bills` under REPORTS).
- **Columns (one row per BILL):** Bill Date · Time · Bill Type (Return/Regular —
  *Exchange is treated as Return per client*) · Customer Mobile · Reg Store (CRM
  registration store) · Store Code · Trans Store Name · Trans ID · Bill # · Customer
  Type (New/Existing) · Recency · Last Visit · 2nd-last Visit · Total Visits · Zone ·
  Customer City · Net before tax · Total Tax · Total Discount · Total Bill Amount ·
  Lifetime Purchase · Lifetime Bill Cuts (**NET** = sale bills − return bills).
- **Recency (from TODAY back to last visit):** Active 0-6M / Dormant 6-12M / Lapsed 12M+.
- **Backend `routes/shopper_report_routes.py`** (2 routers): `GET /shopper-report/bills`
  (paginated listing + 22-col contract), `GET /shopper-report/filter-options`
  (stores+zones), and `export_router GET /shopper-report/export` (streamed CSV, OWN
  router with NO db_deadline so a large export streams; per-batch enrichment wrapped in
  its own pymongo.timeout; cap 200K rows).
- **Scale-safe design:** non-recency listing = indexed find on bill_date + page-scoped
  enrichment (customer lookup + a bounded per-mobile aggregate for 2nd-last-visit & net
  bill cuts + store-master preload). Recency filter (a customer attribute → needs a join)
  uses sort-FIRST (index-backed) → indexed point `$lookup` → bucket `$match` → `$limit`
  (short-circuits; no full-set `$facet`/count) with `maxTimeMS` guard → friendly 400 if
  too heavy; exact total intentionally omitted for that path (`has_more` drives Next).
- **Frontend** `ShopperBillReport.jsx`: date range + quick presets (7d/30d/90d/MTD/1y),
  Bill Type / Customer Type / Recency / Store / Zone / City / search filters, clickable
  sortable headers (bill_date, mobile, bill #, bill amount, trans store), 50/100/200
  page sizes, Prev/Next, colored Bill-Type & Recency badges, "Download CSV".
- **Verified:** pytest `tests/iteration73_shopper_report_test.py` 8/8; testing_agent
  iteration_28 frontend **100%** (filters, header sort, pagination, recency path, CSV
  download all working at 1.5M-txn preview scale). ⚠️ Redeploy required for production.

---

## 2026-06-11 — FIX production deployment MaxTimeMSExpired on dashboards (iter 70)

Production Atlas connection string uses an aggressive `timeoutMS=10000`. The customer-dashboard
ran 9 sequential full-collection-scan aggregations on `customers` and blew past 10s →
`pymongo.errors.ExecutionTimeout` (MaxTimeMSExpired, code 50), 500-ing the endpoint
(`analytics_routes.py:221` recency_pipe). Fixes (code only, no infra):
- **$facet consolidation**: the 7 heavy bucketing aggregations (churn/freq/city/health/
  recency/onetimer/lifecycle) collapsed into ONE `$facet` = a single collection scan instead
  of seven. `top` (lifetime_spend index) and `new` (first_purchase_at index) kept as cheap
  separate queries. Each wrapped in try/except `PyMongoError` → degrades to empty buckets
  (HTTP 200) instead of 500.
- **`db_deadline` dependency** (`routes/_db_timeout.py`): `pymongo.timeout(45)` attached to the
  analytics + dashboard routers, overriding the aggressive client `timeoutMS` for heavy
  endpoints. VERIFIED pymongo.timeout() propagates through Motor 3.3.1 (timeoutMS=1 → raises;
  with override → completes).
- deployment_agent: PASS (no hardcoded env/secrets/ports; MONGO_URL/DB_NAME env-only).
- Tests: `iteration70_dashboard_timeout_test.py` — PASS. customer/sales/kpis dashboards all 200.
- **ACTION: redeploy to production.**

---


## 2026-06-10 (cont.4) — SMS intermittent ConnectTimeout: safe retry mitigation

Production Message Log showed "some Sent / some Error" where Error = `ConnectTimeout` (even
within the same minute) → deployment egresses via a POOL of IPs and Karix has whitelisted only
SOME of them. Requests via a whitelisted IP succeed; others are dropped.
- Mitigation: `send_sms_karix` now RETRIES connect-level failures only (`httpx.ConnectTimeout`
  / `httpx.ConnectError`), up to 4 attempts with small backoff, connect timeout 8s. SAFE — the
  connection was never established so Karix never received the request (no duplicate SMS). Read
  timeouts are NOT retried. Logs "delivered on attempt N/4" when a retry succeeds.
- Real fix (infra): whitelist the FULL production egress IP range/CIDR at Karix (get the list /
  a static egress IP from Emergent Support). One IP is not enough.
- Separate: all rows show DLT TEMPLATE = none → even "Sent" may be carrier-dropped at handset.
  Re-adding the per-template DLT Content Template ID would guarantee handset delivery (client
  had it removed). Pending client decision.
- **ACTION: redeploy to production for the retry to take effect.**

---


## 2026-06-10 (cont.2) — Karix QueryStringReceiver exact param set + egress finding

- Per client instruction, `send_sms_karix` now sends EXACTLY the KAZO Karix QueryStringReceiver
  param set: `ver=1.0, key, encrpt=0, dest, send, dlt_entity_id, text`. Removed
  `dlt_template_id` / `dlt_tm_id` from the outgoing request (kept in DB/UI). `dlt_entity_id`
  is always included. NOT migrating to the JSON `JsonReceiver` API (client chose QueryString).
  Karix response is logged to the Message Log for accept/reject visibility.
- KEY (config-driven, already default): `8iRt9ytmxeyMgtpdMdOpMw==`.
- EGRESS DIAGNOSIS (infra, not code): preview egress IP rotated across sessions
  (34.16.56.64 → 35.225.230.28) — stable within a session, changes on restart/redeploy.
  control_internet/google = 200 but Karix host = ConnectTimeout → host/IP-specific block
  (Karix allow-list dropping the non-whitelisted, rotating egress IP). Resolution requires a
  STATIC egress IP / CIDR from Emergent Support, then whitelist that at Karix. No code fix.

---


## 2026-06-10 (cont) — Block points redemption on DISCOUNTED bills/items (iter 69)

Client rule: redemption is allowed ONLY when discount is zero. If the POS sends any non-zero
discount (bill-level `discount` or any line item's `discount`/`Discount`), reject with
"Redemption is not allowed on discounted items."
- New helper `_redemption_discount(payload)` sums bill + item discounts (handles both
  `discount` and `Discount` key casings).
- Enforced at `posRedeemPointRequest` (before any OTP is issued) AND `posRedeemPointOtpCheck`
  (defense-in-depth).
- Test: `iteration69_redeem_discount_block_test.py` — PASS.
- **ACTION: redeploy to production to go live.**

---


## 2026-06-10 — posRedeemPointOtpCheck: ignore `points` on verify + validate LAST OTP (iter 68)

Client hit a live 400 "Redemption amount mismatch — OTP was issued for 250…" because the
eWards POS sends `points: "0"` on `posRedeemPointOtpCheck` (the amount is fixed earlier at
`posRedeemPointRequest`). Two changes per client instruction:
- **Stopped checking the `points` field on verify.** The authoritative redemption amount is
  now taken from the OTP session's `payload_snapshot.points` (the amount the OTP was issued
  for); the `points` value sent on the verify call is ignored.
- **Validate the LAST OTP.** Verify now fetches the MOST RECENT redeem OTP for the mobile and
  requires the submitted value to equal it; once a newer OTP is issued, older OTP values are
  rejected as "Invalid OTP."
- Test: `iteration68_redeem_verify_ignore_points_last_otp_test.py` — PASS (iter66/67 still PASS).
- Also (per client): Support Desk "Search Redeem Points/Coupon OTP" now shows the OTP value
  (the `otp_demo`) instead of the Redeem ID, for manual redemption while SMS is unreliable.
- **ACTION: redeploy to production to go live.**

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

## 2026-06-11 — Dashboards/Reports super-audit + RECON + AI data expert
- Reproduced production ₹0 dashboards locally by seeding 800K customers / 1.5M txns (perf_seed, purged after): root cause = silent query timeouts + scale-breaking patterns.
- Fixed 4 endpoints that hard-failed (500/502) at scale: city-performance, executive-summary (distinct+giant-$in), store-performance-v2 ($addToSet 16MB), analytics store-dashboard.
- RFM rewritten: index-backed quantile cuts + $facet bucketing (was silently truncating at 100K customers → wrong numbers).
- Cohorts-segmentation: Mongo-side retention triangle + customers-master $facet (was pulling 500K rows into Python).
- Command Center: 16 queries → 3 facet scans + `degraded[]` flag + amber retry banner (no more silent ₹0); cache skips degraded responses.
- KPIs endpoint: 14 sequential scans → 1 customers facet + gather.
- points-economics: 8 sequential scans → 2 facets + gather (31s → 9s → 0.1s cached).
- NEW `_dash_cache.py` TTL cache (5 min) on 20 heavy endpoints; preserves typed signatures (FastAPI body binding fix from testing agent).
- All report routers now under db_deadline (45s) — fixes "legacy reports not opening" under prod 10s client timeout.
- Legacy reports: batch lookups (expiry-points N+1 of 2000 find_ones, location-wise), offset pagination on 7 reports, CSV export limit→10K, frontend Prev/Next pagination + error retry UI in _shell.jsx.
- Raw reports: repeat-purchases fully Mongo-side ($top first-bill), drill paging via $facet (no 16MB distinct), tier filter via cursor aggregation.
- Drill-down bug fixes: month drill compared datetimes to ISO strings (always empty); Command Center cohort drill used created_at instead of first_purchase_at; customer scope used non-existent preferred_store_id (→ home_store_id).
- Date-range fixes: "365d" preset fell back to 30d; sales-trend ignored custom start/end; loyalty/customer trends now respect window with monthly buckets; "" categories/cities → Uncategorised/Unknown.
- /historic-data/reconcile scale-safe ($unionWith anti-join replaces distinct()).
- NEW RECON module (/api/recon/*): chunked CSV re-upload → row-level CSV↔DB compare (missing/amount/mobile mismatches, extra-in-DB, sums) + mismatch CSV download + UI section on Reconciliation page.
- AI Fundle Brain: live data-warehouse snapshot system message (cached 10 min) + run_aggregation/get_data_dictionary guard-railed tools — verified expert answers over full dataset.
- New indexes: points_ledger.bill_date, message_log.created_at, transactions.city/store_name.
- Testing: iteration71 pytest suite (30/30 after fixes), testing agent E2E (frontend pass incl. Command Center, pagination, recon UI).

## 2026-06-11 (later) — Segment Builder/Sales Report P0 fix + AI Brain raw-data & formatting upgrade
- P0 FIX: cohort-library `build_context()` (full 1.5M-bill ATV aggregate) now TTL-cached (10 min) + per-cohort counts cached with bounded concurrency (Semaphore(6)) — list 5s→0.1s, counts 6s→0.16s warm. This was stalling Segment Builder AND saturating the Mongo pool for other dashboards.
- P0 FIX: Sales Report "Loading…" hang — `_dash_cache` upgraded to stale-while-revalidate (serve stale ≤1h instantly, refresh in background) + NEW `_cache_warmer.py` background task (every 4 min, warms 8 heaviest default views via localhost with minted super-admin JWT). Sales dashboard now renders in ~1.3s.
- AI Brain CSV EXPORT: new `export_csv` tool streams up to 1M rows to /app/backend/exports/ai (568,982 one-timers → 52MB CSV in 3.8s); download via auth-protected GET /api/ai/exports/{id} (202 while preparing, 404 unknown). Chat presents Markdown download link → styled download button in UI.
- AI Brain FORMATTING: react-markdown + remark-gfm; new `_markdown_message.jsx` renders GFM tables/bold/bullets/headings with KAZO styling; system prompt mandates Markdown tables + ₹ Indian formatting.
- AI Brain MODELS upgraded: GPT-5.5 (default), Claude Sonnet 4.6, Claude Opus 4.8, Gemini 3.1 Pro (was gpt-5.2/sonnet-4-5/gemini-2.5-pro). MAX_TOOL_ITERATIONS 6→8.
- AI Brain EXPERTISE: warehouse snapshot enriched with brand KPI digest (lifecycle split, tier split, all-time revenue/ATV, top stores 90d) + DATA PROVENANCE note (568K master-CSV customers have no bill-level rows — query customers collection for customer lists).
- BUG FIX: `get_data_dictionary` tool had broken signature (every call returned "Bad arguments") — fixed.
- P3 FIX: React "<span> cannot be a child of <option>" hydration warning — mixed static+dynamic option children converted to single template literals (CommandCenter, CampaignManager, AutoCampaignsPage).
- Testing: iteration_27 (testing agent) — backend 18/18 pytest, frontend 100%; pytest suite at /app/backend/tests/iteration72_perf_ai_brain_test.py.
- NOTE: fixes live in PREVIEW — user must redeploy to push to kazoloyalty.fundlebrain.ai.

## 2026-06-12 — Fundle Brain locked to single best agent + decisiveness hardening
- User reported "AI Brain has no capability" — screenshots were from PRODUCTION (kazoloyalty.fundlebrain.ai) still running the OLD build (raw pipe tables, data:URL hacks, tool-call limit). All previously fixed in preview; REDEPLOY required.
- Removed the model dropdown (user request) — Fundle Brain now runs on ONE locked engine: Claude Sonnet 4.6 (API override params kept for tests; "gpt"→gpt-5.5, "opus"→opus-4-8, "gemini"→3.1-pro).
- Decisiveness rules in system prompt: never ask clarifying questions before data pulls (state assumption + execute), never data:URLs/copy-paste CSV hacks (export_csv is the only file channel), max 1 dictionary call, fix-and-retry-once on pipeline errors.
- items[] schema hints ($size for per-bill item count, $unwind for item analysis) added to system prompt + run_aggregation description + field notes.
- Tool-loop cap raised 8→10 and graceful: on cap, forces a final synthesis answer (table + export link) instead of "(Reached tool-call limit)".
- E2E verified with the user's exact failing prompt "list of people who shopped 2+ items in their bill in last 6 months" → stated assumption, found data nuance (1 item-line/bill → used quantity sum), exported 52,740 customers CSV with working download button + metrics table.

## 2026-06-23 — Downloads Center fully wired (centralized async CSV exports)
- COMPLETED the orphaned Downloads Center: registered `<Route path="downloads" element={<DownloadsCenter/>}/>` in App.js and migrated EVERY server-side report export to the shared `requestExport()` helper (`/app/frontend/src/lib/exportClient.js`).
- Migrated export buttons → `requestExport()`: Store KPI Report (skpi-export), CRM Customer Report (crm-export), Shopper Bill Report (sbr-export), Live Bill Monitor (lm-export), Drill-down modal (drilldown-csv), and ALL legacy reports via shared `legacy_reports/_shell.jsx`.
- UX per user spec: small exports (known_total <= 5000) generate inline + download instantly with toast "Download started"; large exports run in a background task → toast "Download started · find it in the Downloads section" + sidebar badge + "Report ready" toast when complete. Files stored in Emergent object storage, auto-expire after 7 days.
- Per user choice: Customer 360 (cust-export-csv) and KPI Trends (trend-export) intentionally kept as INSTANT client-side downloads (NOT routed through Downloads Center).
- Backend: extended `exports_routes.py` REGISTRY with 11 legacy report types; added `export=csv` support to 3 legacy endpoints that lacked it (fraud-report, missed-calls, location-wise-customers).
- Removed dead `API_URL`/`toast` imports from the 4 migrated KPI/report pages.
- TESTED: backend via curl (instant + async 800,061-row CRM export completed to Ready/107.5MB, downloads return valid CSV); frontend via testing agent iteration_33 → 10/10 scenarios PASS, no bugs.
- NOTE: fixes live in PREVIEW — user must REDEPLOY to push to production.

## 2026-06-23 (later) — Re-tier old (pre-POS) customers from configured tier ranges
- NEW FEATURE (P1, was backlogged): "Update Old Data · Re-tier Customers" section added to the Loyalty Rules page (`_retier_section.jsx` + wired into `LoyaltyConfigurator.jsx`).
- Problem: ~240k pre-POS historical customers carried stale "dummy" tiers (Gold/Platinum despite ~₹3,400 avg billing). New POS customers (created >= 2026-06-08) are correct and must not be touched.
- Backend (`loyalty_routes.py`): 3 new endpoints —
  - `POST /loyalty/retier/preview` {cutoff_date} → before→after tier distribution + changed count (single $switch aggregation, read-only).
  - `POST /loyalty/retier/apply` {cutoff_date} → background job, idempotent bulk `update_many` per tier band (uses ix_cust_created/ix_cust_lifetime_spend/ix_cust_tier), progress tracked in `retier_jobs`.
  - `GET /loyalty/retier/status` → latest job progress (status/updated/total/per_tier).
- Logic is fully CONFIG-DRIVEN: tiers + DISPLAY NAMES read live from `loyalty_config.tier_rules` (mirrors `historic_routes._derive_tier` — highest band whose min_lifetime_spend is reached). So on production it uses the brand's custom tier names (Kazo Insider, Kazo Trendsetter, etc.) automatically. Zero/no billing → lowest configured tier.
- Scope: ONLY `created_at < cutoff` (default 2026-06-08, configurable in UI). POS customers untouched.
- TESTED in preview (curl + screenshot): preview=239,790 changed (798,459 old custs), apply completed (239,092→silver, 698→gold), re-preview=0 changed (idempotent), POS custs (>=2026-06-08) confirmed untouched, UI renders with progress + before/after tables.
- NOTE: live in PREVIEW. User must REDEPLOY, then on production open Loyalty Rules → Re-tier Customers → Preview → Apply.

## 2026-06-23 (fix) — Re-tier matched 0 on production → switched to source-based identification
- BUG: On production the re-tier matched 0 customers. Root cause: imported customers' `created_at` is the IMPORT timestamp (set via datetime.now() in historic_routes), NOT their join date — so a master-CSV uploaded after the cutoff made every old customer's created_at > cutoff, excluding them all from the `created_at < cutoff` filter.
- FIX (`loyalty_routes.py` + `_retier_section.jsx`): added a `mode` to /loyalty/retier/{preview,apply}.
  - mode="source" (NEW DEFAULT, recommended): old = `source $nin [pos_ewards, pos_auto, pos_auto_customer_key, pos_test_seed]`. Reliable regardless of import date; excludes only live POS customers.
  - mode="date" (kept as fallback): old = created_at < cutoff.
  - preview now returns a `source_breakdown` (count per source, is_pos flag) so the user can SEE exactly which customers are included/excluded.
- UI: radio toggle (Historical-not-from-POS vs Created-before-date), date input shown only in date mode, source-breakdown chips (POS sources struck-through), note clarifies "no points awarded — only tier label changes".
- TESTED in preview: source-mode preview classified sources correctly (pos_ewards/pos_test_seed excluded), caught 5 deliberately-corrupted historic customers + ~487 non-POS customers the date filter had missed, applied (492 updated), re-preview = 0 (idempotent). Frontend compiles + renders.
- ACTION: user must REDEPLOY, then on production: Loyalty Rules → Re-tier Customers → keep "Historical (recommended)" → Preview (verify source breakdown) → Apply. If the production POS source name differs from "pos_ewards", the breakdown will reveal it and the exclusion list can be adjusted.

## 2026-06-23 (fix 2) — Re-tier Atlas timeout → batched single-pass job
- BUG (production): "Last run failed: ...mongodb.net:27017: The read operation timed out". The single bulk update_many over hundreds of thousands of Atlas docs exceeded the socket read timeout.
- FIX (`loyalty_routes._run_retier`): rewrote as a single paginated pass — batches of 1000 ordered by _id (find {_id:$gt:last} + projection, max_time_ms 45s), derive correct tier in Python, bulk_write ONLY the diffs (UpdateOne by _id). No single DB op runs long → no socket timeout. Reports processed/total + updated live. apply count_documents now has maxTimeMS=15000 fallback to estimated_document_count.
- Frontend (`_retier_section.jsx`): progress bar now uses processed/total ("X scanned · Y re-tiered · Z%"). Rewrote file fully (prior parallel same-file edits had raced/corrupted it).
- TESTED in preview: scanned all 800,053 old customers, updated exactly the 10 corrupted records, completed fast; UI renders. 
- ACTION: user must REDEPLOY, then re-run Apply (source mode) on production — it will now complete with a live progress bar.
- INTERNAL LESSON: never issue multiple parallel search_replace calls on the SAME file (they race and corrupt/revert it). Edit one file sequentially.
