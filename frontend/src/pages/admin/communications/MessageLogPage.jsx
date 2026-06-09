/* SMS / Message Log — every message dispatch, with the real provider response.
   Shows mobile, date/time, channel, event trigger, bill number, sender, DLT template id,
   delivery status and the raw Karix response so failures are self-diagnosing. */
import { useEffect, useState, useCallback } from "react";
import api from "@/lib/api";
import { PageHeader, SectionHeading } from "../_shared";
import { fmtDateTime } from "@/lib/format";
import { RefreshCw, Search, X, AlertTriangle, Activity, CheckCircle2, XCircle } from "lucide-react";

const STATUS_STYLES = {
  ok: { bg: "#ECFDF5", color: "#047857", border: "#A7F3D0", label: "Sent" },
  ok_no_dlt_template: { bg: "#FFFBEB", color: "#B45309", border: "#FDE68A", label: "Sent · NO DLT ID ⚠" },
  config_missing: { bg: "#FEF2F2", color: "#B91C1C", border: "#FECACA", label: "Provider not configured" },
  exception: { bg: "#FEF2F2", color: "#B91C1C", border: "#FECACA", label: "Error" },
  fire_exception: { bg: "#FEF2F2", color: "#B91C1C", border: "#FECACA", label: "Fire error" },
  skipped_unapproved: { bg: "#F5F3FF", color: "#6D28D9", border: "#DDD6FE", label: "Skipped (unapproved)" },
};
const pill = (s) => STATUS_STYLES[s] || { bg: "#F3F4F6", color: "#374151", border: "#E5E7EB", label: s };

const CHANNELS = ["", "sms", "whatsapp", "rcs"];

export default function MessageLogPage() {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ channel: "", status: "", mobile: "", event_trigger: "" });
  const [expanded, setExpanded] = useState(null);
  const [diag, setDiag] = useState(null);
  const [diagLoading, setDiagLoading] = useState(false);

  const runDiag = async () => {
    setDiagLoading(true);
    setDiag(null);
    try {
      const r = await api.get("/provider-connectivity");
      setDiag(r.data);
    } catch (e) {
      setDiag({ error: e?.response?.data?.detail || e.message || "Diagnostic failed" });
    } finally { setDiagLoading(false); }
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: 200 };
      Object.entries(filters).forEach(([k, v]) => { if (v) params[k] = v; });
      const r = await api.get("/message-log", { params });
      setRows(r.data.rows || []);
      setTotal(r.data.total || 0);
    } finally { setLoading(false); }
  }, [filters]);

  useEffect(() => { load(); }, [load]);

  const set = (k, v) => setFilters((f) => ({ ...f, [k]: v }));
  const clear = () => setFilters({ channel: "", status: "", mobile: "", event_trigger: "" });

  return (
    <div data-testid="message-log-page">
      <PageHeader
        title="SMS / Message Log"
        subtitle="EVERY DISPATCH · LIVE"
        actions={
          <>
            <button onClick={runDiag} className="k-btn k-btn-outline k-btn-sm" data-testid="msglog-diag" disabled={diagLoading}>
              <Activity className={`w-3.5 h-3.5 ${diagLoading ? "animate-pulse" : ""}`} /> {diagLoading ? "Testing…" : "Connectivity check"}
            </button>
            <button onClick={load} className="k-btn k-btn-outline k-btn-sm" data-testid="msglog-refresh">
              <RefreshCw className="w-3.5 h-3.5" /> Refresh
            </button>
          </>
        }
      />

      <div className="p-8 space-y-6">
        {/* Filters */}
        <div className="chart-card p-4 flex flex-wrap items-end gap-3" data-testid="msglog-filters">
          <label className="text-xs">
            <div className="text-neutral-500 uppercase tracking-widest mb-1 text-[10px]">Channel</div>
            <select className="k-input" value={filters.channel} onChange={(e) => set("channel", e.target.value)} data-testid="msglog-f-channel">
              {CHANNELS.map((c) => <option key={c || "all"} value={c}>{c ? c.toUpperCase() : "All"}</option>)}
            </select>
          </label>
          <label className="text-xs">
            <div className="text-neutral-500 uppercase tracking-widest mb-1 text-[10px]">Status</div>
            <input className="k-input" value={filters.status} onChange={(e) => set("status", e.target.value)} placeholder="ok / exception…" data-testid="msglog-f-status" />
          </label>
          <label className="text-xs">
            <div className="text-neutral-500 uppercase tracking-widest mb-1 text-[10px]">Mobile</div>
            <input className="k-input" value={filters.mobile} onChange={(e) => set("mobile", e.target.value)} placeholder="last digits" data-testid="msglog-f-mobile" />
          </label>
          <label className="text-xs">
            <div className="text-neutral-500 uppercase tracking-widest mb-1 text-[10px]">Event</div>
            <input className="k-input" value={filters.event_trigger} onChange={(e) => set("event_trigger", e.target.value)} placeholder="purchase / registration…" data-testid="msglog-f-event" />
          </label>
          <button onClick={load} className="k-btn k-btn-primary k-btn-sm" data-testid="msglog-apply"><Search className="w-3.5 h-3.5" /> Search</button>
          <button onClick={clear} className="k-btn k-btn-outline k-btn-sm" data-testid="msglog-clear"><X className="w-3.5 h-3.5" /> Clear</button>
        </div>

        {/* Connectivity diagnostic results */}
        {diag && (
          <div className="chart-card p-4" data-testid="msglog-diag-result">
            <div className="text-[10px] uppercase tracking-[0.3em] text-neutral-500 mb-2">Outbound Connectivity (run from THIS deployment)</div>
            {diag.error ? (
              <div className="text-sm text-rose-700">{String(diag.error)}</div>
            ) : (
              <>
                <div className="flex flex-wrap gap-x-8 gap-y-1 text-sm">
                  <div><span className="text-neutral-500">Egress IP:</span> <span className="font-mono font-medium" data-testid="diag-egress-ip">{diag.egress_ip}</span></div>
                  <div className="text-neutral-500 break-all">Gateway: <span className="font-mono">{diag.sms_endpoint}</span></div>
                </div>
                <div className="mt-3 grid sm:grid-cols-3 gap-2">
                  {(diag.checks || []).map((ck) => (
                    <div key={ck.target} className={`border p-2 text-xs ${ck.ok ? "border-emerald-200 bg-emerald-50/50" : "border-rose-200 bg-rose-50/50"}`}>
                      <div className="flex items-center gap-1 font-medium">
                        {ck.ok ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> : <XCircle className="w-3.5 h-3.5 text-rose-600" />}
                        {ck.target}
                      </div>
                      <div className="text-[11px] text-neutral-600 mt-1">{ck.ok ? `HTTP ${ck.http_status} · ${ck.ms}ms` : ck.error}</div>
                    </div>
                  ))}
                </div>
                <div className="mt-3 text-[12px] text-neutral-700 bg-amber-50 border border-amber-200 rounded px-3 py-2" data-testid="diag-verdict">
                  <strong>Verdict:</strong> {diag.verdict}
                </div>
              </>
            )}
          </div>
        )}

        <div className="chart-card p-5" data-accent="burgundy">
          <SectionHeading eyebrow={`${total.toLocaleString()} TOTAL · ${rows.length} SHOWN`} title="Message dispatch log" accent="burgundy" />
          <div className="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2 my-2 flex items-start gap-2">
            <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
            <span><strong>"Sent · NO DLT ID"</strong> means Karix accepted the request but no DLT Content Template ID was attached — Indian carriers will silently drop it. Add the DLT Content Template ID on the template (Templates → edit) to fix delivery.</span>
          </div>
          {loading && !rows.length ? (
            <div className="py-10 text-neutral-500 text-sm">Loading…</div>
          ) : rows.length === 0 ? (
            <div className="py-12 text-center text-neutral-500 text-sm" data-testid="msglog-empty">No messages logged for this filter yet.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Date · Time</th><th>Channel</th><th>Event</th>
                    <th>Mobile</th><th>Bill #</th><th>Sender</th>
                    <th>DLT Template</th><th>Status</th><th>Response</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((m) => {
                    const st = pill(m.status);
                    return (
                      <tr key={m.id} onClick={() => setExpanded(expanded === m.id ? null : m.id)} className="cursor-pointer" data-testid={`msglog-row-${m.id}`}>
                        <td className="text-[11px] whitespace-nowrap text-neutral-600">{fmtDateTime(m.timestamp)}</td>
                        <td className="text-[10px] uppercase tracking-widest text-neutral-600">{m.channel}</td>
                        <td className="text-[11px]">{m.event_trigger || "—"}</td>
                        <td className="font-mono text-[11px]">{m.mobile || "—"}</td>
                        <td className="font-mono text-[11px]">{m.bill_number || "—"}</td>
                        <td className="text-[11px]">{m.sender_id || "—"}</td>
                        <td className="font-mono text-[10px]">{m.dlt_template_id || <span className="text-rose-600">none</span>}</td>
                        <td>
                          <span className="pill" style={{ background: st.bg, color: st.color, border: `1px solid ${st.border}` }} data-testid={`msglog-status-${m.id}`}>{st.label}</span>
                        </td>
                        <td className="text-[10px] text-neutral-500 max-w-[280px] truncate" title={m.response || ""}>{m.response || "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
