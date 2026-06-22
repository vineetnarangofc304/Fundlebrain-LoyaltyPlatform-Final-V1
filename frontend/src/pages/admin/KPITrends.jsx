/* Weekly / Monthly KPI Trends — sales, bills, customers, discount and new-vs-repeat
   bucketed by day / week / month with charts + CSV export.
   (Built from the client's "Weekly_KPI" reference format.) */
import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { PageHeader, KPICard, SectionHeading } from "./_shared";
import { fmtINR, fmtNum, fmtMoney2 } from "@/lib/format";
import { Download, Search, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { AreaChart, Area, BarChart, Bar, LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from "recharts";

const yearsAgo = (n) => { const d = new Date(); return new Date(d.getFullYear() - n, d.getMonth(), d.getDate()).toISOString().slice(0, 10); };
const today = () => new Date().toISOString().slice(0, 10);

export default function KPITrends() {
  const [params, setParams] = useState({
    start_date: yearsAgo(1), end_date: today(), granularity: "month",
    zone: "", city: "", store_class: "",
  });
  const [points, setPoints] = useState([]);
  const [opts, setOpts] = useState({ zones: [], cities: [], store_classes: [] });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const set = (k, v) => setParams((p) => ({ ...p, [k]: v }));
  const cleanParams = useCallback(() => {
    const o = {};
    Object.entries(params).forEach(([k, v]) => { if (v === "") return; o[k] = v; });
    return o;
  }, [params]);

  const fetchData = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const r = await api.get("/kpi-reports/trend", { params: cleanParams() });
      setPoints(r.data.points || []);
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to load trend");
    } finally { setLoading(false); }
  }, [cleanParams]);

  useEffect(() => {
    api.get("/kpi-reports/filter-options").then((r) => setOpts(r.data)).catch(() => {});
  }, []);
  useEffect(() => { fetchData(); /* eslint-disable-next-line */ }, [params.granularity]);

  const exportCsv = () => {
    if (!points.length) { toast.error("Nothing to export"); return; }
    const headers = ["Period", "Sales", "Discount", "Bills", "Returns", "New", "Repeat", "Customers"];
    const lines = [headers.join(",")].concat(points.map((p) =>
      [p.period, p.sales, p.discount, p.bills, p.returns, p.new, p.repeat, p.customers].join(",")));
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = `kpi_trend_${params.granularity}_${today()}.csv`; a.click();
    window.URL.revokeObjectURL(url);
    toast.success("Export downloaded");
  };

  const totals = points.reduce((a, p) => ({
    sales: a.sales + p.sales, discount: a.discount + p.discount, bills: a.bills + p.bills, returns: a.returns + p.returns,
  }), { sales: 0, discount: 0, bills: 0, returns: 0 });
  const avgSales = points.length ? totals.sales / points.length : 0;
  const selCls = "k-input w-full !py-1.5 text-sm";
  const lblCls = "text-[10px] uppercase tracking-[0.2em] text-neutral-500 mb-1 block";

  return (
    <div data-testid="kpi-trends">
      <PageHeader title="KPI Trends" subtitle="REPORTS · WEEKLY / MONTHLY"
        actions={
          <button onClick={exportCsv} className="k-btn k-btn-outline" data-testid="trend-export">
            <Download className="w-3.5 h-3.5" /> Download CSV
          </button>
        }
      />
      <div className="p-8 space-y-6">
        {/* Filters */}
        <div className="chart-card p-5 space-y-4" data-testid="trend-filters">
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <div><label className={lblCls}>Start date</label><input type="date" value={params.start_date} onChange={(e) => set("start_date", e.target.value)} className={selCls} data-testid="trend-start" /></div>
            <div><label className={lblCls}>End date</label><input type="date" value={params.end_date} onChange={(e) => set("end_date", e.target.value)} className={selCls} data-testid="trend-end" /></div>
            <div><label className={lblCls}>Granularity</label>
              <select value={params.granularity} onChange={(e) => set("granularity", e.target.value)} className={selCls} data-testid="trend-granularity">
                <option value="day">Daily</option>
                <option value="week">Weekly</option>
                <option value="month">Monthly</option>
              </select></div>
            <div><label className={lblCls}>Zone</label>
              <select value={params.zone} onChange={(e) => set("zone", e.target.value)} className={selCls} data-testid="trend-zone">
                <option value="">All zones</option>{opts.zones.map((z) => <option key={z} value={z}>{z}</option>)}
              </select></div>
            <div><label className={lblCls}>Class</label>
              <select value={params.store_class} onChange={(e) => set("store_class", e.target.value)} className={selCls} data-testid="trend-class">
                <option value="">All classes</option>{opts.store_classes.map((c) => <option key={c} value={c}>{c}</option>)}
              </select></div>
            <div><label className={lblCls}>City</label>
              <select value={params.city} onChange={(e) => set("city", e.target.value)} className={selCls} data-testid="trend-city">
                <option value="">All cities</option>{opts.cities.map((c) => <option key={c} value={c}>{c}</option>)}
              </select></div>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex-1" />
            <button onClick={fetchData} disabled={loading} className="k-btn kazo-bg-burgundy text-white" data-testid="trend-apply">
              <Search className="w-3.5 h-3.5" /> {loading ? "Loading…" : "Apply"}
            </button>
          </div>
        </div>

        {/* KPI tiles */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          <KPICard label="Total Sales" value={fmtINR(totals.sales)} fullValue={totals.sales} accent="burgundy" testid="trend-kpi-sales" />
          <KPICard label="Avg / period" value={fmtINR(avgSales)} fullValue={avgSales} accent="champagne" testid="trend-kpi-avg" />
          <KPICard label="Fresh Bills" value={fmtNum(totals.bills)} accent="indigo" testid="trend-kpi-bills" />
          <KPICard label="Return Bills" value={fmtNum(totals.returns)} accent="rose" testid="trend-kpi-returns" />
          <KPICard label="Periods" value={fmtNum(points.length)} accent="teal" testid="trend-kpi-periods" />
        </div>

        {error ? (
          <div className="chart-card p-5 text-sm text-rose-700 py-12 text-center" data-testid="trend-error">{error}</div>
        ) : (
          <>
            <div className="chart-card p-5" data-accent="burgundy" data-testid="trend-chart-sales">
              <div className="flex items-center justify-between mb-1">
                <SectionHeading eyebrow={params.granularity} title="Sales Trend" accent="burgundy" />
                <button onClick={fetchData} className="text-xs px-2 py-1 border border-neutral-300 hover:bg-neutral-50 flex items-center gap-1">
                  <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} /> Refresh
                </button>
              </div>
              <ResponsiveContainer width="100%" height={320}>
                <AreaChart data={points}>
                  <defs>
                    <linearGradient id="trendGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#571326" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#571326" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                  <XAxis dataKey="period" stroke="#64748b" fontSize={10} />
                  <YAxis stroke="#64748b" fontSize={10} tickFormatter={(v) => `₹${(v / 100000).toFixed(0)}L`} />
                  <Tooltip formatter={(v) => fmtMoney2(v)} />
                  <Area type="monotone" dataKey="sales" stroke="#571326" strokeWidth={2.5} fill="url(#trendGrad)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            <div className="grid lg:grid-cols-2 gap-6">
              <div className="chart-card p-5" data-accent="indigo" data-testid="trend-chart-bills">
                <SectionHeading eyebrow="Volume" title="Bills vs Returns" accent="indigo" />
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={points}>
                    <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                    <XAxis dataKey="period" stroke="#64748b" fontSize={10} />
                    <YAxis stroke="#64748b" fontSize={10} tickFormatter={(v) => fmtNum(v)} />
                    <Tooltip formatter={(v) => fmtNum(v)} /><Legend />
                    <Bar dataKey="bills" name="Fresh Bills" fill="#1E3A8A" radius={[3, 3, 0, 0]} />
                    <Bar dataKey="returns" name="Returns" fill="#9F1239" radius={[3, 3, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="chart-card p-5" data-accent="teal" data-testid="trend-chart-newrepeat">
                <SectionHeading eyebrow="Acquisition" title="New vs Repeat & Customers" accent="teal" />
                <ResponsiveContainer width="100%" height={280}>
                  <LineChart data={points}>
                    <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                    <XAxis dataKey="period" stroke="#64748b" fontSize={10} />
                    <YAxis stroke="#64748b" fontSize={10} tickFormatter={(v) => fmtNum(v)} />
                    <Tooltip formatter={(v) => fmtNum(v)} /><Legend />
                    <Line type="monotone" dataKey="new" name="New" stroke="#0E7C7B" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="repeat" name="Repeat" stroke="#571326" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="customers" name="Customers" stroke="#B45309" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
