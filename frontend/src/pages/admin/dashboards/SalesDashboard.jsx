import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader, KPICard } from "../_shared";
import { fmtINR, fmtNum } from "@/lib/format";
import { LineChart, Line, BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid, PieChart, Pie, Cell, Legend } from "recharts";

const COLORS = ["#0F172A", "#571326", "#C7A76D", "#94A3B8", "#1f2937"];

export default function SalesDashboard() {
  const [period, setPeriod] = useState(30);
  const [data, setData] = useState(null);
  const [trend, setTrend] = useState([]);

  useEffect(() => {
    Promise.all([
      api.get("/analytics/sales-dashboard", { params: { period_days: period } }),
      api.get("/dashboard/sales-trend", { params: { period: `${period}d` } }),
    ]).then(([d, t]) => { setData(d.data); setTrend(t.data); });
  }, [period]);

  if (!data) return <div className="p-10 text-neutral-500">Loading…</div>;

  const totalRevenue = trend.reduce((s, r) => s + r.net, 0);
  const totalTxns = trend.reduce((s, r) => s + r.txns, 0);
  const avgPerDay = trend.length ? totalRevenue / trend.length : 0;

  return (
    <div data-testid="sales-dashboard">
      <PageHeader title="Sales Dashboard" subtitle="REVENUE INTELLIGENCE"
        actions={
          <select className="k-input !w-auto !py-1.5" value={period} onChange={(e) => setPeriod(parseInt(e.target.value))} data-testid="sales-period">
            <option value={7}>7 days</option><option value={30}>30 days</option><option value={90}>90 days</option><option value={365}>365 days</option>
          </select>
        } />
      <div className="p-8 space-y-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KPICard label="Total Revenue" value={fmtINR(totalRevenue)} testid="kpi-total-rev" />
          <KPICard label="Total Transactions" value={fmtNum(totalTxns)} testid="kpi-total-txns" />
          <KPICard label="Avg / Day" value={fmtINR(avgPerDay)} testid="kpi-avg-day" />
          <KPICard label="Active Days" value={trend.length} testid="kpi-active-days" />
        </div>

        <div className="bg-white border border-black/10 p-5">
          <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-1">REVENUE TREND</div>
          <h3 className="font-display text-xl mb-4">Daily net revenue · last {period} days</h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={trend}>
              <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
              <XAxis dataKey="date" stroke="#64748b" fontSize={11} tickFormatter={(d) => d?.slice(5)} />
              <YAxis stroke="#64748b" fontSize={11} tickFormatter={(v) => `₹${(v/1000).toFixed(0)}K`} />
              <Tooltip formatter={(v) => fmtINR(v)} />
              <Line type="monotone" dataKey="net" stroke="#571326" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="grid lg:grid-cols-2 gap-4">
          <div className="bg-white border border-black/10 p-5">
            <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-1">HOURLY DISTRIBUTION</div>
            <h3 className="font-display text-xl mb-4">Sales by hour of day</h3>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={data.hourly}>
                <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                <XAxis dataKey="hour" stroke="#64748b" fontSize={11} tickFormatter={(h) => `${h}h`} />
                <YAxis stroke="#64748b" fontSize={11} tickFormatter={(v) => `₹${(v/1000).toFixed(0)}K`} />
                <Tooltip formatter={(v) => fmtINR(v)} />
                <Bar dataKey="net" fill="#571326" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white border border-black/10 p-5">
            <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-1">DAY OF WEEK</div>
            <h3 className="font-display text-xl mb-4">Sales by weekday</h3>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={data.weekday}>
                <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                <XAxis dataKey="day" stroke="#64748b" fontSize={11} />
                <YAxis stroke="#64748b" fontSize={11} tickFormatter={(v) => `₹${(v/1000).toFixed(0)}K`} />
                <Tooltip formatter={(v) => fmtINR(v)} />
                <Bar dataKey="net" fill="#0F172A" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white border border-black/10 p-5">
            <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-1">PAYMENT MIX</div>
            <h3 className="font-display text-xl mb-4">By payment mode</h3>
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie data={data.payment_mix} dataKey="net" nameKey="mode" cx="50%" cy="50%" outerRadius={85} label={(p) => p.mode}>
                  {data.payment_mix.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip formatter={(v) => fmtINR(v)} />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white border border-black/10 p-5">
            <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-1">DISCOUNT BUCKETS</div>
            <h3 className="font-display text-xl mb-4">Discount distribution</h3>
            <table className="data-table">
              <thead><tr><th>Bucket</th><th className="text-right">Txns</th><th className="text-right">Net</th></tr></thead>
              <tbody>
                {data.discount_distribution.map((r) => (
                  <tr key={r.bucket}>
                    <td><span className="pill pill-neutral">{r.bucket}</span></td>
                    <td className="text-right font-mono">{fmtNum(r.count)}</td>
                    <td className="text-right font-mono">{fmtINR(r.net)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
