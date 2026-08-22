import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { fmtNum } from "@/lib/format";
import { X, Loader2, ShieldBan, Plus, Trash2, Search } from "lucide-react";
import { toast } from "sonner";

export default function CampaignBlacklistModal({ onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [mobile, setMobile] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (query) => {
    setLoading(true);
    try {
      const r = await api.get("/campaigns/blacklist", { params: query ? { q: query } : {} });
      setData(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load blacklist");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const add = async () => {
    if (!mobile.trim()) { toast.error("Enter a mobile number"); return; }
    setBusy(true);
    try {
      await api.post("/campaigns/blacklist", { mobile: mobile.trim(), reason: reason.trim() || "manual" });
      toast.success("Number blacklisted");
      setMobile(""); setReason("");
      load(q);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to add");
    } finally { setBusy(false); }
  };

  const remove = async (m) => {
    try {
      await api.delete(`/campaigns/blacklist/${m}`);
      toast.success("Removed from blacklist");
      load(q);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to remove");
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-neutral-50 w-full max-w-2xl max-h-[92vh] overflow-y-auto rounded" onClick={(e) => e.stopPropagation()} data-testid="campaign-blacklist-modal">
        <div className="flex items-center justify-between p-5 border-b border-black/10 bg-white sticky top-0 z-10">
          <div>
            <div className="text-[10px] uppercase tracking-widest text-neutral-500 flex items-center gap-1"><ShieldBan className="w-3.5 h-3.5" /> SMS delivery blacklist</div>
            <h3 className="font-display text-xl">{data ? `${fmtNum(data.total)} numbers excluded` : "Blacklist"}</h3>
            {data && <div className="text-[11px] text-neutral-500">{fmtNum(data.auto)} auto (3+ failures) · {fmtNum(data.manual)} manual</div>}
          </div>
          <button onClick={onClose} className="k-btn k-btn-ghost" data-testid="blacklist-close"><X className="w-4 h-4" /></button>
        </div>

        <div className="p-5 space-y-4">
          {/* manual add */}
          <div className="flex gap-2 items-center bg-white border border-black/10 rounded p-3">
            <input className="k-input flex-1" placeholder="Mobile number" value={mobile} onChange={(e) => setMobile(e.target.value)} data-testid="blacklist-mobile-input" />
            <input className="k-input flex-1" placeholder="Reason (optional)" value={reason} onChange={(e) => setReason(e.target.value)} data-testid="blacklist-reason-input" />
            <button className="k-btn kazo-bg-burgundy disabled:opacity-50" onClick={add} disabled={busy} data-testid="blacklist-add-btn">
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Add
            </button>
          </div>

          {/* search */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-3 text-neutral-400" />
            <input className="k-input pl-8" placeholder="Search blacklisted number" value={q}
              onChange={(e) => { setQ(e.target.value); load(e.target.value); }} data-testid="blacklist-search" />
          </div>

          {loading ? (
            <div className="flex items-center gap-2 text-neutral-500 py-8 justify-center"><Loader2 className="w-5 h-5 animate-spin" /> Loading…</div>
          ) : (
            <div className="bg-white border border-black/10 rounded overflow-hidden">
              <table className="data-table">
                <thead><tr><th>Mobile</th><th>Reason</th><th>Source</th><th>When</th><th></th></tr></thead>
                <tbody>
                  {(data?.rows || []).map((r) => (
                    <tr key={r.mobile} data-testid={`blacklist-row-${r.mobile}`}>
                      <td className="font-mono">{r.mobile}</td>
                      <td className="text-xs text-neutral-600 max-w-[220px] truncate">{r.reason}</td>
                      <td><span className={`pill ${r.source === "auto_dlr" ? "pill-warning" : "pill-neutral"}`}>{r.source === "auto_dlr" ? "auto" : "manual"}</span></td>
                      <td className="text-xs text-neutral-400">{(r.blacklisted_at || "").slice(0, 10)}</td>
                      <td className="text-right">
                        <button className="k-btn k-btn-sm k-btn-ghost text-rose-600" onClick={() => remove(r.mobile)} data-testid={`blacklist-remove-${r.mobile}`}><Trash2 className="w-3.5 h-3.5" /></button>
                      </td>
                    </tr>
                  ))}
                  {(!data?.rows || data.rows.length === 0) && <tr><td colSpan={5} className="text-center py-8 text-neutral-400">No blacklisted numbers</td></tr>}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
