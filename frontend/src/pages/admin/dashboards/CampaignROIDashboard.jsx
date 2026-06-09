/* Campaign ROI v2 — funnel + leaderboard + channel breakdown. */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { PageHeader, KPICard, SectionHeading, CHART_SERIES, DashboardError } from "../_shared";
import { fmtINR, fmtNum, fmtPct } from "@/lib/format";
import AIInsightStrip from "../AIInsightStrip";
import DrillDownModal from "../DrillDownModal";
import { RefreshCw } from "lucide-react";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  Cell, PieChart, Pie, Legend,
} from "recharts";

const FUNNEL_COLOR = ["#1E3A8A", "#0E7C7B", "#B45309", "#571326", "#047857"];

export default function CampaignROIDashboard() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [drill, setDrill] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get("/dashboard/campaign-roi");
      setData(r.data);
    } finally { setLoading(false); }
  };
  const reload = () => { setError(null); load().catch((e) => setError(e?.response?.data?.detail || e?.message || "Failed to load")); };
  useEffect(() => { reload(); /* eslint-disable-next-line */ }, []);

  if (loading && !data) return <div className="p-10 text-neutral-500">Loading campaign ROI…</div>;
  if (error && !data) return <DashboardError error={error} onRetry={reload} title="Campaign ROI" />;
  if (!data) return null;

  const t = data.totals;
  const aiPayload = {
    campaigns: t.campaigns,
    sent: t.sent, delivered: t.delivered, opened: t.opened,
    clicked: t.clicked, converted: t.converted,
    revenue: t.revenue, cost: t.cost, overall_roi_pct: t.overall_roi_pct,
    ctr_pct: t.overall_ctr_pct, cvr_pct: t.overall_cvr_pct,
    top_channels: data.by_channel.slice(0, 3),
    top_campaigns: data.leaderboard.slice(0, 5).map((c) => ({ name: c.name, roi_pct: c.roi_pct, revenue: c.revenue })),
  };

  return (
    <div data-testid="campaign-roi">
      <PageHeader
        title="Campaign ROI"
        subtitle="FUNNEL · CHANNELS · LEADERBOARD · LIVE"
        actions={
          <button className="k-btn k-btn-outline k-btn-sm" onClick={load} data-testid="cr-refresh">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
          </button>
        }
      />

      <div className="p-8 space-y-6">
        <AIInsightStrip dashboardKey="campaign_roi" payload={aiPayload} title="Marketing Performance Intelligence" />

        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <KPICard label="Campaigns" value={fmtNum(t.campaigns)} accent="slate" testid="cr-kpi-campaigns" />
          <KPICard label="Sent" value={fmtNum(t.sent)} accent="indigo" testid="cr-kpi-sent" />
          <KPICard label="Converted" value={fmtNum(t.converted)} hint={fmtPct(t.overall_cvr_pct)} accent="emerald" testid="cr-kpi-converted" />
          <KPICard label="Revenue" value={fmtINR(t.revenue)} accent="burgundy" testid="cr-kpi-revenue" />
          <KPICard label="Cost" value={fmtINR(t.cost)} accent="rose" testid="cr-kpi-cost" />
          <KPICard label="ROI" value={t.overall_roi_pct == null ? "N/A" : fmtPct(t.overall_roi_pct)} accent="emerald" testid="cr-kpi-roi" />
        </div>

        <div className="grid lg:grid-cols-[3fr_2fr] gap-4">
          <div className="chart-card p-5" data-testid="cr-funnel">
            <SectionHeading eyebrow="FUNNEL" title="Sent → Converted" accent="indigo" />
            <div className="space-y-3 mt-4">
              {data.funnel.map((f, i) => {
                const width = Math.max(f.pct_of_sent, 8); // visual floor for empty bars
                return (
                  <div key={f.stage} data-testid={`cr-funnel-${f.stage.toLowerCase()}`}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="font-medium">{f.stage}</span>
                      <span className="font-mono">{fmtNum(f.count)} <span className="text-neutral-400">({fmtPct(f.pct_of_sent)})</span></span>
                    </div>
                    <div className="h-7 bg-neutral-50 overflow-hidden">
                      <div className="h-full transition-all flex items-center pl-3" style={{ width: `${width}%`, background: FUNNEL_COLOR[i % FUNNEL_COLOR.length] }}>
                        {f.pct_of_sent > 5 && <span className="text-white text-[10px] font-mono">{fmtPct(f.pct_of_sent)}</span>}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="bg-white border border-black/10 p-5" data-testid="cr-channels">
            <SectionHeading eyebrow="CHANNEL MIX" title="Performance by channel" accent="teal" />
            {data.by_channel.length === 0 || data.by_channel.every((c) => c.sent === 0) ? (
              <div className="text-sm text-neutral-500 py-10 text-center">No channel metrics yet</div>
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie data={data.by_channel} dataKey="revenue" nameKey="channel" cx="50%" cy="50%"
                       innerRadius={50} outerRadius={90} paddingAngle={2}
                       label={(e) => e.channel} labelLine={false}>
                    {data.by_channel.map((_, i) => (
                      <Cell key={i} fill={CHART_SERIES[i % CHART_SERIES.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v) => fmtINR(v)} />
                </PieChart>
              </ResponsiveContainer>
            )}
            <table className="data-table mt-2">
              <thead><tr><th>Channel</th><th className="text-right">Camp.</th><th className="text-right">CTR</th><th className="text-right">CVR</th><th className="text-right">ROI</th></tr></thead>
              <tbody>
                {data.by_channel.map((c) => (
                  <tr key={c.channel}>
                    <td className="capitalize">{c.channel}</td>
                    <td className="text-right font-mono">{c.campaigns}</td>
                    <td className="text-right font-mono">{fmtPct(c.ctr_pct)}</td>
                    <td className="text-right font-mono">{fmtPct(c.cvr_pct)}</td>
                    <td className="text-right font-mono">{c.roi_pct == null ? "—" : fmtPct(c.roi_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="bg-white border border-black/10 p-5" data-testid="cr-leaderboard">
          <SectionHeading eyebrow="CAMPAIGN LEADERBOARD" title="Ranked by ROI" accent="burgundy" />
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Campaign</th><th>Channel</th><th>Status</th>
                  <th className="text-right">Sent</th><th className="text-right">Clicked</th>
                  <th className="text-right">Converted</th>
                  <th className="text-right">CTR</th><th className="text-right">CVR</th>
                  <th className="text-right">Revenue</th><th className="text-right">ROI</th>
                </tr>
              </thead>
              <tbody>
                {data.leaderboard.map((c, i) => (
                  <tr key={c.id} className="hover:bg-neutral-50 cursor-pointer" onClick={() => navigate(`/admin/campaigns/${c.id}`)} data-testid={`cr-row-${c.id}`}>
                    <td className="font-medium">{c.name}</td>
                    <td className="capitalize"><span className="pill pill-neutral">{c.channel}</span></td>
                    <td><span className="pill pill-neutral">{c.status}</span></td>
                    <td className="text-right font-mono">{fmtNum(c.sent)}</td>
                    <td className="text-right font-mono">{fmtNum(c.clicked)}</td>
                    <td className="text-right font-mono">{fmtNum(c.converted)}</td>
                    <td className="text-right font-mono text-xs">{fmtPct(c.ctr_pct)}</td>
                    <td className="text-right font-mono text-xs">{fmtPct(c.cvr_pct)}</td>
                    <td className="text-right font-mono">{fmtINR(c.revenue)}</td>
                    <td className="text-right font-mono">
                      {c.roi_pct == null ? <span className="text-neutral-400">—</span> : (
                        <span className={c.roi_pct >= 0 ? "text-emerald-700" : "text-rose-700"}>{fmtPct(c.roi_pct)}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {drill && <DrillDownModal open={true} onClose={() => setDrill(null)} {...drill} />}
    </div>
  );
}
