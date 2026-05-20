/* Store Performance v2 — Leaderboard / By City / Day Analysis tabs.
   Live-computed, drilldown-enabled. */
import { useEffect, useState, useMemo } from "react";
import api from "@/lib/api";
import { PageHeader, KPICard, SectionHeading, CHART_PALETTE } from "../_shared";
import { fmtINR, fmtNum, fmtPct } from "@/lib/format";
import AIInsightStrip from "../AIInsightStrip";
import DrillDownModal from "../DrillDownModal";
import { RefreshCw, Trophy, Map, CalendarDays } from "lucide-react";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid,
  Cell,
} from "recharts";

const TABS = [
  { id: "leaderboard", label: "Leaderboard", icon: Trophy },
  { id: "by_city", label: "By City", icon: Map },
  { id: "by_day", label: "Day Analysis", icon: CalendarDays },
];

export default function StoreDashboard() {
  const [period, setPeriod] = useState(0);   // 0 = All time (default)
  const [tab, setTab] = useState("leaderboard");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [drill, setDrill] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get("/dashboard/store-performance-v2", { params: { period_days: period } });
      setData(r.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [period]);

  const windowStartISO = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() - period);
    return d.toISOString();
  }, [period]);

  if (loading && !data) return <div className="p-10 text-neutral-500">Loading store performance…</div>;
  if (!data) return null;

  const top = data.leaderboard[0];
  const totalNet = data.leaderboard.reduce((s, r) => s + r.net, 0);
  const totalTxns = data.leaderboard.reduce((s, r) => s + r.txns, 0);
  const avgAOV = totalTxns ? totalNet / totalTxns : 0;

  const aiPayload = {
    period_days: period,
    total_stores: data.leaderboard.length,
    total_cities: data.by_city.length,
    total_net_sales: Math.round(totalNet),
    top_store: top ? { name: top.store_name, net: top.net, city: top.city, delta_pct: top.delta_pct } : null,
    bottom_store: data.leaderboard[data.leaderboard.length - 1],
    top_3_cities: data.by_city.slice(0, 3).map((c) => ({ city: c.city, net: c.net, stores: c.stores })),
    best_day: data.by_day.length ? data.by_day.reduce((a, b) => (a.net > b.net ? a : b)) : null,
    worst_day: data.by_day.length ? data.by_day.reduce((a, b) => (a.net < b.net ? a : b)) : null,
  };

  const openStoreTxns = (s) => setDrill({
    title: `${s.store_name} · ${period}d transactions`,
    subtitle: "DRILLDOWN",
    collection: "transactions",
    filter: { store_id: s.store_id, bill_date: { $gte: windowStartISO } },
    sort: [["bill_date", -1]],
    columns: [
      { key: "bill_number", label: "Bill #", mono: true },
      { key: "bill_date", label: "Date" },
      { key: "customer_mobile", label: "Mobile", mono: true },
      { key: "gross_amount", label: "Gross ₹", align: "right", render: (v) => fmtINR(v) },
      { key: "discount_amount", label: "Disc", align: "right", render: (v) => fmtINR(v) },
      { key: "net_amount", label: "Net ₹", align: "right", render: (v) => fmtINR(v) },
      { key: "payment_mode", label: "Mode" },
    ],
  });

  return (
    <div data-testid="store-performance-v2">
      <PageHeader
        title="Store Performance"
        subtitle="RETAIL FOOTPRINT INTELLIGENCE · LIVE"
        actions={
          <>
            <select className="k-input !w-auto !py-1.5" value={period} onChange={(e) => setPeriod(parseInt(e.target.value))} data-testid="sp-period">
              <option value={0}>All time</option>
              <option value={7}>Last 7 days</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
              <option value={180}>Last 180 days</option>
            </select>
            <button className="k-btn k-btn-outline k-btn-sm" onClick={load} data-testid="sp-refresh">
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
            </button>
          </>
        }
      />

      <div className="p-8 space-y-6">
        <AIInsightStrip
          dashboardKey={`store_performance_${period}d`}
          payload={aiPayload}
          title="Retail Network Intelligence"
        />

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KPICard label="Stores reporting" value={fmtNum(data.leaderboard.length)} accent="slate" testid="sp-kpi-stores" />
          <KPICard label="Cities covered" value={fmtNum(data.by_city.length)} accent="teal" testid="sp-kpi-cities" />
          <KPICard label="Total Net Sales" value={fmtINR(totalNet)} accent="burgundy" testid="sp-kpi-net" />
          <KPICard label="Network AOV" value={fmtINR(avgAOV)} accent="indigo" testid="sp-kpi-aov" />
        </div>

        {/* Tabs */}
        <div className="k-tabs" data-testid="sp-tabs">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={tab === t.id ? "active" : ""}
              data-testid={`sp-tab-${t.id}`}
            >
              <span className="inline-flex items-center gap-2">
                <t.icon className="w-3.5 h-3.5" /> {t.label}
              </span>
            </button>
          ))}
        </div>

        {tab === "leaderboard" && <Leaderboard rows={data.leaderboard} onOpen={openStoreTxns} />}
        {tab === "by_city" && <ByCity rows={data.by_city} />}
        {tab === "by_day" && <ByDay rows={data.by_day} heatmap={data.heatmap} />}
      </div>

      {drill && <DrillDownModal open={true} onClose={() => setDrill(null)} {...drill} />}
    </div>
  );
}

/* ---------- Leaderboard ---------- */
function Leaderboard({ rows, onOpen }) {
  return (
    <div className="bg-white border border-black/10 p-5" data-testid="sp-leaderboard">
      <SectionHeading eyebrow="RANKED" title="Top performing stores" accent="burgundy" />
      <div className="overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th>Rank</th><th>Store</th><th>City</th><th>Region</th>
              <th className="text-right">Net ₹</th>
              <th className="text-right">vs prev</th>
              <th className="text-right">Txns</th>
              <th className="text-right">Unique Customers</th>
              <th className="text-right">AOV</th>
              <th className="text-right">UPT</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.store_id} className="hover:bg-neutral-50 cursor-pointer" onClick={() => onOpen(s)} data-testid={`sp-row-${s.store_id}`}>
                <td>
                  <span
                    className="inline-flex items-center justify-center w-7 h-7 font-mono text-xs"
                    style={{
                      background: s.rank <= 3 ? "#C7A76D" : "#f1f5f9",
                      color: s.rank <= 3 ? "#fff" : "#334155",
                    }}
                  >
                    {s.rank}
                  </span>
                </td>
                <td className="font-medium">{s.store_name}<div className="text-[10px] text-neutral-400 font-mono">{s.code}</div></td>
                <td>{s.city}</td>
                <td>{s.region}</td>
                <td className="text-right font-mono font-semibold">{fmtINR(s.net)}</td>
                <td className="text-right font-mono text-xs">
                  {s.delta_pct == null ? (
                    <span className="text-neutral-400">NEW</span>
                  ) : (
                    <span className={s.delta_pct >= 0 ? "text-emerald-700" : "text-rose-700"}>
                      {s.delta_pct >= 0 ? "▲" : "▼"} {Math.abs(s.delta_pct).toFixed(1)}%
                    </span>
                  )}
                </td>
                <td className="text-right font-mono">{fmtNum(s.txns)}</td>
                <td className="text-right font-mono">{fmtNum(s.unique_customers)}</td>
                <td className="text-right font-mono">{fmtINR(s.aov)}</td>
                <td className="text-right font-mono">{s.upt}</td>
                <td className="text-xs text-neutral-400 text-right">→</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ---------- By City ---------- */
function ByCity({ rows }) {
  const COLORS = ["#1E3A8A", "#571326", "#0E7C7B", "#B45309", "#9F1239", "#334155", "#C7A76D", "#047857"];
  return (
    <div className="grid lg:grid-cols-[3fr_2fr] gap-4" data-testid="sp-by-city">
      <div className="chart-card p-5">
        <SectionHeading eyebrow="CITY MIX" title="Net sales by city" accent="indigo" />
        <ResponsiveContainer width="100%" height={420}>
          <BarChart data={rows} layout="vertical" margin={{ left: 40 }}>
            <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
            <XAxis type="number" stroke="#64748b" fontSize={11} tickFormatter={(v) => `₹${(v / 100000).toFixed(1)}L`} />
            <YAxis dataKey="city" type="category" stroke="#64748b" fontSize={11} width={100} />
            <Tooltip formatter={(v) => fmtINR(v)} />
            <Bar dataKey="net" radius={[0, 2, 2, 0]}>
              {rows.map((_, i) => (
                <Cell key={i} fill={COLORS[i % COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="bg-white border border-black/10 p-5">
        <SectionHeading eyebrow="DETAIL" title="City scorecard" accent="teal" />
        <table className="data-table">
          <thead><tr><th>City</th><th className="text-right">Stores</th><th className="text-right">Txns</th><th className="text-right">Customers</th><th className="text-right">AOV</th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.city}>
                <td>
                  <span className="inline-block w-2 h-2 rounded-full mr-2 align-middle" style={{ background: COLORS[i % COLORS.length] }} />
                  {r.city}
                </td>
                <td className="text-right font-mono">{r.stores}</td>
                <td className="text-right font-mono">{fmtNum(r.txns)}</td>
                <td className="text-right font-mono">{fmtNum(r.unique_customers)}</td>
                <td className="text-right font-mono">{fmtINR(r.aov)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ---------- By Day ---------- */
function ByDay({ rows, heatmap }) {
  const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const maxNet = Math.max(...heatmap.map((h) => h.net), 1);

  const cellColor = (net) => {
    if (net === 0) return "#f8fafc";
    const intensity = Math.min(1, net / maxNet);
    // Indigo scale
    const alpha = 0.15 + intensity * 0.85;
    return `rgba(30, 58, 138, ${alpha.toFixed(2)})`;
  };

  return (
    <div className="space-y-4" data-testid="sp-by-day">
      <div className="chart-card p-5">
        <SectionHeading eyebrow="WEEKDAY" title="Sales by day of week" accent="indigo" />
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={rows}>
            <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
            <XAxis dataKey="day" stroke="#64748b" fontSize={11} />
            <YAxis stroke="#64748b" fontSize={11} tickFormatter={(v) => `₹${(v / 1000).toFixed(0)}K`} />
            <Tooltip formatter={(v, name) => name === "net" ? fmtINR(v) : v} />
            <Bar dataKey="net" radius={[2, 2, 0, 0]}>
              {rows.map((r, i) => {
                const max = Math.max(...rows.map((x) => x.net));
                const alpha = 0.4 + 0.6 * (r.net / max);
                return <Cell key={i} fill={`rgba(30, 58, 138, ${alpha.toFixed(2)})`} />;
              })}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="bg-white border border-black/10 p-5">
        <SectionHeading eyebrow="HOUR × DAY" title="Traffic heatmap" accent="burgundy" right={
          <span className="text-[10px] text-neutral-400 uppercase tracking-widest">darker = more revenue</span>
        } />
        <div className="overflow-x-auto" data-testid="sp-heatmap">
          <table className="text-center text-[10px]">
            <thead>
              <tr>
                <th className="w-12 text-neutral-400 font-normal">Day</th>
                {Array.from({ length: 24 }).map((_, h) => (
                  <th key={h} className="px-1 font-mono text-neutral-400 font-normal">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {DAYS.map((day) => (
                <tr key={day}>
                  <td className="text-[11px] text-neutral-600 pr-2 font-medium">{day}</td>
                  {Array.from({ length: 24 }).map((_, h) => {
                    const cell = heatmap.find((c) => c.day === day && c.hour === h) || { net: 0, txns: 0 };
                    return (
                      <td
                        key={h}
                        title={`${day} ${h}:00 → ${fmtINR(cell.net)} · ${cell.txns} txns`}
                        className="h-7 w-7 border border-white"
                        style={{ background: cellColor(cell.net) }}
                      />
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
