import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader, KPICard, StatusPill } from "../_shared";
import { fmtNum, fmtDate } from "@/lib/format";
import { LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";

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
      <PageHeader title="NPS & Feedback Dashboard" subtitle="VOICE OF CUSTOMER" />
      <div className="p-8 space-y-6">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <KPICard label="NPS Score" value={summary.score ?? "N/A"} testid="dash-nps-score" />
          <KPICard label="Promoters" value={fmtNum(summary.promoters)} testid="dash-promoters" />
          <KPICard label="Passives" value={fmtNum(summary.passives)} testid="dash-passives" />
          <KPICard label="Detractors" value={fmtNum(summary.detractors)} testid="dash-detractors" />
          <KPICard label="Avg Score" value={summary.avg_score ?? "N/A"} testid="dash-avg-score" />
        </div>
        <div className="bg-white border border-black/10 p-5">
          <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-1">NPS TREND</div>
          <h3 className="font-display text-xl mb-4">Daily score · last 60 days</h3>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={trend}>
              <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
              <XAxis dataKey="date" stroke="#64748b" fontSize={10} tickFormatter={(d) => d?.slice(5)} />
              <YAxis stroke="#64748b" fontSize={11} domain={[-100, 100]} />
              <Tooltip />
              <Line type="monotone" dataKey="nps" stroke="#571326" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="grid lg:grid-cols-2 gap-4">
          <div className="bg-white border border-black/10 p-5">
            <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-1">BY STORE</div>
            <h3 className="font-display text-xl mb-4">Store NPS rankings</h3>
            <div className="max-h-[400px] overflow-y-auto">
              <table className="data-table">
                <thead><tr><th>Store</th><th>City</th><th className="text-right">NPS</th><th className="text-right">Responses</th></tr></thead>
                <tbody>
                  {byStore.map((s) => (
                    <tr key={s.store_id}>
                      <td>{s.store_name}</td>
                      <td>{s.city}</td>
                      <td className="text-right font-mono font-semibold">{s.nps}</td>
                      <td className="text-right font-mono">{s.total}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div className="bg-white border border-black/10 p-5">
            <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-1">RECENT FEEDBACK</div>
            <h3 className="font-display text-xl mb-4">Latest customer voice</h3>
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
