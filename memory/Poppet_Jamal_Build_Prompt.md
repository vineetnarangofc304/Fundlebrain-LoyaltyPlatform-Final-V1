# BUILD PROMPT — "Poppet Jamal" Loyalty, CRM, Analytics & AI Platform
_(A faithful clone of the KAZO/Fundle platform, rebranded for **Poppet Jamal**, with ALL current functionality — updated with the latest additions.)_

---

## 0. MISSION (one line)
Build a **single-tenant, enterprise loyalty + customer-intelligence + CRM + analytics + campaign-automation + AI platform** for the retail brand **Poppet Jamal**, running on the **Fundle** loyalty engine. It spans a public loyalty website, an in-store POS loyalty integration, a CRM/analytics back-office, campaign automation (SMS **and** WhatsApp), an action-enabled AI assistant, finance-grade reporting/exports, support tooling and operational monitoring — all **config-driven and brandable from a single file**.

---

## 1. TECH STACK & HARD CONSTRAINTS
- **Frontend:** React 19 + React Router, Tailwind + shadcn/ui, lucide-react icons, recharts, sonner toasts. Pages use default exports; shared components named exports.
- **Backend:** FastAPI (async) + Motor (async MongoDB driver). **All routes prefixed `/api`.** MongoDB 7.x.
- **Env rules:** Frontend calls backend **only** via `process.env.REACT_APP_BACKEND_URL`. Backend reads Mongo **only** via `MONGO_URL` + `DB_NAME`. No hardcoded URLs/ports/secrets — read from `.env`; omit fallbacks so missing config fails fast.
- **Mongo discipline:** never return raw BSON; use a `PyObjectId` + `BaseDocument` (`to_mongo`/`from_mongo`). `datetime.now(timezone.utc)` (never `utcnow`).
- **Resilience / scale (must-haves):** operates against **~1M+ customers** and a high-volume bills/points ledger with ~40+ managed indexes. Dedicated **POS connection pool** so till ops are never starved by analytics; `primaryPreferred` reads with fast fail-over; capped analytics query times; non-blocking startup/seeding; disk-safe (no 16MB `$addToSet` overflow) aggregations; **end-to-end streamed CSV/XLSX exports** (million-row downloads never crash).

---

## 2. BRANDING — SINGLE-CONFIG REBRAND (the "one file" rule)
Every brand-visible string, contact, colour and asset is driven from **`frontend/src/brand.config.js`** (imported as `BRAND`). To brand for Poppet Jamal:
1. Edit `brand.config.js` values (identity, loyalty copy, contact/legal, operational defaults, colours) — **change values, not field names**.
2. Mirror `<title>`/`<meta>` in `frontend/public/index.html` (build-time, can't read the config).
3. Backend `.env`: `BRAND_NAME`, `BRAND_ADMIN_EMAIL`, `BRAND_ADMIN_PASSWORD`, optional `BRAND_EMAIL_DOMAIN`, `DEMO_USER_PASSWORD`; add the site origin to `CORS_ORIGINS`.
4. Replace the DLT-approved SMS template + Karix sender/entity seeded in `backend/server.py`.
5. Replace hero/boutique/editorial imagery (or via in-app CMS — CMS overrides win at runtime). Add the brand logo to `/public`.
6. **Do NOT rename** CSS class names (`*-text-burgundy`…) or the `--kazo-*` CSS variables (stable selectors across 50+ components) — only change colour **values**.

### `brand.config.js` for Poppet Jamal (fill TODOs with the real brand kit)
```js
export const BRAND = {
  // Identity
  name: "POPPET JAMAL",
  legalName: "Poppet Jamal",
  domain: "poppetjamal.com",                       // TODO confirm
  shortDescriptor: "contemporary fashion brand",   // TODO confirm
  // Platform (loyalty engine stays "Fundle")
  platform: "Fundle",
  poweredBy: "Powered by Fundle",
  aiAssistant: "Fundle Brain",
  platformLogoUrl: "/fundle-logo.png",
  // Loyalty programme
  loyaltyProgramName: "Poppet Jamal Rewards",
  welcomePointsValue: 100,
  welcomeToast: "Welcome to Poppet Jamal Rewards! 100 bonus points credited.",
  ctaJoinFree: "Join Poppet Jamal Rewards Free",
  // Social / SEO / home copy / footer / login copy / contact — same shape as KAZO, swap wording.
  // Operational defaults
  couponPrefix: "PJ",                              // TODO confirm
  posMerchantId: "POPPETJAMAL_FUNDLE",             // TODO confirm
  sms: { senderId: "PJALIN", campaignSenderId: "PJALFN", campaignAccount: "fundle_campaign" }, // TODO: real DLT headers
  // Brand palette — VALUES only (names stay --kazo-*)
  colors: {
    black: "#0A0A0A", cream: "#F9F8F6",
    burgundy: "#TODO", burgundyDeep: "#TODO",      // primary accent + hover
    champagne: "#TODO", champagneLight: "#TODO",   // secondary / luxury hint
  },
};
export default BRAND;
```

---

## 3. AUTH, PORTALS & RBAC
- **Three portals, portal-gated:** CRM/Admin portal, Enterprise login, in-store **Store** portal (store creds cannot reach the admin back-office and vice-versa).
- **JWT + bcrypt** (12-hour tokens, Bearer or HttpOnly cookie); passwords bcrypt-hashed, never logged.
- **Read-only demo mode** enforced at the auth layer (writes rejected except a tiny allow-list).
- **Audit trail:** logins/logouts + every data-mutating action → immutable audit log (actor, action, entity, IP, timestamp).
- **11-role RBAC** (every endpoint + nav item gated):
  `super_admin, brand_admin, crm_manager, marketing_manager, regional_manager, store_manager, store_staff, support_agent, analytics_viewer, readonly_executive, cxo`.
  - **`cxo` (ultra-restricted — IMPORTANT):** may ONLY see **Fundle Brain**, **Master Brain**, and the **Live Bill Monitor**. No dashboards, reports or settings. Keep its whitelist strict in backend RBAC guards and the frontend sidebar.

---

## 4. MODULES (build ALL of these)

### 4.1 Public Loyalty Website (CMS-managed)
Home/landing (brand hero + CTAs), How It Works, Earn Points, Redeem Points, Loyalty Benefits, Rewards catalogue, Referral Programme, Store Locator, About, FAQs, Contact, Privacy, Terms. All copy/imagery/links editable from the admin **Public CMS** (CMS overrides take precedence at runtime).

### 4.2 Store Portal & POS Loyalty (eWards)
Mobile-friendly Store Operations console; customer check & enrolment at billing; **idempotent, crash-safe points earn** per bill (retries never double-credit) with real-time tier eval + last-visit update; **points redemption with OTP**; **coupon redemption at POS** (public + per-mobile single-use mobile-bound coupons); centrally-managed store logins; resilient reads via dedicated POS pool.

### 4.3 Analytics Dashboards (15+, live aggregations, drill-down, click-to-generate AI narrative)
Command Center / Executive Cockpit, Sales MTD, Customer Analytics, Loyalty, Campaign Performance, Store, RFM & Churn, Cohorts, Points Economics, Campaign ROI, Executive Summary, NPS, KPI Trends, New-vs-Repeat (day-wise), Customer Count by Store. Each supports date/zone/city/store filters + drill-down modal to underlying bills + on-demand AI insight (headline, summary, drivers, recommendations). **No stored snapshots** — computed live.

### 4.4 Customer Intelligence
**Customer 360** (identity, tier, points balance/ledger, lifetime spend & visits, recency, monthly-spend chart, category & store affinity, NPS history, AI "Customer Intelligence Report"); lazy-loads heavy analytics; RFM breakpoints precomputed off-path (startup + every 30 min) for sub-second drill-downs at ~1M customers; customer search/list + quick drawer; live RFM segment labels (Champions, Loyal, At-Risk…).

### 4.5 Reports & Exports (finance-grade, reconciled, streamed)
Store KPI (per-store sales/discount/fresh-return bills/new-repeat-mapped-unmapped/ATV/customer counts + YoY + **live reconciliation banner**), Store-wise KPI matrix, Weekly KPI, **CRM Customer Report** (points/billing/visits/recency/**DOB·DOA**/home store, filters, sort, column-select, streamed export — **dates render full month e.g. "08 June 2026"**), Shopper Bill Report (derived New/New-Repeat/Existing + per-bill recency), Raw Reports (Txn/Customer/Repeat/By-Visit), Custom Report Builder, BOPS Reports, Reconciliation (vs raw source file), Formula Catalog (every KPI definition), Downloads Center.
- **Canonical money:** one revenue definition ("Total Paid" = post-discount incl. GST) used across every report/export/dashboard with locked Gross/Net/Point-Base/Total-Paid identities.
- **Real-time recency** ("Days Since Last Visit") from each customer's live last-visit timestamp.

### 4.6 Marketing & Campaign Automation
- **Campaign Manager + 4-step guided wizard** (Objective → Audience → Message → Review & Launch) with per-step validation and **live audience preview**.
- **Objectives:** generic, store, coupon, SKU, **and `points`** — each with its own ROI window + cost input.
  - **Points objective (LATEST):** resolves each recipient's **live `{{points}}` balance** at send time.
  - **Tiered point bands (LATEST):** send a **different template per balance band** (e.g. <500, 500–1999, 2000+).
  - **Expiring-points targeting (LATEST):** audience = members with points expiring within a window.
- **Real ROI attribution engine:** audience **frozen at launch (t0)**; a real transaction join computes converters, conversion %, attributed net revenue, revenue/recipient, ROI% — with Universal / Store-wise / Coupon / Target-SKU breakdowns over selectable windows (72h…30d). **Channel-agnostic** (works for SMS and WhatsApp).
- **Segment Builder:** audiences from any mix of tier/city/points/visits/spend/recency/cohort filters, one-click "Points ≥ N" preset; preview then launch.
- **Marketing Database:** upload/paste an external number list (CSV/Excel); see members vs non-members; campaign to the full list (members personalised).
- **Coupons:** coupon engine + per-mobile **unique coupon batches** (single-use, mobile-bound, validated at POS) with CSV export.
- **Automated campaigns:** rule-based auto-campaigns on a daily schedule; scheduled campaigns auto-fire at set time.
- **Auto-blacklist:** number auto-suppressed after 3 consecutive delivery failures; excluded from all future sends; manual add/remove.

### 4.7 Communications — SMS **and** WhatsApp (Karix / Tanla)
- **DLT-compliant SMS** via Karix: separate **transactional** and **bulk-marketing** pipes, registered sender IDs + DLT entity/template binding. **DLT Content Template ID is mandatory** for a send — if empty the campaign is (correctly) blocked by the DLT compliance guard (NOT a bug).
- **WhatsApp campaigns (Karix RCM / WABA) — FULL parity with SMS (LATEST):** send to **cohorts / Marketing DB / segments / any audience**, with the same ROI + delivery tracking.
  - Create & **approve WABA templates** in Communications → Templates (channel=whatsapp, `waba_template_id`, language, category, variable order, approval status). Launch validates `waba_approval_status == approved`.
  - **Send endpoint:** `POST https://rcmapi.instaalerts.zone/services/rcm/sendMessage` — payload `message.channel="WABA"`, `content.type="TEMPLATE"` with `template.templateId` + `parameterValues`, `recipient.to` (91-prefixed), `sender.from`, `preferences.webHookDNId="1001"`, `metaData.version="v1.0.9"`.
  - **Auth = Bearer token** generated from the account API key: `POST https://tsp.instaalerts.zone/token/generate` body `{"api_key": "<key>"}` → `{"validity": <minutes, 1440=24h>, "token": "<jwt>"}`; use `Authorization: Bearer <token>`. Implement an in-process **token manager**: cache to `validity−5min`, **negative-cache failures ~60s** (so a bulk job never hammers the token endpoint), force-refresh + one retry on a 401. (NOTE: the provider must have the **Public API / TSP feature enabled** for the account, else token gen returns `"Public API is not enabled for user."`.)
- **Message templates** with variable merge — render `{{name}} {{tier}} {{city}} {{points}} {{points_balance}} {{expiry}} {{coupon_code}} {{link}}` per recipient.
- **Bulk send jobs** with progress, per-message logging tagged to the originating campaign, final-status write-back.
- **Delivery receipts (DLR) — channel-aware (LATEST):**
  - SMS webhook `POST/GET /api/communications/dlr/karix`.
  - **WhatsApp webhook `POST/GET /api/communications/dlr/whatsapp`** (register with Karix for `webHookDNId 1001`). Tolerant parser for flat/nested/batched RCM callbacks; statuses map SENT→submitted, DELIVERED/READ→delivered, FAILED→failed; reconcile by RCM `messageId` else by destination within the whatsapp/rcs channel family.
- **OTP delivery** for redemption/verification.
- **Provider Settings UI** for transactional + bulk + WhatsApp credentials (keys masked): Send Endpoint, **Token Endpoint**, Sender number, **API Key**, version; plus a connectivity diagnostic reporting the deployment egress IP for provider IP-whitelisting.

### 4.8 AI Tools — Fundle Brain & Master Brain (via Emergent Universal LLM key / OpenAI-compatible gateway; no provider secrets in code; models swappable)
- **Fundle Brain (analyst):** NL questions → read-only aggregations → answers, tables, charts; narrates uploaded CSV/report files; floating assistant (FAB).
- **Master Brain (executor):** deep-reasoning function-calling that performs data-changing actions via a safe **preview → confirm → audited-execute** pattern; multi-mobile reads batched into one aggregation; wall-clock budget guarantees every streamed turn completes; **correctly maps custom CSV variables** (e.g. `{{coupon_code}}`) when dispatching campaigns from an uploaded list (LATEST fix — no coupon/variable text leakage).
- **Bulk Bonus tool:** award bonus points to an uploaded mobile list with preview + downloadable "not-found mobiles" CSV.
- **Data Health (Quick Wins):** six read-only integrity audits run off-path daily with a summary panel + deep-links to fix.
- **Multi-model selectable:** Anthropic Claude (default), OpenAI GPT, Google Gemini; every call carries an app identifier for cost attribution.

### 4.9 Loyalty Engine & Configuration
Fully **config-driven Loyalty Rules editor** (earn rates, tier thresholds & benefits, category/SKU multipliers, bonus rules, points expiry, card validity — nothing hardcoded); auditable **points ledger** (balances/tiers derived from it); **Points Integrity Center** (detect/repair negative balances, uncredited/partial-commit earns, double redemptions, duplicate adjustments); **Redemption Repair**; coupon engine (public + unique, validity/min-bill/max-discount, enforced at POS).

### 4.10 Data Operations
**Historical data upload** (large txn files + customer post-pass: home store, visits, points, tiers); **Daily Reco** (add only missing bills, idempotent on bill number; manual CSV upload + optional **M365 IMAP/OAuth2 auto-pull**, credential-gated + daily scheduled job); **Item Master** (SKU/category facets); **Stores master** (code/name/class/zone/region/city — dimensions every report); **Verify Load & POS Credentials**; chunked/streamed processing + disk-safe aggregations.

### 4.11 Support
Tickets / Support Desk (create/assign/track/resolve + detail view + status workflow); NPS Inbox (capture/triage feedback → feeds NPS dashboard).

### 4.12 Administration & Monitoring
User Management (roles; store roles require a store assignment); **API Monitor** (every request logged — method/path/status/latency — via pure-ASGI middleware so streaming exports aren't truncated); **Live Bill Monitor** (real-time bills feed — part of the CXO whitelist); Executive Digests (scheduled weekly); health endpoints + async **scheduler** (weekly digests, report ingest, auto-campaigns, RFM refresh, data-health scans, daily reco pull — each logged).

### 4.13 Marketing Media (optional)
Product film `/watch` (narrated cinematic walkthrough, 1080p MP4 w/ real TTS + synced captions); Fundle Reels `/reel` (three 9:16 films positioning the AI loyalty agents).

---

## 5. INTEGRATIONS
| Integration | Purpose |
|---|---|
| **Karix / Tanla (RCM)** | DLT SMS (transactional + bulk), **WhatsApp/WABA send (Bearer-token via TSP)**, OTP, **SMS + WhatsApp delivery webhooks** |
| **LLM gateway (Anthropic / OpenAI / Google)** | Fundle Brain + Master Brain, narratives, TTS — via Emergent Universal LLM key (OpenAI-compatible), no secrets in code |
| **eWards POS** | In-store loyalty: customer check, earn, redeem, coupon validation |
| **Microsoft 365 mailbox (IMAP/OAuth2)** | Optional daily auto-pull of the reconciliation file (credential-gated) |

---

## 6. PLATFORM CAPABILITIES (acceptance signals)
Single-config rebranding (one file drives all branding, FE+BE, zero-code new-brand launch); real-time everything (no stale snapshots/nightly backfills); production resilience (dedicated POS pool, primaryPreferred fail-over, capped query times, non-blocking startup, disk-safe aggregations); scale-tested (~1M+ customers, ~40+ indexes); finance-grade reconciled reports; streamed exports at any scale.

---

## 7. LATEST ADDITIONS TO INCLUDE (delta vs the earlier prompt)
1. **WhatsApp Campaign Manager (Karix RCM/WABA)** — full SMS parity: cohorts/Marketing DB/segments/any audience, ROI + delivery tracking, WABA template create+approve, **Bearer-token auth via `tsp.instaalerts.zone/token/generate`** with cached/negative-cached/401-refresh token manager.
2. **WhatsApp DLR webhook** `/api/communications/dlr/whatsapp` + **channel-aware** DLR ingest (SENT/DELIVERED/READ/FAILED), RCM `messageId` capture.
3. **Points campaign objective** resolving live `{{points}}` per recipient.
4. **Tiered point bands** (different template per balance band) + **expiring-points audience targeting**.
5. **CXO role** — ultra-restricted (Fundle Brain + Master Brain + Live Bill Monitor only).
6. **Master Brain CSV variable mapping fix** (no `{{coupon_code}}`/variable leakage when sending from an uploaded list).
7. **CRM Customer Report full-date format** ("08 June 2026") + robust DOB/DOA handling (null-out values wrongly copied from visit dates; wide date-range Store KPI rewritten to avoid Mongo 16MB overflow).

---

## 8. ROADMAP (build only if asked — keep separate from "current")
Meta / WhatsApp Cloud API + Meta Ads custom-audience (pending Meta creds); location-wise DLT SMS config, reward brands / gift-voucher rewards, expanded OTP audit search; parameterised DLT SMS templates; scheduled backups to object storage; drag-and-drop report builder; MFA + brute-force lockout.

---

## 9. SEED / TEST
Seed a brand admin (`BRAND_ADMIN_EMAIL`/`BRAND_ADMIN_PASSWORD`) + one user per role (incl. a `cxo`). Seed a DLT-approved transactional SMS template + a sample **approved WABA WhatsApp template** for immediate campaign testing. Keep credentials in a `test_credentials.md`. Verify: POS earn/redeem idempotency, a WhatsApp campaign to a small Marketing DB (builds correct RCM payload + lifecycle completes), DLR webhooks (SMS + WhatsApp), ROI attribution, streamed exports at scale, and CXO sees only its 3 allowed screens.
