/* Customer Data Report */
import { LegacyReportShell, useReportParams, DatePair } from "./_shell";
import { fmtMoney2, fmtNum, fmtDateISO } from "@/lib/format";

const cols = [
  { key: "mobile", label: "Mobile", cellClass: "font-mono" },
  { key: "name", label: "Name" },
  { key: "tier", label: "Tier", fmt: (v) => v ? <span className="text-xs uppercase">{v}</span> : "—" },
  { key: "home_store_id", label: "Home Store", cellClass: "text-xs font-mono" },
  { key: "visit_count", label: "Visits", cellClass: "text-right font-mono", fmt: fmtNum },
  { key: "lifetime_spend", label: "Lifetime ₹", cellClass: "text-right font-mono", fmt: fmtMoney2 },
  { key: "points_balance", label: "Points", cellClass: "text-right font-mono", fmt: fmtNum },
  { key: "created_at", label: "Registered", cellClass: "text-xs text-neutral-600", fmt: fmtDateISO },
  { key: "is_active", label: "Status", fmt: (v) => v === false ? <span className="text-rose-600 text-xs">Deactivated</span> : <span className="text-emerald-600 text-xs">Active</span> },
];

export default function CustomerDataReport() {
  const ps = useReportParams({ limit: 100, offset: 0 });
  return (
    <LegacyReportShell
      testid="lr-customer-data"
      title="Customer Data"
      subtitle="LEGACY REPORT · DETAILED"
      endpoint="/legacy-reports/customer-data"
      paramsState={ps}
      filters={<>
        <div className="flex-1 min-w-[200px]">
          <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Search (mobile/name/email)</label>
          <input value={ps.params.q || ""} onChange={(e) => ps.set("q", e.target.value)} className="k-input w-full" data-testid="lr-cd-q" />
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Tier</label>
          <select value={ps.params.tier || ""} onChange={(e) => ps.set("tier", e.target.value)} className="k-input">
            <option value="">All</option>
            <option value="bronze">Bronze</option>
            <option value="silver">Silver</option>
            <option value="gold">Gold</option>
            <option value="platinum">Platinum</option>
          </select>
        </div>
        <DatePair paramsState={ps} />
      </>}
      columns={cols}
    />
  );
}
