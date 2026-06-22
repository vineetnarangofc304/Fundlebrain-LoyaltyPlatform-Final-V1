/* CRM Customer Report — the customer master (points, billing, visits, recency,
   DOB/DOA …) with filters, sorting, show/hide columns, charts and CSV export.
   (Built from the client's "CRM_Report.csv" reference format.) */
import { useState, useEffect, useCallback } from "react";
import api, { API_URL } from "@/lib/api";
import { PageHeader, KPICard, SectionHeading, CHART_SERIES } from "./_shared";
import { ColumnPicker, ReportTable, useColumns } from "./reportkit";
import { fmtINR, fmtNum, fmtDate } from "@/lib/format";
import { Download, Search, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { PieChart, Pie, Cell, BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from "recharts";

const dateCell = (v) => (v ? fmtDate(v) : "—");

const COLS = [
  { key: "mobile", label: "Mobile", mono: true, sort: "mobile" },
  { key: "name", label: "Name", sort: "name" },
  { key: "city", label: "City", sort: "city" },
  { key: "state", label: "State", sort: "state", default: false },
  { key: "tier", label: "Tier", sort: "tier" },
  { key: "card_validity", label: "Card Validity", default: false },
  { key: "points_balance", label: "Point Balance", num: true, sort: "points_balance" },
  { key: "lifetime_points_redeemed", label: "Redeem Points", num: true, sort: "lifetime_points_redeemed", default: false },
  { key: "lifetime_spend", label: "Total Billing", money: true, sort: "lifetime_spend" },
  { key: "visit_count", label: "Total Visits", num: true, sort: "visit_count" },
  { key: "days_since_last_visit", label: "Days Since Visit", num: true, sort: "days_since_last_visit" },
  { key: "last_visit_at", label: "Last Visit", mono: true, sort: "last_visit_at", render: dateCell },
  { key: "first_purchase_at", label: "First Visit", mono: true, sort: "first_purchase_at", render: dateCell, default: false },
  { key: "registered_account", label: "Registered Account", mono: true, default: false },
  { key: "added_on", label: "Added On", mono: true, sort: "added_on", render: dateCell, default: false },
  { key: "birthday", label: "DOB", mono: true, render: dateCell, default: false },
  { key: "anniversary", label: "DOA", mono: true, render: dateCell, default: false },
];
const PAGE_SIZES = [50, 100, 200];

export default function CRMCustomerReport() {
  const [params, setParams] = useState({
    q: "", city: "", state: "", tier: "", card_validity: "", recency: "",
    min_visits: "", max_visits: "", min_points: "", min_billing: "",
    sort_by: "lifetime_spend", sort_dir: "desc",
  });
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [summary, setSummary] = useState(null);
  const [opts, setOpts] = useState({ cities: [], tiers: [], card_validities: [], states: [] });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [exporting, setExporting] = useState(false);

  const { visible, toggle, reset } = useColumns(COLS, "kazo-crm-cols");
  const set = (k, v) => setParams((p) => ({ ...p, [k]: v }));

  const cleanParams = useCallback(() => {
    const o = {};
    Object.entries(params).forEach(([k, v]) => { if (v === "" || v === null) return; o[k] = v; });
    return o;
  }, [params]);

  const fetchData = useCallback(async (toPage = 1) => {
    setLoading(true); setError(null);
    try {
      const r = await api.get("/kpi-reports/crm-customers", {
        params: { ...cleanParams(), limit: pageSize, skip: (toPage - 1) * pageSize },
      });
      setRows(r.data.rows || []); setTotal(r.data.total ?? 0);
      setHasMore(r.data.has_more ?? false); setPage(toPage);
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to load CRM report");
    } finally { setLoading(false); }
  }, [cleanParams, pageSize]);

  const fetchSummary = useCallback(() => {
    api.get("/kpi-reports/crm-summary", { params: cleanParams() }).then((r) => setSummary(r.data)).catch(() => setSummary(null));
  }, [cleanParams]);

  useEffect(() => {
    api.get("/kpi-reports/filter-options").then((r) => setOpts(r.data)).catch(() => {});
  }, []);
  useEffect(() => { fetchData(1); fetchSummary(); /* eslint-disable-next-line */ }, [params.sort_by, params.sort_dir, pageSize]);

  const apply = () => { fetchData(1); fetchSummary(); };
  const onSort = (sf) => setParams((p) => ({ ...p, sort_by: sf, sort_dir: p.sort_by === sf && p.sort_dir === "desc" ? "asc" : "desc" }));

  const exportCsv = async () => {
    setExporting(true);
    try {
      const token = localStorage.getItem("kazo_token");
      const usp = new URLSearchParams(cleanParams());
      const res = await fetch(`${API_URL}/kpi-reports/crm-customers/export?${usp.toString()}`, {
        headers: { Authorization: `Bearer ${token}` }, credentials: "include",
      });
      if (!res.ok) throw new Error();
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = `crm_customers_${new Date().toISOString().slice(0, 10)}.csv`; a.click();
      window.URL.revokeObjectURL(url);
      toast.success("Export started");
    } catch { toast.error("Export failed"); } finally { setExporting(false); }
  };

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const st = summary?.totals || {};
  const tierData = (summary?.by_tier || []).map((d) => ({ name: d.tier, value: d.count }));
  const cityData = (summary?.top_cities || []).map((d) => ({ name: d.city, count: d.count }));
  const recencyData = summary?.by_recency || [];
  const selCls = "k-input w-full !py-1.5 text-sm";
  const lblCls = "text-[10px] uppercase tracking-[0.2em] text-neutral-500 mb-1 block";

  return (
    <div data-testid="crm-customer-report">
      <PageHeader title="CRM Customer Report" subtitle="REPORTS · CUSTOMER MASTER"
        actions={
          <div className="flex items-center gap-2">
            <ColumnPicker columns={COLS} visible={visible} toggle={toggle} reset={reset} testid="crm-cols" />
            <button onClick={exportCsv} disabled={exporting} className="k-btn k-btn-outline" data-testid="crm-export">
              <Download className={`w-3.5 h-3.5 ${exporting ? "animate-pulse" : ""}`} /> {exporting ? "Preparing…" : "Download CSV"}
            </button>
          </div>
        }
      />
      <div className="p-8 space-y-6">
        {/* Filters */}
        <div className="chart-card p-5 space-y-4" data-testid="crm-filters">
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <div className="lg:col-span-2"><label className={lblCls}>Search (mobile / name)</label>
              <input value={params.q} onChange={(e) => set("q", e.target.value)} className={selCls} onKeyDown={(e) => e.key === "Enter" && apply()} data-testid="crm-search" /></div>
            <div><label className={lblCls}>City</label>
              <select value={params.city} onChange={(e) => set("city", e.target.value)} className={selCls} data-testid="crm-city">
                <option value="">All</option>{opts.cities.map((c) => <option key={c} value={c}>{c}</option>)}
              </select></div>
            <div><label className={lblCls}>State</label>
              <select value={params.state} onChange={(e) => set("state", e.target.value)} className={selCls} data-testid="crm-state">
                <option value="">All</option>{opts.states.map((c) => <option key={c} value={c}>{c}</option>)}
              </select></div>
            <div><label className={lblCls}>Tier</label>
              <select value={params.tier} onChange={(e) => set("tier", e.target.value)} className={selCls} data-testid="crm-tier">
                <option value="">All</option>{opts.tiers.map((c) => <option key={c} value={c}>{c}</option>)}
              </select></div>
            <div><label className={lblCls}>Recency</label>
              <select value={params.recency} onChange={(e) => set("recency", e.target.value)} className={selCls} data-testid="crm-recency">
                <option value="">All</option>
                <option value="active">Active (0-6M)</option>
                <option value="dormant">Dormant (6-12M)</option>
                <option value="lapsed">Lapsed (12M+)</option>
              </select></div>
            <div><label className={lblCls}>Card Validity</label>
              <select value={params.card_validity} onChange={(e) => set("card_validity", e.target.value)} className={selCls} data-testid="crm-card">
                <option value="">All</option>{opts.card_validities.map((c) => <option key={c} value={c}>{c}</option>)}
              </select></div>
            <div><label className={lblCls}>Min visits</label><input type="number" value={params.min_visits} onChange={(e) => set("min_visits", e.target.value)} className={selCls} data-testid="crm-minvisits" /></div>
            <div><label className={lblCls}>Min points</label><input type="number" value={params.min_points} onChange={(e) => set("min_points", e.target.value)} className={selCls} data-testid="crm-minpoints" /></div>
            <div><label className={lblCls}>Min billing</label><input type="number" value={params.min_billing} onChange={(e) => set("min_billing", e.target.value)} className={selCls} data-testid="crm-minbilling" /></div>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex-1" />
            <button onClick={apply} disabled={loading} className="k-btn kazo-bg-burgundy text-white" data-testid="crm-apply">
              <Search className="w-3.5 h-3.5" /> {loading ? "Loading…" : "Apply"}
            </button>
          </div>
        </div>

        {/* KPI tiles */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          <KPICard label="Customers" value={fmtNum(st.customers)} accent="indigo" testid="crm-kpi-cust" />
          <KPICard label="Total Billing" value={fmtINR(st.spend)} fullValue={st.spend} accent="burgundy" testid="crm-kpi-billing" />
          <KPICard label="Points Liability" value={fmtNum(st.points)} accent="amber" testid="crm-kpi-points" />
          <KPICard label="Points Redeemed" value={fmtNum(st.redeemed)} accent="teal" testid="crm-kpi-redeemed" />
          <KPICard label="Total Visits" value={fmtNum(st.visits)} accent="emerald" testid="crm-kpi-visits" />
        </div>

        {/* Charts */}
        <div className="grid lg:grid-cols-3 gap-6">
          <div className="chart-card p-5" data-accent="burgundy" data-testid="crm-chart-tier">
            <SectionHeading eyebrow="Mix" title="Customers by Tier" accent="burgundy" />
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie data={tierData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90} innerRadius={50} paddingAngle={2} label={(p) => p.name}>
                  {tierData.map((_, i) => <Cell key={i} fill={CHART_SERIES[i % CHART_SERIES.length]} />)}
                </Pie>
                <Tooltip formatter={(v) => fmtNum(v)} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-card p-5" data-accent="teal" data-testid="crm-chart-recency">
            <SectionHeading eyebrow="Lifecycle" title="Recency Distribution" accent="teal" />
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={recencyData}>
                <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                <XAxis dataKey="bucket" stroke="#64748b" fontSize={9} interval={0} />
                <YAxis stroke="#64748b" fontSize={10} tickFormatter={(v) => fmtNum(v)} />
                <Tooltip formatter={(v) => fmtNum(v)} />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {recencyData.map((_, i) => <Cell key={i} fill={CHART_SERIES[i % CHART_SERIES.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-card p-5" data-accent="indigo" data-testid="crm-chart-cities">
            <SectionHeading eyebrow="Geography" title="Top Cities" accent="indigo" />
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={cityData} layout="vertical" margin={{ left: 10 }}>
                <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                <XAxis type="number" stroke="#64748b" fontSize={10} tickFormatter={(v) => fmtNum(v)} />
                <YAxis type="category" dataKey="name" stroke="#64748b" fontSize={10} width={90} />
                <Tooltip formatter={(v) => fmtNum(v)} />
                <Bar dataKey="count" fill="#1E3A8A" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Table */}
        <div className="chart-card p-5 overflow-x-auto" data-accent="indigo" data-testid="crm-table-card">
          <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
            <h3 className="font-display text-xl">{rows.length} <span className="text-sm font-normal text-neutral-500">of {total.toLocaleString()} customers</span></h3>
            <button onClick={() => fetchData(page)} className="text-xs px-2 py-1 border border-neutral-300 hover:bg-neutral-50 flex items-center gap-1">
              <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} /> Refresh
            </button>
          </div>
          {error ? (
            <div className="text-sm text-rose-700 py-12 text-center" data-testid="crm-error">{error}</div>
          ) : rows.length === 0 ? (
            <div className="text-sm text-neutral-500 py-12 text-center">{loading ? "Loading…" : "No customers found."}</div>
          ) : (
            <ReportTable columns={COLS} rows={rows} visible={visible}
              sortBy={params.sort_by} sortDir={params.sort_dir} onSort={onSort}
              testid="crm-table" rowKey={(r) => r.mobile} />
          )}
          <div className="flex items-center justify-between mt-4 pt-3 border-t border-black/5" data-testid="crm-pagination">
            <div className="flex items-center gap-3">
              <span className="text-xs text-neutral-500">Page {page} of {totalPages}</span>
              <select value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))} className="k-input k-input-sm !py-1 text-xs" data-testid="crm-page-size">
                {PAGE_SIZES.map((s) => <option key={s} value={s}>{s} / page</option>)}
              </select>
            </div>
            <div className="flex items-center gap-2">
              <button className="k-btn k-btn-outline k-btn-sm" disabled={page <= 1 || loading} onClick={() => fetchData(page - 1)} data-testid="crm-prev">← Prev</button>
              <button className="k-btn k-btn-outline k-btn-sm" disabled={!hasMore || loading} onClick={() => fetchData(page + 1)} data-testid="crm-next">Next →</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
