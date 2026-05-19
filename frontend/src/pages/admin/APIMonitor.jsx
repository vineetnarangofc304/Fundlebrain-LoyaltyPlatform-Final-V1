import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader, KPICard } from "./_shared";
import { fmtNum, fmtPct, fmtDateTime } from "@/lib/format";
import { Activity } from "lucide-react";

export default function APIMonitor() {
  const [health, setHealth] = useState(null);
  const [recent, setRecent] = useState([]);

  const load = async () => {
    const [h, r] = await Promise.all([api.get("/api-monitor/health"), api.get("/api-monitor/recent", { params: { limit: 100 } })]);
    setHealth(h.data);
    setRecent(r.data);
  };
  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  if (!health) return <div className="p-10 text-neutral-500">Loading…</div>;

  return (
    <div data-testid="api-monitor-page">
      <PageHeader title="Live API Monitor" subtitle="REAL-TIME · 5s REFRESH"
        actions={<div className="flex items-center gap-2 text-xs"><span className="pulse-live w-2 h-2 bg-red-500 rounded-full inline-block" /> LIVE</div>} />
      <div className="p-8 space-y-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KPICard label="Uptime (24h)" value={fmtPct(health.uptime_24h_pct, 2)} testid="kpi-uptime-24h" />
          <KPICard label="Uptime (1h)" value={fmtPct(health.uptime_1h_pct, 2)} testid="kpi-uptime-1h" />
          <KPICard label="Failed (24h)" value={fmtNum(health.failed_24h)} hint={`of ${fmtNum(health.total_24h)}`} testid="kpi-failed-24h" />
          <KPICard label="Failed (1h)" value={fmtNum(health.failed_1h)} hint={`of ${fmtNum(health.total_1h)}`} testid="kpi-failed-1h" />
        </div>

        <div className="bg-white border border-black/10 p-5">
          <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-3">BY ENDPOINT</div>
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead><tr><th>Endpoint</th><th className="text-right">Total</th><th className="text-right">Failed</th><th className="text-right">Avg Response (ms)</th><th className="text-right">Health</th></tr></thead>
              <tbody>
                {health.by_endpoint.map((r) => (
                  <tr key={r.endpoint}>
                    <td className="font-mono text-xs">{r.endpoint}</td>
                    <td className="text-right font-mono">{fmtNum(r.total)}</td>
                    <td className="text-right font-mono text-red-600">{fmtNum(r.failed)}</td>
                    <td className="text-right font-mono">{r.avg_response_ms}</td>
                    <td className="text-right"><span className={`pill ${r.health_pct > 95 ? "pill-success" : r.health_pct > 85 ? "pill-warning" : "pill-danger"}`}>{fmtPct(r.health_pct, 2)}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="bg-white border border-black/10 p-5">
          <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-3">LAST 100 API CALLS</div>
          <div className="overflow-x-auto max-h-[500px] overflow-y-auto">
            <table className="data-table">
              <thead><tr><th>Timestamp</th><th>Endpoint</th><th>Mobile</th><th>Bill #</th><th className="text-right">Status</th><th className="text-right">ms</th><th>Error</th></tr></thead>
              <tbody>
                {recent.map((r) => (
                  <tr key={r.id}>
                    <td className="text-xs">{fmtDateTime(r.timestamp)}</td>
                    <td className="font-mono text-xs">{r.endpoint}</td>
                    <td className="font-mono text-xs">{r.customer_mobile || "—"}</td>
                    <td className="font-mono text-xs">{r.bill_number || "—"}</td>
                    <td className="text-right"><span className={`pill ${r.status_code < 400 ? "pill-success" : "pill-danger"}`}>{r.status_code}</span></td>
                    <td className="text-right font-mono">{r.response_time_ms}</td>
                    <td className="text-xs text-red-600">{r.error_reason || ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
