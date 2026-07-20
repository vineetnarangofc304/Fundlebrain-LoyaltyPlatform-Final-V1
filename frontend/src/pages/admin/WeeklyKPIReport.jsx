/* Weekly KPI Report — the business KPI summary from the client's "Weekly_KPI"
   reference, bucketed by day / week / month so trends & graphs can be built on it.
   Orders (total/mapped/new/repeat/unmapped), customers, sales, discount, ATVs,
   frequencies, data-collection % and repeat/unmapped % — with filters, sorting,
   column show/hide, charts and CSV export. */
import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { requestExport } from "@/lib/exportClient";
import { PageHeader, KPICard, SectionHeading } from "./_shared";
import { ColumnPicker, ReportTable, useColumns } from "./reportkit";
import { fmtINR, fmtMoney2, fmtNum, fmtPct } from "@/lib/format";
import { Download, Search, RefreshCw } from "lucide-react";
import { ComposedChart, Line, Area, BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from "recharts";

const monthStart = () => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10); };
const today = () => new Date().toISOString().slice(0, 10);
const yearsAgo = (n) => { const d = new Date(); return new Date(d.getFullYear() - n, d.getMonth(), 1).toISOString().slice(0, 10); };

// fraction (0.9677) -> "96.8%" ; ratio (1.43) -> "1.43"
const pctCell = (v) => (v === null || v === undefined ? "—" : fmtPct(v * 100));
const ratioCell = (v) => (v === null || v === undefined ? "—" : Number(v).toFixed(2));

const COLS = [
  { key: "period", label: "Period", mono: true, sort: "period", default: true },
  { key: "number_of_stores", label: "Stores", num: true, sort: "number_of_stores", default: true },
  { key: "total_orders", label: "Total Orders", num: true, sort: "total_orders", default: true },
  { key: "mapped_orders", label: "Mapped Orders", num: true, sort: "mapped_orders", default: false },
  { key: "new_order", label: "New Orders", num: true, sort: "new_order", default: true },
  { key: "repeat_orders", label: "Repeat Orders", num: true, sort: "repeat_orders", default: true },
  { key: "unmapped_orders", label: "Unmapped Orders", num: true, sort: "unmapped_orders", default: false },
  { key: "overall_customers", label: "Overall Customers", num: true, sort: "overall_customers", default: true },
  { key: "new_customer_count", label: "New Customers", num: true, sort: "new_customer_count", default: true },
  { key: "repeat_customers", label: "Repeat Customers", num: true, sort: "repeat_customers", default: true },
  { key: "new_vs_repeat_ratio", label: "New vs Repeat", sort: "new_vs_repeat_ratio", render: ratioCell, default: false },
  { key: "overall_sales", label: "Overall Sales", money: true, sort: "overall_sales", default: true },
  { key: "total_discount", label: "Total Discount", money: true, sort: "total_discount", default: true },
  { key: "mapped_sales", label: "Mapped Sales", money: true, default: false },
  { key: "unmapped_sales", label: "Unmapped Sales", money: true, default: false },
  { key: "new_customer_value", label: "New Cust Value (Fresh)", money: true, default: false },
  { key: "repeat_customer_sales", label: "Repeat Customer Sales", money: true, default: false },
  { key: "data_collection", label: "Data Collection", sort: "data_collection", render: pctCell, default: true },
  { key: "business_atv", label: "Business ATV", money: true, sort: "business_atv", default: true },
  { key: "business_atv_10k", label: "Business ATV (>10k)", money: true, default: false },
  { key: "mapped_customer_atv", label: "Mapped Cust ATV", money: true, default: false },
  { key: "new_customer_atv", label: "New Cust ATV", money: true, default: false },
  { key: "repeat_customer_atv", label: "Repeat Cust ATV", money: true, default: false },
  { key: "mapped_customer_frequency", label: "Mapped Cust Frequency", render: ratioCell, default: false },
  { key: "repeat_customer_frequency", label: "Repeat Cust Frequency", render: ratioCell, default: false },
  { key: "pct_unmapped_order", label: "% Unmapped Orders", render: pctCell, default: false },
  { key: "pct_repeat_orders", label: "% Repeat Orders", sort: "pct_repeat_orders", render: pctCell, default: true },
];

export default function WeeklyKPIReport() {
  const [params, setParams] = useState({
    start_date: yearsAgo(1), end_date: today(), granularity: "week",
    zone: "", city: "", store_class: "", store_id: "",
    sort_by: "period", sort_dir: "asc",
  });
  const [data, setData] = useState({ rows: [], count: 0, granularity: "week" });
  const [opts, setOpts] = useState({ zones: [], cities: [], store_classes: [] });
  const [stores, setStores] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [exporting, setExporting] = useState(false);

  const { visible, toggle, reset } = useColumns(COLS, "kazo-weekly-cols");
  const set = (k, v) => setParams((p) => ({ ...p, [k]: v }));

  const cleanParams = useCallback(() => {
    const o = {};
    Object.entries(params).forEach(([k, v]) => { if (v === "" || v === false) return; o[k] = v; });
    return o;
  }, [params]);

  const fetchData = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const r = await api.get("/kpi-reports/weekly-kpi", { params: cleanParams() });
      setData(r.data);
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to load Weekly KPI");
    } finally { setLoading(false); }
  }, [cleanParams]);

  useEffect(() => {
    api.get("/kpi-reports/filter-options").then((r) => setOpts(r.data)).catch(() => {});
    api.get("/stores").then((r) => setStores(r.data || [])).catch(() => {});
  }, []);
  useEffect(() => { fetchData(); /* eslint-disable-next-line */ }, [params.sort_by, params.sort_dir, params.granularity]);

  const onSort = (sf) => setParams((p) => ({ ...p, sort_by: sf, sort_dir: p.sort_by === sf && p.sort_dir === "desc" ? "asc" : "desc" }));

  const exportCsv = async () => {
    setExporting(true);
    try {
      await requestExport({
        report_type: "weekly_kpi", params: cleanParams(), label: "Weekly KPI Report",
        known_total: data.count ?? (data.rows || []).length, filename: `weekly_kpi_${params.granularity}_${today()}.csv`,
      });
    } finally { setExporting(false); }
  };

  const rows = data.rows || [];
  const sum = (k) => rows.reduce((a, r) => a + (r[k] || 0), 0);
  const chart = [...rows].sort((a, b) => String(a.period).localeCompare(String(b.period)))
    .map((r) => ({ period: r.period, Sales: r.overall_sales, Orders: r.total_orders, New: r.new_order, Repeat: r.repeat_orders, ATV: r.business_atv }));
  const dedupeStores = (() => {
    const seen = new Set(); const out = [];
    for (const s of stores) { const k = String(s.name || s.code || s.id).toLowerCase().trim(); if (k && !seen.has(k)) { seen.add(k); out.push(s); } }
    return out;
  })();
  const selCls = "k-input w-full !py-1.5 text-sm";
  const lblCls = "text-[10px] uppercase tracking-[0.2em] text-neutral-500 mb-1 block";

  return (
    <div data-testid="weekly-kpi-report">
      <PageHeader title="Weekly KPI Report" subtitle="REPORTS · BUSINESS KPI TRENDS"
        actions={
          <div className="flex items-center gap-2">
            <ColumnPicker columns={COLS} visible={visible} toggle={toggle} reset={reset} testid="wkpi-cols" />
            <button onClick={exportCsv} disabled={exporting} className="k-btn k-btn-outline" data-testid="wkpi-export">
              <Download className={`w-3.5 h-3.5 ${exporting ? "animate-pulse" : ""}`} /> {exporting ? "Preparing…" : "Download CSV"}
            </button>
          </div>
        }
      />
      <div className="p-8 space-y-6">
        <div className="chart-card p-5 space-y-4" data-testid="wkpi-filters">
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <div><label className={lblCls}>Start date</label><input type="date" value={params.start_date} onChange={(e) => set("start_date", e.target.value)} className={selCls} data-testid="wkpi-start" /></div>
            <div><label className={lblCls}>End date</label><input type="date" value={params.end_date} onChange={(e) => set("end_date", e.target.value)} className={selCls} data-testid="wkpi-end" /></div>
            <div><label className={lblCls}>Group by</label>
              <select value={params.granularity} onChange={(e) => set("granularity", e.target.value)} className={selCls} data-testid="wkpi-granularity">
                <option value="day">Daily</option><option value="week">Weekly</option><option value="month">Monthly</option><option value="year">Yearly</option>
              </select></div>
            <div><label className={lblCls}>Zone</label>
              <select value={params.zone} onChange={(e) => set("zone", e.target.value)} className={selCls} data-testid="wkpi-zone">
                <option value="">All zones</option>{opts.zones.map((z) => <option key={z} value={z}>{z}</option>)}
              </select></div>
            <div><label className={lblCls}>Class</label>
              <select value={params.store_class} onChange={(e) => set("store_class", e.target.value)} className={selCls} data-testid="wkpi-class">
                <option value="">All classes</option>{opts.store_classes.map((c) => <option key={c} value={c}>{c}</option>)}
              </select></div>
            <div><label className={lblCls}>Store</label>
              <select value={params.store_id} onChange={(e) => set("store_id", e.target.value)} className={selCls} data-testid="wkpi-store">
                <option value="">All stores</option>{dedupeStores.map((s) => <option key={s.id} value={s.id}>{s.name || s.code}</option>)}
              </select></div>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <button onClick={() => { set("start_date", monthStart()); set("end_date", today()); }} className="k-btn k-btn-outline k-btn-sm" data-testid="wkpi-mtd">This month</button>
            <button onClick={() => { set("start_date", yearsAgo(1)); set("end_date", today()); }} className="k-btn k-btn-outline k-btn-sm" data-testid="wkpi-1y">1y</button>
            <div className="flex-1" />
            <button onClick={fetchData} disabled={loading} className="k-btn kazo-bg-burgundy text-white" data-testid="wkpi-apply">
              <Search className="w-3.5 h-3.5" /> {loading ? "Loading…" : "Apply"}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <KPICard label="Overall Sales" value={fmtINR(sum("overall_sales"))} fullValue={sum("overall_sales")} accent="burgundy" testid="wkpi-kpi-sales" />
          <KPICard label="Total Orders" value={fmtNum(sum("total_orders"))} accent="indigo" testid="wkpi-kpi-orders" />
          <KPICard label="New Orders" value={fmtNum(sum("new_order"))} accent="emerald" testid="wkpi-kpi-new" />
          <KPICard label="Repeat Orders" value={fmtNum(sum("repeat_orders"))} accent="teal" testid="wkpi-kpi-repeat" />
          <KPICard label="Total Discount" value={fmtINR(sum("total_discount"))} fullValue={sum("total_discount")} accent="amber" testid="wkpi-kpi-disc" />
          <KPICard label="Periods" value={fmtNum(rows.length)} accent="rose" testid="wkpi-kpi-periods" />
        </div>

        <div className="grid lg:grid-cols-2 gap-6">
          <div className="chart-card p-5" data-accent="burgundy" data-testid="wkpi-chart-sales">
            <SectionHeading eyebrow="Trend" title="Sales & ATV over time" accent="burgundy" />
            <ResponsiveContainer width="100%" height={320}>
              <ComposedChart data={chart}>
                <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                <XAxis dataKey="period" stroke="#64748b" fontSize={9} angle={-25} textAnchor="end" height={60} interval="preserveStartEnd" />
                <YAxis yAxisId="l" stroke="#64748b" fontSize={10} tickFormatter={(v) => `₹${(v / 100000).toFixed(0)}L`} />
                <YAxis yAxisId="r" orientation="right" stroke="#64748b" fontSize={10} />
                <Tooltip formatter={(v, n) => (n === "ATV" ? fmtMoney2(v) : n === "Sales" ? fmtMoney2(v) : fmtNum(v))} />
                <Legend />
                <Area yAxisId="l" type="monotone" dataKey="Sales" fill="#571326" stroke="#571326" fillOpacity={0.12} />
                <Line yAxisId="r" type="monotone" dataKey="ATV" stroke="#0E7C7B" strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-card p-5" data-accent="teal" data-testid="wkpi-chart-orders">
            <SectionHeading eyebrow="Acquisition" title="New vs Repeat Orders" accent="teal" />
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={chart}>
                <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                <XAxis dataKey="period" stroke="#64748b" fontSize={9} angle={-25} textAnchor="end" height={60} interval="preserveStartEnd" />
                <YAxis stroke="#64748b" fontSize={10} />
                <Tooltip /><Legend />
                <Bar dataKey="New" stackId="a" fill="#0E7C7B" />
                <Bar dataKey="Repeat" stackId="a" fill="#571326" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="chart-card p-5 overflow-x-auto" data-accent="indigo" data-testid="wkpi-table-card">
          <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
            <h3 className="font-display text-xl">{data.count} <span className="text-sm font-normal text-neutral-500">{data.granularity} periods</span></h3>
            <button onClick={fetchData} className="text-xs px-2 py-1 border border-neutral-300 hover:bg-neutral-50 flex items-center gap-1">
              <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} /> Refresh
            </button>
          </div>
          {error ? (
            <div className="text-sm text-rose-700 py-12 text-center" data-testid="wkpi-error">{error}</div>
          ) : rows.length === 0 ? (
            <div className="text-sm text-neutral-500 py-12 text-center">{loading ? "Loading…" : "No data for the current filters."}</div>
          ) : (
            <ReportTable columns={COLS} rows={rows} visible={visible}
              sortBy={params.sort_by} sortDir={params.sort_dir} onSort={onSort}
              testid="wkpi-table" rowKey={(r) => r.period} />
          )}
        </div>
      </div>
    </div>
  );
}
