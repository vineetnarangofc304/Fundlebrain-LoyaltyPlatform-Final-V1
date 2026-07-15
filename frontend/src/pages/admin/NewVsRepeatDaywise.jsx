/* New vs Repeat (Daywise) — per-day distinct New vs Existing customer counts + % split,
   with date-range/store filters, a trend chart and CSV export. */
import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { requestExport } from "@/lib/exportClient";
import { PageHeader, KPICard, SectionHeading } from "./_shared";
import { ReportTable } from "./reportkit";
import { fmtNum, fmtPct } from "@/lib/format";
import { Download, Search } from "lucide-react";
import { BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from "recharts";

const monthStart = () => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10); };
const today = () => new Date().toISOString().slice(0, 10);
const daysAgo = (n) => new Date(Date.now() - n * 86400000).toISOString().slice(0, 10);
const pctCell = (v) => (v === null || v === undefined ? "—" : fmtPct(v * 100));

const COLS = [
  { key: "date", label: "Date", mono: true, default: true },
  { key: "new_customer_count", label: "New Customer Count", num: true, default: true },
  { key: "existing_customer_count", label: "Existing Customer Count", num: true, default: true },
  { key: "total_customer_count", label: "Total Customer Count", num: true, default: true },
  { key: "pct_new", label: "% New Customer", render: pctCell, default: true },
  { key: "pct_existing", label: "% Existing Customers", render: pctCell, default: true },
];

export default function NewVsRepeatDaywise() {
  const [params, setParams] = useState({
    start_date: daysAgo(30), end_date: today(),
    zone: "", city: "", store_class: "", store_id: "",
  });
  const [data, setData] = useState({ rows: [], count: 0, totals: {} });
  const [opts, setOpts] = useState({ zones: [], cities: [], store_classes: [] });
  const [stores, setStores] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [exporting, setExporting] = useState(false);
  const set = (k, v) => setParams((p) => ({ ...p, [k]: v }));

  const cleanParams = useCallback(() => {
    const o = {};
    Object.entries(params).forEach(([k, v]) => { if (v === "" || v === false) return; o[k] = v; });
    return o;
  }, [params]);

  const fetchData = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const r = await api.get("/bops-reports/new-vs-repeat-daywise", { params: cleanParams() });
      setData(r.data);
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to load New vs Repeat report");
    } finally { setLoading(false); }
  }, [cleanParams]);

  useEffect(() => {
    api.get("/kpi-reports/filter-options").then((r) => setOpts(r.data)).catch(() => {});
    api.get("/stores").then((r) => setStores(r.data || [])).catch(() => {});
    fetchData(); /* eslint-disable-next-line */
  }, []);

  const exportCsv = async () => {
    setExporting(true);
    try {
      await requestExport({
        report_type: "new_vs_repeat_daywise", params: cleanParams(), label: "New vs Repeat (Daywise)",
        known_total: data.count ?? (data.rows || []).length, filename: `new_vs_repeat_daywise_${today()}.csv`,
      });
    } finally { setExporting(false); }
  };

  const rows = data.rows || [];
  const t = data.totals || {};
  const chart = [...rows].map((r) => ({ date: r.date, New: r.new_customer_count, Existing: r.existing_customer_count }));
  const dedupeStores = (() => {
    const seen = new Set(); const out = [];
    for (const s of stores) { const k = String(s.name || s.code || s.id).toLowerCase().trim(); if (k && !seen.has(k)) { seen.add(k); out.push(s); } }
    return out;
  })();
  const selCls = "k-input w-full !py-1.5 text-sm";
  const lblCls = "text-[10px] uppercase tracking-[0.2em] text-neutral-500 mb-1 block";

  return (
    <div data-testid="new-vs-repeat-daywise">
      <PageHeader title="New vs Repeat (Daywise)" subtitle="REPORTS · ACQUISITION"
        actions={
          <button onClick={exportCsv} disabled={exporting} className="k-btn k-btn-outline" data-testid="nvr-export">
            <Download className={`w-3.5 h-3.5 ${exporting ? "animate-pulse" : ""}`} /> {exporting ? "Preparing…" : "Download CSV"}
          </button>
        }
      />
      <div className="p-8 space-y-6">
        <div className="chart-card p-5 space-y-4" data-testid="nvr-filters">
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <div><label className={lblCls}>Start date</label><input type="date" value={params.start_date} onChange={(e) => set("start_date", e.target.value)} className={selCls} data-testid="nvr-start" /></div>
            <div><label className={lblCls}>End date</label><input type="date" value={params.end_date} onChange={(e) => set("end_date", e.target.value)} className={selCls} data-testid="nvr-end" /></div>
            <div><label className={lblCls}>Zone</label>
              <select value={params.zone} onChange={(e) => set("zone", e.target.value)} className={selCls} data-testid="nvr-zone">
                <option value="">All zones</option>{(opts.zones || []).map((z) => <option key={z} value={z}>{z}</option>)}
              </select></div>
            <div><label className={lblCls}>Class</label>
              <select value={params.store_class} onChange={(e) => set("store_class", e.target.value)} className={selCls} data-testid="nvr-class">
                <option value="">All classes</option>{(opts.store_classes || []).map((c) => <option key={c} value={c}>{c}</option>)}
              </select></div>
            <div className="lg:col-span-2"><label className={lblCls}>Store</label>
              <select value={params.store_id} onChange={(e) => set("store_id", e.target.value)} className={selCls} data-testid="nvr-store">
                <option value="">All stores</option>{dedupeStores.map((s) => <option key={s.id} value={s.id}>{s.name || s.code}</option>)}
              </select></div>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <button onClick={() => { set("start_date", monthStart()); set("end_date", today()); }} className="k-btn k-btn-outline k-btn-sm" data-testid="nvr-mtd">This month</button>
            <button onClick={() => { set("start_date", daysAgo(30)); set("end_date", today()); }} className="k-btn k-btn-outline k-btn-sm" data-testid="nvr-30d">Last 30d</button>
            <div className="flex-1" />
            <button onClick={fetchData} disabled={loading} className="k-btn kazo-bg-burgundy text-white" data-testid="nvr-apply">
              <Search className="w-3.5 h-3.5" /> {loading ? "Loading…" : "Apply"}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KPICard label="New Customers" value={fmtNum(t.new_customer_count || 0)} accent="emerald" testid="nvr-kpi-new" />
          <KPICard label="Existing Customers" value={fmtNum(t.existing_customer_count || 0)} accent="burgundy" testid="nvr-kpi-existing" />
          <KPICard label="Total Customers" value={fmtNum(t.total_customer_count || 0)} accent="indigo" testid="nvr-kpi-total" />
          <KPICard label="% New" value={t.total_customer_count ? fmtPct((t.pct_new || 0) * 100) : "—"} accent="teal" testid="nvr-kpi-pctnew" />
        </div>

        <div className="chart-card p-5" data-accent="teal" data-testid="nvr-chart">
          <SectionHeading eyebrow="Daily" title="New vs Existing customers per day" accent="teal" />
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={chart}>
              <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
              <XAxis dataKey="date" stroke="#64748b" fontSize={9} angle={-25} textAnchor="end" height={60} interval="preserveStartEnd" />
              <YAxis stroke="#64748b" fontSize={10} />
              <Tooltip formatter={(v) => fmtNum(v)} /><Legend />
              <Bar dataKey="New" stackId="a" fill="#0E7C7B" />
              <Bar dataKey="Existing" stackId="a" fill="#571326" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="chart-card p-5 overflow-x-auto" data-accent="indigo" data-testid="nvr-table-card">
          <h3 className="font-display text-xl mb-3">{data.count} <span className="text-sm font-normal text-neutral-500">days</span></h3>
          {error ? (
            <div className="text-sm text-rose-700 py-12 text-center" data-testid="nvr-error">{error}</div>
          ) : rows.length === 0 ? (
            <div className="text-sm text-neutral-500 py-12 text-center">{loading ? "Loading…" : "No data for the current filters."}</div>
          ) : (
            <ReportTable columns={COLS} rows={rows} visible={new Set(COLS.map((c) => c.key))} testid="nvr-table" rowKey={(r) => r.date} />
          )}
        </div>
      </div>
    </div>
  );
}
