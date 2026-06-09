import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader, KPICard, SectionHeading, CHART_SERIES, mongoDateFilter, DashboardError } from "../_shared";
import { fmtINR, fmtNum } from "@/lib/format";
import { LineChart, Line, BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid, PieChart, Pie, Cell, Area, AreaChart } from "recharts";
import DateRangePicker from "../_date_range_picker";
import DrillDownModal from "../DrillDownModal";

const TXN_COLUMNS = [
  { key: "bill_date", label: "Bill Date" },
  { key: "bill_number", label: "Bill #", mono: true },
  { key: "customer_mobile", label: "Mobile", mono: true },
  { key: "store_name", label: "Store" },
  { key: "net_amount", label: "Net ₹", align: "right", render: (v) => fmtINR(v) },
  { key: "points_earned", label: "Pts", align: "right" },
];

export default function SalesDashboard() {
  const [range, setRange] = useState({ preset: "0", period_days: 0, start_date: "", end_date: "" });
  const [data, setData] = useState(null);
  const [trend, setTrend] = useState([]);
  const [error, setError] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [drill, setDrill] = useState(null);

  const openTxnDrill = () => setDrill({
    title: "Transactions",
    subtitle: range.label || (range.period_days === 0 ? "All time" : `Last ${range.period_days} days`),
    collection: "transactions",
    filter: mongoDateFilter("bill_date", range),
    sort: [["bill_date", -1]],
    columns: TXN_COLUMNS,
  });

  useEffect(() => {
    const params = { period_days: range.period_days };
    if (range.start_date && range.end_date) {
      params.start_date = range.start_date;
      params.end_date = range.end_date;
    }
    const trendParams = { period: range.period_days === 0 ? "all" : `${range.period_days}d` };
    if (range.start_date && range.end_date) {
      trendParams.start_date = range.start_date;
      trendParams.end_date = range.end_date;
    }
    Promise.all([
      api.get("/analytics/sales-dashboard", { params }),
      api.get("/dashboard/sales-trend", { params: trendParams }),
    ]).then(([d, t]) => { setData(d.data); setTrend(t.data); setError(null); })
      .catch((e) => setError(e?.response?.data?.detail || e?.message || "Failed to load"));
  }, [range, reloadKey]);

  if (error && !data) return <DashboardError error={error} onRetry={() => setReloadKey((k) => k + 1)} title="the Sales dashboard" />;
  if (!data) return <div className="p-10 text-neutral-500">Loading…</div>;

  const totalRevenue = trend.reduce((s, r) => s + r.net, 0);
  const totalTxns = trend.reduce((s, r) => s + r.txns, 0);
  const avgPerDay = trend.length ? totalRevenue / trend.length : 0;

  return (
    <div data-testid="sales-dashboard">
      <PageHeader title="Sales Dashboard" subtitle="REVENUE INTELLIGENCE · LIVE"
        actions={
          <DateRangePicker value={range} onChange={setRange} testid="sales-date-range" />
        } />
      <div className="p-8 space-y-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KPICard label="Total Revenue" value={fmtINR(totalRevenue)} accent="burgundy" testid="kpi-total-rev" onClick={openTxnDrill} />
          <KPICard label="Total Transactions" value={fmtNum(totalTxns)} accent="indigo" testid="kpi-total-txns" onClick={openTxnDrill} />
          <KPICard label="Avg / Day" value={fmtINR(avgPerDay)} accent="teal" testid="kpi-avg-day" onClick={openTxnDrill} />
          <KPICard label="Active Days" value={trend.length} accent="slate" testid="kpi-active-days" />
        </div>

        <div className="chart-card p-5" data-accent="burgundy">
          <SectionHeading eyebrow="REVENUE TREND" title={`Daily net revenue · ${range.label || (range.period_days === 0 ? "all time" : `last ${range.period_days} days`)}`} accent="burgundy" />
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={trend}>
              <defs>
                <linearGradient id="salesGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#571326" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="#571326" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
              <XAxis dataKey="date" stroke="#64748b" fontSize={11} tickFormatter={(d) => d?.slice(5)} />
              <YAxis stroke="#64748b" fontSize={11} tickFormatter={(v) => `₹${(v/1000).toFixed(0)}K`} />
              <Tooltip formatter={(v) => fmtINR(v)} />
              <Area type="monotone" dataKey="net" stroke="#571326" strokeWidth={2.5} fill="url(#salesGrad)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="grid lg:grid-cols-2 gap-4">
          <div className="chart-card p-5" data-accent="indigo">
            <SectionHeading eyebrow="HOURLY DISTRIBUTION" title="Sales by hour of day" accent="indigo" />
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={data.hourly}>
                <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                <XAxis dataKey="hour" stroke="#64748b" fontSize={11} tickFormatter={(h) => `${h}h`} />
                <YAxis stroke="#64748b" fontSize={11} tickFormatter={(v) => `₹${(v/1000).toFixed(0)}K`} />
                <Tooltip formatter={(v) => fmtINR(v)} />
                <Bar dataKey="net" radius={[3, 3, 0, 0]}>
                  {data.hourly.map((r, i) => {
                    const max = Math.max(...data.hourly.map((x) => x.net));
                    const alpha = max ? 0.35 + 0.65 * (r.net / max) : 0.35;
                    return <Cell key={i} fill={`rgba(30, 58, 138, ${alpha.toFixed(2)})`} />;
                  })}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="chart-card p-5" data-accent="teal">
            <SectionHeading eyebrow="DAY OF WEEK" title="Sales by weekday" accent="teal" />
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={data.weekday}>
                <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                <XAxis dataKey="day" stroke="#64748b" fontSize={11} />
                <YAxis stroke="#64748b" fontSize={11} tickFormatter={(v) => `₹${(v/1000).toFixed(0)}K`} />
                <Tooltip formatter={(v) => fmtINR(v)} />
                <Bar dataKey="net" radius={[3, 3, 0, 0]}>
                  {data.weekday.map((r, i) => {
                    const max = Math.max(...data.weekday.map((x) => x.net));
                    const alpha = max ? 0.35 + 0.65 * (r.net / max) : 0.35;
                    return <Cell key={i} fill={`rgba(14, 124, 123, ${alpha.toFixed(2)})`} />;
                  })}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="chart-card p-5" data-accent="amber">
            <SectionHeading eyebrow="PAYMENT MIX" title="By payment mode" accent="amber" />
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie data={data.payment_mix} dataKey="net" nameKey="mode" cx="50%" cy="50%" outerRadius={90} innerRadius={50} paddingAngle={2} label={(p) => p.mode}>
                  {data.payment_mix.map((_, i) => <Cell key={i} fill={CHART_SERIES[i % CHART_SERIES.length]} />)}
                </Pie>
                <Tooltip formatter={(v) => fmtINR(v)} />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="chart-card p-5" data-accent="rose">
            <SectionHeading eyebrow="DISCOUNT BUCKETS" title="Discount distribution" accent="rose" />
            <table className="data-table">
              <thead><tr><th>Bucket</th><th className="text-right">Txns</th><th className="text-right">Net</th></tr></thead>
              <tbody>
                {data.discount_distribution.map((r, i) => (
                  <tr key={r.bucket}>
                    <td>
                      <span className="inline-block w-2 h-2 rounded-full mr-2 align-middle" style={{ background: CHART_SERIES[i % CHART_SERIES.length] }} />
                      {r.bucket}
                    </td>
                    <td className="text-right font-mono">{fmtNum(r.count)}</td>
                    <td className="text-right font-mono">{fmtINR(r.net)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
      <DrillDownModal open={!!drill} onClose={() => setDrill(null)} {...(drill || {})} />

    </div>
  );
}
