# PRD — KAZO Fundle Platform

## Original problem statement
Build a complete enterprise-grade standalone loyalty, CRM, analytics, campaign automation, customer intelligence, support, reporting and API-monitoring platform for KAZO (kazo.com — premium Indian women's fashion brand), powered by Fundle. Dedicated single-tenant deployment.

## User-locked design constraints
- ✅ LIGHT editorial theme only (NO dark themes)
- ✅ REAL-TIME live MongoDB aggregations (NO stored snapshots, NO cron precompute)
- ✅ Emergent LLM Key (GPT-5.2 / Claude Sonnet 4.5) for AI narratives
- ✅ ZERO dummies / hardcode / fallbacks — real data or N/A
- ✅ Build dashboards one-by-one, full drilldown, test after each before moving on

## Architecture
- Backend: FastAPI + Motor MongoDB + JWT/cookie auth + Emergent LLM
- Frontend: React + Tailwind + shadcn primitives + Recharts + Cormorant Garamond + Manrope
- MongoDB DB: `kazo_fundle_db` (single tenant)
- All routes prefixed `/api`

## Roles (10)
Super Admin · Brand Admin · CRM Manager · Marketing Manager · Regional Manager · Store Manager · Store Staff · Support Agent · Analytics Viewer · Read-only Executive

## Sidebar sections
- **DASHBOARDS** — Command Center *(new)*, Sales, Customer Analytics, Loyalty, Campaign Performance, Store Performance, NPS & Feedback
- **CUSTOMERS** — Customer 360
- **MARKETING** — Campaigns, Coupons
- **AI TOOLS** — Fundle Brain
- **OPERATIONS** — Stores, Item Master, API Monitor
- **SUPPORT** — Tickets, NPS Inbox
- **REPORTS** — Reports & Exports
- **CONFIGURATION** — Loyalty Rules, Public Site CMS
- **ADMINISTRATION** (admin only) — User Management

## What's been implemented

### Iteration 1 (Jan 2026)
- Auth (JWT + portal gating), 10-role RBAC, audit logging
- Executive Cockpit (24+ KPIs), Customer 360, Loyalty Configurator
- Coupon Engine (13 types), Campaign Manager, Fundle Brain AI (real Mongo function-calling)
- Live API Monitor (5s refresh), POS endpoints, NPS, Tickets, Reports (CSV exports)
- 3 login portals (Enterprise / Store / CRM), Store Ops portal
- Public website (13 SEO pages)
- Seeded: 1504 customers, 8003 transactions, 26 stores, 8 coupons, 9 campaigns, 400 API logs, 300 NPS, 30 tickets

### Iteration 2 (Jan 2026) — ✅ 83/83 backend tests passing
- 9-section sidebar, 6 dashboards (Sales/Customer/Loyalty/Campaign/Store/NPS), Item & Store Master, CMS, Coupon edit, Ticket detail, Transaction drilldown

### Iteration 3 (May 2026) — ✅ Foundation for FundleBrain Dashboards
- ✅ **Universal Drilldown** — `POST /api/dashboard/drilldown` + `/csv` with collection whitelist, role-aware store scoping (security-hardened), `_id` & `password_hash` scrubbed, 200-row paginated, 10k CSV cap
- ✅ **AI Intelligence Report** — `POST /api/dashboard/insight` returns structured `{headline, summary, drivers[], recommendations[]}`. 1-hour in-memory cache, regenerate-on-force; uses Emergent LLM (GPT-5.2). Frontend renders a full multi-section editorial report panel.
- ✅ **Command Center Dashboard** — Replaces Executive Cockpit as `/admin` index. 12 live KPIs, sparkline area chart, cohort distribution bar chart (Today / 1–7d / 8–30d / 31–90d / 90d+), live alerts, 30s auto-refresh
- ✅ **City + Store global filters** on Command Center — every KPI, sparkline, cohort, alert, drilldown, and AI report re-computes live for the chosen scope
- ✅ **Active customers** now computed from ground-truth transactions (`distinct customer_id` in window) instead of stale `last_visit_at`
- ✅ **Reusable `DrillDownModal.jsx` + `AIInsightStrip.jsx`** components for every upcoming dashboard
- ✅ **Security fix** — `_store_scope` now denies (403) when store-bound role has no `store_id`; startup migration backfills `store_id` for `store.mumbai@kazo.com` and `staff.delhi@kazo.com`
- ⏳ Iteration 3 testing: 30/31 pytest pass, 1 P0 fixed (store-scope bypass)

## Prioritized backlog

### P0 — FundleBrain Phase 3A (next up)
- [ ] **Customer 360 v2** — RFM segment badge, lifetime stats, monthly spend chart
- [ ] **Store Performance v2** — Leaderboard / By City / Day Analysis tabs
- [ ] **RFM & Churn Dashboard** — live RFM quintile bucketing, 5×5 heatmap, 11 segments

### P1 — FundleBrain Phase 3B
- [ ] Points Economics v2 — earn-burn gauge, liability value, monthly flow, top redeemers
- [ ] Cohort Migration — triangular retention heatmap by signup month
- [ ] Campaign ROI v2 — Sent→Delivered→Clicked→Converted funnel + retention heatmap
- [ ] Executive Summary v2 — AI narrative + PDF download (ReportLab)
- [ ] Formula Catalog — auto-generated audit page

### P1 — AI Engine Upgrade
- [ ] True function-calling against MongoDB, streaming, CSV narration upload

### P1 — Pre-existing
- [ ] Live POS API integration, messaging gateways, Historic Sync UI, Daily Scheduler UI

### P2
- [ ] Digital Invoice Engine, OTP login / password reset, WebSocket dashboards, sitemap.xml, birthday auto-campaigns, image upload, more CMS controls
- [ ] Move AI insight cache to Redis (for multi-worker deploy)
- [ ] Drag-and-drop report builder, support bot, mobile app

## Test credentials
See `/app/memory/test_credentials.md` — Brand Admin: `admin@kazo.com / Kazo@2026`

## Known production hardening pending
- AI insight cache is in-memory (single worker only) — fine for preview, move to Redis for prod
- Drilldown CSV uses single-chunk StreamingResponse — fine at 10k cap, chunk for true streaming later
