/* Sales MTD — customer base split by recency segment (Active / No Mapping / Win-Back-Lost /
   At-Risk) with each segment's total lifetime revenue and the count of customers acquired
   month-to-date. Segment logic matches the Store-wise Customer Count report. */
import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { PageHeader, KPICard, SectionHeading } from "./_shared";
import { fmtNum, fmtINR } from "@/lib/format";
import { Download, Search } from "lucide-react";

const thisMonth = () => new Date().toISOString().slice(0, 7);

export default function SalesMTD() {
  const [params, setParams] = useState({ month: thisMonth(), store_id: "" });
  const [data, setData] = useState({ rows: [], totals: {}, month: "" });
  const [stores, setStores] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const set = (k, v) => setParams((p) => ({ ...p, [k]: v }));

  const cleanParams = useCallback(() => {
    const o = {};
    Object.entries(params).forEach(([k, v]) => { if (v === "" || v == null) return; o[k] = v; });
    return o;
  }, [params]);

  const fetchData = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const r = await api.get("/bops-reports/sales-mtd", { params: cleanParams() });
      setData(r.data);
    } catch (e) {
      setError(e.response?.data?.detail || "Failed to load Sales MTD report");
    } finally { setLoading(false); }
  }, [cleanParams]);

  useEffect(() => {
    api.get("/stores").then((r) => setStores(r.data || [])).catch(() => {});
    fetchData(); /* eslint-disable-next-line */
  }, []);

  const exportCsv = () => {
    const rows = data.rows || [];
    const header = ["Segment", "Customer Count", "Total Revenue", "New Customer Count (MTD)"];
    const lines = [header.join(",")];
    rows.forEach((r) => lines.push([`"${r.segment}"`, r.count, r.revenue, r.new_count].join(",")));
    const t = data.totals || {};
    lines.push([`"Grand Total"`, t.count ?? "", t.revenue ?? "", t.new_count ?? ""].join(","));
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `sales_mtd_${data.month || params.month}.csv`; a.click();
    URL.revokeObjectURL(url);
  };

  const t = data.totals || {};
  const rows = data.rows || [];

  return (
    <div className="space-y-6" data-testid="sales-mtd-page">
      <PageHeader
        title="Sales — MTD"
        subtitle={`Customer base by recency segment with lifetime revenue and new customers acquired month-to-date${data.month ? ` · ${data.month}` : ""}`}
        actions={
          <button onClick={exportCsv} disabled={!rows.length}
            className="k-btn k-btn-outline inline-flex items-center gap-2 disabled:opacity-50" data-testid="sales-mtd-export">
            <Download className="w-4 h-4" /> Export CSV
          </button>
        }
      />

      {/* Filters */}
      <div className="flex flex-wrap items-end gap-3 bg-white border border-neutral-200 rounded-xl p-4">
        <div>
          <label className="block text-[10px] uppercase tracking-[0.2em] text-neutral-500 mb-1">New-customer month</label>
          <input type="month" value={params.month} onChange={(e) => set("month", e.target.value)}
            className="k-input" data-testid="sales-mtd-month" />
        </div>
        <div>
          <label className="block text-[10px] uppercase tracking-[0.2em] text-neutral-500 mb-1">Store (optional)</label>
          <select value={params.store_id} onChange={(e) => set("store_id", e.target.value)} className="k-input min-w-[220px]" data-testid="sales-mtd-store">
            <option value="">All stores</option>
            {stores.map((s) => <option key={s.id} value={s.id}>{s.name || s.code}</option>)}
          </select>
        </div>
        <button onClick={fetchData} className="k-btn k-btn-primary inline-flex items-center gap-2" data-testid="sales-mtd-run">
          <Search className="w-4 h-4" /> Run
        </button>
      </div>

      {error && <div className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-lg p-3">{error}</div>}

      {/* KPI summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard testid="smtd-kpi-customers" label="Total Customers" value={fmtNum(t.count || 0)} accent="burgundy" />
        <KPICard testid="smtd-kpi-revenue" label="Total Revenue" value={fmtINR(t.revenue || 0)} fullValue={t.revenue} accent="champagne" />
        <KPICard testid="smtd-kpi-new" label="New (MTD)" value={fmtNum(t.new_count || 0)} accent="burgundy" />
        <KPICard testid="smtd-kpi-active" label="Active (0-6M)" value={fmtNum((rows.find((r) => r.key === "active") || {}).count || 0)} accent="champagne" />
      </div>

      {/* Table */}
      <div>
        <SectionHeading eyebrow="Breakdown" title="By recency segment" />
        <div className="bg-white border border-neutral-200 rounded-xl overflow-hidden">
          <table className="w-full text-sm" data-testid="sales-mtd-table">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wider text-neutral-500 border-b border-neutral-200">
                <th className="px-4 py-3">Segment</th>
                <th className="px-4 py-3 text-right">Customer Count</th>
                <th className="px-4 py-3 text-right">Total Revenue</th>
                <th className="px-4 py-3 text-right">New Customer Count (MTD)</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={4} className="px-4 py-10 text-center text-neutral-400">Loading…</td></tr>
              ) : rows.length === 0 ? (
                <tr><td colSpan={4} className="px-4 py-10 text-center text-neutral-400">No data</td></tr>
              ) : (
                rows.map((r) => (
                  <tr key={r.key} className="border-b border-neutral-100 hover:bg-neutral-50">
                    <td className="px-4 py-3 font-medium text-neutral-800">{r.segment}</td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums">{fmtNum(r.count)}</td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums" title={String(r.revenue)}>{fmtINR(r.revenue)}</td>
                    <td className="px-4 py-3 text-right font-mono tabular-nums">{fmtNum(r.new_count)}</td>
                  </tr>
                ))
              )}
            </tbody>
            {rows.length > 0 && (
              <tfoot>
                <tr className="bg-neutral-50 font-semibold border-t border-neutral-200">
                  <td className="px-4 py-3">Grand Total</td>
                  <td className="px-4 py-3 text-right font-mono tabular-nums">{fmtNum(t.count || 0)}</td>
                  <td className="px-4 py-3 text-right font-mono tabular-nums" title={String(t.revenue)}>{fmtINR(t.revenue || 0)}</td>
                  <td className="px-4 py-3 text-right font-mono tabular-nums">{fmtNum(t.new_count || 0)}</td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      </div>
    </div>
  );
}
