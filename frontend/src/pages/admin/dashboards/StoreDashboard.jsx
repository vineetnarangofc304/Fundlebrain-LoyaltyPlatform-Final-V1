import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader, KPICard } from "../_shared";
import { fmtINR, fmtNum } from "@/lib/format";
import { BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";

export default function StoreDashboard() {
  const [period, setPeriod] = useState(30);
  const [data, setData] = useState(null);
  useEffect(() => { api.get("/analytics/store-dashboard", { params: { period_days: period } }).then((r) => setData(r.data)); }, [period]);
  if (!data) return <div className="p-10 text-neutral-500">Loading…</div>;
  return (
    <div data-testid="store-dashboard">
      <PageHeader title="Store Performance" subtitle="RETAIL FOOTPRINT INTELLIGENCE"
        actions={
          <select className="k-input !w-auto !py-1.5" value={period} onChange={(e) => setPeriod(parseInt(e.target.value))}>
            <option value={7}>7 days</option><option value={30}>30 days</option><option value={90}>90 days</option><option value={365}>365 days</option>
          </select>
        } />
      <div className="p-8 space-y-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KPICard label="Stores Reporting" value={fmtNum(data.stores.length)} testid="kpi-stores-count" />
          <KPICard label="Top Store" value={data.stores[0]?.store_name?.split(" - ")[0] || "—"} hint={fmtINR(data.stores[0]?.net)} testid="kpi-top-store" />
          <KPICard label="Total Net" value={fmtINR(data.stores.reduce((s, r) => s + r.net, 0))} testid="kpi-total-store-net" />
          <KPICard label="Top Region" value={data.regions[0]?.region || "—"} hint={fmtINR(data.regions[0]?.net)} testid="kpi-top-region" />
        </div>

        <div className="bg-white border border-black/10 p-5">
          <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-1">BY REGION</div>
          <h3 className="font-display text-xl mb-4">Revenue by region</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={data.regions}>
              <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
              <XAxis dataKey="region" stroke="#64748b" fontSize={11} />
              <YAxis stroke="#64748b" fontSize={11} tickFormatter={(v) => `₹${(v/100000).toFixed(1)}L`} />
              <Tooltip formatter={(v) => fmtINR(v)} />
              <Bar dataKey="net" fill="#571326" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white border border-black/10 p-5">
          <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-1">STORE LEADERBOARD</div>
          <h3 className="font-display text-xl mb-4">All stores · last {period} days</h3>
          <table className="data-table">
            <thead><tr><th>Rank</th><th>Store</th><th>City</th><th>Region</th><th className="text-right">Net</th><th className="text-right">Txns</th><th className="text-right">Customers</th><th className="text-right">AOV</th><th className="text-right">Discount</th></tr></thead>
            <tbody>
              {data.stores.map((s, i) => (
                <tr key={s.store_id}>
                  <td className="font-mono text-xs">#{i + 1}</td>
                  <td className="font-medium">{s.store_name}</td>
                  <td>{s.city}</td>
                  <td><span className="pill pill-neutral">{s.region}</span></td>
                  <td className="text-right font-mono">{fmtINR(s.net)}</td>
                  <td className="text-right font-mono">{fmtNum(s.txns)}</td>
                  <td className="text-right font-mono">{fmtNum(s.unique_customers)}</td>
                  <td className="text-right font-mono">{fmtINR(s.aov)}</td>
                  <td className="text-right font-mono text-red-600">{fmtINR(s.discount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
