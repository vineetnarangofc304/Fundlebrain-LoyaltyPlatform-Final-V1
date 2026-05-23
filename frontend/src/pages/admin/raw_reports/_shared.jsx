/* Shared scaffolding for the 5 raw-data reports. */
import { useState, useEffect, useRef, useMemo } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Legend,
  CartesianGrid, ComposedChart, Line, LabelList,
} from "recharts";
import {
  Filter as FilterIcon, Search, Sparkles, Loader2,
  Download, FileText, FileSpreadsheet, FileType2, ChevronDown,
  ChevronUp, ChevronsUpDown, RefreshCw, Columns3, Check,
} from "lucide-react";
import CustomerDetailDrawer from "../_customer_drawer";

export const KAZO_PALETTE = [
  "#3B1A2A", "#9b2c2c", "#84cc16", "#0e7c7b", "#7c3aed",
  "#f59e0b", "#0ea5e9", "#ec4899", "#10b981", "#6366f1",
  "#facc15", "#64748b",
];

export const fmtNum = (v) => v == null ? "—" : Number(v).toLocaleString("en-IN");
export const fmtINR = (v) => v == null ? "—" : `₹${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
export const fmtPct = (v) => v == null ? "—" : `${Number(v).toFixed(1)}%`;
export const fmtDecimal = (v) => v == null ? "—" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: 2 });

/* ============================================================
 * Filter Bar — date range + group_by radio + apply
 * group_by clicks auto-trigger refetch via onChange(value, true).
 * ============================================================ */
export function FilterBar({ groupOptions, value, onChange, onApply, loading, extraSlot }) {
  return (
    <div className="bg-white border border-neutral-200 rounded-lg p-4 mb-4" data-testid="report-filter-bar">
      <div className="flex flex-wrap gap-4 items-end">
        <div className="flex flex-col">
          <label className="text-[10px] uppercase tracking-widest text-neutral-500 mb-1">Start Date</label>
          <input
            type="date"
            value={value.start_date || ""}
            onChange={(e) => onChange({ ...value, start_date: e.target.value })}
            className="border border-neutral-300 rounded px-2 py-1.5 text-sm w-44"
            data-testid="filter-start-date"
          />
        </div>
        <div className="flex flex-col">
          <label className="text-[10px] uppercase tracking-widest text-neutral-500 mb-1">End Date</label>
          <input
            type="date"
            value={value.end_date || ""}
            onChange={(e) => onChange({ ...value, end_date: e.target.value })}
            className="border border-neutral-300 rounded px-2 py-1.5 text-sm w-44"
            data-testid="filter-end-date"
          />
        </div>
        {extraSlot}
        <button
          onClick={onApply}
          disabled={loading}
          className="px-4 py-1.5 text-sm font-medium text-white rounded disabled:opacity-50 flex items-center gap-1"
          style={{ backgroundColor: "#9b2c2c" }}
          data-testid="filter-apply"
        >
          {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FilterIcon className="w-3.5 h-3.5" />}
          {loading ? "Loading…" : "Apply Filters"}
        </button>
      </div>
      {groupOptions && (
        <div className="mt-3 pt-3 border-t border-neutral-100">
          <label className="text-[10px] uppercase tracking-widest text-neutral-500 mr-3">Report Type</label>
          <div className="inline-flex gap-1 flex-wrap">
            {groupOptions.map((opt) => (
              <button
                key={opt}
                type="button"
                onClick={() => onChange({ ...value, group_by: opt }, true)}
                className={`text-xs px-3 py-1 rounded-full border ${
                  value.group_by === opt
                    ? "bg-amber-50 font-medium"
                    : "bg-white text-neutral-600 border-neutral-300 hover:bg-neutral-50"
                }`}
                style={value.group_by === opt ? { color: "#9b2c2c", borderColor: "#9b2c2c" } : {}}
                data-testid={`group-${opt}`}
              >
                {opt[0].toUpperCase() + opt.slice(1)}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ============================================================
 * AI Narrative Card — DEFERRED: fires 1s AFTER data lands, so the
 * report renders first. Lives at the BOTTOM of the page.
 * ============================================================ */
export function NarrativeCard({ report, group_by, rows, totals, filters, deps }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const generate = async () => {
    if (!rows || rows.length === 0) return;
    setLoading(true);
    try {
      const r = await api.post("/raw-reports/narrative", { report, group_by, rows, totals, filters });
      setData(r.data);
    } catch (e) {
      // Silent — narrative is non-critical
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setData(null);
    if (!rows || rows.length === 0) return;
    // Defer so the report renders FIRST, then narrative kicks in
    const t = setTimeout(generate, 1000);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(deps || [rows?.length, group_by])]);

  if (!rows || rows.length === 0) return null;
  return (
    <div className="mt-4 border border-indigo-200 bg-gradient-to-br from-indigo-50/40 to-amber-50/30 rounded-lg p-4" data-testid="narrative-card">
      <div className="flex items-center justify-between mb-2">
        <div className="text-[10px] uppercase tracking-widest text-indigo-700 font-medium flex items-center gap-1">
          <Sparkles className="w-3 h-3" /> Fundle Brain · AI Insights
          {data?.source && (
            <span className="text-neutral-500 normal-case tracking-normal ml-2">
              {data.source === "fundle_brain_gpt5" ? "GPT-5" : data.source}
            </span>
          )}
        </div>
        <button
          onClick={generate}
          disabled={loading}
          className="text-[10px] flex items-center gap-1 px-2 py-1 border border-indigo-300 text-indigo-700 rounded hover:bg-indigo-50 disabled:opacity-50"
          data-testid="narrative-regen"
        >
          {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
          Refresh
        </button>
      </div>
      {loading && !data ? (
        <div className="text-xs text-neutral-500 italic flex items-center gap-1.5">
          <Loader2 className="w-3 h-3 animate-spin" /> Fundle Brain is reading your data…
        </div>
      ) : data?.bullets?.length > 0 ? (
        <ul className="space-y-1.5 text-sm text-neutral-800">
          {data.bullets.map((b, i) => (
            <li key={i} className="flex gap-2">
              <span style={{ color: "#9b2c2c" }}>•</span>
              <span>{b}</span>
            </li>
          ))}
        </ul>
      ) : data?.narrative ? (
        <div className="text-sm text-neutral-800 whitespace-pre-wrap">{data.narrative}</div>
      ) : null}
    </div>
  );
}

/* ============================================================
 * Column Picker — toggle visibility of optional columns
 * ============================================================ */
export function ColumnPicker({ allColumns, visibleKeys, onChange, requiredKeys = [] }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [open]);

  const toggle = (k) => {
    if (requiredKeys.includes(k)) return;
    onChange(visibleKeys.includes(k) ? visibleKeys.filter((x) => x !== k) : [...visibleKeys, k]);
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="text-xs flex items-center gap-1 px-3 py-1.5 border border-neutral-300 bg-white rounded hover:bg-neutral-50"
        data-testid="column-picker-btn"
      >
        <Columns3 className="w-3.5 h-3.5" />
        Columns ({visibleKeys.length}/{allColumns.length})
        <ChevronDown className="w-3 h-3" />
      </button>
      {open && (
        <div className="absolute right-0 mt-1 w-64 bg-white border border-neutral-200 rounded shadow-lg z-30 overflow-hidden max-h-80 overflow-y-auto" data-testid="column-picker-menu">
          <div className="px-3 py-2 text-[10px] uppercase tracking-widest text-neutral-400 border-b border-neutral-100 bg-neutral-50">
            Show / hide columns
          </div>
          {allColumns.map((c) => {
            const isVisible = visibleKeys.includes(c.key);
            const isLocked = requiredKeys.includes(c.key);
            return (
              <button
                key={c.key}
                type="button"
                onClick={() => toggle(c.key)}
                className={`w-full flex items-center gap-2 px-3 py-1.5 text-xs text-left hover:bg-amber-50 ${
                  isLocked ? "opacity-60 cursor-not-allowed" : ""
                }`}
                data-testid={`col-toggle-${c.key}`}
              >
                <div className={`w-3.5 h-3.5 border rounded flex items-center justify-center ${
                  isVisible ? "bg-emerald-600 border-emerald-600" : "border-neutral-300 bg-white"
                }`}>
                  {isVisible && <Check className="w-2.5 h-2.5 text-white" />}
                </div>
                <span className="flex-1">{c.label}</span>
                {isLocked && <span className="text-[9px] text-neutral-400">locked</span>}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ============================================================
 * Export Menu (CSV / XLSX / PDF) — reuses /raw-reports/export
 * ============================================================ */
export function ExportMenu({ report, group_by, columns, rows, totals }) {
  const [open, setOpen] = useState(false);
  const [exporting, setExporting] = useState(null);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [open]);

  const onExport = async (fmt) => {
    setExporting(fmt);
    setOpen(false);
    const tid = toast.loading(`Preparing ${fmt.toUpperCase()}…`);
    try {
      const resp = await api.post("/raw-reports/export", {
        report, group_by, columns, rows, totals, format: fmt,
      }, { responseType: "blob", timeout: 300000 });
      const cd = resp.headers["content-disposition"] || "";
      const m = /filename="?([^";]+)"?/.exec(cd);
      const fname = m ? m[1] : `${report}_${Date.now()}.${fmt}`;
      const blob = new Blob([resp.data]);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = fname;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success(`Exported ${rows.length} rows as ${fmt.toUpperCase()}`, { id: tid });
    } catch (e) {
      toast.error("Export failed", { id: tid });
    } finally {
      setExporting(null);
    }
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        disabled={exporting || rows.length === 0}
        className="text-xs flex items-center gap-1 px-3 py-1.5 bg-emerald-600 text-white rounded hover:bg-emerald-700 disabled:opacity-50"
        data-testid="report-export"
      >
        {exporting ? (
          <><Loader2 className="w-3.5 h-3.5 animate-spin" /> {exporting.toUpperCase()}…</>
        ) : (
          <><Download className="w-3.5 h-3.5" /> Export <ChevronDown className="w-3 h-3" /></>
        )}
      </button>
      {open && (
        <div className="absolute right-0 mt-1 w-44 bg-white border border-neutral-200 rounded shadow-lg z-20 overflow-hidden" data-testid="export-menu">
          <button onClick={() => onExport("csv")} data-testid="export-csv" className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-amber-50 text-left">
            <FileText className="w-3.5 h-3.5 text-neutral-500" /> CSV (.csv)
          </button>
          <button onClick={() => onExport("xlsx")} data-testid="export-xlsx" className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-amber-50 text-left">
            <FileSpreadsheet className="w-3.5 h-3.5 text-neutral-500" /> Excel (.xlsx)
          </button>
          <button onClick={() => onExport("pdf")} data-testid="export-pdf" className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-amber-50 text-left">
            <FileType2 className="w-3.5 h-3.5 text-neutral-500" /> PDF (.pdf)
          </button>
        </div>
      )}
    </div>
  );
}

/* ============================================================
 * Sortable / searchable / paginated table
 * EVERY numeric cell is drill-down clickable when onCellClick is set.
 * ============================================================ */
export function ReportTable({ columns, rows, totals, onCellClick, defaultSort, multiHeader, loading }) {
  const [sort, setSort] = useState(defaultSort || { key: null, dir: -1 });
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 25;

  const filtered = useMemo(() => {
    if (!search.trim()) return rows;
    const s = search.toLowerCase();
    return rows.filter((r) => columns.some((c) => String(r[c.key] ?? "").toLowerCase().includes(s)));
  }, [rows, search, columns]);

  const sorted = useMemo(() => {
    if (!sort.key) return filtered;
    return [...filtered].sort((a, b) => {
      const va = a[sort.key]; const vb = b[sort.key];
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      if (typeof va === "number") return (va - vb) * sort.dir * -1;
      return String(va).localeCompare(String(vb)) * sort.dir * -1;
    });
  }, [filtered, sort]);

  const pages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const startIdx = (page - 1) * pageSize;
  const pageRows = sorted.slice(startIdx, startIdx + pageSize);

  const toggleSort = (key) => {
    if (sort.key === key) setSort((s) => ({ ...s, dir: -s.dir }));
    else setSort({ key, dir: -1 });
    setPage(1);
  };

  return (
    <div className="bg-white border border-neutral-200 rounded-lg overflow-hidden" data-testid="report-table">
      <div className="px-4 py-2.5 border-b border-neutral-100 flex items-center justify-between gap-2 flex-wrap">
        <div className="text-xs text-neutral-500 flex items-center gap-2">
          {loading ? (
            <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading data…</>
          ) : (
            <>{fmtNum(sorted.length)} rows {search && `(filtered from ${fmtNum(rows.length)})`}</>
          )}
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2 top-1/2 -translate-y-1/2 text-neutral-400" />
            <input
              type="text"
              placeholder="Search…"
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              className="border border-neutral-300 rounded pl-7 pr-2 py-1 text-xs w-56"
              data-testid="report-search"
            />
          </div>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="bg-neutral-50 text-neutral-700">
            {multiHeader ? (
              multiHeader
            ) : (
              <tr>
                {columns.map((c) => (
                  <th
                    key={c.key}
                    onClick={() => c.sortable !== false && toggleSort(c.key)}
                    className={`px-3 py-2 text-left font-medium uppercase tracking-widest text-[10px] ${
                      c.sortable !== false ? "cursor-pointer hover:bg-neutral-100" : ""
                    } ${c.align === "right" ? "text-right" : ""}`}
                    style={{ minWidth: c.width || undefined }}
                  >
                    <span className="inline-flex items-center gap-1">
                      {c.label}
                      {c.sortable !== false && (
                        sort.key === c.key
                          ? (sort.dir === -1 ? <ChevronDown className="w-3 h-3" /> : <ChevronUp className="w-3 h-3" />)
                          : <ChevronsUpDown className="w-3 h-3 opacity-30" />
                      )}
                    </span>
                  </th>
                ))}
              </tr>
            )}
          </thead>
          <tbody>
            {loading && pageRows.length === 0 && (
              // Skeleton rows so user sees the table "reacting" to filter changes
              [0, 1, 2, 3, 4].map((i) => (
                <tr key={`sk-${i}`} className="border-t border-neutral-100" data-testid={`skeleton-row-${i}`}>
                  {columns.map((c) => (
                    <td key={c.key} className="px-3 py-2.5">
                      <div className="h-3 bg-neutral-100 rounded animate-pulse" style={{ width: c.align === "right" ? "60%" : "80%", marginLeft: c.align === "right" ? "auto" : 0 }} />
                    </td>
                  ))}
                </tr>
              ))
            )}
            {pageRows.map((r, i) => (
              <tr key={i} className="border-t border-neutral-100 hover:bg-amber-50/30" data-testid={`row-${i}`}>
                {columns.map((c) => {
                  const val = r[c.key];
                  const formatted = c.format ? c.format(val) : (val ?? "—");
                  const isNumber = typeof val === "number";
                  const drillable = onCellClick && c.drillable !== false && c.key !== "sno";
                  return (
                    <td key={c.key} className={`px-3 py-2 ${c.align === "right" ? "text-right font-mono" : ""}`}>
                      {c.render ? c.render(val, r) : (
                        drillable && isNumber ? (
                          <button
                            onClick={() => onCellClick(c, r)}
                            className="underline decoration-dotted hover:text-burgundy"
                            style={{ color: "#9b2c2c" }}
                            data-testid={`cell-${i}-${c.key}`}
                          >
                            {formatted}
                          </button>
                        ) : (
                          formatted
                        )
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
            {!loading && pageRows.length === 0 && (
              <tr><td colSpan={columns.length} className="text-center py-8 text-neutral-400 italic">No data</td></tr>
            )}
            {totals && pageRows.length > 0 && (
              <tr className="border-t-2 border-neutral-300 bg-neutral-50 font-medium">
                {columns.map((c, i) => (
                  <td key={c.key} className={`px-3 py-2 ${c.align === "right" ? "text-right font-mono" : ""}`}>
                    {i === 0 ? "TOTAL" : (c.format ? c.format(totals[c.key]) : (totals[c.key] ?? ""))}
                  </td>
                ))}
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {pages > 1 && (
        <div className="px-3 py-2 border-t border-neutral-100 flex items-center justify-between text-xs">
          <span className="text-neutral-500">Page {page} of {pages}</span>
          <div className="flex gap-1">
            <button disabled={page === 1} onClick={() => setPage((p) => Math.max(1, p - 1))} className="px-2 py-1 border rounded disabled:opacity-40">Prev</button>
            <button disabled={page === pages} onClick={() => setPage((p) => Math.min(pages, p + 1))} className="px-2 py-1 border rounded disabled:opacity-40">Next</button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ============================================================
 * Drill-Down Modal — shows customers for a clicked cell
 * ============================================================ */
export function DrillModal({ open, onClose, report, group_by, group_key, metric, visits, filters }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [drawerMobile, setDrawerMobile] = useState(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    api.post("/raw-reports/drill", {
      report, group_by, group_key, metric, visits, filters, page, page_size: 50,
    }).then((r) => setData(r.data)).catch(() => toast.error("Drill failed"))
      .finally(() => setLoading(false));
  }, [open, group_key, metric, visits, page]); // eslint-disable-line

  if (!open) return null;
  return (
    <div className="fixed inset-0 bg-black/50 z-40 flex items-center justify-center p-4" onClick={onClose} data-testid="drill-modal">
      <div className="bg-white rounded-lg max-w-5xl w-full max-h-[85vh] overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="px-5 py-3 border-b border-neutral-200 flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-widest text-neutral-500">{report} · {group_by}</div>
            <div className="font-display text-lg">{group_key}{metric ? ` · ${metric}` : ""}{visits != null ? ` · ${visits} visits` : ""}</div>
          </div>
          <button onClick={onClose} className="text-neutral-400 hover:text-neutral-700 text-2xl leading-none">×</button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {loading && <div className="p-8 text-center"><Loader2 className="w-5 h-5 animate-spin inline-block text-neutral-400" /></div>}
          {data && (
            <table className="w-full text-xs">
              <thead className="bg-neutral-50 text-neutral-700 sticky top-0">
                <tr>
                  <th className="px-3 py-2 text-left">Mobile</th>
                  <th className="px-3 py-2 text-left">Name</th>
                  <th className="px-3 py-2 text-left">City</th>
                  <th className="px-3 py-2 text-left">Tier</th>
                  <th className="px-3 py-2 text-right">Bills</th>
                  <th className="px-3 py-2 text-right">Lifetime Spend</th>
                  <th className="px-3 py-2 text-right">Points</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((c) => (
                  <tr key={c.mobile} className="border-t border-neutral-100 hover:bg-amber-50/30 cursor-pointer"
                       onClick={() => setDrawerMobile(c.mobile)}
                       data-testid={`drill-row-${c.mobile}`}>
                    <td className="px-3 py-1.5 font-mono">{c.mobile}</td>
                    <td className="px-3 py-1.5">{c.name || "—"}</td>
                    <td className="px-3 py-1.5">{c.city || "—"}</td>
                    <td className="px-3 py-1.5">{c.tier || "—"}</td>
                    <td className="px-3 py-1.5 text-right font-mono">{fmtNum(c.visit_count)}</td>
                    <td className="px-3 py-1.5 text-right font-mono">{fmtINR(c.lifetime_spend)}</td>
                    <td className="px-3 py-1.5 text-right font-mono">{fmtNum(c.points_balance)}</td>
                  </tr>
                ))}
                {data.rows.length === 0 && (
                  <tr><td colSpan={7} className="text-center py-8 text-neutral-400 italic">No customers in this slice</td></tr>
                )}
              </tbody>
            </table>
          )}
        </div>
        {data && data.pages > 1 && (
          <div className="px-5 py-2 border-t border-neutral-200 flex justify-between text-xs items-center">
            <span>Page {data.page} of {data.pages} · {fmtNum(data.total)} customers</span>
            <div className="flex gap-1">
              <button disabled={page === 1} onClick={() => setPage((p) => p - 1)} className="px-2 py-1 border rounded disabled:opacity-40">Prev</button>
              <button disabled={page === data.pages} onClick={() => setPage((p) => p + 1)} className="px-2 py-1 border rounded disabled:opacity-40">Next</button>
            </div>
          </div>
        )}
      </div>
      <CustomerDetailDrawer mobile={drawerMobile} open={!!drawerMobile} onClose={() => setDrawerMobile(null)} />
    </div>
  );
}

/* ============================================================
 * Chart wrappers — bar / composed
 * ============================================================ */
export function ReportBarChart({ data, dataKey, xKey = "label", title, color }) {
  if (!data || data.length === 0) return null;
  return (
    <div className="bg-white border border-neutral-200 rounded-lg p-4" data-testid="report-chart">
      {title && <div className="text-sm font-medium mb-3 text-neutral-700">{title}</div>}
      <ResponsiveContainer width="100%" height={360}>
        <BarChart data={data} margin={{ top: 20, right: 16, left: 8, bottom: 56 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey={xKey} angle={-25} textAnchor="end" interval={0} tick={{ fontSize: 10 }} height={70} />
          <YAxis tick={{ fontSize: 10 }} />
          <Tooltip />
          <Bar dataKey={dataKey} fill={color || "#9b2c2c"} radius={[4, 4, 0, 0]}>
            <LabelList dataKey={dataKey} position="top" style={{ fontSize: 10, fill: "#3B1A2A" }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ReportComposedChart({ data, bars, lines, xKey = "label", title }) {
  if (!data || data.length === 0) return null;
  return (
    <div className="bg-white border border-neutral-200 rounded-lg p-4" data-testid="report-chart">
      {title && <div className="text-sm font-medium mb-3 text-neutral-700">{title}</div>}
      <ResponsiveContainer width="100%" height={400}>
        <ComposedChart data={data} margin={{ top: 20, right: 16, left: 8, bottom: 56 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey={xKey} angle={-25} textAnchor="end" interval={0} tick={{ fontSize: 10 }} height={70} />
          <YAxis tick={{ fontSize: 10 }} />
          <Tooltip />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          {bars.map((b, i) => (
            <Bar key={b.key} dataKey={b.key} name={b.label} fill={b.color || KAZO_PALETTE[i % KAZO_PALETTE.length]} radius={[4, 4, 0, 0]} />
          ))}
          {lines.map((l, i) => (
            <Line key={l.key} type="monotone" dataKey={l.key} name={l.label}
                    stroke={l.color || KAZO_PALETTE[(i + bars.length) % KAZO_PALETTE.length]}
                    strokeWidth={2} dot={{ r: 3 }} strokeDasharray={l.dashed ? "5 5" : undefined} />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
