/* Expiry Points Report */
import { LegacyReportShell, useReportParams, DatePair } from "./_shell";
import { fmtNum } from "@/lib/format";

const cols = [
  { key: "mobile", label: "Mobile", cellClass: "font-mono" },
  { key: "name", label: "Name" },
  { key: "tier", label: "Tier", fmt: (v) => v ? <span className="text-xs uppercase">{v}</span> : "—" },
  { key: "home_store_id", label: "Home Store", cellClass: "text-xs font-mono" },
  { key: "points_balance", label: "Balance", cellClass: "text-right font-mono", fmt: fmtNum },
  { key: "expiring_points", label: "Expiring", cellClass: "text-right font-mono text-rose-700 font-medium", fmt: fmtNum },
  { key: "earliest_expiry", label: "Earliest Expiry", cellClass: "text-xs font-mono", fmt: (v) => (v || "").slice(0, 10) },
];

export default function ExpiryPoints() {
  const ps = useReportParams({ days_ahead: 60, limit: 500 });
  return (
    <LegacyReportShell
      testid="lr-expiry-points"
      title="Expiry Points Report"
      subtitle="LEGACY REPORT · POINTS EXPIRING SOON"
      endpoint="/legacy-reports/expiry-points"
      paramsState={ps}
      filters={<>
        <DatePair paramsState={ps} />
        <div>
          <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Days ahead</label>
          <input type="number" min={1} max={365} value={ps.params.days_ahead || 60} onChange={(e) => ps.set("days_ahead", parseInt(e.target.value) || 60)} className="k-input w-24" data-testid="lr-ep-days" />
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
      </>}
      columns={cols}
    />
  );
}
