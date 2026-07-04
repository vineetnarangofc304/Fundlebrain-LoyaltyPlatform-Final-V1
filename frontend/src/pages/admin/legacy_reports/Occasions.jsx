/* Birthdays & Anniversaries Report — monthly occasion lists for campaigns. */
import { LegacyReportShell, useReportParams } from "./_shell";
import { fmtMoney2, fmtNum, fmtDateISO } from "@/lib/format";

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const CURRENT_YEAR = new Date().getFullYear();
const YEARS = Array.from({ length: 40 }, (_, i) => CURRENT_YEAR - i);

const LABEL = "text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block";

const cols = [
  { key: "mobile", label: "Mobile", cellClass: "font-mono" },
  { key: "name", label: "Name" },
  { key: "occasion_date", label: "Date", cellClass: "text-xs text-neutral-600", fmt: (v) => v || "—" },
  { key: "points_balance", label: "Points", cellClass: "text-right font-mono", fmt: fmtNum },
  { key: "last_visit_at", label: "Last Txn", cellClass: "text-xs text-neutral-600", fmt: fmtDateISO },
  { key: "lifetime_spend", label: "Lifetime ₹", cellClass: "text-right font-mono", fmt: fmtMoney2 },
  { key: "tier", label: "Tier", fmt: (v) => (v ? <span className="text-xs uppercase">{v}</span> : "—") },
  { key: "visit_count", label: "Visits", cellClass: "text-right font-mono", fmt: fmtNum },
  { key: "city", label: "City", cellClass: "text-xs" },
];

export default function OccasionsReport() {
  const now = new Date();
  const ps = useReportParams({
    type: "birthday", month: now.getMonth() + 1, year: "all",
    sort: "points_balance", dir: "desc", limit: 100, offset: 0,
  });
  return (
    <LegacyReportShell
      testid="lr-occasions"
      title="Birthdays & Anniversaries"
      subtitle="LEGACY REPORT · DETAILED"
      endpoint="/legacy-reports/occasions"
      paramsState={ps}
      filters={<>
        <div>
          <label className={LABEL}>Occasion</label>
          <select value={ps.params.type} onChange={(e) => ps.set("type", e.target.value)} className="k-input" data-testid="lr-occ-type">
            <option value="birthday">🎂 Birthday</option>
            <option value="anniversary">💍 Anniversary</option>
          </select>
        </div>
        <div>
          <label className={LABEL}>Month</label>
          <select value={ps.params.month} onChange={(e) => ps.set("month", e.target.value)} className="k-input" data-testid="lr-occ-month">
            {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
          </select>
        </div>
        <div>
          <label className={LABEL}>Year</label>
          <select value={ps.params.year} onChange={(e) => ps.set("year", e.target.value)} className="k-input" data-testid="lr-occ-year">
            <option value="all">All years</option>
            {YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
        <div>
          <label className={LABEL}>Sort by</label>
          <select value={ps.params.sort} onChange={(e) => ps.set("sort", e.target.value)} className="k-input" data-testid="lr-occ-sort">
            <option value="points_balance">Points balance</option>
            <option value="last_visit_at">Last transaction</option>
            <option value="lifetime_spend">Lifetime spend</option>
            <option value="name">Name</option>
          </select>
        </div>
        <div className="flex-1 min-w-[180px]">
          <label className={LABEL}>Search (mobile / name)</label>
          <input value={ps.params.q || ""} onChange={(e) => ps.set("q", e.target.value)} className="k-input w-full" data-testid="lr-occ-q" />
        </div>
      </>}
      columns={cols}
    />
  );
}
