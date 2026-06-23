/* Downloads Center — every requested report export shows up here with its status.
   Ready files download from object storage; records auto-expire after 7 days. */
import { useState, useEffect, useCallback, useRef } from "react";
import api from "@/lib/api";
import { downloadExport } from "@/lib/exportClient";
import { PageHeader } from "./_shared";
import { fmtNum } from "@/lib/format";
import { Download, RefreshCw, Trash2, Clock, CheckCircle2, XCircle, Info } from "lucide-react";
import { toast } from "sonner";

const fmtSize = (b) => {
  if (b == null) return "—";
  if (b < 1024) return `${b} B`;
  if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
  return `${(b / 1048576).toFixed(1)} MB`;
};
const fmtWhen = (iso) => {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium", timeStyle: "short" }); }
  catch { return iso; }
};
const summarizeParams = (p = {}) => {
  const parts = [];
  for (const [k, v] of Object.entries(p)) {
    if (v == null || v === "" || v === "all") continue;
    if (k === "filter" || k === "columns" || k === "sort") continue;
    parts.push(`${k.replace(/_/g, " ")}: ${v}`);
  }
  return parts.length ? parts.join(" · ") : "All data";
};

const StatusBadge = ({ status }) => {
  const map = {
    ready: ["bg-emerald-100 text-emerald-800", CheckCircle2, "Ready"],
    processing: ["bg-amber-100 text-amber-800", Clock, "Processing"],
    failed: ["bg-rose-100 text-rose-800", XCircle, "Failed"],
  };
  const [cls, Icon, label] = map[status] || ["bg-neutral-100 text-neutral-700", Clock, status];
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium ${cls}`} data-testid={`dl-status-${status}`}>
      <Icon className={`w-3 h-3 ${status === "processing" ? "animate-spin" : ""}`} /> {label}
    </span>
  );
};

export default function DownloadsCenter() {
  const [exports, setExports] = useState([]);
  const [retentionDays, setRetentionDays] = useState(7);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);
  const timerRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const r = await api.get("/exports");
      setExports(r.data.exports || []);
      setRetentionDays(r.data.retention_days ?? 7);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    load();
    timerRef.current = setInterval(() => {
      // keep polling while anything is still processing
      setExports((cur) => {
        if (cur.some((e) => e.status === "processing")) load();
        return cur;
      });
    }, 5000);
    return () => clearInterval(timerRef.current);
  }, [load]);

  const onDownload = async (e) => {
    setBusyId(e.id);
    try { await downloadExport(e.id, e.filename); }
    catch { toast.error("Download failed"); }
    finally { setBusyId(null); }
  };

  const onDelete = async (e) => {
    try {
      await api.delete(`/exports/${e.id}`);
      setExports((cur) => cur.filter((x) => x.id !== e.id));
      toast.success("Removed");
    } catch { toast.error("Could not remove"); }
  };

  const processingCount = exports.filter((e) => e.status === "processing").length;

  return (
    <div data-testid="downloads-center">
      <PageHeader title="Downloads" subtitle="REPORTS · DOWNLOAD CENTER"
        actions={
          <button onClick={load} className="k-btn k-btn-outline" data-testid="dl-refresh">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
          </button>
        }
      />
      <div className="p-8 space-y-5">
        <div className="flex items-center gap-2 text-[13px] text-neutral-600 bg-amber-50 border border-amber-200 rounded-md px-4 py-2.5" data-testid="dl-retention-note">
          <Info className="w-4 h-4 text-amber-600 shrink-0" />
          Reports are kept for <span className="font-medium mx-1">{retentionDays} days</span> and are automatically removed after that.
          {processingCount > 0 && <span className="ml-2 text-amber-700">· {processingCount} report{processingCount > 1 ? "s" : ""} preparing…</span>}
        </div>

        <div className="chart-card p-0 overflow-x-auto" data-accent="burgundy" data-testid="dl-table-card">
          {loading ? (
            <div className="py-16 text-center text-sm text-neutral-500">Loading…</div>
          ) : exports.length === 0 ? (
            <div className="py-16 text-center text-sm text-neutral-500" data-testid="dl-empty">
              No downloads yet. Request a report export from any dashboard and it will appear here.
            </div>
          ) : (
            <table className="w-full text-sm" data-testid="dl-table">
              <thead className="border-b border-black/10 text-left">
                <tr>
                  {["Report", "Filters", "Requested by", "Rows", "Size", "Requested", "Status", ""].map((h) => (
                    <th key={h} className="py-2.5 px-3 text-[10px] uppercase tracking-widest text-neutral-500">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {exports.map((e) => (
                  <tr key={e.id} className="border-b border-black/5 hover:bg-amber-50/40" data-testid={`dl-row-${e.id}`}>
                    <td className="py-2.5 px-3 font-medium">{e.label}</td>
                    <td className="py-2.5 px-3 text-neutral-600 max-w-[260px] truncate" title={summarizeParams(e.params)}>{summarizeParams(e.params)}</td>
                    <td className="py-2.5 px-3 text-neutral-600">{e.requested_by_name}</td>
                    <td className="py-2.5 px-3 font-mono text-right">{e.row_count != null ? fmtNum(e.row_count) : "—"}</td>
                    <td className="py-2.5 px-3 font-mono text-right">{fmtSize(e.file_size)}</td>
                    <td className="py-2.5 px-3 text-neutral-600 whitespace-nowrap">{fmtWhen(e.created_at)}</td>
                    <td className="py-2.5 px-3">
                      <StatusBadge status={e.status} />
                      {e.status === "failed" && e.error && <div className="text-[10px] text-rose-600 mt-1 max-w-[180px] truncate" title={e.error}>{e.error}</div>}
                    </td>
                    <td className="py-2.5 px-3 whitespace-nowrap">
                      <div className="flex items-center gap-1.5 justify-end">
                        {e.status === "ready" && (
                          <button onClick={() => onDownload(e)} disabled={busyId === e.id}
                            className="k-btn kazo-bg-burgundy text-white k-btn-sm" data-testid={`dl-download-${e.id}`}>
                            <Download className={`w-3.5 h-3.5 ${busyId === e.id ? "animate-pulse" : ""}`} /> Download
                          </button>
                        )}
                        <button onClick={() => onDelete(e)} className="p-1.5 text-neutral-400 hover:text-rose-600" title="Remove" data-testid={`dl-delete-${e.id}`}>
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
