/* Missed Call Requests Report */
import { LegacyReportShell, useReportParams, DatePair } from "./_shell";

const cols = [
  { key: "received_at", label: "When", cellClass: "text-xs font-mono", fmt: (v) => (v || "").slice(0, 16) },
  { key: "mobile", label: "Mobile", cellClass: "font-mono" },
  { key: "campaign_code", label: "Campaign Code", cellClass: "font-mono text-xs" },
  { key: "status", label: "Status" },
  { key: "store_id", label: "Store", cellClass: "text-xs font-mono" },
];

export default function MissedCalls() {
  const ps = useReportParams({ limit: 200 });
  return (
    <LegacyReportShell
      testid="lr-missed-calls"
      title="Missed Call Requests"
      subtitle="LEGACY REPORT · IVR CAPTURES"
      paginate={false}
      endpoint="/legacy-reports/missed-calls"
      paramsState={ps}
      filters={<DatePair paramsState={ps} />}
      columns={cols}
    />
  );
}
