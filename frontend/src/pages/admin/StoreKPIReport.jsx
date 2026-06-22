/* Store KPI Report — per-store sales/customer KPIs with optional Year-over-Year
   growth, charts, sortable columns, show/hide columns and CSV export.
   (Built from the client's "MARCH KPI" / "Store_wise_KPI" reference formats.) */
import { useState, useEffect, useCallback } from "react";
import api, { API_URL } from "@/lib/api";
import { PageHeader, KPICard, SectionHeading, CHART_SERIES } from "./_shared";
import { ColumnPicker, ReportTable, useColumns, GrowthCell } from "./reportkit";
import { fmtINR, fmtMoney2, fmtNum } from "@/lib/format";
import { Download, Search, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid, Cell, Legend } from "recharts";

const monthStart = () => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10); };
const today = () => new Date().toISOString().slice(0, 10);
const yearsAgo = (n) => { const d = new Date(); return new Date(d.getFullYear() - n, d.getMonth(), 1).toISOString().slice(0, 10); };

const BASE_COLS = [
  { key: "store_code", label: "Store Code", mono: true, sort: "store_code" },
  { key: "store_name", label: "Store", sort: "store_name" },
  { key: "store_class", label: "Class", sort: "store_class" },
  { key: "zone", label: "Zone", sort: "zone" },
  { key: "city", label: "City", sort: "city" },
  { key: "overall_sales", label: "Overall Sales", money: true, sort: "overall_sales" },
  { key: "total_discount", label: "Discount", money: true, sort: "total_discount" },
  { key: "net_before_tax", label: "Net (pre-tax)", money: true, default: false },
  { key: "total_tax", label: "Tax", money: true, default: false },
  { key: "fresh_bills", label: "Fresh Bills", num: true, sort: "fresh_bills" },
  { key: "fresh_value", label: "Fresh Value", money: true, sort: "fresh_value", default: false },
  { key: "return_bills", label: "Return Bills", num: true, sort: "return_bills" },
  { key: "return_value", label: "Return Value", money: true, default: false },
  { key: "new_txn", label: "New Txns", num: true, sort: "new_txn" },
  { key: "new_value", label: "New Value", money: true, default: false },
  { key: "new_atv", label: "New ATV", money: true, sort: "new_atv", default: false },
  { key: "repeat_txn", label: "Repeat Txns", num: true, sort: "repeat_txn" },
  { key: "repeat_value", label: "Repeat Value", money: true, default: false },
  { key: "repeat_atv", label: "Repeat ATV", money: true, sort: "repeat_atv", default: false },
  { key: "mapped_txn", label: "Mapped Txns", num: true, sort: "mapped_txn", default: false },
  { key: "unmapped_txn", label: "Unmapped Txns", num: true, sort: "unmapped_txn", default: false },
  { key: "overall_customers", label: "Customers", num: true, sort: "overall_customers" },
  { key: "new_customer_count", label: "New Cust", num: true, sort: "new_customer_count" },
  { key: "existing_customers", label: "Existing Cust", num: true, sort: "existing_customers" },
  { key: "overall_atv", label: "Overall ATV", money: true, sort: "overall_atv" },
];
const COMPARE_COLS = [
  { key: "prev_sales", label: "Sales (PY)", money: true },
  { key: "growth_sales", label: "Sales Growth", render: GrowthCell },
  { key: "prev_customers", label: "Cust (PY)", num: true },
  { key: "growth_customers", label: "Cust Growth", render: GrowthCell },
];

export default function StoreKPIReport() {
  const [params, setParams] = useState({
    start_date: monthStart(), end_date: today(),
    zone: "", city: "", store_class: "", store_id: "",
    compare: false, sort_by: "overall_sales", sort_dir: "desc",
  });
  const [data, setData] = useState({ rows: [], totals: {}, count: 0 });
  const [opts, setOpts] = useState({ zones: [], cities: [], store_classes: [] });
  const [stores, setStores] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [exporting, setExporting] = useState(false);

  const allCols = params.compare ? [...BASE_COLS, ...COMPARE_COLS] : BASE_COLS;
  const { visible, toggle, reset } = useColumns(BASE_COLS, "kazo-storekpi-cols");
  // When YoY is on, surface the comparison columns automatically.
  const tableVisible = params.compare ? new Set([...visible, ...COMPARE_COLS.map((c) => c.key)]) : visible;
  const set = (k, v) => setParams((p) => ({ ...p, [k]: v }));

  const cleanParams = useCallback(() => {
    const o = {};
    Object.entries(params).forEach(([k, v]) => { if (v === "" || v === false) return; o[k] = v; });
    return o;
  }, [params]);

  const fetchData = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const r = await api.get("/kpi-reports/store-kpi", { params: cleanParams() });
      setData(r.data);
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to load Store KPI");
    } finally { setLoading(false); }
  }, [cleanParams]);

  useEffect(() => {
    api.get("/kpi-reports/filter-options").then((r) => setOpts(r.data)).catch(() => {});
    api.get("/stores").then((r) => setStores(r.data || [])).catch(() => {});
  }, []);
  useEffect(() => { fetchData(); /* eslint-disable-next-line */ }, [params.sort_by, params.sort_dir, params.compare]);

  const onSort = (sf) => setParams((p) => ({ ...p, sort_by: sf, sort_dir: p.sort_by === sf && p.sort_dir === "desc" ? "asc" : "desc" }));

  const exportCsv = async () => {
    setExporting(true);
    try {
      const token = localStorage.getItem("kazo_token");
      const { compare, ...rest } = cleanParams();
      const usp = new URLSearchParams(rest);
      const res = await fetch(`${API_URL}/kpi-reports/store-kpi/export?${usp.toString()}`, {
        headers: { Authorization: `Bearer ${token}` }, credentials: "include",
      });
      if (!res.ok) throw new Error();
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = `store_kpi_${today()}.csv`; a.click();
      window.URL.revokeObjectURL(url);
      toast.success("Export downloaded");
    } catch { toast.error("Export failed"); } finally { setExporting(false); }
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
    <div data-testid="store-kpi-report">
      <PageHeader title="Store KPI Report" subtitle="REPORTS · STORE PERFORMANCE"
        actions={
          <div className="flex items-center gap-2">
            <ColumnPicker columns={allCols} visible={visible} toggle={toggle} reset={reset} testid="skpi-cols" />
            <button onClick={exportCsv} disabled={exporting} className="k-btn k-btn-outline" data-testid="skpi-export">
              <Download className={`w-3.5 h-3.5 ${exporting ? "animate-pulse" : ""}`} /> {exporting ? "Preparing…" : "Download CSV"}
            </button>
          </div>
        }
      />
      <div className="p-8 space-y-6">
        {/* Filters */}
        <div className="chart-card p-5 space-y-4" data-testid="skpi-filters">
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <div><label className={lblCls}>Start date</label><input type="date" value={params.start_date} onChange={(e) => set("start_date", e.target.value)} className={selCls} data-testid="skpi-start" /></div>
            <div><label className={lblCls}>End date</label><input type="date" value={params.end_date} onChange={(e) => set("end_date", e.target.value)} className={selCls} data-testid="skpi-end" /></div>
            <div><label className={lblCls}>Zone</label>
              <select value={params.zone} onChange={(e) => set("zone", e.target.value)} className={selCls} data-testid="skpi-zone">
                <option value="">All zones</option>{opts.zones.map((z) => <option key={z} value={z}>{z}</option>)}
              </select></div>
            <div><label className={lblCls}>Class</label>
              <select value={params.store_class} onChange={(e) => set("store_class", e.target.value)} className={selCls} data-testid="skpi-class">
                <option value="">All classes</option>{opts.store_classes.map((c) => <option key={c} value={c}>{c}</option>)}
              </select></div>
            <div><label className={lblCls}>City</label>
              <select value={params.city} onChange={(e) => set("city", e.target.value)} className={selCls} data-testid="skpi-city">
                <option value="">All cities</option>{opts.cities.map((c) => <option key={c} value={c}>{c}</option>)}
              </select></div>
            <div><label className={lblCls}>Store</label>
              <select value={params.store_id} onChange={(e) => set("store_id", e.target.value)} className={selCls} data-testid="skpi-store">
                <option value="">All stores</option>{dedupeStores.map((s) => <option key={s.id} value={s.id}>{s.name || s.code}</option>)}
              </select></div>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <label className="flex items-center gap-2 text-sm cursor-pointer" data-testid="skpi-compare-label">
              <input type="checkbox" checked={params.compare} onChange={(e) => set("compare", e.target.checked)} data-testid="skpi-compare" />
              Year-over-Year comparison
            </label>
            <button onClick={() => { set("start_date", monthStart()); set("end_date", today()); }} className="k-btn k-btn-outline k-btn-sm" data-testid="skpi-mtd">This month</button>
            <button onClick={() => { set("start_date", yearsAgo(1)); set("end_date", today()); }} className="k-btn k-btn-outline k-btn-sm" data-testid="skpi-1y">1y</button>
            <div className="flex-1" />
            <button onClick={fetchData} disabled={loading} className="k-btn kazo-bg-burgundy text-white" data-testid="skpi-apply">
              <Search className="w-3.5 h-3.5" /> {loading ? "Loading…" : "Apply"}
            </button>
          </div>
        </div>

        {/* KPI tiles */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <KPICard label="Overall Sales" value={fmtINR(t.overall_sales)} fullValue={t.overall_sales} accent="burgundy" testid="skpi-kpi-sales" />
          <KPICard label="Total Discount" value={fmtINR(t.total_discount)} fullValue={t.total_discount} accent="amber" testid="skpi-kpi-disc" />
          <KPICard label="Fresh Bills" value={fmtNum(t.fresh_bills)} accent="indigo" testid="skpi-kpi-bills" />
          <KPICard label="Return Bills" value={fmtNum(t.return_bills)} accent="rose" testid="skpi-kpi-rbills" />
          <KPICard label="Customers" value={fmtNum(t.overall_customers)} accent="teal" testid="skpi-kpi-cust" />
          <KPICard label="New Customers" value={fmtNum(t.new_customer_count)} accent="emerald" testid="skpi-kpi-new" />
        </div>

        {/* Charts */}
        <div className="grid lg:grid-cols-2 gap-6">
          <div className="chart-card p-5" data-accent="burgundy" data-testid="skpi-chart-sales">
            <SectionHeading eyebrow="Top stores" title="Overall Sales (Top 10)" accent="burgundy" />
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
          <div className="chart-card p-5" data-accent="teal" data-testid="skpi-chart-newrepeat">
            <SectionHeading eyebrow="Acquisition" title="New vs Repeat Customers" accent="teal" />
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={newVsRepeat}>
                <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                <XAxis dataKey="name" stroke="#64748b" fontSize={9} angle={-20} textAnchor="end" height={60} interval={0} />
                <YAxis stroke="#64748b" fontSize={10} />
                <Tooltip /><Legend />
                <Bar dataKey="New" stackId="a" fill="#0E7C7B" radius={[0, 0, 0, 0]} />
                <Bar dataKey="Repeat" stackId="a" fill="#571326" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Table */}
        <div className="chart-card p-5 overflow-x-auto" data-accent="indigo" data-testid="skpi-table-card">
          <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
            <h3 className="font-display text-xl">{data.count} <span className="text-sm font-normal text-neutral-500">stores</span></h3>
            <button onClick={fetchData} className="text-xs px-2 py-1 border border-neutral-300 hover:bg-neutral-50 flex items-center gap-1">
              <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} /> Refresh
            </button>
          </div>
          {error ? (
            <div className="text-sm text-rose-700 py-12 text-center" data-testid="skpi-error">{error}</div>
          ) : (data.rows || []).length === 0 ? (
            <div className="text-sm text-neutral-500 py-12 text-center">{loading ? "Loading…" : "No data for the current filters."}</div>
          ) : (
            <ReportTable columns={allCols} rows={data.rows} visible={tableVisible}
              sortBy={params.sort_by} sortDir={params.sort_dir} onSort={onSort}
              testid="skpi-table" rowKey={(r) => r.store_id || r.store_code} />
          )}
        </div>
      </div>
    </div>
  );
}
