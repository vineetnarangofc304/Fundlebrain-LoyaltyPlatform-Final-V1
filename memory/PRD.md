# PRD — KAZO Fundle Platform

## Original problem statement
Build a complete enterprise-grade standalone loyalty, CRM, analytics, campaign automation, customer intelligence, support, reporting and API-monitoring platform for KAZO (kazo.com — premium Indian women's fashion brand), powered by Fundle. Dedicated single-tenant deployment for Kazo. Public website with SEO, separate Enterprise / Store / CRM login portals, full admin dashboard, store operations interface, POS integration layer, AI analytics that queries real DB only.

## Architecture
- Backend: FastAPI + async Motor MongoDB + JWT/cookie auth + Emergent LLM (GPT-5.2 / Claude / Gemini)
- Frontend: React + TailwindCSS + shadcn primitives + Recharts + Cormorant Garamond + Manrope
- Single MongoDB (`kazo_fundle_db`) — no multi-tenant
- All routes prefixed `/api`

## User personas / roles
1. Super Admin (Fundle) — full platform control, can create Brand Admins
2. Brand Admin (Kazo IT/Head) — creates CRM/Marketing/Regional/Store/Staff/Support/Analytics/Executive users
3. CRM Manager — Customer 360, campaigns, NPS, tickets
4. Marketing Manager — Campaigns, coupons
5. Regional Manager — store cluster oversight
6. Store Manager / Store Staff — store ops portal only
7. Support Agent — tickets
8. Analytics Viewer / Read-only Executive — dashboards only

## What's been implemented (2026-01-19)

### Backend
- [x] User management hierarchy (Super Admin → Brand Admin → other roles)
- [x] JWT login with portal-based role gating (Enterprise/Store/CRM)
- [x] 10 roles + RBAC decorators
- [x] Audit logging on every mutation
- [x] Executive Cockpit KPI APIs (sales, customers, loyalty, NPS, API, campaigns, drill-downs)
- [x] Customer 360 (search, deep profile with txns, ledger, redemptions, tickets, NPS, favourites)
- [x] Loyalty Configurator (earn/burn ratio, tier rules, bonuses, OTP rules)
- [x] Coupon Engine (13 types, code generator, validate, redeem)
- [x] Campaign Manager (multi-channel, audience builder, launch with metrics simulation)
- [x] Fundle Brain AI (real DB function-calling for churn/stores/campaigns/SKUs/tiers/NPS)
- [x] Live API Monitor (health, uptime, by endpoint, last 100 calls, 5s refresh)
- [x] POS Integration endpoints (validate-customer, issue-otp, issue-points, redeem-points, redeem-coupon)
- [x] Public-facing APIs (stores list, FAQ, register-interest)
- [x] NPS engine (submit, summary, by-store, recent)
- [x] Support Tickets (CRUD + status workflow)
- [x] Reports (transactions, customers exports as CSV, audit logs, custom report builder)
- [x] Stores management

### Frontend
- [x] Public Website (Home, AboutProgram, LoyaltyBenefits, HowItWorks, EarnPoints, RedeemPoints, Rewards, ReferralProgram, StoreLocator, FAQs, Privacy, Terms, Contact)
- [x] 3 Login Portals (Enterprise, Store, CRM)
- [x] Admin Layout with dark sidebar (#0F172A, 6px radius, burgundy accent, "Powered by Fundle")
- [x] Executive Cockpit (24+ KPI cards, sales trend, tier pie, category bar, store table, top SKUs)
- [x] Customer 360 (list + filters + detail page with 360° profile)
- [x] Loyalty Configurator
- [x] Coupon Engine
- [x] Campaign Manager
- [x] Fundle Brain AI Chat (multi-session, model switcher, suggested prompts)
- [x] Live API Monitor (auto-refresh 5s)
- [x] User Management
- [x] Stores list
- [x] NPS dashboard
- [x] Tickets workflow
- [x] Reports (with CSV exports)
- [x] Store Operations portal (customer lookup, OTP, award points, validate coupon, recent txns)

### Seed data
- 25 stores across 15 Indian cities
- 1,500 customers (with realistic tier distribution)
- 8,000 transactions over 365 days
- 8 coupons (welcome, VIP, birthday, win-back, denim, party, jewelry, flat ₹500)
- 9 campaigns with realistic ROI metrics
- 400 API log entries
- 300 NPS responses
- 30 support tickets
- 9 demo users covering all roles

## Prioritized backlog

### P0 — Immediate
- [ ] Live POS API documentation integration when client shares ERP specs
- [ ] WhatsApp Business / SMS gateway / Email actually wired (currently simulated)
- [ ] Historic sync UI (year/month/store progress bars)
- [ ] Daily scheduler UI

### P1 — Soon
- [ ] Digital Invoice Engine (PDF templates with branding)
- [ ] OTP login (passwordless)
- [ ] Email verification flow
- [ ] Password reset email
- [ ] CSV upload UI for bulk customer/transaction imports
- [ ] Real-time WebSocket dashboards (currently polled 30s)
- [ ] SEO sitemap.xml / robots.txt generation
- [ ] Birthday/Anniversary auto-trigger jobs

### P2 — Later
- [ ] Drag-and-drop visual report builder
- [ ] Support Bot chat for staff
- [ ] Mobile app
- [ ] Storefront on POS terminal
- [ ] Advanced cohort analytics (RFM matrix visualisation)
- [ ] A/B test framework for campaigns
- [ ] Customer-facing self-serve portal

## Production notes
- All environment variables in `/app/backend/.env`
- Emergent LLM key configured for AI chat (Brain)
- All passwords bcrypt; JWT 12h expiry
- POS endpoints intentionally unauthenticated (to be locked with API key + IP allow-list when ERP specs arrive)
