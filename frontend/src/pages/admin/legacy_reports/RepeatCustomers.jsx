/* Repeat Customers Report — customers with >=N visits */
import { LegacyReportShell, useReportParams } from "./_shell";
import { fmtINR, fmtNum } from "@/lib/format";

const cols = [
  { key: "mobile", label: "Mobile", cellClass: "font-mono" },
  { key: "name", label: "Name" },
  { key: "tier", label: "Tier", fmt: (v) => v ? <span className="text-xs uppercase">{v}</span> : "—" },
  { key: "visit_count", label: "Visits", cellClass: "text-right font-mono", fmt: fmtNum },
  { key: "lifetime_spend", label: "Lifetime ₹", cellClass: "text-right font-mono", fmt: fmtINR },
  { key: "last_visit_at", label: "Last Visit", cellClass: "text-xs text-neutral-600", fmt: (v) => (v || "").slice(0, 10) },
  { key: "home_store_id", label: "Home Store", cellClass: "text-xs font-mono" },
];

export default function RepeatCustomers() {
  const ps = useReportParams({ min_visits: 2, limit: 100 });
  return (
    <LegacyReportShell
      testid="lr-repeat-cust"
      title="Repeat Customers"
      subtitle="LEGACY REPORT · DETAILED"
      endpoint="/legacy-reports/repeat-customers"
      paramsState={ps}
      filters={<>
        <div>
          <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Min visits</label>
          <input type="number" min={2} value={ps.params.min_visits || 2} onChange={(e) => ps.set("min_visits", parseInt(e.target.value) || 2)} className="k-input w-24" />
        </div>
      </>}
      columns={cols}
    />
  );
}
