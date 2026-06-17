/* Top Customers Report */
import { LegacyReportShell, useReportParams, DatePair } from "./_shell";
import { fmtMoney2, fmtNum } from "@/lib/format";

const cols = [
  { key: "rank", label: "#", cellClass: "text-right font-mono w-10", fmt: (_, r, i) => "" },
  { key: "mobile", label: "Mobile", cellClass: "font-mono" },
  { key: "name", label: "Name" },
  { key: "tier", label: "Tier", fmt: (v) => v ? <span className="text-xs uppercase">{v}</span> : "—" },
  { key: "visit_count", label: "Visits", cellClass: "text-right font-mono", fmt: fmtNum },
  { key: "lifetime_spend", label: "Lifetime ₹", cellClass: "text-right font-mono", fmt: fmtMoney2 },
  { key: "points_balance", label: "Points", cellClass: "text-right font-mono", fmt: fmtNum },
];

export default function TopCustomers() {
  const ps = useReportParams({ by: "purchase", limit: 50 });
  return (
    <LegacyReportShell
      testid="lr-top-cust"
      title="Top Customers"
      subtitle="LEGACY REPORT · DETAILED"
      paginate={false}
      endpoint="/legacy-reports/top-customers"
      paramsState={ps}
      filters={<>
        <DatePair paramsState={ps} />
        <div>
          <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Sort by</label>
          <select value={ps.params.by} onChange={(e) => ps.set("by", e.target.value)} className="k-input">
            <option value="purchase">Purchase</option>
            <option value="visits">Visits</option>
            <option value="points">Points Balance</option>
          </select>
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
        <div>
          <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Top N</label>
          <input type="number" min={10} max={500} value={ps.params.limit || 50} onChange={(e) => ps.set("limit", parseInt(e.target.value) || 50)} className="k-input w-24" />
        </div>
      </>}
      columns={cols}
      responseKey="rows"
    />
  );
}
