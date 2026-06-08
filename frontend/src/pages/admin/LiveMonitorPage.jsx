/* Live Monitor — cockpit-style real-time view of every bill flowing into Fundle.
   Green = mobile attached. Red = "Lost Opportunity" (anonymous walk-in / no mobile). */
import { useEffect, useMemo, useRef, useState } from "react";
import api from "@/lib/api";
import { PageHeader, SectionHeading } from "./_shared";
import { fmtDateTime } from "@/lib/format";
import { toast } from "sonner";
import {
  Activity, ShoppingBag, AlertTriangle, CheckCircle2, RefreshCw, Pause, Play,
  Phone, PhoneOff, MapPin, Receipt, Filter, X, TrendingDown, Coins, Award, Calculator,
} from "lucide-react";

const PALETTE = {
  burgundy: "#571326",
  indigo: "#1E3A8A",
  teal: "#0E7C7B",
  amber: "#B45309",
  rose: "#9F1239",
  emerald: "#047857",
};

export default function LiveMonitorPage() {
  const [rows, setRows] = useState([]);
  const [stats, setStats] = useState(null);
  const [stores, setStores] = useState([]);
  const [paused, setPaused] = useState(false);
  const [recalcing, setRecalcing] = useState(false);
  const [filters, setFilters] = useState({
    store_id: "",
    region: "",
    has_mobile: "all", // all | yes | no
    payment_mode: "",
    source: "",
    min_amount: "",
    max_amount: "",
    start_date: "",
    end_date: "",
  });
  const [statsWindow, setStatsWindow] = useState(10080); // default = 7d so the KPI strip and table aren't blank on fresh login (a 24h default would show zero on quieter stores)
  const [drillRow, setDrillRow] = useState(null);
  const lastFetchRef = useRef(null);

  const load = () => {
    const hasRange = filters.start_date || filters.end_date;
    const params = { limit: 200 };
    const statsParams = {};
    if (hasRange) {
      // Explicit date range overrides the relative stats window
      if (filters.start_date) { params.start_date = filters.start_date; statsParams.start_date = filters.start_date; }
      if (filters.end_date) { params.end_date = filters.end_date; statsParams.end_date = filters.end_date; }
    } else {
      params.since_minutes = statsWindow;
      statsParams.minutes = statsWindow;
    }
    Object.entries(filters).forEach(([k, v]) => {
      if (k === "start_date" || k === "end_date") return;
      if (v !== "" && v !== "all") params[k] = v;
    });
    return Promise.all([
      api.get("/live-monitor/transactions", { params }),
      api.get("/live-monitor/stats", { params: statsParams }),
    ]).then(([tx, st]) => {
      setRows(tx.data.rows || []);
      setStats(st.data || null);
      lastFetchRef.current = new Date();
    }).catch((e) => console.error("live-monitor load failed", e));
  };

  const loadStores = () => api.get("/stores").then((r) => setStores(r.data || [])).catch(() => {});

  // Re-credit points for bills that earned 0 (e.g. captured before the earn-engine fix).
  // Dry-run first to preview, then confirm to apply. Idempotent on the backend.
  const recalcPoints = async () => {
    setRecalcing(true);
    try {
      const preview = (await api.post("/live-monitor/recalc-points", { dry_run: true })).data;
      if (!preview.eligible) {
        toast.info("No bills need recalculation — all eligible sale bills already have points.");
        return;
      }
      const ok = window.confirm(
        `${preview.eligible} bill(s) currently have 0 points and qualify to earn ` +
        `${preview.total_points.toLocaleString()} points total.\n\nApply now and credit the customers?`
      );
      if (!ok) return;
      const res = (await api.post("/live-monitor/recalc-points", { dry_run: false })).data;
      toast.success(`Recalculated ${res.credited} bill(s) · credited ${res.total_points.toLocaleString()} points.`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Recalculation failed");
    } finally {
      setRecalcing(false);
    }
  };

  useEffect(() => { loadStores(); }, []);
  useEffect(() => {
    load();
    if (paused) return undefined;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [paused, filters, statsWindow]);

  const clearFilters = () => setFilters({ store_id: "", region: "", has_mobile: "all", payment_mode: "", source: "", min_amount: "", max_amount: "", start_date: "", end_date: "" });
  const activeFilterCount = useMemo(() =>
    Object.values(filters).filter((v) => v !== "" && v !== "all").length, [filters]);

  return (
    <div data-testid="live-monitor-page">
      <PageHeader
        title="Live Bill Monitor"
        subtitle={`COCKPIT · ${rows.length} BILLS · AUTO-REFRESH ${paused ? "PAUSED" : "EVERY 3s"}`}
        actions={
          <>
            <button onClick={() => setPaused((p) => !p)} className="k-btn k-btn-outline k-btn-sm" data-testid="lm-toggle-pause">
              {paused ? <><Play className="w-3.5 h-3.5" /> Resume</> : <><Pause className="w-3.5 h-3.5" /> Pause</>}
            </button>
            <button onClick={recalcPoints} disabled={recalcing} className="k-btn k-btn-outline k-btn-sm" data-testid="lm-recalc-points">
              <Calculator className="w-3.5 h-3.5" /> {recalcing ? "Recalculating…" : "Recalc points"}
            </button>
            <button onClick={load} className="k-btn k-btn-outline k-btn-sm" data-testid="lm-refresh">
              <RefreshCw className="w-3.5 h-3.5" /> Refresh now
            </button>
          </>
        }
      />

      <div className="p-8 space-y-6">
        {/* KPI strip */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-9 gap-3" data-testid="lm-kpis">
            <KPI label="Bills" value={(stats.bills_total || 0).toLocaleString()} icon={Receipt} color={PALETTE.burgundy} />
            <KPI label="Loyalty Bills" value={(stats.bills_with_mobile || 0).toLocaleString()} icon={Phone} color={PALETTE.emerald} testid="lm-kpi-loyalty-bills" />
            <KPI label="Repeat Bills" value={(stats.repeat_bills || 0).toLocaleString()} icon={Award} color={PALETTE.indigo} testid="lm-kpi-repeat-bills" />
            <KPI label="Lost Opp." value={(stats.bills_without_mobile || 0).toLocaleString()}
                  icon={PhoneOff} color={PALETTE.rose} testid="lm-kpi-lost" />
            <KPI label="Attach %" value={`${(stats.mobile_attach_rate_pct || 0).toFixed(1)}%`} icon={CheckCircle2} color={PALETTE.indigo} />
            <KPI label="Total Purchase" value={fmtCurrency(stats.revenue_total)} icon={ShoppingBag} color={PALETTE.teal} testid="lm-kpi-total-rev" />
            <KPI label="Loyalty Purchase" value={fmtCurrency(stats.revenue_with_mobile)} icon={Award} color={PALETTE.emerald} testid="lm-kpi-loyalty-rev" />
            <KPI label="Pts Earned" value={(stats.points_earned || 0).toLocaleString()} icon={Coins} color={PALETTE.amber} />
            <KPI label="Returns" value={(stats.returns || 0).toLocaleString()} icon={TrendingDown} color={PALETTE.rose} />
          </div>
        )}

        {/* Filter row */}
        <div className="chart-card p-4" data-accent="indigo">
          <div className="flex flex-wrap items-end gap-3">
            <div className="text-[10px] uppercase tracking-[0.25em] text-neutral-500 self-center mr-1 flex items-center gap-1">
              <Filter className="w-3 h-3" /> FILTERS {activeFilterCount > 0 && <span className="pill pill-info ml-1">{activeFilterCount}</span>}
            </div>
            <Select label="Mobile" value={filters.has_mobile} onChange={(v) => setFilters({ ...filters, has_mobile: v })} options={[
              { value: "all", label: "All" },
              { value: "yes", label: "With mobile" },
              { value: "no", label: "Lost opp. only" },
            ]} testid="lm-fil-mobile" />
            <Select label="Store" value={filters.store_id} onChange={(v) => setFilters({ ...filters, store_id: v })} options={[
              { value: "", label: "All stores" },
              ...stores.map((s) => ({ value: s.id, label: s.name || s.code })),
            ]} testid="lm-fil-store" />
            <Select label="Source" value={filters.source} onChange={(v) => setFilters({ ...filters, source: v })} options={[
              { value: "", label: "All" },
              { value: "pos_ewards", label: "POS (live)" },
              { value: "historic_upload", label: "Historical" },
              { value: "pos_auto", label: "POS auto-created" },
            ]} testid="lm-fil-source" />
            <Select label="Payment" value={filters.payment_mode} onChange={(v) => setFilters({ ...filters, payment_mode: v })} options={[
              { value: "", label: "All" },
              { value: "upi", label: "UPI" },
              { value: "card", label: "Card" },
              { value: "cash", label: "Cash" },
              { value: "wallet", label: "Wallet" },
            ]} testid="lm-fil-payment" />
            <NumInput label="Min ₹" value={filters.min_amount} onChange={(v) => setFilters({ ...filters, min_amount: v })} testid="lm-fil-min" />
            <NumInput label="Max ₹" value={filters.max_amount} onChange={(v) => setFilters({ ...filters, max_amount: v })} testid="lm-fil-max" />
            <DateInput label="From date" value={filters.start_date} onChange={(v) => setFilters({ ...filters, start_date: v })} testid="lm-fil-start-date" />
            <DateInput label="To date" value={filters.end_date} onChange={(v) => setFilters({ ...filters, end_date: v })} testid="lm-fil-end-date" />
            <Select label="Stats window" value={String(statsWindow)} onChange={(v) => setStatsWindow(Number(v))} disabled={!!(filters.start_date || filters.end_date)} options={[
              { value: "15", label: "Last 15m" },
              { value: "60", label: "Last 1h" },
              { value: "360", label: "Last 6h" },
              { value: "1440", label: "Last 24h" },
              { value: "10080", label: "Last 7d" },
              { value: "43200", label: "Last 30d" },
              { value: "129600", label: "Last 90d" },
              { value: "525600", label: "Last 365d" },
            ]} testid="lm-fil-window" />
            {(filters.start_date || filters.end_date) && (
              <div className="self-center text-[10px] text-amber-700 uppercase tracking-widest" data-testid="lm-range-active">Date range active · live window ignored</div>
            )}
            {activeFilterCount > 0 && (
              <button onClick={clearFilters} className="k-btn k-btn-ghost k-btn-sm" data-testid="lm-clear-filters">
                <X className="w-3 h-3" /> Clear
              </button>
            )}
          </div>
        </div>

        {/* Top stores */}
        {stats?.by_store_top10?.length > 0 && (
          <div className="chart-card p-5" data-accent="teal">
            <SectionHeading eyebrow={(filters.start_date || filters.end_date) ? `${filters.start_date || "…"} → ${filters.end_date || "…"}` : `LAST ${statsWindow} MIN`} title="Top stores by revenue" accent="teal" />
            <div className="grid md:grid-cols-2 lg:grid-cols-5 gap-3 mt-3">
              {stats.by_store_top10.slice(0, 5).map((s) => (
                <div key={s.store_id || s.store_name} className="p-3 border border-black/10 bg-neutral-50" data-testid={`lm-top-store-${s.store_id}`}>
                  <div className="text-[10px] uppercase tracking-widest text-neutral-500">{s.bills} BILLS · {s.attach_rate_pct}% ATTACH</div>
                  <div className="font-display text-base truncate mt-1">{s.store_name}</div>
                  <div className="font-mono text-sm mt-1">₹{(s.revenue || 0).toLocaleString()}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Live transactions table */}
        <div className="chart-card p-5" data-accent="burgundy" data-testid="lm-table-card">
          <SectionHeading eyebrow={`${rows.length} RECENT`} title="Bills as they arrive" accent="burgundy" />
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th className="w-2"></th>
                  <th>Bill Date · Time</th>
                  <th>Store</th>
                  <th>Loc Code</th>
                  <th>Bill #</th>
                  <th>Customer</th>
                  <th>Type</th>
                  <th>Mobile</th>
                  <th className="text-right">Bill Amt</th>
                  <th className="text-right">Pts Base</th>
                  <th className="text-right">Tax</th>
                  <th className="text-right">Discount</th>
                  <th className="text-right">Earn</th>
                  <th className="text-right">Redeem</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 ? (
                  <tr><td colSpan={15} className="py-10 text-center text-neutral-500 text-sm">Waiting for live bills…</td></tr>
                ) : rows.map((r) => (
                  <tr key={r.id} onClick={() => setDrillRow(r)} className="cursor-pointer hover:bg-neutral-50"
                       style={{ borderLeft: `4px solid ${r.has_mobile ? PALETTE.emerald : PALETTE.rose}` }}
                       data-testid={`lm-row-${r.id}`}>
                    <td>
                      {r.has_mobile
                        ? <span className="inline-flex items-center" title="Mobile attached"><CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /></span>
                        : <span className="inline-flex items-center" title="LOST OPPORTUNITY — no customer mobile"><AlertTriangle className="w-3.5 h-3.5 text-rose-600" /></span>}
                    </td>
                    <td className="text-[11px] whitespace-nowrap">{fmtDateTime(r.bill_date)}</td>
                    <td className="text-[12px]">
                      <div className="font-medium truncate max-w-[200px]" title={r.store_name}>{r.store_name || "—"}</div>
                      {r.city && <div className="text-[10px] text-neutral-500">{r.city}{r.zone ? ` · ${r.zone}` : ""}</div>}
                    </td>
                    <td className="font-mono text-[11px] text-neutral-700">{r.store_code || "—"}</td>
                    <td className="font-mono text-[11px]">{r.bill_number}</td>
                    <td className="text-[12px]">
                      {r.customer_name ? (
                        <div className="truncate max-w-[160px]">{r.customer_name}</div>
                      ) : r.has_mobile ? (
                        <span className="text-[11px] text-neutral-500 italic">Name unknown</span>
                      ) : (
                        <span className="text-[10px] text-rose-700 font-medium uppercase tracking-widest">LOST OPP.</span>
                      )}
                      {r.tier && <div className="text-[10px] text-neutral-500 uppercase tracking-widest">{r.tier}</div>}
                    </td>
                    <td className="text-[10px] uppercase tracking-widest">
                      {!r.has_mobile
                        ? <span className="pill pill-danger">Walk-in</span>
                        : r.customer_status === "new"
                          ? <span className="pill" style={{ background: "#FDE68A", color: "#92400E", border: "1px solid #FBBF24" }}>New</span>
                          : <span className="pill pill-success">Repeat</span>}
                    </td>
                    <td className="font-mono text-[12px]">
                      {r.customer_mobile ? (
                        <span className="text-emerald-700">{r.customer_mobile}</span>
                      ) : (
                        <span className="text-rose-700">—</span>
                      )}
                    </td>
                    <td className="text-right font-mono tabular-nums" data-testid={`lm-row-amount-${r.bill_number}`}>₹{Math.round((r.bill_with_tax ?? r.net_amount ?? r.final_amount) || 0).toLocaleString()}</td>
                    <td className="text-right font-mono tabular-nums text-emerald-700" data-testid={`lm-row-base-${r.bill_number}`}>₹{Math.round((r.points_base ?? r.amount ?? r.net_amount) || 0).toLocaleString()}</td>
                    <td className="text-right font-mono tabular-nums text-neutral-500">₹{Math.round(r.tax_amount || 0).toLocaleString()}</td>
                    <td className="text-right font-mono tabular-nums text-neutral-500">₹{Math.round(r.discount_amount || 0).toLocaleString()}</td>
                    <td className="text-right font-mono tabular-nums text-amber-700">{r.points_earned || 0}</td>
                    <td className="text-right font-mono tabular-nums text-indigo-700">{r.points_redeemed || 0}</td>
                    <td>
                      <SourcePill source={r.source} />
                      {r.is_return && <span className="pill pill-warning ml-1">RETURN</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {drillRow && <BillDrillModal row={drillRow} onClose={() => setDrillRow(null)} />}
    </div>
  );
}


function KPI({ label, value, icon: Icon, color, testid }) {
  return (
    <div className="kpi-card" style={{ borderLeftColor: color, borderLeftWidth: 3 }} data-testid={testid}>
      <div className="text-[10px] uppercase tracking-[0.2em] text-neutral-500 mb-1 font-medium flex items-center gap-1">
        <Icon className="w-3 h-3" style={{ color }} /> {label}
      </div>
      <div className="kpi-value font-mono text-neutral-900" title={typeof value === 'string' || typeof value === 'number' ? String(value) : undefined}>{value}</div>
    </div>
  );
}

function Select({ label, value, onChange, options, testid, disabled }) {
  return (
    <label className="block">
      <div className="text-neutral-500 uppercase tracking-widest text-[10px] mb-1">{label}</div>
      <select className="k-input k-input-sm" value={value} onChange={(e) => onChange(e.target.value)} data-testid={testid} disabled={disabled} style={{ minWidth: 130, opacity: disabled ? 0.5 : 1 }}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  );
}

function DateInput({ label, value, onChange, testid }) {
  return (
    <label className="block">
      <div className="text-neutral-500 uppercase tracking-widest text-[10px] mb-1">{label}</div>
      <input type="date" className="k-input k-input-sm" value={value} onChange={(e) => onChange(e.target.value)} data-testid={testid} style={{ minWidth: 140 }} />
    </label>
  );
}

function NumInput({ label, value, onChange, testid }) {
  return (
    <label className="block">
      <div className="text-neutral-500 uppercase tracking-widest text-[10px] mb-1">{label}</div>
      <input type="number" className="k-input k-input-sm" value={value} onChange={(e) => onChange(e.target.value)} data-testid={testid} style={{ width: 100 }} placeholder="—" />
    </label>
  );
}

function SourcePill({ source }) {
  if (!source) return <span className="text-neutral-400">—</span>;
  const map = {
    pos_ewards: { bg: "#ECFDF5", color: "#047857", border: "#A7F3D0", label: "POS live" },
    pos_auto: { bg: "#ECFDF5", color: "#047857", border: "#A7F3D0", label: "POS" },
    historic_upload: { bg: "#FAE8FF", color: "#86198F", border: "#F5D0FE", label: "Historical" },
    pos_test_seed: { bg: "#DBEAFE", color: "#1E40AF", border: "#BFDBFE", label: "Test seed" },
  };
  const s = map[source] || { bg: "#F3F4F6", color: "#374151", border: "#E5E7EB", label: source };
  return <span className="pill" style={{ background: s.bg, color: s.color, border: `1px solid ${s.border}` }}>{s.label}</span>;
}

function fmtCurrency(n) {
  if (!n && n !== 0) return "—";
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(1)}Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(1)}L`;
  if (n >= 1e3) return `₹${(n / 1e3).toFixed(1)}K`;
  return `₹${Math.round(n).toLocaleString()}`;
}


function BillDrillModal({ row, onClose }) {
  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white w-full max-w-2xl" onClick={(e) => e.stopPropagation()} data-testid="bill-drill-modal">
        <div className="p-5 border-b border-black/10 flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.22em]" style={{ color: row.has_mobile ? "#047857" : "#B91C1C" }}>
              {row.has_mobile ? "BILL DETAIL" : "LOST OPPORTUNITY"}
            </div>
            <h3 className="font-display text-2xl">{row.bill_number}</h3>
          </div>
          <button onClick={onClose} className="k-btn k-btn-ghost k-btn-sm" data-testid="bill-drill-close"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-5 grid grid-cols-2 gap-3 text-sm">
          <Field label="Date" value={fmtDateTime(row.bill_date)} />
          <Field label="Store" value={row.store_name} />
          <Field label="Customer" value={row.customer_name || (row.has_mobile ? "Name unknown" : "LOST OPP.")} />
          <Field label="Mobile" value={row.customer_mobile || "—"} valueClass={row.has_mobile ? "text-emerald-700" : "text-rose-700 font-medium"} />
          <Field label="Tier" value={row.tier || "—"} />
          <Field label="Current Points" value={row.current_points?.toLocaleString() || "—"} />
          <Field label="Gross" value={`₹${(row.gross_amount || 0).toLocaleString()}`} />
          <Field label="Points base (₹)" value={`₹${((row.points_base ?? row.amount ?? row.net_amount) || 0).toLocaleString()}`} valueClass="text-emerald-700 font-medium" />
          <Field label="Tax (GST)" value={`₹${(row.tax_amount || 0).toLocaleString()}`} />
          <Field label="Bill w/ tax" value={`₹${((row.bill_with_tax ?? row.net_amount) || 0).toLocaleString()}`} />
          <Field label="Discount" value={`₹${(row.discount_amount || 0).toLocaleString()}`} />
          <Field label="Net" value={`₹${(row.net_amount || 0).toLocaleString()}`} />
          <Field label="Final paid" value={`₹${(row.final_amount || row.net_amount || 0).toLocaleString()}`} />
          <Field label="Points Earned" value={(row.points_earned || 0).toLocaleString()} valueClass="text-amber-700 font-medium" />
          <Field label="Points Redeemed" value={(row.points_redeemed || 0).toLocaleString()} valueClass="text-indigo-700 font-medium" />
          <Field label="Items" value={row.items_count} />
          <Field label="Payment" value={row.payment_mode} />
          <Field label="Source" value={row.source} />
          {row.is_return && <Field label="Return" value="YES" valueClass="text-rose-700 font-medium" />}
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, valueClass = "" }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-widest text-neutral-500 mb-0.5">{label}</div>
      <div className={`font-mono text-sm ${valueClass}`}>{value || "—"}</div>
    </div>
  );
}
