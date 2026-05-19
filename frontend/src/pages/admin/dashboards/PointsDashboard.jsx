/* Points Economics v2 — earn/burn, liability, monthly flow, top redeemers. */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { PageHeader, KPICard, SectionHeading } from "../_shared";
import { fmtINR, fmtNum, fmtPct } from "@/lib/format";
import AIInsightStrip from "../AIInsightStrip";
import DrillDownModal from "../DrillDownModal";
import { RefreshCw } from "lucide-react";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  Legend, Cell,
} from "recharts";

export default function PointsDashboard() {
  const navigate = useNavigate();
  const [period, setPeriod] = useState(90);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [drill, setDrill] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get("/dashboard/points-economics", { params: { period_days: period } });
      setData(r.data);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [period]);

  if (loading && !data) return <div className="p-10 text-neutral-500">Loading points economics…</div>;
  if (!data) return null;

  const aiPayload = {
    period_days: period,
    window_earn: data.window.earn_points,
    window_burn: data.window.burn_points,
    burn_to_earn_pct: data.window.burn_to_earn_pct,
    outstanding_liability_inr: data.liability.outstanding_inr,
    redemption_pct: data.liability.redemption_pct,
    breakage_inr_at_risk: data.breakage_risk.inr_at_risk,
    top_redeemers: data.top_redeemers.slice(0, 5).map((r) => ({ name: r.name, burned: r.points_burned })),
  };

  // Earn-burn gauge (0% no burn, 100% balanced burn relative to earn)
  const gaugePct = Math.min(100, data.window.burn_to_earn_pct);

  return (
    <div data-testid="points-dashboard">
      <PageHeader
        title="Points Economics"
        subtitle="EARN · BURN · LIABILITY · BREAKAGE · LIVE"
        actions={
          <>
            <select className="k-input !w-auto !py-1.5" value={period} onChange={(e) => setPeriod(parseInt(e.target.value))} data-testid="pe-period">
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
              <option value={180}>Last 180 days</option>
              <option value={365}>Last 365 days</option>
            </select>
            <button className="k-btn k-btn-outline k-btn-sm" onClick={load} data-testid="pe-refresh">
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
            </button>
          </>
        }
      />

      <div className="p-8 space-y-6">
        <AIInsightStrip dashboardKey={`points_economics_${period}d`} payload={aiPayload} title="Points Economics Intelligence" />

        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <KPICard label="Outstanding Points" value={fmtNum(data.liability.outstanding_points)} accent="amber" testid="pe-kpi-out-points" />
          <KPICard label="Liability" value={fmtINR(data.liability.outstanding_inr)} hint={`@ ₹${data.config.burn_ratio}/pt`} accent="rose" testid="pe-kpi-liability" />
          <KPICard label="Lifetime Earned" value={fmtNum(data.liability.lifetime_earned)} accent="emerald" testid="pe-kpi-earned" />
          <KPICard label="Lifetime Redeemed" value={fmtNum(data.liability.lifetime_redeemed)} hint={fmtPct(data.liability.redemption_pct)} accent="indigo" testid="pe-kpi-redeemed" />
          <KPICard label="Breakage risk" value={fmtINR(data.breakage_risk.inr_at_risk)} hint={`${data.breakage_risk.stale_180d_customers} stale customers`} accent="rose" testid="pe-kpi-breakage" />
          <KPICard label="Burn ratio" value={`₹${data.config.burn_ratio}`} hint="per point" accent="slate" testid="pe-kpi-ratio" />
        </div>

        {/* Earn-burn gauge + window summary */}
        <div className="grid lg:grid-cols-[2fr_3fr] gap-4">
          <div className="chart-card p-5" data-testid="pe-gauge">
            <SectionHeading eyebrow={`LAST ${period}d`} title="Earn vs Burn" accent="indigo" />
            <div className="text-center mt-4">
              <div className="font-display text-5xl text-neutral-900">{data.window.burn_to_earn_pct}%</div>
              <div className="text-xs text-neutral-500 mt-1 uppercase tracking-widest">Burn-to-earn ratio</div>
            </div>
            <div className="relative h-3 bg-neutral-100 mt-6">
              <div className="absolute inset-y-0 left-0" style={{ width: `${gaugePct}%`, background: "linear-gradient(90deg, #047857 0%, #B45309 50%, #9F1239 100%)" }} />
            </div>
            <div className="flex justify-between text-[10px] text-neutral-500 mt-1 uppercase tracking-widest">
              <span>0% (no burn)</span><span>100% (1:1 balanced)</span>
            </div>
            <div className="mt-6 grid grid-cols-2 gap-3 text-sm">
              <div>
                <div className="text-[10px] uppercase tracking-widest text-emerald-700">EARNED</div>
                <div className="font-mono text-xl">{fmtNum(data.window.earn_points)}</div>
                <div className="text-xs text-neutral-500">≈ {fmtINR(data.window.earn_inr_equivalent)}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-widest text-rose-700">BURNED</div>
                <div className="font-mono text-xl">{fmtNum(data.window.burn_points)}</div>
                <div className="text-xs text-neutral-500">≈ {fmtINR(data.window.burn_inr_equivalent)}</div>
              </div>
            </div>
          </div>

          <div className="chart-card p-5" data-testid="pe-monthly">
            <SectionHeading eyebrow="MONTHLY FLOW" title="Earn vs Burn · last 12 months" accent="burgundy" />
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={data.monthly_flow} stackOffset="sign">
                <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                <XAxis dataKey="month" stroke="#64748b" fontSize={11} />
                <YAxis stroke="#64748b" fontSize={11} tickFormatter={(v) => `${(v / 1000000).toFixed(1)}M`} />
                <Tooltip formatter={(v) => fmtNum(v)} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="earn" stackId="a" fill="#047857" name="Earned" />
                <Bar dataKey="burn" stackId="a" fill="#9F1239" name="Burned" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Top redeemers */}
        <div className="bg-white border border-black/10 p-5">
          <SectionHeading eyebrow="REDEMPTION CHAMPIONS" title={`Top redeemers · last ${period} days`} accent="amber" />
          <table className="data-table">
            <thead><tr><th>Rank</th><th>Customer</th><th>City</th><th>Tier</th><th className="text-right">Points burned</th><th className="text-right">INR value</th><th className="text-right">Events</th></tr></thead>
            <tbody>
              {data.top_redeemers.length === 0 && (
                <tr><td colSpan={7} className="text-center py-6 text-neutral-500">No redemptions in this window</td></tr>
              )}
              {data.top_redeemers.map((r, i) => (
                <tr key={r.customer_id} className="hover:bg-neutral-50 cursor-pointer" onClick={() => navigate(`/admin/customers/${r.customer_id}`)} data-testid={`pe-redeemer-${i}`}>
                  <td className="font-mono">{i + 1}</td>
                  <td className="font-medium">{r.name || "—"}<div className="text-[10px] text-neutral-400 font-mono">{r.mobile}</div></td>
                  <td>{r.city || "—"}</td>
                  <td><span className="pill pill-neutral">{r.tier}</span></td>
                  <td className="text-right font-mono">{fmtNum(r.points_burned)}</td>
                  <td className="text-right font-mono">{fmtINR(r.inr_value)}</td>
                  <td className="text-right font-mono">{r.events}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {drill && <DrillDownModal open={true} onClose={() => setDrill(null)} {...drill} />}
    </div>
  );
}
