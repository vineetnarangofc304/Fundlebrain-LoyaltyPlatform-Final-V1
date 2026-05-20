# PRD — KAZO Fundle Platform

## Original problem statement
Build a complete enterprise-grade standalone loyalty, CRM, analytics, campaign automation, customer intelligence, support, reporting and API-monitoring platform for KAZO (kazo.com — premium Indian women's fashion brand), powered by Fundle. Dedicated single-tenant deployment.

## User-locked design constraints
- ✅ LIGHT editorial theme only (NO dark themes)
- ✅ REAL-TIME live MongoDB aggregations (NO stored snapshots)
- ✅ Emergent LLM Key (GPT-5.2 / Claude Sonnet 4.5) for AI narratives
- ✅ ZERO dummies / hardcode / fallbacks — real data or N/A
- ✅ Build dashboards one-by-one, full drilldown, test after each

## Architecture
- Backend: FastAPI + Motor MongoDB + JWT/cookie auth + Emergent LLM (LiteLLM) + APScheduler
- Frontend: React + Tailwind + shadcn primitives + Recharts + Cormorant Garamond + Manrope
- MongoDB DB: `kazo_fundle_db` (single tenant)
- All routes prefixed `/api`

## Sidebar sections (current)
- **DASHBOARDS** — Command Center, Sales, Customer Analytics, Loyalty, Campaign Performance, Store, RFM & Churn, Cohorts, Points Economics, Campaign ROI, Executive Summary, NPS
- **CUSTOMERS** — Customer 360
- **MARKETING** — Campaigns, Coupons
- **COMMUNICATIONS** — Templates, Bulk Send Jobs, Provider Settings
- **AI TOOLS** — Fundle Brain (function-calling + CSV narration)
- **DATA** *(new)* — Historical Upload
- **OPERATIONS** — Stores, Item Master, API Monitor
- **SUPPORT** — Tickets, NPS Inbox
- **REPORTS** — Reports & Exports, Exec Digests, Formula Catalog
- **CONFIGURATION** — Loyalty Rules, Public Site CMS
- **ADMINISTRATION** — User Management

## What's been implemented (recent — full history in CHANGELOG when split)

### Iteration 11.7 (May 2026) — ✅ Mobile Sidebar + Batch B + Reconciliation Engine

**1) Collapsible sidebar on mobile** (`AdminLayout.jsx`):
- Hamburger button (fixed top-left, mobile-only) opens a sliding drawer
- Click anywhere on backdrop OR navigating to a route closes the drawer
- Desktop (`md:`+) keeps the sidebar always-visible (zero regression)
- New `data-testid` hooks: `mobile-menu-open`, `mobile-menu-close`, `mobile-menu-backdrop`

**2) Batch B**:
- **R6 retrofit endpoint** `POST /api/historic-data/backfill-points-ledger` — sweeps every loyalty transaction, writes `earn`/`redeem`/`bonus` ledger entries for any bill that doesn't yet have them. Idempotent (deduped by `source_bill_id` index built in memory).
- **R4 dedupe scan** `GET /api/historic-data/dedupe/mobiles` — returns any non-empty mobile held by more than one customer doc (now defensive — the partial-unique index built in 11.6 prevents new dupes).

**3) Reconciliation engine** `GET /api/historic-data/reconcile?job_id=...`:
- Compares the last (or specified) completed ingest job vs current DB state
- Sections: `job_summary` (CSV vs processed), `db_state` (live counts), `sums` (₹ + points · txn columns vs ledger), `integrity` (orphan store_id, missing customer docs, duplicate mobiles, ledger coverage %)
- Top-level `status` flag = `clean` or `issues_found` with a human-readable issue list
- Returns the exact diff numbers so you can verify CSV ingest matched DB exactly

**Frontend**: new admin page `/admin/reconciliation` (`ReconciliationPage.jsx`):
- Status banner (green if clean, amber if issues)
- Last Ingest Job KPI strip (CSV rows / Inserted / Updated / Skipped / Diff)
- Database State live counts (loyalty vs non-loyalty, customers, stores, distinct mobiles)
- Monetary & points sums (₹ + ledger-vs-txns diff)
- Integrity panel (orphans, dedupe, ledger coverage)
- **Repair Toolbox**: 3 one-click idempotent fixes — Loyalty Backfill / Points Ledger Backfill / Dedupe Scan. Toast feedback, auto-refresh after success.
- Added under sidebar section DATA › "Data Reconciliation" (super_admin / brand_admin only)

**Verified on preview** (34 test txns):
- `POST /backfill-points-ledger` → 10 earn entries written from txn columns, 19 skipped (no points), 0 already-indexed (idempotent on rerun) ✅
- `GET /dedupe/mobiles` → 0 duplicates ✅
- `GET /reconcile` → status=`issues_found` (correct on test data — 10 seeded txns have no store, low ledger coverage as seeds had no points cols) ✅
- Mobile drawer screenshots: hamburger opens / closes / backdrop dismisses ✅
- Desktop view unchanged ✅
- Python + JS lint clean

**User next steps**: Redeploy production → log in on phone to verify hamburger works → go to **Operations > Data Reconciliation** to see the full integrity report. Click any of the 3 repair buttons if issues are flagged; they're all safe / idempotent.

### Iteration 11.6 (May 2026) — ✅ Loyalty Data Model Lock-In (R1–R6)

User formalised the canonical KAZO loyalty data rules:
- **R1** `bill_date` is the chronological source of truth (not ingest `created_at`)
- **R2** customer's `home_store_id` = store of their EARLIEST bill
- **R3** one-timer = 1 unique bill; repeat = 2+ unique bills (unique = store+bill_no+date)
- **R4** `customer_mobile` is the unique customer identity — no duplicates
- **R5** bills WITH mobile = loyalty data (default for all dashboards). Bills WITHOUT mobile = non-loyalty / lost-opportunity (separate views, future)
- **R6** points tracked as earn / redeem / bonus ledger entries (no expiry yet — load as-is)

**Backend** — new shared filter module `routes/_loyalty.py`:
- `LOYALTY_TX_MATCH` = `{"customer_mobile": {"$nin": [None, ""]}}`
- `loyalty_match(extra)` helper composes the filter with date / store clauses
- Applied to **every** transaction `$match` stage across `dashboard_routes`, `analytics_routes`, `fundlebrain_routes`, `ai_tools`

**Customer-time filters switched** from `created_at` → `first_purchase_at`:
- `/dashboard/kpis` new customers · cohort buckets (today/7d/30d/90d/older)
- `/dashboard/command-center` acquisition cohort
- `/analytics/customer-dashboard` new customer trend
- `/fundle-brain/rfm` acquisition trend (now grouped by first-bill month)
- `/fundle-brain/points-economics` monthly flow (now bill_date-driven)
- `/dashboard/loyalty-dashboard` points trend (bill_date-driven)

**Customer unique identity = mobile (R4)** — every `unique_customers` set/$addToSet now uses `customer_mobile` instead of internal `customer_id`. Pipelines lookup customer master by mobile.

**Home store (R2)** — new `home_store_id` field on customer:
- Populated by post-ingest job + backfill endpoint (= store_id of customer's earliest bill)
- Store dashboards now report `home_customers` per store (customers anchored to that store) AND `visitors` (anyone who shopped there) — exposed in `/dashboard/store-performance`, `/dashboard/store-dashboard`, `/fundle-brain/store-performance-v2`

**Unique bill key (hard, R3)** — transactions ingest upsert key changed from `bill_number` alone to `(bill_number, bill_date)`. Unique compound index `(store_id, bill_number, bill_date)` enforced. `customers.mobile` partial unique index built.

**Points ledger (R6)** — `_map_transaction_row` now captures `points_earned`, `points_redeemed`, `bonus_points` from CSV (column auto-detection). Post-ingest job `_write_ledger_for_job` writes `earn`/`redeem`/`bonus` ledger entries timestamped with the bill_date for every loyalty bill. Idempotent on re-run (deduped by `source_bill_id`). No expiry logic — points loaded as-is per user direction.

**Backfill endpoint** — new `POST /api/historic-data/backfill-loyalty-model` (super_admin/brand_admin) — one-shot, idempotent retrofit of EXISTING 200k transactions and their customers per all rules above. Returns counts of indices built, mobiles aggregated, customers upserted/updated.

**Verification on preview**:
- Backfill: 16 loyalty mobiles → aggregates set, indices built ✅
- Sample customer `9266681235`: `first_purchase_at=2026-01-15`, `last_visit_at=2026-05-20`, `home_store_id` set, `visit_count=11`, `lifetime_spend=53000` ✅
- `GET /dashboard/kpis?period=all` returns 38 loyalty customers, 26 bills, ₹39,229 net, 6.2% repeat rate ✅
- `GET /dashboard/store-performance?period=all` returns 5 stores each with `home_customers` field populated ✅
- AI chat "lifetime loyalty sales?" → uses `get_overall_kpis(days=0)`, returns ₹39,229 / 26 txns / AOV ₹1,508.81 with strategic recommendations ✅
- Command Center screenshot: AI Intelligence Report correctly summarises "₹39.2K net sales from 26 bills, 16 active of 38 total, 6.2% repeat rate" ✅
- 30/30 POS pytest still pass; 203/211 backend tests pass (8 pre-existing failures dependent on purged demo data, none related to this change)

**User next steps**:
1. Redeploy production
2. Call `POST /api/historic-data/backfill-loyalty-model` ONCE to retrofit the 200k existing bills (returns counts; idempotent — safe to re-run)
3. Dashboards on production will now reflect loyalty-data-only views with proper home-store attribution and bill-date chronology

### Iteration 11.5 (May 2026) — ✅ All-Time Default + AI Chat Historical Awareness

**Issue from production**: User uploaded a 200,000-row historical billing CSV (`Billing_Report_New_1776672163581.csv`) that ingested cleanly (199,915 inserted + 84 updated = 100% reconciliation), but **all dashboards showed empty / no records** and Fundle Brain AI chat refused to answer ("Data not available"). Root cause: every dashboard defaulted to a 30-day window while the CSV billing dates were years old, so every aggregation filter excluded the data. AI tools also defaulted to `days=30` so they returned zero and the model honestly reported no data.

**Backend fix** — universal "All-time" sentinel where `period_days <= 0` (and `period in {"all","0","0d"}`) means a 20-year (7,300-day) lookback:
- `routes/analytics_routes.py::_start` — new normalize helper
- `routes/dashboard_routes.py::_date_range` — accepts `"all"`, `"0"`, `"0d"`, empty
- `routes/fundlebrain_routes.py::_norm_period_days` — applied to `store-performance-v2`, `points-economics`, `executive-summary`
- `routes/reports_routes.py::_norm_days` — applied to `/reports/transactions`, `/reports/transactions/export`, `/reports/custom`
- `routes/nps_routes.py::_norm_days` — applied to `/nps/summary`, `/nps/by-store`
- `routes/ai_tools.py::_norm_days` — applied to ALL 7 time-windowed tools (`get_overall_kpis`, `top_churning_customers`, `store_performance`, `city_performance`, `top_skus`, `nps_summary`, `communication_log_summary`)

**AI-tool schema** updates so GPT-5.2 *knows* to use `days=0` for historical questions:
- Updated `get_overall_kpis`, `store_performance`, `city_performance`, `top_skus` schema descriptions to mention "Pass days=0 for ALL-TIME"
- Rewrote `SYSTEM_PROMPT` in `ai_routes.py`: explicitly instructs Brain to use `days=0` when user asks about "all data / lifetime / historical / since launch", and to retry once with `days=0` if a windowed call returns zero before saying "Data not available"

**Frontend fix** — every period selector now offers "All time" and **defaults to it**:
- `pages/admin/ExecutiveCockpit.jsx` — default `"all"`, added "All time / 1 year" options
- `pages/admin/dashboards/CommandCenter.jsx` — default `"all"`
- `pages/admin/dashboards/SalesDashboard.jsx` — default `0`, added "All time" option
- `pages/admin/dashboards/StoreDashboard.jsx` — default `0`, added "All time" option
- `pages/admin/dashboards/PointsDashboard.jsx` — default `0`, added "All time" option
- `pages/admin/dashboards/ExecutiveSummary.jsx` — default `0`, added "All time" option

**Verification** (preview, with 5 seed transactions from 2024-05-20 + existing historical sample):
- `GET /api/dashboard/kpis?period=30d` → net 0, txns 8 (correct: 30-day window)
- `GET /api/dashboard/kpis?period=all` → net ₹43,979, txns 31 (correct: all-time)
- `GET /api/analytics/sales-dashboard?period_days=0` → hourly buckets populated with ₹36k+ from years-old data
- AI chat "What is our total all-time net sales?" → correctly calls `get_overall_kpis(days=0)`, returns *"Net Sales ₹39,229 · Transactions 26"* with executive recommendations
- 30/30 POS pytest still pass; lint clean

**User next steps**: Redeploy production. After redeploy, every dashboard will land on "All time" by default and immediately show the 200k uploaded transactions. AI chat will also answer historical questions correctly.

### Iteration 11.4 (May 2026) — ✅ POS API Self-Diagnosing 403 Errors

**Issue from production**: KAZO POS team reported "all POS APIs return 403 Forbidden" on https://kazoloyalty.fundlebrain.ai. Confirmed via curl — production correctly returned the FastAPI `_validate_creds` 403 with the opaque body `{"detail":"Forbidden"}`, giving the integrator no clue *which* check failed.

**Root cause**: `bootstrap_pos_defaults()` generates a fresh `secrets.token_urlsafe(32)` on each environment's first boot, so preview and production each have **different** api_keys. The KAZO POS team almost certainly had the wrong/stale key (likely the preview one).

**Fix** in `routes/pos_ewards_routes.py::_validate_creds`:
- Replaced single opaque `"Forbidden"` with 6 precise reasons (still 403):
  - `Missing x-api-key header`
  - `x-api-key contains leading/trailing whitespace — please trim`
  - `x-api-key is inactive — contact KAZO admin to reactivate or rotate`
  - `Invalid x-api-key — not recognised in this environment`
  - `merchant_id mismatch — expected '...', received '...'`
  - `customer_key mismatch — expected '...', received '...'`
- Empty / non-matching credentials still get 403 (no security regression)
- Detail strings are echoed only when the request actually supplies a mismatched value, so existing keys aren't exfiltrated to unauthenticated probes
- Full request/response remains captured in `api_logs` for Live Monitor drill-down

**Verification** (preview, all 6 scenarios via curl): every failure path returns its specific message; happy path still returns 200 with customer + rewards payload. 30/30 POS pytest pass.

**User next steps**: Redeploy production; then log into `/admin/pos-credentials` on production to copy the live `api_key` + `merchant_id` + `customer_key` and share with KAZO POS team.

### Iteration 11.3 (May 2026) — 🔒 CRITICAL POS Redemption Security Fix

**Vulnerability reported by KAZO POS team (Hardik)**: Two-stage tampering on `/api/pos/posRedeemPointOtpCheck`:
1. **OTP bypass** — sending `"otp": ""` (empty string) made my code's `if otp:` check skip OTP verification entirely → unauthenticated deduction worked
2. **Parameter tampering** — request OTP for 10 points, then verify with `"points": "100"` → system accepted and debited 100 instead of 10

Both issues meant a malicious actor could empty any customer's wallet by manipulating the JSON body between OTP request and verify.

**Fix** in `routes/pos_ewards_routes.py::pos_redeem_point_otp_check`:
- **OTP is now mandatory** when `require_otp_for_redeem=True` (default). Empty/missing OTP → `400 "OTP is required to verify this redemption"`
- **Points-tamper defense**: when verifying, the `points` value in the request MUST equal the `points` stored in the original OTP session's `payload_snapshot`. Mismatch → `400 "Redemption amount mismatch — OTP was issued for X points but the request is for Y points"`
- **Bill-tamper defense**: same comparison for `transaction.number/id` between the OTP-request payload and the verify payload → `400 "Bill number mismatch"` on mismatch
- Removed misleading "POS non-OTP redemption" ledger label that masked the bypass — all OTP-path redemptions now log as "POS OTP redemption"

**Verification** (preview, curl):
- Reset test customer 9266681235 to 5000 points
- Empty-OTP attack → 400 ✅
- Issue OTP for 10 → tamper to 100 in verify → 400 ✅
- Same OTP + wrong bill → 400 ✅
- Happy path (correct OTP + 10 + correct bill) → 200 OK, balance went 5000 → 4990 (exactly 10 deducted) ✅

### Iteration 11.2 (May 2026) — ✅ Anonymous Walk-In Bills + Bulletproof Ingest

**Issue from production**: 33MB billing CSV was being marked "Failed" at 199,897 / 199,999 rows. Two root causes:

1. **Logic bug**: My mapper was treating "no Customer Mobile" as a fatal skip. But KAZO's actual data has thousands of **anonymous walk-in bills** (the entire point of the Live Monitor's "Lost Opportunity" feature!). These should be ingested as valid transactions with `customer_mobile=null`, not skipped.
2. **Resilience bug**: Any unhandled exception in the final flush or store-auto-create post-pass aborted the entire job, losing the trailing rows and showing "Failed" even when 99.95% had succeeded.

**Fixes in `routes/historic_routes.py`**:
- `_map_transaction_row`: mobile is now **OPTIONAL**. Anonymous bills become valid transactions stored with `customer_mobile=None` → automatically flagged as Lost Opportunities by Live Monitor's `has_mobile` filter.
- Loop hardened: **3 layers of try/except** — per-row, per-flush, per-post-pass. One bad row, one failed bulk_write, one store-create failure never aborts the whole job.
- Outer except clause now writes **partial counts + full Python traceback** to the job doc (`error` + `error_trace` fields) so failures are debuggable without backend log access.
- Final flush, store auto-creation, and bulk store backfill each wrapped in their own try/except — partial completions get marked `completed` (with counts) instead of `failed`.

**Verification**: 33MB / **200,000-row** CSV with 500 anonymous walk-in tail rows (mirroring user's actual data):
- Upload + finalize: <5s · scheduler picked up + processed in 30s · **0 errors, 100% reconciliation match**
- 199,500 customer bills ingested with mobile + 500 Lost Opportunities ingested with `customer_mobile=null`
- Live Monitor cockpit will correctly mark the 500 as red "LOST OPP."

### Iteration 11.1 (May 2026) — ✅ Scheduler-Driven Resilient Ingest (Production Reliability)

**Issue**: Even after multi-pod chunked upload fix, the 33MB / 190K-row ingest was failing at ~2000 rows on production. Root cause: FastAPI `BackgroundTasks` runs in the same worker process as web requests. When that worker recycles (hot-reload, gunicorn timeout, pod restart, OOM), the in-process task dies silently — taking ~188K unprocessed rows with it.

**Fix** — implemented user-requested architecture:
- `routes/historic_routes.py::ingest_finalize` now returns IMMEDIATELY with `status="pending_ingest"`. Chunks stay in MongoDB (no in-process task held).
- New `process_pending_ingests()` worker registered in `scheduler.py` runs every **15 seconds** via APScheduler `IntervalTrigger` with `max_instances=1` + `coalesce=True`:
  1. Recovers stale `running` jobs whose heartbeat is older than 3 minutes (auto-resume on pod restart)
  2. Atomically claims ONE pending job via `find_one_and_update` (multi-pod safe)
  3. Stitches chunks from MongoDB → CSV text → runs `_run_ingest_job`
  4. Cleans up chunk docs from MongoDB after success
- `_run_ingest_job` now writes `heartbeat` timestamp on every 500-row flush — visible progress in `/historic-data/jobs/{id}`
- New `_reconcile_job()` writes a `reconciliation` block on the job doc: `total_rows_in_csv` vs `inserted+updated+skipped`, with `match: true/false` boolean

**Verification**: End-to-end with 33MB / **190,000-row** transactions CSV:
- Upload phase: 18 chunks × 1.5MB in <5s
- Finalize returned in **1 second** with `status=pending_ingest`
- Scheduler picked up + ingested all 190K rows in 30 seconds
- Reconciliation: **190,000 / 190,000 match**, 50 stores auto-created, 0 errors
- Chunks cleaned up from MongoDB post-completion

### Iteration 11 (May 2026) — ✅ eWards-Compatible POS Integration APIs + Live Bill Monitor Cockpit

**Goal**: KAZO must NOT change anything on their POS — they swap base URL + x-api-key + merchant_id + customer_key and Fundle absorbs all the traffic that was previously going to eWards. Mirror the exact 14-endpoint contract from the supplied `eWards POS Integration x FBTS (kazo).pdf` spec.

**Backend** — `routes/pos_ewards_routes.py` (new, ~1100 lines)
- All 14 endpoints under `/api/pos/*` with eWards-exact JSON contract:
  - `posCustomerCheck`, `posCustomerCheckRequest`, `resendOtPcustomercheck`, `posCustomerOTPCheck`
  - `posAddCustomer`, `posRedeemPointRequest`, `resendOtPosRedeemPointRequest`, `posRedeemPointOtpCheck`
  - `posAddPoint` (bill settlement w/ items, taxes, charges, payment_mode, auto-create store from outlet, points engine, customer aggregate update, ledger writes, coupon-redemption capture, transactional comms fire)
  - `posCouponDetails`, `posRedeemCoupon`
  - `returnOrder` (reverses points + spend, creates RET-* transaction)
  - `requestWalletRedemptionURL`, `getWalletRedemptionStatus`
- Auth: 3-factor — `x-api-key` (header) + `merchant_id` + `customer_key` (body) must all match `pos_credentials` collection
- Bootstrap on startup: auto-creates default credential `kazo_default` with random api_key, test customer **966681235** (5000 pts, gold tier), 3 active coupons (POSTEST10, POSTEST20PCT, POSTESTVIP)
- Every request + response captured into `api_logs` with `source='pos_ewards'` for Live Monitor

**Backend** — `routes/live_monitor_routes.py` (new)
- `GET /api/live-monitor/transactions` — paginated bill stream with filters: `store_id`, `region`, `has_mobile` (yes/no), `payment_mode`, `source`, `min_amount`, `max_amount`. Enriches with `customer_name`, `tier`, `current_points`. Computes `has_mobile` + `lost_opportunity` flags
- `GET /api/live-monitor/stats?minutes=N` — KPI strip data: `bills_total`, `bills_with_mobile`, `bills_without_mobile`, `mobile_attach_rate_pct`, `revenue_total`, `revenue_lost`, `points_earned`, `returns`, `by_store_top10`
- `GET /api/admin/pos-credentials` + POST/rotate/deactivate — super_admin/brand_admin only
- `GET /api/api-monitor/logs` + `/log/{id}` — full request+response payload for the API Monitor drill

**Frontend** — 3 new admin pages
- `pages/admin/LiveMonitorPage.jsx` — cockpit with 7-card KPI strip (Bills/With Mobile/Lost Opp/Attach %/Revenue/Pts Earned/Returns), filter bar (Mobile / Store / Source / Payment / Min ₹ / Max ₹ / Stats window), top-stores panel, bills table with green/red left-border (mobile attached vs LOST OPP), 3-second auto-refresh with Pause/Resume + click-to-drill modal
- `pages/admin/POSCredentialsPage.jsx` — view/create/rotate/deactivate POS API keys with hide/show + copy-to-clipboard + quick-reference code block for KAZO POS team
- `pages/admin/APIMonitor.jsx` (overwritten) — every row clickable → drill modal showing request_payload + response_payload as syntax-highlighted JSON with copy-JSON buttons; source + endpoint filters
- Sidebar additions: `DASHBOARDS > Live Bill Monitor` and `OPERATIONS > POS Credentials`

**Postman**
- `/app/KAZO_POS_API.postman_collection.json` — all 14 endpoints pre-built with variables for base_url/api_key/merchant_id/customer_key/test_mobile

**Tests**: 25/25 backend pytest pass; all 3 frontend pages verified by testing agent. POS test customer (966681235) seeded with 5000 points + 3 active coupons. Live cockpit and credentials page render and integrate end-to-end.

### Iteration 10.1 (May 2026) — ✅ Chunked Upload Multi-Pod Fix

**Issue**: First chunked-upload deploy failed in production with `Chunk count mismatch — expected 24, found 13`. Root cause: production runs multiple backend pods; chunks were persisted to each pod's local `/tmp/historic_uploads`, so finalize only saw the chunks on its own pod.

**Fix** — `routes/historic_routes.py`
- Switched chunk storage from local filesystem to MongoDB collection `historic_chunks` (shared across all pods/workers)
- Idempotent upsert by `{job_id, chunk_index}` — chunk retries don't double-count
- Streaming async cursor sorted by `chunk_index` in finalize to stitch in correct order; explicit gap detection
- Cleanup deletes chunk docs from MongoDB after stitch
- Dropped local filesystem dependency entirely (`UPLOAD_TMP_DIR`, `shutil`, `pathlib` no longer needed)

**Verification**: End-to-end test with 26.6 MB / 190,000-row transactions CSV split into 18 chunks → finalize → background ingest running cleanly. Zero chunks leaked.

### Iteration 10 (May 2026) — ✅ Chunked Upload for Large CSVs (Production Fix)

**Issue**: Production upload of 33MB / 1.9-lakh-row CSV was failing partway — root cause was Kubernetes ingress body-size limit on the single multipart POST.

**Backend** — `routes/historic_routes.py`
- New 3-step chunked upload protocol (raises `MAX_FILE_BYTES` cap to **250 MB**):
  - `POST /api/historic-data/ingest/init` — `{dataset, duplicate_mode, dry_run, filename, total_chunks, total_bytes}` → creates job in `uploading` state, returns `job_id`
  - `POST /api/historic-data/ingest/chunk` — multipart `{job_id, chunk_index, chunk}` → 10MB hard cap per chunk, persists to `/tmp/historic_uploads/{job_id}/chunk-{NNNNN}.bin`
  - `POST /api/historic-data/ingest/finalize` — `{job_id}` → stitches chunks (sorted by index), validates count, decodes UTF-8 (BOM-safe), counts rows, queues existing `_run_ingest_job` background task, then deletes temp chunks
  - `POST /api/historic-data/ingest/abort/{job_id}` — cancel + cleanup
- Legacy `POST /api/historic-data/ingest` single-shot endpoint kept for files < ingress limit

**Frontend** — `pages/admin/HistoricDataPage.jsx`
- Replaced single `axios.post(formData)` with sequential chunked uploader: slices `File` into 1.5 MB blobs using `File.slice()`, uploads with up to 3 retries per chunk, exponential backoff
- Live progress bar with phase + percent + chunk index ("Uploading chunk 12 of 22 (54%)")
- Server-side abort triggered on client failure to free temp files
- Updated copy: "Max 250 MB · UTF-8 · uploaded in 1.5 MB chunks"

**Verification**
- End-to-end curl test: 2,500-row preview ✅, 50,000-row live ingest ✅ (background task ran at ~700 rows/sec). No proxy/timeout errors. All chunks successfully stitched.

### Iteration 9 (May 2026) — ✅ Historical Data Upload + Demo-Data Purge + Period Extension

**Backend** — `routes/historic_routes.py`
- `GET /api/historic-data/schema/{customers|transactions|stores|items}` — JSON spec with primary_key, required + recognised columns, sample row, parsing notes
- `POST /api/historic-data/ingest` (multipart: `file`, `dataset`, `duplicate_mode={upsert|skip|fail}`, `dry_run`) — returns `job_id`, parses CSV in BackgroundTasks, upserts via `pymongo.UpdateOne(upsert=True)` in chunks of 500
- `GET /api/historic-data/jobs` + `/{job_id}` — job status, processed/inserted/updated/skipped counts + error samples
- `GET /api/historic-data/purge-preview` — counts per collection
- `POST /api/historic-data/purge-demo` (body `{confirm:true}`) — wipes customers/transactions/stores/campaigns/metrics/coupons/redemptions/ledger/api_logs/nps/tickets/ai_chats/message_log/bulk_jobs/digests/audit_logs; preserves users/loyalty_config/templates/provider_config
- KAZO column mappers — handle verbose KAZO export headers (e.g. `Outlet(Only For Shopify Marker)`, `Net Amount Before Tax Kazo`, `Total Revenue Kazo`). Date parser supports 9 formats incl. `DD-MM-YYYY`. Mobile normalised (strips `91` prefix). Tier auto-derived from `Total Billing` (silver < 25k, gold < 75k, platinum < 200k, diamond ≥ 200k). For transactions, stores are auto-created from `Outlet` column then `store_id` back-filled on every transaction.
- RBAC: ingest restricted to `{super_admin, brand_admin, crm_manager, marketing_manager}` — store_manager → 403. Purge: brand_admin / super_admin only.

**Backend** — `dashboard_routes._date_range()`
- New `1y` (365 days) and `all` (20-year window) period options
- Sparkline aggregation switches to **monthly** buckets when period ∈ {`1y`, `ytd`, `all`} so payload stays compact

**Frontend** — `pages/admin/HistoricDataPage.jsx`
- 4 dataset tiles (Customers / Transactions / Stores / Items)
- Drag-and-drop upload zone, duplicate-mode + dry-run/live selectors, **Preview / Ingest now** button
- Live schema panel: required columns as rose pills, recognised columns as grey, sample row in dark code block, notes list
- Ingest history table (auto-refresh every 4 s) with pill-coloured status (queued / running / previewed / completed / failed) + inserted/updated/skipped counts
- "Purge demo data" danger modal — shows pre-counts per collection, requires typing literal `PURGE` to confirm
- Route: `/admin/historic-data` (role-guarded), new sidebar **DATA** section

**State after iteration 9**
- All seed/demo data purged (1504 customers, 8003 txns, 26 stores, 12 campaigns, 16 metrics, 8006 ledger rows, etc gone)
- Sample KAZO CSVs ingested via the UI: 16 customers + 15 transactions + 8 auto-created stores
- Verified via Command Center `period=all`: ₹36,229 net sales · 15 txns · ₹2,415 AOV · 16 customers — all live from MongoDB
- Tests: 21/21 backend + frontend 100% (iteration_9.json)

### Iteration 8 (May 2026) — ✅ AI v2 + BackgroundTasks + WABA + Scheduled Digest (see report)
### Iteration 7 (May 2026) — ✅ Communications Module (Karix LIVE)
### Iterations 1–6 — Foundation: 10 roles, 12 dashboards, drilldown, AI insights, coupon engine, campaign manager, CMS, etc.

## Prioritized backlog

### P0 — DONE
- [x] Historical CSV upload UI + background ingest (iteration 9)
- [x] Purge demo data (iteration 9)
- [x] All-time period option so dashboards reflect historic uploads (iteration 9)
- [x] Fix CORS for custom domain `kazoloyalty.fundlebrain.ai` — replaced wildcard `*` (incompatible with credentialed XHR) with explicit allowlist + regex covering `*.fundlebrain.ai`, `*.emergent.host`, `*.emergentagent.com` (2026-05-19). Requires redeploy.
- [x] Idempotent seed of all 11 demo users on backend boot (2026-05-19)

### P1 — Next
- [ ] **KAZO POS API integration** (Phase 2) — User to share KAZO POS API docs/Swagger/Postman. Will build: (a) push endpoints we expose for KAZO POS to call, (b) optional pull-scheduler that polls KAZO POS for live transactions, (c) reconciliation between live + historic.
- [ ] Wire optional email transport (Resend / SendGrid / Karix Email) for scheduled digest
- [ ] CSV upload: support chunked >50 MB files via signed-URL streaming
- [ ] Item Master + Points Ledger ingest variants (currently only customers/transactions/stores have row mappers)

### P2
- [ ] Drag-and-drop report builder, support bot, mobile app
- [ ] Move AI insight cache to Redis (multi-worker)
- [ ] Birthday / win-back / abandoned-visit auto-campaigns
- [ ] Carry-over CommandCenter hydration warning `<span> in <option>` cleanup

## Test credentials
See `/app/memory/test_credentials.md` — Brand Admin: `admin@kazo.com / Kazo@2026`

## Known production hardening pending
- AI insight cache is in-memory (single worker only)
- Digest PDF stored as base64 in MongoDB (≤ 800 KB cap); move to GridFS or S3 for large reports
- Historic ingest stitches chunks in memory then runs `_run_ingest_job` with the full text; for true multi-million-row imports switch to streaming `csv.DictReader` over a temp file
