import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader, KPICard } from "../_shared";
import { fmtNum, fmtINR } from "@/lib/format";
import { BarChart, Bar, LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from "recharts";

export default function LoyaltyDashboard() {
  const [data, setData] = useState(null);
  useEffect(() => { api.get("/analytics/loyalty-dashboard").then((r) => setData(r.data)); }, []);
  if (!data) return <div className="p-10 text-neutral-500">Loading…</div>;
  return (
    <div data-testid="loyalty-dashboard">
      <PageHeader title="Loyalty Dashboard" subtitle="POINTS & TIERS HEALTH" />
      <div className="p-8 space-y-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {data.tiers.map((t) => (
            <div key={t.tier} className="kpi-card">
              <div className="text-[10px] uppercase tracking-widest text-neutral-500 mb-2">{t.tier?.toUpperCase()} TIER</div>
              <div className="font-mono text-2xl">{fmtNum(t.count)}</div>
              <div className="text-xs text-neutral-500 mt-1">avg spend {fmtINR(t.avg_spend)} · {fmtNum(t.total_points)} pts outstanding</div>
            </div>
          ))}
        </div>

        <div className="bg-white border border-black/10 p-5">
          <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-1">POINTS FLOW</div>
          <h3 className="font-display text-xl mb-4">Issued vs Redeemed · last 30 days</h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={data.points_trend}>
              <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
              <XAxis dataKey="date" stroke="#64748b" fontSize={10} tickFormatter={(d) => d?.slice(5)} />
              <YAxis stroke="#64748b" fontSize={11} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="issued" stroke="#571326" strokeWidth={2} name="Issued" />
              <Line type="monotone" dataKey="redeemed" stroke="#C7A76D" strokeWidth={2} name="Redeemed" />
              <Line type="monotone" dataKey="bonus" stroke="#0F172A" strokeWidth={2} name="Bonus" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
