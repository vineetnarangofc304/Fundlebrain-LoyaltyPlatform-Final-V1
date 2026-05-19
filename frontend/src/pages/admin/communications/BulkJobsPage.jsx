/* Bulk Send Jobs — monitor background dispatch jobs (queued/running/completed/failed). */
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader, SectionHeading } from "../_shared";
import { fmtDateTime } from "@/lib/format";
import { RefreshCw, CheckCircle2, AlertCircle, Loader2, Clock } from "lucide-react";

const STATUS_STYLES = {
  queued: { bg: "#FEF3C7", color: "#92400E", border: "#FDE68A", icon: Clock, label: "Queued" },
  running: { bg: "#DBEAFE", color: "#1E40AF", border: "#BFDBFE", icon: Loader2, label: "Running", spin: true },
  completed: { bg: "#ECFDF5", color: "#047857", border: "#A7F3D0", icon: CheckCircle2, label: "Completed" },
  failed: { bg: "#FEF2F2", color: "#B91C1C", border: "#FECACA", icon: AlertCircle, label: "Failed" },
};

export default function BulkJobsPage() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

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
          <SectionHeading
            eyebrow={`${rows.length} JOBS`}
            title="All bulk dispatch jobs"
            accent="teal"
          />
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
                </tr>
              </thead>
              <tbody>
                {rows.map((j) => {
                  const st = STATUS_STYLES[j.status] || STATUS_STYLES.queued;
                  const Icon = st.icon;
                  return (
                    <tr key={j.id} data-testid={`bulk-row-${j.id}`}>
                      <td className="font-medium">{j.template_name || j.template_id?.slice(0,8)}</td>
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
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        <div className="text-xs text-neutral-500">
          <strong>Background dispatch</strong>: jobs run asynchronously via FastAPI BackgroundTasks, so the UI remains responsive even for 5,000+ recipient audiences. Status auto-refreshes every 5 seconds.
        </div>
      </div>
    </div>
  );
}
