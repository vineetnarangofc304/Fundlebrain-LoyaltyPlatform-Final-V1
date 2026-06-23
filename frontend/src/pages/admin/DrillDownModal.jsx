/* Universal drilldown modal — every dashboard KPI tile opens this.

   Props:
     - title: string                         (modal title)
     - subtitle?: string                     (small caption above title)
     - collection: string                    (whitelisted backend collection key)
     - filter?: object                       (Mongo filter)
     - sort?: [[field, 1|-1], …]
     - columns: [{key, label, render?, align?}]
     - onClose: () => void
     - onRowClick?: (row) => void
*/
import { useEffect, useState, useCallback } from "react";
import api from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { X, Download, ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";

export default function DrillDownModal({
  open,
  onClose,
  title,
  subtitle,
  collection,
  filter = {},
  sort = null,
  columns = [],
  pageSize = 50,
  onRowClick,
}) {
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [downloading, setDownloading] = useState(false);

  const load = useCallback(async (p = 1) => {
    if (!open) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.post("/dashboard/drilldown", {
        collection,
        filter,
        sort,
        page: p,
        page_size: pageSize,
      });
      setData(res.data);
      setPage(p);
    } catch (e) {
      setError(e?.response?.data?.detail || "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [open, collection, JSON.stringify(filter), JSON.stringify(sort), pageSize]);

  useEffect(() => { if (open) load(1); /* eslint-disable-next-line */ }, [open, collection, JSON.stringify(filter)]);

  const exportCSV = async () => {
    setDownloading(true);
    try {
      const res = await api.get("/dashboard/drilldown/csv", {
        params: {
          collection,
          filter: JSON.stringify(filter || {}),
          sort: sort ? JSON.stringify(sort) : undefined,
          columns: JSON.stringify(columns.map((c) => c.key)),
        },
        responseType: "blob",
      });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "text/csv" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `${collection}_${Date.now()}.csv`;
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      setError("CSV export failed");
    } finally {
      setDownloading(false);
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
      onClick={onClose}
      data-testid="drilldown-modal-backdrop"
    >
      <div
        className="bg-white w-full max-w-6xl max-h-[92vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
        data-testid="drilldown-modal"
      >
        <div className="p-5 border-b border-black/10 flex items-center justify-between">
          <div>
            {subtitle && (
              <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-1">
                {subtitle}
              </div>
            )}
            <h3 className="font-display text-2xl tracking-tight" data-testid="drilldown-title">
              {title}
            </h3>
            {data && (
              <div className="text-xs text-neutral-500 mt-1 font-mono">
                {data.total.toLocaleString("en-IN")} rows · page {data.page} of {data.pages || 1}
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => load(page)}
              className="k-btn k-btn-outline k-btn-sm"
              data-testid="drilldown-refresh"
              disabled={loading}
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
            </button>
            <button
              onClick={exportCSV}
              className="k-btn k-btn-outline k-btn-sm"
              data-testid="drilldown-csv"
              disabled={downloading || !data?.total}
            >
              <Download className="w-3.5 h-3.5" /> {downloading ? "Exporting…" : "CSV"}
            </button>
            <button
              onClick={onClose}
              className="text-neutral-500 hover:text-black"
              data-testid="drilldown-close"
              aria-label="Close"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-auto p-5">
          {error && (
            <div className="text-sm text-red-600 mb-3" data-testid="drilldown-error">{error}</div>
          )}
          {loading && !data && (
            <div className="text-sm text-neutral-500" data-testid="drilldown-loading">Loading…</div>
          )}
          {data && data.rows.length === 0 && (
            <div className="text-sm text-neutral-500 py-10 text-center" data-testid="drilldown-empty">
              No rows match this filter.
            </div>
          )}
          {data && data.rows.length > 0 && (
            <div className="overflow-x-auto">
              <table className="data-table w-full">
                <thead>
                  <tr>
                    {columns.map((c) => (
                      <th
                        key={c.key}
                        className={c.align === "right" ? "text-right" : ""}
                      >
                        {c.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((r, i) => (
                    <tr
                      key={r.id || i}
                      onClick={() => onRowClick && onRowClick(r)}
                      className={onRowClick ? "cursor-pointer hover:bg-neutral-50" : ""}
                      data-testid={`drilldown-row-${i}`}
                    >
                      {columns.map((c) => {
                        const v = getNested(r, c.key);
                        return (
                          <td
                            key={c.key}
                            className={c.align === "right" ? "text-right font-mono" : c.mono ? "font-mono text-xs" : ""}
                          >
                            {c.render ? c.render(v, r) : formatDefault(v)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {data && data.pages > 1 && (
          <div className="p-4 border-t border-black/10 flex items-center justify-between text-sm">
            <span className="text-neutral-500 font-mono text-xs">
              Showing {(data.page - 1) * data.page_size + 1}–
              {Math.min(data.page * data.page_size, data.total)} of {data.total.toLocaleString("en-IN")}
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => load(page - 1)}
                disabled={page <= 1 || loading}
                className="k-btn k-btn-outline k-btn-sm"
                data-testid="drilldown-prev"
              >
                <ChevronLeft className="w-3.5 h-3.5" /> Prev
              </button>
              <button
                onClick={() => load(page + 1)}
                disabled={page >= data.pages || loading}
                className="k-btn k-btn-outline k-btn-sm"
                data-testid="drilldown-next"
              >
                Next <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function getNested(obj, path) {
  if (!obj || !path) return undefined;
  if (path.indexOf(".") === -1) return obj[path];
  return path.split(".").reduce((o, k) => (o == null ? o : o[k]), obj);
}

function formatDefault(v) {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "object") return JSON.stringify(v);
  if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}T/.test(v)) return fmtDateTime(v);
  return String(v);
}
