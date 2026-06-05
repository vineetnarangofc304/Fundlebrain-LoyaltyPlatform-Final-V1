/* Unsubscribe Customer — opt-out / opt-in by channel + see the master unsub list. */
import { useState, useEffect } from "react";
import api from "@/lib/api";
import { PageHeader } from "../_shared";
import { Pill, ConfirmReasonModal } from "./_shared";
import { Search, BellOff, BellRing, RefreshCw } from "lucide-react";
import { toast } from "sonner";

const CHANNELS = [
  { value: "all", label: "All channels" },
  { value: "sms", label: "SMS" },
  { value: "whatsapp", label: "WhatsApp" },
  { value: "rcs", label: "RCS" },
  { value: "email", label: "Email" },
];

export default function UnsubscribeCustomer() {
  const [mobile, setMobile] = useState("");
  const [channel, setChannel] = useState("all");
  const [list, setList] = useState([]);
  const [filterChannel, setFilterChannel] = useState("");
  const [confirmRow, setConfirmRow] = useState(null);
  const [confirmAction, setConfirmAction] = useState(null);  // 'unsubscribe' or 'resubscribe'

  const loadList = async () => {
    try {
      const params = filterChannel ? { channel: filterChannel } : {};
      const r = await api.get("/support-desk/unsubscribed", { params });
      setList(r.data.rows || []);
    } catch (e) { /* silent */ }
  };
  useEffect(() => { loadList(); /* eslint-disable-next-line */ }, [filterChannel]);

  const unsubscribe = async (reason) => {
    if (!mobile) return;
    try {
      await api.post("/support-desk/unsubscribe", { mobile, channel, reason });
      toast.success(`Unsubscribed ${mobile} from ${channel}`);
      setMobile("");
      setConfirmAction(null);
      loadList();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    }
  };

  const resubscribe = async (reason) => {
    if (!confirmRow) return;
    try {
      await api.post("/support-desk/resubscribe", { mobile: confirmRow.mobile, channel: "all", reason });
      toast.success(`Re-subscribed ${confirmRow.mobile}`);
      setConfirmRow(null);
      loadList();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    }
  };

  return (
    <div data-testid="sd-unsubscribe-page">
      <PageHeader title="Unsubscribe Customer" subtitle="SUPPORT DESK · OPT-OUT" />
      <div className="p-8 space-y-6">
        <div className="chart-card p-5">
          <h3 className="font-display text-xl mb-3">Add to opt-out list</h3>
          <div className="grid md:grid-cols-3 gap-3 items-end">
            <div>
              <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Mobile</label>
              <input value={mobile} onChange={(e) => setMobile(e.target.value)} className="k-input w-full" data-testid="sd-unsub-mobile" />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Channel</label>
              <select value={channel} onChange={(e) => setChannel(e.target.value)} className="k-input w-full" data-testid="sd-unsub-channel">
                {CHANNELS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </div>
            <button
              onClick={() => setConfirmAction("unsubscribe")}
              disabled={!mobile}
              className="k-btn kazo-bg-burgundy text-white disabled:opacity-50"
              data-testid="sd-unsub-btn"
            >
              <BellOff className="w-3.5 h-3.5" /> Unsubscribe
            </button>
          </div>
        </div>

        <div className="chart-card p-5" data-accent="rose" data-testid="sd-unsub-list">
          <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
            <h3 className="font-display text-xl">Unsubscribed customers · {list.length}</h3>
            <div className="flex items-center gap-2">
              <select value={filterChannel} onChange={(e) => setFilterChannel(e.target.value)} className="k-input k-input-sm !w-auto !py-1.5" data-testid="sd-unsub-filter">
                <option value="">All channels</option>
                {CHANNELS.filter((c) => c.value !== "all").map((c) => <option key={c.value} value={c.value}>{c.label} only</option>)}
              </select>
              <button onClick={loadList} className="text-xs px-2 py-1 border border-neutral-300 hover:bg-neutral-50 flex items-center gap-1">
                <RefreshCw className="w-3 h-3" /> Refresh
              </button>
            </div>
          </div>
          {list.length === 0 ? (
            <div className="text-sm text-neutral-500 py-6 text-center">No customers in the opt-out list.</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="border-b border-black/10 text-left">
                <tr>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Mobile</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Name</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Channels</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">When</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Reason</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Action</th>
                </tr>
              </thead>
              <tbody>
                {list.map((c) => (
                  <tr key={c.id || c.mobile} className="border-b border-black/5">
                    <td className="py-2 px-2 font-mono">{c.mobile}</td>
                    <td className="py-2 px-2">{c.name || "—"}</td>
                    <td className="py-2 px-2 text-xs">
                      <div className="flex gap-1 flex-wrap">
                        {(c.unsub_channels || []).map((ch) => <Pill key={ch} tone="warning">{ch}</Pill>)}
                      </div>
                    </td>
                    <td className="py-2 px-2 text-xs text-neutral-600">{(c.unsubscribed_at || "").slice(0, 19).replace("T", " ")}</td>
                    <td className="py-2 px-2 text-xs text-neutral-600">{c.unsubscribed_reason || "—"}</td>
                    <td className="py-2 px-2">
                      <button
                        onClick={() => setConfirmRow(c)}
                        className="text-xs px-3 py-1 border border-emerald-300 text-emerald-700 hover:bg-emerald-50 flex items-center gap-1"
                        data-testid={`sd-resub-${c.mobile}`}
                      >
                        <BellRing className="w-3 h-3" /> Re-subscribe
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
      <ConfirmReasonModal
        open={confirmAction === "unsubscribe"}
        title="Unsubscribe customer"
        description={`Add ${mobile} to the ${channel === "all" ? "global" : channel} opt-out list. They won't receive future ${channel === "all" ? "campaigns" : channel + " messages"} until re-subscribed.`}
        confirmLabel="Confirm Unsubscribe"
        onConfirm={unsubscribe}
        onCancel={() => setConfirmAction(null)}
      />
      <ConfirmReasonModal
        open={!!confirmRow}
        title="Re-subscribe customer"
        description={confirmRow ? `Clear all opt-outs for ${confirmRow.mobile}. They will be eligible for campaigns again.` : ""}
        confirmLabel="Re-subscribe"
        onConfirm={resubscribe}
        onCancel={() => setConfirmRow(null)}
      />
    </div>
  );
}
