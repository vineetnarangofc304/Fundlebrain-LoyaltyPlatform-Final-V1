/* RFM & Churn Dashboard — 5×5 heatmap + 11 named segments + churn buckets.
   Live aggregation on every load. */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { PageHeader, KPICard, SectionHeading } from "../_shared";
import { fmtINR, fmtNum, fmtPct } from "@/lib/format";
import AIInsightStrip from "../AIInsightStrip";
import DrillDownModal from "../DrillDownModal";
import { RefreshCw, Users, TrendingDown } from "lucide-react";

// Colour scale for the 5x5 heatmap — burgundy-to-indigo by health
const SEG_COLORS = {
  Champions: "#047857",
  Loyalists: "#0E7C7B",
  "Big Spenders": "#1E3A8A",
  Promising: "#2563EB",
  "New Customers": "#0EA5E9",
  "Potential Loyalists": "#0891B2",
  "Cant Lose Them": "#B45309",
  "At Risk": "#9F1239",
  "About to Sleep": "#A16207",
  Hibernating: "#475569",
  Lost: "#6B7280",
};

export default function RFMDashboard() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeSeg, setActiveSeg] = useState(null);
  const [drill, setDrill] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get("/dashboard/rfm");
      setData(r.data);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  if (loading && !data) return <div className="p-10 text-neutral-500">Computing RFM…</div>;
  if (!data) return null;

  const champions = data.segments.find((s) => s.segment === "Champions");
  const atRisk = data.segments.find((s) => s.segment === "At Risk");
  const lost = data.segments.find((s) => s.segment === "Lost");
  const newCust = data.segments.find((s) => s.segment === "New Customers");

  const maxHeat = Math.max(...data.heatmap.map((h) => h.count), 1);

  const aiPayload = {
    total_customers: data.total_customers,
    segments: data.segments.map((s) => ({ segment: s.segment, count: s.count, pct: s.pct, total_spend: s.total_spend })),
    churn: data.churn_distribution,
    rfm_cutoffs: data.rfm_cutoffs,
  };

  const openSegmentDrill = (seg) => {
    setActiveSeg(seg.segment);
    // Drilldown to customer collection — segment examples already have ids
    // For full drilldown we filter customers by churn_risk + visit_count + lifetime_spend ranges? Simpler: show ALL customers, sorted by lifetime_spend
    // Best UX: open a list pre-filtered to the segment examples set
    if (seg.examples?.length === 0) return;
    setDrill({
      title: `${seg.segment} · ${fmtNum(seg.count)} customers`,
      subtitle: "RFM SEGMENT DRILLDOWN",
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
        { key: "churn_risk", label: "Churn" },
      ],
      onRowClick: (r) => { setDrill(null); navigate(`/admin/customers/${r.id}`); },
    });
  };

  return (
    <div data-testid="rfm-dashboard">
      <PageHeader
        title="RFM & Churn"
        subtitle="11-SEGMENT CUSTOMER INTELLIGENCE · LIVE"
        actions={
          <button className="k-btn k-btn-outline k-btn-sm" onClick={load} data-testid="rfm-refresh">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
          </button>
        }
      />

      <div className="p-8 space-y-6">
        <AIInsightStrip
          dashboardKey="rfm_churn"
          payload={aiPayload}
          title="Segmentation Intelligence"
        />

        {/* Hero KPIs */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          <KPICard
            label="Total Customers"
            value={fmtNum(data.total_customers)}
            accent="slate"
            onClick={() => navigate("/admin/customers")}
            testid="rfm-kpi-total"
          />
          <KPICard
            label="Champions"
            value={fmtNum(champions?.count)}
            hint={fmtPct(champions?.pct)}
            accent="emerald"
            onClick={() => openSegmentDrill(champions)}
            testid="rfm-kpi-champions"
          />
          <KPICard
            label="At Risk"
            value={fmtNum(atRisk?.count)}
            hint={fmtPct(atRisk?.pct)}
            accent="rose"
            onClick={() => openSegmentDrill(atRisk)}
            testid="rfm-kpi-atrisk"
          />
          <KPICard
            label="Lost"
            value={fmtNum(lost?.count)}
            hint={fmtPct(lost?.pct)}
            accent="slate"
            onClick={() => openSegmentDrill(lost)}
            testid="rfm-kpi-lost"
          />
          <KPICard
            label="New Customers"
            value={fmtNum(newCust?.count)}
            hint={fmtPct(newCust?.pct)}
            accent="indigo"
            onClick={() => openSegmentDrill(newCust)}
            testid="rfm-kpi-new"
          />
          <KPICard
            label="High-risk Churn"
            value={fmtNum(data.churn_distribution.high)}
            hint={fmtPct((data.churn_distribution.high / data.total_customers) * 100)}
            accent="rose"
            onClick={() => setDrill({
              title: "High-risk churn customers",
              subtitle: "CHURN DRILLDOWN",
              collection: "customers",
              filter: { churn_risk: "high" },
              sort: [["lifetime_spend", -1]],
              columns: [
                { key: "name", label: "Name" },
                { key: "mobile", label: "Mobile", mono: true },
                { key: "city", label: "City" },
                { key: "tier", label: "Tier" },
                { key: "lifetime_spend", label: "Lifetime ₹", align: "right", render: (v) => fmtINR(v) },
                { key: "last_visit_at", label: "Last visit" },
              ],
              onRowClick: (r) => { setDrill(null); navigate(`/admin/customers/${r.id}`); },
            })}
            testid="rfm-kpi-highrisk"
          />
        </div>

        {/* Heatmap + Legend */}
        <div className="grid lg:grid-cols-[3fr_2fr] gap-4">
          <div className="bg-white border border-black/10 p-5" data-testid="rfm-heatmap">
            <SectionHeading
              eyebrow="5 × 5 MATRIX"
              title="Recency × Frequency · counts"
              accent="burgundy"
              right={<span className="text-[10px] text-neutral-400 uppercase tracking-widest">5 = best</span>}
            />
            <div className="flex">
              {/* Y-axis labels (Recency) */}
              <div className="flex flex-col justify-around pr-2 text-[11px] text-neutral-500 font-mono w-10">
                {[5, 4, 3, 2, 1].map((r) => (
                  <div key={r} className="text-right">R{r}</div>
                ))}
              </div>
              <div className="flex-1">
                <table className="w-full">
                  <tbody>
                    {[5, 4, 3, 2, 1].map((r) => (
                      <tr key={r}>
                        {[1, 2, 3, 4, 5].map((f) => {
                          const cell = data.heatmap.find((h) => h.r === r && h.f === f);
                          if (!cell) return <td key={f} />;
                          const intensity = cell.count / maxHeat;
                          const alpha = 0.15 + intensity * 0.85;
                          // Health-based hue: bottom-left (low R, low F) is risky; top-right is great
                          const baseColor = r >= 4 && f >= 4 ? "4, 120, 87"   // emerald
                            : r >= 3 && f >= 3 ? "30, 58, 138"                 // indigo
                            : r <= 2 && f <= 2 ? "159, 18, 57"                 // rose
                            : "180, 83, 9";                                    // amber
                          return (
                            <td
                              key={f}
                              className="p-0"
                              style={{ width: "20%" }}
                              data-testid={`rfm-cell-${r}-${f}`}
                            >
                              <div
                                className="aspect-square flex items-center justify-center border border-white cursor-pointer hover:ring-2 hover:ring-black/30 transition-all"
                                style={{ background: `rgba(${baseColor}, ${alpha.toFixed(2)})` }}
                                title={`R${r} F${f} → ${cell.count} customers · avg ₹${(cell.avg_spend || 0).toFixed(0)}`}
                              >
                                <div className="text-center">
                                  <div className={`font-mono text-sm ${alpha > 0.55 ? "text-white" : "text-neutral-800"}`}>
                                    {cell.count}
                                  </div>
                                  <div className={`text-[9px] ${alpha > 0.55 ? "text-white/80" : "text-neutral-500"}`}>
                                    {cell.pct.toFixed(1)}%
                                  </div>
                                </div>
                              </div>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {/* X-axis labels (Frequency) */}
                <div className="flex pt-2 text-[11px] text-neutral-500 font-mono">
                  {[1, 2, 3, 4, 5].map((f) => (
                    <div key={f} className="flex-1 text-center">F{f}</div>
                  ))}
                </div>
              </div>
            </div>
            <div className="mt-4 text-[11px] text-neutral-500">
              R = Recency quintile · F = Frequency quintile · cell shows customer count
            </div>
          </div>

          {/* Churn distribution */}
          <div className="bg-white border border-black/10 p-5" data-testid="rfm-churn-buckets">
            <SectionHeading eyebrow="CHURN BUCKETS" title="Health distribution" accent="rose" />
            <div className="space-y-3">
              {[
                { key: "low", label: "Low risk", color: "#047857" },
                { key: "medium", label: "Medium risk", color: "#B45309" },
                { key: "high", label: "High risk", color: "#9F1239" },
              ].map((b) => {
                const count = data.churn_distribution[b.key] || 0;
                const pct = data.total_customers ? (count / data.total_customers) * 100 : 0;
                return (
                  <div key={b.key} data-testid={`rfm-churn-${b.key}`}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="font-medium">{b.label}</span>
                      <span className="font-mono">{fmtNum(count)} · {fmtPct(pct)}</span>
                    </div>
                    <div className="h-2 bg-neutral-100 overflow-hidden">
                      <div
                        className="h-full transition-all"
                        style={{ width: `${pct}%`, background: b.color }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="mt-6 pt-4 border-t border-black/5">
              <div className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-2">QUINTILE CUTOFFS</div>
              <div className="text-xs space-y-1 font-mono text-neutral-700">
                <div>Recency days: {data.rfm_cutoffs.recency_days_q.map((v) => Math.round(v)).join(" · ")}</div>
                <div>Frequency: {data.rfm_cutoffs.frequency_q.map((v) => Math.round(v)).join(" · ")}</div>
                <div>Monetary ₹: {data.rfm_cutoffs.monetary_inr_q.map((v) => Math.round(v)).join(" · ")}</div>
              </div>
            </div>
          </div>
        </div>

        {/* 11 Segments grid */}
        <div className="bg-white border border-black/10 p-5" data-testid="rfm-segments">
          <SectionHeading eyebrow="11 SEGMENTS" title="Named cohorts · click any to drill down" accent="indigo" />
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {data.segments.map((s) => {
              const color = SEG_COLORS[s.segment] || "#571326";
              return (
                <button
                  key={s.segment}
                  onClick={() => openSegmentDrill(s)}
                  disabled={!s.count}
                  className={`text-left border p-4 transition-all relative overflow-hidden ${
                    activeSeg === s.segment ? "ring-2 ring-black/30" : ""
                  } ${s.count ? "hover:shadow-md cursor-pointer" : "opacity-40 cursor-not-allowed"}`}
                  style={{ borderColor: `${color}30`, background: `${color}06` }}
                  data-testid={`rfm-segment-${s.segment.replace(/\s+/g, "-").toLowerCase()}`}
                >
                  <div className="absolute top-0 left-0 bottom-0 w-1" style={{ background: color }} />
                  <div className="pl-2">
                    <div className="text-[10px] uppercase tracking-[0.2em] text-neutral-500 mb-1">{s.segment}</div>
                    <div className="font-mono text-2xl">{fmtNum(s.count)}</div>
                    <div className="text-xs text-neutral-500 mt-0.5">{fmtPct(s.pct)} of base</div>
                    <div className="mt-3 pt-3 border-t border-black/5 grid grid-cols-2 gap-2 text-xs">
                      <div>
                        <div className="text-[10px] text-neutral-400 uppercase">Avg spend</div>
                        <div className="font-mono">{fmtINR(s.avg_spend)}</div>
                      </div>
                      <div>
                        <div className="text-[10px] text-neutral-400 uppercase">Pool ₹</div>
                        <div className="font-mono">{fmtINR(s.total_spend)}</div>
                      </div>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {drill && <DrillDownModal open={true} onClose={() => setDrill(null)} {...drill} />}
    </div>
  );
}
