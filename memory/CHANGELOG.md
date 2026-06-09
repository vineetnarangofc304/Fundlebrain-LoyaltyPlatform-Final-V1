# CHANGELOG — KAZO Fundle Platform

(PRD.md holds the full problem statement, architecture, data rules and history.
This file appends what was implemented, newest first.)

---

## 2026-06-09 — Scheduler hardening + Customer 360 fix + Live Monitor numbers

### P0 — Historic ingest scheduler no longer hangs/loops on 126MB+ CSVs
File: `backend/routes/historic_routes.py`
- Root cause of "job lies in queue forever": long post-passes (opening-balance ledger,
  points ledger, customer-aggregate recompute, registered-store link, auto-backfill)
  wrote NO heartbeat, so the 3-min stale-recovery watchdog kept re-queueing the still-
  running job → it re-ran the whole file endlessly.
- Added `_beat(job_id)` heartbeat helper; every post-pass now beats per batch.
- Stale-recovery window widened to 8 min + **recovery cap (MAX_RECOVERIES=4)**: a job
  recovered 4× without completing is marked `failed` (chunks cleaned) — hard stop to the
  re-run loop.
- Memory: `process_pending_ingests` now **streams chunks to a temp file on disk** and
  `_run_ingest_job(csv_path=...)` reads the CSV line-by-line (O(1) memory) instead of
  joining the whole file into a ~2-4× in-memory decoded string (OOM risk). xlsx still
  stitched in-memory (small). `_recompute_customer_aggregates` now streams the aggregate
  with `allowDiskUse=True` + batched flushes + heartbeats.
- Regression test: `backend/tests/iteration57_scheduler_streaming_test.py` (PASS).
- NOTE: production already redeployed with this; a redeploy mid-ingest auto-resumes from
  stored chunks (idempotent upserts; no data loss).

### Customer 360 — search hung + detail page blank (FIXED)
- `backend/routes/fundlebrain_routes.py::customer_360_v2` queried transactions/points_ledger
  by `customer_id` — which is NULL on bulk-loaded (historic) bills and is NOT indexed →
  6 collection scans over 8.6L txns → timeout → blank page. Now queries by indexed
  `customer_mobile` (the canonical loyalty identity). NPS kept on customer_id (tiny coll).
- `backend/routes/customers_routes.py::list_customers` replaced unanchored
  `/{q}/i` regex (full COLLSCAN at 1.1M) with **anchored mobile-prefix regex** (uses the
  `{mobile:1}` index) for digit queries, anchored prefix for name/email, bounded count
  (`maxTimeMS`) and search-mode sort by mobile. `award/deduct-points` now persist
  `customer_mobile` on the ledger entry.
- `frontend/.../CustomerDetail.jsx` "View all transactions" drilldown now filters by
  `customer_mobile`.
- Verified: customer 6000535682 (id a26865d9...) shows ₹2980 lifetime, 2 visits, 2 bills.

### Live Monitor (`/admin/live-monitor`)
File: `backend/routes/live_monitor_routes.py`, `frontend/.../LiveMonitorPage.jsx`,
`backend/routes/pos_ewards_routes.py`
- **Default window = Today (IST 00:00→23:59)**; all relative windows (15m…365d) remain.
- **Store cards fixed**: excluded null-store group (was an "Unknown −₹2,957" card from
  returns); revenue = SALES only (returns split into a `returns` count); each card shows
  the store **LOC code** badge resolved from the store master.
- **LOC code** now resolves from the store master in the bills table + cards; live POS
  bills now persist `store_code` natively (pos_ewards txn_doc).
- **Row colour-coding** by bill type with a legend: Repeat=emerald, New=amber,
  Walk-in=rose, Return=orange.
- **KPI definitions**: `Total Purchase` = GROSS SALES (`gross_amount`, returns excluded);
  new `loyalty_revenue` = `Loyalty Purchase` = gross of bills where points were given
  (`points_earned>0`, returns excluded). Total ≥ Loyalty (subset) always holds.

### Validation
- testing_agent iteration_23: 7/7 acceptance criteria + 7/7 backend pytest PASS, no issues.
- Test: `backend/tests/iteration58_customer360_livemon_test.py`.

### Open / next
- Confirm whether Total Purchase = gross sales & Loyalty Purchase = points-given should
  also be applied to Command Center / Sales dashboards (currently only Live Monitor).
- P2: React `<span> in <option>` hydration warning (source NOT in `_date_range_picker.jsx`
  — that uses buttons; needs locating).
- P1 backlog: Gap-analysis Phase 2/3 (Location-wise DLT SMS, OTP audit search, Reward
  Brands, Reward GVs); modularize bloated route files.
