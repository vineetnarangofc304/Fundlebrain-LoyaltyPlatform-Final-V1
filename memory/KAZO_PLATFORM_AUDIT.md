# KAZO / FundleBrain — Platform Audit (Functional · Data · UX)

_Date: 16 Jun 2026 · Author: E1 · Scope: live production (kazoloyalty.fundlebrain.ai) + preview codebase._

> **How to read this:** Part A = the exact issues you reported, with root cause and fix status.
> Parts B/C/D = the broader functional, data and UX/product audit you asked for. Part E = a
> prioritised action list. Items marked **[VERIFY ON PROD]** depend on real production data and
> should be confirmed once the fresh build is live (the preview DB is customer‑heavy but has almost
> no transactions, so production‑scale numbers cannot be reproduced in preview).

---

## PART A — Your reported issues: root cause + fix status

| # | Issue | Root cause | Fix (this session) | Status |
|---|-------|-----------|--------------------|--------|
| A1 | 7 dashboards stuck permanently on "Loading…" (Command Center, Sales, Loyalty, Store Performance, RFM & Churn, Cohorts & Segments, Executive Summary) — while Points Economics, Customer Analytics, Campaign Perf/ROI loaded | Those 7 used only an **in‑process** cache (wiped on every restart / new pod). After each redeploy, the first viewer on a cold pod triggered a **live full‑collection scan on the request path**; at production scale this never returned in time. The frontend axios client had **no timeout**, so the spinner spun forever instead of erroring. The working dashboards were already backed by **persistent Mongo rollups**. | (1) Added a **persistent Mongo L2 cache** (`dash_cache_l2`) behind the in‑process cache — cold pods now serve the last computed value instantly and revalidate in the background. (2) A **one‑shot startup seeder** pre‑computes every dashboard's default view ~45s after boot, so even the first post‑deploy viewer waits 0s. (3) A **60s client timeout** on every dashboard load → a slow call now shows **error + Retry**, never an infinite spinner. | ✅ Fixed, verified on preview (cold‑pod dashboards now 0.15–0.2s; testing agent 11/11 render, 0 stuck). **Live after deploy.** |
| A2 | "High‑risk churn: 0" (clearly wrong) | `customers.churn_risk` is a **static stored field**. It was only ever set to the default `"low"` at signup (or randomly in seed data) — **nothing ever recomputed it from behaviour**. So every real ingested customer stayed `"low"` → high‑risk = 0. | Added a background **churn recompute** job (daily 06:00 IST + a deferred one‑time run after each boot, idempotent). Definition (recency of last purchase): **≤90d → low · 91–180d → medium · >180d → high · never purchased → unscored**. | ✅ Fixed (recomputed 800k customers on preview). **Confirm the definition suits you — see C3.** |
| A3 | ~9.83 lakh customers with blank / "unidentified" city (₹320 cr sitting under it) | Imported/legacy customer records have no `city`; it was never derived. Analytics groups by `customers.city`, so all blanks collapsed into one giant bucket. | Added a background **city backfill**: a customer's **default city = the city of the store of their FIRST bill** (their home store), and it never changes if they later buy elsewhere (your rule). Blank cities are filled from that home store's city; for the residual with no home store on file, we derive it from the earliest bill. Only blank cities are ever filled — an existing city is never overwritten. | ✅ Fixed (machinery verified). **Production impact visible after deploy + the first daily/startup run.** |

---

## PART B — Functional audit (screens · filters · calculations · exports · workflows)

| ID | Area | Finding | Severity | Recommendation |
|----|------|---------|----------|----------------|
| B1 | Dashboard deep‑links | Sidebar routes use slugs like `/admin/dashboards/customers`, `/campaigns`, `/stores`, `/points`. External/doc/email links using the "logical" names (`customer-analytics`, `store-performance`, `points-economics`) **404 → silently land on the marketing home page**. | Med | Add redirect aliases for the intuitive slugs so shared links never drop users. |
| B2 | Empty vs loading vs error states | Period‑scoped dashboards legitimately return **0 / empty** when there's no data in the selected window, but the UI can look "blank" and be mistaken for broken. Loading copy also varies per page ("Loading…", "Computing RFM…", "Generating executive summary…"). | Med | Add a distinct **"No data in this period"** empty state (with a "widen range" hint), separate from loading and from the new error+retry state. |
| B3 | Two churn definitions | Customer Analytics churn (stored `churn_risk`, now recency‑based) and the RFM & Churn dashboard's churn buckets (computed live from RFM recency) are **two different code paths**. They are now broadly aligned but can still differ at the margins. | Med | Pick **one** canonical churn definition + label and use it in both places (and in Segment Builder / campaign cohorts, which filter `churn_risk`). |
| B4 | Store KPI reconciliation (your earlier Point 5) | Already reconciled: **Overall Sales = New + Repeat + Unmapped + Returns** ties exactly. The residual confusion is **terminology** — "Overall Sales" (all mapped + walk‑in + returns) vs "Total Loyalty Sales". | Low (math) / Med (clarity) | Keep a **persistent on‑screen legend/tooltip** on the reconciliation banner defining each column, so the identity is self‑explanatory. |
| B5 | Reporting surface duplication | There are many overlapping reporting screens: Dashboards (×12), Reports (Legacy), Raw Reports, Shopper Bill Report, Store KPI, Store‑wise KPI, Weekly KPI, KPI Trends, BOPS reports, plus Legacy Reports hub. Users must learn which one answers which question. | Med‑High | Consolidate into a smaller set with a clear taxonomy (Operational vs Analytical vs Compliance), or add a "which report should I use?" index. |
| B6 | Exports | Most CSV/PDF exports work and already set long per‑call timeouts (300s); a few paths use a raw `fetch` instead of the shared client (auth handled manually). | Low | Standardise all downloads on the shared client for consistent auth/retry; **[VERIFY ON PROD]** large exports complete within the ingress limit. |
| B7 | Filter default inconsistency | Some dashboards default to **All‑time** (RFM, Cohorts, Loyalty, Customer), others to **30 days** (Command Center, Sales, Store, Executive). This makes the same "period" control mean different things across pages. | Low‑Med | Standardise the default period (or clearly show the active period on every page header). |

---

## PART C — Data audit (discrepancies · mappings · unreliable metrics · reconciliation)

| ID | Metric / field | Finding | Severity | Recommendation |
|----|----------------|---------|----------|----------------|
| C1 | **Zero‑bill customers = 58.9% (~6.0 lakh)** | This is the single most important data question. It is **either** genuine (mass enrolments — campaigns/uploads — that never purchased) **or** a **linkage bug** (their purchases exist but are attributed to a different mobile format / not joined to the customer record). On preview only 26 such customers exist, so this cannot be reproduced here. | **HIGH** | **[VERIFY ON PROD]** Sample ~50 zero‑bill mobiles → search `transactions` for the same number under alternate normalisations (leading 0 / +91 / 91 / 10‑digit) and by name. If matches are found under a different mobile form, the fix is a **mobile‑normalisation + re‑attribution backfill**; if not, they are truly non‑purchasers and the metric is correct. |
| C2 | City attribution | Now derived from the **first‑bill (home) store**. Depends on `home_store_id` being populated. Any customer whose bills carry no `store_id` cannot get a city; a small residual will remain "Unidentified". | Med | Run the data‑quality job after deploy; then review the residual "Unidentified" count and whether those bills should carry a store. |
| C3 | Churn `churn_risk` — never‑purchased handling | We set never‑purchased customers to **"unscored"** (excluded from low/med/high) so "high‑risk churn" means *lapsed buyers*, not un‑activated enrolments. You may instead want them counted as "high" (activation risk). | Med | Confirm the preferred treatment; one‑line change either way. |
| C4 | Recency thresholds are inconsistent across modules | Command Center churn cutoff = **180d**; Customer health = **30/90/180d**; Shopper Bill recency = **182/365d** (Active/Dormant/Lapsed); new churn_risk = **90/180d**. Same concept, different numbers → different screens disagree on who is "lapsed". | Med | Define **one canonical recency band config** (e.g. in Loyalty Rules) and reference it everywhere. |
| C5 | `lifetime_spend` accumulator basis | Per PRD, display/report revenue was unified to canonical **"Total Paid"** (post‑discount, incl. GST), **but the `lifetime_spend` accumulator that drives RFM Monetary, cohort spend‑bands and TIER assignment is still pre‑tax.** So a customer's tier/segment may not match their "Total Paid" spend. | Med | Decide whether to re‑base `lifetime_spend` to Total Paid (will shift some tiers/segments) + backfill; deferred pending your sign‑off (noted as an open item in PRD). |
| C6 | Points liability | Command Center shows outstanding points → INR liability. Confirm the conversion rate/definition matches finance's expectation. | Low | **[VERIFY ON PROD]** Reconcile the liability figure with a manual points×rate check. |
| C7 | DOB / DOA | Prior repair nulled ~220k DOB/DOA values that had been mis‑filled with a visit date; ingest now guards against it. | Resolved | No action; monitor future uploads. |

---

## PART D — UX & product audit (navigation · usability · terminology · duplication · config)

| ID | Area | Finding | Severity | Recommendation |
|----|------|---------|----------|----------------|
| D1 | Terminology sprawl | "Overall Sales", "Total Loyalty Sales", "Net", "Gross", "Total Paid", "Point Base" all appear without an in‑app definition. This is the root of the recurring "sales don't match" confusion. | Med‑High | Add an in‑app **glossary / info‑tooltips** on every money figure, sourced from the locked definitions already documented in code (`_money.py`). |
| D2 | Navigation density | The sidebar has ~12 sections and 40+ screens. New users struggle to find the right report (see B5). | Med | Group by task, add search, and surface the 5–6 most‑used screens as "pinned". |
| D3 | Configuration complexity | Provider settings split transactional vs campaign/bulk SMS, DLT templates, sender/PE IDs, loyalty rules — powerful but steep, and mis‑config silently drops SMS. | Med | A **guided setup wizard** + inline "why this matters" help, and a **pre‑flight check** that flags a template whose body doesn't match an approved DLT template before launch. |
| D4 | Feedback on long operations | Now that dashboards can't hang forever, ensure every long op (exports, ingest, campaign launch) shows progress + a clear terminal state. | Low | Audit each long‑running workflow for an explicit success/failure toast. |
| D5 | Consistency of states | Error state is now standardised (`DashboardError` + Retry); loading and empty states still vary. | Low | Standardise loading + empty state components (see B2). |

---

## PART E — Prioritised recommendations

**P0 — do next (data trust):**
- **C1** Investigate the 58.9% zero‑bill population on production (real vs mobile‑linkage bug). This underpins every customer metric.
- **A1/A2/A3** Verify on the live site post‑deploy: the 7 dashboards load, high‑risk churn is non‑zero and sensible, and the blank‑city bucket has collapsed.
- **C3** Confirm the never‑purchased churn treatment ("unscored" vs "high").

**P1 — soon (consistency & correctness):**
- **C4** One canonical recency band config used everywhere.
- **C5** Decide on re‑basing `lifetime_spend` to Total Paid (tier/segment impact) + backfill.
- **B1** Dashboard route aliases.
- **B5** Consolidate the overlapping reporting screens.
- **B3** Unify the two churn definitions.

**P2 — polish:**
- **D1** In‑app money glossary/tooltips.
- **D3** Guided provider/DLT setup + pre‑flight SMS check.
- **B2/D5** Standardise empty/loading states.

---

### Note on scope
A literal line‑by‑line audit of all 40+ screens and 60+ backend route modules is a larger engagement; this report prioritises the highest‑impact functional, data and UX findings surfaced by your report + a code/architecture review. Tell me which area to **deep‑dive next** (e.g. the reporting‑surface consolidation, or the zero‑bill linkage investigation) and I'll produce a screen‑by‑screen breakdown for it.
