import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader, KPICard } from "./_shared";
import { fmtNum, fmtPct, fmtDateTime } from "@/lib/format";
import { Activity, X, Copy } from "lucide-react";
import { toast } from "sonner";

export default function APIMonitor() {
  const [health, setHealth] = useState(null);
  const [recent, setRecent] = useState([]);
  const [byStore, setByStore] = useState([]);
  const [storeSearch, setStoreSearch] = useState("");
  const [drill, setDrill] = useState(null);
  const [filter, setFilter] = useState({ endpoint: "", source: "", method: "", status: "", store: "" });

  const load = async () => {
    const params = { limit: 200 };
    if (filter.endpoint) params.endpoint = filter.endpoint;
    if (filter.source) params.source = filter.source;
    if (filter.method) params.method = filter.method;
    if (filter.status) params.status_code = filter.status;
    if (filter.store) params.store_code = filter.store;
    const [h, r, s] = await Promise.all([
      api.get("/api-monitor/health"),
      api.get("/api-monitor/logs", { params }),
      api.get("/api-monitor/by-store", { params: { window_hours: 24, search: storeSearch } }),
    ]);
    setHealth(h.data);
    setRecent(r.data.rows || r.data || []);
    setByStore(s.data.stores || []);
  };
  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter, storeSearch]);

  if (!health) return <div className="p-10 text-neutral-500">Loading…</div>;

  return (
    <div data-testid="api-monitor-page">
      <PageHeader title="Live API Monitor" subtitle="REAL-TIME · 5s REFRESH · CLICK ANY ROW FOR REQUEST/RESPONSE"
        actions={<div className="flex items-center gap-2 text-xs"><span className="pulse-live w-2 h-2 bg-red-500 rounded-full inline-block" /> LIVE</div>} />
      <div className="p-8 space-y-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KPICard label="Uptime (24h)" value={fmtPct(health.uptime_24h_pct, 2)} testid="kpi-uptime-24h" />
          <KPICard label="Uptime (1h)" value={fmtPct(health.uptime_1h_pct, 2)} testid="kpi-uptime-1h" />
          <KPICard label="Failed (24h)" value={fmtNum(health.failed_24h)} hint={`of ${fmtNum(health.total_24h)}`} testid="kpi-failed-24h" />
          <KPICard label="Failed (1h)" value={fmtNum(health.failed_1h)} hint={`of ${fmtNum(health.total_1h)}`} testid="kpi-failed-1h" />
        </div>

        <div className="bg-white border border-black/10 p-5">
          <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-3">BY ENDPOINT (LAST 24h)</div>
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead><tr><th>Endpoint</th><th className="text-right">Total</th><th className="text-right">Failed</th><th className="text-right">Avg Response (ms)</th><th className="text-right">Health</th></tr></thead>
              <tbody>
                {health.by_endpoint.map((r) => (
                  <tr key={r.endpoint} className="cursor-pointer hover:bg-neutral-50" onClick={() => setFilter({ ...filter, endpoint: r.endpoint })}>
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

        <div className="bg-white border border-black/10 p-5" data-testid="apimon-by-store">
          <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
            <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500">BY STORE · POS HITS (LAST 24h) · WORST FIRST</div>
            <input
              className="k-input k-input-sm w-56"
              placeholder="Search store code or name…"
              value={storeSearch}
              onChange={(e) => setStoreSearch(e.target.value)}
              data-testid="apimon-store-search"
            />
          </div>
          <div className="overflow-x-auto max-h-[360px] overflow-y-auto">
            <table className="data-table">
              <thead><tr>
                <th>Store</th><th className="text-right">Hits</th><th className="text-right">Failed</th>
                <th className="text-right">Timeouts</th><th className="text-right">Err %</th>
                <th className="text-right">Avg ms</th><th className="text-right">Max ms</th><th>Last seen</th>
              </tr></thead>
              <tbody>
                {byStore.length === 0 && (
                  <tr><td colSpan={8} className="text-center text-neutral-400 py-4">No POS hits in the last 24h.</td></tr>
                )}
                {byStore.map((s) => (
                  <tr key={s.store_code}
                      className={`cursor-pointer hover:bg-neutral-50 ${filter.store === s.store_code ? "bg-neutral-100" : ""}`}
                      onClick={() => setFilter({ ...filter, store: s.store_code, source: "pos_ewards" })}
                      data-testid={`apimon-store-row-${s.store_code}`}>
                    <td className="text-xs">
                      <span className="font-mono">{s.store_code}</span>
                      <span className="text-neutral-500"> · {s.store_name}{s.city ? `, ${s.city}` : ""}</span>
                    </td>
                    <td className="text-right font-mono">{fmtNum(s.total)}</td>
                    <td className={`text-right font-mono ${s.failed > 0 ? "text-red-600" : ""}`}>{fmtNum(s.failed)}</td>
                    <td className={`text-right font-mono ${s.timeouts > 0 ? "text-red-600 font-semibold" : ""}`}>{fmtNum(s.timeouts)}</td>
                    <td className="text-right">
                      <span className={`pill ${s.error_rate_pct === 0 ? "pill-success" : s.error_rate_pct < 5 ? "pill-warning" : "pill-danger"}`}>{fmtPct(s.error_rate_pct, 2)}</span>
                    </td>
                    <td className="text-right font-mono">{s.avg_response_ms}</td>
                    <td className={`text-right font-mono ${s.max_response_ms > 9000 ? "text-red-600" : ""}`}>{s.max_response_ms}</td>
                    <td className="text-xs whitespace-nowrap">{fmtDateTime(s.last_seen)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="bg-white border border-black/10 p-5">
          <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
            <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500">RECENT API CALLS</div>
            <div className="flex items-center gap-2 text-xs flex-wrap">
              <select className="k-input k-input-sm" value={filter.source} onChange={(e) => setFilter({ ...filter, source: e.target.value })} data-testid="apimon-source-filter">
                <option value="">All sources</option>
                <option value="internal">Internal (admin / dashboards)</option>
                <option value="pos_ewards">POS (eWards spec)</option>
              </select>
              <select className="k-input k-input-sm" value={filter.method} onChange={(e) => setFilter({ ...filter, method: e.target.value })} data-testid="apimon-method-filter">
                <option value="">All methods</option>
                <option value="GET">GET</option>
                <option value="POST">POST</option>
                <option value="PUT">PUT</option>
                <option value="PATCH">PATCH</option>
                <option value="DELETE">DELETE</option>
              </select>
              <select className="k-input k-input-sm" value={filter.status} onChange={(e) => setFilter({ ...filter, status: e.target.value })} data-testid="apimon-status-filter">
                <option value="">All status</option>
                <option value="200">200 OK</option>
                <option value="400">400</option>
                <option value="401">401</option>
                <option value="403">403</option>
                <option value="404">404</option>
                <option value="500">500</option>
              </select>
              {filter.endpoint && (
                <span className="pill pill-info inline-flex items-center gap-1">
                  {filter.endpoint}
                  <button onClick={() => setFilter({ ...filter, endpoint: "" })} className="ml-1"><X className="w-3 h-3" /></button>
                </span>
              )}
              {filter.store && (
                <span className="pill pill-info inline-flex items-center gap-1" data-testid="apimon-store-chip">
                  Store: {filter.store}
                  <button onClick={() => setFilter({ ...filter, store: "" })} className="ml-1"><X className="w-3 h-3" /></button>
                </span>
              )}
            </div>
          </div>
          <div className="overflow-x-auto max-h-[500px] overflow-y-auto">
            <table className="data-table">
              <thead><tr><th>Timestamp</th><th>Method</th><th>Endpoint</th><th>Actor</th><th>Bill #</th><th className="text-right">Status</th><th className="text-right">ms</th><th>Error</th></tr></thead>
              <tbody>
                {recent.map((r) => (
                  <tr key={r.id} onClick={() => setDrill(r)} className="cursor-pointer hover:bg-neutral-50" data-testid={`apilog-row-${r.id}`}>
                    <td className="text-xs whitespace-nowrap">{fmtDateTime(r.timestamp)}</td>
                    <td className="font-mono text-xs">{r.method || "—"}</td>
                    <td className="font-mono text-xs">{r.endpoint}</td>
                    <td className="font-mono text-xs">{r.api_key_label || r.customer_mobile || "—"}</td>
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

      {drill && <ApiLogDrill row={drill} onClose={() => setDrill(null)} />}
    </div>
  );
}


function ApiLogDrill({ row, onClose }) {
  const copy = async (obj) => {
    try { await navigator.clipboard.writeText(JSON.stringify(obj, null, 2)); toast.success("Copied"); }
    catch (e) { toast.error("Copy failed"); }
  };
  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white w-full max-w-4xl max-h-[90vh] flex flex-col" onClick={(e) => e.stopPropagation()} data-testid="apilog-drill">
        <div className="p-5 border-b border-black/10 flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.22em] text-neutral-500">API CALL DETAIL · {row.method}</div>
            <h3 className="font-display text-2xl">{row.endpoint}</h3>
            <div className="text-xs text-neutral-500 mt-1">
              {fmtDateTime(row.timestamp)} · {row.response_time_ms}ms · status <span className={`pill ${row.status_code < 400 ? "pill-success" : "pill-danger"}`}>{row.status_code}</span>
              {row.api_key_label && <span className="ml-2">key={row.api_key_label}</span>}
              {row.actor_ip && <span className="ml-2">ip={row.actor_ip}</span>}
            </div>
          </div>
          <button onClick={onClose} className="k-btn k-btn-ghost k-btn-sm" data-testid="apilog-drill-close"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-5 grid md:grid-cols-2 gap-4 overflow-auto">
          <PayloadBlock title="Request" obj={row.request_payload} onCopy={() => copy(row.request_payload)} testid="apilog-request" />
          <PayloadBlock title="Response" obj={row.response_payload} onCopy={() => copy(row.response_payload)} testid="apilog-response" />
        </div>
      </div>
    </div>
  );
}

function PayloadBlock({ title, obj, onCopy, testid }) {
  return (
    <div data-testid={testid}>
      <div className="flex items-center justify-between mb-2">
        <div className="text-[10px] uppercase tracking-widest text-neutral-500">{title}</div>
        {obj && <button onClick={onCopy} className="k-btn k-btn-ghost k-btn-sm"><Copy className="w-3 h-3" /> Copy JSON</button>}
      </div>
      <pre className="bg-neutral-900 text-emerald-200 p-3 font-mono text-[10px] overflow-x-auto whitespace-pre max-h-[55vh] overflow-y-auto">
        {obj ? JSON.stringify(obj, null, 2) : "—"}
      </pre>
    </div>
  );
}
