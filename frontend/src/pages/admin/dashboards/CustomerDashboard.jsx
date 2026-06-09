import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { PageHeader, KPICard, SectionHeading, CHART_SERIES, DashboardError } from "../_shared";
import { fmtINR, fmtNum, tierClass } from "@/lib/format";
import { BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid, PieChart, Pie, Cell, Area, AreaChart } from "recharts";
import { RefreshCw } from "lucide-react";
import DateRangePicker from "../_date_range_picker";
import DrillDownModal from "../DrillDownModal";

const CUST_COLUMNS = [
  { key: "name", label: "Name" },
  { key: "mobile", label: "Mobile", mono: true },
  { key: "city", label: "City" },
  { key: "tier", label: "Tier" },
  { key: "lifetime_spend", label: "Lifetime ₹", align: "right", render: (v) => fmtINR(v) },
  { key: "visit_count", label: "Visits", align: "right" },
  { key: "points_balance", label: "Points", align: "right" },
];

const RISK_COLOR = { low: "#047857", medium: "#B45309", high: "#9F1239" };
const HEALTH_COLOR = {
  "Healthy": "#047857",
  "Slipping": "#B45309",
  "At Risk": "#DC2626",
  "Lost": "#7F1D1D",
  "Never transacted": "#737373",
};

export default function CustomerDashboard() {
  const navigate = useNavigate();
  const [range, setRange] = useState({ preset: "0", period_days: 0, start_date: "", end_date: "" });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [drill, setDrill] = useState(null);
  const openCustomers = (title, filter) => setDrill({
    title, subtitle: "Customers", collection: "customers", filter,
    sort: [["lifetime_spend", -1]], columns: CUST_COLUMNS,
    onRowClick: (r) => { setDrill(null); navigate(`/admin/customers/${r.id}`); },
  });
  const load = async () => {
    setLoading(true);
    try {
      const params = { period_days: range.period_days };
      if (range.start_date && range.end_date) {
        params.start_date = range.start_date;
        params.end_date = range.end_date;
      }
      const r = await api.get("/analytics/customer-dashboard", { params });
      setData(r.data);
    } finally { setLoading(false); }
  };
  const reload = () => { setError(null); load().catch((e) => setError(e?.response?.data?.detail || e?.message || "Failed to load")); };
  useEffect(() => { reload(); /* eslint-disable-next-line */ }, [range]);
  if (error && !data) return <DashboardError error={error} onRetry={reload} title="Customer Analytics" />;
  if (!data) return <div className="p-10 text-neutral-500">Loading…</div>;
  const totalCust = data.churn_distribution.reduce((s, r) => s + r.count, 0);
  const life = data.lifecycle_split || { one_timer: { count: 0, lifetime_spend: 0 }, repeat: { count: 0, lifetime_spend: 0 } };
  const lifeTotal = life.one_timer.count + life.repeat.count;
  const lifePct = (n) => lifeTotal ? (n / lifeTotal) * 100 : 0;
  return (
    <div data-testid="customer-dashboard">
      <PageHeader
        title="Customer Analytics"
        subtitle="WHO IS KAZO · LIVE"
        actions={
          <>
            <DateRangePicker value={range} onChange={setRange} testid="cust-date-range" />
            <button className="k-btn k-btn-outline k-btn-sm" onClick={load} data-testid="cust-refresh">
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
            </button>
          </>
        }
      />
      <div className="p-8 space-y-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KPICard label="Total Customers" value={fmtNum(totalCust)} accent="indigo" testid="kpi-total-cust" onClick={() => openCustomers("All Customers", {})} />
          <KPICard label="High-Risk Churn" value={fmtNum(data.churn_distribution.find(c => c.risk === "high")?.count || 0)} accent="rose" testid="kpi-high-risk" onClick={() => openCustomers("High-Risk Churn", { churn_risk: "high" })} />
          <KPICard label="One-Time Buyers" value={fmtNum(life.one_timer.count)} hint={`${lifePct(life.one_timer.count).toFixed(1)}% of base · ${fmtINR(life.one_timer.lifetime_spend)} spend`} accent="amber" testid="kpi-one-time"
            onClick={() => openCustomers("One-Time Buyers", { visit_count: 1 })}
            info="ONE-TIME BUYERS — loyalty customers who have placed exactly 1 bill in their lifetime. The unconverted majority — best targets for the second-purchase nudge." />
          <KPICard label="Top City" value={data.city_distribution[0]?.city || "—"} hint={fmtINR(data.city_distribution[0]?.spend)} accent="teal" testid="kpi-top-city" onClick={() => data.city_distribution[0]?.city && openCustomers(`Customers · ${data.city_distribution[0].city}`, { city: data.city_distribution[0].city })} />
        </div>

        {/* Lifecycle split — One-timer vs Repeat (docx #11) */}
        <div className="chart-card p-5" data-accent="indigo" data-testid="cust-lifecycle-split">
          <SectionHeading eyebrow="LIFECYCLE BIFURCATION" title="One-time vs Repeat buyers" accent="indigo" />
          <div className="grid md:grid-cols-2 gap-4 mt-4">
            <div className="border border-amber-200 bg-amber-50/50 p-5 min-w-0" data-testid="lifecycle-one-timer">
              <div className="text-[10px] uppercase tracking-[0.3em] text-amber-800 font-medium mb-2">ONE-TIME BUYERS</div>
              <div className="font-display hero-number text-amber-900" title={String(life.one_timer.count ?? "")}>{fmtNum(life.one_timer.count)}</div>
              <div className="mt-2 text-sm text-neutral-600">
                <span className="font-mono">{lifePct(life.one_timer.count).toFixed(1)}%</span> of loyalty base · contributing <span className="font-mono">{fmtINR(life.one_timer.lifetime_spend)}</span> lifetime spend
              </div>
              <div className="mt-3 h-2 bg-white border border-amber-200">
                <div className="h-full bg-amber-500" style={{ width: `${lifePct(life.one_timer.count)}%` }} />
              </div>
            </div>
            <div className="border border-emerald-200 bg-emerald-50/50 p-5 min-w-0" data-testid="lifecycle-repeat">
              <div className="text-[10px] uppercase tracking-[0.3em] text-emerald-800 font-medium mb-2">REPEAT BUYERS</div>
              <div className="font-display hero-number text-emerald-900" title={String(life.repeat.count ?? "")}>{fmtNum(life.repeat.count)}</div>
              <div className="mt-2 text-sm text-neutral-600">
                <span className="font-mono">{lifePct(life.repeat.count).toFixed(1)}%</span> of loyalty base · contributing <span className="font-mono">{fmtINR(life.repeat.lifetime_spend)}</span> lifetime spend
              </div>
              <div className="mt-3 h-2 bg-white border border-emerald-200">
                <div className="h-full bg-emerald-500" style={{ width: `${lifePct(life.repeat.count)}%` }} />
              </div>
            </div>
          </div>
        </div>

        <div className="grid lg:grid-cols-2 gap-4">
          {/* Customer Health Distribution — replaces churn pie (was rendering null) */}
          <div className="chart-card p-5" data-accent="rose" data-testid="cust-health-distribution">
            <SectionHeading eyebrow="HEALTH DISTRIBUTION" title="Customers by recency of last bill" accent="rose" />
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie data={(data.health_distribution || []).filter(d => d.count > 0)} dataKey="count" nameKey="bucket" cx="50%" cy="50%" outerRadius={90} innerRadius={50} paddingAngle={2} label={(p) => `${p.bucket}: ${p.count}`}>
                  {(data.health_distribution || []).filter(d => d.count > 0).map((d, i) => <Cell key={i} fill={HEALTH_COLOR[d.bucket] || CHART_SERIES[i]} />)}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
            <div className="text-[10px] text-neutral-500 text-center mt-1">Healthy: ≤30d · Slipping: 31-90d · At Risk: 91-180d · Lost: 180d+</div>
          </div>

          {/* One-timer Recency — addresses docx #22 */}
          <div className="chart-card p-5" data-accent="amber" data-testid="cust-one-timer-recency">
            <SectionHeading eyebrow="ONE-TIMER RECENCY" title="When did one-time buyers last visit?" accent="amber" />
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={data.one_timer_recency_distribution || []}>
                <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                <XAxis dataKey="bucket" stroke="#64748b" fontSize={11} />
                <YAxis stroke="#64748b" fontSize={11} />
                <Tooltip />
                <Bar dataKey="count" fill="#B45309" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
            <div className="text-[10px] text-neutral-500 text-center mt-1">Recency = days since their single bill. The 91-180d cohort is your highest-ROI winback target.</div>
          </div>

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
      <DrillDownModal open={!!drill} onClose={() => setDrill(null)} {...(drill || {})} />

    </div>
  );
}
