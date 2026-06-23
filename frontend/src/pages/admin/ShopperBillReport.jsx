/* Shopper Bill Report — one row per bill for everyone who shopped in a date range.
   Full filters + sortable columns + server-side pagination + streamed CSV export.
   Spec & recency rules (Active 0-6M / Dormant 6-12M / Lapsed 12M+) per client. */
import { useState, useEffect, useCallback } from "react";
import api from "@/lib/api";
import { requestExport } from "@/lib/exportClient";
import { PageHeader } from "./_shared";
import { ColumnPicker, useColumns } from "./reportkit";
import { fmtMoney2, fmtNum } from "@/lib/format";
import { Download, RefreshCw, Search, ArrowUp, ArrowDown } from "lucide-react";

const isoDaysAgo = (n) => new Date(Date.now() - n * 86400000).toISOString().slice(0, 10);
const today = () => new Date().toISOString().slice(0, 10);

// key, label, numeric?, money?, sortBy (backend SORT_FIELDS value or null)
const COLS = [
  { key: "bill_date", label: "Bill Date", sort: "bill_date", mono: true },
  { key: "bill_time", label: "Time", mono: true },
  { key: "bill_type", label: "Bill Type" },
  { key: "customer_mobile", label: "Mobile", sort: "customer_mobile", mono: true },
  { key: "reg_store", label: "Reg Store" },
  { key: "store_code", label: "Store Code", mono: true },
  { key: "trans_store_name", label: "Trans Store", sort: "store_name" },
  { key: "transaction_id", label: "Trans ID", mono: true },
  { key: "bill_number", label: "Bill #", sort: "bill_number", mono: true },
  { key: "customer_type", label: "Cust Type" },
  { key: "recency", label: "Recency" },
  { key: "last_visit", label: "Last Visit", mono: true },
  { key: "second_last_visit", label: "2nd Last Visit", mono: true },
  { key: "total_visits", label: "Total Visits", num: true },
  { key: "zone", label: "Zone" },
  { key: "store_class", label: "Store Class" },
  { key: "customer_city", label: "City" },
  { key: "net_before_tax", label: "Net (pre-tax)", num: true, money: true },
  { key: "total_tax", label: "Tax", num: true, money: true },
  { key: "total_discount", label: "Discount", num: true, money: true },
  { key: "total_bill_amount", label: "Bill Amount", num: true, money: true, sort: "net_amount" },
  { key: "lifetime_purchase", label: "LT Purchase", num: true, money: true },
  { key: "lifetime_bill_cuts", label: "LT Bill Cuts", num: true },
];

const PAGE_SIZES = [50, 100, 200];

function badge(kind, text) {
  const map = {
    Return: "bg-orange-100 text-orange-800",
    Regular: "bg-emerald-100 text-emerald-800",
  };
  const rec = text.startsWith("Active") ? "bg-emerald-100 text-emerald-800"
    : text.startsWith("Dormant") ? "bg-amber-100 text-amber-800"
    : text.startsWith("Lapsed") ? "bg-rose-100 text-rose-800" : "bg-neutral-100 text-neutral-600";
  const cls = kind === "bill_type" ? (map[text] || "bg-neutral-100 text-neutral-600") : rec;
  return <span className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${cls}`}>{text || "—"}</span>;
}

export default function ShopperBillReport() {
  const [params, setParams] = useState({
    start_date: isoDaysAgo(30),
    end_date: today(),
    bill_type: "all",
    customer_type: "all",
    recency: "all",
    store_id: "",
    zone: "",
    city: "",
    q: "",
    sort_by: "bill_date",
    sort_dir: "desc",
  });
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [opts, setOpts] = useState({ stores: [], zones: [] });

  const { visible, toggle, reset } = useColumns(COLS, "kazo-shopper-cols");
  const cols = COLS.filter((c) => visible.has(c.key));
  const set = (k, v) => setParams((p) => ({ ...p, [k]: v }));

  const cleanParams = useCallback(() => {
    const out = {};
    Object.entries(params).forEach(([k, v]) => {
      if (v === "" || v === "all") return;
      out[k] = v;
    });
    // Recency (Dormant/Lapsed) describes a customer's GLOBAL last visit, which is
    // necessarily OLDER than a recent bill-date window — sending the default recent
    // range would intersect to zero rows. Same for a specific search (mobile / bill /
    // trans-id): the matched bills may sit outside the default 30-day window. In both
    // cases drop the date range so the search spans all history.
    if (out.recency === "dormant" || out.recency === "lapsed" || out.q) {
      delete out.start_date;
      delete out.end_date;
    }
    return out;
  }, [params]);

  const fetchReport = useCallback(async (toPage = 1) => {
    setLoading(true);
    setError(null);
    try {
      const r = await api.get("/shopper-report/bills", {
        params: { ...cleanParams(), limit: pageSize, offset: (toPage - 1) * pageSize },
      });
      setRows(r.data.rows || []);
      setTotal(r.data.total ?? null);
      setHasMore(r.data.has_more ?? false);
      setPage(toPage);
    } catch (e) {
      const msg = e.response?.data?.detail || e.message || "Report failed to load";
      setError(typeof msg === "string" ? msg : "Report failed to load");
    } finally {
      setLoading(false);
    }
  }, [cleanParams, pageSize]);

  useEffect(() => {
    api.get("/shopper-report/filter-options").then((r) => setOpts(r.data)).catch(() => {});
  }, []);
  // initial + re-fetch when sort/pageSize change
  useEffect(() => {
    fetchReport(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.sort_by, params.sort_dir, pageSize]);

  const onSort = (col) => {
    if (!col.sort) return;
    setParams((p) => ({
      ...p,
      sort_by: col.sort,
      sort_dir: p.sort_by === col.sort && p.sort_dir === "desc" ? "asc" : "desc",
    }));
  };

  const exportCsv = async () => {
    setExporting(true);
    try {
      await requestExport({
        report_type: "shopper_bills",
        params: cleanParams(),
        label: "Shopper Bill Report",
        known_total: total,
        filename: `shopper_bill_report_${today()}.csv`,
      });
    } finally {
      setExporting(false);
    }
  };

  const quick = (days, mtd) => {
    if (mtd) {
      const d = new Date();
      set("start_date", new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10));
    } else {
      set("start_date", isoDaysAgo(days));
    }
    set("end_date", today());
  };

  const totalPages = total != null ? Math.max(1, Math.ceil(total / pageSize)) : null;
  const canNext = total != null ? page < totalPages : hasMore;
  const selCls = "k-input w-full !py-1.5 text-sm";
  const lblCls = "text-[10px] uppercase tracking-[0.2em] text-neutral-500 mb-1 block";

  return (
    <div data-testid="shopper-bill-report">
      <PageHeader title="Shopper Bill Report" subtitle="REPORTS · BILL-LEVEL"
        actions={
          <div className="flex items-center gap-2">
            <ColumnPicker columns={COLS} visible={visible} toggle={toggle} reset={reset} testid="sbr-cols" />
            <button onClick={exportCsv} disabled={exporting} className="k-btn k-btn-outline" data-testid="sbr-export">
              <Download className={`w-3.5 h-3.5 ${exporting ? "animate-pulse" : ""}`} /> {exporting ? "Preparing…" : "Download CSV"}
            </button>
          </div>
        }
      />
      <div className="p-8 space-y-6">
        {/* Filters */}
        <div className="chart-card p-5 space-y-4" data-testid="sbr-filters">
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <div>
              <label className={lblCls}>Start date</label>
              <input type="date" value={params.start_date} onChange={(e) => set("start_date", e.target.value)}
                className={selCls} data-testid="sbr-start-date" />
            </div>
            <div>
              <label className={lblCls}>End date</label>
              <input type="date" value={params.end_date} onChange={(e) => set("end_date", e.target.value)}
                className={selCls} data-testid="sbr-end-date" />
            </div>
            <div>
              <label className={lblCls}>Bill type</label>
              <select value={params.bill_type} onChange={(e) => set("bill_type", e.target.value)} className={selCls} data-testid="sbr-bill-type">
                <option value="all">All</option>
                <option value="regular">Regular</option>
                <option value="return">Return</option>
              </select>
            </div>
            <div>
              <label className={lblCls}>Customer type</label>
              <select value={params.customer_type} onChange={(e) => set("customer_type", e.target.value)} className={selCls} data-testid="sbr-cust-type">
                <option value="all">All</option>
                <option value="new">New</option>
                <option value="existing">Existing</option>
              </select>
            </div>
            <div>
              <label className={lblCls}>Recency</label>
              <select value={params.recency} onChange={(e) => set("recency", e.target.value)} className={selCls} data-testid="sbr-recency">
                <option value="all">All</option>
                <option value="active">Active (0-6M)</option>
                <option value="dormant">Dormant (6-12M)</option>
                <option value="lapsed">Lapsed (12M+)</option>
              </select>
              {(params.recency === "dormant" || params.recency === "lapsed") && (
                <div className="text-[9px] text-amber-700 mt-1" data-testid="sbr-recency-hint">Date range ignored — searches all history</div>
              )}
            </div>
            <div>
              <label className={lblCls}>Store</label>
              <select value={params.store_id} onChange={(e) => set("store_id", e.target.value)} className={selCls} data-testid="sbr-store">
                <option value="">All stores</option>
                {opts.stores.map((s) => (
                  <option key={s.id} value={s.id}>{(s.name || s.code) + (s.code ? ` (${s.code})` : "")}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={lblCls}>Zone</label>
              <select value={params.zone} onChange={(e) => set("zone", e.target.value)} className={selCls} data-testid="sbr-zone">
                <option value="">All zones</option>
                {opts.zones.map((z) => <option key={z} value={z}>{z}</option>)}
              </select>
            </div>
            <div>
              <label className={lblCls}>City</label>
              <input value={params.city} onChange={(e) => set("city", e.target.value)} className={selCls} placeholder="City starts with…" data-testid="sbr-city" />
            </div>
            <div className="lg:col-span-2">
              <label className={lblCls}>Search (mobile / bill / trans ID)</label>
              <input value={params.q} onChange={(e) => set("q", e.target.value)} className={selCls}
                onKeyDown={(e) => e.key === "Enter" && fetchReport(1)} data-testid="sbr-search" />
              {params.q && (
                <div className="text-[9px] text-amber-700 mt-1" data-testid="sbr-search-hint">Date range ignored — searches all history</div>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[10px] uppercase tracking-[0.2em] text-neutral-500">Quick:</span>
            <button onClick={() => quick(7)} className="k-btn k-btn-outline k-btn-sm" data-testid="sbr-q7">7d</button>
            <button onClick={() => quick(30)} className="k-btn k-btn-outline k-btn-sm" data-testid="sbr-q30">30d</button>
            <button onClick={() => quick(90)} className="k-btn k-btn-outline k-btn-sm" data-testid="sbr-q90">90d</button>
            <button onClick={() => quick(0, true)} className="k-btn k-btn-outline k-btn-sm" data-testid="sbr-qmtd">This month</button>
            <button onClick={() => quick(365)} className="k-btn k-btn-outline k-btn-sm" data-testid="sbr-q365">1y</button>
            <div className="flex-1" />
            <button onClick={() => fetchReport(1)} disabled={loading} className="k-btn kazo-bg-burgundy text-white" data-testid="sbr-apply">
              <Search className="w-3.5 h-3.5" /> {loading ? "Loading…" : "Apply"}
            </button>
          </div>
        </div>

        {/* Table */}
        <div className="chart-card p-5 overflow-x-auto" data-accent="indigo" data-testid="sbr-table-card">
          <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
            <h3 className="font-display text-xl">
              {rows.length} <span className="text-sm font-normal text-neutral-500">{total != null ? `of ${total.toLocaleString()} bills` : "bills (recency-filtered)"}</span>
            </h3>
            <button onClick={() => fetchReport(page)} className="text-xs px-2 py-1 border border-neutral-300 hover:bg-neutral-50 flex items-center gap-1">
              <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} /> Refresh
            </button>
          </div>

          {error ? (
            <div className="text-sm text-rose-700 py-12 text-center" data-testid="sbr-error">
              <p className="mb-3">{error}</p>
              <button onClick={() => fetchReport(page)} className="k-btn k-btn-outline k-btn-sm" data-testid="sbr-retry">
                <RefreshCw className="w-3.5 h-3.5" /> Retry
              </button>
            </div>
          ) : rows.length === 0 ? (
            <div className="text-sm text-neutral-500 py-12 text-center">
              {loading ? "Loading…" : "No bills found for the current filters."}
            </div>
          ) : (
            <table className="w-full text-sm whitespace-nowrap" data-testid="sbr-table">
              <thead className="border-b border-black/10 text-left">
                <tr>
                  {cols.map((c) => (
                    <th key={c.key}
                      onClick={() => onSort(c)}
                      className={`py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500 ${c.num ? "text-right" : ""} ${c.sort ? "cursor-pointer hover:text-neutral-900 select-none" : ""}`}
                      data-testid={`sbr-th-${c.key}`}
                    >
                      <span className="inline-flex items-center gap-1">
                        {c.label}
                        {c.sort && params.sort_by === c.sort && (
                          params.sort_dir === "desc" ? <ArrowDown className="w-3 h-3" /> : <ArrowUp className="w-3 h-3" />
                        )}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={`${r.bill_number}-${i}`} className="border-b border-black/5 hover:bg-amber-50/40">
                    {cols.map((c) => (
                      <td key={c.key} className={`py-2 px-2 ${c.mono ? "font-mono text-xs" : ""} ${c.num ? "text-right font-mono" : ""}`}>
                        {c.key === "bill_type" || c.key === "recency"
                          ? badge(c.key, r[c.key])
                          : c.money
                            ? fmtMoney2(r[c.key])
                            : c.num
                              ? (r[c.key] === "" || r[c.key] == null ? "—" : fmtNum(r[c.key]))
                              : (r[c.key] === "" || r[c.key] == null ? "—" : r[c.key])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {!error && (
            <div className="flex items-center justify-between mt-4 pt-3 border-t border-black/5" data-testid="sbr-pagination">
              <div className="flex items-center gap-3">
                <span className="text-xs text-neutral-500">Page {page}{totalPages ? ` of ${totalPages}` : ""}</span>
                <select value={pageSize} onChange={(e) => setPageSize(Number(e.target.value))} className="k-input k-input-sm !py-1 text-xs" data-testid="sbr-page-size">
                  {PAGE_SIZES.map((s) => <option key={s} value={s}>{s} / page</option>)}
                </select>
              </div>
              <div className="flex items-center gap-2">
                <button className="k-btn k-btn-outline k-btn-sm" disabled={page <= 1 || loading} onClick={() => fetchReport(page - 1)} data-testid="sbr-prev">← Prev</button>
                <button className="k-btn k-btn-outline k-btn-sm" disabled={!canNext || loading} onClick={() => fetchReport(page + 1)} data-testid="sbr-next">Next →</button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
