/* Active Coupon Report */
import { LegacyReportShell, useReportParams, DatePair } from "./_shell";
import { fmtNum } from "@/lib/format";

const cols = [
  { key: "code", label: "Code", cellClass: "font-mono", fmt: (v) => <span className="px-2 py-0.5 bg-amber-100 text-amber-900 rounded text-xs">{v}</span> },
  { key: "name", label: "Name" },
  { key: "customer_mobile", label: "Mobile", cellClass: "font-mono", fmt: (v) => v || <span className="text-neutral-400 text-xs">—</span> },
  { key: "discount_type", label: "Type", cellClass: "text-xs uppercase" },
  { key: "discount_value", label: "Value", cellClass: "text-right font-mono", fmt: (v, r) => r.discount_type === "percent" ? `${v}%` : fmtNum(v) },
  { key: "valid_from", label: "Valid From", cellClass: "text-xs font-mono", fmt: (v) => (v || "").slice(0, 10) },
  { key: "valid_to", label: "Valid To", cellClass: "text-xs font-mono", fmt: (v) => (v || "").slice(0, 10) },
  { key: "times_used", label: "Used", cellClass: "text-right font-mono", fmt: (v) => fmtNum(v || 0) },
  { key: "times_issued", label: "Issued", cellClass: "text-right font-mono", fmt: (v) => fmtNum(v || 0) },
];

export default function ActiveCoupons() {
  const ps = useReportParams({ limit: 500 });
  return (
    <LegacyReportShell
      testid="lr-active-coupons"
      title="Active Coupon Report"
      subtitle="LEGACY REPORT · CURRENTLY ACTIVE"
      endpoint="/legacy-reports/active-coupons"
      paramsState={ps}
      filters={<>
        <DatePair paramsState={ps} />
        <div>
          <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Code prefix</label>
          <input value={ps.params.code_prefix || ""} onChange={(e) => ps.set("code_prefix", e.target.value)} className="k-input" />
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Customer mobile</label>
          <input value={ps.params.customer_mobile || ""} onChange={(e) => ps.set("customer_mobile", e.target.value)} className="k-input" />
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Expiring in (days)</label>
          <input type="number" value={ps.params.expiring_within_days || ""} onChange={(e) => ps.set("expiring_within_days", parseInt(e.target.value) || undefined)} className="k-input w-32" />
        </div>
      </>}
      columns={cols}
    />
  );
}
