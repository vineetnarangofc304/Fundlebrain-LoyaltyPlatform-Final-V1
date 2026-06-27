# EMERGENT BUILD PROMPT — "CITY METRO" (Loyalty + CRM + Analytics + AI platform)

> Paste this whole prompt into a NEW Emergent project to build the platform for the brand **City Metro**. It reproduces, end-to-end, an enterprise single-tenant loyalty/CRM/analytics/campaign-automation/customer-intelligence/support platform (the same product we already run for KAZO), rebranded for City Metro. Build it in phases, test each phase, and keep everything production-grade.

---

## 0) WHAT TO BUILD (one line)
Build a single-tenant, enterprise-grade **Loyalty + CRM + Analytics + Campaign Automation + Customer Intelligence + Support + Reporting + API-monitoring** platform for **City Metro**, with a live POS integration, a public loyalty microsite, 13 analytics dashboards, and two AI copilots ("Fundle Brain" = analyst, "Master Brain" = privileged operator). The loyalty engine that powers the app is **Fundle** ("Powered by Fundle") — keep that platform identity; only the customer-facing brand is City Metro.

## 1) BRAND IDENTITY (the ONLY things that change vs the base product)
- **Brand name:** City Metro
- **Descriptor:** "a multi-category urban lifestyle & fashion retail chain" (apparel, footwear, accessories, beauty, home)
- **Public domain:** citymetro.com
- **Loyalty programme name:** "City Metro Privileges"
- **Welcome bonus:** 100 points on signup
- **Platform engine:** Fundle · AI copilots: **Fundle Brain** + **Master Brain** (keep these names & training verbatim)
- **Palette suggestion:** urban-editorial — charcoal/ink base, brushed-steel neutrals, a single confident accent (deep teal `#0E7C7B` or metro-cobalt). Keep a LIGHT editorial theme (NOT dark, NOT purple-on-white "AI slop").
- **Centralise ALL brand strings** in `frontend/src/brand.config.js` (single source of truth) and the `--brand-*` CSS variables in `index.css`, plus `BRAND_NAME` / admin emails in `backend/.env`. Rebranding must only require editing those 3 places.

## 2) TECH STACK & NON-NEGOTIABLE ARCHITECTURE
- **Backend:** FastAPI + **Motor (async MongoDB)** + APScheduler (schedulers/watchdogs) + custom JWT auth (PyJWT + bcrypt). Python 3.11.
- **Frontend:** React (CRA) + React Router + Tailwind + **shadcn/ui** + lucide-react icons + Recharts + sonner toasts. NO emoji icons.
- **AI:** Use the **Emergent Universal LLM key** via `emergentintegrations` (GPT-4o/Claude for text, OpenAI for TTS, Gemini Nano-Banana if images needed). Do NOT install vendor SDKs directly.
- **Routing rules (hard):** every backend route is prefixed **`/api`**; backend binds `0.0.0.0:8001`; frontend calls **only** `process.env.REACT_APP_BACKEND_URL`; Mongo via **`MONGO_URL`** + `DB_NAME` from env. No hardcoded URLs/ports/secrets — omit fallbacks so missing config fails fast.
- **Mongo discipline:** never return raw `_id`; use a `PyObjectId`/`BaseDocument` pattern (`to_mongo`/`from_mongo`). All datetimes `datetime.now(timezone.utc)`. **Stored dates are ISO strings.**
- **Heavy jobs:** any large CSV parse / cross-check runs OFF the event loop (`asyncio.to_thread` for CPU parse) with **heartbeat + stale-recovery watchdog** (auto-fail jobs with no heartbeat > 8 min) and `await asyncio.sleep(0)` yields between DB batches. Chunked uploads (1.5 MB chunks) for big files.
- Split backend into `/backend/routes/*` modules (auth, pos, loyalty, customers, dashboards, analytics, campaigns, communications, ai/fundlebrain, master_brain, historic, recon, stores, items, reports, nps, tickets, users, public, cms, api_monitor, exports, segments, coupons, live_monitor…). Frontend pages under `src/pages/{admin,auth,public,store}`.

## 3) AUTH & ROLES (RBAC)
- Custom JWT (email+password, bcrypt-hashed). Seed from `.env`: **super_admin** + **brand_admin**. Roles: `super_admin`, `brand_admin`, `crm_manager`, `support_agent`, `store_user`, `analyst/viewer`. Plus two flags: **`is_master_admin`** (can use Master Brain action layer) and **`is_master_query_admin`** (global Master-Brain query-log oversight).
- Login routes: `/crm/login` (admin/CRM), `/store/login` (store ops), enterprise login shell. Every write is **audit-logged**.
- Save all seeded credentials to `/app/memory/test_credentials.md`.

## 4) PUBLIC LOYALTY MICROSITE (CMS-driven)
Pages: Home, How It Works, Earn Points, Redeem Points, Rewards, Loyalty Benefits, Tiers, Referral Program, Store Locator, About Program, FAQs, Contact, Privacy, Terms. Join-free CTA + welcome bonus. All copy/images editable at runtime via **Public Site CMS** (admin). Editorial typography (e.g. a serif display + clean grotesque body), generous spacing, micro-animations.

## 5) POS INTEGRATION (eWards-compatible JSON API)  — the live revenue path
Implement these POS endpoints under `/api/pos/...` (header `x-api-key` validated against `pos_credentials`; payload carries `merchant_id` + `customer_key`):
`posCustomerCheck`, `posCustomerCheckRequest`, `resendOtPcustomercheck`, `posCustomerOTPCheck`, `posAddCustomer`, `posRedeemPointRequest`, `resendOtPosRedeemPointRequest`, `posRedeemPointOtpCheck`, `posAddPoint`, `posCouponDetails`, `posRedeemCoupon`, `returnOrder`, `requestWalletRedemptionURL`, `getWalletRedemptionStatus`.

**CANONICAL LOYALTY RULES (enforce strictly):**
1. **Valid-Indian-mobile gate → "Lost Customers":** points/accounts only for a valid Indian mobile (10 digits starting 6–9). A bill with invalid/missing mobile is a NON-loyalty "Lost Customer" — recorded for purchase analytics (`is_lost_customer=true`, `customer_mobile=null`, keep `raw_mobile`), NO points/account/SMS, returns 200. `posAddCustomer` rejects invalid mobiles (400).
2. **Mobile canonicalisation everywhere:** match on last-10-digits (`_mobile_key`) so `+91…`/`0…`/`0091-…`/spaces/hyphens all resolve the same customer. OTP lookups match `{otp, purpose, $or:[mobile_key, mobile]}`.
3. **Redemption is OTP-only and applied ONCE.** Points are deducted in the redeem flow (`posRedeemPointRequest` non-OTP OR `posRedeemPointOtpCheck`). When the **bill** arrives (`posAddPoint`) it must **record** redeemed points for reporting but **NEVER deduct again** (double-deduction is a P0 bug — do not write a 2nd `redeem` ledger row from the bill).
4. **Earn math (config-driven):** Sales points base = bill `amount` (pre-tax loyalty base; Bill-with-tax = `amount` + `taxes.amount`(GST)). Returns base = `return_loyalty_gross_amount`. `min_bill_for_earn`, `block_earn_on_returns`, tier multiplier, category/store-type multipliers, earn/burn pauses all apply.
5. **Loyalty analytics exclude anonymous walk-ins** (filter `customer_mobile` not-null).
6. **returnOrder** keyed by **mobile** (original bill optional, best-effort enrichment); reverses points + decrements spend; writes a return txn + ledger adjust.
- **Live Bill Monitor** page: real-time bill feed with KPI cards (incl. Lost Cust. / Lost Purchase), "Recalc points" (today-IST, pos_ewards-only), distinct styling for lost/return rows.

## 6) LOYALTY ENGINE (Loyalty Rules editor)
Config doc with: `earn_mode` (points_per_spend), `earn_ratio`, `burn_ratio` (₹/point), `min_redeem_points`, `point_expiry_days` (+ per-tier override), `welcome_bonus`, `min_bill_for_earn`, `block_earn_on_returns`, `require_otp_for_redeem`, `earn_enabled`/`burn_enabled`, `earn_burn_pauses`, `category_multipliers`, `store_type_multipliers`, and **`tier_rules`** (Silver/Gold/Platinum/Diamond by `min/max_lifetime_spend`, `earn_multiplier`, welcome/birthday/anniversary/upgrade bonuses, colour). **Tiers come ONLY from this editor — no hardcoded fallback ladder.** Tier reset cadence/anchor. Points ledger (`earn`/`redeem`/`adjust`/`expire`) is the source of truth; opening-balance import supported.

## 7) DATA LAYER (bulk + integrity)
- **Historical Upload:** chunked CSV ingest (Customers / Transactions/Billing / SKU-wise / Stores datasets) as background jobs with progress, skipped-row capture, dedupe, **chunk retention** for healing. Auto-backfill stub customers from txn mobiles + recompute R1 (first_purchase_at), R2 (home/registered store by **store K-code**), R3 (visit/spend/earn aggregates). Opening balances valid till a configurable cutoff date; live POS points expire 1 yr from bill date; **all dates IST**.
- **Verify Load:** post-ingest sanity (counts, coverage, sample).
- **Data Reconciliation:** upload a source CSV per dataset and compare to DB (matched / missing-in-DB / amount & mobile mismatches / extra-in-DB). MUST: instant file listing, **Check & Heal** with an editable go-live cutoff date, parse OFF the event loop, heartbeat + stale-job watchdog, a **Cancel** button per job, and an optional "Deep DB-side scan" (off by default).

## 8) DASHBOARDS (13 — Recharts, IST, drill-downs, date-range picker, CSV export)
Command Center, Sales, Customer Analytics, Loyalty, Campaign Performance, Store Performance, RFM & Churn, Cohorts & Segments, Points Economics, Campaign ROI, Executive Summary, NPS & Feedback, plus the Live Bill Monitor. Each KPI/chart drill-down opens a transaction/customer table. Server-side aggregation with `days=0` = all-time (20-yr) sentinel; cache warming for heavy aggregations.

## 9) CUSTOMERS
- **Customer 360 / Customer Detail:** identity, tier, RFM, home/registered store, lifetime spend/visits/points, full bill history, points ledger, comms history, tickets, drawer view.
- **Segment Builder:** AND/OR rules over RFM/tier/spend/recency/city/store/category → saved audiences usable by campaigns.
- RFM segmentation, churn risk, cohort library.

## 10) MARKETING
- **Campaigns:** build audience (segment/upload), pick channel + template, schedule/send, track delivery/opens/redemptions, ROI.
- **Auto-Campaigns:** triggered journeys (welcome, birthday/anniversary, win-back/dormant, tier-upgrade, points-expiry reminder).
- **Coupons:** coupon engine (codes, validity, redemption rules, per-customer caps) integrated with POS `posCouponDetails`/`posRedeemCoupon`.

## 11) COMMUNICATIONS (Karix)
Integrate **Karix** SMS / WhatsApp / RCS (DLT-compliant: entity/template/header IDs). Templates manager, **Bulk Send Jobs** (chunked, throttled, retried), full **Message Log**, **Provider Settings** (API key, sender/header, DLT config). Karix API key is user-supplied — collect it, store in settings/.env, never hardcode.

## 12) AI COPILOTS — train EXACTLY like ours
### 12a) FUNDLE BRAIN (analyst + L1 ops) — chat with function-calling
- **Identity/system prompt:** "You are Fundle Brain, the AI analytics assistant AND operations agent for City Metro powered by Fundle." Direct READ access to live Mongo via tools; ALWAYS call a tool before any numeric answer; never fabricate ("Data not available" if empty after an all-time retry).
- **A live DATA-WAREHOUSE SNAPSHOT** is injected as a 2nd system message every turn: collections + row counts, bill-date coverage, brand KPI digest, and the loyalty config — treat as ground truth.
- **READ tools:** `get_overall_kpis, customer_search, customer_lookup, recent_bills_for_customer, points_ledger_for_customer, top_customers_report, top_skus, top_churning_customers, tier_distribution, rfm_segments, store_performance, city_performance, location_wise_customer_summary, campaign_leaderboard, coupon_performance, active_coupons_summary, communication_log_summary, nps_summary, tickets_summary, expiry_points_summary, pending_bills_summary, fraud_anomalies, support_desk_audit_log, list_redeemed_points, list_redeemed_coupons, list_deactivated_customers, list_unsubscribed, get_data_dictionary, run_aggregation, export_csv`.
- **`run_aggregation`** = read-only Mongo pipelines (call `get_data_dictionary` first if unsure of fields) → answers ANY slice by city/store/month/tier/category. **`export_csv`** streams up to 1,000,000 rows to a download link (return EXACTLY `[Download <file> (<n> rows)](<url>)`; never paste >20 rows inline).
- **WRITE (L1) tools, role-gated + audit-logged:** `customer_deactivate, customer_reactivate, unsubscribe_customer, resubscribe_customer, reactivate_coupon_redemption, reactivate_redeem_points`. Protocol: never write without explicit intent → look up target first → require a REASON → confirm in plain English + cite the audit entry.
- **IST timezone rule:** never string-slice dates; group/format with `$dateToString`/`$dateTrunc` `timezone:"Asia/Kolkata"`. Currency in ₹. End with 1–2 recommended actions. CSV uploads in chat are reasoned over inline. A floating Fundle-Brain FAB is available across admin.

### 12b) MASTER BRAIN (privileged operator) = Fundle Brain + ACTION layer
- Gated to **Master Admins**. System prompt = Fundle Brain's FULL prompt **+ a Master addendum**: "You are Master Brain… as smart as Fundle Brain on reads, PLUS authority to execute — always **preview → confirm (with a reason) → execute → log**." It MUST still answer every read/analytics/export exactly like Fundle Brain (never downgrade).
- **ACTION tools (two-turn execute pattern, write to `audit_logs` + snapshots for Undo):** `grant_bonus_points, adjust_points, fix_negative_balances, retier_customers, set_customer_tier, apply_to_uploaded_report, send_campaign (Karix bulk), list_campaigns, cancel_campaign, master_action_log, undo_action`, and **`fix_double_redemptions`** (find duplicate redemption deductions — bug rows whose note starts "Bill " that ALSO have a legit OTP/non-OTP redeem row for the same bill — credit the points back, correct `lifetime_points_redeemed`, void the duplicate ledger rows; idempotent; preview→confirm+reason; not auto-undoable).
- Recommendations the agent CAN execute render a one-click **Execute** button; each applied action shows in the **Action Log** with an **Undo** (where a snapshot exists). A per-user **Query Log** records every Master-Brain input; a Query Admin sees everyone's.

## 13) REPORTS
Downloads Center, Reports (Legacy), Shopper Bill Report, Store KPI Report, CRM Customer Report, KPI Trends, Reports & Exports, Exec Digests (scheduled email/PDF summaries), Formula Catalog (documents every KPI's formula). All respect R1 (bill_date = source of truth) + R5 (loyalty filter).

## 14) OPERATIONS
Stores (master by **K-code**, tagged `pos_customer_key`+`pos_merchant_id` to align 1:1 with POS; bulk upload), Item Master (SKU catalog), **API Monitor** (every POS call logged with request/response/latency/errors + diffs), POS Credentials (issue/rotate `x-api-key`, merchant_id, customer_key).

## 15) SUPPORT
Tickets (+ detail), NPS Inbox, and a **Support Desk** of OTP-gated L1 actions: Search Redeem-Points OTP, Search Redeem-Coupon OTP, Reactivate Coupon, Reactivate Redeem Points, Customer Deactivate/Reactivate, Update Mobile, Unsubscribe, Support Desk Audit log.

## 16) USER MANAGEMENT
Admin CRUD for users/roles, master-admin & query-admin flags, activity/audit visibility.

## 17) ENV VARS (backend/.env)
`MONGO_URL, DB_NAME, CORS_ORIGINS, JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRY_HOURS, EMERGENT_LLM_KEY, BRAND_NAME, SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD, BRAND_ADMIN_EMAIL, BRAND_ADMIN_PASSWORD` (+ Karix keys in Provider Settings). Frontend: `REACT_APP_BACKEND_URL`.

## 18) BUILD ORDER (phase-by-phase, test each)
1. Auth + roles + brand config + design system + admin shell/sidebar.
2. Data model + Loyalty Rules editor + points ledger.
3. POS API (all endpoints + canonical rules) + Live Monitor + API Monitor + POS Credentials.
4. Historical Upload + Verify Load + Reconciliation (with watchdog/cancel).
5. Customers (360, segments, RFM) + Stores + Item Master.
6. 13 Dashboards + drill-downs + exports.
7. Communications (Karix) + Campaigns + Auto-Campaigns + Coupons.
8. Fundle Brain (reads + L1 writes + run_aggregation + export_csv + data snapshot).
9. Master Brain (action layer + Execute buttons + Action Log/Undo + Query Log + fix_double_redemptions).
10. Reports suite + NPS + Tickets + Support Desk + Public site/CMS.

**Ask me for the Karix API key when you reach Phase 7, and confirm the City Metro palette/logo before Phase 1. Build production-grade, test every phase (use the testing agent for multi-endpoint/CRUD flows), and keep all brand strings in the 3 rebrand points.**
