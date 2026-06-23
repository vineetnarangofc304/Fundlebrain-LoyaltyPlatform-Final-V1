/* Legacy Reports — shared shell.
   Mirrors newu.fundlezone.com layout: filters → table → CSV export.
   Children pass `endpoint`, `columns`, `defaultParams`, and an optional `filters` block. */
import { useState, useEffect } from "react";
import api from "@/lib/api";
import { requestExport } from "@/lib/exportClient";
import { PageHeader } from "../_shared";
import { Download, RefreshCw, Search } from "lucide-react";
import { toast } from "sonner";

/** Generic report shell — used by every page in /legacy-reports/. */
export function LegacyReportShell({
  title,
  subtitle,
  endpoint,        // e.g. '/legacy-reports/customer-data'
  defaultParams = {},
  filters,         // ReactNode: bound to params via setParam/getParam
  paramsState,     // { params, setParams }
  columns,         // [{ key, label, type, fmt }]
  responseKey = "rows",
  totalKey = "total",
  paginate = true, // server-side limit/offset pagination
  pageSize = 50,
  testid,
}) {
  const { params, setParams } = paramsState;
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [extra, setExtra] = useState({});

  const fetchReport = async (toPage = 1) => {
    setLoading(true);
    setError(null);
    try {
      const pageParams = paginate
        ? { ...params, limit: pageSize, offset: (toPage - 1) * pageSize }
        : params;
      const r = await api.get(endpoint, { params: pageParams });
      setRows(r.data[responseKey] || []);
      setTotal(r.data[totalKey] ?? (r.data[responseKey] || []).length);
      setPage(toPage);
      // Stash any extra response keys (e.g. 'note', 'sort_by') for display
      const ex = {};
      Object.keys(r.data).forEach((k) => {
        if (k !== responseKey && k !== totalKey && k !== "offset" && k !== "limit") ex[k] = r.data[k];
      });
      setExtra(ex);
    } catch (e) {
      const msg = e.response?.data?.detail || e.message || "Report failed to load";
      setError(typeof msg === "string" ? msg : "Report failed to load");
      toast.error(typeof msg === "string" ? msg : "Report failed to load");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchReport(1); /* eslint-disable-next-line */ }, []);

  const totalPages = paginate ? Math.max(1, Math.ceil(total / pageSize)) : 1;

  const exportCsv = async () => {
    const reportType = "legacy_" + endpoint.split("/").pop().replace(/-/g, "_");
    await requestExport({
      report_type: reportType,
      params: { ...params, export: "csv" },
      label: title,
      known_total: total,
      filename: `${title.toLowerCase().replace(/\s+/g, "_")}_${new Date().toISOString().slice(0, 10)}.csv`,
    });
  };

  return (
    <div data-testid={testid}>
      <PageHeader title={title} subtitle={subtitle} />
      <div className="p-8 space-y-6">
        {filters && (
          <div className="chart-card p-5">
            <div className="flex items-end gap-3 flex-wrap">
              {filters}
              <button onClick={fetchReport} disabled={loading} className="k-btn kazo-bg-burgundy text-white" data-testid={`${testid}-apply`}>
                <Search className="w-3.5 h-3.5" /> {loading ? "…" : "Apply"}
              </button>
              <button onClick={exportCsv} className="k-btn k-btn-outline" data-testid={`${testid}-export`}>
                <Download className="w-3.5 h-3.5" /> CSV
              </button>
            </div>
          </div>
        )}

        <div className="chart-card p-5 overflow-x-auto" data-accent="indigo" data-testid={`${testid}-table-card`}>
          <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
            <h3 className="font-display text-xl">
              {rows.length} {total > rows.length ? <span className="text-sm font-normal text-neutral-500">of {total}</span> : "rows"}
            </h3>
            <div className="flex items-center gap-2">
              {Object.entries(extra).map(([k, v]) => (
                typeof v === "string" || typeof v === "number" ? (
                  <span key={k} className="text-xs uppercase tracking-widest text-neutral-500">
                    {k.replace(/_/g, " ")}: <span className="font-mono text-neutral-700">{String(v).slice(0, 60)}</span>
                  </span>
                ) : null
              ))}
              <button onClick={() => fetchReport(page)} className="text-xs px-2 py-1 border border-neutral-300 hover:bg-neutral-50 flex items-center gap-1">
                <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} /> Refresh
              </button>
            </div>
          </div>

          {error ? (
            <div className="text-sm text-rose-700 py-12 text-center" data-testid={`${testid}-error`}>
              <p className="mb-3">{error}</p>
              <button onClick={() => fetchReport(page)} className="k-btn k-btn-outline k-btn-sm" data-testid={`${testid}-retry`}>
                <RefreshCw className="w-3.5 h-3.5" /> Retry
              </button>
            </div>
          ) : rows.length === 0 ? (
            <div className="text-sm text-neutral-500 py-12 text-center">
              {loading ? "Loading…" : (extra.note || "No data found for current filters.")}
            </div>
          ) : (
            <table className="w-full text-sm" data-testid={`${testid}-table`}>
              <thead className="border-b border-black/10 text-left">
                <tr>
                  {columns.map((c) => (
                    <th key={c.key} className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">
                      {c.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={r.id || r.mobile || r.bill_number || r.code || i} className="border-b border-black/5 hover:bg-amber-50/40">
                    {columns.map((c) => (
                      <td key={c.key} className={`py-2 px-2 ${c.cellClass || ""}`}>
                        {c.fmt ? c.fmt(r[c.key], r) : (r[c.key] ?? "—")}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {paginate && totalPages > 1 && !error && (
            <div className="flex items-center justify-between mt-4 pt-3 border-t border-black/5" data-testid={`${testid}-pagination`}>
              <span className="text-xs text-neutral-500">
                Page {page} of {totalPages} · {total.toLocaleString()} rows
              </span>
              <div className="flex items-center gap-2">
                <button
                  className="k-btn k-btn-outline k-btn-sm"
                  disabled={page <= 1 || loading}
                  onClick={() => fetchReport(page - 1)}
                  data-testid={`${testid}-prev`}
                >
                  ← Prev
                </button>
                <button
                  className="k-btn k-btn-outline k-btn-sm"
                  disabled={page >= totalPages || loading}
                  onClick={() => fetchReport(page + 1)}
                  data-testid={`${testid}-next`}
                >
                  Next →
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/** Tiny helper: param-state hook with setter. */
export function useReportParams(initial = {}) {
  const [params, setParams] = useState(initial);
  const set = (k, v) => setParams((p) => ({ ...p, [k]: v === "" ? undefined : v }));
  return { params, setParams, set };
}

/** Date-range filter pair. */
export function DatePair({ paramsState }) {
  const { params, set } = paramsState;
  return (
    <>
      <div>
        <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Start date</label>
        <input type="date" value={params.start_date || ""} onChange={(e) => set("start_date", e.target.value)} className="k-input" />
      </div>
      <div>
        <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">End date</label>
        <input type="date" value={params.end_date || ""} onChange={(e) => set("end_date", e.target.value)} className="k-input" />
      </div>
    </>
  );
}
