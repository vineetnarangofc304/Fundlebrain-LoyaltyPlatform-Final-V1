# EMERGENT BUILD PROMPT — "DOODLES CINEMA" (Loyalty + CRM + Analytics + AI platform)

> Paste this whole prompt into a NEW Emergent project to build the platform for the cinema brand **Doodles Cinema**. It reproduces, end-to-end, an enterprise single-tenant loyalty/CRM/analytics/campaign-automation/customer-intelligence/support platform (the same product we already run for KAZO), rebranded and lightly domain-adapted for a multiplex cinema chain. Build it in phases, test each phase, and keep everything production-grade.

---

## 0) WHAT TO BUILD (one line)
Build a single-tenant, enterprise-grade **Loyalty + CRM + Analytics + Campaign Automation + Customer Intelligence + Support + Reporting + API-monitoring** platform for **Doodles Cinema**, with a live POS integration (box-office + concessions), a public loyalty microsite, 13 analytics dashboards, and two AI copilots ("Fundle Brain" = analyst, "Master Brain" = privileged operator). The loyalty engine is **Fundle** ("Powered by Fundle") — keep that platform identity; only the customer-facing brand is Doodles Cinema.

## 1) BRAND IDENTITY (the ONLY things that change vs the base product)
- **Brand name:** Doodles Cinema
- **Descriptor:** "a premium multiplex cinema chain" (movie tickets + F&B/concessions + merchandise + gaming)
- **Public domain:** doodlescinema.com
- **Loyalty programme name:** "Doodles Club"
- **Welcome bonus:** 100 points on signup (e.g. "₹100 snack credit on joining")
- **Platform engine:** Fundle · AI copilots: **Fundle Brain** + **Master Brain** (keep these names & training verbatim)
- **Palette suggestion:** cinematic-editorial — warm ink/charcoal base, a single bold accent (marquee-red `#E11D2A` or screen-gold `#D4A23B`). Keep a LIGHT editorial theme (NOT dark, NOT purple-on-white "AI slop"); cinema warmth via accent + grain texture, not a dark dump.
- **Centralise ALL brand strings** in `frontend/src/brand.config.js` (single source of truth) and the `--brand-*` CSS variables in `index.css`, plus `BRAND_NAME` / admin emails in `backend/.env`. Rebranding must only require editing those 3 places.

### CINEMA DOMAIN MAPPING (functionality identical — only labels/framing differ)
- **Stores → "Properties"** = cinema locations (each with screens/audis); identity by **property K-code**, tagged `pos_customer_key`+`pos_merchant_id`.
- **Bills/Transactions** = box-office ticket bookings + concession (F&B) bills + merchandise; a single visit may have a ticket bill and an F&B bill.
- **Item Master / SKUs** = concession items, combos, ticket classes (Recliner/Premium/Regular), movies/shows.
- **Categories** for multipliers = `Tickets`, `F&B`, `Merchandise`, `Gaming`.
- **Tiers** (cinema-flavoured, still spend-driven & fully editable): Silver → Gold → Platinum → **Director's Circle**.
- Keep EVERYTHING else (engine, dashboards, AI, POS rules) exactly as the base product.

## 2) TECH STACK & NON-NEGOTIABLE ARCHITECTURE
- **Backend:** FastAPI + **Motor (async MongoDB)** + APScheduler + custom JWT (PyJWT + bcrypt). Python 3.11.
- **Frontend:** React (CRA) + React Router + Tailwind + **shadcn/ui** + lucide-react + Recharts + sonner. NO emoji icons.
- **AI:** **Emergent Universal LLM key** via `emergentintegrations` (GPT-4o/Claude text, OpenAI TTS, Gemini Nano-Banana for images). Do NOT install vendor SDKs directly.
- **Routing rules (hard):** all backend routes prefixed **`/api`**; backend `0.0.0.0:8001`; frontend calls **only** `process.env.REACT_APP_BACKEND_URL`; Mongo via **`MONGO_URL`** + `DB_NAME`. No hardcoded URLs/ports/secrets.
- **Mongo discipline:** never return raw `_id` (`PyObjectId`/`BaseDocument` + `to_mongo`/`from_mongo`); `datetime.now(timezone.utc)`; stored dates are ISO strings.
- **Heavy jobs:** CPU parse via `asyncio.to_thread`, **heartbeat + stale-recovery watchdog** (auto-fail if no heartbeat > 8 min), `await asyncio.sleep(0)` between DB batches, chunked uploads (1.5 MB).
- Modular `/backend/routes/*` + frontend pages under `src/pages/{admin,auth,public,store}`.

## 3) AUTH & ROLES (RBAC)
- Custom JWT (email+password, bcrypt). Seed super_admin + brand_admin from `.env`. Roles: `super_admin, brand_admin, crm_manager, support_agent, store_user (property staff), analyst/viewer`. Flags: **`is_master_admin`** (Master Brain actions) + **`is_master_query_admin`** (query-log oversight). Login routes `/crm/login`, `/store/login`. Every write audit-logged. Save creds to `/app/memory/test_credentials.md`.

## 4) PUBLIC LOYALTY MICROSITE (CMS-driven)
Pages: Home, How It Works, Earn Points (on tickets & snacks), Redeem Points (free tickets/combos/upgrades), Rewards, Loyalty Benefits, Tiers, Referral Program, **Property/Cinema Locator**, About Program, FAQs, Contact, Privacy, Terms. Join-free CTA + welcome credit. All copy/images editable via **Public Site CMS**. Editorial typography, generous spacing, micro-animations, subtle cinema grain.

## 5) POS INTEGRATION (eWards-compatible JSON API) — box-office + concessions
Endpoints under `/api/pos/...` (header `x-api-key` ↔ `pos_credentials`; payload `merchant_id`+`customer_key`):
`posCustomerCheck, posCustomerCheckRequest, resendOtPcustomercheck, posCustomerOTPCheck, posAddCustomer, posRedeemPointRequest, resendOtPosRedeemPointRequest, posRedeemPointOtpCheck, posAddPoint, posCouponDetails, posRedeemCoupon, returnOrder, requestWalletRedemptionURL, getWalletRedemptionStatus`.

**CANONICAL LOYALTY RULES (enforce strictly):**
1. **Valid-Indian-mobile gate → "Lost Customers":** loyalty only for valid Indian mobile (10 digits, 6–9). Invalid/missing → non-loyalty "Lost Customer" (recorded for analytics, no points/account/SMS, 200). `posAddCustomer` rejects invalid (400).
2. **Mobile canonicalisation** on last-10-digits (`_mobile_key`) everywhere; OTP lookups `{otp, purpose, $or:[mobile_key, mobile]}`.
3. **Redemption is OTP-only and applied ONCE** in the redeem flow. When the **bill** (`posAddPoint`) arrives it RECORDS redeemed points for reporting but **NEVER deducts again** (double-deduction is a P0 bug — no 2nd `redeem` ledger row from the bill).
4. **Earn math (config-driven):** Sales base = bill `amount` (pre-tax; Bill-with-tax = `amount`+`taxes.amount` GST). Returns base = `return_loyalty_gross_amount`. `min_bill_for_earn`, `block_earn_on_returns`, tier/category/property multipliers, earn/burn pauses all apply. (Tickets vs F&B can carry different category multipliers.)
5. **Loyalty analytics exclude anonymous walk-ins** (`customer_mobile` not-null).
6. **returnOrder/cancellation** keyed by **mobile** (original booking optional), reverses points + decrements spend, writes return txn + ledger adjust.
- **Live Bill Monitor:** real-time feed of ticket+F&B bills, KPI cards (incl. Lost Cust./Lost Purchase), "Recalc points" (today-IST, pos-only), distinct lost/return styling.

## 6) LOYALTY ENGINE (Loyalty Rules editor)
Config: `earn_mode` (points_per_spend), `earn_ratio`, `burn_ratio`, `min_redeem_points`, `point_expiry_days` (+per-tier override), `welcome_bonus`, `min_bill_for_earn`, `block_earn_on_returns`, `require_otp_for_redeem`, `earn_enabled`/`burn_enabled`, `earn_burn_pauses`, `category_multipliers` (Tickets/F&B/Merch/Gaming), `store_type_multipliers`, **`tier_rules`** (Silver/Gold/Platinum/Director's Circle by lifetime spend, multipliers, welcome/birthday/anniversary/upgrade bonuses, colour). **Tiers ONLY from this editor — no hardcoded ladder.** Points ledger (earn/redeem/adjust/expire) is the source of truth; opening-balance import supported.

## 7) DATA LAYER (bulk + integrity)
- **Historical Upload:** chunked CSV ingest (Members / Bookings+Bills / Concession-SKU / Properties datasets) as background jobs w/ progress, skipped-row capture, dedupe, **chunk retention** for healing. Auto-backfill stub members from txn mobiles + recompute R1 (first_visit_at), R2 (home/registered property by K-code), R3 (visit/spend/earn aggregates). Opening balances valid till a configurable cutoff; live points expire 1 yr from bill date; **all dates IST**.
- **Verify Load:** post-ingest sanity. 
- **Data Reconciliation:** upload source CSV per dataset, compare to DB (matched/missing/amount&mobile mismatch/extra). MUST: instant file listing, **Check & Heal** w/ editable go-live cutoff, parse OFF the event loop, heartbeat + stale-job watchdog, per-job **Cancel**, optional "Deep DB-side scan" (off by default).

## 8) DASHBOARDS (13 — Recharts, IST, drill-downs, date-range, CSV export)
Command Center, Sales (box-office + F&B split), Customer Analytics, Loyalty, Campaign Performance, **Property Performance** (per-cinema), RFM & Churn, Cohorts & Segments, Points Economics, Campaign ROI, Executive Summary, NPS & Feedback, + Live Bill Monitor. Drill-downs to bills/members. `days=0` = all-time sentinel; cache-warm heavy aggregations.

## 9) CUSTOMERS (Members)
- **Member 360 / detail:** identity, tier, RFM, home/registered property, lifetime spend/visits/points, full booking+F&B history, points ledger, comms history, tickets.
- **Segment Builder:** AND/OR over RFM/tier/spend/recency/city/property/category/favourite-genre → saved audiences for campaigns.
- RFM, churn risk, cohorts.

## 10) MARKETING
- **Campaigns:** audience → channel + template → schedule/send → delivery/opens/redemptions + ROI.
- **Auto-Campaigns:** welcome, birthday/anniversary, win-back/dormant, tier-upgrade, points-expiry reminder, "new release near your favourite property".
- **Coupons:** combo/upgrade/free-ticket coupons (codes, validity, caps) wired to POS `posCouponDetails`/`posRedeemCoupon`.

## 11) COMMUNICATIONS (Karix)
**Karix** SMS / WhatsApp / RCS (DLT: entity/template/header IDs). Templates, **Bulk Send Jobs** (chunked/throttled/retried), **Message Log**, **Provider Settings**. Karix key is user-supplied — collect & store in settings/.env, never hardcode.

## 12) AI COPILOTS — train EXACTLY like ours
### 12a) FUNDLE BRAIN (analyst + L1 ops)
- **System prompt:** "You are Fundle Brain, the AI analytics assistant AND operations agent for Doodles Cinema powered by Fundle." READ access to live Mongo via tools; ALWAYS call a tool before numeric answers; never fabricate ("Data not available" after an all-time retry).
- A live **DATA-WAREHOUSE SNAPSHOT** (collections+counts, bill-date coverage, KPI digest, loyalty config) is injected as a 2nd system message each turn — ground truth.
- **READ tools:** `get_overall_kpis, customer_search, customer_lookup, recent_bills_for_customer, points_ledger_for_customer, top_customers_report, top_skus, top_churning_customers, tier_distribution, rfm_segments, store_performance, city_performance, location_wise_customer_summary, campaign_leaderboard, coupon_performance, active_coupons_summary, communication_log_summary, nps_summary, tickets_summary, expiry_points_summary, pending_bills_summary, fraud_anomalies, support_desk_audit_log, list_redeemed_points, list_redeemed_coupons, list_deactivated_customers, list_unsubscribed, get_data_dictionary, run_aggregation, export_csv`. (`store_performance`/`city_performance` = property/city.)
- **`run_aggregation`** = read-only Mongo pipelines (call `get_data_dictionary` first); **`export_csv`** streams ≤1,000,000 rows → return EXACTLY `[Download <file> (<n> rows)](<url>)`; never paste >20 rows inline.
- **WRITE (L1) tools, role-gated + audited:** `customer_deactivate, customer_reactivate, unsubscribe_customer, resubscribe_customer, reactivate_coupon_redemption, reactivate_redeem_points`. Protocol: explicit intent → look up first → require REASON → confirm + cite audit entry.
- **IST rule:** never string-slice dates; use `$dateToString`/`$dateTrunc` `timezone:"Asia/Kolkata"`. ₹ currency, end with 1–2 actions. Floating Fundle-Brain FAB across admin.

### 12b) MASTER BRAIN = Fundle Brain + ACTION layer (Master Admins only)
- System prompt = Fundle Brain's full prompt **+ Master addendum**: "always **preview → confirm (with reason) → execute → log**"; still answers every read/analytics/export like Fundle Brain.
- **ACTION tools (two-turn; write `audit_logs` + Undo snapshots):** `grant_bonus_points, adjust_points, fix_negative_balances, retier_customers, set_customer_tier, apply_to_uploaded_report, send_campaign (Karix bulk), list_campaigns, cancel_campaign, master_action_log, undo_action`, and **`fix_double_redemptions`** (find duplicate redemption deductions — bug `redeem` rows whose note starts "Bill " that ALSO have a legit OTP/non-OTP redeem row for the same bill — credit points back, fix `lifetime_points_redeemed`, void duplicate rows; idempotent; preview→confirm+reason; not auto-undoable).
- Executable recommendations show a one-click **Execute** button; applied actions appear in the **Action Log** with **Undo** (where a snapshot exists). Per-user **Query Log**; Query Admin sees all.

## 13) REPORTS
Downloads Center, Reports (Legacy), **Shopper/Booking Bill Report**, **Property KPI Report**, CRM/Member Report, KPI Trends, Reports & Exports, Exec Digests (scheduled email/PDF), Formula Catalog. Respect R1 (bill_date) + R5 (loyalty filter).

## 14) OPERATIONS
**Properties** (master by K-code, tagged `pos_customer_key`+`pos_merchant_id`, bulk upload), Item Master (concession SKUs/combos/ticket classes), **API Monitor** (every POS call: request/response/latency/errors/diffs), POS Credentials (issue/rotate `x-api-key`, merchant_id, customer_key).

## 15) SUPPORT
Tickets (+detail), NPS Inbox, **Support Desk** (OTP-gated L1): Search Redeem-Points OTP, Search Redeem-Coupon OTP, Reactivate Coupon, Reactivate Redeem Points, Member Deactivate/Reactivate, Update Mobile, Unsubscribe, Support Desk Audit.

## 16) USER MANAGEMENT
Admin CRUD for users/roles, master-admin & query-admin flags, audit visibility.

## 17) ENV VARS (backend/.env)
`MONGO_URL, DB_NAME, CORS_ORIGINS, JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRY_HOURS, EMERGENT_LLM_KEY, BRAND_NAME, SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD, BRAND_ADMIN_EMAIL, BRAND_ADMIN_PASSWORD` (+ Karix keys in Provider Settings). Frontend: `REACT_APP_BACKEND_URL`.

## 18) BUILD ORDER (phase-by-phase, test each)
1. Auth + roles + brand config + design system + admin shell/sidebar.
2. Data model + Loyalty Rules editor + points ledger.
3. POS API (all endpoints + canonical rules) + Live Monitor + API Monitor + POS Credentials.
4. Historical Upload + Verify Load + Reconciliation (watchdog/cancel).
5. Members (360, segments, RFM) + Properties + Item Master.
6. 13 Dashboards + drill-downs + exports.
7. Communications (Karix) + Campaigns + Auto-Campaigns + Coupons.
8. Fundle Brain (reads + L1 writes + run_aggregation + export_csv + data snapshot).
9. Master Brain (action layer + Execute + Action Log/Undo + Query Log + fix_double_redemptions).
10. Reports + NPS + Tickets + Support Desk + Public site/CMS.

**Ask me for the Karix API key at Phase 7, and confirm the Doodles Cinema palette/logo before Phase 1. Keep ticket vs F&B as separate category multipliers, build production-grade, test every phase, and keep all brand strings in the 3 rebrand points.**
