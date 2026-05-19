# PRD — KAZO Fundle Platform

## Original problem statement
Build a complete enterprise-grade standalone loyalty, CRM, analytics, campaign automation, customer intelligence, support, reporting and API-monitoring platform for KAZO (kazo.com — premium Indian women's fashion brand), powered by Fundle. Dedicated single-tenant deployment.

## Architecture
- Backend: FastAPI + Motor MongoDB + JWT/cookie auth + Emergent LLM (GPT-5.2 / Claude / Gemini)
- Frontend: React + Tailwind + shadcn primitives + Recharts + Cormorant Garamond + Manrope
- MongoDB DB: `kazo_fundle_db` (single tenant)
- All routes prefixed `/api`

## Roles (10)
Super Admin · Brand Admin · CRM Manager · Marketing Manager · Regional Manager · Store Manager · Store Staff · Support Agent · Analytics Viewer · Read-only Executive

## Sidebar sections (Iteration 2)
- **DASHBOARDS** — Executive Cockpit, Sales, Customer Analytics, Loyalty, Campaign Performance, Store Performance, NPS & Feedback
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
- Seeded: 1500 customers, 8000 transactions, 25 stores, 8 coupons, 9 campaigns, 400 API logs, 300 NPS, 30 tickets

### Iteration 2 (Jan 2026) — ✅ 83/83 backend tests passing
- ✅ **Removed all "Emergent" mentions** from page titles, meta, HTML, and replaced editorial imagery
- ✅ **Restructured sidebar** into 9 logical sections with collapsible groups
- ✅ **6 new dashboards** with full data: Sales / Customer Analytics / Loyalty / Campaign Performance / Store Performance / NPS Dashboard
- ✅ **Executive Cockpit KPIs are now clickable** and route to the appropriate drill-down dashboard
- ✅ **Item Master** (categories + SKUs with bulk CSV upload, sample download, edit, delete)
- ✅ **Store Master** with bulk CSV upload, sample download, edit, soft-delete
- ✅ **CMS for public site** — admin can edit hero text, headline, subtext, stats, images, footer tagline, support info; public Home + PublicLayout consume CMS content
- ✅ **Coupon edit modal** — full edit capability on existing coupons
- ✅ **Support Ticket detail page** with conversation/notes thread, status & priority quick-actions, customer link
- ✅ **Transaction drill-down modal** — clicking a transaction row in Reports opens a full detail modal with line items + linked customer/store
- ✅ All bulk APIs return `{inserted, skipped, errors}` with sample CSV downloads

## Prioritized backlog

### P0
- [ ] Live POS API integration (when client shares ERP docs: Logic ERP / BOSS / XML / JSON)
- [ ] Live messaging gateways (WhatsApp Business Cloud API, MSG91/Gupshup SMS, SendGrid/Resend)
- [ ] Historic Sync UI with year/month/store progress bars
- [ ] Daily Scheduler UI (cron toggle, success/failure history)

### P1
- [ ] Digital Invoice Engine (PDF templates with KAZO branding)
- [ ] OTP login / Password reset email
- [ ] Real-time WebSocket dashboards (currently polled 30s)
- [ ] sitemap.xml / robots.txt generation
- [ ] Birthday/Anniversary auto-trigger campaigns
- [ ] Image upload (currently CMS uses URLs — could add to cloud storage)
- [ ] More public website CMS controls (FAQs, About text, Privacy/Terms editing)

### P2
- [ ] Drag-and-drop visual report builder
- [ ] Support Bot chat for staff
- [ ] Mobile app
- [ ] Storefront on POS terminal
- [ ] RFM matrix heatmap, advanced cohort analytics
- [ ] A/B test framework for campaigns
- [ ] Customer-facing self-serve portal at /me

## Test credentials
See `/app/memory/test_credentials.md` — Brand Admin: `admin@kazo.com / Kazo@2026`
