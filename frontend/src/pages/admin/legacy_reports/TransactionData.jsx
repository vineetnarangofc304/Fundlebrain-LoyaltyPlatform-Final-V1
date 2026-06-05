/* Transaction Data Report */
import { LegacyReportShell, useReportParams, DatePair } from "./_shell";
import { fmtINR, fmtNum } from "@/lib/format";

const cols = [
  { key: "bill_date", label: "Bill Date", cellClass: "text-xs font-mono", fmt: (v) => (v || "").slice(0, 10) },
  { key: "bill_number", label: "Bill #", cellClass: "font-mono text-xs" },
  { key: "customer_mobile", label: "Mobile", cellClass: "font-mono" },
  { key: "store_id", label: "Store", cellClass: "text-xs font-mono" },
  { key: "net_amount", label: "Net ₹", cellClass: "text-right font-mono", fmt: fmtINR },
  { key: "gross_amount", label: "Gross ₹", cellClass: "text-right font-mono", fmt: fmtINR },
  { key: "points_earned", label: "Pts Earned", cellClass: "text-right font-mono", fmt: fmtNum },
  { key: "points_redeemed", label: "Pts Redeemed", cellClass: "text-right font-mono", fmt: (v) => v ? fmtNum(v) : "—" },
];

export default function TransactionData() {
  const ps = useReportParams({ limit: 100, offset: 0 });
  return (
    <LegacyReportShell
      testid="lr-transaction-data"
      title="Transaction Data"
      subtitle="LEGACY REPORT · DETAILED"
      endpoint="/legacy-reports/transaction-data"
      paramsState={ps}
      filters={<>
        <div className="flex-1 min-w-[200px]">
          <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Search (mobile/bill #)</label>
          <input value={ps.params.q || ""} onChange={(e) => ps.set("q", e.target.value)} className="k-input w-full" />
        </div>
        <DatePair paramsState={ps} />
      </>}
      columns={cols}
    />
  );
}
