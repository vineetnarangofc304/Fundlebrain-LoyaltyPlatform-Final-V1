/* Store-wise Customer Count — snapshot of each store's mapped customer base bucketed by
   recency: Active (0-6M) / Win-Back-Lost (6-12M) / At-Risk (12M+) + No Mapping (no mobile).
   Grouped by the customer's home store, with a grand-total row and CSV export. */
import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { requestExport } from "@/lib/exportClient";
import { PageHeader, KPICard, SectionHeading } from "./_shared";
import { ReportTable } from "./reportkit";
import { fmtNum } from "@/lib/format";
import { Download, Search } from "lucide-react";

const today = () => new Date().toISOString().slice(0, 10);

const COLS = [
  { key: "store_name", label: "Store Name", default: true },
  { key: "active", label: "Active (0-6 M)", num: true, default: true },
  { key: "no_mapping", label: "No Mapping (No Mob Num)", num: true, default: true },
  { key: "win_back_lost", label: "Win Back- Lost (6-12M)", num: true, default: true },
  { key: "at_risk", label: "Win-Back- At-Risk (12 & Abv M)", num: true, default: true },
  { key: "grand_total", label: "Grand Total", num: true, default: true },
];

export default function CustomerCountByStore() {
  const [params, setParams] = useState({ as_of: today(), store_id: "" });
  const [data, setData] = useState({ rows: [], count: 0, totals: {}, as_of: "" });
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
      const r = await api.get("/bops-reports/customer-count-by-store", { params: cleanParams() });
      setData(r.data);
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to load customer-count report");
    } finally { setLoading(false); }
  }, [cleanParams]);

  useEffect(() => {
    api.get("/stores").then((r) => setStores(r.data || [])).catch(() => {});
    fetchData(); /* eslint-disable-next-line */
  }, []);

  const exportCsv = async () => {
    setExporting(true);
    try {
      await requestExport({
        report_type: "customer_count_by_store", params: cleanParams(), label: "Store-wise Customer Count",
        known_total: data.count ?? (data.rows || []).length, filename: `customer_count_by_store_${today()}.csv`,
      });
    } finally { setExporting(false); }
  };

  const rows = data.rows || [];
  const t = data.totals || {};
  const dedupeStores = (() => {
    const seen = new Set(); const out = [];
    for (const s of stores) { const k = String(s.name || s.code || s.id).toLowerCase().trim(); if (k && !seen.has(k)) { seen.add(k); out.push(s); } }
    return out;
  })();
  const tableRows = rows.length
    ? [...rows, { store_id: "__total__", store_name: "Grand Total", active: t.active, no_mapping: t.no_mapping, win_back_lost: t.win_back_lost, at_risk: t.at_risk, grand_total: t.grand_total }]
    : [];
  const selCls = "k-input w-full !py-1.5 text-sm";
  const lblCls = "text-[10px] uppercase tracking-[0.2em] text-neutral-500 mb-1 block";

  return (
    <div data-testid="customer-count-by-store">
      <PageHeader title="Store-wise Customer Count" subtitle="REPORTS · CUSTOMER SEGMENTS (RECENCY)"
        actions={
          <button onClick={exportCsv} disabled={exporting} className="k-btn k-btn-outline" data-testid="ccs-export">
            <Download className={`w-3.5 h-3.5 ${exporting ? "animate-pulse" : ""}`} /> {exporting ? "Preparing…" : "Download CSV"}
          </button>
        }
      />
      <div className="p-8 space-y-6">
        <div className="chart-card p-5 space-y-4" data-testid="ccs-filters">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div><label className={lblCls}>As of date</label><input type="date" value={params.as_of} onChange={(e) => set("as_of", e.target.value)} className={selCls} data-testid="ccs-asof" /></div>
            <div className="md:col-span-2"><label className={lblCls}>Store</label>
              <select value={params.store_id} onChange={(e) => set("store_id", e.target.value)} className={selCls} data-testid="ccs-store">
                <option value="">All stores</option>{dedupeStores.map((s) => <option key={s.id} value={s.id}>{s.name || s.code}</option>)}
              </select></div>
            <div className="flex items-end">
              <button onClick={fetchData} disabled={loading} className="k-btn kazo-bg-burgundy text-white w-full" data-testid="ccs-apply">
                <Search className="w-3.5 h-3.5" /> {loading ? "Loading…" : "Apply"}
              </button>
            </div>
          </div>
          <p className="text-xs text-neutral-500">
            Recency measured from the “as of” date on each customer’s home store. Active = last visit within 6 months,
            Win-Back-Lost = 6–12 months, At-Risk = 12 months+. No Mapping = customers with no mobile number.
          </p>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <KPICard label="Active (0-6M)" value={fmtNum(t.active || 0)} accent="emerald" testid="ccs-kpi-active" />
          <KPICard label="No Mapping" value={fmtNum(t.no_mapping || 0)} accent="amber" testid="ccs-kpi-nomap" />
          <KPICard label="Win-Back Lost (6-12M)" value={fmtNum(t.win_back_lost || 0)} accent="indigo" testid="ccs-kpi-wbl" />
          <KPICard label="At-Risk (12M+)" value={fmtNum(t.at_risk || 0)} accent="rose" testid="ccs-kpi-atrisk" />
          <KPICard label="Grand Total" value={fmtNum(t.grand_total || 0)} accent="burgundy" testid="ccs-kpi-total" />
        </div>

        <div className="chart-card p-5 overflow-x-auto" data-accent="indigo" data-testid="ccs-table-card">
          <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
            <SectionHeading eyebrow={`As of ${data.as_of || params.as_of}`} title={`${data.count} stores`} accent="indigo" />
          </div>
          {error ? (
            <div className="text-sm text-rose-700 py-12 text-center" data-testid="ccs-error">{error}</div>
          ) : rows.length === 0 ? (
            <div className="text-sm text-neutral-500 py-12 text-center">{loading ? "Loading…" : "No data for the current filters."}</div>
          ) : (
            <ReportTable columns={COLS} rows={tableRows} visible={new Set(COLS.map((c) => c.key))} testid="ccs-table" rowKey={(r) => r.store_id} />
          )}
        </div>
      </div>
    </div>
  );
}
