/* Store-wise KPI Report — the FULL per-outlet matrix from the client's
   "Store_wise_KPI" reference: sales/discount, fresh & return bills/value/discount,
   and the New / Repeat / Mapped / Unmapped × Fresh / Return matrix (txns, value, ATV)
   plus Overall / New / Existing customer counts. Filters, sorting, column show/hide,
   charts and CSV export. */
import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { requestExport } from "@/lib/exportClient";
import { PageHeader, KPICard, SectionHeading, CHART_SERIES } from "./_shared";
import { ColumnPicker, ReportTable, useColumns } from "./reportkit";
import { fmtINR, fmtMoney2, fmtNum } from "@/lib/format";
import { Download, Search, RefreshCw } from "lucide-react";
import { BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid, Cell, Legend } from "recharts";

const monthStart = () => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10); };
const today = () => new Date().toISOString().slice(0, 10);
const yearsAgo = (n) => { const d = new Date(); return new Date(d.getFullYear() - n, d.getMonth(), 1).toISOString().slice(0, 10); };

const M = (key, label, extra = {}) => ({ key, label, money: true, sort: key, default: false, ...extra });
const N = (key, label, extra = {}) => ({ key, label, num: true, sort: key, default: false, ...extra });

// Full matrix (matches the backend STORE_MATRIX_COLUMNS). Core columns visible by
// default; the deep New/Repeat/Mapped/Unmapped × Fresh/Return breakdown is available
// via the Columns picker so the table stays readable.
const COLS = [
  { key: "store_name", label: "Outlet", sort: "store_name", default: true },
  { key: "email", label: "Email", mono: true, default: true },
  { key: "store_code", label: "Store Code", mono: true, sort: "store_code", default: true },
  { key: "store_class", label: "Class", sort: "store_class", default: true },
  { key: "zone", label: "Zone", sort: "zone", default: false },
  { key: "city", label: "City", sort: "city", default: false },
  M("overall_sales", "Overall Sales", { default: true }),
  M("total_discount", "Total Discount", { default: true }),
  N("fresh_bills", "Fresh Bills", { default: true }),
  M("fresh_value", "Fresh Bill Value", { default: true }),
  M("fresh_discount", "Fresh Bill Discount"),
  N("return_bills", "Return Bills", { default: true }),
  M("return_value", "Return Bills Value", { default: true }),
  M("return_discount", "Return Bills Discount"),
  N("new_fresh_txn", "New Cust (Fresh Txn)", { default: true }),
  N("new_return_txn", "New Cust (Return Txn)"),
  M("new_fresh_value", "New Cust Value (Fresh)"),
  M("new_return_value", "New Cust Value (Return)"),
  N("repeat_fresh_txn", "Repeat Cust (Fresh Txn)", { default: true }),
  N("repeat_return_txn", "Repeat Cust Txn (Return)"),
  M("repeat_fresh_value", "Repeat Cust Value (Fresh)"),
  M("repeat_return_value", "Repeat Cust Value (Return)"),
  M("new_fresh_atv", "New Cust ATV (Fresh)"),
  M("new_return_atv", "New Cust ATV (Return)"),
  M("repeat_fresh_atv", "Repeat Cust ATV (Fresh)"),
  M("repeat_return_atv", "Repeat Cust ATV (Return)"),
  N("mapped_fresh_txn", "Mapped Cust Txn (Fresh)"),
  N("mapped_return_txn", "Mapped Cust Txn (Return)"),
  M("mapped_fresh_value", "Mapped Cust Value (Fresh)"),
  M("mapped_return_value", "Mapped Cust Value (Return)"),
  M("mapped_fresh_atv", "Mapped Cust ATV (Fresh)"),
  M("mapped_return_atv", "Mapped Cust ATV (Return)"),
  N("unmapped_fresh_txn", "Unmapped Cust Txn (Fresh)"),
  N("unmapped_return_txn", "Unmapped Cust Txn (Return)"),
  M("unmapped_fresh_value", "Unmapped Cust Value (Fresh)"),
  M("unmapped_return_value", "Unmapped Cust Value (Return)"),
  M("unmapped_fresh_atv", "Unmapped Cust ATV (Fresh)"),
  M("unmapped_return_atv", "Unmapped Cust ATV (Return)"),
  N("overall_customers", "Overall Customers", { default: true }),
  N("new_customer_count", "New Customer Count", { default: true }),
  N("existing_customers", "Existing Customers", { default: true }),
];

export default function StoreWiseKPIReport() {
  const [params, setParams] = useState({
    start_date: yearsAgo(1), end_date: today(),
    zone: "", city: "", store_class: "", store_id: "",
    sort_by: "overall_sales", sort_dir: "desc",
  });
  const [data, setData] = useState({ rows: [], totals: {}, count: 0 });
  const [opts, setOpts] = useState({ zones: [], cities: [], store_classes: [] });
  const [stores, setStores] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [exporting, setExporting] = useState(false);

  const { visible, toggle, reset } = useColumns(COLS, "kazo-storewise-cols");
  const set = (k, v) => setParams((p) => ({ ...p, [k]: v }));

  const cleanParams = useCallback(() => {
    const o = {};
    Object.entries(params).forEach(([k, v]) => { if (v === "" || v === false) return; o[k] = v; });
    return o;
  }, [params]);

  const fetchData = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const r = await api.get("/kpi-reports/store-wise-kpi", { params: cleanParams() });
      setData(r.data);
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to load Store-wise KPI");
    } finally { setLoading(false); }
  }, [cleanParams]);

  useEffect(() => {
    api.get("/kpi-reports/filter-options").then((r) => setOpts(r.data)).catch(() => {});
    api.get("/stores").then((r) => setStores(r.data || [])).catch(() => {});
  }, []);
  useEffect(() => { fetchData(); /* eslint-disable-next-line */ }, [params.sort_by, params.sort_dir]);

  const onSort = (sf) => setParams((p) => ({ ...p, sort_by: sf, sort_dir: p.sort_by === sf && p.sort_dir === "desc" ? "asc" : "desc" }));

  const exportCsv = async () => {
    setExporting(true);
    try {
      await requestExport({
        report_type: "store_wise_kpi", params: cleanParams(), label: "Store-wise KPI Report",
        known_total: data.count ?? (data.rows || []).length, filename: `store_wise_kpi_${today()}.csv`,
      });
    } finally { setExporting(false); }
  };

  const t = data.totals || {};
  const dedupeStores = (() => {
    const seen = new Set(); const out = [];
    for (const s of stores) { const k = String(s.name || s.code || s.id).toLowerCase().trim(); if (k && !seen.has(k)) { seen.add(k); out.push(s); } }
    return out;
  })();
  const topSales = [...(data.rows || [])].sort((a, b) => b.overall_sales - a.overall_sales).slice(0, 10)
    .map((r) => ({ name: (r.store_name || r.store_code || "—").slice(0, 18), sales: r.overall_sales }));
  const newVsRepeat = [...(data.rows || [])].sort((a, b) => b.overall_customers - a.overall_customers).slice(0, 8)
    .map((r) => ({ name: (r.store_name || r.store_code || "—").slice(0, 14), New: r.new_customer_count, Repeat: r.existing_customers }));
  const selCls = "k-input w-full !py-1.5 text-sm";
  const lblCls = "text-[10px] uppercase tracking-[0.2em] text-neutral-500 mb-1 block";

  return (
    <div data-testid="store-wise-kpi-report">
      <PageHeader title="Store-wise KPI Report" subtitle="REPORTS · OUTLET PERFORMANCE MATRIX"
        actions={
          <div className="flex items-center gap-2">
            <ColumnPicker columns={COLS} visible={visible} toggle={toggle} reset={reset} testid="swkpi-cols" />
            <button onClick={exportCsv} disabled={exporting} className="k-btn k-btn-outline" data-testid="swkpi-export">
              <Download className={`w-3.5 h-3.5 ${exporting ? "animate-pulse" : ""}`} /> {exporting ? "Preparing…" : "Download CSV"}
            </button>
          </div>
        }
      />
      <div className="p-8 space-y-6">
        <div className="chart-card p-5 space-y-4" data-testid="swkpi-filters">
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <div><label className={lblCls}>Start date</label><input type="date" value={params.start_date} onChange={(e) => set("start_date", e.target.value)} className={selCls} data-testid="swkpi-start" /></div>
            <div><label className={lblCls}>End date</label><input type="date" value={params.end_date} onChange={(e) => set("end_date", e.target.value)} className={selCls} data-testid="swkpi-end" /></div>
            <div><label className={lblCls}>Zone</label>
              <select value={params.zone} onChange={(e) => set("zone", e.target.value)} className={selCls} data-testid="swkpi-zone">
                <option value="">All zones</option>{opts.zones.map((z) => <option key={z} value={z}>{z}</option>)}
              </select></div>
            <div><label className={lblCls}>Class</label>
              <select value={params.store_class} onChange={(e) => set("store_class", e.target.value)} className={selCls} data-testid="swkpi-class">
                <option value="">All classes</option>{opts.store_classes.map((c) => <option key={c} value={c}>{c}</option>)}
              </select></div>
            <div><label className={lblCls}>City</label>
              <select value={params.city} onChange={(e) => set("city", e.target.value)} className={selCls} data-testid="swkpi-city">
                <option value="">All cities</option>{opts.cities.map((c) => <option key={c} value={c}>{c}</option>)}
              </select></div>
            <div><label className={lblCls}>Store</label>
              <select value={params.store_id} onChange={(e) => set("store_id", e.target.value)} className={selCls} data-testid="swkpi-store">
                <option value="">All stores</option>{dedupeStores.map((s) => <option key={s.id} value={s.id}>{s.name || s.code}</option>)}
              </select></div>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <button onClick={() => { set("start_date", monthStart()); set("end_date", today()); }} className="k-btn k-btn-outline k-btn-sm" data-testid="swkpi-mtd">This month</button>
            <button onClick={() => { set("start_date", yearsAgo(1)); set("end_date", today()); }} className="k-btn k-btn-outline k-btn-sm" data-testid="swkpi-1y">1y</button>
            <div className="flex-1" />
            <button onClick={fetchData} disabled={loading} className="k-btn kazo-bg-burgundy text-white" data-testid="swkpi-apply">
              <Search className="w-3.5 h-3.5" /> {loading ? "Loading…" : "Apply"}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <KPICard label="Overall Sales" value={fmtINR(t.overall_sales)} fullValue={t.overall_sales} accent="burgundy" testid="swkpi-kpi-sales" />
          <KPICard label="Total Discount" value={fmtINR(t.total_discount)} fullValue={t.total_discount} accent="amber" testid="swkpi-kpi-disc" />
          <KPICard label="Fresh Bills" value={fmtNum(t.fresh_bills)} accent="indigo" testid="swkpi-kpi-fresh" />
          <KPICard label="Return Bills" value={fmtNum(t.return_bills)} accent="rose" testid="swkpi-kpi-return" />
          <KPICard label="Overall Customers" value={fmtNum(t.overall_customers)} accent="teal" testid="swkpi-kpi-cust" />
          <KPICard label="New Customers" value={fmtNum(t.new_customer_count)} accent="emerald" testid="swkpi-kpi-new" />
        </div>

        <div className="grid lg:grid-cols-2 gap-6">
          <div className="chart-card p-5" data-accent="burgundy" data-testid="swkpi-chart-sales">
            <SectionHeading eyebrow="Top outlets" title="Overall Sales (Top 10)" accent="burgundy" />
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={topSales} layout="vertical" margin={{ left: 20 }}>
                <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                <XAxis type="number" stroke="#64748b" fontSize={10} tickFormatter={(v) => `₹${(v / 100000).toFixed(0)}L`} />
                <YAxis type="category" dataKey="name" stroke="#64748b" fontSize={10} width={120} />
                <Tooltip formatter={(v) => fmtMoney2(v)} />
                <Bar dataKey="sales" radius={[0, 4, 4, 0]}>
                  {topSales.map((_, i) => <Cell key={i} fill={CHART_SERIES[i % CHART_SERIES.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-card p-5" data-accent="teal" data-testid="swkpi-chart-newrepeat">
            <SectionHeading eyebrow="Acquisition" title="New vs Repeat Customers" accent="teal" />
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={newVsRepeat}>
                <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                <XAxis dataKey="name" stroke="#64748b" fontSize={9} angle={-20} textAnchor="end" height={60} interval={0} />
                <YAxis stroke="#64748b" fontSize={10} />
                <Tooltip /><Legend />
                <Bar dataKey="New" stackId="a" fill="#0E7C7B" />
                <Bar dataKey="Repeat" stackId="a" fill="#571326" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="chart-card p-5 overflow-x-auto" data-accent="indigo" data-testid="swkpi-table-card">
          <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
            <h3 className="font-display text-xl">{data.count} <span className="text-sm font-normal text-neutral-500">outlets</span></h3>
            <button onClick={fetchData} className="text-xs px-2 py-1 border border-neutral-300 hover:bg-neutral-50 flex items-center gap-1">
              <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} /> Refresh
            </button>
          </div>
          {error ? (
            <div className="text-sm text-rose-700 py-12 text-center" data-testid="swkpi-error">{error}</div>
          ) : (data.rows || []).length === 0 ? (
            <div className="text-sm text-neutral-500 py-12 text-center">{loading ? "Loading…" : "No data for the current filters."}</div>
          ) : (
            <ReportTable columns={COLS} rows={data.rows} visible={visible}
              sortBy={params.sort_by} sortDir={params.sort_dir} onSort={onSort}
              testid="swkpi-table" rowKey={(r) => r.store_id || r.store_code} />
          )}
        </div>
      </div>
    </div>
  );
}
