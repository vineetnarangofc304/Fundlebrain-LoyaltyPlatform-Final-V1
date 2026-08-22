import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { fmtNum } from "@/lib/format";
import { X, Loader2, Truck, RefreshCw, DownloadCloud, CheckCircle2, AlertTriangle, Clock } from "lucide-react";
import { toast } from "sonner";

function Stat({ label, value, sub, accent, testid }) {
  return (
    <div className="border border-black/10 rounded p-3 bg-white" data-testid={testid}>
      <div className="text-[10px] uppercase tracking-widest text-neutral-500">{label}</div>
      <div className={`text-2xl font-display mt-1 ${accent || ""}`}>{value}</div>
      {sub && <div className="text-[11px] text-neutral-500 mt-0.5">{sub}</div>}
    </div>
  );
}

export default function CampaignDeliveryModal({ campaign, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [pulling, setPulling] = useState(false);
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    setLoading(true); setErr(null);
    try {
      const r = await api.get(`/campaigns/${campaign.id}/delivery`);
      setData(r.data);
    } catch (e) {
      setErr(e?.response?.data?.detail || "Failed to load delivery report");
    } finally { setLoading(false); }
  }, [campaign.id]);

  useEffect(() => { load(); }, [load]);

  const pullDlrs = async () => {
    setPulling(true);
    try {
      const r = await api.post("/communications/dlr/pull", {});
      if (r.data.configured === false) toast.info(r.data.message || "Karix delivers DLRs by webhook — no pull API configured");
      else toast.success(`Reconciled ${fmtNum(r.data.ingested || 0)} delivery report(s)`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "DLR pull failed");
    } finally { setPulling(false); }
  };

  const c = data?.counts || {};

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-neutral-50 w-full max-w-3xl max-h-[92vh] overflow-y-auto rounded" onClick={(e) => e.stopPropagation()} data-testid="campaign-delivery-modal">
        <div className="flex items-center justify-between p-5 border-b border-black/10 bg-white sticky top-0 z-10">
          <div>
            <div className="text-[10px] uppercase tracking-widest text-neutral-500 flex items-center gap-1"><Truck className="w-3.5 h-3.5" /> Delivery report (Karix DLR)</div>
            <h3 className="font-display text-xl">{campaign.name}</h3>
          </div>
          <div className="flex gap-2">
            <button onClick={load} className="k-btn k-btn-sm k-btn-ghost" data-testid="delivery-refresh"><RefreshCw className="w-3.5 h-3.5" /> Refresh</button>
            <button onClick={pullDlrs} disabled={pulling} className="k-btn k-btn-sm k-btn-ghost" data-testid="delivery-pull">
              {pulling ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <DownloadCloud className="w-3.5 h-3.5" />} Pull DLRs
            </button>
            <button onClick={onClose} className="k-btn k-btn-ghost" data-testid="delivery-close"><X className="w-4 h-4" /></button>
          </div>
        </div>

        <div className="p-5 space-y-5">
          {loading && <div className="flex items-center gap-2 text-neutral-500 py-10 justify-center"><Loader2 className="w-5 h-5 animate-spin" /> Loading delivery report…</div>}
          {err && <div className="text-rose-600 text-sm py-6 text-center" data-testid="delivery-error">{err}</div>}

          {!loading && !err && data && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Stat label="Total messages" value={fmtNum(data.total)} testid="delivery-total" />
                <Stat label="Delivered" value={fmtNum(c.delivered)} sub={`${data.delivery_rate_pct}% delivery`} accent="text-emerald-700" testid="delivery-delivered" />
                <Stat label="Failed / Undelivered" value={fmtNum((c.failed || 0) + (c.undelivered || 0))} sub={`${data.failure_rate_pct}% failure`} accent="text-rose-600" testid="delivery-failed" />
                <Stat label="Pending (submitted)" value={fmtNum(c.pending)} testid="delivery-pending" />
              </div>

              {data.total === 0 && (
                <div className="text-sm text-neutral-500 bg-white border border-black/10 rounded p-4" data-testid="delivery-empty">
                  No messages logged for this campaign yet. Real delivery statuses arrive as Karix posts DLRs to
                  <code className="mx-1 px-1 bg-neutral-100 rounded">{data.webhook_url}</code>. Register this callback with Karix support.
                </div>
              )}

              {Object.keys(data.by_status || {}).length > 0 && (
                <div>
                  <div className="text-[10px] uppercase tracking-widest text-neutral-500 mb-2">By raw status</div>
                  <div className="flex gap-1.5 flex-wrap">
                    {Object.entries(data.by_status).map(([k, v]) => (
                      <span key={k} className="pill pill-neutral" data-testid={`delivery-status-${k}`}>
                        {k === "delivered" ? <CheckCircle2 className="w-3 h-3 inline mr-1 text-emerald-600" /> : ["failed", "undelivered", "rejected", "expired"].includes(k) ? <AlertTriangle className="w-3 h-3 inline mr-1 text-rose-500" /> : <Clock className="w-3 h-3 inline mr-1 text-amber-500" />}
                        {k}: {fmtNum(v)}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {data.failures_sample?.length > 0 && (
                <div data-testid="delivery-failures">
                  <div className="text-[10px] uppercase tracking-widest text-neutral-500 mb-2">Recent failures</div>
                  <div className="bg-white border border-black/10 rounded overflow-hidden">
                    <table className="data-table">
                      <thead><tr><th>Mobile</th><th>Status</th><th>Response</th><th>When</th></tr></thead>
                      <tbody>
                        {data.failures_sample.map((f, i) => (
                          <tr key={i}>
                            <td className="font-mono">{f.mobile}</td>
                            <td><span className="pill pill-warning">{f.delivery_status}</span></td>
                            <td className="text-xs text-neutral-500 max-w-[240px] truncate">{f.response || "—"}</td>
                            <td className="text-xs text-neutral-400">{(f.timestamp || "").slice(0, 16).replace("T", " ")}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              <div className="text-[10px] text-neutral-400 pt-2 border-t border-black/5">
                Numbers with 3 successive delivery failures are auto-blacklisted and excluded from future campaigns.
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
