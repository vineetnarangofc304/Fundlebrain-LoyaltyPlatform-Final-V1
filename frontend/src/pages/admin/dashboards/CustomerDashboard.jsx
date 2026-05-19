import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { PageHeader, KPICard } from "../_shared";
import { fmtINR, fmtNum, tierClass } from "@/lib/format";
import { BarChart, Bar, LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid, PieChart, Pie, Cell } from "recharts";

const COLORS = ["#0F172A", "#571326", "#C7A76D", "#94A3B8"];

export default function CustomerDashboard() {
  const [data, setData] = useState(null);
  useEffect(() => { api.get("/analytics/customer-dashboard").then((r) => setData(r.data)); }, []);
  if (!data) return <div className="p-10 text-neutral-500">Loading…</div>;
  const totalCust = data.churn_distribution.reduce((s, r) => s + r.count, 0);
  return (
    <div data-testid="customer-dashboard">
      <PageHeader title="Customer Analytics" subtitle="WHO IS KAZO" />
      <div className="p-8 space-y-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KPICard label="Total Customers" value={fmtNum(totalCust)} testid="kpi-total-cust" />
          <KPICard label="High-Risk Churn" value={fmtNum(data.churn_distribution.find(c => c.risk === "high")?.count || 0)} testid="kpi-high-risk" />
          <KPICard label="One-Time Buyers" value={fmtNum(data.visit_frequency.find(v => v.bucket?.startsWith("1"))?.count || 0)} testid="kpi-one-time" />
          <KPICard label="Top City" value={data.city_distribution[0]?.city || "—"} hint={fmtINR(data.city_distribution[0]?.spend)} testid="kpi-top-city" />
        </div>

        <div className="grid lg:grid-cols-2 gap-4">
          <div className="bg-white border border-black/10 p-5">
            <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-1">NEW REGISTRATIONS</div>
            <h3 className="font-display text-xl mb-4">Daily sign-ups · last 90 days</h3>
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={data.new_customer_trend}>
                <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                <XAxis dataKey="date" stroke="#64748b" fontSize={10} tickFormatter={(d) => d?.slice(5)} />
                <YAxis stroke="#64748b" fontSize={11} />
                <Tooltip />
                <Line type="monotone" dataKey="count" stroke="#571326" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white border border-black/10 p-5">
            <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-1">CHURN RISK</div>
            <h3 className="font-display text-xl mb-4">Customer health distribution</h3>
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={data.churn_distribution} dataKey="count" nameKey="risk" cx="50%" cy="50%" outerRadius={85} label={(p) => `${p.risk}: ${p.count}`}>
                  {data.churn_distribution.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white border border-black/10 p-5">
            <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-1">VISIT FREQUENCY</div>
            <h3 className="font-display text-xl mb-4">How often they come back</h3>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={data.visit_frequency}>
                <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                <XAxis dataKey="bucket" stroke="#64748b" fontSize={11} />
                <YAxis stroke="#64748b" fontSize={11} />
                <Tooltip />
                <Bar dataKey="count" fill="#571326" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white border border-black/10 p-5">
            <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-1">TOP CITIES</div>
            <h3 className="font-display text-xl mb-4">By lifetime spend</h3>
            <div className="overflow-x-auto max-h-[280px] overflow-y-auto">
              <table className="data-table">
                <thead><tr><th>City</th><th className="text-right">Customers</th><th className="text-right">Spend</th></tr></thead>
                <tbody>
                  {data.city_distribution.map((r) => (
                    <tr key={r.city}>
                      <td>{r.city}</td>
                      <td className="text-right font-mono">{fmtNum(r.count)}</td>
                      <td className="text-right font-mono">{fmtINR(r.spend)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div className="bg-white border border-black/10 p-5">
          <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-1">TOP 10 SPENDERS</div>
          <h3 className="font-display text-xl mb-4">Highest lifetime value customers</h3>
          <table className="data-table">
            <thead><tr><th>Customer</th><th>Mobile</th><th>City</th><th>Tier</th><th className="text-right">Lifetime Spend</th><th className="text-right">Visits</th><th></th></tr></thead>
            <tbody>
              {data.top_customers.map((c) => (
                <tr key={c.id}>
                  <td className="font-medium">{c.name}</td>
                  <td className="font-mono text-xs">{c.mobile}</td>
                  <td>{c.city}</td>
                  <td><span className={tierClass(c.tier)}>{c.tier?.toUpperCase()}</span></td>
                  <td className="text-right font-mono">{fmtINR(c.lifetime_spend)}</td>
                  <td className="text-right font-mono">{c.visit_count}</td>
                  <td><Link to={`/admin/customers/${c.id}`} className="text-xs kazo-text-burgundy font-medium hover:underline">View →</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
