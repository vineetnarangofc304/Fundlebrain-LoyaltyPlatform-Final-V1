import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { LineChart, Line, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, PieChart, Pie, Cell, Legend, CartesianGrid } from "recharts";
import api from "@/lib/api";
import { fmtINR, fmtNum, fmtPct } from "@/lib/format";
import { PageHeader, KPICard } from "./_shared";
import { RefreshCw } from "lucide-react";

const COLORS = ["#0F172A", "#571326", "#C7A76D", "#94A3B8", "#1f2937", "#7c2d4a"];

export default function ExecutiveCockpit() {
  const navigate = useNavigate();
  const [period, setPeriod] = useState("30d");
  const [kpis, setKpis] = useState(null);
  const [trend, setTrend] = useState([]);
  const [stores, setStores] = useState([]);
  const [cats, setCats] = useState([]);
  const [tiers, setTiers] = useState([]);
  const [skus, setSkus] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [k, t, s, c, ti, sk] = await Promise.all([
        api.get("/dashboard/kpis", { params: { period } }),
        api.get("/dashboard/sales-trend", { params: { period } }),
        api.get("/dashboard/store-performance", { params: { period } }),
        api.get("/dashboard/category-mix", { params: { period } }),
        api.get("/dashboard/tier-distribution"),
        api.get("/dashboard/top-skus", { params: { period, limit: 8 } }),
      ]);
      setKpis(k.data);
      setTrend(t.data);
      setStores(s.data);
      setCats(c.data);
      setTiers(ti.data);
      setSkus(sk.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [period]);
  useEffect(() => {
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, [period]);

  if (loading && !kpis) return <div className="p-10 text-neutral-500">Loading dashboard…</div>;
  if (!kpis) return null;

  return (
    <div data-testid="executive-cockpit">
      <PageHeader
        title="Executive Cockpit"
        subtitle="REAL-TIME COMMAND CENTER"
        actions={
          <>
            <select className="k-input !w-auto !py-1.5" value={period} onChange={(e) => setPeriod(e.target.value)} data-testid="period-selector">
              <option value="today">Today</option>
              <option value="7d">Last 7 days</option>
              <option value="30d">Last 30 days</option>
              <option value="90d">Last 90 days</option>
              <option value="mtd">Month to date</option>
              <option value="ytd">Year to date</option>
            </select>
            <button className="k-btn k-btn-outline k-btn-sm" onClick={load} data-testid="refresh-btn"><RefreshCw className="w-3.5 h-3.5" /> Refresh</button>
          </>
        }
      />

      <div className="p-8 space-y-8">
        {/* Top KPI grid */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <KPICard label="Total Customers" value={fmtNum(kpis.customers.total)} hint="Across all stores" onClick={() => navigate("/admin/customers")} testid="kpi-total-customers" />
          <KPICard label="Active Customers" value={fmtNum(kpis.customers.active)} hint={`${period}`} onClick={() => navigate("/admin/dashboards/customers")} testid="kpi-active-customers" />
          <KPICard label="New Customers" value={fmtNum(kpis.customers.new)} hint={`${period}`} onClick={() => navigate("/admin/dashboards/customers")} testid="kpi-new-customers" />
          <KPICard label="Repeat Customers" value={fmtNum(kpis.customers.repeat)} hint="≥2 visits" onClick={() => navigate("/admin/customers")} testid="kpi-repeat-customers" />
          <KPICard label="Churned" value={fmtNum(kpis.customers.churned)} hint=">180 days" onClick={() => navigate("/admin/customers?churn_risk=high")} testid="kpi-churned-customers" />
          <KPICard label="Loyalty Penetration" value={fmtPct(kpis.loyalty.penetration_pct)} onClick={() => navigate("/admin/dashboards/loyalty")} testid="kpi-loyalty-pct" />
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <KPICard label="Net Sales" value={fmtINR(kpis.sales.net)} delta={kpis.sales.delta_pct} onClick={() => navigate("/admin/dashboards/sales")} testid="kpi-net-sales" />
          <KPICard label="Gross Sales" value={fmtINR(kpis.sales.gross)} onClick={() => navigate("/admin/dashboards/sales")} testid="kpi-gross-sales" />
          <KPICard label="Transactions" value={fmtNum(kpis.sales.txn_count)} delta={kpis.sales.txn_delta_pct} onClick={() => navigate("/admin/reports")} testid="kpi-txns" />
          <KPICard label="AOV" value={fmtINR(kpis.sales.aov)} hint="₹/transaction" onClick={() => navigate("/admin/dashboards/sales")} testid="kpi-aov" />
          <KPICard label="UPT" value={kpis.sales.upt?.toFixed(2)} hint="Units per txn" onClick={() => navigate("/admin/dashboards/sales")} testid="kpi-upt" />
          <KPICard label="Discount" value={fmtINR(kpis.sales.discount)} onClick={() => navigate("/admin/dashboards/sales")} testid="kpi-discount" />
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <KPICard label="Points Issued" value={fmtNum(kpis.loyalty.points_issued)} onClick={() => navigate("/admin/dashboards/loyalty")} testid="kpi-points-issued" />
          <KPICard label="Points Redeemed" value={fmtNum(kpis.loyalty.points_redeemed)} onClick={() => navigate("/admin/dashboards/loyalty")} testid="kpi-points-redeemed" />
          <KPICard label="Outstanding Liability" value={fmtINR(kpis.loyalty.outstanding_liability_inr)} hint="Points × ₹0.25" onClick={() => navigate("/admin/dashboards/loyalty")} testid="kpi-liability" />
          <KPICard label="Repeat Rate" value={fmtPct(kpis.loyalty.repeat_rate_pct)} onClick={() => navigate("/admin/dashboards/customers")} testid="kpi-repeat-rate" />
          <KPICard label="Churn %" value={fmtPct(kpis.loyalty.churn_pct)} onClick={() => navigate("/admin/dashboards/customers")} testid="kpi-churn-pct" />
          <KPICard label="Coupons Used" value={fmtNum(kpis.campaigns.coupon_usage)} onClick={() => navigate("/admin/coupons")} testid="kpi-coupons" />
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KPICard label="Campaign Revenue" value={fmtINR(kpis.campaigns.revenue_generated)} onClick={() => navigate("/admin/dashboards/campaigns")} testid="kpi-camp-revenue" />
          <KPICard label="NPS Score" value={kpis.nps.score == null ? "N/A" : kpis.nps.score} onClick={() => navigate("/admin/dashboards/nps")} testid="kpi-nps" />
          <KPICard label="Open Complaints" value={fmtNum(kpis.nps.complaints_open)} onClick={() => navigate("/admin/tickets?status=open")} testid="kpi-complaints" />
          <KPICard label="API Health" value={fmtPct(kpis.api.health_pct, 2)} hint={`${kpis.api.failed} failed / ${kpis.api.total}`} onClick={() => navigate("/admin/api-monitor")} testid="kpi-api-health" />
        </div>

        {/* Charts */}
        <div className="grid lg:grid-cols-3 gap-4">
          <div className="bg-white border border-black/10 p-5 lg:col-span-2" data-testid="chart-sales-trend">
            <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-1">SALES TREND</div>
            <h3 className="font-display text-xl mb-4">Net revenue per day</h3>
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={trend}>
                <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                <XAxis dataKey="date" stroke="#64748b" fontSize={11} tickFormatter={(d) => d?.slice(5)} />
                <YAxis stroke="#64748b" fontSize={11} tickFormatter={(v) => `₹${(v/1000).toFixed(0)}K`} />
                <Tooltip contentStyle={{ borderRadius: 2, fontSize: 12 }} formatter={(v) => fmtINR(v)} />
                <Line type="monotone" dataKey="net" stroke="#571326" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white border border-black/10 p-5" data-testid="chart-tier">
            <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-1">LOYALTY TIERS</div>
            <h3 className="font-display text-xl mb-4">Customer distribution</h3>
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={tiers} dataKey="count" nameKey="tier" cx="50%" cy="50%" outerRadius={75} label={(p) => p.tier}>
                  {tiers.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="grid lg:grid-cols-2 gap-4">
          <div className="bg-white border border-black/10 p-5" data-testid="chart-category-mix">
            <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-1">CATEGORY MIX</div>
            <h3 className="font-display text-xl mb-4">Revenue by category</h3>
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={cats}>
                <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                <XAxis dataKey="category" stroke="#64748b" fontSize={11} angle={-25} textAnchor="end" height={70} />
                <YAxis stroke="#64748b" fontSize={11} tickFormatter={(v) => `₹${(v/1000).toFixed(0)}K`} />
                <Tooltip formatter={(v) => fmtINR(v)} />
                <Bar dataKey="revenue" fill="#571326" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white border border-black/10 p-5" data-testid="chart-top-skus">
            <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-1">BESTSELLERS</div>
            <h3 className="font-display text-xl mb-4">Top SKUs by revenue</h3>
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr><th>SKU</th><th>Name</th><th>Category</th><th className="text-right">Qty</th><th className="text-right">Revenue</th></tr>
                </thead>
                <tbody>
                  {skus.map((s) => (
                    <tr key={s.sku}>
                      <td className="font-mono text-xs">{s.sku}</td>
                      <td>{s.name}</td>
                      <td><span className="pill pill-neutral">{s.category}</span></td>
                      <td className="text-right font-mono">{s.quantity}</td>
                      <td className="text-right font-mono">{fmtINR(s.revenue)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Store performance */}
        <div className="bg-white border border-black/10 p-5" data-testid="store-performance-table">
          <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-1">STORE PERFORMANCE</div>
          <h3 className="font-display text-xl mb-4">Top stores ({period})</h3>
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead><tr><th>Store</th><th>City</th><th className="text-right">Net Sales</th><th className="text-right">Txns</th><th className="text-right">Unique Customers</th><th className="text-right">AOV</th></tr></thead>
              <tbody>
                {stores.map((s, i) => (
                  <tr key={s.store_id || i}>
                    <td>{s.store_name}</td>
                    <td>{s.city}</td>
                    <td className="text-right font-mono">{fmtINR(s.net)}</td>
                    <td className="text-right font-mono">{fmtNum(s.txns)}</td>
                    <td className="text-right font-mono">{fmtNum(s.unique_customers)}</td>
                    <td className="text-right font-mono">{fmtINR(s.aov)}</td>
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
