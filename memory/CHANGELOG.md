# CHANGELOG — KAZO Fundle Platform

(PRD.md holds the full problem statement, architecture, data rules and history.
This file appends what was implemented, newest first.)

---

## 2026-07-07 — Fix P0 (round 2): POS `NetworkTimeout` persists after pool fix → aggressive prod Atlas `timeoutMS` on the POS path

⚠️ Redeploy required for production.

- **Symptom:** After the connection-pool isolation fix was deployed, `posAddPoint` STILL returned `NetworkTimeout: ...mongodb.net: The read operation timed out` on live tills ("Working on it…" hang on the coupon/amount screens).
- **Root cause (confirmed):** Production Atlas has an aggressive client-wide `timeoutMS` (~10s). Master Brain already wraps its bulk DB ops in `pymongo.timeout(600)` to survive it — but the **POS endpoints had NO such override**, so when Atlas is momentarily slow under peak store load, a POS query breaches the ~10s client timeout and dies with `NetworkTimeout`. Verified locally: `pymongo.timeout(0.0005)` around a Motor query raises the exact same `NetworkTimeout`, and `pymongo.timeout(30)` lets it through. All relevant indexes already exist and the pool fix is deployed, so it is neither a missing index nor pool starvation — it is the client timeout being exceeded server-side.
- **Fix:** `APILogMiddleware` now wraps every `/api/pos/*` request in `with pymongo.timeout(POS_DB_DEADLINE_SEC)` (default **30s**, env-tunable via `POS_DB_DEADLINE_SEC`) — a pure-ASGI middleware so the CSOT deadline propagates into the handler's Motor ops. A slow-but-alive Atlas now DELAYS a live bill instead of failing it. Same proven pattern Master Brain uses.
- **Validated (preview):** CSOT mechanism enforced with Motor; POS endpoints respond ~0.1–0.2s with the wrap in place (no regression). Files: `backend/server.py` (import pymongo, `POS_DB_DEADLINE_SEC`, middleware wrap).
- **After redeploy, confirm on prod:** watch API Monitor — `posAddPoint` NetworkTimeouts should drop to ~0. If they PERSIST even with the 30s deadline, the Atlas cluster is genuinely saturated at peak (queries >30s) → the real fix is **scaling the MongoDB Atlas tier** (infra, via Emergent Support), not code.

---


## 2026-07-07 — Master Brain data-integrity audits + corrections (deterministic, audited, UNDOABLE) + canonical cutoff rule

⚠️ Redeploy required for production. Verified on preview via seeded apply→undo round-trips + live chat invocation.

**Canonical rule locked (user directive):** Cutoff = **2026-06-08**. Bills BEFORE = HISTORICAL → `points_balance` is the sole authoritative points, NOTHING computed. Bills ON/AFTER = LIVE POS → points computed + ledgered in real time. Master Brain must be 100% deterministic (real DB reads/writes, no LLM/guess/dummy), audited and undoable. Nothing is ever hard-deleted — corrections VOID rows (points→0, `original_points` kept, `voided_*` fields) so the trail is preserved.

- **Cutoff default corrected** `2025-06-08 → 2026-06-08` in `historic_routes.py` + `master_brain_tools.py`. This was the ROOT CAUSE of Issue #2: with the cutoff a year too early, historical 2026 bills were treated as "live" and earned computed points (e.g. SURUCHI's derived `lifetime_points_earned=2510` on a real balance of 249). Future ingests now correctly exclude pre-cutoff bills from earning. ⚠️ Production DB likely still has a `2025-06-08` override — must be set to `2026-06-08` (via the new `set_points_cutoff` tool or the Loyalty settings page) BEFORE running audits/fixes.

- **3 NEW deterministic READ-ONLY audits** (exact aggregations, honest "couldn't compute" instead of fake zeros, always report the cutoff used):
  - `audit_missing_redemption_ledger` — bills with points_redeemed>0 but no matching non-voided redeem ledger row; split HISTORIC (audit-gap only) vs LIVE (real over-balance).
  - `audit_duplicate_adjustments` — customers with >1 identical `adjust` row (bulk adjust run twice); surplus rows + points owed back.
  - `audit_historical_derived_points` — migrated customers with derived `lifetime_points_earned>0` + non-voided historic earn/bonus ledger rows (exactly what normalize would remove).

- **4 NEW MUTATION tools** (preview→confirm+reason, audit-logged, UNDOABLE):
  - `fix_missing_redemption_ledger` — LIVE bills only: writes the missing redeem row + deducts the never-debited points (raises lifetime_points_redeemed). Historic left untouched.
  - `reverse_duplicate_adjustments` — keeps ONE adjust per (mobile,points,reason) group, voids the surplus, credits back the double-deducted amount.
  - `normalize_historical_points` — voids derived historic earn/bonus ledger rows + resets lifetime_earned/redeemed to 0 + flags `historical_balance_authoritative:true`; `points_balance` NEVER changed.
  - `set_points_cutoff` — read/set the historical↔live cutoff (audited).

- **Undo made fully general:** `_reverse_changes_bulk` now also restores `lifetime_points_redeemed`; `undo_action` now generically voids rows a fix INSERTED (tagged `fix_audit_id`) and restores rows a fix VOIDED (tagged `voided_by_audit`). Verified: apply→undo returns balances/ledger to the exact prior state for all 3 fixes.

- **Files:** `backend/routes/master_brain_tools.py` (audits+fixes+cutoff+undo), `backend/routes/historic_routes.py` (cutoff default). Registry: 24 handlers, 19 action schemas, 5 read schemas — all wired, no dupes.

**Deferred (user is deciding — decision #5 "leave for now"):** (a) global recompute after the cutoff change; (b) recurrence-prevention CODE for `posAddPoint` writing the redeem row/deducting (held due to double-deduction-bug history — needs discussion); (c) double-run idempotency guard on bulk adjust/bonus jobs.

---


## 2026-07-07 — Fix P0: POS `posAddPoint` 500 `NetworkTimeout` (till hangs "Working on it…") + Master Brain timeouts (iter 83, 8/8 PASS)

⚠️ Redeploy required for production.
- **Symptom (production, from API Monitor):** `POST /api/pos/posAddPoint → 500 → "unhandled_exception: NetworkTimeout: customer-apps-shard-00-01.o9d3cj.mongodb.net:27017: The read operation timed out"`. LS Central till stuck on "Working on it…"; billing delayed. Master Brain also intermittently showed connection/timeout errors.
- **Root cause:** The previous deploy moved POS logging to *unbounded* `asyncio.create_task(api_logs_col.insert_one(...))` fire-and-forget, and the global `APILogMiddleware` did the same for every internal API call. On production `api_logs` holds millions of rows (multi-index inserts). Under live store traffic these background inserts saturated the **single shared Motor connection pool**, so a foreground `posAddPoint` bill (and Master Brain) could not check out a socket within the Atlas client `timeoutMS` → `NetworkTimeout: read operation timed out`. Confirmed non-reproducible in preview (no load) — a load/pool-starvation regression.
- **Fix:** New `backend/db_logging.py` — a **bounded queue (5000) drained by 2 workers on a SEPARATE, tiny Motor client (maxPoolSize=8)**. All best-effort `api_logs` writes now go through `submit_log()` (POS `_log_api`, both `APILogMiddleware` paths, and the POS unhandled-exception handler). Background logging can no longer steal connections from live POS/dashboard/Master-Brain reads; a burst just fills the queue and drops overflow (a lost monitor row is acceptable; a blocked till is not). Batched `insert_many` cuts round-trips.
- **Also:** main Motor client given explicit `maxPoolSize=100, minPoolSize=10` (warm sockets for live bills). New observability endpoint `GET /api/api-monitor/log-writer-health` (queue_depth, inserted, dropped, failed_batches, last_error) + periodic WARNING logs so operators can confirm on production that logging keeps up.
- **Validated (preview, testing_agent 8/8):** all POS flows (customer check, OTP, `posAddPoint` on store K00055, redeem) 200 & fast; `api_logs` still records via the isolated writer; **30 concurrent posCustomerCheck → 30/30 200, max 0.36s** (proves logging no longer starves the pool); Master Brain SSE `/chat/stream` returns replies & analytics numbers. NOTE: the pool-starvation itself only manifests under production load, so the concurrency test is a best-effort proxy — verify on prod via the health endpoint after redeploy.
- **Files:** `backend/db_logging.py` (new), `backend/database.py` (pool sizing), `backend/server.py` (middleware + exception handler + startup wiring), `backend/routes/pos_ewards_routes.py` (`_log_api` → `submit_log`), `backend/routes/api_monitor_routes.py` (health endpoint).
- **Deferred (needs user OK):** `api_logs` retention/TTL to keep the collection small (keeps inserts fast, lowers chance the isolated writer backs up on prod). Separate: deployment_agent flagged `.gitignore` blocks `.env` — a deployment-config item, not this bug.

---


## 2026-07-02 — Fix: Master Brain "not working / timing out / doesn't understand commands" (iters 77+78, 17/17 PASS)

⚠️ Redeploy required for production.
- **Symptoms (production):** (1) Analytics questions returned *"Data Unavailable — System Timeout / database read timeout"* (a KPI query took 71s on prod vs 28s in preview). (2) Natural-language action commands ("change customer X to gold tier") and bare confirmations ("yes / go ahead") were refused with *"I don't have that tool."*
- **Root cause A (timeout):** Master Brain's analytics tools ran heavy full-collection aggregations but — unlike Fundle Brain — had NO DB-deadline override, so production's aggressive Atlas client `timeoutMS` (~10s) killed them (aggregations themselves are only 1–6s). Proven: same aggregation under a 200ms client timeout → NetworkTimeout; wrapped in `pymongo.timeout(25)` → completes in ~1s.
- **Root cause B (commands):** `chat()` used a brittle keyword regex (`_has_action_intent`) to decide read-vs-action. It handed a READ-ONLY tool schema + read prompt to anything that didn't match the regex, so natural commands ("change X to gold tier") and confirmations ("yes/go ahead") had no matching action tool → the model hallucinated a "capability gap."
- **Fixes:**
  - `master_brain_routes.py`: `_master_execute_tool` now wraps every tool call in `with pymongo.timeout(MB_TOOL_DB_DEADLINE=25)` and clears the stats cache after action handlers. `chat()` now ALWAYS exposes `ALL_TOOL_SCHEMAS` with the write-capable prompt; writes stay safe via the mandatory preview→confirm(+reason) audited protocol. `is_action_command` (action verb OR confirmation-of-a-pending-preview) now only gates the instant deterministic read-audit fast-path. New helpers: `_looks_like_confirmation`, `_session_has_pending_action`.
  - `ai_tools.py`: `get_overall_kpis` / `tier_distribution` cached (60s TTL) with `clear_stats_cache()` invalidation after writes.
- **Verified:** iter 77 (7/7) + iter 78 (10/10). Analytics return real data (~800k customers) with no timeout; deterministic negative-balance audit instant (2.8s) & honest; natural-language tier/points commands preview→confirm→apply on one "yes/go ahead" turn with audit IDs; reads don't mutate.
- **Note:** Master Brain still depends on the Emergent Universal LLM Key balance (auto top-up is ON). If it ever runs dry, Master Brain replies "AI usage budget exhausted."

---


## 2026-06-25 (b) — Fix: Recon "failing when we try to upload file" — fragile chunk upload (iter 76, 3/3 PASS)

⚠️ Redeploy required for production (frontend change).
- **Symptom (production):** New attempts to recon a large `billing kazo.csv` (114 chunks ≈ 171MB)
  got stuck in status `uploading` at only **2–10 / 114 chunks** and never finished. Backend chunk
  endpoint is healthy (verified 25/25 chunks OK from a datacenter) — the problem was purely client-side.
- **Root cause:** `CsvReconSection.jsx` uploaded chunks sequentially with **NO retry** and **NO
  per-request timeout**. A single transient network blip / Cloudflare 5xx on any chunk over the
  user's real-world uplink threw, broke the for-loop, and abandoned the whole upload — leaving the
  job stuck `uploading` (then watchdog-failed after 8 min).
- **Fix (`frontend/src/pages/admin/recon/CsvReconSection.jsx`):** each chunk now goes through
  `uploadChunk()` with **5-attempt exponential backoff** (1→2→4→8s), a **120s per-chunk timeout**,
  and short-circuits genuine 4xx (400/401/403/413). `finalize` also retries ×3. A new inline note
  (`data-testid="recon-upload-note"`) shows retry progress; on total failure a friendly
  "Upload interrupted — likely a network drop, click Upload again" toast appears instead of a silent stall.
- **Verified (testing agent 3/3):** normal 6.29MB/5-chunk upload → done; a simulated abort of chunk 2
  auto-recovered (retry note shown, job reached done); total failure showed the toast + reset the button
  with no hang.

---


## 2026-06-25 — Fix: CSV Recon "still not done" — large-file OOM stall (iter 75, 5/5 PASS)

⚠️ Redeploy required for production (this fix lives in preview until Save to GitHub → Deploy).
- **Symptom (production):** Recon of large billing CSVs never finished. Prod jobs
  `Billing_Report_New.csv` (114 chunks ≈ 171 MB) and `SKU-wise_Billing_Rep.csv`
  (179 chunks ≈ 268 MB) both auto-failed with *"Stalled — no progress for over 8 min
  (likely a server restart mid-run)"*, frozen at `processed=150000`. Prod DB is only
  ~759k transactions, so the DB compare was NOT the bottleneck — the file size was.
- **Root cause:** `_run_recon_job` still used the OLD in-memory stitch — accumulated every
  uploaded chunk into a `List[bytes]`, joined them into one bytes blob, then decoded to a
  full string (peak ≈ 2–4× file size). On a 170–270 MB file this OOM-restarted the pod;
  the job row stayed "running" with no heartbeat and the 8-min stale watchdog failed it.
  (The historic *ingest* path was already fixed to stream to disk; recon was not.)
- **Fix (`/app/backend/routes/recon_routes.py`):**
  1. Stream uploaded chunks straight to a temp file on disk (O(chunk) memory); parse the
     CSV line-by-line from disk. `_parse_transactions/customers/items_csv` now take a
     `csv_path` and `open()` it instead of `io.StringIO(text)`. xlsx still stitched in
     memory (small in practice).
  2. Wrap the whole background body in `with pymongo.timeout(RECON_DB_DEADLINE_SECONDS=1800)`
     so the detached task isn't killed by the aggressive prod client `timeoutMS` (~10s) on
     the deep-scan / final `$group`.
- **Verified:** 244 MB wide CSV (150k rows) → done in 15.5s, **peak RSS 153 MB** (was ~730MB+).
  Testing agent 5/5 PASS: 90 MB / 64-chunk upload → `status=done` in 21.6s, no stall, correct counts.
- **Known follow-up (P2):** very large **.xlsx** recon still buffers in memory (same OOM path).
  CSV — the actual failing format — is fixed.

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

## 2026-06-30 (P0 fix) — Master Brain audit timeouts on production (the "taking longer / narrow it" message)
- BUG (production, recurring): "Customers with negative loyalty points balance and the exact reason?" went through the LLM tool loop (audit_negative_balances ×2 + run_aggregation) and returned the 46s-cap fallback "That query is taking longer than expected... narrow it to a single store, tier, or date range." (nonsensical for a global balance audit).
- ROOT CAUSE: the deterministic fast-path (`_deterministic_audit`) wraps the audit tool in `asyncio.wait_for(timeout=40)`. The old `_tool_audit_negative_balances` ran a FULL-LEDGER `$group` cross-check (1.5M+ rows) on every call; under the user's many concurrent retries these piled up, each sub-op hit its maxTimeMS cap, total exceeded 40s → wait_for killed it → returned None → fell to the slow LLM loop → 46s overall cap → fallback message. Also `_tool_audit_double_redemptions` swallowed a pass-1 timeout and returned a MISLEADING "0 affected / exact:True".
- FIX (`master_brain_tools.py` + `master_brain_routes.py`):
  - `_tool_audit_negative_balances`: authoritative count/total/worst now come from ONE bounded indexed `$facet` (15s cap, uses ix_cust_points_balance). The heavy ledger-sum cross-check moved to `_neg_ledger_crosscheck()` — 8s cap + module-level 5-min TTL cache, so a burst of repeated questions can't re-trigger the full-ledger group (kills the load spiral). On compute failure returns honest `computed:false` + "retry in a few seconds" (never a fake 0 or -1).
  - `_tool_audit_double_redemptions`: pass-2 bounded by a 15s wall-clock budget; tracks pass-1/pass-2 completion; on timeout returns honest `exact:false, computed:false` + "retry, or scope to a single mobile" (no more misleading "0/exact").
  - Formatters `_fmt_negative_balances` / `_fmt_double_redemptions` render the honest "couldn't compute" message.
- TESTED in preview (production-scale: 800,064 customers, 1,542,467 ledger rows): neg-balance Q resolves deterministically in ~9s (tool itself 2.6s, cross-check cached → 0.0s on repeat), single audit_negative_balances tool, exact answer, NO LLM loop. Dup-redemption Q in 0.18s. Honest-fail rendering verified with synthetic dicts.
- ACTION: user must REDEPLOY to push this live on production. ix_cust_points_balance is created by ensure_indexes() at startup (server.py:429) so it lands on deploy.
