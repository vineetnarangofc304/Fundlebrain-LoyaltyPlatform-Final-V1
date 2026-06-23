# ORCHID HOTELS — Loyalty / CRM / Analytics Platform — FULL BUILD PROMPT (for a fresh Emergent project)

> **How to use this file:** Open a brand-new Emergent project and paste this entire document
> as the opening prompt. It is a faithful, complete replica spec of the existing KAZO “Fundle”
> platform, re-branded and re-architected for **The Orchid Hotels** (eco-luxury hospitality
> chain). The agent should build it phase-by-phase and test after each phase.
>
> **The ONLY things that change vs. the original platform:**
> 1. **Brand** → Orchid Hotels (logo, colours, copy from orchidhotel.com; hospitality terminology).
> 2. **Data ingestion** → instead of POS systems pushing bills directly, all customer + transaction
>    data is **PULLED from an upstream “Fundle” system via a Data Bridge (API key)**, and
>    **loyalty points arrive PRE-COMPUTED** (Fundle does the point math; this platform does NOT
>    recompute earning).
>
> Everything else (modules, dashboards, reports, RBAC, AI brain, comms, scale guardrails) is the same.

---

## 0. PRODUCT SUMMARY (what we are building)

A complete, enterprise-grade, **single-tenant** loyalty + CRM + analytics + campaign-automation +
customer-intelligence + support + reporting + integration-monitoring platform for **The Orchid Hotels**,
powered by **Fundle**.

- **Tenant:** Orchid Hotels only (dedicated deployment, dedicated MongoDB).
- **Audience:** brand HQ marketing/CRM/analytics teams, regional managers, property (hotel) managers,
  support agents, and read-only executives.
- **Core promise:** one real-time command center over every guest, stay, folio, point, tier,
  campaign and channel — with zero dummy data (real data or “N/A”).

### Brand context (Orchid Hotels)
- The Orchid Hotels = **Asia’s first 5-star eco-luxury hotel chain** (“Green Stay” philosophy),
  operated by Kamat Hotels India. Positioning: **sustainable luxury** (“luxury that’s kind to the planet”).
- Tone: premium, warm, eco-conscious hospitality. NOT fashion/retail.
- **Get exact colours + logo from:** `https://www.orchidhotel.com` and `https://brandfetch.com/orchidhotel.com`.
  Default working palette (verify/replace against the site): deep eco-green primary, gold/champagne
  secondary accent, ivory/cream background, charcoal/near-black for header/footer.

### Hospitality terminology mapping (relabel UI strings; keep DB collection names neutral)
| Original (retail) | Orchid (hospitality) |
| --- | --- |
| Store / Outlet | **Hotel / Property** |
| Bill / Transaction | **Folio / Stay / Invoice** |
| Shopper | **Guest** |
| Item / SKU Master | **Services / Room-types / F&B / Spa items** |
| Purchase | **Stay / Visit** |
| Store Code | **Property Code** |
> Keep MongoDB collections (`customers`, `transactions`, `stores`, `points_ledger`, …) and API
> prefixes (`/api/...`) **unchanged** — only the human-visible labels change.

---

## 1. TECH STACK & ENVIRONMENT (non-negotiable)

- **Backend:** FastAPI + Motor (async MongoDB) + JWT/cookie auth + APScheduler + Emergent LLM
  (LiteLLM via `emergentintegrations`).
- **Frontend:** React + Tailwind + shadcn/ui primitives + Recharts + lucide-react icons.
  Typography: an elegant serif display (e.g. Cormorant Garamond) + a clean sans (e.g. Manrope).
- **DB:** single MongoDB database; name from `DB_NAME` env. All data real-time aggregations
  (NO stored snapshots unless explicitly cached for performance).
- **Routing:** every backend route prefixed with `/api`. Frontend calls ONLY
  `process.env.REACT_APP_BACKEND_URL`. Backend reads ONLY `os.environ` (MONGO_URL, DB_NAME, etc.).
  No hardcoded URLs/keys/ports. Missing config must fail fast (no silent defaults).
- **Timezone:** **everything IST / Asia-Kolkata** for display, grouping and date math
  (use `$dateToString`/`$dateTrunc` with `timezone:"Asia/Kolkata"`; never string-slice raw dates).
- **Theme:** LIGHT editorial theme only (no dark themes).
- **No dummies / no hardcode / no fallbacks** — show real data or “N/A”.
- **data-testid** on every interactive + every critical info element (kebab-case, unique).

### GLOBAL SCALE GUARDRAILS (production runs at ~1M+ guests / ~1M+ folios)
- NEVER run `.aggregate()` on large `transactions`/`customers` without: a `$match`, `allowDiskUse=True`,
  AND caching or a bounded page scope.
- Add a `db_deadline` FastAPI dependency wrapping requests in `pymongo.timeout(45)`; attach to every
  analytics/dashboard/report router.
- Consolidate multi-aggregation dashboard endpoints into a **single `$facet` scan** where possible;
  wrap each branch in try/except → degrade to empty buckets (HTTP 200 + `degraded[]` flag) instead of 500.
- Add a TTL cache module (~5 min, stale-while-revalidate ≤1h) on the ~20 heaviest endpoints + a
  background cache-warmer (~4 min) that warms the 8 heaviest default views via localhost with a minted
  super-admin JWT. Never cache degraded responses.
- Build all hot-path indexes on startup (idempotent background task). See §11.
- After ANY change, remind the user a **REDEPLOY** is required for production to reflect it.

---

## 2. DATA MODEL (MongoDB collections + Pydantic models)

Use a `BaseDocument` pattern (map `_id`→`id` as string; never return raw ObjectId).
`datetime.now(timezone.utc)`; store ISO strings where compared as strings.

**Core collections & key fields:**

- **users** — `email, name, role, phone, store_id, region, is_active, created_at, last_login_at, last_login_ip`.
  Roles (enum): `super_admin, brand_admin, crm_manager, marketing_manager, regional_manager,
  store_manager (=property_manager), store_staff, support_agent, analytics_viewer, readonly_executive`.
- **customers (guests)** — `mobile (canonical id), name, email, birthday, anniversary, city, state,
  gender, tier, points_balance, lifetime_points_earned, lifetime_points_redeemed, lifetime_spend,
  visit_count, last_visit_at, first_purchase_at, churn_risk(low|med|high), favourite_categories[],
  nps_score, home_store_id, registered_store_id, source, created_at`.
- **stores (hotels/properties)** — `code, name, city, state, region(zone), address, phone, manager_name,
  latitude, longitude, is_active, pos_merchant_id, pos_customer_key, source, created_at`.
- **transactions (folios/stays)** — `customer_id, customer_mobile, store_id, store_code, bill_number,
  bill_date, gross_amount, discount_amount, net_amount, tax_amount, bill_with_tax, items[]
  {sku,name,category,quantity,unit_price,total}, payment_mode, points_earned, points_redeemed,
  coupon_code, is_return, original_bill_number, source, received_at(created_at)`.
- **loyalty_config** (single `default` doc) — full earn/burn/tier/bonus/multiplier/compliance config (see §6).
- **points_ledger** — `customer_id, customer_mobile, type(earn|redeem|bonus|adjust|expire|opening),
  points, reference_type(transaction|campaign|manual|welcome|tier_upgrade|recalc|opening),
  reference_id, source_bill_id, note, expires_at, created_at, created_by`.
- **coupons** — code, name, coupon_type(flat|percentage|sku|category|store|city|referral|birthday|
  anniversary|winback|new_customer|festival|vip), discount_value, min_bill_amount, max_discount,
  valid_from/to, usage limits, targeting (cohort/tier/city/category/sku), require_otp, times_used/issued.
- **campaigns** — name, channels[](whatsapp|sms|email|push), audience_type(all|tier|city|cohort|custom|
  segment), audience_filter, message_template, template_id, coupon_code, schedule_at, status, send_limit,
  metrics (sent/delivered/opened/clicked/redeemed/revenue_generated), bulk_job_id, send_mode.
- **api_logs** — endpoint, method, status_code, response_time_ms, customer_mobile, bill_number,
  error_reason, store_id, request_payload, timestamp (the Integration/API Monitor feed).
- **nps_responses** — customer_mobile, store_id, score(0-10), sentiment(promoter|passive|detractor),
  feedback, category, created_at.
- **tickets** — customer_mobile, subject, description, category, priority, status, assigned_to, notes[].
- **ai_chat_sessions** — user_id, title, messages[]{role,content,data,timestamp}.
- **audit_logs** — user_id, user_email, action, entity, entity_id, metadata, ip, timestamp.
- **message_log** — every SMS/WhatsApp/RCS dispatch w/ raw provider response, channel, status,
  bill_number, sender_id, dlt_template_id, trigger_source, created_at.
- Plus: `provider_config` (loyalty_config + comms provider creds + **data_bridge** config, see §7),
  `templates` (comms), `bulk_send_jobs`, `segments`, `historic_ingest_jobs` + `historic_chunks`,
  `tts_cache`, `cms` content, `pos_otp_sessions` (canonical OTP store), `items`(master).

---

## 3. AUTH & RBAC (custom JWT — treat as an integration; use the JWT auth playbook)

- **Three login portals** (one backend, gated by `portal` field): `/enterprise/login`, `/crm/login`,
  `/store/login`. CRM portal allows all dashboard roles; Store portal allows store roles + admins.
- **JWT** (HS256) + httpOnly cookie; bcrypt password hashing. Brute-force protection. Password reset.
- **Role groups:** `ADMIN_ROLES = {super_admin, brand_admin}`;
  `MANAGEMENT_ROLES = {+crm_manager, marketing_manager, regional_manager}`;
  `ALL_DASHBOARD_ROLES = {+store_manager, analytics_viewer, readonly_executive, support_agent}`.
- **Seeding (idempotent, from `.env`):** super admin (`SUPER_ADMIN_EMAIL`) + brand admin
  (`BRAND_ADMIN_EMAIL`/`BRAND_ADMIN_PASSWORD`). Force password rotation after first login.
- **Read-only demo user** (`is_demo`) — all write methods blocked except an allowlist
  (`/api/demo*`, logout, AI chat, dashboard insight/drilldown).
- Audit-log every privileged write.

> ⚠️ When implementing ANY auth code, FIRST consult the custom-JWT integration playbook
> (do not hand-roll). Save created credentials to the project’s test-credentials file.

---

## 4. BACKEND MODULES (FastAPI routers — build all; `/api` prefix)

Register all routers under a single `/api` `APIRouter`. Modules (group as noted):

**Auth & users:** `auth_routes` (login per-portal, me, logout, password reset),
`users_routes` (CRUD users, role mgmt — admin only).

**Customers & loyalty:** `customers_routes` (Guest 360, search, detail, ledger),
`loyalty_routes` (loyalty config GET/PUT, tier CRUD, earn/burn master switches + scheduled pause
windows, **re-tier tool** preview/apply — see §6), `coupons_routes` (coupon engine CRUD + targeting).

**Campaigns & comms:** `campaigns_routes` (campaign CRUD + launch), `auto_campaigns_routes`
(trigger-based automation), `communications_routes` (templates, provider settings, bulk send jobs,
message log, `send_sms_karix`, `fire_event`, provider-connectivity diagnostic), `segments_routes`
(segment builder), `cohort_library_routes`.

**Analytics & dashboards:** `dashboard_routes` (command-center, kpis, tier-distribution, insight,
drilldown), `analytics_routes` (lifecycle split, RFM, cohorts/retention, etc.), `drilldown_routes`
(+ export), `reports_kpi_routes` (+ export), `reports_routes`, `legacy_reports_routes`,
`raw_reports_routes`, `shopper_report_routes` (+ export) → relabel **Guest Folio Report**,
`recon_routes` (CSV↔DB reconciliation), `exports_routes` (download center).

**Ingestion & ops:** `historic_routes` (chunked CSV historical upload + verify-load),
**`data_bridge_routes`** (NEW for Orchid — see §7), `live_monitor_routes` (live folio feed + stats
+ recalc), `stores_routes` (hotel master), `items_routes` (services/room/F&B master),
`api_monitor_routes` + `api_log_detail` (integration monitor), `pos_creds_routes` (API keys).

**AI / support / public:** `fundlebrain_routes` + `ai_routes`/`ai_tools`/`ai_extended_tools`/
`ai_data_expert` (the “Orchid Brain” assistant), `support_desk_routes` (L1 ops), `tickets_routes`,
`nps_routes`, `cms_routes` (public site CMS), `public_routes` (public site data), `demo_routes`
(self-running narrated demo + OpenAI TTS).

> **Optional/legacy:** the original 14 eWards-compatible POS endpoints (`/api/pos/*`) MAY be kept as
> an inbound fallback, but for Orchid the **canonical inbound path is the Fundle Data Bridge (§7)**.

---

## 5. FRONTEND (React) — routes & screens

### Public marketing site (`PublicLayout`, content from orchidhotel.com)
`/` Home, `/about-program`, `/loyalty-benefits`, `/rewards`, `/how-it-works`, `/earn-points`,
`/redeem-points`, `/referral-program`, `/store-locator` (→ **Hotel/Property Locator**), `/faqs`,
`/privacy`, `/terms`, `/contact`. All copy/imagery editable via the **Public Site CMS**.

### Login portals
`/enterprise/login`, `/crm/login`, `/store/login`. Plus `/demo` (public narrated product tour).

### Admin app (`/admin`, `ProtectedRoute` + `AdminLayout` with accordion sidebar)
Default landing = **Live Monitor** (live folio feed). Sidebar sections + pages:

- **DASHBOARDS:** Command Center, Executive Cockpit, Sales (→ **Revenue/Stays**), Customer Analytics
  (→ **Guest Analytics**), Loyalty, Campaign Performance, Store (→ **Property**), NPS, RFM & Churn,
  Cohorts, Points Economics, Campaign ROI, Executive Summary. (Each with full drill-down + Retry-on-error.)
- **CUSTOMERS:** Guest 360 (list) + Guest detail.
- **MARKETING:** Campaigns, Auto-Campaigns, Coupons, Segment Builder.
- **COMMUNICATIONS:** Templates, Message Log, Bulk Send Jobs, Provider Settings.
- **AI TOOLS:** Orchid Brain (function-calling analytics + L1 ops + CSV export; markdown tables).
- **DATA:** **Fundle Data Bridge** (sync status/config — see §7), Historical Upload, Verify Load,
  Reconciliation.
- **OPERATIONS:** Hotels/Properties (master, paging, S.No, City/State/Zone dropdowns), Services Master
  (item master), API/Integration Monitor, API Credentials, Live Monitor.
- **SUPPORT:** Support Desk (search redeem points/coupon OTP, reactivate coupon/points, deactivate/
  reactivate guest, update mobile, unsubscribe, audit log), Tickets, NPS Inbox.
- **REPORTS:** Reports (Legacy hub: customer-data, transaction-data, repeat-customers, top-customers,
  fraud, pending-bills, feedback, missed-calls, location-wise, expiry-points, active-coupons),
  Raw Reports, Guest Folio Report (shopper-bills), Store/Property KPI, CRM Guest Report, KPI Trends,
  Exec Digests, Formula Catalog, Downloads Center.
- **CONFIGURATION:** Loyalty Rules (configurator), Public Site CMS.
- **ADMINISTRATION:** User Management.

### Store/Property portal
`/store` → `StoreOps` (property-manager day-to-day view; role-gated).

### Shared UI behaviours
- Accordion sidebar (only active section expanded) + desktop collapse + mobile drawer.
- Every dashboard: graceful error card + Retry (never infinite spinner / blank).
- Movable floating **Orchid Brain** FAB (pointer-drag with click-vs-drag threshold; position persisted).
- Exact money formatting (`fmtMoney2`: Indian commas, always 2 decimals, no Cr/L/K compaction in
  tables; compaction only on KPI tiles). IST date formatters (`fmtDateISO`/`fmtDateTimeISO`).

---

## 6. LOYALTY ENGINE (configurable rules — Loyalty Rules page)

> ⚠️ Orchid note: because **points are pre-computed by Fundle** (§7), the EARN math here is
> **reference/config only** for bridge-sourced folios — the platform does NOT recompute earning for
> them. Keep the full configurator (tiers drive segmentation, badges, reports; bonuses/redeem rules
> still apply to any in-platform actions). Add a global flag `loyalty_source = "fundle_bridge"` that
> disables in-platform earn recompute + the Recalc tool for bridge data.

**Earn engine config:** `earn_mode` (`points_per_spend` | `percent_of_spend`), `earn_ratio`,
`percent_of_spend`. (Canonical earn rule from the original build, retained for documentation /
non-bridge paths: when the global earn rate is blank/0, the **per-tier multiplier IS the % of bill** —
mult 2 → 2%, 3 → 3%, 5 → 5%; otherwise base × rate × tier-multiplier. Earn on **net (pre-GST)** base,
gated by `loyalty_flag`, `min_bill_for_earn`, and earn pause windows.)

**Redeem engine:** `burn_ratio` (₹ per point), `min_redeem_points`, `max_redeem_pct_of_bill`,
`require_otp_for_redeem`, `point_expiry_days` (default 365). Block redemption on discounted bills.

**Tiers (free-string slugs, brand-defined — NO hardcoded ladder):** each `TierRule` has
`tier, name, min_lifetime_spend, max_lifetime_spend, earn_multiplier, welcome_bonus, birthday_bonus,
anniversary_bonus, upgrade_bonus (slab-wise), tier_type, is_active, coupon_discount_pct,
free_shipping_min_bill, point_expiry_override_days, visit_threshold, color`. Tier is derived strictly
from configured bands (highest band whose `min_lifetime_spend` is met); empty config → untiered (“”).
`tier_reset_cadence` (never|annual|rolling_12m).

**Bonuses:** global `welcome_bonus` (once per guest, ledger-guarded), `birthday_bonus`,
`anniversary_bonus`, referral points (referrer/referee), slab-wise `upgrade_bonus`.

**Multipliers / boosters:** `category_multipliers`, `store_type_multipliers`, `festival_boosters`.

**Earn & Burn Control:** master `earn_enabled`/`burn_enabled` switches + scheduled blackout windows
(`earn_burn_pauses`: id, label, start/end, pause_earn, pause_burn, active).

**Re-tier tool (admin):** `POST /api/loyalty/retier/preview` + `/retier/apply` — re-maps historical/
pre-bridge guests onto the current configured tiers **without awarding any bonus points**; processes
in bounded batches (≤1–2k/loop) to avoid Atlas timeouts; filters by `source` (excludes bridge/live).

---

## 7. 🔌 FUNDLE DATA BRIDGE (Orchid’s ingestion model — REPLACES direct POS)

> This is the single biggest architectural change vs. the original (KAZO) build. Read carefully.

### 7.1 Concept
For Orchid, there is **no direct POS/PMS push** into this platform. Instead, an upstream system called
**Fundle** is the system of record: all guest data, stay/folio data, AND the **loyalty point math**
live in Fundle. This platform **pulls** that data over HTTPS using an **API key** the user provides,
and stores it. **Points arrive already computed** — this platform must treat
`points_earned` / `points_redeemed` / `points_balance` / `tier` from the bridge as **authoritative**
and must **NOT recompute** them.

### 7.2 Connector config (stored in `provider_config.data_bridge`; editable on the Data Bridge page)
```
data_bridge = {
  base_url:            "https://<fundle-bridge-host>",      // from user
  api_key:             "<provided by user>",                 // sent as header
  auth_header:         "x-api-key",                          // or "Authorization: Bearer"
  customers_endpoint:  "/export/customers",                  // confirm with Fundle
  transactions_endpoint:"/export/transactions",             // confirm with Fundle
  ledger_endpoint:     "/export/points-ledger",              // optional
  sync_enabled:        true,
  sync_interval_min:   15,
  page_size:           1000,
  cursor_customers:    "<ISO updated_since>",                // incremental cursor
  cursor_transactions: "<ISO updated_since>",
  last_sync_at:        null,
  last_sync_status:    null
}
```
> ⚠️ Do NOT hardcode the URL or key — read from saved config (which the user enters in the UI / `.env`).
> Ask the user for: Fundle bridge **base URL**, **API key**, the **exact field names** in Fundle’s
> customer & transaction payloads, the auth header style, and the incremental-sync field
> (e.g. `updated_since`). (Confirm with the user before building the field mapper.)

### 7.3 Sync job (APScheduler + manual “Sync Now” button)
A scheduled job (every `sync_interval_min`) **and** a manual trigger:
1. **Pull customers** (paginated, `updated_since=cursor_customers`): map → `customers` and **upsert by
   `mobile`**. Fields: mobile, name, email, city, state, tier, **points_balance**, lifetime_points_earned,
   lifetime_points_redeemed, lifetime_spend, visit_count, last_visit_at, first_purchase_at, birthday,
   anniversary. **`points_balance` and `tier` are authoritative — overwrite local with bridge values.**
2. **Pull transactions/folios** (paginated, `updated_since=cursor_transactions`): map → `transactions`
   and **upsert by `bill_number`** (or Fundle’s folio/transaction id). Fields: bill_number, bill_date,
   property code → resolve to `store_id`, customer_mobile, gross/discount/tax/net, items[],
   **points_earned (pre-computed)**, **points_redeemed (pre-computed)**, is_return. **Store points
   exactly as delivered. Never run the earn engine on these rows.**
3. **(Optional) Pull points_ledger** to mirror exact balance history (`type, points, reference_type,
   created_at, expires_at`). If not available, synthesize one `earn`/`redeem` ledger row per folio from
   the delivered points so reports/expiry still work.
4. After each dataset, **advance the cursor** to the max `updated_since` seen; persist
   `last_sync_at`, counts (pulled / upserted / skipped / errors) and `last_sync_status`.

### 7.4 Resilience / scale (mandatory)
- Incremental cursors (only pull changed rows since last sync). Pagination (`page_size`).
- **Bounded batched upserts** (1–2k/batch) with a heartbeat per batch; `pymongo.timeout` on writes.
- Retry on connect-level errors only (ConnectTimeout/ConnectError), small backoff (≤4 attempts);
  never retry read timeouts (avoid double-processing). Idempotent (upserts) so a re-run is safe.
- Wrap the whole sync in try/except → record errors to the sync status + `api_logs` (so failures are
  visible in the Integration Monitor). A failed page must not abort the whole job.

### 7.5 Data Bridge page (DATA section, super_admin/brand_admin)
- **Config card:** base URL, masked API key (with reveal/rotate), endpoints, auth header, interval,
  enable/disable toggle, “Test connection” button (calls a lightweight `/ping` or first page).
- **Sync controls:** “Sync Now” (full or incremental), per-dataset toggles, last-sync verdict banner,
  cursors shown.
- **Sync log / stats:** last sync time, rows pulled vs upserted vs skipped vs errors per dataset,
  recent errors, link to Integration Monitor. (Model this on the existing Historic Data / Verify-Load
  pages.)

### 7.6 Redemption with pre-computed points (decision point — confirm with user)
Because points are computed at Fundle, **redemption also normally originates upstream**. Default
behaviour: this platform **mirrors** balances/ledger from Fundle and shows redemption history
(read-only). If Orchid wants guests to redeem **from this platform**, the redeem/OTP flow must
**write back** to Fundle via a Fundle endpoint (the user must provide it) so balances stay in sync —
otherwise local deductions would drift from Fundle. **Build redemption as read-only mirror by default;
make write-back a configurable add-on.**

### 7.7 Backfill
Keep the **Historical CSV Upload** module for a one-time backfill of years of history (chunked upload,
idempotent ingest, opening-balance ledger). For Orchid the historical files likewise carry
pre-computed points/tiers → ingest them as authoritative (no recompute), same as the bridge.

---

## 8. INTEGRATIONS (use the integration playbooks; ask user for keys)

- **Fundle Data Bridge** — REST pull over HTTPS with an **API key** (user-provided; see §7).
- **Karix / Kaleyra (Instaalerts)** SMS + WhatsApp + RCS — user provides API key, sender ID, and
  **DLT Content Template IDs + Telemarketer/Entity IDs** (mandatory for Indian SMS delivery).
  Send the exact provider QueryString param set from saved Provider Settings; sender ID from Provider
  Settings is authoritative; only send `active` templates; retry connect-errors only.
  > NOTE: intermittent `ConnectTimeout` is usually an **egress-IP allowlist** issue → needs a static
  > egress IP/CIDR from Emergent Support (not a code fix).
- **Emergent LLM key** (universal) for: **Orchid Brain** text (GPT / Claude / Gemini) and **OpenAI TTS**
  (demo narration, cached in `tts_cache`). Use `emergentintegrations` — do NOT install vendor SDKs directly.
- **Emergent Object Storage** — for AI CSV exports + (optionally) scheduled backups + CMS image uploads.
- **OpenAI TTS** — `tts-1`, voice `nova`, cached by content hash, returns audio/mpeg.

> For each integration, call the integration playbook FIRST, then ask the user for the required keys
> BEFORE coding. Implement exactly per the playbook (model names, versions, config).

---

## 9. AI “ORCHID BRAIN” ASSISTANT

- Inject a cached (~10 min) **live data-warehouse snapshot** system message: collections + row counts,
  folio-date coverage, a brand KPI digest (lifecycle split, tier split, all-time revenue/ATV, top
  properties 90d), loyalty config, and a data-provenance note.
- Guard-railed **read tools**: `run_aggregation` (read-only; forbid `$out/$merge/$function/$where`;
  cap ~200 rows; require server-side `$group/$sort/$limit`) + `get_data_dictionary`.
- `export_csv` tool: streams up to ~1M rows to object storage / exports dir, served via auth-protected
  `GET /api/ai/exports/{id}` (202 while preparing, 404 unknown). Chat renders a styled download button.
- Role-gated **write tools** for L1 support (deactivate/reactivate/unsubscribe/reactivate coupon/redeem)
  with mandatory confirm + reason + audit log.
- Rendering: react-markdown + remark-gfm; mandate Markdown tables + ₹ Indian grouping; IST date rule.
- Single locked best model (no model dropdown). Decisive: never ask clarifying Qs before a read; never
  copy-paste CSV hacks (use `export_csv`); fix-and-retry-once on pipeline errors; always end with a
  table + export link.

---

## 10. DASHBOARDS & REPORTS (build one-by-one; full drill-down; test each)

- **Command Center / Executive Cockpit / Executive Summary** — top-line KPIs (guests, stays, revenue,
  ATV, point liability), AI intelligence report, sparkline, cohort tiles. Single `$facet`, degrade-not-500.
- **Revenue (Sales), Guest Analytics, Loyalty, Campaign Performance, Property (Store), NPS, RFM & Churn,
  Cohorts, Points Economics, Campaign ROI** — each with KPI cards + charts + a reusable DrillDownModal.
- **Guest Folio Report (Shopper Bill):** one row PER folio for everyone who stayed in a date range,
  ~22 columns (Folio Date/Time, Type Regular/Return, Guest Mobile, Reg Property, Property Code, Trans
  Property, Trans ID, Folio #, Guest Type New/Existing, Recency Active 0-6M/Dormant 6-12M/Lapsed 12M+,
  Last Visit, 2nd-last Visit, Total Visits, Zone, City, Net-before-tax, Total Tax, Total Discount,
  Total Folio Amount, Lifetime Purchase, Lifetime Bill-cuts NET). Paginated listing + separate streamed
  CSV export router (no db_deadline on export). Scale-safe sort-first/short-circuit path.
- **Legacy Reports hub** (11 reports) + **Raw Reports** — server-side pagination, batch lookups (kill
  N+1), capped CSV export, error-retry UI, date filters everywhere, all under `db_deadline`.
- **Live Monitor:** live folio feed (3s auto-refresh) + KPI cards + date-range filter + client-side
  pagination (50/page) + per-folio drill drawer + “Lost guest” handling (invalid mobile → non-loyalty).
  For Orchid this shows bridge-synced folios near-real-time after each sync.
- **Reconciliation:** chunked CSV re-upload → row-level CSV↔DB compare (missing/mismatch/extra +
  totals), downloadable mismatch CSV. (For Orchid, also reconcile bridge-pulled counts vs Fundle.)
- **Downloads Center:** central list of generated exports.

---

## 11. INDEXES (build idempotently on startup, background task)
- `transactions`: `bill_date`, `customer_mobile`, `(store_id,bill_date)`, `(customer_mobile,bill_date)`,
  `bill_number`, `transaction_id`, `is_return`, `city`, `store_name`.
- `customers`: `mobile` (plain non-unique lookup + partial-unique), `tier`, `home_store_id`,
  `last_visit_at`, `first_purchase_at`, `lifetime_spend`, `city`, `created_at`, `visit_count`.
- `points_ledger`: `customer_mobile`, `(type,expires_at)`, `created_at`, `source_bill_id`, `bill_date`.
- `api_logs`: `(timestamp,status_code)`. `message_log`: `created_at`.
- `historic_chunks (job_id,chunk_index)`, `historic_ingest_jobs (status,queued_at)`.

---

## 12. BRANDING CUSTOMIZATION (Orchid) — exact steps

1. **`frontend/src/brand.config.js`** — single source of truth for display strings + colours:
   - `name:"The Orchid Hotels"`, `legalName`, `domain:"orchidhotel.com"`,
     `shortDescriptor:"eco-luxury hotels & resorts"`.
   - `loyaltyProgramName` (e.g. “Orchid Rewards” / “Green Stay Rewards”), `welcomeToast`, `ctaJoinFree`.
   - `social.*`, `meta.title/description`, `homeCopy.*`, `footerTagline`, `loginCopy.*`.
   - `colors{ black, cream, burgundy(=primary), burgundyDeep, champagne(=secondary), champagneLight }`
     → set to Orchid’s palette (eco-green primary + gold/champagne secondary + ivory background).
     **Keep the CSS variable NAMES (`--kazo-*`) — only swap the hex values** (50+ classes depend on them).
2. **`frontend/src/index.css`** (top) — same hex values as fallback before React mounts.
3. **`frontend/public/index.html`** — static `<title>` + meta/og tags → Orchid.
4. **Logo** — replace `/public/<platform>-logo.png` (and any KAZO wordmark) with the **Orchid Hotels
   logo** (get from orchidhotel.com / brandfetch); render on dark surfaces (sidebar, login, footer).
5. **`backend/.env`** — `BRAND_NAME="The Orchid Hotels"`, `BRAND_ADMIN_EMAIL`, `BRAND_ADMIN_PASSWORD`,
   `SUPER_ADMIN_EMAIL`, fresh random `JWT_SECRET`, plus Data-Bridge + Karix + Emergent keys.
6. **Imagery & copy** — pull hero/property/dining/wellness imagery + program copy from
   `orchidhotel.com` (or upload via the **Public Site CMS** after first login). Relabel all retail terms
   to hospitality (§0 table).
> Everything else (React/FastAPI/Mongo plumbing) is brand-neutral — do NOT rename CSS classes,
> collections, or `/api` prefixes.

---

## 13. BUILD PHASES (do in order; TEST after each before moving on)

1. **Foundation:** env + Mongo connect + `BaseDocument` + startup indexes + JWT auth (3 portals) +
   seed super/brand admin. Test: login per portal, RBAC gate.
2. **Core entities + masters:** customers(guests), stores(hotels), items(services), transactions
   schema, loyalty_config + Loyalty Rules configurator (tiers/earn/burn/bonuses/pauses/re-tier).
   Test: CRUD + config persistence.
3. **🔌 Fundle Data Bridge (§7):** connector config UI + test-connection + field mapper + scheduled
   pull + manual Sync Now + idempotent batched upserts + cursors + sync status page. Treat points/tiers
   as authoritative. Test: dry-run sync against Fundle sandbox; verify guests + folios + points land and
   re-sync is idempotent. **(Confirm Fundle payload field names with user first.)**
4. **Live Monitor + Integration/API Monitor + reconciliation + historical CSV backfill.**
5. **Dashboards (one-by-one, with drill-downs + Retry + degrade-not-500) + scale guardrails
   (db_deadline, $facet, TTL cache, cache-warmer).**
6. **Reports:** legacy hub, raw reports, Guest Folio report (+streamed export), Property KPI, CRM Guest
   report, KPI trends, Downloads Center.
7. **Marketing & comms:** coupons, segments, campaigns, auto-campaigns, templates, Karix provider
   (SMS/WA/RCS), message log, bulk jobs, DLT fields.
8. **Support desk + tickets + NPS.**
9. **Orchid Brain AI (read tools + export_csv + L1 write tools + markdown).**
10. **Public marketing site + CMS + 3 login portals + demo tour (TTS).**
11. **Branding pass (§12)** + final end-to-end testing + deploy.

> After each phase: run the testing agent (backend + frontend) and fix all issues before proceeding.
> Remind the user that production needs a **redeploy** to reflect changes.

---

## 14. ACCEPTANCE CRITERIA
- All modules above present and functional; zero dummy data; real-time aggregations.
- Fundle Data Bridge pulls guests + folios + pre-computed points on schedule and on demand;
  points/tiers authoritative; idempotent; visible sync status + errors in Integration Monitor.
- Dashboards never 500 / never hang (degrade + Retry); reports paginate + export; all dates IST;
  money exact-2dp in tables.
- Full RBAC across 3 portals + 10 roles; audit logging on privileged writes.
- Orchid branding applied (logo, palette, copy, hospitality terminology) end-to-end.

---

## 15. DECISIONS TO CONFIRM WITH THE USER (before/early in build)
1. **Fundle bridge contract:** base URL, API key, auth header style, exact customer + transaction +
   ledger field names, incremental-sync field, pagination style, and a test/sandbox endpoint.
2. **Redemption model:** read-only mirror of Fundle balances (default) vs in-platform redeem with
   write-back to Fundle (§7.6).
3. **Loyalty program name** for Orchid (e.g. “Orchid Rewards” vs “Green Stay Rewards”).
4. **Exact Orchid palette + logo asset** (confirm hex from orchidhotel.com / brandfetch).
5. Whether to **keep the legacy `/api/pos/*` push endpoints** as a fallback inbound path or remove them.
