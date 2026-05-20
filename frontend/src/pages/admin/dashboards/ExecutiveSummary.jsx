/* Executive Summary v2 — composite snapshot + branded PDF download. */
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader, KPICard, SectionHeading } from "../_shared";
import { fmtINR, fmtNum } from "@/lib/format";
import AIInsightStrip from "../AIInsightStrip";
import { Download, RefreshCw } from "lucide-react";

export default function ExecutiveSummary() {
  const [period, setPeriod] = useState(0);   // 0 = All time (default)
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get("/dashboard/executive-summary", { params: { period_days: period } });
      setData(r.data);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [period]);

  const downloadPDF = async () => {
    setDownloading(true);
    try {
      const res = await api.get("/dashboard/executive-summary/pdf", {
        params: { period_days: period },
        responseType: "blob",
      });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `KAZO_Executive_Summary_${period}d.pdf`;
      a.click();
      window.URL.revokeObjectURL(url);
    } finally {
      setDownloading(false);
    }
  };

  if (loading && !data) return <div className="p-10 text-neutral-500">Generating executive summary…</div>;
  if (!data) return null;

  const k = data.kpis;
  const aiPayload = { ...k, period_days: period,
    top_stores: data.top_stores, top_cities: data.top_cities };

  return (
    <div data-testid="exec-summary">
      <PageHeader
        title="Executive Summary"
        subtitle="BOARDROOM SNAPSHOT · LIVE"
        actions={
          <>
            <select className="k-input !w-auto !py-1.5" value={period} onChange={(e) => setPeriod(parseInt(e.target.value))} data-testid="es-period">
              <option value={0}>All time</option>
              <option value={7}>Last 7 days</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
              <option value={365}>Last 365 days</option>
            </select>
            <button className="k-btn k-btn-outline k-btn-sm" onClick={load}><RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh</button>
            <button className="k-btn kazo-bg-burgundy k-btn-sm" onClick={downloadPDF} disabled={downloading} data-testid="es-pdf">
              <Download className="w-3.5 h-3.5" /> {downloading ? "Generating…" : "Download PDF"}
            </button>
          </>
        }
      />

      <div className="p-8 space-y-6">
        <AIInsightStrip dashboardKey={`exec_summary_${period}d`} payload={aiPayload} title="Executive Intelligence Brief" />

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KPICard label="Net Sales" value={fmtINR(k.net_sales)} delta={k.net_sales_delta_pct} hint={`vs prev ${period}d`} accent="burgundy" testid="es-kpi-net-sales" />
          <KPICard label="Transactions" value={fmtNum(k.transactions)} accent="indigo" testid="es-kpi-txns" />
          <KPICard label="AOV" value={fmtINR(k.aov)} accent="teal" testid="es-kpi-aov" />
          <KPICard label="Items Sold" value={fmtNum(k.items_sold)} accent="amber" testid="es-kpi-items" />
          <KPICard label="Active Customers" value={fmtNum(k.active_customers)} hint={`of ${fmtNum(k.total_customers)}`} accent="emerald" testid="es-kpi-active" />
          <KPICard label="Total Base" value={fmtNum(k.total_customers)} accent="slate" testid="es-kpi-base" />
          <KPICard label="Liability" value={fmtINR(k.outstanding_liability_inr)} accent="rose" testid="es-kpi-liability" />
          <KPICard label="Period" value={`${period} days`} accent="slate" testid="es-kpi-period" />
        </div>

        <div className="grid lg:grid-cols-2 gap-4">
          <div className="bg-white border border-black/10 p-5">
            <SectionHeading eyebrow="LEADERBOARD" title="Top 5 stores" accent="indigo" />
            <table className="data-table">
              <thead><tr><th>Rank</th><th>Store</th><th>City</th><th className="text-right">Net ₹</th></tr></thead>
              <tbody>
                {data.top_stores.map((s, i) => (
                  <tr key={i}>
                    <td className="font-mono">{i + 1}</td>
                    <td>{s.name}</td>
                    <td>{s.city || "—"}</td>
                    <td className="text-right font-mono">{fmtINR(s.net)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="bg-white border border-black/10 p-5">
            <SectionHeading eyebrow="LEADERBOARD" title="Top 5 cities" accent="teal" />
            <table className="data-table">
              <thead><tr><th>Rank</th><th>City</th><th className="text-right">Net ₹</th></tr></thead>
              <tbody>
                {data.top_cities.map((c, i) => (
                  <tr key={i}>
                    <td className="font-mono">{i + 1}</td>
                    <td>{c.city}</td>
                    <td className="text-right font-mono">{fmtINR(c.net)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="text-[10px] text-neutral-400 uppercase tracking-widest" data-testid="es-generated-at">
          Generated at {data.generated_at} · No snapshots · Live from MongoDB
        </div>
      </div>
    </div>
  );
}
