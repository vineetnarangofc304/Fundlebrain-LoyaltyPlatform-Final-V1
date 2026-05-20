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
