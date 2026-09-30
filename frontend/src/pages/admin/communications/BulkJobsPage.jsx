/* Bulk Send Jobs — monitor background dispatch jobs (queued/running/completed/failed),
   drill into per-recipient delivery status, and download the full result as CSV. */
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader, SectionHeading } from "../_shared";
import { fmtDateTime } from "@/lib/format";
import { toast } from "sonner";
import { RefreshCw, CheckCircle2, AlertCircle, Loader2, Clock, X, Download } from "lucide-react";

const STATUS_STYLES = {
  queued: { bg: "#FEF3C7", color: "#92400E", border: "#FDE68A", icon: Clock, label: "Queued" },
  running: { bg: "#DBEAFE", color: "#1E40AF", border: "#BFDBFE", icon: Loader2, label: "Running", spin: true },
  completed: { bg: "#ECFDF5", color: "#047857", border: "#A7F3D0", icon: CheckCircle2, label: "Completed" },
  failed: { bg: "#FEF2F2", color: "#B91C1C", border: "#FECACA", icon: AlertCircle, label: "Failed" },
};

const DLR_STYLES = {
  Delivered: { bg: "#ECFDF5", color: "#047857" },
  Pending: { bg: "#FEF3C7", color: "#92400E" },
  Failed: { bg: "#FEF2F2", color: "#B91C1C" },
  Undelivered: { bg: "#FEF2F2", color: "#B91C1C" },
  Rejected: { bg: "#FEF2F2", color: "#B91C1C" },
  Expired: { bg: "#F3F4F6", color: "#6B7280" },
};

export default function BulkJobsPage() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sel, setSel] = useState(null);
  const [recips, setRecips] = useState(null);
  const [recipsLoading, setRecipsLoading] = useState(false);
  const [downloading, setDownloading] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get("/communications/bulk-jobs", { params: { limit: 100 } });
      setRows(r.data.rows || []);
    } finally { setLoading(false); }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);

  const openJob = async (job) => {
    setSel(job); setRecips(null); setRecipsLoading(true);
    try {
      const r = await api.get(`/communications/bulk-jobs/${job.id}/recipients`, { params: { limit: 3000 }, timeout: 60000 });
      setRecips(r.data.recipients || []);
    } catch { setRecips([]); toast.error("Could not load recipients"); }
    finally { setRecipsLoading(false); }
  };

  const downloadCsv = async (job) => {
    setDownloading(job.id);
    try {
      const r = await api.get(`/communications/bulk-jobs/${job.id}/recipients.csv`, { responseType: "blob", timeout: 120000 });
      const url = window.URL.createObjectURL(new Blob([r.data], { type: "text/csv" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `bulk_job_${job.id.slice(0, 8)}_recipients.csv`;
      document.body.appendChild(a); a.click(); a.remove();
      window.URL.revokeObjectURL(url);
    } catch { toast.error("Download failed"); }
    finally { setDownloading(null); }
  };

  return (
    <div data-testid="bulk-jobs-page">
      <PageHeader
        title="Bulk Send Jobs"
        subtitle="BACKGROUND DISPATCH · LIVE"
        actions={
          <button onClick={load} className="k-btn k-btn-outline k-btn-sm" data-testid="bulk-refresh">
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </button>
        }
      />

      <div className="p-8 space-y-6">
        <div className="chart-card p-5" data-accent="teal">
          <SectionHeading eyebrow={`${rows.length} JOBS`} title="All bulk dispatch jobs" accent="teal" />
          {loading && !rows.length ? (
            <div className="py-10 text-neutral-500 text-sm">Loading…</div>
          ) : rows.length === 0 ? (
            <div className="py-12 text-center text-neutral-500 text-sm">
              No bulk jobs yet. Trigger a campaign from <a className="kazo-text-burgundy underline" href="/admin/communications/templates">Templates → Bulk send</a>.
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Template</th><th>Channel</th><th>Status</th>
                  <th className="text-right">Audience</th>
                  <th className="text-right">Processed</th>
                  <th className="text-right">Sent</th>
                  <th className="text-right">Failed</th>
                  <th>Queued at</th>
                  <th>By</th>
                  <th className="text-right">Details</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((j) => {
                  const st = STATUS_STYLES[j.status] || STATUS_STYLES.queued;
                  const Icon = st.icon;
                  return (
                    <tr key={j.id} data-testid={`bulk-row-${j.id}`}
                        className="cursor-pointer hover:bg-neutral-50" onClick={() => openJob(j)}>
                      <td className="font-medium">{j.template_name || j.template_id?.slice(0, 8)}</td>
                      <td className="text-xs uppercase tracking-widest text-neutral-600">{j.channel}</td>
                      <td>
                        <span className="pill inline-flex items-center gap-1" style={{ background: st.bg, color: st.color, border: `1px solid ${st.border}` }}>
                          <Icon className={`w-3 h-3 ${st.spin ? "animate-spin" : ""}`} /> {st.label}
                        </span>
                      </td>
                      <td className="text-right tabular-nums">{j.audience_size_total?.toLocaleString() ?? "—"}</td>
                      <td className="text-right tabular-nums">{j.processed?.toLocaleString() ?? 0}</td>
                      <td className="text-right tabular-nums text-emerald-700 font-medium">{j.sent?.toLocaleString() ?? 0}</td>
                      <td className="text-right tabular-nums text-rose-700">{j.failed?.toLocaleString() ?? 0}</td>
                      <td className="text-xs text-neutral-500">{fmtDateTime(j.queued_at)}</td>
                      <td className="text-xs text-neutral-600">{j.queued_by}</td>
                      <td className="text-right" onClick={(e) => e.stopPropagation()}>
                        <div className="inline-flex items-center gap-1.5">
                          <button className="k-btn k-btn-outline k-btn-sm" data-testid={`bulk-view-${j.id}`} onClick={() => openJob(j)}>View</button>
                          <button className="k-btn k-btn-outline k-btn-sm" data-testid={`bulk-download-${j.id}`}
                                  onClick={() => downloadCsv(j)} disabled={downloading === j.id} title="Download recipients CSV">
                            {downloading === j.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        <div className="text-xs text-neutral-500">
          <strong>Background dispatch</strong>: jobs run asynchronously so the UI stays responsive even for 5,000+ recipient audiences. Click any row to drill into per-recipient delivery status, or download the full result as CSV. Status auto-refreshes every 5 seconds.
        </div>
      </div>

      {sel && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" data-testid="bulk-job-modal"
             onClick={() => setSel(null)}>
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-4xl max-h-[85vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-6 py-4 border-b">
              <div>
                <div className="text-[10px] uppercase tracking-widest text-neutral-500">Recipient delivery report</div>
                <div className="text-lg font-semibold">{sel.template_name || sel.template_id?.slice(0, 8)} · {sel.channel?.toUpperCase()}</div>
              </div>
              <div className="flex items-center gap-2">
                <button className="k-btn k-btn-outline k-btn-sm" data-testid="bulk-modal-download" onClick={() => downloadCsv(sel)} disabled={downloading === sel.id}>
                  {downloading === sel.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />} Download CSV
                </button>
                <button className="k-btn k-btn-ghost k-btn-sm" onClick={() => setSel(null)} data-testid="bulk-modal-close"><X className="w-4 h-4" /></button>
              </div>
            </div>
            <div className="overflow-auto p-2">
              {recipsLoading ? (
                <div className="py-12 text-center text-neutral-500 text-sm">Loading recipients…</div>
              ) : !recips || recips.length === 0 ? (
                <div className="py-12 text-center text-neutral-500 text-sm">No recipient records for this job.</div>
              ) : (
                <table className="data-table">
                  <thead>
                    <tr><th>Mobile</th><th>Delivery status</th><th>Message</th><th>Provider MID</th><th>Time</th></tr>
                  </thead>
                  <tbody>
                    {recips.map((r, i) => {
                      const d = DLR_STYLES[r.delivery_label] || { bg: "#F3F4F6", color: "#6B7280" };
                      return (
                        <tr key={i} data-testid="bulk-recipient-row">
                          <td className="tabular-nums">{r.mobile}</td>
                          <td><span className="pill" style={{ background: d.bg, color: d.color }}>{r.delivery_label || "—"}</span>
                            {r.error ? <div className="text-[10px] text-rose-600 mt-0.5 max-w-[220px] truncate" title={r.error}>{r.error}</div> : null}
                          </td>
                          <td className="text-xs text-neutral-700 max-w-[280px] truncate" title={r.message}>{r.message || "—"}</td>
                          <td className="text-[10px] text-neutral-500 font-mono">{r.provider_mid || "—"}</td>
                          <td className="text-xs text-neutral-500">{fmtDateTime(r.timestamp)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
            <div className="px-6 py-2 border-t text-[11px] text-neutral-500">
              {recips ? `${recips.length} recipient(s) shown` : ""}{recips && recips.length >= 3000 ? " (first 3,000 — download CSV for the full list)" : ""}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
