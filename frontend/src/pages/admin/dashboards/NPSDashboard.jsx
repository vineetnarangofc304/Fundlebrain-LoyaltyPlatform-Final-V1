import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader, KPICard, SectionHeading, DashboardError } from "../_shared";
import { fmtNum } from "@/lib/format";
import { Area, AreaChart, BarChart, Bar, ResponsiveContainer, XAxis, YAxis, CartesianGrid, Tooltip } from "recharts";
import { RefreshCw, MessageSquare, Star } from "lucide-react";
import DateRangePicker from "../_date_range_picker";
import DrillDownModal from "../DrillDownModal";

const NPS_COLUMNS = [
  { key: "created_at", label: "Date" },
  { key: "mobile", label: "Mobile", mono: true },
  { key: "store_name", label: "Store" },
  { key: "score", label: "Score", align: "right" },
  { key: "comment", label: "Feedback" },
];

export default function NPSDashboard() {
  const [range, setRange] = useState({ preset: "0", period_days: 60, start_date: "", end_date: "" });
  const [summary, setSummary] = useState(null);
  const [byStore, setByStore] = useState([]);
  const [recent, setRecent] = useState([]);
  const [trend, setTrend] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [drill, setDrill] = useState(null);
  const openNps = (title, filter) => setDrill({
    title, subtitle: "NPS responses", collection: "nps_responses",
    filter, sort: [["created_at", -1]], columns: NPS_COLUMNS,
  });

  const load = async () => {
    setLoading(true);
    try {
      const params = { period_days: range.period_days || 60 };
      if (range.start_date && range.end_date) {
        params.start_date = range.start_date;
        params.end_date = range.end_date;
      }
      const [s, bs, rc, td] = await Promise.all([
        api.get("/nps/summary"),
        api.get("/nps/by-store"),
        api.get("/nps/recent"),
        api.get("/analytics/nps-dashboard", { params }),
      ]);
      setSummary(s.data);
      setByStore(Array.isArray(bs.data) ? bs.data : []);
      setRecent(Array.isArray(rc.data) ? rc.data : []);
      setTrend(Array.isArray(td.data) ? td.data : []);
    } finally {
      setLoading(false);
    }
  };
  const reload = () => { setError(null); load().catch((e) => setError(e?.response?.data?.detail || e?.message || "Failed to load")); };
  useEffect(() => { reload(); /* eslint-disable-next-line */ }, [range]);

  if (error && !summary) return <DashboardError error={error} onRetry={reload} title="NPS & Feedback" />;
  if (loading && !summary) return <div className="p-10 text-neutral-500">Loading NPS data…</div>;

  // Empty state — no NPS responses yet. Render an explanatory panel instead of a broken-looking dashboard.
  const isEmpty = !summary || (!summary.total && !trend.length && !byStore.length && !recent.length);

  return (
    <div data-testid="nps-dashboard">
      <PageHeader
        title="NPS & Voice of Customer"
        subtitle="POST-PURCHASE EXPERIENCE TRACKING · LIVE"
        actions={
          <>
            <DateRangePicker value={range} onChange={setRange} testid="nps-date-range" />
            <button className="k-btn k-btn-outline k-btn-sm" onClick={load} data-testid="nps-refresh">
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
            </button>
          </>
        }
      />
      <div className="p-8 space-y-6">
        {isEmpty ? (
          <div className="bg-gradient-to-br from-amber-50 to-white border border-amber-200 p-10 text-center" data-testid="nps-empty">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-amber-100 mb-5">
              <Star className="w-7 h-7 text-amber-700" />
            </div>
            <div className="font-display text-2xl text-neutral-900 mb-2">No NPS responses captured yet</div>
            <div className="text-sm text-neutral-600 max-w-xl mx-auto leading-relaxed">
              NPS surveys are sent automatically after each transaction via the configured
              channel (SMS or WhatsApp). Once customers respond — or you submit a manual
              entry via <code className="px-1 py-0.5 bg-amber-100 rounded text-xs">/api/nps</code> —
              this dashboard will populate with score distribution, daily trend, store-level
              breakdown and recent feedback.
            </div>
            <div className="mt-6 grid grid-cols-3 gap-4 max-w-xl mx-auto text-left">
              <div className="bg-white border border-amber-200 p-3">
                <div className="text-[10px] uppercase tracking-[0.2em] text-emerald-700 font-medium mb-1">PROMOTERS</div>
                <div className="text-xs text-neutral-600">Score 9–10. Your loyalty programme champions.</div>
              </div>
              <div className="bg-white border border-amber-200 p-3">
                <div className="text-[10px] uppercase tracking-[0.2em] text-amber-700 font-medium mb-1">PASSIVES</div>
                <div className="text-xs text-neutral-600">Score 7–8. At risk of becoming detractors.</div>
              </div>
              <div className="bg-white border border-amber-200 p-3">
                <div className="text-[10px] uppercase tracking-[0.2em] text-rose-700 font-medium mb-1">DETRACTORS</div>
                <div className="text-xs text-neutral-600">Score 0–6. Service-recovery candidates.</div>
              </div>
            </div>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <KPICard label="NPS Score" value={summary?.nps_score ?? 0} accent="amber" testid="nps-kpi-score"
                onClick={() => openNps("All NPS responses", {})}
                info="NPS = % Promoters minus % Detractors. Industry benchmark for fashion retail is 35-50 (good), 50+ (excellent)." />
              <KPICard label="Total Responses" value={fmtNum(summary?.total || 0)} accent="indigo" testid="nps-kpi-total" onClick={() => openNps("All NPS responses", {})} />
              <KPICard label="Promoters" value={fmtNum(summary?.promoters || 0)} hint={`${summary?.promoter_pct?.toFixed(1) || 0}%`} accent="emerald" testid="nps-kpi-promoters" onClick={() => openNps("Promoters (score 9–10)", { score: { $gte: 9 } })} />
              <KPICard label="Detractors" value={fmtNum(summary?.detractors || 0)} hint={`${summary?.detractor_pct?.toFixed(1) || 0}%`} accent="rose" testid="nps-kpi-detractors" onClick={() => openNps("Detractors (score 0–6)", { score: { $lte: 6 } })} />
            </div>

            {trend.length > 0 && (
              <div className="chart-card p-5" data-accent="amber">
                <SectionHeading eyebrow="NPS TREND" title="Score over time" accent="amber" />
                <ResponsiveContainer width="100%" height={260}>
                  <AreaChart data={trend}>
                    <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                    <XAxis dataKey="date" stroke="#64748b" fontSize={10} />
                    <YAxis stroke="#64748b" fontSize={11} domain={[-100, 100]} />
                    <Tooltip />
                    <Area type="monotone" dataKey="nps" stroke="#B45309" fill="#FDE68A" strokeWidth={2.5} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}

            {byStore.length > 0 && (
              <div className="chart-card p-5" data-accent="indigo">
                <SectionHeading eyebrow="STORE-LEVEL" title="NPS by store" accent="indigo" />
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={byStore.slice(0, 15)}>
                    <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                    <XAxis dataKey="store_name" stroke="#64748b" fontSize={10} angle={-25} textAnchor="end" height={80} />
                    <YAxis stroke="#64748b" fontSize={11} />
                    <Tooltip />
                    <Bar dataKey="nps" fill="#1E3A8A" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}

            {recent.length > 0 && (
              <div className="bg-white border border-black/10 p-5" data-testid="nps-recent">
                <SectionHeading eyebrow="RECENT FEEDBACK" title="Latest NPS responses" accent="rose" />
                <table className="data-table">
                  <thead><tr><th>Date</th><th>Customer</th><th>Store</th><th>Score</th><th>Category</th><th>Feedback</th></tr></thead>
                  <tbody>
                    {recent.slice(0, 30).map((r) => (
                      <tr key={r.id || `${r.mobile}-${r.created_at}`} data-testid={`nps-recent-${r.id}`}>
                        <td className="text-xs whitespace-nowrap">{r.created_at?.slice(0, 10)}</td>
                        <td className="font-mono text-xs">{r.mobile}</td>
                        <td className="text-xs">{r.store_name || "—"}</td>
                        <td className="font-mono text-right">{r.score}</td>
                        <td>
                          {r.score >= 9 ? <span className="pill pill-success">Promoter</span>
                            : r.score >= 7 ? <span className="pill pill-warning">Passive</span>
                            : <span className="pill pill-danger">Detractor</span>}
                        </td>
                        <td className="text-xs text-neutral-600 max-w-md truncate" title={r.comment}>{r.comment || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>
      <DrillDownModal open={!!drill} onClose={() => setDrill(null)} {...(drill || {})} />

    </div>
  );
}
