/* Executive Digests — weekly auto-generated PDF reports. */
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { PageHeader, SectionHeading } from "./_shared";
import { fmtDateTime } from "@/lib/format";
import { Download, FileText, Zap, RefreshCw, Calendar } from "lucide-react";

export default function DigestsPage() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get("/reports/digests", { params: { limit: 50 } });
      setRows(r.data.rows || []);
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const trigger = async () => {
    setTriggering(true);
    try {
      const r = await api.post("/reports/digests/run-now", null, { params: { period_days: 7 } });
      toast.success(`Generated ${r.data.filename}`);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
    finally { setTriggering(false); }
  };

  const download = async (digest) => {
    try {
      const res = await api.get(`/reports/digests/${digest.id}/download`, {
        responseType: "blob",
      });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = digest.filename;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (e) { toast.error("Download failed"); }
  };

  return (
    <div data-testid="digests-page">
      <PageHeader
        title="Executive Digests"
        subtitle="WEEKLY · AUTO-GENERATED · BRANDED PDF"
        actions={
          <>
            <button onClick={load} className="k-btn k-btn-outline k-btn-sm" data-testid="digests-refresh">
              <RefreshCw className="w-3.5 h-3.5" /> Refresh
            </button>
            <button onClick={trigger} disabled={triggering} className="k-btn kazo-bg-burgundy k-btn-sm" data-testid="digests-trigger">
              <Zap className="w-3.5 h-3.5" /> {triggering ? "Generating…" : "Generate now"}
            </button>
          </>
        }
      />

      <div className="p-8 space-y-6">
        <div className="chart-card p-5" data-accent="burgundy">
          <div className="grid grid-cols-3 gap-4 mb-5">
            <KpiTile
              eyebrow="SCHEDULE"
              value="Mon · 09:00 IST"
              caption="Weekly cron"
              icon={Calendar}
              accent="#571326"
            />
            <KpiTile
              eyebrow="RUNS"
              value={rows.length.toString()}
              caption="Stored digests"
              icon={FileText}
              accent="#1E3A8A"
            />
            <KpiTile
              eyebrow="LATEST"
              value={rows[0] ? fmtDateTime(rows[0].generated_at) : "—"}
              caption={rows[0] ? `${(rows[0].size_bytes / 1024).toFixed(1)} KB` : "Not generated yet"}
              icon={Zap}
              accent="#0E7C7B"
            />
          </div>

          <SectionHeading
            eyebrow={`${rows.length} DIGESTS`}
            title="All scheduled digests"
            accent="burgundy"
          />
          {loading && !rows.length ? (
            <div className="py-10 text-neutral-500 text-sm">Loading…</div>
          ) : rows.length === 0 ? (
            <div className="py-12 text-center text-neutral-500 text-sm">
              No digests generated yet.<br />
              Click <b>Generate now</b> above to create the first one, or wait for the weekly Monday 09:00 IST schedule.
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr><th>Filename</th><th>Period</th><th>Size</th><th>Trigger</th><th>Generated</th><th></th></tr>
              </thead>
              <tbody>
                {rows.map((d) => (
                  <tr key={d.id} data-testid={`digest-${d.id}`}>
                    <td className="font-medium font-mono text-xs">{d.filename}</td>
                    <td className="text-xs">{d.period_days} days</td>
                    <td className="text-xs text-neutral-600 tabular-nums">{(d.size_bytes / 1024).toFixed(1)} KB</td>
                    <td className="text-xs">
                      {d.triggered_by === "weekly_cron"
                        ? <span className="pill" style={{ background: "#EEF2FF", color: "#3730A3", border: "1px solid #C7D2FE" }}>auto · weekly</span>
                        : <span className="pill" style={{ background: "#FAF5FF", color: "#6B21A8", border: "1px solid #E9D5FF" }}>{d.triggered_by}</span>}
                    </td>
                    <td className="text-xs text-neutral-500">{fmtDateTime(d.generated_at)}</td>
                    <td className="text-right">
                      <button onClick={() => download(d)} className="k-btn k-btn-outline k-btn-sm" data-testid={`download-${d.id}`}>
                        <Download className="w-3.5 h-3.5" /> Download PDF
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="text-xs text-neutral-500">
          <strong>What's in the digest?</strong> Net sales, AOV, transactions, active customers, sales delta vs previous period, outstanding points liability, top 5 stores and top 5 cities — all computed live from MongoDB at run time (no snapshots).
        </div>
      </div>
    </div>
  );
}

function KpiTile({ eyebrow, value, caption, icon: Icon, accent }) {
  return (
    <div className="border-l-2 bg-gradient-to-r from-white via-white to-neutral-50 p-3" style={{ borderLeftColor: accent }}>
      <div className="flex items-start justify-between mb-1">
        <div className="text-[9px] uppercase tracking-[0.22em] text-neutral-500">{eyebrow}</div>
        <Icon className="w-3.5 h-3.5" style={{ color: accent }} />
      </div>
      <div className="font-display text-xl leading-tight">{value}</div>
      <div className="text-[10px] text-neutral-500 mt-0.5">{caption}</div>
    </div>
  );
}
