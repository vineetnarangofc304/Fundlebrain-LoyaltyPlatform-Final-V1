import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader, KPICard, StatusPill, SectionHeading } from "../_shared";
import { fmtNum, fmtDate } from "@/lib/format";
import { LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid, ReferenceLine, Area, AreaChart } from "recharts";

export default function NPSDashboard() {
  const [summary, setSummary] = useState(null);
  const [trend, setTrend] = useState([]);
  const [byStore, setByStore] = useState([]);
  const [recent, setRecent] = useState([]);
  useEffect(() => {
    Promise.all([
      api.get("/nps/summary"),
      api.get("/analytics/nps-dashboard"),
      api.get("/nps/by-store"),
      api.get("/nps/recent"),
    ]).then(([s, t, b, r]) => { setSummary(s.data); setTrend(t.data); setByStore(b.data); setRecent(r.data); });
  }, []);
  if (!summary) return <div className="p-10 text-neutral-500">Loading…</div>;
  return (
    <div data-testid="nps-dashboard-page">
      <PageHeader title="NPS & Feedback Dashboard" subtitle="VOICE OF CUSTOMER · LIVE" />
      <div className="p-8 space-y-6">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <KPICard label="NPS Score" value={summary.score ?? "N/A"} accent="burgundy" testid="dash-nps-score" />
          <KPICard label="Promoters" value={fmtNum(summary.promoters)} accent="emerald" testid="dash-promoters" />
          <KPICard label="Passives" value={fmtNum(summary.passives)} accent="amber" testid="dash-passives" />
          <KPICard label="Detractors" value={fmtNum(summary.detractors)} accent="rose" testid="dash-detractors" />
          <KPICard label="Avg Score" value={summary.avg_score ?? "N/A"} accent="indigo" testid="dash-avg-score" />
        </div>
        <div className="chart-card p-5" data-accent="burgundy">
          <SectionHeading eyebrow="NPS TREND" title="Daily score · last 60 days" accent="burgundy" />
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={trend}>
              <defs>
                <linearGradient id="npsGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#571326" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#571326" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
              <XAxis dataKey="date" stroke="#64748b" fontSize={10} tickFormatter={(d) => d?.slice(5)} />
              <YAxis stroke="#64748b" fontSize={11} domain={[-100, 100]} />
              <ReferenceLine y={50} stroke="#047857" strokeDasharray="3 3" label={{ value: "Excellent ≥50", fontSize: 10, fill: "#047857" }} />
              <ReferenceLine y={0} stroke="#9F1239" strokeDasharray="3 3" />
              <Tooltip />
              <Area type="monotone" dataKey="nps" stroke="#571326" strokeWidth={2.5} fill="url(#npsGrad)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div className="grid lg:grid-cols-2 gap-4">
          <div className="chart-card p-5" data-accent="indigo">
            <SectionHeading eyebrow="BY STORE" title="Store NPS rankings" accent="indigo" />
            <div className="max-h-[400px] overflow-y-auto">
              <table className="data-table">
                <thead><tr><th>Store</th><th>City</th><th className="text-right">NPS</th><th className="text-right">Responses</th></tr></thead>
                <tbody>
                  {byStore.map((s) => {
                    const color = s.nps >= 50 ? "#047857" : s.nps >= 0 ? "#B45309" : "#9F1239";
                    return (
                      <tr key={s.store_id}>
                        <td>{s.store_name}</td>
                        <td>{s.city}</td>
                        <td className="text-right font-mono font-semibold" style={{ color }}>{s.nps}</td>
                        <td className="text-right font-mono">{s.total}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
          <div className="chart-card p-5" data-accent="teal">
            <SectionHeading eyebrow="RECENT FEEDBACK" title="Latest customer voice" accent="teal" />
            <div className="space-y-3 max-h-[400px] overflow-y-auto">
              {recent.map((r) => (
                <div key={r.id} className="border-b border-black/5 pb-3">
                  <div className="flex items-center gap-2 mb-1">
                    <StatusPill status={r.sentiment} />
                    <span className="font-mono text-sm">{r.score}/10</span>
                    <span className="text-xs text-neutral-500">{fmtDate(r.created_at)}</span>
                  </div>
                  {r.feedback && <div className="text-sm text-neutral-700">"{r.feedback}"</div>}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
