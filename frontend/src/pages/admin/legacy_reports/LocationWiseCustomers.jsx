/* Location Wise Customer Report */
import { LegacyReportShell, useReportParams, DatePair } from "./_shell";
import { fmtMoney2, fmtNum } from "@/lib/format";

const cols = [
  { key: "store_code", label: "Code", cellClass: "font-mono text-xs" },
  { key: "store_name", label: "Store Name", cellClass: "font-medium" },
  { key: "city", label: "City" },
  { key: "state", label: "State" },
  { key: "zone", label: "Zone" },
  { key: "customer_count", label: "Customers", cellClass: "text-right font-mono", fmt: fmtNum },
  { key: "total_visits", label: "Total Visits", cellClass: "text-right font-mono", fmt: fmtNum },
  { key: "lifetime_spend", label: "Lifetime ₹", cellClass: "text-right font-mono", fmt: fmtMoney2 },
];

export default function LocationWiseCustomers() {
  const ps = useReportParams({});
  return (
    <LegacyReportShell
      testid="lr-loc-wise"
      title="Location Wise Customer"
      subtitle="LEGACY REPORT · STORE BREAKDOWN"
      paginate={false}
      endpoint="/legacy-reports/location-wise-customers"
      paramsState={ps}
      filters={<>
        <DatePair paramsState={ps} />
        <div>
          <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">State</label>
          <input value={ps.params.state || ""} onChange={(e) => ps.set("state", e.target.value)} className="k-input" />
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Zone</label>
          <input value={ps.params.zone || ""} onChange={(e) => ps.set("zone", e.target.value)} className="k-input" />
        </div>
      </>}
      columns={cols}
    />
  );
}
