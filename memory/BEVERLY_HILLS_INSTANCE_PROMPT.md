# Build Prompt — Beverly Hills instance (beverlyhills.fundlebrain.ai)

> Use in a NEW Emergent project. First import the source repo, then rebrand + fresh DB.
> GitHub: **vineetnarangofc304 / Fundlebrain-LoyaltyPlatform-Final-V1**
> (Connect this repo to the new project so it starts from the full, latest codebase.)

---

Create a new **single-tenant** instance of this existing platform for the brand **"Beverly Hills"**,
served at **beverlyhills.fundlbrain.ai**. Start from the current GitHub repo — do NOT rebuild from
scratch. Keep **100% of the existing functionality** (listed below); only re-brand and point it at a
fresh, empty database.

## 1. Rebrand KAZO → Beverly Hills (config-driven — do NOT rename CSS classes or `--kazo-*` vars)
Follow the documented rebrand checklist in `frontend/src/brand.config.js`:
1. `frontend/src/brand.config.js` — set `name`, `legalName`, `domain`, `shortDescriptor`,
   `loyaltyProgramName` ("Beverly Hills Rewards"), welcome copy, social links, `meta`, `homeCopy`,
   `footerTagline`, `loginCopy`. Keep `platform: "Fundle"`, `aiAssistant: "Fundle Brain"`.
2. `frontend/src/index.css` — swap ONLY the hex VALUES of the `--kazo-*` palette variables to the
   Beverly Hills palette (keep the variable names). Palette: «give me your brand colours, or I'll
   propose a Beverly Hills luxury palette».
3. `frontend/public/index.html` — update `<title>` + `<meta>` tags (build-time, can't read the config).
4. `backend/.env` — set `BRAND_NAME` and the super-admin / brand-admin emails to Beverly Hills values.
5. Replace hero / boutique / editorial imagery (Unsplash URLs in brand.config or upload via the
   in-app Public Site CMS after login). Add the Beverly Hills logo asset.
6. Regenerate the tech-overview PDF via `backend/gen_tech_doc.py` if the client needs a branded copy
   (already parameterised; just swap the brand string + logo).

## 1b. What's now config-driven (post-refactor) vs. still manual
After the config refactor, **every user-facing brand string lives in `frontend/src/brand.config.js`**
(name, loyalty/program copy, domain, audience descriptor, region, store-count line, legal entity,
head office, support phone, coupon prefix, POS merchant id, SMS sender IDs, hero/meta copy, colours).
Public pages, the store portal, the admin console and the `/demo` tour all read `BRAND.*`. So editing
`brand.config.js` rebrands the whole app UI in one place.

**Still manual per brand (cannot read the JS config):**
- `frontend/public/index.html` — `<title>` + description/keywords/OG meta (build-time static).
- `frontend/src/index.css` — swap the `--kazo-*` colour VALUES (keep the names) OR just set them in
  `brand.config.js.colors` (injected at runtime via App.js). Prefer brand.config.
- `backend/.env` — `BRAND_NAME`, `BRAND_ADMIN_EMAIL`, `BRAND_ADMIN_PASSWORD`, optional
  `BRAND_EMAIL_DOMAIN` + `DEMO_USER_PASSWORD` (seed logins), fresh `JWT_SECRET`, and add the new site
  origin to `CORS_ORIGINS` (regex already allows `*.fundlebrain.ai`).
- `backend/server.py` — replace the seeded "KAZO End of Season Sale" DLT template with the new brand's
  Karix-registered sender/entity/template + exact approved body (DLT content is inherently per-brand).
- Add the brand logo asset(s) in `/public`.
- (Optional cosmetic: `raw_reports/_shared.jsx` `KAZO_PALETTE` chart colours are brand-independent
  categorical colours — leave unless you want them tied to the brand palette. A few code comments
  still say "KAZO" — invisible, harmless.)

## 1c. CORS + domain (WILL block the app if wrong)
`server.py` allows `*.fundlebrain.ai` (with an "e"). The requested `beverlyhills.fundlbrain.ai`
(no "e") will FAIL CORS. Either use **beverlyhills.fundlebrain.ai**, or add the exact new origin to
the CORS allow-list + regex in `server.py`. Also remove/replace the KAZO-specific hostnames there.

## 2. Fresh single-tenant data
- New empty MongoDB (its own `DB_NAME`); keep the idempotent startup seeds (admin user + any DLT
  template seed) but seed them with **Beverly Hills** values, not KAZO.
- No KAZO demo/customer data should carry over. Keep the ~43 startup indexes.

## 3. Per-brand integrations to (re)configure — collect fresh credentials
- **Karix / Tanla SMS+WhatsApp** (transactional + bulk/campaign): new API keys, **Sender ID**,
  **DLT Entity/PE id** and **DLT-approved template IDs + bodies** for Beverly Hills. Whitelist this
  deployment's egress IP with Karix.
- **Microsoft 365 IMAP** (optional daily reconciliation auto-pull) — only if the brand uses it.
- **Meta WhatsApp Cloud API / Meta Ads** (optional, Phase 5) — brand's own keys.
- **LLM** — uses the Emergent universal key automatically (Anthropic Claude, OpenAI GPT, Google
  Gemini via LiteLLM). No provider keys needed.
- **POS e-wards** endpoints — point the brand's POS at this instance's `/api` loyalty endpoints.

## 4. Preserve ALL current functionality (single tenant, real-time Mongo aggregations, no dummies)
Backend = FastAPI + Motor (MongoDB) + JWT/cookie auth + APScheduler + LiteLLM. Frontend = React 19 +
Tailwind + shadcn + Recharts + Framer Motion. All routes under `/api`.

**DASHBOARDS:** Command Center, Sales, Customer Analytics, Loyalty, Campaign Performance, Store,
RFM & Churn, Cohorts, Points Economics, Campaign ROI, Executive Summary, NPS — all with drill-downs.

**CUSTOMERS:** Customer 360 (search, profile, tier, points ledger, transactions, drill-downs).

**MARKETING:**
- Campaign Manager with a 4-step guided **Wizard** (Objective → Audience → Message → Review/Launch),
  live audience preview, scheduling (auto-fire due campaigns), real ROI, delivery report modal,
  auto-blacklist / suppression.
- **Segment Builder** — RFM, tier/city/cohort filters + "Quick: Points ≥ N" presets.
- **Marketing Database** — build external audiences by paste OR CSV/Excel upload (mobile auto-detect),
  member vs non-member split, per-mobile **personalisation variables** (name/points/expiry/link),
  "Run campaign on this dataset".
- **Coupons** — bulk coupons + **unique per-mobile** coupon batches (mobile-bound, single-use at POS).
- **Auto Campaigns** (trigger-based).

**COMMUNICATIONS:** SMS **Templates** (DLT-compliant, variable merge `{{name}} {{points}} {{expiry}}
{{link}} {{tier}} {{city}} {{points_balance}} {{coupon_code}}`), **Bulk Send Jobs**, **Message Log**
with Karix **DLR** delivery tracking, **Provider Settings** (separate transactional + bulk/campaign
Karix accounts).

**AI TOOLS:** **Fundle Brain** (function-calling analytics assistant + CSV narration) and
**Master Brain** (deep-reasoning, action-enabled campaign execution via preview → confirm →
audited-execute; role-gated, reversible).

**DATA:** Historical Upload, Reconciliation / Daily Reco, Verify Load.

**OPERATIONS:** Stores, Item Master, API Monitor (per-request method/path/status/latency + `/db-info`),
Points Integrity, Redemption Repair.

**SUPPORT:** Tickets, NPS Inbox, and Support Desk tools (deactivate/reactivate customer, reactivate
coupon, reactivate/redeem points, search redeem coupon/points by OTP, unsubscribe, update mobile,
audit log).

**REPORTS:** Store KPI (reconciled: New + Repeat + Unmapped + Returns = Overall), CRM Customer (with
Home Store), Shopper Bill (derived customer type), KPI Trends, Weekly / Store-wise KPI, New vs Repeat
Daywise, Legacy Reports Hub (customer/transaction/repeat/top/fraud/pending bills/feedback/missed
calls/location-wise/expiry points/active coupons/occasions), Raw Reports, Reports & Exports,
async **Downloads Center** (object-storage exports, 7-day retention), Exec Digests, Formula Catalog.

**CONFIGURATION:** Loyalty Rules (tier rules, earn/burn, re-tier tool), Public Site CMS, POS Credentials.

**ADMINISTRATION:** User Management with **10-role RBAC**.

**PUBLIC SITE + PORTALS:** marketing site (Home, About, How It Works, Earn/Redeem, Rewards, Benefits,
Referral, Store Locator, FAQs, Contact, Privacy, Terms), Store portal (StoreOps), Watch/Reel demo.

**SECURITY:** JWT (HS256) + bcrypt, 10-role RBAC, portal gating (store vs CRM), immutable audit log,
API monitor, env-only secrets (fail fast), CORS allow-list, read-only demo mode.

## 5. Acceptance
- Site + CRM login load at the new domain with Beverly Hills branding (no "KAZO" anywhere).
- Fresh empty DB; a Beverly Hills super-admin can log in (seeded).
- All modules above are present and functional against real Mongo data.
- SMS/campaign sends work once Beverly Hills Karix creds + DLT templates are added and the egress IP
  is whitelisted.

> Note: confirm the domain spelling — the platform prod domain elsewhere is `fundlebrain.ai`
> (with an "e"); you wrote `fundlbrain.ai`. Use whichever is correct for the DNS you own.
