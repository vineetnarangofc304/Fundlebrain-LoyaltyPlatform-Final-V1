/* Fraud Report — anomaly detection */
import { LegacyReportShell, useReportParams, DatePair } from "./_shell";
import { fmtINR, fmtNum } from "@/lib/format";

const SEVERITY_COLORS = {
  high: "bg-rose-100 text-rose-800",
  medium: "bg-amber-100 text-amber-800",
  low: "bg-sky-100 text-sky-800",
};

const cols = [
  { key: "severity", label: "Severity", fmt: (v) => (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium ${SEVERITY_COLORS[v] || "bg-neutral-100"}`}>{v}</span>
  )},
  { key: "type", label: "Type", cellClass: "text-xs uppercase tracking-wider" },
  { key: "customer_mobile", label: "Mobile", cellClass: "font-mono" },
  { key: "bill_count", label: "Bills/Pts", cellClass: "text-right font-mono", fmt: (v, r) => v ? fmtNum(v) : (r.points ? fmtNum(r.points) : "—") },
  { key: "total_amount", label: "Amount", cellClass: "text-right font-mono", fmt: (v) => v ? fmtINR(v) : "—" },
  { key: "hour", label: "When", cellClass: "text-xs font-mono", fmt: (v, r) => v || (r.created_at || "").slice(0, 16) },
  { key: "bill_numbers", label: "Details", cellClass: "text-xs", fmt: (v, r) => v ? v.slice(0, 3).join(", ") : (r.bill_number || r.ledger_id) },
  { key: "store_count", label: "Stores", cellClass: "text-right font-mono", fmt: (v) => v || "—" },
];

export default function FraudReport() {
  const ps = useReportParams({ limit: 200 });
  return (
    <LegacyReportShell
      testid="lr-fraud"
      title="Fraud Report"
      subtitle="LEGACY REPORT · ANOMALY FLAGS"
      paginate={false}
      endpoint="/legacy-reports/fraud-report"
      paramsState={ps}
      filters={<DatePair paramsState={ps} />}
      columns={cols}
      responseKey="flags"
    />
  );
}
