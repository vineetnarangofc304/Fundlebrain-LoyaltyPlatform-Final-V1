# EMERGENT BUILD PROMPT — "FUNDLE — STAGING" (staging.fundlebrain.ai · QA + multi-POS API test harness)

You are building a **STAGING / testing instance** of our enterprise, single-tenant **Loyalty + CRM + Analytics + Campaign-Automation + Customer-Intelligence + Support + Reporting + POS-API-monitoring** platform. This is the SAME product we run in production — DO NOT reinvent it. Start from our public GitHub repo (below), run it, then apply the staging identity + the multi-POS test-harness changes in this prompt. Keep EVERY feature: all dashboards, the full POS integration, historical/old-data ingestion, reconciliation, communications, both AI copilots (Fundle Brain + Master Brain), reports, support desk, user management, and the public site. Build/verify in phases.

**Purpose of THIS instance:** a safe **staging environment for internal QA** AND a **sandbox for testing the APIs of different POS vendors** (eWards, Genesis, Vista, or any other) before we wire them into production. It is NOT a customer-facing brand — it stays generic "Fundle". Domain: **staging.fundlebrain.ai**.

==================================================================
A) SOURCE OF TRUTH — IMPORT FROM GITHUB FIRST (do this before anything else)
==================================================================
- The complete, working codebase is **PUBLIC on GitHub**. Pull it and use it as the baseline; only apply the staging identity + the POS test-harness items below. Do not omit modules.
- **Repo URL:**            `<<PASTE YOUR PUBLIC GITHUB REPO URL HERE>>`
- **Branch / tag:**        `<<e.g. main (latest)>>`
- **GitHub username:**     `<<YOUR GITHUB USERNAME>>`
- **Access (if needed):**  `<<leave blank if public; else connect GitHub / paste a read-only PAT>>`
- Steps: (1) Import the repo into this project (use Emergent's "Import from GitHub"/clone). (2) Install backend (`pip install -r backend/requirements.txt`, incl. `emergentintegrations`) + frontend (`yarn`). (3) Boot both via supervisor and confirm the app runs and seeds the super-admin. (4) THEN apply sections B–C and the identity block. If any file/feature in this prompt is missing from the repo, BUILD it to match this spec.

==================================================================
B) MULTI-POS VENDOR TEST HARNESS — the core reason this staging instance exists
==================================================================
Our reference build integrates a POS called **eWards**. On STAGING we must be able to **register, switch between, and exercise the APIs of MANY POS vendors** (eWards, Genesis, Vista, or any new vendor) side-by-side — without code changes per vendor. Build this as a first-class feature (extend the existing POS Credentials + API Monitor):

1. **POS Vendor Profiles (data-driven adapters):** a `pos_vendors` collection where each profile holds: `vendor_name`, `base_url`, `auth_scheme` (header name(s) + key/secret placement: header/query/body), and a **field-mapping table** (their field ↔ our canonical field, per operation) + **endpoint-name map** (their route name ↔ our internal handler). Adding a vendor = adding a profile, NOT editing code.
2. **Canonical operations stay identical** for every vendor — member lookup/enrol, OTP-once redemption, earn (bill), returns/cancellation, coupons, wallet (see §6). The adapter just translates names/fields/auth in and out.
3. **POS Playground / API Tester (new admin page):** pick a vendor profile + an operation, see a prefilled sample request (their schema), edit it, **Send**, and view the raw request, raw response, latency, status, our-side parsed result, and the field-mapping diff. Supports (a) hitting the **vendor's real sandbox** (paste their sandbox base_url + creds) and (b) a built-in **Mock POS** mode that simulates vendor responses so flows can be tested with no external dependency.
4. **Contract checks:** for each vendor + operation, validate that required canonical fields are satisfied by the mapping; flag missing/renamed/extra fields; capture optional domain fields a vendor may send (e.g. show/screen/seat, table/room, order-type) onto the transaction without breaking others.
5. **Everything is logged** in the **API Monitor** (request/response/latency/status/error + mapping diff), filterable by vendor. Produce a per-vendor **POS mapping doc** (their field ↔ our field, endpoint ↔ handler).
6. **NEVER hardcode a vendor's URL/keys/fields** — all via `pos_vendors` + POS Credentials. If a vendor's documentation is needed, ASK for it (endpoints, auth/header scheme, request & response JSON, OTP flow, redemption flow, returns/cancellation, coupons, wallet) — never guess a schema silently.
- Everything downstream of the POS (ledger, members, dashboards, AI, reports) is **POS-agnostic** and unchanged.

==================================================================
C) IDENTITY = GENERIC "FUNDLE (STAGING)" · REMOVE ALL "EMERGENT" / BUILDER BRANDING
==================================================================
- This instance is **not a customer brand** — keep the platform's own generic identity: **"Fundle"** engine, **"Fundle Brain"** + **"Master Brain"** copilots (names & training verbatim). No cinema/retail brand skin.
- **Add a persistent "STAGING" indicator** so testers never confuse it with production: a small non-intrusive `STAGING` ribbon/badge in the admin top bar + the `<title>` prefixed with `[STAGING]`, driven by an env flag (e.g. `APP_ENV=staging`). Keep it subtle, not disruptive.
- **Strip every trace of the builder:** any "Made with Emergent" / "Powered by Emergent" badge or floating button, `index.html` title/meta/OG tags, favicon, console banners, footer mentions, and any "emergent" string in copy or assets. Surface ONLY **Fundle** (+ optional "Powered by Fundle"). (The Emergent LLM key is still used internally for AI — that's fine; just no visible Emergent branding.)

==================================================================
1) STAGING IDENTITY (minimal — this is an internal test instance)
==================================================================
- **Name:** Fundle (Staging) · **Domain:** staging.fundlebrain.ai · **Loyalty programme:** keep the base product's generic naming (e.g. "Fundle Rewards").
- **Engine stays "Fundle"; AI copilots stay "Fundle Brain" + "Master Brain"** (keep names & training verbatim).
- **Palette:** keep the base product's design system as-is (do NOT invent a new brand skin). Only add the neutral `STAGING` badge from §C. If the repo uses `--brand-*`/`--kazo-*` CSS variables, leave the variable NAMES + class names intact.
- **Rebrand/identity is confined to:** `frontend/src/brand.config.js` (set generic "Fundle" strings + staging domain + SEO), `frontend/public/index.html` (`[STAGING]` title/meta), and `BRAND_NAME` + admin emails + `APP_ENV=staging` in `backend/.env`. Do NOT restyle the app.
- **Domain / category framing stays GENERIC retail** (no cinema mapping): Stores stay **Stores**, SKUs stay generic Item Master, categories are the base product's generic categories, tiers come from the Loyalty Rules editor (no hardcoded ladder). Everything else (engine, dashboards, AI, POS rules, reports) is EXACTLY the base product.
- **Test-data friendly:** provide an easy way to **seed sample members/bills/SKUs/stores** and (super-admin only, staging-gated) **reset/clear test data** so QA can start clean. This reset MUST be disabled unless `APP_ENV=staging`.

==================================================================
2) TECH STACK & NON-NEGOTIABLE ARCHITECTURE
==================================================================
- **Backend:** FastAPI + **Motor (async MongoDB)** + APScheduler + custom JWT (PyJWT + bcrypt). Python 3.11.
- **Frontend:** React (CRA) + React Router + Tailwind + **shadcn/ui** + lucide-react + Recharts + sonner. NO emoji icons.
- **AI:** **Emergent Universal LLM key** via `emergentintegrations` (GPT-4o/Claude text, OpenAI TTS, Gemini Nano-Banana images). Do NOT install vendor SDKs directly.
- **Hard routing rules:** all backend routes prefixed **`/api`**; backend binds `0.0.0.0:8001`; frontend calls **only** `process.env.REACT_APP_BACKEND_URL`; Mongo via **`MONGO_URL`**+`DB_NAME`. No hardcoded URLs/ports/secrets (omit fallbacks).
- **Mongo discipline:** never return raw `_id` (PyObjectId/BaseDocument + to_mongo/from_mongo); `datetime.now(timezone.utc)`; stored dates are ISO strings; index hot fields.
- **Heavy/background jobs (CRITICAL):** CPU parse via `asyncio.to_thread`; heartbeat + **stale-recovery watchdog** (auto-fail if no heartbeat > 8 min); `await asyncio.sleep(0)` between DB batches; **chunked uploads** (1.5 MB, streamed to disk, retained for healing); **Cancel** control on long jobs.
- **Modular layout:** same backend `/routes/*` + frontend `src/pages/{admin,auth,public,store}` structure as the repo.

==================================================================
3) DATA MODEL (core collections — keep field names stable)
==================================================================
- **users:** email, password_hash, name, role, is_active, is_master_admin, is_master_query_admin, created_at.
- **customers (members):** mobile, mobile_key, name, email, city, state, gender, language, birthday, anniversary, card_validity, tier, points_balance, lifetime_points_earned, lifetime_points_redeemed, lifetime_spend, visit_count, first_visit_at, last_visit_at, days_since_last_visit, home_store_id, registered_store_id, first_purchase_store_id, source, is_lost_customer, raw_mobile, is_active, unsubscribed.
- **transactions:** bill_number, transaction_id, customer_mobile, customer_id, store_id, store_code, bill_date (ISO/IST), amount (pre-tax base), taxes[{name:GST, amount}], net_amount, total_revenue, points_earned, points_redeemed, redemption_value, is_return, original_bill_number, source (pos/historic), is_lost_customer, line_items[{sku, name, qty, amount, category}], + any optional vendor-specific fields captured via the POS adapter.
- **points_ledger:** type (earn|redeem|adjust|expire), points (+/-), reference_type, reference_id, note, customer_id, customer_mobile, created_at, expires_at, voided, original_points, voided_by/at/reason. **Source of truth for balances.**
- **pos_vendors (NEW — see §B):** vendor_name, base_url, auth_scheme, endpoint_map, field_map, is_active, sandbox flag.
- **loyalty_config / stores / items / pos_credentials / otps / campaigns / auto_campaigns / coupons / segments / master_campaigns / communications(message_log) / comm_templates / bulk_jobs / provider_settings / audit_logs / support_desk audit / ai_chats / mb_action_snapshots / mb_query_log / historic_ingest_jobs / historic_skipped_rows / historic_uploads / historic_chunks / recon_jobs(heartbeat,phase,deep_scan,cancel_requested) / recon_mismatches / api_monitor / cms_content / nps / tickets** — as in the repo.

==================================================================
4) AUTH & ROLES (RBAC)
==================================================================
Custom JWT (bcrypt). Seed super_admin + brand_admin from `.env`. Roles: `super_admin, brand_admin, crm_manager, support_agent, store_user, analyst/viewer`. Flags: `is_master_admin` (Master Brain actions), `is_master_query_admin` (global query-log oversight). Login routes `/crm/login`, `/store/login`. Every mutation audit-logged. Save creds to `/app/memory/test_credentials.md`.

==================================================================
5) CANONICAL LOYALTY DATA RULES — ENFORCE STRICTLY (R1–R6)
==================================================================
- **R1 — bill_date is the source of truth** for time-based analytics (not created_at).
- **R2 — store resolution by code:** registered store (from POS account) authoritative regardless of load order; bill-derived store → first_purchase_store_id.
- **R3 — aggregates** (visit_count, lifetime_spend, points) recomputed from ledger + bills.
- **R4 — points expiry:** opening-balance/historical points valid till a configurable cutoff; live points expire 1 year from bill date (per-tier override). All IST.
- **R5 — loyalty analytics exclude anonymous walk-ins** (`customer_mobile` not-null).
- **R6 — Valid-Indian-mobile gate → "Lost Customers":** loyalty only for valid Indian mobile (10 digits, 6–9). Invalid/missing → non-loyalty Lost Customer (recorded for analytics, `is_lost_customer=true`, `customer_mobile=null`, keep `raw_mobile`, no points/account/SMS, 200); posAddCustomer rejects invalid (400).
- **Mobile canonicalisation** on last-10-digits (`_mobile_key`) everywhere; OTP lookups `{otp, purpose, $or:[mobile_key, mobile]}`; one `_find_customer_by_mobile()` for all POS reads.
- **IST timezone:** never string-slice ISO dates; use `$dateToString`/`$dateTrunc` `timezone:"Asia/Kolkata"`.

==================================================================
6) POS INTEGRATION — canonical functionality (served through the §B multi-vendor adapter)
==================================================================
Canonical capabilities (eWards endpoint names for reference; each vendor profile maps its own names/fields onto these). Auth via per-merchant credentials ↔ `pos_credentials`/`pos_vendors`; canonical payload `merchant_id`+`customer_key`:
- **Member lookup & enrolment:** posCustomerCheck, posCustomerCheckRequest, resendOtPcustomercheck, posCustomerOTPCheck, posAddCustomer.
- **Redemption (OTP):** posRedeemPointRequest, resendOtPosRedeemPointRequest, posRedeemPointOtpCheck. **Redemption applied EXACTLY ONCE** in the redeem flow; the sale bill (posAddPoint) RECORDS redeemed points for reporting but **NEVER deducts again** (no 2nd `redeem` ledger row from the bill — this was a real P0 double-deduction bug; prevent it).
- **Earning (the bill):** posAddPoint — earn from `amount` (pre-tax base; bill-with-tax = amount + taxes.amount(GST)) × tier/category/store multipliers; honours min_bill_for_earn, block_earn_on_returns, pauses, welcome/upgrade bonuses; writes transaction + earn ledger + updates aggregates; enforces R6 + duplicate-bill guard.
- **Coupons:** posCouponDetails, posRedeemCoupon (validity, caps, single-use).
- **Returns / cancellation:** returnOrder — keyed by **mobile** (original bill optional); reverses points via `return_loyalty_gross_amount`, decrements spend/points, writes return txn (`is_return`, `bill_number=RET-…`) + ledger adjust.
- **Wallet:** requestWalletRedemptionURL, getWalletRedemptionStatus.
- **Live Bill Monitor:** real-time feed, KPI cards incl. **Lost Cust.** + **Lost Purchase**, distinct lost/return styling, "Recalc points" (today-IST, **pos-only**).
- **API Monitor:** every POS call logged with request/response/latency/status/error + mapping diff, filterable by vendor (§B).

==================================================================
7) LOYALTY ENGINE (Loyalty Rules editor — fully config-driven)
==================================================================
Config: `earn_mode` (points_per_spend), `earn_ratio`, `burn_ratio`, `min_redeem_points`, `point_expiry_days` (+per-tier override), `welcome_bonus`, `min_bill_for_earn`, `block_earn_on_returns`, `require_otp_for_redeem`, `earn_enabled`, `burn_enabled`, `earn_burn_pauses[]`, `category_multipliers`, `store_type_multipliers`, `tier_reset_cadence`, `tier_reset_anchor_date`, `tier_rules[]` (min/max_lifetime_spend, earn_multiplier, welcome/birthday/anniversary/upgrade bonuses, colour, expiry override). **Tiers come ONLY from this editor — no hardcoded ladder.** Full editor UI.

==================================================================
8) DATA LAYER — OLD/HISTORICAL DATA + INTEGRITY (must be complete)
==================================================================
- **Historical Upload (old data):** chunked CSV ingest for **Members / Bills / SKU / Stores** as background jobs with progress, skipped-row capture, dedupe, **chunk retention** for healing. Extract store code from the registered account; post-pass links code→store (auto-creating stubs) and sets registered/home store. **Auto-backfill** stub members from txn mobiles + recompute R1/R2/R3. Opening balances → ledger, valid till the configurable cutoff (R4).
- **Verify Load:** counts, bill-date coverage, distinct SKUs/members/stores, samples.
- **Data Reconciliation:** upload a source CSV per dataset and compare to DB → matched / missing-in-DB / amount mismatch / mobile mismatch / extra-in-DB, with per-mismatch CSV download. MUST: instant file listing; **Check & Heal** with an **editable go-live cutoff date**; parse OFF the event loop; **stream chunks to disk (never hold the whole file in memory)**; heartbeat + **stale-job watchdog** (auto-fail > 8 min); per-job **Cancel**; optional **"Deep DB-side scan"** (off by default). Handle ~800k+ row / 250MB+ files without stalling.

==================================================================
9) DASHBOARDS (13 + Live Monitor — Recharts, IST, drill-downs, date-range, CSV export)
==================================================================
1. **Command Center** — revenue, bills, active members, points liability, redemption rate, today vs MTD.
2. **Sales** — revenue/bills/AOV by day/month/store/city/category; top SKUs.
3. **Customer Analytics** — new vs repeat, acquisition, demographics, visit frequency.
4. **Loyalty** — points earned/redeemed/expired, liability, breakage, tier movement.
5. **Campaign Performance** — sends/delivered/opens/redemptions per campaign.
6. **Store Performance** — per-store revenue, members, enrolment, redemption.
7. **RFM & Churn** — RFM grid, churn cohorts, top churning members.
8. **Cohorts & Segments** — retention cohorts, segment sizes.
9. **Points Economics** — issuance vs redemption, cost of points, liability trend, expiry forecast.
10. **Campaign ROI** — spend vs incremental revenue.
11. **Executive Summary** — one-screen exec digest.
12. **NPS & Feedback** — NPS trend, promoter/detractor mix, verbatims.
13. **Live Bill Monitor** — real-time POS feed (§6).
Every KPI/chart drills down to the underlying bill/member table. `days=0` = all-time; cache-warm heavy aggregations.

==================================================================
10) CUSTOMERS (Members)
==================================================================
- **Member 360 / detail + drawer:** identity, tier, RFM, home/registered store, lifetime spend/visits/points, full bill history, points ledger, comms history, tickets, NPS.
- **Segment Builder:** AND/OR groups over RFM/tier/spend/recency/visit-count/city/store/category/birthday → saved audiences; live preview + count + table + CSV.
- RFM, churn risk, cohorts.

==================================================================
11) MARKETING
==================================================================
- **Campaigns:** audience (segment/upload) → channel + template → schedule/send → delivery/opens/redemptions + ROI.
- **Auto-Campaigns:** welcome, birthday/anniversary, win-back/dormant, tier-upgrade, points-expiry reminder.
- **Coupons:** codes, validity, caps, single-use — wired to POS coupon endpoints.

==================================================================
12) COMMUNICATIONS (channel provider configurable)
==================================================================
Integrate **Karix** SMS / WhatsApp / RCS as reference (DLT: entity/template/header IDs). Templates, **Bulk Send Jobs** (chunked/throttled/retried/resumable), **Message Log**, **Provider Settings** (API key, sender/header, DLT IDs). Provider/credentials user-supplied — collect & store, never hardcode. On staging, prefer a **safe test/sandbox mode** for the provider so QA sends don't blast real recipients (gate live sends behind an explicit toggle). If a different provider is used, ASK and adapt like the POS (§B).

==================================================================
13) AI — FUNDLE BRAIN (analyst + L1 ops; train EXACTLY like ours)
==================================================================
- **System prompt:** "You are Fundle Brain, the AI analytics assistant AND operations agent for Fundle (staging) powered by Fundle." READ access to live Mongo via tools; **ALWAYS call a tool before any numeric answer**; never fabricate ("Data not available" only after an all-time retry with `days=0`).
- **Live DATA-WAREHOUSE SNAPSHOT** injected as a 2nd system message every turn (collections + counts, bill-date coverage, KPI digest, loyalty config) = ground truth.
- **READ tools:** `get_overall_kpis, customer_search, customer_lookup, recent_bills_for_customer, points_ledger_for_customer, top_customers_report, top_skus, top_churning_customers, tier_distribution, rfm_segments, store_performance, city_performance, location_wise_customer_summary, campaign_leaderboard, coupon_performance, active_coupons_summary, communication_log_summary, nps_summary, tickets_summary, expiry_points_summary, pending_bills_summary, fraud_anomalies, support_desk_audit_log, list_redeemed_points, list_redeemed_coupons, list_deactivated_customers, list_unsubscribed, get_data_dictionary, run_aggregation, export_csv`.
- **`run_aggregation`** = read-only Mongo pipelines (call `get_data_dictionary` first if unsure of fields). **`export_csv`** streams up to **1,000,000 rows** → present EXACTLY `[Download <filename> (<row_count> rows)](<download_url>)`; never paste >20 rows inline; never refuse a raw-data/export request.
- **WRITE (L1) tools, role-gated + audited:** `customer_deactivate, customer_reactivate, unsubscribe_customer, resubscribe_customer, reactivate_coupon_redemption, reactivate_redeem_points`. Protocol: explicit intent → look up target first → require REASON → confirm + cite audit entry → on permission-denied, tell user, don't retry.
- **PERFORMANCE (learned on prod):** heavy analytics tools MUST run under a generous DB-deadline override (`pymongo.timeout(...)`) so they don't die on the client's aggressive `timeoutMS`; cache platform-wide KPI/tier snapshots. **IST + currency:** group/format dates with `timezone:"Asia/Kolkata"`; ₹ money, % ratios; end with 1–2 actions; floating Fundle-Brain FAB across admin.

==================================================================
14) AI — MASTER BRAIN = Fundle Brain + ACTION layer (Master Admins only)
==================================================================
- System prompt = Fundle Brain's FULL prompt **+ Master addendum**: "always **preview → confirm (with a reason) → execute → log**"; still answers every read/analytics/export exactly like Fundle Brain (never downgrade).
- **ALWAYS expose the full tool set** (reads + actions) with the write-capable prompt — do NOT gate tool exposure on brittle keyword routing (natural commands like "change customer X to gold tier" and bare confirmations like "yes / go ahead" must work); safety comes from the mandatory preview→confirm(+reason) protocol, not from hiding tools. Every tool call runs under a per-call DB-deadline override.
- **ACTION tools (two-turn; write `audit_logs` + Undo snapshots where applicable):** `grant_bonus_points, adjust_points, fix_negative_balances, retier_customers, set_customer_tier, apply_to_uploaded_report, send_campaign (Karix bulk), list_campaigns, cancel_campaign, master_action_log, undo_action`, and **`fix_double_redemptions`** — finds members double-deducted by the old redemption bug (duplicate `redeem` ledger rows whose `note` starts "Bill " that ALSO have a legit OTP/non-OTP redeem row for the SAME bill → credits points back, corrects `lifetime_points_redeemed`, voids the duplicate rows; conservative join; idempotent; preview→confirm+reason; not auto-undoable).
- **Execution UX:** every executable recommendation renders a one-click **Execute** button; applied actions appear in the **Action Log** with **Undo** (only where a snapshot exists). Per-user **Query Log**; **Query Admin** sees everyone's. All actions audited (name + reason + timestamp + actor + before/after).

==================================================================
15) REPORTS
==================================================================
Downloads Center, Reports (Legacy), Bill Report, Store KPI Report, Member Report, KPI Trends, Reports & Exports, Exec Digests (scheduled email/PDF), Formula Catalog (every KPI's formula). Respect R1 (bill_date) + R5 (loyalty filter). Large exports via the streaming pipeline.

==================================================================
16) OPERATIONS
==================================================================
Stores (master by code, tagged `pos_customer_key`+`pos_merchant_id`, bulk upload), Item Master (SKUs/combos), API Monitor (§6, per-vendor filter), **POS Credentials + POS Vendor Profiles + POS Playground/API Tester** (§B — issue/rotate keys, register vendors, run test calls).

==================================================================
17) SUPPORT
==================================================================
Tickets (+detail/threads), NPS Inbox, **Support Desk** (OTP-gated L1): Search Redeem-Points OTP, Search Redeem-Coupon OTP, Reactivate Coupon, Reactivate Redeem Points, Member Deactivate/Reactivate, Update Mobile, Unsubscribe, Support Desk Audit.

==================================================================
18) USER MANAGEMENT
==================================================================
Admin CRUD for users/roles, master-admin & query-admin flags, audit visibility, password reset.

==================================================================
19) PUBLIC SITE + CMS
==================================================================
Keep the base public site (Home, How It Works, Earn/Redeem, Rewards, Tiers, Referral, Store Locator, About, FAQs, Contact, Privacy, Terms) editable at runtime via the **Public Site CMS**, with generic "Fundle" copy. (On staging this is mainly for QA of the CMS + public flows.)

==================================================================
20) ENV VARS
==================================================================
backend/.env: `MONGO_URL, DB_NAME, CORS_ORIGINS, JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRY_HOURS, EMERGENT_LLM_KEY, BRAND_NAME, APP_ENV=staging, SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD, BRAND_ADMIN_EMAIL, BRAND_ADMIN_PASSWORD` (+ POS keys via POS Credentials/Vendor Profiles, + provider keys via Provider Settings). frontend/.env: `REACT_APP_BACKEND_URL`. No comments in .env; no hardcoded fallbacks. Point DNS/app at **staging.fundlebrain.ai**.

==================================================================
21) NON-FUNCTIONAL
==================================================================
Production-grade even though it's staging: indexed queries, cache-warmed dashboards, streaming exports, event-loop-safe background jobs with watchdogs + disk-streamed chunked uploads, DB-deadline overrides on heavy AI/analytics queries, full audit trails, RBAC on every mutation, IST everywhere, no Emergent branding, no mocked flows (except the deliberate **Mock POS** and **safe SMS test mode** for staging). Clear STAGING badge + a staging-gated test-data reset.

==================================================================
22) BUILD / ADAPT ORDER (test each phase before moving on)
==================================================================
0. Import the GitHub repo, run it, confirm it boots + seeds super-admin. Set `APP_ENV=staging`, generic Fundle identity, staging domain. Strip Emergent branding (§C).
1. Identity/staging badge + auth/roles + admin shell/sidebar + test-data seed & (staging-gated) reset.
2. Data model + Loyalty Rules editor + points ledger + canonical rules R1–R6.
3. **Multi-POS Vendor Test Harness (§B): pos_vendors profiles + adapter + POS Playground/API Tester + Mock POS + API Monitor per-vendor.** Then the canonical POS operations + Live Monitor + POS Credentials.
4. Historical/old-data Upload + Verify Load + Reconciliation (disk-streamed, watchdog/cancel/deep-scan).
5. Members (360, segments, RFM, cohorts) + Stores + Item Master.
6. 13 Dashboards + drill-downs + exports.
7. Communications (Karix/provider, safe test mode) + Campaigns + Auto-Campaigns + Coupons.
8. Fundle Brain (reads + L1 writes + run_aggregation + export_csv + data snapshot + DB-deadline overrides).
9. Master Brain (full tool set always exposed + Execute buttons + Action Log/Undo + Query Log + fix_double_redemptions).
10. Reports suite + NPS + Tickets + Support Desk + Public site/CMS. Final pass: remove any remaining Emergent strings; full regression test.

==================================================================
23) ACCEPTANCE CHECKLIST (nothing may be missing)
==================================================================
[ ] Imported from our GitHub repo as the baseline. [ ] `APP_ENV=staging`, generic Fundle identity, STAGING badge, staging.fundlebrain.ai. [ ] All Emergent branding removed. [ ] **Multi-POS Vendor Test Harness: register/switch vendors, POS Playground/API Tester, Mock POS, per-vendor API Monitor + mapping doc.** [ ] Full canonical POS API (lookup/enrol/OTP redeem-once/earn/returns/coupons/wallet) with R1–R6 through the adapter. [ ] All 13 dashboards + Live Monitor. [ ] Loyalty Rules editor (tiers from editor only). [ ] Historical/old-data ingest + opening balances + Verify Load + Reconciliation (disk-streamed, watchdog/cancel). [ ] Members 360 + Segment Builder + RFM/cohorts. [ ] Campaigns + Auto-Campaigns + Coupons. [ ] Communications (templates/bulk/log/provider settings, DLT, safe test mode). [ ] Fundle Brain (full read + L1 write tools + run_aggregation + export_csv + DB-deadline overrides). [ ] Master Brain (all action tools incl. fix_double_redemptions + full tool set always exposed + Execute + Action Log/Undo + Query Log). [ ] Reports suite + Formula Catalog. [ ] Stores/Items/API Monitor/POS Credentials + Vendor Profiles + Playground. [ ] Tickets + NPS + Support Desk. [ ] User Management (roles + master/query-admin flags). [ ] Public site + CMS. [ ] Test-data seed + staging-gated reset. [ ] IST everywhere, audit on every mutation, production-grade, no mocks (except Mock POS + safe SMS test mode).

**Build production-grade, test every phase (use the testing agent for multi-endpoint/CRUD flows), keep the identity generic "Fundle (Staging)" with a clear STAGING badge, and make the multi-POS vendor test harness (§B) a first-class, data-driven feature so we can plug in and exercise ANY POS vendor's API without code changes. ASK me whenever a POS or provider's documentation is needed.**
