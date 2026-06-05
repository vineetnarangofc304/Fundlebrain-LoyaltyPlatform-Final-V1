/* Support Desk Audit Log — every reactivation, deactivation, unsubscribe is logged. */
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader } from "../_shared";
import { RefreshCw } from "lucide-react";

const ACTIONS = [
  { value: "", label: "All actions" },
  { value: "reactivate_coupon", label: "Coupon Reactivations" },
  { value: "reactivate_redeem_points", label: "Points Reactivations" },
  { value: "customer_deactivate", label: "Customer Deactivations" },
  { value: "customer_reactivate", label: "Customer Reactivations" },
  { value: "unsubscribe", label: "Unsubscribes" },
  { value: "resubscribe", label: "Re-subscribes" },
];

export default function SupportDeskAuditLog() {
  const [action, setAction] = useState("");
  const [actor, setActor] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const params = {};
      if (action) params.action = action;
      if (actor) params.actor = actor;
      if (startDate && endDate) { params.start_date = startDate; params.end_date = endDate; }
      const r = await api.get("/support-desk/audit-log", { params });
      setRows(r.data.rows || []);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  return (
    <div data-testid="sd-audit-log-page">
      <PageHeader title="Support Desk Audit Log" subtitle="SUPPORT DESK · COMPLIANCE TRAIL" />
      <div className="p-8 space-y-6">
        <div className="chart-card p-5">
          <div className="grid md:grid-cols-2 lg:grid-cols-5 gap-3 items-end">
            <div>
              <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Action</label>
              <select value={action} onChange={(e) => setAction(e.target.value)} className="k-input w-full" data-testid="sd-audit-action">
                {ACTIONS.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
              </select>
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Actor email</label>
              <input value={actor} onChange={(e) => setActor(e.target.value)} className="k-input w-full" placeholder="agent@kazo.com" data-testid="sd-audit-actor" />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Start date</label>
              <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="k-input w-full" />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">End date</label>
              <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="k-input w-full" />
            </div>
            <button onClick={load} disabled={loading} className="k-btn kazo-bg-burgundy text-white" data-testid="sd-audit-search">
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> Apply
            </button>
          </div>
        </div>

        <div className="chart-card p-5 overflow-x-auto" data-accent="slate">
          <h3 className="font-display text-xl mb-3">{rows.length} log entries</h3>
          {rows.length === 0 ? (
            <div className="text-sm text-neutral-500 py-6 text-center">No support desk actions logged in this window.</div>
          ) : (
            <table className="w-full text-sm" data-testid="sd-audit-table">
              <thead className="border-b border-black/10 text-left">
                <tr>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">When</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Actor</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Action</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Entity</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Metadata</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-b border-black/5">
                    <td className="py-2 px-2 text-xs text-neutral-600 font-mono">{(r.timestamp || "").slice(0, 19).replace("T", " ")}</td>
                    <td className="py-2 px-2 text-xs">{r.user_email}</td>
                    <td className="py-2 px-2 text-xs font-mono">{(r.action || "").replace("support_desk.", "")}</td>
                    <td className="py-2 px-2 text-xs font-mono">{r.entity}{r.entity_id ? ` · ${r.entity_id.slice(0, 8)}…` : ""}</td>
                    <td className="py-2 px-2 text-xs text-neutral-600">
                      {r.metadata ? <code className="bg-neutral-50 px-1 py-0.5 text-[10px]">{JSON.stringify(r.metadata).slice(0, 80)}</code> : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
