# INCREMENTAL UPGRADE PROMPT — Fundle CRM/Loyalty platform

> **Purpose:** Apply on top of an existing *cloned* Fundle build (an earlier full-copy
> snapshot) to bring it up to date with everything substantive built since then
> (≈ iterations 57 → 73). Describes **behavior + architecture** (not brand-specific
> data) so it generalizes across brands. Copy the fenced block below into a new
> Emergent project chat, or cherry-pick individual modules per brand.

> **Stack assumed:** React + Tailwind + Shadcn (frontend); FastAPI + Motor/MongoDB
> (backend). Single-tenant. All dates IST/Asia-Kolkata. All config from `.env` only.
> Production runs on an Emergent-managed Mongo with an aggressive per-op `timeoutMS` —
> design every heavy query for scale.

---

```
INCREMENTAL UPGRADE PROMPT — Fundle CRM/Loyalty platform
(Apply on top of an existing cloned build. React + Tailwind + Shadcn frontend; FastAPI + Motor/MongoDB backend. Single-tenant. All dates IST/Asia-Kolkata. All config from .env only. Production runs on an Emergent-managed Mongo with an aggressive per-op timeoutMS — design every heavy query for scale.)

GLOBAL GUARDRAILS (enforce throughout)
- NEVER run .aggregate() on the large transactions/customers collections without: a $match filter, allowDiskUse=True, AND either caching or a bounded page scope. Unbounded scans WILL 500 at production scale (1M+ customers, 1M+ bills).
- Add a `db_deadline` FastAPI dependency that wraps requests in `pymongo.timeout(45)` and attach it to every analytics/dashboard/report router (overrides the aggressive client timeoutMS).
- Every interactive/important element gets a unique kebab-case data-testid.
- After any change, remind the user a REDEPLOY is required for production to reflect it.

1) PRODUCTION-SCALE PERFORMANCE & RESILIENCE
- Consolidate multi-aggregation dashboard endpoints into a SINGLE $facet scan (e.g. Command Center's ~16 queries → ~3 facet scans; KPIs 14 scans → 1 facet+gather; points-economics 8 → 2 facets). Wrap each facet branch in try/except PyMongoError → degrade to empty buckets (HTTP 200 + a `degraded[]` flag) instead of 500. Frontend shows an amber "some data delayed, retry" banner when degraded, never a silent ₹0.
- Add allowDiskUse=True to ALL aggregations.
- Add a TTL cache module (`_dash_cache.py`, ~5 min) on the ~20 heaviest endpoints, with STALE-WHILE-REVALIDATE (serve stale ≤1h instantly, refresh in background). Cache must NOT cache degraded responses. Preserve typed FastAPI signatures (don't break body binding).
- Add a background cache-warmer (`_cache_warmer.py`) that every ~4 min warms the 8 heaviest default views via localhost using a minted super-admin JWT.
- RFM: rewrite with index-backed quantile cuts + $facet bucketing (no Python-side truncation).
- Cohorts/retention: compute the retention triangle Mongo-side via $facet (never pull 500K rows into Python).

2) HISTORIC CSV INGEST SCHEDULER HARDENING (large-file safety)
- Root problem to fix: long post-passes wrote no heartbeat, so a stale-recovery watchdog re-queued still-running jobs → infinite re-run loop.
- Add a `_beat(job_id)` heartbeat written per batch in every post-pass (ledger, points ledger, customer-aggregate recompute, store-link, backfill).
- Widen stale-recovery window (~8 min) + a MAX_RECOVERIES cap (e.g. 4) → a job recovered N× without completing is marked `failed` and chunks cleaned (hard stop).
- Stream chunks to a temp file on disk and read the CSV line-by-line (O(1) memory) instead of decoding the whole file in memory. Recompute aggregates with allowDiskUse + batched flushes + heartbeats. Ingest must be idempotent (upserts) so a redeploy mid-ingest resumes from stored chunks with no data loss.

3) POS EARNING CORRECTNESS (tier-driven loyalty)
- Earn engine: when the global earn rate is blank/0, the PER-TIER multiplier itself IS the % of the bill (mult 2 → 2% of bill, 3 → 3%, 5 → 5%). Preserve base×rate×mult when a global rate IS set. Apply in the SHARED earn function so POS add-point, returns, recalc, the earn simulator and legacy issue-points are all consistent.
- loyalty_flag robustness: EARN unless the POS explicitly sends 0/false/no/off (don't require strict "1"/"true").
- Auto-register: when a POS bill creates a NEW member, fire the "registration"/welcome SMS template (add "registration" to the events list + Templates UI dropdown).
- Earn SMS: fire both "purchase" and "points_earned" triggers on add-point.
- Self-diagnosis: when a bill earns 0 points, record an `earn_skip_reason` in the response AND the API Monitor log: loyalty_flag_off / earn_paused / zero_base / below_min_bill / computed_zero. (Lets users see WHY without server access.)
- Recalc upgrade: dry-run returns a skip breakdown + earn config; add an `ignore_loyalty_flag` (Force-credit) option to backfill bills wrongly stored as flag-off; surface reason + Force-credit in the UI.

4) POS OTP REDEMPTION CORRECTNESS
- UNIFY OTP storage: all POS flows (modern x-api-key/eWards flow AND any legacy /pos/* flow) must read/write ONE canonical `pos_otp_sessions` collection with last-10-digit mobile normalization. (Two collections = OTP issued by one flow can never be verified by the other → permanent "Invalid OTP".)
- Idempotent verify: match the OTP session by mobile+otp+purpose REGARDLESS of verified state; if already redeemed, return the SAME success (already_redeemed:true) WITHOUT deducting again; atomically CLAIM the redemption via find_one_and_update so concurrent duplicates can't double-deduct; only a genuinely unknown OTP is "Invalid". Add precise failure-reason diagnostics.
- On verify, IGNORE the `points` field sent by the POS — take the authoritative amount from the OTP session's payload_snapshot.points (the amount the OTP was issued for). Validate against the MOST RECENT OTP for that mobile (older OTPs rejected once a newer one is issued).
- Block redemption on DISCOUNTED bills: if the POS sends any non-zero discount (bill-level or any line-item, handle "discount"/"Discount" casings), reject with "Redemption is not allowed on discounted items." Enforce at request time (before issuing OTP) AND at verify (defense-in-depth).
- Support Desk: "Search Redeem Points/Coupon OTP" shows the OTP VALUE (for manual redemption when SMS is unreliable) and renders timestamps in IST.

5) SMS / KARIX PROVIDER (config-driven; infra caveat)
- Send EXACTLY the provider's QueryString param set from saved Provider Settings (no dummy/fallback at send time): ver, key, encrpt, dest, send, dlt_entity_id, text. Sender ID from Provider Settings is authoritative (a stale per-template sender cannot override it). fire_event only sends templates whose status == "active".
- Retry connect-level failures only (httpx.ConnectTimeout/ConnectError), up to 4 attempts with small backoff, 8s connect timeout — SAFE (connection never established → no duplicate SMS). Never retry read timeouts. Log "delivered on attempt N/4".
- NOTE for the user: intermittent ConnectTimeout is usually an egress-IP whitelist issue at the SMS provider (rotating egress IPs) — needs a static egress IP/CIDR from Emergent Support, not a code fix.

6) DASHBOARDS & REPORTS AT SCALE
- Fix scale-breakers: replace distinct()+giant-$in, $addToSet>16MB, and datetime-vs-ISO-string comparisons in drilldowns (always compare ISO strings to ISO strings). Cohort drill must use first_purchase_at (not created_at); customer scope must use home_store_id (not a non-existent preferred_store_id).
- Date ranges: ensure every preset (incl. 365d) and custom start/end actually applies; empty category/city → "Uncategorised"/"Unknown".
- Legacy + raw reports: server-side offset pagination (Prev/Next + page X/Y), batch lookups (kill N+1 find_ones), CSV export capped (~10K) on the listing endpoints, error-retry UI, all under db_deadline. Repeat-purchases computed fully Mongo-side; tier filter via cursor aggregation.
- Reconcile endpoint: scale-safe $unionWith anti-join (not distinct()).

7) RECONCILIATION MODULE (/api/recon/*)
- Chunked CSV re-upload → row-level CSV↔DB compare: missing rows, amount mismatches, mobile mismatches, extra-in-DB, and sum totals; downloadable mismatch CSV; a Reconciliation page UI section.

8) AI "BRAIN" ANALYTICS ASSISTANT (data expert + L1 ops agent)
- Inject a cached (~10 min) LIVE DATA-WAREHOUSE SNAPSHOT system message: collections + row counts, bill-date coverage, a brand KPI digest (lifecycle split, tier split, all-time revenue/ATV, top stores 90d), loyalty config, and a DATA PROVENANCE note (e.g. master-CSV-only customers have no bill-level rows → query the customers collection for people-lists).
- Guard-railed READ tools: run_aggregation (read-only pipelines; forbid $out/$merge/$function/$where; cap ~200 rows; require server-side $group/$sort/$limit) and get_data_dictionary (correct function signature!).
- export_csv tool: streams up to ~1M rows to a file (object storage or /app/.../exports), served via an auth-protected GET /api/ai/exports/{id} (202 while preparing, 404 unknown). Chat presents a Markdown download link; UI renders it as a styled download button.
- Role-gated WRITE tools for L1 support (deactivate/reactivate/unsubscribe/resubscribe/reactivate coupon/redeem) with mandatory confirm + reason + audit log.
- Rendering: react-markdown + remark-gfm; a `_markdown_message.jsx` that renders GFM tables/bold/bullets/headings; system prompt MANDATES Markdown tables + ₹ Indian grouping.
- Single locked best agent (remove any model dropdown). Decisiveness rules: never ask clarifying questions before a READ/data pull (state assumption + execute); never data:/base64/copy-paste CSV hacks (export_csv is the only file channel); ≤1 dictionary call; fix-and-retry-once on pipeline errors; on tool-loop cap force a final synthesis answer (table + export link), never "reached limit".
- items[] schema hints: items is an array of {sku,name,category,quantity,total}; use $size for per-bill item count, $unwind for item analysis.
- TIMEZONE RULE (critical): when grouping/displaying any date from bill_date/created_at/last_visit_at, format in IST via $dateToString/$dateTrunc with timezone "Asia/Kolkata" — NEVER string-slice the raw value (it may be UTC → off-by-one near midnight, mismatching the dashboard).

9) NEW: SHOPPER BILL REPORT (bill-level report, under REPORTS)
- One row PER BILL for everyone who shopped in a date range. 22 columns: Bill Date, Bill Time, Bill Type (Return/Regular; treat Exchange as Return), Customer Mobile, Reg Store (CRM registration store), Store Code, Trans Store Name, Trans ID, Bill #, Customer Type (New/Existing), Recency, Last Visit, 2nd-last Visit, Total Visits, Zone, Customer City, Net before tax, Total Tax, Total Discount, Total Bill Amount, Lifetime Purchase, Lifetime Bill Cuts (NET = sale bills − return bills).
- Recency from TODAY back to last visit: Active 0-6M / Dormant 6-12M / Lapsed 12M+.
- Backend (two routers): GET /shopper-report/bills (paginated listing), GET /shopper-report/filter-options (stores+zones), and a SEPARATE export router GET /shopper-report/export (streamed CSV, NO db_deadline so big exports stream; wrap per-batch enrichment in its own pymongo.timeout; cap ~200K rows).
- Scale-safe: non-recency path = indexed find on bill_date + page-scoped enrichment (customer lookup + a bounded per-mobile aggregate for 2nd-last-visit & net bill cuts + store-master preload). Recency path = sort-FIRST (index-backed) → indexed point $lookup to customers → bucket $match → $limit (short-circuits; no full-set $facet/count) with maxTimeMS guard → friendly 400 if too heavy; omit exact total (use has_more). Render all dates in IST.
- Frontend page: date range + quick presets (7d/30d/90d/MTD/1y), filters (bill type, customer type, recency, store, zone, city, search), clickable sortable headers, 50/100/200 page sizes, Prev/Next, colored Bill-Type & Recency badges, Download CSV.

10) EXACT MONEY FORMATTING + IST DATES (display layer)
- Add fmtMoney2(n): Indian commas, ALWAYS 2 decimals, NO Cr/L/K compaction, sign-aware, "—" for empty. Use it in EVERY report/table/detail/drill-down/live-monitor amount cell (never round to whole rupees or compact in tabular contexts). Make fmtINRFull (tooltips) exact 2-dp too. Keep fmtINR (Cr/L/K compaction) ONLY for dashboard KPI tiles.
- Add fmtDateISO(s)/fmtDateTimeISO(s): parse tolerantly (ISO + day-first + naive=IST) and render in Asia/Kolkata as YYYY-MM-DD / YYYY-MM-DD HH:MM. Replace all raw .slice(0,10/16) date cells in reports with these so report dates match the dashboard (fixes off-by-one for late-night bills).

11) INDEXES (ensure on startup)
- transactions: bill_date, customer_mobile, city, store_name. points_ledger: bill_date. message_log: created_at. customers: mobile (lookup), lifetime_spend, first_purchase_at, last_visit_at.

12) TESTS
- For each module, add a pytest under /app/backend/tests covering the API contract + scale-safe behavior, and run the testing agent for end-to-end (backend + frontend) before declaring done.
```

---

## Notes for whoever applies this
- These increments assume the base clone already has: auth, the loyalty configurator, POS
  integration endpoints, dashboards, legacy/raw report shells, the AI Brain shell, and the
  historic CSV ingest pipeline. If a module doesn't exist yet in a given clone, build the
  base first, then layer the increment.
- Loyalty math (tier-driven %) and the "redemption blocked on discount" rule are
  brand policy — keep them configurable so other brands can change thresholds/rules.
- Everything is verified to work at ~1M+ customers / ~1M+ bills scale. Don't drop the
  scale guardrails (caching, db_deadline, allowDiskUse, facet consolidation).
- After applying, REDEPLOY for production to reflect the changes.
