/* Command Center — single-pane real-time KPI overview.

   - 6 hero KPIs (Net Sales · AOV · Active Customers · Repeat Rate · NPS · API Health)
   - 8 secondary KPIs (Txns, UPT, Liability, Outstanding Points, Total Customers,
     Open Complaints, Net Sales Δ, Txns Δ)
   - Sparkline of net sales for the selected window
   - Cohort distribution (today / 7d / 30d / 90d / older)
   - Alerts strip (computed live in the backend)
   - AI insight strip (cached 1 hr)
   - Every tile / row drills down via DrillDownModal
*/
import { useEffect, useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid, BarChart, Bar } from "recharts";
import api from "@/lib/api";
import { fmtINR, fmtINRFull, fmtNum, fmtPct, fmtCompactNum } from "@/lib/format";
import { PageHeader, KPICard } from "../_shared";
import { RefreshCw, AlertTriangle, AlertCircle, ChevronRight } from "lucide-react";
import DrillDownModal from "../DrillDownModal";
import AIInsightStrip from "../AIInsightStrip";

const COHORT_COLORS = { today: "#0F172A", last_7d: "#571326", last_30d: "#94A3B8", last_90d: "#C7A76D", older: "#cbd5e1" };

export default function CommandCenter() {
  const navigate = useNavigate();
  const [period, setPeriod] = useState("all");   // Default to All time so historical CSV uploads are visible immediately
  const [storeId, setStoreId] = useState("");
  const [city, setCity] = useState("");
  const [filterOpts, setFilterOpts] = useState({ cities: [], stores: [] });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [drill, setDrill] = useState(null);

  // Load filter options once
  useEffect(() => {
    api.get("/dashboard/filter-options").then((r) => setFilterOpts(r.data)).catch(() => {});
  }, []);

  // Stores filtered by selected city (UX: narrow the store list)
  const visibleStores = useMemo(() => {
    if (!city) return filterOpts.stores;
    return filterOpts.stores.filter((s) => s.city === city);
  }, [filterOpts.stores, city]);

  const load = async () => {
    setLoading(true);
    try {
      const params = { period };
      if (storeId) params.store_id = storeId;
      if (city && !storeId) params.city = city;
      const res = await api.get("/dashboard/command-center", { params });
      setData(res.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [period, storeId, city]);
  useEffect(() => {
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
    // eslint-disable-next-line
  }, [period, storeId, city]);

  const windowStartISO = useMemo(() => {
    if (!data) return null;
    // Mirror backend _date_range
    const now = new Date();
    const d = new Date(now);
    if (period === "today") d.setHours(0, 0, 0, 0);
    else if (period === "7d") d.setDate(d.getDate() - 7);
    else if (period === "30d") d.setDate(d.getDate() - 30);
    else if (period === "90d") d.setDate(d.getDate() - 90);
    else if (period === "1y") d.setDate(d.getDate() - 365);
    else if (period === "all") d.setFullYear(d.getFullYear() - 20);
    else if (period === "mtd") { d.setDate(1); d.setHours(0,0,0,0); }
    else if (period === "ytd") { d.setMonth(0,1); d.setHours(0,0,0,0); }
    else d.setDate(d.getDate() - 30);
    return d.toISOString();
  }, [period, data]);

  // Mongo filter fragments to layer store/city scope into drilldowns
  const scopedStoreIds = useMemo(() => {
    if (storeId) return [storeId];
    if (city) {
      const ids = visibleStores.map((s) => s.id);
      return ids.length ? ids : ["__none__"];
    }
    return null;
  }, [storeId, city, visibleStores]);

  if (loading && !data) return <div className="p-10 text-neutral-500">Loading Command Center…</div>;
  if (!data) return null;

  const k = data.kpis;
  const cohortBars = [
    { label: "Today", value: data.cohort_distribution.today, key: "today" },
    { label: "1–7d", value: data.cohort_distribution.last_7d, key: "last_7d" },
    { label: "8–30d", value: data.cohort_distribution.last_30d, key: "last_30d" },
    { label: "31–90d", value: data.cohort_distribution.last_90d, key: "last_90d" },
    { label: "90d+", value: data.cohort_distribution.older, key: "older" },
  ];

  const txnScope = scopedStoreIds ? { store_id: { $in: scopedStoreIds } } : {};
  const custScope = scopedStoreIds ? { preferred_store_id: { $in: scopedStoreIds } } : {};

  // Drilldown configs
  const openSalesDrill = () => setDrill({
    title: `Transactions · ${period}${city ? " · " + city : ""}${storeId ? " · 1 store" : ""}`,
    subtitle: "DRILLDOWN",
    collection: "transactions",
    filter: { bill_date: { $gte: windowStartISO }, ...txnScope },
    sort: [["bill_date", -1]],
    columns: [
      { key: "bill_number", label: "Bill #", mono: true },
      { key: "bill_date", label: "Date" },
      { key: "customer_mobile", label: "Mobile", mono: true },
      { key: "store_id", label: "Store", mono: true },
      { key: "gross_amount", label: "Gross ₹", align: "right", render: (v) => fmtINR(v) },
      { key: "discount_amount", label: "Discount", align: "right", render: (v) => fmtINR(v) },
      { key: "net_amount", label: "Net ₹", align: "right", render: (v) => fmtINR(v) },
      { key: "payment_mode", label: "Mode" },
    ],
  });

  const openActiveCustomers = () => setDrill({
    title: `Active customers · ${period}${city ? " · " + city : ""}`,
    subtitle: "DRILLDOWN",
    collection: "customers",
    filter: { last_visit_at: { $gte: windowStartISO }, ...custScope },
    sort: [["lifetime_spend", -1]],
    columns: [
      { key: "name", label: "Name" },
      { key: "mobile", label: "Mobile", mono: true },
      { key: "city", label: "City" },
      { key: "tier", label: "Tier" },
      { key: "lifetime_spend", label: "Lifetime ₹", align: "right", render: (v) => fmtINR(v) },
      { key: "visit_count", label: "Visits", align: "right" },
      { key: "last_visit_at", label: "Last visit" },
    ],
    onRowClick: (r) => { setDrill(null); navigate(`/admin/customers/${r.id}`); },
  });

  const openOpenComplaints = () => setDrill({
    title: "Open complaints" + (city ? " · " + city : "") + (storeId ? " · 1 store" : ""),
    subtitle: "DRILLDOWN",
    collection: "support_tickets",
    filter: { status: { $in: ["open", "in_progress", "escalated"] }, ...txnScope },
    sort: [["created_at", -1]],
    columns: [
      { key: "subject", label: "Subject" },
      { key: "customer_mobile", label: "Mobile", mono: true },
      { key: "category", label: "Category" },
      { key: "priority", label: "Priority" },
      { key: "status", label: "Status" },
      { key: "created_at", label: "Opened" },
    ],
    onRowClick: (r) => { setDrill(null); navigate(`/admin/tickets/${r.id}`); },
  });

  const openAPIFailures = () => setDrill({
    title: `API failures · ${period}`,
    subtitle: "DRILLDOWN",
    collection: "api_logs",
    filter: { status_code: { $gte: 400 }, timestamp: { $gte: windowStartISO }, ...txnScope },
    sort: [["timestamp", -1]],
    columns: [
      { key: "timestamp", label: "When" },
      { key: "method", label: "Method" },
      { key: "endpoint", label: "Endpoint", mono: true },
      { key: "status_code", label: "Status", align: "right" },
      { key: "response_time_ms", label: "ms", align: "right" },
      { key: "error_reason", label: "Reason" },
    ],
  });

  // Payload for AI insight — only the numbers + selected scope
  const aiPayload = {
    period,
    scope: {
      city: city || "ALL",
      store: storeId ? (visibleStores.find((s) => s.id === storeId)?.name || storeId) : "ALL",
    },
    net_sales: k.net_sales,
    net_sales_delta_pct: k.net_sales_delta_pct,
    transactions: k.transactions,
    transactions_delta_pct: k.transactions_delta_pct,
    aov: k.aov,
    upt: k.upt,
    active_customers: k.active_customers,
    total_customers: k.total_customers,
    repeat_rate_pct: k.repeat_rate_pct,
    nps_score: k.nps_score,
    api_health_pct: k.api_health_pct,
    outstanding_liability_inr: k.outstanding_liability_inr,
    open_complaints: k.open_complaints,
    cohort_distribution: data.cohort_distribution,
    alerts_count: data.alerts.length,
  };

  return (
    <div data-testid="command-center">
      <PageHeader
        title="Command Center"
        subtitle="LIVE · REAL-TIME COMPUTED"
        actions={
          <>
            <select
              className="k-input !w-auto !py-1.5"
              value={city}
              onChange={(e) => {
                setCity(e.target.value);
                setStoreId(""); // reset store when city changes
              }}
              data-testid="cc-city"
            >
              <option value="">All cities</option>
              {filterOpts.cities.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
            <select
              className="k-input !w-auto !py-1.5"
              value={storeId}
              onChange={(e) => setStoreId(e.target.value)}
              data-testid="cc-store"
            >
              <option value="">All stores{city ? ` in ${city}` : ""}</option>
              {visibleStores.map((s) => (
                <option key={s.id} value={s.id}>{s.code} · {s.name}</option>
              ))}
            </select>
            <select
              className="k-input !w-auto !py-1.5"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              data-testid="cc-period"
            >
              <option value="today">Today</option>
              <option value="7d">Last 7 days</option>
              <option value="30d">Last 30 days</option>
              <option value="90d">Last 90 days</option>
              <option value="mtd">Month to date</option>
              <option value="ytd">Year to date</option>
              <option value="1y">Last 1 year</option>
              <option value="all">All time</option>
            </select>
            <button className="k-btn k-btn-outline k-btn-sm" onClick={load} data-testid="cc-refresh">
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
            </button>
          </>
        }
      />

      <div className="p-8 space-y-6">
        {/* AI insight strip */}
        <AIInsightStrip dashboardKey="command_center" payload={aiPayload} />

        {/* Alerts */}
        {data.alerts.length > 0 && (
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-3" data-testid="cc-alerts">
            {data.alerts.map((a, i) => {
              const isHigh = a.severity === "high";
              return (
                <button
                  key={i}
                  onClick={() => navigate(a.link)}
                  className="text-left p-4 flex items-start gap-3 transition-all relative overflow-hidden hover:shadow-md border"
                  style={{
                    background: isHigh
                      ? "linear-gradient(135deg, #FFF1F2 0%, #fff 100%)"
                      : "linear-gradient(135deg, #FEF6E7 0%, #fff 100%)",
                    borderColor: isHigh ? "rgba(159, 18, 57, 0.3)" : "rgba(180, 83, 9, 0.3)",
                  }}
                  data-testid={`cc-alert-${i}`}
                >
                  <span
                    className="absolute top-0 left-0 bottom-0 w-1"
                    style={{ background: isHigh ? "#9F1239" : "#B45309" }}
                  />
                  {isHigh ? (
                    <AlertTriangle className="w-4 h-4 text-rose-700 mt-0.5 shrink-0" />
                  ) : (
                    <AlertCircle className="w-4 h-4 text-amber-700 mt-0.5 shrink-0" />
                  )}
                  <div className="flex-1 min-w-0 pl-1">
                    <div
                      className="text-[10px] uppercase tracking-[0.22em] font-semibold"
                      style={{ color: isHigh ? "#9F1239" : "#B45309" }}
                    >
                      {isHigh ? "CRITICAL" : "WARNING"}
                    </div>
                    <div className="font-medium text-sm mt-0.5">{a.title}</div>
                    <div className="text-xs text-neutral-600 mt-0.5">{a.detail}</div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-neutral-400" />
                </button>
              );
            })}
          </div>
        )}

        {/* Hero KPIs */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <KPICard
            label="Net Sales"
            value={fmtINR(k.net_sales)}
            fullValue={fmtINRFull(k.net_sales)}
            delta={k.net_sales_delta_pct}
            hint={`vs prev ${period}`}
            onClick={openSalesDrill}
            accent="burgundy"
            testid="cc-kpi-net-sales"
          />
          <KPICard
            label="AOV"
            value={fmtINR(k.aov)}
            fullValue={fmtINRFull(k.aov)}
            hint="₹ per txn"
            onClick={openSalesDrill}
            accent="indigo"
            testid="cc-kpi-aov"
          />
          <KPICard
            label="Active Customers"
            value={fmtCompactNum(k.active_customers)}
            fullValue={fmtNum(k.active_customers)}
            hint={`of ${fmtCompactNum(k.total_customers)}`}
            onClick={openActiveCustomers}
            accent="teal"
            testid="cc-kpi-active"
          />
          <KPICard
            label="Repeat Rate"
            value={fmtPct(k.repeat_rate_pct)}
            hint={`≥2 txns in ${period}`}
            onClick={() => navigate("/admin/dashboards/customers")}
            accent="emerald"
            testid="cc-kpi-repeat-rate"
          />
          <KPICard
            label="NPS Score"
            value={k.nps_score == null ? "N/A" : k.nps_score}
            hint={`${period}`}
            onClick={() => navigate("/admin/dashboards/nps")}
            accent="amber"
            testid="cc-kpi-nps"
          />
          <KPICard
            label="API Health"
            value={fmtPct(k.api_health_pct, 2)}
            onClick={openAPIFailures}
            accent="slate"
            testid="cc-kpi-api"
          />
        </div>

        {/* Secondary KPIs */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          <KPICard
            label="Transactions"
            value={fmtCompactNum(k.transactions)}
            fullValue={fmtNum(k.transactions)}
            delta={k.transactions_delta_pct}
            onClick={openSalesDrill}
            accent="burgundy"
            testid="cc-kpi-txns"
          />
          <KPICard
            label="UPT"
            value={k.upt?.toFixed(2)}
            hint="units per txn"
            onClick={openSalesDrill}
            accent="indigo"
            testid="cc-kpi-upt"
          />
          <KPICard
            label="Outstanding Points"
            value={fmtCompactNum(k.outstanding_points)}
            fullValue={fmtNum(k.outstanding_points)}
            onClick={() => navigate("/admin/dashboards/loyalty")}
            accent="amber"
            testid="cc-kpi-out-points"
          />
          <KPICard
            label="Liability"
            value={fmtINR(k.outstanding_liability_inr)}
            fullValue={fmtINRFull(k.outstanding_liability_inr)}
            hint="@ ₹0.25/pt"
            onClick={() => navigate("/admin/dashboards/loyalty")}
            accent="amber"
            testid="cc-kpi-liability"
          />
          <KPICard
            label="Open Complaints"
            value={fmtNum(k.open_complaints)}
            onClick={openOpenComplaints}
            accent="rose"
            testid="cc-kpi-complaints"
          />
          <KPICard
            label="Total Customers"
            value={fmtCompactNum(k.total_customers)}
            fullValue={fmtNum(k.total_customers)}
            onClick={() => navigate("/admin/customers")}
            accent="teal"
            testid="cc-kpi-total-customers"
          />
        </div>

        {/* Sparkline + Cohorts */}
        <div className="grid lg:grid-cols-3 gap-4">
          <div className="chart-card p-5 lg:col-span-2" data-testid="cc-sparkline">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-3">
                <span className="inline-block w-6 h-px" style={{ background: "#571326" }} />
                <div>
                  <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-0.5">SALES TREND</div>
                  <h3 className="font-display text-xl">Net revenue · {period}</h3>
                </div>
              </div>
              <div className="flex items-center gap-3 text-[10px] uppercase tracking-widest text-neutral-500">
                <span className="flex items-center gap-1"><span className="w-3 h-1" style={{ background: "#571326" }} />Net ₹</span>
                <span className="flex items-center gap-1"><span className="w-3 h-1" style={{ background: "#1E3A8A" }} />Txns</span>
              </div>
            </div>
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={data.sparkline}>
                <defs>
                  <linearGradient id="gradNet" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#571326" stopOpacity={0.45} />
                    <stop offset="100%" stopColor="#571326" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="gradTxns" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#1E3A8A" stopOpacity={0.25} />
                    <stop offset="100%" stopColor="#1E3A8A" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                <XAxis dataKey="date" stroke="#64748b" fontSize={11} tickFormatter={(d) => d?.slice(5)} />
                <YAxis yAxisId="l" stroke="#571326" fontSize={11} tickFormatter={(v) => `₹${(v / 1000).toFixed(0)}K`} />
                <YAxis yAxisId="r" orientation="right" stroke="#1E3A8A" fontSize={11} />
                <Tooltip
                  contentStyle={{ borderRadius: 2, fontSize: 12 }}
                  formatter={(v, key) => (key === "net" ? fmtINR(v) : v)}
                  labelFormatter={(d) => `Date: ${d}`}
                />
                <Area yAxisId="l" type="monotone" dataKey="net" stroke="#571326" strokeWidth={2.5} fill="url(#gradNet)" />
                <Area yAxisId="r" type="monotone" dataKey="txns" stroke="#1E3A8A" strokeWidth={2} fill="url(#gradTxns)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div className="chart-card p-5" data-testid="cc-cohorts">
            <div className="flex items-center gap-3 mb-3">
              <span className="inline-block w-6 h-px" style={{ background: "#1E3A8A" }} />
              <div>
                <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-0.5">ACQUISITION COHORTS</div>
                <h3 className="font-display text-xl">Customers by signup window</h3>
              </div>
            </div>
            <ResponsiveContainer width="100%" height={230}>
              <BarChart data={cohortBars} margin={{ top: 8, right: 0, left: -10, bottom: 0 }}>
                <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                <XAxis dataKey="label" stroke="#64748b" fontSize={11} />
                <YAxis stroke="#64748b" fontSize={11} />
                <Tooltip formatter={(v) => fmtNum(v)} />
                <Bar
                  dataKey="value"
                  radius={[3, 3, 0, 0]}
                  onClick={(d) => {
                    const ranges = {
                      today: { gte: new Date(new Date().setHours(0,0,0,0)).toISOString() },
                      last_7d: { gte: new Date(Date.now() - 7*86400000).toISOString(),
                                 lt: new Date(new Date().setHours(0,0,0,0)).toISOString() },
                      last_30d: { gte: new Date(Date.now() - 30*86400000).toISOString(),
                                  lt: new Date(Date.now() - 7*86400000).toISOString() },
                      last_90d: { gte: new Date(Date.now() - 90*86400000).toISOString(),
                                  lt: new Date(Date.now() - 30*86400000).toISOString() },
                      older: { lt: new Date(Date.now() - 90*86400000).toISOString() },
                    };
                    const r = ranges[d.key];
                    const filt = { created_at: {}, ...custScope };
                    if (r.gte) filt.created_at.$gte = r.gte;
                    if (r.lt) filt.created_at.$lt = r.lt;
                    setDrill({
                      title: `Customers · ${d.label}`,
                      subtitle: "COHORT DRILLDOWN",
                      collection: "customers",
                      filter: filt,
                      sort: [["created_at", -1]],
                      columns: [
                        { key: "name", label: "Name" },
                        { key: "mobile", label: "Mobile", mono: true },
                        { key: "city", label: "City" },
                        { key: "tier", label: "Tier" },
                        { key: "lifetime_spend", label: "Lifetime ₹", align: "right", render: (v) => fmtINR(v) },
                        { key: "created_at", label: "Joined" },
                      ],
                      onRowClick: (r) => { setDrill(null); navigate(`/admin/customers/${r.id}`); },
                    });
                  }}
                  cursor="pointer"
                  fill="#0F172A"
                >
                  {cohortBars.map((b, i) => (
                    <Bar key={i} dataKey="value" fill={COHORT_COLORS[b.key]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <div className="text-[10px] text-neutral-400 mt-2 uppercase tracking-widest">Click a bar to drill down</div>
          </div>
        </div>

        <div className="text-[10px] text-neutral-400 uppercase tracking-widest" data-testid="cc-generated-at">
          Generated at {data.generated_at} · Auto-refresh 30s
        </div>
      </div>

      {drill && (
        <DrillDownModal
          open={true}
          onClose={() => setDrill(null)}
          {...drill}
        />
      )}
    </div>
  );
}
