# EMERGENT BUILD PROMPT — "DOODLES CINEMA"  (Loyalty + CRM + Analytics + AI platform — full clone)

You are building an enterprise, single-tenant **Loyalty + CRM + Analytics + Campaign-Automation + Customer-Intelligence + Support + Reporting + POS-API-monitoring** platform for the cinema brand **DOODLES CINEMA**. This product already exists and is fully built — DO NOT reinvent it. Start from our public GitHub repo (below), run it, then apply the Doodles Cinema brand + the brand's POS + the changes in this prompt. Keep EVERY feature: all dashboards, the full POS integration, historical/old-data ingestion, reconciliation, communications, both AI copilots (Fundle Brain + Master Brain), reports, support desk, user management, and the public site. Build/verify in phases.

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
- Our reference build integrates a POS called **eWards**. Doodles Cinema may use a **different POS / box-office + concession system** (e.g. **Genesis**, Vista, or another vendor).
- **FIRST, ASK ME:** "Which POS / ticketing+concession system does Doodles Cinema use — eWards, Genesis, or another (name it)? Do you have its API documentation (endpoints, auth/header scheme, request & response JSON, OTP flow, redemption flow, returns/cancellation, coupons, wallet)? Paste it or share a link."
- Then **MAP our canonical loyalty functionality onto that POS's actual API**:
  - KEEP 100% of the business logic identical (earn/redeem/tiers/lost-customer gate/mobile-canonicalisation/OTP-once redemption/returns/coupons/wallet — see §5, §6, §7).
  - **ADD** any endpoints, headers, or request/response fields the new POS documentation requires (e.g. a cinema POS may send show/screen/seat/movie fields — capture them on the transaction).
  - **REMOVE/RENAME** any eWards-specific endpoints or fields the new POS does not have.
  - Expose the new POS's endpoint names but route them to the same internal handlers.
  - Produce a short **POS mapping doc** (their field ↔ our field) and log every POS call in the API Monitor.
- If no documentation is provided, ASK before assuming a schema — never guess silently.
- Everything downstream of the POS (ledger, members, dashboards, AI, reports) is **POS-agnostic** and unchanged.

==================================================================
C) REMOVE ALL "EMERGENT" / BUILDER BRANDING EVERYWHERE
==================================================================
- Strip every trace of the builder: any "Made with Emergent" / "Powered by Emergent" badge or floating button, `index.html` title/meta/OG tags, favicon, console banners, footer mentions, and any "emergent" string in copy or assets. The app must surface ONLY **Doodles Cinema** + **"Powered by Fundle"**. (The Emergent LLM key is still used internally for AI — that's fine; just no visible Emergent branding.)

==================================================================
1) BRAND IDENTITY  (the only customer-facing things that change)
==================================================================
- **Brand:** Doodles Cinema — "a premium multiplex cinema chain" (movie tickets + F&B/concessions + merchandise + gaming).
- **Public domain:** doodlescinema.com · **Loyalty programme:** "Doodles Club" · **Welcome bonus:** 100 pts ("₹100 snack credit on joining").
- **Platform engine stays "Fundle"; AI copilots stay "Fundle Brain" + "Master Brain"** (keep their names & training verbatim).
- **Palette:** cinematic-editorial — warm ink/charcoal base, ONE bold accent (marquee-red `#E11D2A` or screen-gold `#D4A23B`) + a subtle film-grain texture. LIGHT editorial theme (cinema warmth via accent + grain, NOT a dark dump, NOT purple-on-white AI-slop). Custom display serif + clean grotesque body, generous whitespace, micro-animations.
- **Rebrand is confined to 3 places ONLY:** `frontend/src/brand.config.js` (all display strings, logos, social, SEO, public copy), the `--brand-*` (or `--kazo-*`) CSS variables in `frontend/src/index.css` (swap hex values, keep variable NAMES + class names), and `BRAND_NAME` + admin emails in `backend/.env`. Also update `frontend/public/index.html` static title/meta. **Confirm palette + logo with me before Phase 1.**

### CINEMA DOMAIN MAPPING (functionality identical — only labels/framing differ)
- **Stores → "Properties"** = cinema locations (with screens/audis); identity by **property K-code**, tagged `pos_customer_key`+`pos_merchant_id`.
- **Bills/Transactions** = box-office ticket bookings + concession (F&B) bills + merchandise; one visit may produce a ticket bill and an F&B bill. Capture show/screen/seat/movie if the POS sends them.
- **Item Master / SKUs** = concession items, combos, ticket classes (Recliner/Premium/Regular), movies/shows.
- **Category multipliers:** `Tickets`, `F&B`, `Merchandise`, `Gaming` (Tickets vs F&B can carry different earn multipliers).
- **Tiers** (spend-driven & fully editable): Silver → Gold → Platinum → **Director's Circle**.
- Everything else (engine, dashboards, AI, POS rules, reports) is EXACTLY the base product.

==================================================================
2) TECH STACK & NON-NEGOTIABLE ARCHITECTURE
==================================================================
- **Backend:** FastAPI + **Motor (async MongoDB)** + APScheduler + custom JWT (PyJWT + bcrypt). Python 3.11.
- **Frontend:** React (CRA) + React Router + Tailwind + **shadcn/ui** + lucide-react + Recharts + sonner. NO emoji icons.
- **AI:** **Emergent Universal LLM key** via `emergentintegrations` (GPT-4o/Claude text, OpenAI TTS, Gemini Nano-Banana images). Do NOT install vendor SDKs directly.
- **Hard routing rules:** all backend routes prefixed **`/api`**; backend binds `0.0.0.0:8001`; frontend calls **only** `process.env.REACT_APP_BACKEND_URL`; Mongo via **`MONGO_URL`**+`DB_NAME`. No hardcoded URLs/ports/secrets (omit fallbacks).
- **Mongo discipline:** never return raw `_id` (PyObjectId/BaseDocument + to_mongo/from_mongo); `datetime.now(timezone.utc)`; stored dates are ISO strings; index hot fields.
- **Heavy/background jobs (CRITICAL):** CPU parse via `asyncio.to_thread`; heartbeat + **stale-recovery watchdog** (auto-fail if no heartbeat > 8 min); `await asyncio.sleep(0)` between DB batches; **chunked uploads** (1.5 MB, retained for healing); **Cancel** control on long jobs.
- **Modular layout:** same backend `/routes/*` + frontend `src/pages/{admin,auth,public,store}` structure as the repo.

==================================================================
3) DATA MODEL (core collections — keep field names stable)
==================================================================
- **users:** email, password_hash, name, role, is_active, is_master_admin, is_master_query_admin, created_at.
- **customers (members):** mobile, mobile_key, name, email, city, state, gender, language, birthday, anniversary, card_validity, tier, points_balance, lifetime_points_earned, lifetime_points_redeemed, lifetime_spend, visit_count, first_visit_at, last_visit_at, days_since_last_visit, home_store_id (property), registered_store_id, first_purchase_store_id, source, is_lost_customer, raw_mobile, is_active, unsubscribed.
- **transactions:** bill_number, transaction_id, customer_mobile, customer_id, store_id (property), store_code, bill_date (ISO/IST), amount (pre-tax base), taxes[{name:GST, amount}], net_amount, total_revenue, points_earned, points_redeemed, redemption_value, is_return, original_bill_number, source (pos/historic), is_lost_customer, line_items[{sku, name, qty, amount, category}], + optional movie/show/screen/seat fields if POS provides.
- **points_ledger:** type (earn|redeem|adjust|expire), points (+/-), reference_type, reference_id, note, customer_id, customer_mobile, created_at, expires_at, voided, original_points, voided_by/at/reason. **Source of truth for balances.**
- **loyalty_config / stores(properties) / items / pos_credentials / otps / campaigns / auto_campaigns / coupons / segments / master_campaigns / communications(message_log) / comm_templates / bulk_jobs / provider_settings / audit_logs / support_desk audit / ai_chats / mb_action_snapshots / mb_query_log / historic_ingest_jobs / historic_skipped_rows / historic_uploads / historic_chunks / recon_jobs(heartbeat,phase,deep_scan,cancel_requested) / recon_mismatches / api_monitor / cms_content / nps / tickets** — as in the repo.

==================================================================
4) AUTH & ROLES (RBAC)
==================================================================
Custom JWT (bcrypt). Seed super_admin + brand_admin from `.env`. Roles: `super_admin, brand_admin, crm_manager, support_agent, store_user (property staff), analyst/viewer`. Flags: `is_master_admin` (Master Brain actions), `is_master_query_admin` (global query-log oversight). Login routes `/crm/login`, `/store/login`. Every mutation audit-logged. Save creds to `/app/memory/test_credentials.md`.

==================================================================
5) CANONICAL LOYALTY DATA RULES — ENFORCE STRICTLY (R1–R6)
==================================================================
- **R1 — bill_date is the source of truth** for time-based analytics (not created_at).
- **R2 — property resolution by K-code:** registered property (from POS account) authoritative regardless of load order; bill-derived property → first_purchase_store_id.
- **R3 — aggregates** (visit_count, lifetime_spend, points) recomputed from ledger + bills.
- **R4 — points expiry:** opening-balance/historical points valid till a configurable cutoff; live points expire 1 year from bill date (per-tier override). All IST.
- **R5 — loyalty analytics exclude anonymous walk-ins** (`customer_mobile` not-null).
- **R6 — Valid-Indian-mobile gate → "Lost Customers":** loyalty only for valid Indian mobile (10 digits, 6–9). Invalid/missing → non-loyalty Lost Customer (recorded for analytics, `is_lost_customer=true`, `customer_mobile=null`, keep `raw_mobile`, no points/account/SMS, 200); posAddCustomer rejects invalid (400).
- **Mobile canonicalisation** on last-10-digits (`_mobile_key`) everywhere; OTP lookups `{otp, purpose, $or:[mobile_key, mobile]}`; one `_find_customer_by_mobile()` for all POS reads.
- **IST timezone:** never string-slice ISO dates; use `$dateToString`/`$dateTrunc` `timezone:"Asia/Kolkata"`.

==================================================================
6) POS INTEGRATION — canonical functionality (map onto Doodles' POS from §B)
==================================================================
Capabilities (eWards endpoint names for reference; rename/add/remove per the chosen POS docs). Auth via per-merchant `x-api-key` ↔ `pos_credentials`; payload `merchant_id`+`customer_key`:
- **Member lookup & enrolment:** posCustomerCheck, posCustomerCheckRequest, resendOtPcustomercheck, posCustomerOTPCheck, posAddCustomer.
- **Redemption (OTP):** posRedeemPointRequest, resendOtPosRedeemPointRequest, posRedeemPointOtpCheck. **Redemption applied EXACTLY ONCE** in the redeem flow; the sale bill (posAddPoint) RECORDS redeemed points for reporting but **NEVER deducts again** (no 2nd `redeem` ledger row from the bill — this was a real P0 double-deduction bug; prevent it).
- **Earning (the bill):** posAddPoint — earn from `amount` (pre-tax base; bill-with-tax = amount + taxes.amount(GST)) × tier/category/property multipliers; honours min_bill_for_earn, block_earn_on_returns, pauses, welcome/upgrade bonuses; writes transaction + earn ledger + updates aggregates; enforces R6 + duplicate-bill guard. Tickets vs F&B use their category multipliers.
- **Coupons:** posCouponDetails, posRedeemCoupon (combo/upgrade/free-ticket; validity, caps, single-use).
- **Returns / cancellation:** returnOrder — keyed by **mobile** (original booking optional); reverses points via `return_loyalty_gross_amount`, decrements spend/points, writes return txn (`is_return`, `bill_number=RET-…`) + ledger adjust.
- **Wallet:** requestWalletRedemptionURL, getWalletRedemptionStatus.
- **Live Bill Monitor:** real-time ticket+F&B feed, KPI cards incl. **Lost Cust.**+**Lost Purchase**, distinct lost/return styling, "Recalc points" (today-IST, **pos-only**).
- **API Monitor:** every POS call logged with request/response/latency/status/error + diff.

==================================================================
7) LOYALTY ENGINE (Loyalty Rules editor — fully config-driven)
==================================================================
Config: `earn_mode` (points_per_spend), `earn_ratio`, `burn_ratio`, `min_redeem_points`, `point_expiry_days` (+per-tier override), `welcome_bonus`, `min_bill_for_earn`, `block_earn_on_returns`, `require_otp_for_redeem`, `earn_enabled`, `burn_enabled`, `earn_burn_pauses[]`, `category_multipliers{Tickets,F&B,Merchandise,Gaming}`, `store_type_multipliers`, `tier_reset_cadence`, `tier_reset_anchor_date`, `tier_rules[]` (Silver/Gold/Platinum/Director's Circle: min/max_lifetime_spend, earn_multiplier, welcome/birthday/anniversary/upgrade bonuses, colour, expiry override). **Tiers come ONLY from this editor — no hardcoded ladder.** Full editor UI.

==================================================================
8) DATA LAYER — OLD/HISTORICAL DATA + INTEGRITY (must be complete)
==================================================================
- **Historical Upload (old data):** chunked CSV ingest for **Members / Bookings+Bills / Concession-SKU / Properties** as background jobs with progress, skipped-row capture, dedupe, **chunk retention** for healing. Extract property K-code from the registered account; post-pass links code→property (auto-creating stubs) and sets registered/home property. **Auto-backfill** stub members from txn mobiles + recompute R1/R2/R3. Opening balances → ledger, valid till the configurable cutoff (R4).
- **Verify Load:** counts, bill-date coverage, distinct SKUs/members/properties, samples.
- **Data Reconciliation:** upload a source CSV per dataset and compare to DB → matched / missing-in-DB / amount mismatch / mobile mismatch / extra-in-DB, with per-mismatch CSV download. MUST: instant file listing; **Check & Heal** with an **editable go-live cutoff date**; parse OFF the event loop; heartbeat + **stale-job watchdog** (auto-fail > 8 min); per-job **Cancel**; optional **"Deep DB-side scan"** (off by default). Handle ~800k-row files without stalling.

==================================================================
9) DASHBOARDS (13 + Live Monitor — Recharts, IST, drill-downs, date-range, CSV export)
==================================================================
1. **Command Center** — revenue, bills, active members, points liability, redemption rate, today vs MTD.
2. **Sales** — box-office vs F&B vs merch split; revenue/bills/AOV by day/month/property/city/category; top SKUs/movies.
3. **Customer Analytics** — new vs repeat, acquisition, demographics, visit frequency.
4. **Loyalty** — points earned/redeemed/expired, liability, breakage, tier movement.
5. **Campaign Performance** — sends/delivered/opens/redemptions per campaign.
6. **Property Performance** — per-cinema revenue, members, enrolment, redemption.
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
- **Member 360 / detail + drawer:** identity, tier, RFM, home/registered property, lifetime spend/visits/points, full booking+F&B history, points ledger, comms history, tickets, NPS.
- **Segment Builder:** AND/OR groups over RFM/tier/spend/recency/visit-count/city/property/category/favourite-genre/birthday → saved audiences; live preview + count + table + CSV.
- RFM, churn risk, cohorts.

==================================================================
11) MARKETING
==================================================================
- **Campaigns:** audience (segment/upload) → channel + template → schedule/send → delivery/opens/redemptions + ROI.
- **Auto-Campaigns:** welcome, birthday/anniversary, win-back/dormant, tier-upgrade, points-expiry reminder, "new release near your favourite property".
- **Coupons:** combo/upgrade/free-ticket coupons (codes, validity, caps) wired to POS coupon endpoints.

==================================================================
12) COMMUNICATIONS (channel provider configurable)
==================================================================
Integrate **Karix** SMS / WhatsApp / RCS as reference (DLT: entity/template/header IDs). Templates, **Bulk Send Jobs** (chunked/throttled/retried/resumable), **Message Log**, **Provider Settings** (API key, sender/header, DLT IDs). Provider/credentials user-supplied — collect & store, never hardcode. If Doodles uses a different provider, ASK and adapt like the POS (§B).

==================================================================
13) AI — FUNDLE BRAIN (analyst + L1 ops; train EXACTLY like ours)
==================================================================
- **System prompt:** "You are Fundle Brain, the AI analytics assistant AND operations agent for Doodles Cinema powered by Fundle." READ access to live Mongo via tools; **ALWAYS call a tool before any numeric answer**; never fabricate ("Data not available" only after an all-time retry with `days=0`).
- **Live DATA-WAREHOUSE SNAPSHOT** injected as a 2nd system message every turn (collections + counts, bill-date coverage, KPI digest, loyalty config) = ground truth.
- **READ tools:** `get_overall_kpis, customer_search, customer_lookup, recent_bills_for_customer, points_ledger_for_customer, top_customers_report, top_skus, top_churning_customers, tier_distribution, rfm_segments, store_performance (=property), city_performance, location_wise_customer_summary, campaign_leaderboard, coupon_performance, active_coupons_summary, communication_log_summary, nps_summary, tickets_summary, expiry_points_summary, pending_bills_summary, fraud_anomalies, support_desk_audit_log, list_redeemed_points, list_redeemed_coupons, list_deactivated_customers, list_unsubscribed, get_data_dictionary, run_aggregation, export_csv`.
- **`run_aggregation`** = read-only Mongo pipelines (call `get_data_dictionary` first if unsure of fields). **`export_csv`** streams up to **1,000,000 rows** → present EXACTLY `[Download <filename> (<row_count> rows)](<download_url>)`; never paste >20 rows inline; never refuse a raw-data/export request.
- **WRITE (L1) tools, role-gated + audited:** `customer_deactivate, customer_reactivate, unsubscribe_customer, resubscribe_customer, reactivate_coupon_redemption, reactivate_redeem_points`. Protocol: explicit intent → look up target first → require REASON → confirm + cite audit entry → on permission-denied, tell user, don't retry.
- **IST + currency:** group/format dates with `timezone:"Asia/Kolkata"`; ₹ money, % ratios; end with 1–2 actions; reason over CSVs pasted in chat; floating Fundle-Brain FAB across admin.

==================================================================
14) AI — MASTER BRAIN = Fundle Brain + ACTION layer (Master Admins only)
==================================================================
- System prompt = Fundle Brain's FULL prompt **+ Master addendum**: "always **preview → confirm (with a reason) → execute → log**"; still answers every read/analytics/export exactly like Fundle Brain (never downgrade).
- **ACTION tools (two-turn; write `audit_logs` + Undo snapshots where applicable):** `grant_bonus_points, adjust_points, fix_negative_balances, retier_customers, set_customer_tier, apply_to_uploaded_report, send_campaign (Karix bulk), list_campaigns, cancel_campaign, master_action_log, undo_action`, and **`fix_double_redemptions`** — finds members double-deducted by the old redemption bug (duplicate `redeem` ledger rows whose `note` starts "Bill " that ALSO have a legit OTP/non-OTP redeem row for the SAME bill → credits points back, corrects `lifetime_points_redeemed`, voids the duplicate rows; conservative join; idempotent; preview→confirm+reason; not auto-undoable).
- **Execution UX:** every executable recommendation renders a one-click **Execute** button; applied actions appear in the **Action Log** with **Undo** (only where a snapshot exists). Per-user **Query Log**; **Query Admin** sees everyone's. All actions audited (name + reason + timestamp + actor + before/after).

==================================================================
15) REPORTS
==================================================================
Downloads Center, Reports (Legacy), Booking Bill Report, Property KPI Report, Member Report, KPI Trends, Reports & Exports, Exec Digests (scheduled email/PDF), Formula Catalog (every KPI's formula). Respect R1 (bill_date) + R5 (loyalty filter). Large exports via the streaming pipeline.

==================================================================
16) OPERATIONS
==================================================================
Properties (master by **K-code**, tagged `pos_customer_key`+`pos_merchant_id`, bulk upload), Item Master (concession SKUs/combos/ticket classes), API Monitor (§6), POS Credentials (issue/rotate `x-api-key`, merchant_id, customer_key).

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
Home, How It Works, Earn Points (tickets & snacks), Redeem Points (free tickets/combos/upgrades), Rewards, Loyalty Benefits, Tiers, Referral, **Property/Cinema Locator**, About, FAQs, Contact, Privacy, Terms — join-free CTA + welcome credit. ALL copy/images editable at runtime via the **Public Site CMS**.

==================================================================
20) ENV VARS
==================================================================
backend/.env: `MONGO_URL, DB_NAME, CORS_ORIGINS, JWT_SECRET, JWT_ALGORITHM, JWT_EXPIRY_HOURS, EMERGENT_LLM_KEY, BRAND_NAME, SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD, BRAND_ADMIN_EMAIL, BRAND_ADMIN_PASSWORD` (+ POS keys via POS Credentials, + provider keys via Provider Settings). frontend/.env: `REACT_APP_BACKEND_URL`. No comments in .env; no hardcoded fallbacks.

==================================================================
21) NON-FUNCTIONAL
==================================================================
Production-grade: indexed queries, cache-warmed dashboards, streaming exports, event-loop-safe background jobs with watchdogs, full audit trails, RBAC on every mutation, IST everywhere, no Emergent branding, no mocked flows.

==================================================================
22) BUILD / ADAPT ORDER (test each phase before moving on)
==================================================================
0. Import the GitHub repo, run it, confirm it boots. ASK which POS + get docs (§B). Confirm brand palette/logo. Strip Emergent branding (§C).
1. Brand config + design system + auth/roles + admin shell/sidebar.
2. Data model + Loyalty Rules editor + points ledger + canonical rules R1–R6.
3. POS integration (mapped to Doodles' POS) + Live Monitor + API Monitor + POS Credentials.
4. Historical/old-data Upload + Verify Load + Reconciliation (watchdog/cancel/deep-scan).
5. Members (360, segments, RFM, cohorts) + Properties + Item Master.
6. 13 Dashboards + drill-downs + exports.
7. Communications (Karix/provider) + Campaigns + Auto-Campaigns + Coupons.
8. Fundle Brain (reads + L1 writes + run_aggregation + export_csv + data snapshot).
9. Master Brain (action layer + Execute buttons + Action Log/Undo + Query Log + fix_double_redemptions).
10. Reports suite + NPS + Tickets + Support Desk + Public site/CMS. Final pass: remove any remaining Emergent strings; full regression test.

==================================================================
23) ACCEPTANCE CHECKLIST (nothing may be missing)
==================================================================
[ ] Imported from our GitHub repo as the baseline. [ ] POS confirmed + adapted from docs (added/removed fields, incl. show/screen/seat/movie if present). [ ] All Emergent branding removed. [ ] All 13 dashboards + Live Monitor. [ ] Full POS API (lookup/enrol/OTP redeem-once/earn/returns/coupons/wallet) with R1–R6. [ ] Loyalty Rules editor (tiers from editor only; Tickets vs F&B multipliers). [ ] Historical/old-data ingest + opening balances + Verify Load + Reconciliation (watchdog/cancel). [ ] Members 360 + Segment Builder + RFM/cohorts. [ ] Campaigns + Auto-Campaigns + Coupons. [ ] Communications (templates/bulk/log/provider settings, DLT). [ ] Fundle Brain (full read + L1 write tools + run_aggregation + export_csv). [ ] Master Brain (all action tools incl. fix_double_redemptions + Execute + Action Log/Undo + Query Log). [ ] Reports suite + Formula Catalog. [ ] Properties/Items/API Monitor/POS Credentials. [ ] Tickets + NPS + Support Desk. [ ] User Management (roles + master/query-admin flags). [ ] Public site + CMS. [ ] IST everywhere, audit on every mutation, production-grade, no mocks.

**Build production-grade, test every phase (use the testing agent for multi-endpoint/CRUD flows), confine all branding to the 3 rebrand points, keep Tickets vs F&B as separate category multipliers, and ASK me whenever the POS or provider documentation is needed.**
