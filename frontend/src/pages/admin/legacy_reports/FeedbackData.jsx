/* Feedback Data Report */
import { LegacyReportShell, useReportParams, DatePair } from "./_shell";

const BUCKET_COLOR = {
  promoter: "text-emerald-700",
  passive: "text-amber-700",
  detractor: "text-rose-700",
};

const cols = [
  { key: "created_at", label: "When", cellClass: "text-xs font-mono", fmt: (v) => (v || "").slice(0, 16).replace("T", " ") },
  { key: "mobile", label: "Mobile", cellClass: "font-mono" },
  { key: "score", label: "Score", cellClass: "text-center font-mono font-medium", fmt: (v) => v ?? "—" },
  { key: "bucket", label: "Bucket", fmt: (v) => v ? <span className={`text-xs uppercase font-medium ${BUCKET_COLOR[v] || ""}`}>{v}</span> : "—" },
  { key: "feedback", label: "Comment", cellClass: "text-xs text-neutral-700", fmt: (v) => v ? <span className="line-clamp-2 max-w-md">{v}</span> : <span className="text-neutral-400">— no comment —</span> },
  { key: "store_id", label: "Store", cellClass: "text-xs font-mono" },
];

export default function FeedbackData() {
  const ps = useReportParams({ limit: 200 });
  return (
    <LegacyReportShell
      testid="lr-feedback"
      title="Feedback Data"
      subtitle="LEGACY REPORT · CUSTOMER FEEDBACK"
      endpoint="/legacy-reports/feedback-data"
      paramsState={ps}
      filters={<>
        <div>
          <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Bucket</label>
          <select value={ps.params.bucket || ""} onChange={(e) => ps.set("bucket", e.target.value)} className="k-input">
            <option value="">All</option>
            <option value="promoter">Promoter (9-10)</option>
            <option value="passive">Passive (7-8)</option>
            <option value="detractor">Detractor (0-6)</option>
          </select>
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Has comment?</label>
          <select value={ps.params.has_comment ?? ""} onChange={(e) => ps.set("has_comment", e.target.value === "" ? undefined : e.target.value === "true")} className="k-input">
            <option value="">Either</option>
            <option value="true">With comment</option>
            <option value="false">Without comment</option>
          </select>
        </div>
        <DatePair paramsState={ps} />
      </>}
      columns={cols}
    />
  );
}
