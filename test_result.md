#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: |
  User (production) reported for customer 9899533604 (omkar patil): the "Earn · burn timeline"
  (points ledger) shows "No ledger entries", the customer should have 68 points but Points
  Balance shows 0, and a RETURN bill happened but is not showing on the profile.

backend:
  - task: "POS returnOrder writes a fully-attributed reversal ledger row (customer_mobile + bill_number + ledger_kind)"
    implemented: true
    working: "NA"
    file: "routes/pos_ewards_routes.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: |
            ROOT CAUSE (reproduced in preview): the /api/pos/returnOrder reversal ledger row was
            inserted with ONLY customer_id — no customer_mobile, no bill_number, no ledger_kind.
            This violates the iter-106 rule "every ledger write must carry customer_mobile". Effect:
            the return (burn) is INVISIBLE on every mobile-keyed read — the /customer-by-mobile
            profile endpoint and all mobile-keyed reports/tools query points_ledger by
            customer_mobile ONLY. FIX: capture the RET- bill number once, attach it + customer_mobile
            + ledger_kind:"return" + original_bill_number to the reversal ledger row. Verified via
            tests/repro_return_ledger.py: after a purchase(+earn)+return, "LEDGER by customer_mobile
            ONLY" went 2 -> 3 (the return row is now visible by mobile), balance math correct
            (2100 earn -> 1300 after -800 return).

frontend:
  - task: "Customer 360 'Last 10 bills' renders return rows correctly (sign + RETURN pill)"
    implemented: true
    working: "NA"
    file: "pages/admin/CustomerDetail.jsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: |
            The Pts+ column hardcoded "+{points_earned}" which rendered a return as "+-68". Fixed to
            show the correct sign (rose colour for negative) and a "RETURN" pill next to the bill#.

metadata:
  created_by: "main_agent"
  version: "1.1"
  test_sequence: 93
  run_ui: true

test_plan:
  current_focus:
    - "POS returnOrder writes a fully-attributed reversal ledger row (customer_mobile + bill_number + ledger_kind)"
    - "Customer 360 'Last 10 bills' renders return rows correctly (sign + RETURN pill)"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: |
        Please verify the purchase -> return -> profile flow end-to-end against the live preview POS
        endpoints. Steps:
        1) POST {BASE}/api/pos/posAddPoint with header x-api-key: ZFQWql7I3vCH0ckuWmA8zVKDDJWYPBtoQGLruEnRrFI,
           body merchant_id "KAZO_FUNDLE", customer_key "K00055", a NEW test mobile (e.g. 9812345670),
           transaction {number:"QATEST-<unique>", amount:2000, net_amount:2000, taxes:[]}. Expect 200
           with points_earned > 0 and new_balance credited.
        2) POST {BASE}/api/pos/returnOrder same headers, body merchant_id/customer_key, mobile (same),
           transaction {number:"QATEST-<same>", return_amount:-800, return_net_amount:-800,
           return_loyalty_gross_amount:-800}. Expect 200.
        3) GET {BASE}/api/dashboard/customer-360/<customer_id> (login superadmin@fundle.io / Fundle@2026
           to get a token). Verify: points_ledger contains BOTH an "earn" row and an "adjust"/return row
           (the return row MUST have customer_mobile set and a bill_number starting "RET-");
           recent_transactions includes the RET- bill with is_return true; balance reflects earn minus
           the reversed points.
        4) ALSO GET {BASE}/api/fundlebrain/customer-by-mobile/<mobile> (this endpoint queries ledger by
           customer_mobile ONLY) and confirm the return/adjust row now appears there too (this is the
           core regression — it was invisible before the fix).
        Clean up the test customer/mobile afterward if possible. This is BACKEND-focused; a light
        frontend smoke of the Customer 360 page (superadmin) to confirm no render errors is a plus.

# ==== Iteration 94: Correct negative balances -> restore TRUE value (not 0) ====
backend:
  - task: "fix_negative_balances restores TRUE balance (current + duplicate-redemption excess, floored 0)"
    implemented: true
    working: "NA"
    file: "routes/master_brain_tools.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: |
            Points Integrity Center Issue D previously hard-reset negatives to 0, losing points the
            customer legitimately had. New behavior: target = max(0, current_balance + points wrongly
            deducted by DUPLICATE redemption rows). New helpers _dup_redemption_excess (groups negative
            non-master_brain ledger rows by bill_number|reference_id + amount; excess = (count-1)*|pts|)
            and _neg_balance_targets. Both single (mobile) and bulk paths updated; compensating adjust
            ledger row written; audited + snapshotted (UNDOABLE). Endpoints POST
            /api/points-integrity/negative-balances/{preview,apply} (require_master_admin). Self-verified:
            dup case -60->20, genuine over-redeem -20->0.

agent_communication:
    - agent: "main"
      message: |
        VERIFY iteration 94 (Master Admin masteradmin@fundle.io / Master@2026; panel is master-only):
        1) SINGLE preview+apply for a duplicate-redemption customer -> true POSITIVE balance (NOT 0),
           compensating adjust ledger row written, re-preview shows nothing to fix.
        2) SINGLE genuine over-redemption (no dup) -> floored to 0.
        3) BULK preview (omit mobile) returns customers_affected, points_to_restore,
           customers_with_duplicates + per-customer sample (points_balance -> true_balance); BULK apply corrects.
        4) UNDO the apply (capture audit_id) and confirm the balance reverts to the original negative.
        Seed throwaway negative customers (e.g. 9700000011/12) with ledger rows and CLEAN UP after.
        Backend-focused; light frontend smoke of /admin/points-integrity Issue D panel is a plus.
        Reference helper: /app/backend/tests/repro_neg_balance_truevalue.py (passing).


# ==== Wave 1 (BOPS doc): points 7, 9 (new reports) + point 4 (fix) ====
backend:
  - task: "New vs Repeat (Daywise) report + CSV export"
    implemented: true
    working: "NA"
    file: "routes/bops_reports_routes.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: |
            GET /api/bops-reports/new-vs-repeat-daywise + /export. Distinct customers per IST bill-day,
            split New vs Existing (fresh bills only, new_or_existing tag), with total + %new/%existing +
            per-range totals. Reuses _store_match (start_date/end_date/zone/city/store_class/store_id).
            Self-verified: range incl 2021-04-01 -> 15 new / 0 existing / 100% new; empty ranges -> 0.
  - task: "Store-wise Customer Count (recency segments) report + CSV export"
    implemented: true
    working: "NA"
    file: "routes/bops_reports_routes.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: |
            GET /api/bops-reports/customer-count-by-store (+ /export). Groups the customers collection by
            home_store_id, buckets by recency vs as_of (default today): Active(0-6M)/Win-Back-Lost(6-12M)/
            At-Risk(12M+) + No-Mapping(no mobile) + Grand Total; resolves store name/zone/class. Self-verified:
            64 stores, totals sum to 800,065 (active 209513 + no_mapping 0 + wbl 149862 + at_risk 440690).
            NOTE (assumption): all 800K customers have a mobile so No-Mapping=0 in this dataset — flagged to user.
  - task: "Shopper Bill Report — Dormant & Lapsed visible with a recent date range (point 4 fix)"
    implemented: true
    working: "NA"
    file: "routes/shopper_report_routes.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: |
            BUG: dormant/lapsed + a recent start_date (default MTD range) produced an impossible window
            (start_date > bucket cutoff) -> zero rows ("dormant & lapsed not visible"). FIX: in the recency
            branch, drop the lower bound ($gte/$gt) on bill_date and keep only the bucket upper cap.
            Self-verified: dormant/lapsed + range 2026-07-01..07-31 now return rows (was 0 before).

frontend:
  - task: "New vs Repeat (Daywise) + Store-wise Customer Count report pages"
    implemented: true
    working: "NA"
    file: "pages/admin/NewVsRepeatDaywise.jsx, pages/admin/CustomerCountByStore.jsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: |
            Two new report pages under Reports nav (/admin/reports/new-vs-repeat-daywise and
            /admin/reports/customer-count-by-store) with filters, KPI cards, chart (NVR), table (ReportTable),
            and CSV export via requestExport. Fixed a ReportTable `visible` prop bug (must be a Set).
            Both render cleanly (verified via screenshot).

agent_communication:
    - agent: "main"
      message: |
        VERIFY Wave 1 (login superadmin@fundle.io / Fundle@2026):
        1) GET /api/bops-reports/new-vs-repeat-daywise?start_date=2021-01-01&end_date=2026-12-31 -> rows with
           new/existing/total/%; totals present. Also /export returns a CSV.
        2) GET /api/bops-reports/customer-count-by-store -> 64 store rows, each with active/no_mapping/
           win_back_lost/at_risk/grand_total; totals sum to grand_total. Also /export CSV.
        3) Shopper Bill Report point-4 fix: GET /api/shopper-report/bills?recency=dormant&start_date=2026-07-01&
           end_date=2026-07-31 (and recency=lapsed) MUST now return rows (was 0 before). Also confirm recency=all
           and recency=active still work.
        4) Frontend: open /admin/reports/new-vs-repeat-daywise and /admin/reports/customer-count-by-store,
           confirm they render, filters + Apply work, table populates, and Download CSV triggers an export.
        Backend-first; frontend smoke of the two pages. Do NOT run bulk mutations. Reference: earlier iterations
        93/94 passed.


# ==== Bug fix: reverse_duplicate_bonus_credits non-idempotency (runaway -750) ====
backend:
  - task: "reverse_duplicate_bonus_credits is idempotent (nets out prior reversals, never over-deducts)"
    implemented: true
    working: "NA"
    file: "routes/master_brain_tools.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: |
            ROOT CAUSE (from customer 9303632456 Master Brain ledger screenshot): a top-up campaign was run
            3x (+375 x3) and then reverse_duplicate_bonus_credits was run 3x, each deducting -750 ("Reversal of
            2 duplicates") -> runaway negative + balance/ledger divergence. The tool detected duplicates from the
            original type:'bonus' rows but wrote its reversal as a type:'adjust' row and NEVER voided the bonus
            rows, so every re-run re-detected the same duplicates and deducted again (non-idempotent).
            FIX: before applying, sum the reversals ALREADY applied per customer (our own master_brain 'adjust'
            rows with reason ~ /duplicat/i) and only reverse the OUTSTANDING surplus = max(0, excess - already).
            Customers already fully/over-reversed are skipped. Preview now shows already_reversed +
            outstanding_to_reverse; result reports total_points_to_reverse + already_reversed_customers.
            Self-verified (tests/repro_dup_bonus_idempotent.py): Case A 3 dup top-ups (bal 1250) -> run1 reverses
            750 -> 500; run2/run3 do NOTHING (stays 500). Case B already over-reversed (bal -250) -> tool reverses
            NOTHING (does not drop further). Undo of a reversal run still restores exact balance (verified earlier).

agent_communication:
    - agent: "main"
      message: |
        VERIFY the reverse_duplicate_bonus_credits idempotency fix (Master Admin masteradmin@fundle.io / Master@2026).
        The tool is invoked through the Master Brain agent flow (no plain REST endpoint), so the reliable path is to
        run/extend /app/backend/tests/repro_dup_bonus_idempotent.py (invokes the real handler
        routes.master_brain_tools._tool_reverse_duplicate_bonus_credits against the DB) and assert:
        1) A customer with N duplicate master_brain bonus rows (same mobile/points/reason within window) is reversed
           by exactly (N-1)*points ONCE; balance + lifetime_points_earned drop by that amount only.
        2) Running the tool again for the same scope reverses NOTHING (idempotent) — balance unchanged.
        3) A customer already OVER-reversed (prior reversal adjust rows summing >= the surplus) is skipped — balance
           does NOT drop further.
        4) Preview (confirm=false) returns total_points_to_reverse and already_reversed_customers and a sample with
           outstanding_to_reverse.
        Seed throwaway customers (e.g. 9700000101/102) with customers + points_ledger rows and CLEAN UP after.
        Backend-only. Prior passing iterations: 93 (return ledger), 94 (neg-balance true value), 95 (BOPS wave1).


# ==== Campaign Manager Phase 2/3/4 (Guided Wizard + DLR delivery + Blacklist + MB unified ROI) ====
backend:
  - task: "Blacklist CRUD + auto-blacklist on 3 successive DLR failures + exclude from datasets"
    implemented: true
    working: true
    file: "routes/blacklist_util.py, routes/campaigns_routes.py, routes/communications_routes.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: |
            Phase 4. New routes/blacklist_util.py (sms_blacklist + dlr_mobile_stats collections).
            _ingest_dlr now resolves the mobile + calls record_dlr_status -> a per-mobile consecutive
            failure counter (reset on 'delivered'); at 3 failures the number is auto-added to the blacklist.
            _freeze_dataset + _freeze_dataset_from_mobiles + _run_bulk_send_job all exclude blacklisted mobiles.
            Endpoints (declared BEFORE /{campaign_id} to avoid path shadowing): GET/POST /api/campaigns/blacklist,
            DELETE /api/campaigns/blacklist/{mobile}. Self-verified via curl: 2 failure DLRs -> not blacklisted,
            3rd -> auto-blacklisted; manual add/list/delete OK; freeze excludes blacklisted (test_mb_unified_roi.py).
  - task: "Ad-hoc audience preview for the wizard + campaign delivery report"
    implemented: true
    working: true
    file: "routes/campaigns_routes.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: |
            POST /api/campaigns/audience-preview (audience_type + audience_filter -> total + sample + blacklist total).
            GET /api/campaigns/{id}/delivery already existed (counts from message_log DLR statuses). Self-verified via curl.
  - task: "Master Brain campaigns unified into core ROI pipeline"
    implemented: true
    working: true
    file: "routes/master_brain_tools.py, routes/campaigns_routes.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
        - working: true
          agent: "main"
          comment: |
            Phase 2. _tool_send_campaign now accepts objective/objective_params/roi_window/cost and calls
            register_mb_campaign() -> creates a CORE campaigns_col doc (source=master_brain) + freezes the
            dataset (campaign_datasets_col, blacklist-excluded) so MB campaigns show in Campaign Manager with
            real ROI + delivery. _run_mb_campaign tags message_log with campaign_id and syncs core status/sent.
            send_campaign tool schema extended (cohort/segment audiences + objective params). Verified via
            tests/test_mb_unified_roi.py (PASS: core doc + frozen dataset, blacklisted number excluded).

frontend:
  - task: "Guided Campaign Wizard (Objective -> Audience -> Message -> Review & Launch) + Delivery modal + Blacklist manager"
    implemented: true
    working: "NA"
    file: "pages/admin/CampaignManager.jsx, pages/admin/campaigns/CampaignWizard.jsx, CampaignDeliveryModal.jsx, CampaignBlacklistModal.jsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: |
            Phase 2/3/4 frontend. Replaced the single-page modal with a 4-step CampaignWizard (stepper,
            per-step validation, live audience preview, review summary, Save-draft / Create-&-Launch).
            Added a Delivery button per launched campaign -> CampaignDeliveryModal (counts, delivery/failure
            rate, failures table, Pull DLRs) and a header Blacklist button -> CampaignBlacklistModal (add/search/
            remove, auto vs manual). MB campaigns show a "MB" pill. Smoke-tested via screenshots (wizard steps,
            delivery modal, blacklist modal all render).

metadata:
  created_by: "main_agent"
  version: "1.2"
  test_sequence: 101

test_plan:
  current_focus:
    - "Guided Campaign Wizard (Objective -> Audience -> Message -> Review & Launch) + Delivery modal + Blacklist manager"
    - "Blacklist CRUD + auto-blacklist on 3 successive DLR failures + exclude from datasets"
    - "Ad-hoc audience preview for the wizard + campaign delivery report"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: |
        Test Campaign Manager Phases 2/3/4 (login superadmin@fundle.io / Fundle@2026 at /crm/login).
        IMPORTANT: do NOT launch campaigns that have a Karix template linked (would send real SMS to real
        customers). Only test SIMULATED campaigns (no template selected) and use throwaway mobiles for blacklist.
        BACKEND: 1) POST /api/campaigns/audience-preview {audience_type,audience_filter} -> total_audience+sample.
        2) Blacklist: POST /api/campaigns/blacklist {mobile,reason}; GET /api/campaigns/blacklist; DELETE
        /api/campaigns/blacklist/{mobile}. 3) Auto-blacklist: hit GET /api/communications/dlr/karix?dest=<10digit>&status=UNDELIV
        THREE times -> the 3rd returns auto_blacklisted:true and it appears in GET /api/campaigns/blacklist; clean up after.
        4) Create a SIMULATED campaign (no template_id) via POST /api/campaigns, launch it POST /api/campaigns/{id}/launch,
        then GET /api/campaigns/{id}/delivery and GET /api/campaigns/{id}/roi?window=7d. Clean up test campaigns.
        FRONTEND: open /admin/campaigns -> New campaign opens the WIZARD. Step through Objective (name + objective +
        ROI window) -> Next -> Audience (shows a live count) -> Next -> Message (channels/coupon/cost) -> Next ->
        Review (summary) -> Save draft creates a row. Launch a simulated draft, open its ROI + Delivery modals.
        Header "Blacklist" button opens the manager: add a throwaway number, see it listed, remove it. testids:
        new-campaign-btn, campaign-wizard, wizard-step-*, campaign-name-input, objective-generic, wizard-next,
        audience-count, wizard-create-draft, wizard-create-launch, launch-{id}, roi-{id}, delivery-{id},
        campaign-delivery-modal, open-blacklist-btn, campaign-blacklist-modal, blacklist-mobile-input,
        blacklist-add-btn, blacklist-remove-{mobile}.

# ==== Marketing Database + Unique Coupons + Campaign Scheduling + Bulk SMS pipe (session 3) ====
backend:
  - task: "Marketing Database — create (paste/upload), list, detail with member vs non-member stats, delete; usable as campaign audience"
    implemented: true
    working: true
    file: "routes/marketing_db_routes.py, routes/campaigns_routes.py (_audience_filter_async marketing_db)"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: |
            New /api/marketing-db router. POST "" (paste mobiles_text/mobiles), POST /upload (CSV/XLSX, auto-detects
            mobile column), GET "" list, GET /{id}, GET /{id}/customers (paginated, member flag + name/tier), DELETE /{id},
            POST /{id}/recompute. Mobiles normalised to last-10, deduped; member stats = intersection with customers_col.
            audience_type='marketing_db' resolves to {mobile:{$in:mobiles}} in campaigns. Self-verified via curl + tests/test_mdb_unique_sched.py (member stats correct).
  - task: "Unique per-mobile coupons — allocate (segment/marketing_db/mobiles), batches list/detail/export/delete; POS mobile-bound single-use redemption"
    implemented: true
    working: true
    file: "routes/coupons_routes.py (unique/*), routes/pos_ewards_routes.py (_lookup_pos_coupon), database.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: |
            POST /api/coupons/unique/allocate → coupon_batches + unique_coupons (one code per mobile, locked to that
            mobile). GET /unique/batches, GET /unique/batches/{id} (paginated codes + counts), GET /unique/batches/{id}/export
            (CSV), DELETE /unique/batches/{id}. POS posCouponDetails + posRedeemCoupon now fall back to unique_coupons via
            _lookup_pos_coupon: rejects if a different mobile tries it, rejects if already redeemed, marks redeemed + bumps
            batch counter. Verified via tests/test_mdb_unique_sched.py (correct/wrong/redeemed lookups).
  - task: "Campaign scheduling — schedule_at auto-fires via scheduler; unschedule"
    implemented: true
    working: true
    file: "routes/campaigns_routes.py (_do_launch, run_due_campaigns, /unschedule), scheduler.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: |
            Launch refactored to _do_launch(c,user). New run_due_campaigns() APScheduler job every 60s auto-launches any
            status='scheduled' campaign whose schedule_at<=now (no user action). POST /campaigns/{id}/unschedule reverts to
            draft. Verified via tests/test_mdb_unique_sched.py (past-due scheduled campaign auto-fired to completed).
  - task: "Campaign SMS via BULK Karix account (fundle_campaign JSON API); transactional stays on old pipe; MID capture + body-aware status"
    implemented: true
    working: true
    file: "routes/communications_routes.py (send_sms_campaign_karix, _parse_provider_mid, _karix_json_ok, config), routes/master_brain_tools.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: true
          agent: "main"
          comment: |
            Campaign bulk sends now use send_sms_campaign_karix → Karix JsonReceiver (account fundle_campaign, sender KAZOFN,
            key from provider_config). _run_bulk_send_job + MB campaigns use it; transactional SMS unchanged. Fixed
            _parse_provider_mid to capture 'Request ID=' (so DLRs match) and _karix_submit_ok/_karix_json_ok so 'Platform
            Accepted' vs in-body failures are labelled correctly. Provider config backfills the campaign account keys.
            NOTE: real delivery needs the correct DLT-approved template body under KAZOFN — untested live-send (needs a real number).

frontend:
  - task: "Marketing Database page + Unique Coupons tab + Wizard (marketing_db audience, unique-batch attach, scheduling) + Provider Settings bulk section"
    implemented: true
    working: "NA"
    file: "pages/admin/MarketingDatabasePage.jsx, pages/admin/coupons/UniqueCouponsPanel.jsx, pages/admin/CouponEngine.jsx, pages/admin/campaigns/CampaignWizard.jsx, pages/admin/CampaignManager.jsx, pages/admin/communications/ProviderSettingsPage.jsx, AdminLayout.jsx, App.js"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        - working: "NA"
          agent: "main"
          comment: |
            New nav 'Marketing Database' under Segment Builder. Page: list w/ member vs non-member counts, create modal
            (paste OR CSV/Excel upload), detail w/ member-filter + search + 'Run campaign on this dataset'. Coupons page now
            has Static/Unique tabs; Unique panel: create-batch (offer + audience: marketing_db/segment/paste) → batches list
            → detail (codes, filter, export CSV, delete). Wizard adds marketing_db audience, unique-coupon attach, and a
            'Schedule for later' datetime → Schedule button. Campaign list shows scheduled time + Launch-now + Unschedule.
            Provider Settings has a 'SMS — Campaign / Bulk (fundle_campaign)' section. Smoke-tested via screenshots.

metadata:
  version: "1.3"
  test_sequence: 102

test_plan:
  current_focus:
    - "Marketing Database page + Unique Coupons tab + Wizard (marketing_db audience, unique-batch attach, scheduling) + Provider Settings bulk section"
    - "Marketing Database — create (paste/upload), list, detail with member vs non-member stats, delete; usable as campaign audience"
    - "Unique per-mobile coupons — allocate, batches, POS mobile-bound single-use redemption"
    - "Campaign scheduling — schedule_at auto-fires via scheduler; unschedule"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    - agent: "main"
      message: |
        Session-3 features (login superadmin@fundle.io / Fundle@2026 at /crm/login). SAFETY: do NOT launch any campaign
        with a Karix template linked (sends REAL SMS). Use SIMULATED campaigns (no template). Use throwaway 10-digit mobiles
        and clean up test data (marketing DBs, coupon batches, campaigns) after.
        BACKEND: (1) Marketing DB: POST /api/marketing-db {name,mobiles_text} (mix a real customer mobile + fake numbers) →
        total/member_count/non_member_count; GET /api/marketing-db; GET /api/marketing-db/{id}/customers?member=true; DELETE.
        (2) Unique coupons: POST /api/coupons/unique/allocate {name,coupon_type,discount_value,min_bill_amount,valid_from,valid_to,
        prefix,audience:{source:'mobiles',mobiles:[...]}} → batch; GET /api/coupons/unique/batches; GET /unique/batches/{id};
        DELETE. (3) Scheduling: create a campaign with status 'scheduled' + a PAST schedule_at, then the 60s scheduler auto-fires
        it (status→completed); POST /api/campaigns/{id}/unschedule reverts a future-scheduled one to draft.
        FRONTEND: 'Marketing Database' nav under Segment Builder → New database (paste numbers) → row shows members vs
        non-members → open detail → member filter + 'Run campaign on this dataset' opens the wizard prefilled. Coupons page →
        'Unique coupons' tab → New unique batch (offer + Paste numbers) → Allocate → batch appears → open → Export CSV.
        Campaign wizard: audience 'From Marketing Database' selectable; Review step has a 'Schedule for later' datetime that
        turns the button into 'Schedule'. Campaign list shows scheduled time + 'Launch now' + 'Unschedule'. testids:
        nav-marketing-db, marketing-database-page, mdb-new-btn, mdb-create-modal, mdb-name-input, mdb-paste-input,
        mdb-create-submit, mdb-open-{id}, mdb-member-filter, mdb-run-campaign, coupon-tab-unique, unique-new-btn,
        unique-allocate-btn, unique-open-{id}, unique-export, audience-mdb-select, coupon-batch-select, schedule-at-input,
        wizard-create-schedule, launch-now-{id}, unschedule-{id}.
