import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { PageHeader, KPICard, SectionHeading, CHART_SERIES } from "../_shared";
import { fmtINR, fmtNum, tierClass } from "@/lib/format";
import { BarChart, Bar, LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid, PieChart, Pie, Cell, Area, AreaChart } from "recharts";

const RISK_COLOR = { low: "#047857", medium: "#B45309", high: "#9F1239" };

export default function CustomerDashboard() {
  const [data, setData] = useState(null);
  useEffect(() => { api.get("/analytics/customer-dashboard").then((r) => setData(r.data)); }, []);
  if (!data) return <div className="p-10 text-neutral-500">Loading…</div>;
  const totalCust = data.churn_distribution.reduce((s, r) => s + r.count, 0);
  return (
    <div data-testid="customer-dashboard">
      <PageHeader title="Customer Analytics" subtitle="WHO IS KAZO · LIVE" />
      <div className="p-8 space-y-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KPICard label="Total Customers" value={fmtNum(totalCust)} accent="indigo" testid="kpi-total-cust" />
          <KPICard label="High-Risk Churn" value={fmtNum(data.churn_distribution.find(c => c.risk === "high")?.count || 0)} accent="rose" testid="kpi-high-risk" />
          <KPICard label="One-Time Buyers" value={fmtNum(data.visit_frequency.find(v => v.bucket?.startsWith("1"))?.count || 0)} accent="amber" testid="kpi-one-time" />
          <KPICard label="Top City" value={data.city_distribution[0]?.city || "—"} hint={fmtINR(data.city_distribution[0]?.spend)} accent="teal" testid="kpi-top-city" />
        </div>

        <div className="grid lg:grid-cols-2 gap-4">
          <div className="chart-card p-5" data-accent="burgundy">
            <SectionHeading eyebrow="NEW REGISTRATIONS" title="Daily sign-ups · last 90 days" accent="burgundy" />
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={data.new_customer_trend}>
                <defs>
                  <linearGradient id="newCustGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#571326" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="#571326" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                <XAxis dataKey="date" stroke="#64748b" fontSize={10} tickFormatter={(d) => d?.slice(5)} />
                <YAxis stroke="#64748b" fontSize={11} />
                <Tooltip />
                <Area type="monotone" dataKey="count" stroke="#571326" strokeWidth={2.5} fill="url(#newCustGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div className="chart-card p-5" data-accent="rose">
            <SectionHeading eyebrow="CHURN RISK" title="Customer health distribution" accent="rose" />
            <ResponsiveContainer width="100%" height={240}>
              <PieChart>
                <Pie data={data.churn_distribution} dataKey="count" nameKey="risk" cx="50%" cy="50%" outerRadius={90} innerRadius={50} paddingAngle={2} label={(p) => `${p.risk}: ${p.count}`}>
                  {data.churn_distribution.map((d, i) => <Cell key={i} fill={RISK_COLOR[d.risk] || CHART_SERIES[i]} />)}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="chart-card p-5" data-accent="indigo">
            <SectionHeading eyebrow="VISIT FREQUENCY" title="How often they come back" accent="indigo" />
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={data.visit_frequency}>
                <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                <XAxis dataKey="bucket" stroke="#64748b" fontSize={11} />
                <YAxis stroke="#64748b" fontSize={11} />
                <Tooltip />
                <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                  {data.visit_frequency.map((_, i) => <Cell key={i} fill={CHART_SERIES[i % CHART_SERIES.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="chart-card p-5" data-accent="teal">
            <SectionHeading eyebrow="TOP CITIES" title="By lifetime spend" accent="teal" />
            <div className="overflow-x-auto max-h-[280px] overflow-y-auto">
              <table className="data-table">
                <thead><tr><th>City</th><th className="text-right">Customers</th><th className="text-right">Spend</th></tr></thead>
                <tbody>
                  {data.city_distribution.map((r, i) => (
                    <tr key={r.city}>
                      <td>
                        <span className="inline-block w-2 h-2 rounded-full mr-2 align-middle" style={{ background: CHART_SERIES[i % CHART_SERIES.length] }} />
                        {r.city}
                      </td>
                      <td className="text-right font-mono">{fmtNum(r.count)}</td>
                      <td className="text-right font-mono">{fmtINR(r.spend)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div className="chart-card p-5" data-accent="amber">
          <SectionHeading eyebrow="TOP 10 SPENDERS" title="Highest lifetime value customers" accent="amber" />
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
