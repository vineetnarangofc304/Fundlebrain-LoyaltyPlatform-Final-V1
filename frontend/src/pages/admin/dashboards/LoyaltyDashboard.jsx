import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader, KPICard, SectionHeading } from "../_shared";
import { fmtNum, fmtINR } from "@/lib/format";
import { LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid, Legend, Area, AreaChart } from "recharts";
import { RefreshCw } from "lucide-react";

const TIER_ACCENT = {
  silver: "slate",
  gold: "amber",
  platinum: "indigo",
  diamond: "burgundy",
};

export default function LoyaltyDashboard() {
  const [period, setPeriod] = useState(0); // 0 = all time
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get("/analytics/loyalty-dashboard", { params: { period_days: period } });
      setData(r.data);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [period]);
  if (!data) return <div className="p-10 text-neutral-500">Loading…</div>;
  const totalSpend = data.tiers.reduce((s, t) => s + (t.total_spend || 0), 0);
  return (
    <div data-testid="loyalty-dashboard">
      <PageHeader
        title="Loyalty Dashboard"
        subtitle="POINTS & TIERS HEALTH · LIVE"
        actions={
          <>
            <select className="k-input !w-auto !py-1.5" value={period} onChange={(e) => setPeriod(parseInt(e.target.value))} data-testid="ld-period">
              <option value={0}>All time</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
              <option value={180}>Last 180 days</option>
              <option value={365}>Last 365 days</option>
            </select>
            <button className="k-btn k-btn-outline k-btn-sm" onClick={load} data-testid="ld-refresh">
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
            </button>
          </>
        }
      />
      <div className="p-8 space-y-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {data.tiers.map((t) => (
            <KPICard
              key={t.tier}
              label={`${t.tier?.toUpperCase()} TIER`}
              value={fmtNum(t.count)}
              hint={`${fmtINR(t.total_spend)} sales · avg ${fmtINR(t.avg_spend)}`}
              accent={TIER_ACCENT[t.tier?.toLowerCase()] || "slate"}
              testid={`tier-${t.tier}`}
              info={`${t.tier?.toUpperCase()} tier — ${fmtNum(t.count)} customers contributing ${fmtINR(t.total_spend)} in lifetime sales. Average lifetime spend per customer: ${fmtINR(t.avg_spend)}. Total outstanding points in this tier: ${fmtNum(t.total_points)}.`}
            />
          ))}
        </div>

        {/* Tier-wise customers along with sale — addresses docx item #14 */}
        <div className="chart-card p-5" data-accent="amber" data-testid="ld-tier-table">
          <SectionHeading eyebrow="TIER-WISE" title="Customer count along with sales" accent="amber" />
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr><th>Tier</th><th className="text-right">Customers</th><th className="text-right">Share %</th><th className="text-right">Total Sales</th><th className="text-right">Sales Share %</th><th className="text-right">Avg Spend</th><th className="text-right">Outstanding Points</th></tr>
              </thead>
              <tbody>
                {data.tiers.map((t) => {
                  const totalCust = data.tiers.reduce((s, x) => s + x.count, 0);
                  const custShare = totalCust ? (t.count / totalCust) * 100 : 0;
                  const salesShare = totalSpend ? ((t.total_spend || 0) / totalSpend) * 100 : 0;
                  return (
                    <tr key={t.tier}>
                      <td><span className={`pill pill-${TIER_ACCENT[t.tier?.toLowerCase()] === "burgundy" ? "danger" : (TIER_ACCENT[t.tier?.toLowerCase()] === "amber" ? "warning" : "neutral")}`}>{t.tier?.toUpperCase()}</span></td>
                      <td className="text-right font-mono">{fmtNum(t.count)}</td>
                      <td className="text-right font-mono">{custShare.toFixed(1)}%</td>
                      <td className="text-right font-mono">{fmtINR(t.total_spend)}</td>
                      <td className="text-right font-mono">{salesShare.toFixed(1)}%</td>
                      <td className="text-right font-mono">{fmtINR(t.avg_spend)}</td>
                      <td className="text-right font-mono">{fmtNum(t.total_points)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        <div className="chart-card p-5" data-accent="burgundy">
          <SectionHeading eyebrow="POINTS FLOW" title="Issued vs Redeemed · last 30 days" accent="burgundy" />
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={data.points_trend}>
              <defs>
                <linearGradient id="issuedGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#571326" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#571326" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="redeemedGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#C7A76D" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#C7A76D" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="bonusGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#1E3A8A" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#1E3A8A" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
              <XAxis dataKey="date" stroke="#64748b" fontSize={10} tickFormatter={(d) => d?.slice(5)} />
              <YAxis stroke="#64748b" fontSize={11} />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Area type="monotone" dataKey="issued" stroke="#571326" strokeWidth={2.5} fill="url(#issuedGrad)" name="Issued" />
              <Area type="monotone" dataKey="redeemed" stroke="#C7A76D" strokeWidth={2.5} fill="url(#redeemedGrad)" name="Redeemed" />
              <Area type="monotone" dataKey="bonus" stroke="#1E3A8A" strokeWidth={2} fill="url(#bonusGrad)" name="Bonus" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
