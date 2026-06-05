/* Cohorts & Segmentation Dashboard — one-timers, repeat bands, ATV, retention.
   Live aggregation. Every segment / row is drillable. */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { PageHeader, KPICard, SectionHeading } from "../_shared";
import { fmtINR, fmtNum, fmtPct } from "@/lib/format";
import AIInsightStrip from "../AIInsightStrip";
import DrillDownModal from "../DrillDownModal";
import { RefreshCw, AlertTriangle, Users, TrendingUp, Download } from "lucide-react";
import { downloadCsv } from "@/lib/csv_export";
import DateRangePicker from "../_date_range_picker";
import {
  ResponsiveContainer, BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip,
  CartesianGrid, Cell, PieChart, Pie, Legend, ComposedChart, Area,
} from "recharts";

const TIER_COLOR = {
  silver: "#94A3B8",
  gold: "#C7A76D",
  platinum: "#1E3A8A",
  diamond: "#571326",
  unknown: "#cbd5e1",
};

export default function CohortsDashboard() {
  const navigate = useNavigate();
  const [range, setRange] = useState({ preset: "0", period_days: 0, start_date: "", end_date: "" });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [drill, setDrill] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const params = { period_days: range.period_days };
      if (range.start_date && range.end_date) {
        params.start_date = range.start_date;
        params.end_date = range.end_date;
      }
      const r = await api.get("/dashboard/cohorts-segmentation", { params });
      setData(r.data);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [range]);

  const exportCsv = () => {
    if (!data) return;
    const sections = [];
    // 1) Frequency segments
    sections.push("=== FREQUENCY SEGMENTS ===");
    sections.push("Segment,Customers,Total Spend,Share %,Avg ATV");
    for (const s of data.frequency_segments || []) {
      sections.push([s.segment, s.count, s.total_spend, s.pct?.toFixed(1), s.avg_atv?.toFixed(0)].join(","));
    }
    // 2) ATV distribution
    sections.push("");
    sections.push("=== AVERAGE TRANSACTION VALUE BANDS ===");
    sections.push("Band,Customers");
    for (const a of data.atv_distribution || []) sections.push([a.band, a.count].join(","));
    // 3) Retention triangle
    sections.push("");
    sections.push("=== RETENTION TRIANGLE ===");
    sections.push("Cohort,New customers," + (data.retention_triangle?.months || []).map(m => `M+${m}`).join(","));
    for (const r of data.retention_triangle?.rows || []) {
      sections.push([r.cohort, r.new_customers, ...(r.retained || []).map(v => `${(v.pct || 0).toFixed(1)}%`)].join(","));
    }
    const blob = new Blob([sections.join("\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `cohorts-segmentation-${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  if (loading && !data) return <div className="p-10 text-neutral-500">Computing cohorts & segments…</div>;
  if (!data) return null;

  const oneTimer = data.one_timer;
  const transactedPct = data.total_customers ? (data.transacted_customers / data.total_customers) * 100 : 0;

  const aiPayload = {
    total_customers: data.total_customers,
    transacted: data.transacted_customers,
    untransacted: data.untransacted_customers,
    one_timer: oneTimer,
    frequency: data.frequency_segments.map((f) => ({ label: f.label, count: f.count, atv: f.atv, avg_lifetime_spend: f.avg_lifetime_spend, total_spend: f.total_spend })),
    spend_segments: data.spend_segments.map((s) => ({ label: s.label, count: s.count, atv: s.atv })),
    tier_segments: data.tier_segments.map((t) => ({ tier: t.tier, count: t.count, total_spend: t.total_spend })),
    avg_retention_m1_to_m6: avgRetention(data.retention_triangle.rows, 1, 6),
  };

  const openSegmentDrill = (seg, label) => {
    if (!seg.examples?.length) return;
    setDrill({
      title: `${label} · ${fmtNum(seg.count)} customers`,
      subtitle: "SEGMENT DRILLDOWN",
      collection: "customers",
      filter: { id: { $in: seg.examples.map((e) => e.id) } },
      sort: [["lifetime_spend", -1]],
      columns: [
        { key: "name", label: "Name" },
        { key: "mobile", label: "Mobile", mono: true },
        { key: "city", label: "City" },
        { key: "tier", label: "Tier" },
        { key: "visit_count", label: "Visits", align: "right" },
        { key: "lifetime_spend", label: "Lifetime ₹", align: "right", render: (v) => fmtINR(v) },
        { key: "last_visit_at", label: "Last visit" },
      ],
      onRowClick: (r) => { setDrill(null); navigate(`/admin/customers/${r.id}`); },
    });
  };

  return (
    <div data-testid="cohorts-dashboard">
      <PageHeader
        title="Cohorts & Segmentation"
        subtitle="ONE-TIMERS · REPEAT BANDS · ATV · RETENTION · LIVE"
        actions={
          <>
            <DateRangePicker value={range} onChange={setRange} testid="cohorts-date-range" />
            <button className="k-btn k-btn-outline k-btn-sm" onClick={exportCsv} data-testid="cohorts-export-csv">
              <Download className="w-3.5 h-3.5" /> Export CSV
            </button>
            <button className="k-btn k-btn-outline k-btn-sm" onClick={load} data-testid="cohorts-refresh">
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
            </button>
          </>
        }
      />

      <div className="p-8 space-y-6">
        <AIInsightStrip
          dashboardKey="cohorts_segmentation"
          payload={aiPayload}
          title="Cohort & Segment Intelligence"
        />

        {/* Hero KPIs */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KPICard label="Total Customers" value={fmtNum(data.total_customers)} accent="slate" testid="co-kpi-total" />
          <KPICard label="Transacted" value={fmtNum(data.transacted_customers)} hint={fmtPct(transactedPct)} accent="emerald" testid="co-kpi-transacted" />
          <KPICard label="Untransacted" value={fmtNum(data.untransacted_customers)} hint="signed up · 0 bills" accent="amber" testid="co-kpi-untransacted" />
          <KPICard
            label="One-Timers"
            value={fmtNum(oneTimer.count)}
            hint={`${fmtPct(oneTimer.pct_of_transacted)} of transacted`}
            accent="rose"
            onClick={() => openSegmentDrill(data.frequency_segments[0], "One-Timers")}
            testid="co-kpi-onetimer"
          />
        </div>

        {/* One-timer focus panel */}
        <div className="bg-gradient-to-br from-[#9F1239]/5 to-white border border-[#9F1239]/20 p-6 grid lg:grid-cols-3 gap-6" data-testid="co-onetimer-panel">
          <div className="lg:col-span-1">
            <div className="flex items-center gap-2 mb-1">
              <AlertTriangle className="w-4 h-4 text-rose-700" />
              <div className="text-[10px] uppercase tracking-[0.22em] text-rose-700 font-semibold">
                ONE-TIMER REVENUE AT RISK
              </div>
            </div>
            <div className="font-display text-4xl tracking-tight text-rose-900">{fmtINR(oneTimer.total_spend)}</div>
            <div className="text-xs text-neutral-600 mt-1">
              from {oneTimer.count} customers who bought once · avg first basket {fmtINR(oneTimer.avg_first_basket)}
            </div>
            <div className="mt-4 p-3 bg-white border border-emerald-200">
              <div className="text-[10px] uppercase tracking-[0.2em] text-emerald-700 font-semibold">EST RECOVERY POOL</div>
              <div className="font-display text-2xl text-emerald-800 mt-1">{fmtINR(oneTimer.estimated_recovery_pool_inr)}</div>
              <div className="text-[11px] text-neutral-500 mt-1">Industry: ~15% of one-timers can be reactivated with the right play</div>
            </div>
          </div>

          <div className="lg:col-span-2">
            <SectionHeading eyebrow="WHEN DID THEY LAST VISIT?" title="One-timer recency distribution" accent="rose" />
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
              {Object.entries(oneTimer.recency_distribution).map(([bucket, count], i) => {
                const colors = ["#047857", "#B45309", "#9F1239", "#3B0D1B"];
                const pct = oneTimer.count ? (count / oneTimer.count) * 100 : 0;
                return (
                  <div key={bucket} className="border p-3" style={{ borderColor: `${colors[i]}30`, background: `${colors[i]}08` }} data-testid={`co-onetimer-${bucket}`}>
                    <div className="text-[10px] uppercase tracking-[0.2em] text-neutral-500">{bucket}</div>
                    <div className="font-mono text-3xl mt-1" style={{ color: colors[i] }}>{count}</div>
                    <div className="text-xs text-neutral-500 mt-0.5">{fmtPct(pct)} of one-timers</div>
                    <div className="h-1 mt-2" style={{ background: colors[i], width: `${pct}%` }} />
                  </div>
                );
              })}
            </div>
            <div className="mt-4 text-xs text-neutral-600">
              <strong>Reactivation playbook:</strong> Target the 0-30d bucket with a "complete your wardrobe" 15% offer in 48 hrs · 31-90d with a personalised stylist look · 91-180d with a clean second-basket bundle · 180d+ low-cost SMS sweep.
            </div>
          </div>
        </div>

        {/* Repeat customer block — the counterpart to one-timer (docx item #21) */}
        {data.repeat && (
          <div className="bg-gradient-to-br from-emerald-50 to-white border border-emerald-200 p-6 grid lg:grid-cols-3 gap-6" data-testid="co-repeat-panel">
            <div>
              <div className="text-[10px] uppercase tracking-[0.3em] text-emerald-700 font-medium mb-2 flex items-center gap-2">
                <TrendingUp className="w-3 h-3" />
                REPEAT CUSTOMER BLOCK
              </div>
              <div className="font-display text-4xl tracking-tight text-emerald-900">{fmtNum(data.repeat.count)}</div>
              <div className="text-sm text-neutral-600 mt-2">
                <span className="font-mono">{fmtPct(data.repeat.pct_of_transacted)}</span> of transacted · contributing <span className="font-mono">{fmtINR(data.repeat.total_spend)}</span> in lifetime spend
              </div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-[0.3em] text-neutral-500 mb-2">AVG SPEND / REPEAT CUSTOMER</div>
              <div className="font-display text-2xl text-neutral-900">{fmtINR(data.repeat.avg_spend_per_customer)}</div>
              <div className="text-xs text-neutral-500 mt-2">
                Versus one-timer avg first basket of <span className="font-mono">{fmtINR(oneTimer.avg_first_basket)}</span> — the second-purchase nudge unlocks <span className="font-mono">{oneTimer.avg_first_basket ? `${((data.repeat.avg_spend_per_customer / oneTimer.avg_first_basket) - 1).toFixed(1)}x` : "—"}</span> ARPU
              </div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-[0.3em] text-neutral-500 mb-2">FREQUENCY BREAKDOWN</div>
              <div className="space-y-1.5">
                {(data.repeat.frequency_breakdown || []).map((b) => (
                  <div key={b.band} className="flex justify-between items-center text-sm" data-testid={`co-repeat-band-${b.band.replace(/\s/g,"")}`}>
                    <span className="text-neutral-700">{b.band}</span>
                    <span className="font-mono">{fmtNum(b.count)} · {fmtINR(b.total_spend)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Frequency segmentation */}
        <div className="grid lg:grid-cols-[3fr_2fr] gap-4">
          <div className="chart-card p-5" data-testid="co-frequency-bars">
            <SectionHeading eyebrow="REPEAT FREQUENCY" title="Customers by visit band" accent="indigo" />
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={data.frequency_segments} margin={{ top: 12 }}>
                <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                <XAxis dataKey="label" stroke="#64748b" fontSize={11} />
                <YAxis yAxisId="l" stroke="#64748b" fontSize={11} />
                <YAxis yAxisId="r" orientation="right" stroke="#B45309" fontSize={11} tickFormatter={(v) => `₹${(v / 1000).toFixed(0)}K`} />
                <Tooltip formatter={(v, name) => name === "atv" ? fmtINR(v) : fmtNum(v)} />
                <Bar yAxisId="l" dataKey="count" name="Customers" radius={[3, 3, 0, 0]}>
                  {data.frequency_segments.map((s, i) => <Cell key={i} fill={s.color} />)}
                </Bar>
                <Line yAxisId="r" type="monotone" dataKey="atv" stroke="#B45309" strokeWidth={2.5} dot={{ fill: "#B45309", r: 4 }} name="ATV" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white border border-black/10 p-5">
            <SectionHeading eyebrow="BAND DETAIL" title="Frequency table" accent="indigo" />
            <table className="data-table">
              <thead><tr><th>Band</th><th className="text-right">Count</th><th className="text-right">ATV</th><th className="text-right">Avg LTS</th></tr></thead>
              <tbody>
                {data.frequency_segments.map((s) => (
                  <tr
                    key={s.key}
                    onClick={() => openSegmentDrill(s, s.label)}
                    className={s.count ? "cursor-pointer hover:bg-neutral-50" : "opacity-50"}
                    data-testid={`co-freq-row-${s.key}`}
                  >
                    <td>
                      <span className="inline-block w-2 h-2 rounded-full mr-2 align-middle" style={{ background: s.color }} />
                      <span className="font-medium">{s.label}</span>
                    </td>
                    <td className="text-right font-mono">{fmtNum(s.count)}</td>
                    <td className="text-right font-mono">{fmtINR(s.atv)}</td>
                    <td className="text-right font-mono text-xs">{fmtINR(s.avg_lifetime_spend)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Spend bands + Tier */}
        <div className="grid lg:grid-cols-[3fr_2fr] gap-4">
          <div className="chart-card p-5" data-testid="co-spend-bars">
            <SectionHeading eyebrow="LIFETIME SPEND" title="Customers by spend band" accent="burgundy" />
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={data.spend_segments} margin={{ top: 12 }}>
                <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
                <XAxis dataKey="label" stroke="#64748b" fontSize={11} />
                <YAxis yAxisId="l" stroke="#64748b" fontSize={11} />
                <YAxis yAxisId="r" orientation="right" stroke="#0E7C7B" fontSize={11} tickFormatter={(v) => `₹${(v / 1000).toFixed(0)}K`} />
                <Tooltip formatter={(v, name) => name === "atv" ? fmtINR(v) : fmtNum(v)} />
                <Bar yAxisId="l" dataKey="count" name="Customers" radius={[3, 3, 0, 0]}>
                  {data.spend_segments.map((s, i) => <Cell key={i} fill={s.color} />)}
                </Bar>
                <Line yAxisId="r" type="monotone" dataKey="atv" stroke="#0E7C7B" strokeWidth={2.5} dot={{ fill: "#0E7C7B", r: 4 }} name="ATV" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white border border-black/10 p-5" data-testid="co-tier-donut">
            <SectionHeading eyebrow="LOYALTY TIER" title="Programme split" accent="amber" />
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie
                  data={data.tier_segments}
                  dataKey="count"
                  nameKey="tier"
                  cx="50%" cy="50%"
                  innerRadius={55} outerRadius={90}
                  paddingAngle={2}
                  label={(e) => `${e.tier} ${fmtPct(e.pct_of_base)}`}
                  labelLine={false}
                >
                  {data.tier_segments.map((t, i) => (
                    <Cell key={i} fill={TIER_COLOR[t.tier] || "#cbd5e1"} />
                  ))}
                </Pie>
                <Tooltip formatter={(v, n, ctx) => [`${fmtNum(v)} customers · ${fmtINR(ctx.payload.total_spend)} total spend`, ctx.payload.tier]} />
              </PieChart>
            </ResponsiveContainer>
            <table className="data-table mt-2">
              <thead><tr><th>Tier</th><th className="text-right">Count</th><th className="text-right">ATV</th></tr></thead>
              <tbody>
                {data.tier_segments.map((t) => (
                  <tr key={t.tier}>
                    <td>
                      <span className="inline-block w-2 h-2 rounded-full mr-2 align-middle" style={{ background: TIER_COLOR[t.tier] }} />
                      {t.tier}
                    </td>
                    <td className="text-right font-mono">{fmtNum(t.count)}</td>
                    <td className="text-right font-mono text-xs">{fmtINR(t.atv)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Retention triangle */}
        <RetentionTriangle triangle={data.retention_triangle} />

        {/* Acquisition trend */}
        <div className="chart-card p-5" data-testid="co-acquisition">
          <SectionHeading eyebrow="ACQUISITION" title="New customers per month · last 18m" accent="teal" />
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={data.acquisition_trend}>
              <defs>
                <linearGradient id="acqGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#0E7C7B" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="#0E7C7B" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#f1f5f9" strokeDasharray="3 3" />
              <XAxis dataKey="month" stroke="#64748b" fontSize={11} />
              <YAxis stroke="#64748b" fontSize={11} />
              <Tooltip />
              <Area type="monotone" dataKey="new_customers" stroke="#0E7C7B" strokeWidth={2.5} fill="url(#acqGrad)" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>

      {drill && <DrillDownModal open={true} onClose={() => setDrill(null)} {...drill} />}
    </div>
  );
}

function avgRetention(rows, fromOffset, toOffset) {
  let sum = 0;
  let n = 0;
  rows.forEach((r) => {
    r.offsets.forEach((o) => {
      if (o.offset >= fromOffset && o.offset <= toOffset) {
        sum += o.pct;
        n += 1;
      }
    });
  });
  return n ? Math.round(sum / n) : 0;
}

function RetentionTriangle({ triangle }) {
  const { rows, max_offset } = triangle;
  if (!rows.length) return null;
  // Color helper: green at 80%+, blue at 40-60, amber at 20-40, rose <20
  const colorFor = (pct) => {
    if (pct >= 80) return "rgba(4, 120, 87,";
    if (pct >= 50) return "rgba(14, 124, 123,";
    if (pct >= 30) return "rgba(30, 58, 138,";
    if (pct >= 15) return "rgba(180, 83, 9,";
    return "rgba(159, 18, 57,";
  };
  return (
    <div className="bg-white border border-black/10 p-5" data-testid="co-retention-triangle">
      <SectionHeading
        eyebrow="COHORT RETENTION"
        title="% returning by months since first purchase"
        accent="indigo"
        right={<span className="text-[10px] text-neutral-400 uppercase tracking-widest">M0 = signup month</span>}
      />
      <div className="overflow-x-auto">
        <table className="text-center text-[11px] w-full">
          <thead>
            <tr>
              <th className="text-left text-neutral-500 font-normal p-1 pl-0 sticky left-0 bg-white">COHORT</th>
              <th className="text-right text-neutral-500 font-normal px-2">SIZE</th>
              {Array.from({ length: max_offset + 1 }).map((_, o) => (
                <th key={o} className="font-mono text-neutral-400 font-normal px-1">M{o}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.cohort_month}>
                <td className="text-left p-1 pl-0 font-medium text-xs sticky left-0 bg-white">{r.cohort_month}</td>
                <td className="text-right font-mono text-xs px-2 text-neutral-500">{fmtNum(r.cohort_size)}</td>
                {r.offsets.map((o) => {
                  const baseColor = colorFor(o.pct);
                  const alpha = 0.15 + (o.pct / 100) * 0.7;
                  return (
                    <td key={o.offset} className="p-0">
                      <div
                        className="aspect-square flex items-center justify-center border border-white text-[10px]"
                        style={{
                          background: `${baseColor} ${alpha.toFixed(2)})`,
                          color: alpha > 0.55 ? "#fff" : "#0f172a",
                        }}
                        title={`Cohort ${r.cohort_month} · M${o.offset}: ${o.retained} of ${r.cohort_size} (${o.pct}%)`}
                      >
                        {o.pct > 0 ? `${o.pct}%` : "·"}
                      </div>
                    </td>
                  );
                })}
                {/* Pad missing offsets */}
                {Array.from({ length: max_offset + 1 - r.offsets.length }).map((_, i) => (
                  <td key={`pad-${i}`} className="p-0">
                    <div className="aspect-square bg-neutral-50" />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center gap-4 mt-3 text-[10px] uppercase tracking-widest text-neutral-500">
        <span>RETENTION:</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3" style={{ background: "rgba(159, 18, 57, 0.7)" }} /> &lt;15%</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3" style={{ background: "rgba(180, 83, 9, 0.7)" }} /> 15-30%</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3" style={{ background: "rgba(30, 58, 138, 0.7)" }} /> 30-50%</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3" style={{ background: "rgba(14, 124, 123, 0.7)" }} /> 50-80%</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3" style={{ background: "rgba(4, 120, 87, 0.85)" }} /> 80%+</span>
      </div>
    </div>
  );
}
