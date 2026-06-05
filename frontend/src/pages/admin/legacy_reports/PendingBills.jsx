/* Pending Bills Report */
import { LegacyReportShell, useReportParams, DatePair } from "./_shell";
import { fmtINR, fmtNum } from "@/lib/format";

const cols = [
  { key: "bill_date", label: "Bill Date", cellClass: "text-xs font-mono", fmt: (v) => (v || "").slice(0, 10) },
  { key: "bill_number", label: "Bill #", cellClass: "font-mono text-xs" },
  { key: "customer_mobile", label: "Mobile", cellClass: "font-mono" },
  { key: "store_id", label: "Store", cellClass: "text-xs font-mono" },
  { key: "net_amount", label: "Net ₹", cellClass: "text-right font-mono", fmt: fmtINR },
  { key: "points_earned", label: "Pts Awarded", cellClass: "text-right font-mono text-amber-700", fmt: (v) => v == null ? "—" : fmtNum(v) },
];

export default function PendingBills() {
  const ps = useReportParams({ limit: 200 });
  return (
    <LegacyReportShell
      testid="lr-pending-bills"
      title="Pending Bills"
      subtitle="LEGACY REPORT · UNPROCESSED"
      endpoint="/legacy-reports/pending-bills"
      paramsState={ps}
      filters={<DatePair paramsState={ps} />}
      columns={cols}
    />
  );
}
