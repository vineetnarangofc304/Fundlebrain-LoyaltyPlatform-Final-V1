"""Oct-2026 Kazo Reports batch — PURE synthetic harness (no DB writes, no real data).
Reproduces the defects against synthetic fixtures and asserts the repaired behaviour.
Run: /root/.venv/bin/python -m backend.tests.oct2026_batch_synth_harness  (from /app)
"""
import csv
import io
import sys

sys.path.insert(0, "/app/backend")

from routes.historic_routes import _map_customer_row
from routes.reports_kpi_routes import _finalize_store_row, CRM_COLUMNS

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + detail) if detail else ""))


# ── 1. DOB/DOA import mapping (Oct Point 2 / lower Point 7) ───────────────────
# Distinct, legitimately-equal-to-visit, and null must ALL be preserved verbatim,
# and DOB/DOA must NEVER be inferred from visit columns.
def row(dob, doa, fv="2026-01-10", lv="2026-09-20"):
    return {"Mobile": "9800000001", "Name": "Synth A", "City": "Delhi",
            "First Visit Date": fv, "Last Visit Date": lv,
            "DOB": dob, "DOA": doa, "Total Billing": "1000", "Total Visits": "3"}

m_distinct, _ = _map_customer_row(row("1990-05-14", "2015-11-02"))
check("DOB distinct preserved", m_distinct["birthday"] == "1990-05-14", m_distinct["birthday"])
check("DOA distinct preserved", m_distinct["anniversary"] == "2015-11-02", m_distinct["anniversary"])

# Legitimately equal to a visit day (shops on birthday/anniversary) — must be KEPT now.
m_equal, _ = _map_customer_row(row("2026-09-20", "2026-01-10"))
check("DOB equal-to-last-visit KEPT (not nulled)", m_equal["birthday"] == "2026-09-20", repr(m_equal["birthday"]))
check("DOA equal-to-first-visit KEPT (not nulled)", m_equal["anniversary"] == "2026-01-10", repr(m_equal["anniversary"]))

# Null stays null; never back-filled from visits.
m_null, _ = _map_customer_row(row("", ""))
check("DOB null stays null (not inferred from visit)", m_null["birthday"] is None, repr(m_null["birthday"]))
check("DOA null stays null (not inferred from visit)", m_null["anniversary"] is None, repr(m_null["anniversary"]))
# Visit fields themselves still map correctly and independently.
check("first_purchase_at independent of DOB", m_null["first_purchase_at"][:10] == "2026-01-10", m_null["first_purchase_at"])
check("last_visit_at independent of DOA", m_null["last_visit_at"][:10] == "2026-09-20", m_null["last_visit_at"])


# ── 2. Store-KPI sales partition identity (Oct Points 4/5, lower Point 5) ─────
# Overall == New + Repeat + Unmapped + Return  ;  Loyalty == New + Repeat.
# Synthetic store: overall 100000, mapped 70000 (repeat 40000 => new 30000),
# returns 5000 => unmapped residual = 100000 - 5000 - 30000 - 40000 = 25000 (walk-ins).
g = {"_id": "S1", "fresh_bills": 90, "mapped_txn": 60, "unmapped_txn": 30, "repeat_txn": 35,
     "mapped_value": 70000, "repeat_value": 40000, "overall_sales": 100000,
     "return_value": 5000, "fresh_value": 95000, "return_bills": 5}
r = _finalize_store_row(g, {"overall": 50, "new": 20})
ident = round(r["new_value"] + r["repeat_value"] + r["unmapped_value"] + r["return_value"], 2)
check("Overall == New+Repeat+Unmapped+Return", ident == r["overall_sales"],
      f"{ident} vs {r['overall_sales']}")
check("Loyalty Sales == New+Repeat", r["loyalty_sales"] == round(r["new_value"] + r["repeat_value"], 2),
      f"loyalty={r['loyalty_sales']} new={r['new_value']} repeat={r['repeat_value']}")
# Reproduce the client's complaint precisely: New+Repeat alone != Overall (gap = unmapped+returns).
gap = round(r["overall_sales"] - r["loyalty_sales"], 2)
check("New+Repeat != Overall by exactly Unmapped+Returns (definition, not a bug)",
      gap == round(r["unmapped_value"] + r["return_value"], 2),
      f"gap={gap} unmapped={r['unmapped_value']} returns={r['return_value']}")
check("Customer partition New+Existing == Overall",
      r["new_customer_count"] + r["existing_customers"] == r["overall_customers"],
      f"{r['new_customer_count']}+{r['existing_customers']} vs {r['overall_customers']}")


# ── 3. CRM export format (lower Point 4 — 'cannot open') ──────────────────────
# Rebuild the exact CRM CSV (BOM + header + csv.writer) on synthetic rows incl. non-ASCII
# ('·' store separator, Indian name) and prove it round-trips through the csv parser.
def build_crm_csv(rows):
    out = io.StringIO()
    out.write("\ufeff")                      # UTF-8 BOM (the fix)
    w = csv.writer(out)
    w.writerow([l for _, l in CRM_COLUMNS])
    for c in rows:
        w.writerow([c.get(k, "") for k, _ in CRM_COLUMNS])
    return out.getvalue()

synthetic_rows = [
    {"mobile": "9800000001", "name": "Ananyā Śarmā", "city": "Delhi",
     "home_store": "K00119 · Jasola", "tier": "Gold", "points_balance": 1200,
     "last_visit_at": "2026-09-20", "birthday": "1990-05-14", "anniversary": "2015-11-02"},
    {"mobile": "9800000002", "name": "O'Brien, Rhea\nLine2", "city": "Mumbai",
     "home_store": "K00077 · Phoenix", "tier": "Silver"},  # embedded comma+newline+quote
]
csv_text = build_crm_csv(synthetic_rows)
raw = csv_text.encode("utf-8")
check("CRM CSV starts with UTF-8 BOM", raw[:3] == b"\xef\xbb\xbf", repr(raw[:3]))
# Parse back exactly as Excel/pandas would (strip the BOM via utf-8-sig).
parsed = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
header = parsed[0]
check("CRM CSV header matches column labels", header == [l for _, l in CRM_COLUMNS],
      f"{len(header)} cols")
check("CRM CSV row count correct (header + 2 data)", len(parsed) == 3, str(len(parsed)))
# The field with embedded comma/newline/quote round-trips to one cell, not broken columns.
check("CRM CSV embedded comma/newline/quote round-trips intact",
      parsed[2][1] == "O'Brien, Rhea\nLine2", repr(parsed[2][1]))
check("CRM CSV non-ASCII name preserved", parsed[1][1] == "Ananyā Śarmā", parsed[1][1])
check("CRM CSV '·' store separator preserved", "·" in parsed[1][4], parsed[1][4])


print("\n==== SUMMARY ====")
print(f"PASSED {len(PASS)}  FAILED {len(FAIL)}")
if FAIL:
    print("FAILURES:", FAIL)
    sys.exit(1)
