# EMERGENT BUILD PROMPT — "CITY METRO"  (Loyalty + CRM + Analytics + AI platform — full clone)

You are building an enterprise, single-tenant **Loyalty + CRM + Analytics + Campaign-Automation + Customer-Intelligence + Support + Reporting + POS-API-monitoring** platform for the brand **CITY METRO**. This product already exists and is fully built — DO NOT reinvent it. Start from our public GitHub repo (below), run it, then apply the City Metro brand + the brand's POS + the changes in this prompt. Keep EVERY feature: all dashboards, the full POS integration, historical/old-data ingestion, reconciliation, communications, both AI copilots (Fundle Brain + Master Brain), reports, support desk, user management, and the public site. Build/verify in phases.

==================================================================
A) SOURCE OF TRUTH — IMPORT FROM GITHUB FIRST (do this before anything else)
==================================================================
- The complete, working codebase is **PUBLIC on GitHub**. Pull it and use it as the baseline; only adapt brand + POS + the items below. Do not omit modules.
- **Repo URL:**            `<<PASTE YOUR PUBLIC GITHUB REPO URL HERE>>`
- **Branch / tag:**        `<<e.g. main (latest)>>`
- **GitHub username:**     `<<YOUR GITHUB USERNAME>>`
- **Access (if needed):**  `<<leave blank if public; else connect GitHub / paste a read-only PAT>>`
- Steps: (1) Import the repo into this project (use Emergent's "Import from GitHub"/clone). (2) Install backend (`pip install -r backend/requirements.txt`, incl. `emergentintegrations`) + frontend (`yarn`). (3) Boot both via supervisor and confirm the app runs and seeds the super-admin. (4) THEN apply sections B–C and the brand block. If any file/feature in this prompt is missing from the repo, BUILD it to match this spec.

==================================================================
B) POS IS CONFIGURABLE — IT IS **NOT ALWAYS eWARDS**  (ask first, then adapt)
==================================================================
- Our reference build integrates a POS called **eWards**. City Metro may use a **different POS** (e.g. **Genesis**, or another vendor).
- **FIRST, ASK ME:** "Which POS does City Metro use — eWards, Genesis, or another (name it)? Do you have the POS API documentation (endpoints, auth/header scheme, request & response JSON, OTP flow, redemption flow, returns/cancellation, coupons, wallet)? Paste it or share a link."
- Then **MAP our canonical loyalty functionality onto that POS's actual API**:
  - KEEP 100% of the business logic identical (earn/redeem/tiers/lost-customer gate/mobile-canonicalisation/OTP-once redemption/returns/coupons/wallet — see §5, §6, §7).
  - **ADD** any endpoints, headers, or request/response fields the new POS documentation requires.
  - **REMOVE/RENAME** any eWards-specific endpoints or fields the new POS does not have.
  - Preserve the exact endpoint NAMES only if the new POS uses them; otherwise expose the new POS's endpoint names but route them to the same internal handlers.
  - Produce a short **POS mapping doc** (their field ↔ our field) and log every POS call in the API Monitor.
- If no documentation is provided, ASK before assuming a schema — never guess silently.
- Everything downstream of the POS (ledger, customers, dashboards, AI, reports) is **POS-agnostic** and unchanged.

==================================================================
C) REMOVE ALL "EMERGENT" / BUILDER BRANDING EVERYWHERE
==================================================================
- Strip every trace of the builder: any "Made with Emergent" / "Powered by Emergent" badge or floating button, `index.html` title/meta/OG tags, favicon, console banners, footer mentions, and any "emergent" string in copy or assets. The app must surface ONLY **City Metro** + **"Powered by Fundle"**. (The Emergent LLM key is still used internally for AI — that's fine; just no visible Emergent branding.)

==================================================================
1) BRAND IDENTITY  (the only customer-facing things that change)
==================================================================
- **Brand:** City Metro — "a multi-category urban lifestyle & fashion retail chain" (apparel, footwear, accessories, beauty, home).
- **Public domain:** citymetro.com · **Loyalty programme:** "City Metro Privileges" · **Welcome bonus:** 100 pts.
- **Platform engine stays "Fundle"; AI copilots stay "Fundle Brain" + "Master Brain"** (keep their names & training verbatim).
- **Palette:** urban-editorial — charcoal/ink base, brushed-steel neutrals, ONE confident accent (deep teal `#0E7C7B` or metro-cobalt). LIGHT editorial theme. Avoid AI-slop (no purple-on-white, no generic Inter-on-white card grids). Custom display serif + clean grotesque body, generous whitespace, micro-animations.
- **Rebrand is confined to 3 places ONLY:** `frontend/src/brand.config.js` (all display strings, logos, social, SEO, public copy), the `--brand-*` (or `--kazo-*`) CSS variables in `frontend/src/index.css` (swap hex values, keep variable NAMES + class names), and `BRAND_NAME` + admin emails in `backend/.env`. Also update `frontend/public/index.html` static title/meta. **Confirm palette + logo with me before Phase 1.**

==================================================================
2) TECH STACK & NON-NEGOTIABLE ARCHITECTURE
==================================================================
- **Backend:** FastAPI + **Motor (async MongoDB)** + APScheduler (schedulers/watchdogs/cache-warmers) + custom JWT (PyJWT + bcrypt). Python 3.11.
- **Frontend:** React (CRA) + React Router + Tailwind + **shadcn/ui** + lucide-react icons + Recharts + sonner toasts. NO emoji icons.
- **AI:** **Emergent Universal LLM key** via `emergentintegrations` (GPT-4o / Claude for text, OpenAI for TTS, Gemini "Nano-Banana" for any images). Do NOT install vendor SDKs directly.
- **Hard routing rules:** every backend route prefixed **`/api`**; backend binds `0.0.0.0:8001` (supervisor-managed); frontend calls **only** `process.env.REACT_APP_BACKEND_URL`; Mongo via **`MONGO_URL`** + `DB_NAME` from env. No hardcoded URLs / ports / secrets — omit fallbacks so missing config fails fast. Never edit the protected env keys' meaning.
- **Mongo discipline:** never return raw `_id` (use `PyObjectId`/`BaseDocument` with `to_mongo`/`from_mongo`); all datetimes `datetime.now(timezone.utc)`; **stored dates are ISO strings**; index hot fields (mobile, mobile_key, bill_number, bill_date, store code, ledger type).
- **Heavy/background jobs (CRITICAL):** any large CSV parse or cross-check runs OFF the event loop — CPU parse via `asyncio.to_thread`; write a **heartbeat** through the run + a **stale-recovery watchdog** that auto-fails any job with no heartbeat for > 8 min (so a pod restart can't leave a job "running" forever); `await asyncio.sleep(0)` between DB batches; **chunked uploads** (1.5 MB chunks, retained for healing). Provide a **Cancel** control on long jobs.
- **Modular layout:** `/backend/routes/*` (auth, pos, loyalty, customers, dashboard, analytics, drilldown, segments, campaigns, auto_campaigns, coupons, communications, ai/fundlebrain (+ai_tools, ai_extended_tools, ai_data_expert), master_brain (+master_brain_tools), historic, recon, stores, items, live_monitor, api_monitor, reports (+kpi, shopper, store_kpi, crm_customer, legacy, raw, exports, digests, formula_catalog), nps, tickets, support_desk, users, public, cms, demo). Frontend pages under `src/pages/{admin,auth,public,store}`.

==================================================================
3) DATA MODEL (core collections — keep field names stable)
==================================================================
- **users:** email, password_hash, name, role, is_active, is_master_admin, is_master_query_admin, created_at.
- **customers:** mobile, mobile_key (last-10 canonical), name, email, city, state, gender, language, birthday, anniversary, card_validity, tier, points_balance, lifetime_points_earned, lifetime_points_redeemed, lifetime_spend, visit_count, first_purchase_at, last_visit_at, days_since_last_visit, home_store_id, registered_store_id, first_purchase_store_id, source (pos / historic / auto_from_transactions), is_lost_customer, raw_mobile, is_active, unsubscribed, created_at.
- **transactions:** bill_number, transaction_id, customer_mobile, customer_id, store_id, store_code, bill_date (ISO, IST-aware), amount (pre-tax loyalty base), taxes[{name:GST, amount}], net_amount, total_revenue, points_earned, points_redeemed, redemption_value, is_return, original_bill_number, source (pos / historic), is_lost_customer, line_items[{sku, name, qty, amount, category}], created_at.
- **points_ledger:** type (earn|redeem|adjust|expire), points (+/-), reference_type, reference_id, note, customer_id, customer_mobile, created_at, expires_at, voided, original_points, voided_by/at/reason. **This ledger is the source of truth for balances.**
- **loyalty_config:** full config doc (see §7).
- **stores:** code (K-code, canonical identity), name, city, pos_customer_key, pos_merchant_id, is_active.
- **items:** sku, name, category, brand, mrp/price, attributes.
- **pos_credentials:** label, api_key (x-api-key), merchant_id, customer_key, is_active.
- **otps:** mobile, mobile_key, otp, purpose (customer_check | redeem_points | redeem_coupon), created_at, expires_at, consumed.
- **campaigns / auto_campaigns / coupons / segments / master_campaigns.**
- **communications (message_log) / comm_templates / bulk_jobs / provider_settings.**
- **audit_logs / support_desk audit / ai_chats / mb_action_snapshots / mb_query_log.**
- **historic_ingest_jobs / historic_skipped_rows / historic_uploads / historic_chunks (chunks_retained flag).**
- **recon_jobs (heartbeat, phase, deep_scan, cancel_requested) / recon_mismatches.**
- **api_monitor (request, response, latency, status, error, diff) / cms_content / nps / tickets.**

==================================================================
4) AUTH & ROLES (RBAC)
==================================================================
- Custom JWT (email+password, bcrypt). Seed **super_admin** + **brand_admin** from `.env`. Roles: `super_admin, brand_admin, crm_manager, support_agent, store_user, analyst/viewer`. Flags: **`is_master_admin`** (may use the Master Brain action layer) and **`is_master_query_admin`** (sees the global Master-Brain query log). Login routes: `/crm/login` (admin/CRM), `/store/login` (store ops). Every mutation is **audit-logged**. Save all seeded credentials to `/app/memory/test_credentials.md`.

==================================================================
5) CANONICAL LOYALTY DATA RULES — ENFORCE STRICTLY (R1–R6)
==================================================================
- **R1 — bill_date is the source of truth** for all time-based analytics (NOT created_at).
- **R2 — store resolution:** home/registered store resolved by **store K-code**; registered store (from POS account / "Registered Account" `<K-code>@brand`) is authoritative regardless of load order; bill-derived store → first_purchase_store_id.
- **R3 — aggregates** (visit_count, lifetime_spend, lifetime_points_earned) are recomputed from the ledger + bills, never trusted blindly from CSV.
- **R4 — points expiry:** opening-balance/historical points valid till a configurable cutoff date; live POS points expire 1 year from bill date (per-tier override allowed). All in IST.
- **R5 — loyalty analytics exclude anonymous walk-ins:** filter `customer_mobile` not-null.
- **R6 — Valid-Indian-mobile gate → "Lost Customers":** loyalty only for a valid Indian mobile (10 digits starting 6–9; `_is_valid_indian_mobile`). A bill with invalid/missing mobile is a NON-loyalty **Lost Customer** — recorded for purchase analytics (`is_lost_customer=true`, `customer_mobile=null`, keep `raw_mobile`), NO points/account/SMS, returns 200. `posAddCustomer` rejects invalid Indian mobiles (400).
- **Mobile canonicalisation everywhere:** match on last-10-digits (`_mobile_key`) so `+91…`/`0…`/`0091-…`/spaces/hyphens resolve the same customer; OTP lookups match `{otp, purpose, $or:[mobile_key, mobile]}` (latest first); all 7 POS read lookups use a single `_find_customer_by_mobile()` (exact → last-10 → trailing-digits regex).
- **IST timezone:** never derive a calendar date by slicing the first 10 chars of an ISO string (off-by-one across midnight). Always convert with `$dateToString`/`$dateTrunc` `timezone:"Asia/Kolkata"` for grouping/formatting/display.

==================================================================
6) POS INTEGRATION — canonical functionality (map onto City Metro's POS from §B)
==================================================================
Implement these capabilities (eWards endpoint names shown for reference; rename/add/remove per the chosen POS's docs). Auth via per-merchant `x-api-key` ↔ `pos_credentials`; payload carries `merchant_id` + `customer_key`:
- **Customer lookup & enrolment:** posCustomerCheck, posCustomerCheckRequest, resendOtPcustomercheck, posCustomerOTPCheck, posAddCustomer.
- **Redemption (OTP):** posRedeemPointRequest, resendOtPosRedeemPointRequest, posRedeemPointOtpCheck. **Redemption is applied EXACTLY ONCE** (in the redeem flow). When the sale bill arrives (posAddPoint) it **records** redeemed points for reporting/recon parity but **NEVER deducts again** — do NOT write a 2nd `redeem` ledger row from the bill. (This double-deduction was a real P0 bug; prevent it.)
- **Earning (the sale bill):** posAddPoint — computes earn from `amount` (pre-tax base; bill-with-tax = amount + taxes.amount(GST)) × tier/category/store multipliers, honouring min_bill_for_earn, block_earn_on_returns, earn/burn pauses, welcome/upgrade bonuses; writes a transaction + earn ledger entry + updates customer aggregates; enforces R6 (lost customers) and duplicate-bill guard.
- **Coupons:** posCouponDetails, posRedeemCoupon (validity, caps, single-use).
- **Returns / cancellation:** returnOrder — keyed by **mobile** (original bill optional best-effort); reverses points via `return_loyalty_gross_amount`, decrements spend/points, writes a return txn (`is_return`, `bill_number=RET-…`) + ledger adjust.
- **Wallet redemption:** requestWalletRedemptionURL, getWalletRedemptionStatus.
- **Live Bill Monitor** page: real-time bill feed with KPI cards (incl. **Lost Cust.** + **Lost Purchase**), distinct styling for lost/return rows, and a "Recalc points" action (today-IST, **pos-only** so historical bills are never re-credited).
- **API Monitor:** every POS call logged with request/response/latency/status/error + a human-readable diff for failures.

==================================================================
7) LOYALTY ENGINE (Loyalty Rules editor — fully config-driven)
==================================================================
Config doc fields: `earn_mode` (points_per_spend), `earn_ratio`, `burn_ratio` (₹/point), `min_redeem_points`, `point_expiry_days` (+ per-tier `point_expiry_override_days`), `welcome_bonus`, `min_bill_for_earn`, `block_earn_on_returns`, `require_otp_for_redeem`, `earn_enabled`, `burn_enabled`, `earn_burn_pauses[]`, `category_multipliers{}`, `store_type_multipliers{online,offline}`, `tier_reset_cadence`, `tier_reset_anchor_date`, and **`tier_rules[]`** (Silver/Gold/Platinum/Diamond: name, min/max_lifetime_spend, earn_multiplier, welcome/birthday/anniversary/upgrade bonuses, colour, point_expiry_override_days). **Tiers come ONLY from this editor — never a hardcoded fallback ladder.** Validate ascending min_lifetime_spend. Editor UI to manage all of it.

==================================================================
8) DATA LAYER — OLD/HISTORICAL DATA + INTEGRITY (must be complete)
==================================================================
- **Historical Upload (old data):** chunked CSV ingest for datasets **Customers / Transactions(Billing) / SKU-wise Billing / Stores** as background jobs with live progress, skipped-row capture (with reasons), dedupe, and **chunk retention** (raw bytes kept) so files can be healed/re-ingested. Mappers extract the **Registered Account** store K-code; a post-pass links code→store (auto-creating stub stores) and sets registered/home store. **Auto-backfill** stub customers from transaction mobiles + recompute R1/R2/R3. Opening balances imported into the ledger, valid till the configurable cutoff (R4).
- **Verify Load:** post-ingest sanity — counts, bill-date coverage, distinct SKUs/customers/stores, sample rows.
- **Data Reconciliation:** upload a source CSV per dataset and compare against the DB → **matched / missing-in-DB / amount mismatch / mobile mismatch / extra-in-DB**, with per-mismatch CSV download. MUST: list all loaded files instantly; **Check & Heal** with an **editable loyalty go-live cutoff date**; parse OFF the event loop (`asyncio.to_thread`); heartbeat + **stale-job watchdog** (auto-fail > 8 min); a **Cancel** button per run; an optional **"Deep DB-side scan"** (off by default — the full DB-side extra-rows scan) so normal runs stay fast. Must handle ~800k-row files without stalling.

==================================================================
9) DASHBOARDS (13 + Live Monitor — Recharts, IST, drill-downs, date-range picker, CSV export)
==================================================================
1. **Command Center** — headline KPIs (revenue, bills, active members, points liability, redemption rate, today vs MTD).
2. **Sales** — revenue/bills/AOV by day/month/store/city/category; top SKUs.
3. **Customer Analytics** — new vs repeat, acquisition, gender/age/city mix, visit frequency.
4. **Loyalty** — points earned/redeemed/expired, balance liability, breakage, tier movement.
5. **Campaign Performance** — sends/delivered/opens/redemptions per campaign.
6. **Store Performance** — per-store revenue, members, enrolment, redemption.
7. **RFM & Churn** — RFM grid, churn-risk cohorts, top churning customers.
8. **Cohorts & Segments** — retention cohorts, segment sizes.
9. **Points Economics** — issuance vs redemption, cost of points, liability trend, expiry forecast.
10. **Campaign ROI** — spend vs incremental revenue.
11. **Executive Summary** — one-screen exec digest.
12. **NPS & Feedback** — NPS trend, promoter/detractor mix, verbatims.
13. **Live Bill Monitor** — real-time POS feed (see §6).
Every KPI/chart supports drill-down to the underlying bill/customer table. `days=0` sentinel = all-time (20-yr) scans; cache-warm heavy aggregations.

==================================================================
10) CUSTOMERS
==================================================================
- **Customer 360 / Customer Detail + drawer:** identity, tier, RFM, home/registered store, lifetime spend/visits/points, full bill history, points ledger, comms history, tickets, NPS.
- **Segment Builder:** AND/OR rule groups over RFM/tier/spend/recency/visit-count/city/store/category/birthday → saved audiences usable by campaigns; live audience preview + count + table + CSV.
- RFM segmentation, churn risk, cohort library.

==================================================================
11) MARKETING
==================================================================
- **Campaigns:** pick audience (segment or upload) → channel + template → schedule/send → track delivery/opens/redemptions + ROI.
- **Auto-Campaigns:** triggered journeys — welcome, birthday/anniversary, win-back/dormant, tier-upgrade, points-expiry reminder.
- **Coupons:** coupon engine (codes, validity windows, redemption rules, per-customer caps) integrated with POS coupon endpoints.

==================================================================
12) COMMUNICATIONS  (channel provider is configurable)
==================================================================
- Integrate **Karix** SMS / WhatsApp / RCS as the reference provider, **DLT-compliant** (entity ID, template ID, header/sender ID). Templates manager, **Bulk Send Jobs** (chunked, throttled, retried, resumable), full **Message Log**, **Provider Settings** (API key, sender/header, DLT IDs). The provider/credentials are user-supplied — collect and store in Provider Settings/.env, never hardcode. If City Metro uses a different SMS provider, ASK and adapt the same way as the POS (§B).

==================================================================
13) AI — FUNDLE BRAIN (analyst + L1 ops; train EXACTLY like ours)
==================================================================
- **System prompt:** "You are Fundle Brain, the AI analytics assistant AND operations agent for City Metro powered by Fundle." Direct READ access to live Mongo via tools; **ALWAYS call a tool before any numeric answer**; never fabricate ("Data not available" only after an all-time retry with `days=0`).
- **Live DATA-WAREHOUSE SNAPSHOT** injected as a 2nd system message every turn: existing collections + row counts, bill-date coverage, brand KPI digest, and the loyalty config — treat as ground truth.
- **READ tools (each does what its name says):** `get_overall_kpis, customer_search, customer_lookup, recent_bills_for_customer, points_ledger_for_customer, top_customers_report, top_skus, top_churning_customers, tier_distribution, rfm_segments, store_performance, city_performance, location_wise_customer_summary, campaign_leaderboard, coupon_performance, active_coupons_summary, communication_log_summary, nps_summary, tickets_summary, expiry_points_summary, pending_bills_summary, fraud_anomalies, support_desk_audit_log, list_redeemed_points, list_redeemed_coupons, list_deactivated_customers, list_unsubscribed, get_data_dictionary, run_aggregation, export_csv`.
- **`run_aggregation`** = arbitrary READ-ONLY Mongo pipelines (call `get_data_dictionary` first if unsure of fields) → answers ANY slice by city/store/month/tier/category. **`export_csv`** streams up to **1,000,000 rows** to a download link — present EXACTLY as `[Download <filename> (<row_count> rows)](<download_url>)`; never paste >20 rows inline; never refuse a raw-data/export request.
- **WRITE (L1) tools, role-gated to super_admin/brand_admin/support_agent + audit-logged:** `customer_deactivate, customer_reactivate, unsubscribe_customer, resubscribe_customer, reactivate_coupon_redemption, reactivate_redeem_points`. Protocol (non-negotiable): never write without explicit intent → ALWAYS look up the target with a READ tool first → require a REASON string → after success, confirm in plain English and cite where the audit entry lives → on permission-denied, tell the user, don't retry.
- **IST + currency:** group/format dates with `timezone:"Asia/Kolkata"`; ₹ for money, % for ratios; end with 1–2 recommended actions. Reason over CSVs pasted into chat. Floating Fundle-Brain FAB available across the admin.

==================================================================
14) AI — MASTER BRAIN  = Fundle Brain + ACTION layer (Master Admins only)
==================================================================
- System prompt = Fundle Brain's FULL prompt **+ a Master addendum**: "You are Master Brain … as smart as Fundle Brain on reads, PLUS the authority to execute — always **preview → confirm (with a reason) → execute → log**." It MUST still answer every read/analytics/list/export exactly like Fundle Brain (never downgrade or say "I can only do actions").
- **ACTION tools (two-turn execute pattern; write to `audit_logs` + a snapshot for Undo where applicable):** `grant_bonus_points, adjust_points, fix_negative_balances, retier_customers, set_customer_tier, apply_to_uploaded_report, send_campaign (Karix bulk SMS), list_campaigns, cancel_campaign, master_action_log, undo_action`, and **`fix_double_redemptions`** — finds customers double-deducted by the old redemption bug (duplicate `redeem` ledger rows whose `note` starts "Bill " that ALSO have a legit OTP/non-OTP redeem row for the SAME bill → credits the wrongly-deducted points back, corrects `lifetime_points_redeemed`, and voids the duplicate rows; conservative join so single-deduction bills are never touched; idempotent; preview→confirm+reason; intentionally NOT auto-undoable).
- **Execution UX:** every recommendation the agent can actually carry out renders a one-click **Execute** button; each applied action appears in the **Action Log** with an **Undo** (only where a snapshot exists). A per-user **Query Log** records every Master-Brain input; a **Query Admin** (`is_master_query_admin`) sees everyone's. All actions are audited (name + reason + timestamp + actor + before/after).

==================================================================
15) REPORTS
==================================================================
Downloads Center, Reports (Legacy), Shopper Bill Report, Store KPI Report, CRM Customer Report, KPI Trends, Reports & Exports, Exec Digests (scheduled email/PDF summaries), Formula Catalog (documents every KPI's exact formula). All respect R1 (bill_date) + R5 (loyalty filter). Large exports go through the streaming export pipeline.

==================================================================
16) OPERATIONS
==================================================================
Stores (master by **K-code**, tagged `pos_customer_key`+`pos_merchant_id` to align 1:1 with POS; bulk upload — Name+City required, upsert by code), Item Master (SKU catalog), API Monitor (§6), POS Credentials (issue/rotate `x-api-key`, merchant_id, customer_key per outlet/merchant).

==================================================================
17) SUPPORT
==================================================================
Tickets (+ detail/threads), NPS Inbox, and a **Support Desk** of OTP-gated L1 actions: Search Redeem-Points OTP, Search Redeem-Coupon OTP, Reactivate Coupon, Reactivate Redeem Points, Customer Deactivate/Reactivate, Update Mobile Number, Unsubscribe, Support Desk Audit log.

==================================================================
18) USER MANAGEMENT
==================================================================
Admin CRUD for users/roles, the master-admin & query-admin flags, activity/audit visibility, password reset.

==================================================================
19) PUBLIC SITE + CMS
==================================================================
Public microsite: Home, How It Works, Earn Points, Redeem Points, Rewards, Loyalty Benefits, Tiers, Referral Program, Store Locator, About Program, FAQs, Contact, Privacy, Terms — join-free CTA + welcome bonus. ALL copy/images editable at runtime via the **Public Site CMS** (admin).

==================================================================
20) ENV VARS
==================================================================
backend/.env: `MONGO_URL, DB_NAME, CORS_ORIGINS, JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRY_HOURS, EMERGENT_LLM_KEY, BRAND_NAME, SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD, BRAND_ADMIN_EMAIL, BRAND_ADMIN_PASSWORD` (+ POS keys via POS Credentials, + Karix/provider keys via Provider Settings). frontend/.env: `REACT_APP_BACKEND_URL`. No comments in .env; no hardcoded fallbacks.

==================================================================
21) NON-FUNCTIONAL
==================================================================
Production-grade: indexed queries, cache-warmed dashboards, streaming exports, event-loop-safe background jobs with watchdogs, full audit trails, RBAC on every mutation, IST everywhere, no Emergent branding, no mocked flows (everything real & wired).

==================================================================
22) BUILD / ADAPT ORDER (test each phase before moving on)
==================================================================
0. Import the GitHub repo, run it, confirm it boots. ASK which POS + get docs (§B). Confirm brand palette/logo. Strip Emergent branding (§C).
1. Brand config + design system + auth/roles + admin shell/sidebar.
2. Data model + Loyalty Rules editor + points ledger + canonical rules R1–R6.
3. POS integration (mapped to City Metro's POS) + Live Monitor + API Monitor + POS Credentials.
4. Historical/old-data Upload + Verify Load + Reconciliation (watchdog/cancel/deep-scan).
5. Customers (360, segments, RFM, cohorts) + Stores + Item Master.
6. 13 Dashboards + drill-downs + exports.
7. Communications (Karix/provider) + Campaigns + Auto-Campaigns + Coupons.
8. Fundle Brain (reads + L1 writes + run_aggregation + export_csv + data snapshot).
9. Master Brain (action layer + Execute buttons + Action Log/Undo + Query Log + fix_double_redemptions).
10. Reports suite + NPS + Tickets + Support Desk + Public site/CMS. Final pass: remove any remaining Emergent strings; full regression test.

==================================================================
23) ACCEPTANCE CHECKLIST (nothing may be missing)
==================================================================
[ ] Imported from our GitHub repo as the baseline. [ ] POS confirmed + adapted from docs (added/removed fields). [ ] All Emergent branding removed. [ ] All 13 dashboards + Live Monitor. [ ] Full POS API (lookup/enrol/OTP redeem-once/earn/returns/coupons/wallet) with R1–R6. [ ] Loyalty Rules editor (tiers from editor only). [ ] Historical/old-data ingest + opening balances + Verify Load + Reconciliation (watchdog/cancel). [ ] Customers 360 + Segment Builder + RFM/cohorts. [ ] Campaigns + Auto-Campaigns + Coupons. [ ] Communications (templates/bulk/log/provider settings, DLT). [ ] Fundle Brain (full read + L1 write tools + run_aggregation + export_csv). [ ] Master Brain (all action tools incl. fix_double_redemptions + Execute + Action Log/Undo + Query Log). [ ] Reports suite + Formula Catalog. [ ] Stores/Items/API Monitor/POS Credentials. [ ] Tickets + NPS + Support Desk. [ ] User Management (roles + master/query-admin flags). [ ] Public site + CMS. [ ] IST everywhere, audit on every mutation, production-grade, no mocks.

**Build production-grade, test every phase (use the testing agent for multi-endpoint/CRUD flows), confine all branding to the 3 rebrand points, and ASK me whenever the POS or provider documentation is needed.**
