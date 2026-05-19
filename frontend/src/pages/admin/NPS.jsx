import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader, KPICard, StatusPill } from "./_shared";
import { fmtNum, fmtDate } from "@/lib/format";

export default function NPSPage() {
  const [summary, setSummary] = useState(null);
  const [byStore, setByStore] = useState([]);
  const [recent, setRecent] = useState([]);

  useEffect(() => {
    Promise.all([
      api.get("/nps/summary"),
      api.get("/nps/by-store"),
      api.get("/nps/recent"),
    ]).then(([s, b, r]) => { setSummary(s.data); setByStore(b.data); setRecent(r.data); });
  }, []);

  if (!summary) return <div className="p-10 text-neutral-500">Loading…</div>;

  return (
    <div data-testid="nps-page">
      <PageHeader title="NPS & Feedback" subtitle="VOICE OF CUSTOMER" />
      <div className="p-8 space-y-6">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <KPICard label="NPS Score" value={summary.score == null ? "N/A" : summary.score} testid="kpi-nps-overall" />
          <KPICard label="Promoters" value={fmtNum(summary.promoters)} testid="kpi-promoters" />
          <KPICard label="Passives" value={fmtNum(summary.passives)} testid="kpi-passives" />
          <KPICard label="Detractors" value={fmtNum(summary.detractors)} testid="kpi-detractors" />
          <KPICard label="Avg Score" value={summary.avg_score == null ? "N/A" : summary.avg_score} testid="kpi-avg-score" />
        </div>
        <div className="bg-white border border-black/10 p-5">
          <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-3">BY STORE</div>
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead><tr><th>Store</th><th>City</th><th className="text-right">NPS</th><th className="text-right">Avg</th><th className="text-right">Total</th><th className="text-right">Promoters</th><th className="text-right">Detractors</th></tr></thead>
              <tbody>
                {byStore.map((s) => (
                  <tr key={s.store_id}>
                    <td>{s.store_name}</td><td>{s.city}</td>
                    <td className="text-right font-mono font-semibold">{s.nps}</td>
                    <td className="text-right font-mono">{s.avg_score}</td>
                    <td className="text-right font-mono">{s.total}</td>
                    <td className="text-right font-mono text-green-600">{s.promoters}</td>
                    <td className="text-right font-mono text-red-600">{s.detractors}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="bg-white border border-black/10 p-5">
          <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-3">RECENT FEEDBACK</div>
          <div className="space-y-3 max-h-[500px] overflow-y-auto">
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
  );
}
