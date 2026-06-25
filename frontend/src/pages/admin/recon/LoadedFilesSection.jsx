import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { RefreshCw, FileSpreadsheet, CheckCircle2, AlertTriangle } from "lucide-react";
import { SectionHeading } from "../_shared";

const fmtNum = (v) => (v == null ? "—" : Number(v).toLocaleString("en-IN"));
const fmtTime = (iso) => {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-IN", {
      timeZone: "Asia/Kolkata", day: "2-digit", month: "short", year: "2-digit",
      hour: "2-digit", minute: "2-digit", hour12: true,
    });
  } catch { return iso; }
};

const STATUS_CLS = {
  completed: "bg-emerald-100 text-emerald-800",
  failed: "bg-rose-100 text-rose-800",
  ingesting: "bg-amber-100 text-amber-800",
  pending_ingest: "bg-amber-100 text-amber-800",
  uploading: "bg-slate-100 text-slate-700",
  previewed: "bg-indigo-100 text-indigo-800",
};

export default function LoadedFilesSection() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get("/historic-data/jobs", { params: { limit: 100 } });
      setJobs(r.data.rows || []);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load files");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const csvRows = (j) => Number(j.total_rows || j.row_count_estimated || 0);
  const accounted = (j) => Number(j.inserted || 0) + Number(j.updated || 0) + Number(j.skipped || 0);
  const diffOf = (j) => csvRows(j) - accounted(j);

  return (
    <div className="chart-card p-5" data-accent="indigo" data-testid="loaded-files-section">
      <div className="flex items-start justify-between gap-3">
        <SectionHeading eyebrow="FILES LOADED" title="Every CSV / Excel ingested — with row counts" accent="indigo" />
        <button className="k-btn k-btn-outline k-btn-sm shrink-0" onClick={load} disabled={loading} data-testid="loaded-files-refresh">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
        </button>
      </div>
      <p className="text-xs text-neutral-500 mt-1">
        <b>Rows</b> = rows in the file · <b>Inserted/Updated</b> = landed in the database · <b>Skipped</b> = rows the
        loader rejected · <b>Diff</b> = file rows minus everything accounted for. A non-zero Skipped or Diff means
        that file did not fully land.
      </p>

      {loading && jobs.length === 0 && <div className="text-sm text-neutral-500 mt-4">Loading files…</div>}
      {!loading && jobs.length === 0 && <div className="text-sm text-neutral-500 mt-4">No files have been loaded yet.</div>}

      {jobs.length > 0 && (
        <div className="overflow-x-auto border border-black/5 mt-4">
          <table className="w-full text-xs" data-testid="loaded-files-table">
            <thead className="bg-neutral-50">
              <tr>
                <th className="text-left px-2 py-1.5">File</th>
                <th className="text-left px-2 py-1.5">Dataset</th>
                <th className="text-left px-2 py-1.5">Status</th>
                <th className="text-right px-2 py-1.5">Rows</th>
                <th className="text-right px-2 py-1.5">Inserted</th>
                <th className="text-right px-2 py-1.5">Updated</th>
                <th className="text-right px-2 py-1.5">Skipped</th>
                <th className="text-right px-2 py-1.5">Diff</th>
                <th className="text-left px-2 py-1.5">Loaded (IST)</th>
                <th className="text-center px-2 py-1.5">Landed?</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => {
                const d = diffOf(j);
                const skipped = Number(j.skipped || 0);
                const clean = j.status === "completed" && d === 0 && skipped === 0;
                return (
                  <tr key={j.id} className="border-t border-black/5" data-testid={`loaded-file-${j.id}`}>
                    <td className="px-2 py-1 font-medium flex items-center gap-1.5">
                      <FileSpreadsheet className="w-3.5 h-3.5 text-indigo-600 shrink-0" />
                      <span className="max-w-[220px] truncate" title={j.filename}>{j.filename || "—"}</span>
                    </td>
                    <td className="px-2 py-1">{j.dataset}</td>
                    <td className="px-2 py-1">
                      <span className={`px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${STATUS_CLS[j.status] || "bg-slate-100 text-slate-700"}`}>
                        {(j.status || "").replace(/_/g, " ")}
                      </span>
                    </td>
                    <td className="px-2 py-1 text-right">{fmtNum(csvRows(j))}</td>
                    <td className="px-2 py-1 text-right">{fmtNum(j.inserted)}</td>
                    <td className="px-2 py-1 text-right">{fmtNum(j.updated)}</td>
                    <td className={`px-2 py-1 text-right ${skipped ? "text-rose-700 font-semibold" : ""}`}>{fmtNum(skipped)}</td>
                    <td className={`px-2 py-1 text-right ${d ? "text-rose-700 font-semibold" : ""}`}>{fmtNum(d)}</td>
                    <td className="px-2 py-1 text-neutral-500 whitespace-nowrap">{fmtTime(j.completed_at || j.queued_at)}</td>
                    <td className="px-2 py-1 text-center">
                      {clean
                        ? <CheckCircle2 className="w-4 h-4 text-emerald-600 inline" data-testid={`landed-ok-${j.id}`} />
                        : <AlertTriangle className="w-4 h-4 text-amber-600 inline" data-testid={`landed-warn-${j.id}`} />}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
