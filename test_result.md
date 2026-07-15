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

