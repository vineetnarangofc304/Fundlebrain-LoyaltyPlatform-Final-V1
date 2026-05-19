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
- Historic CSV upload reads the entire file into memory then iterates — fine to ~50 MB; for true multi-million-row imports stream via aiofiles + chunked DictReader
