/* Customer Reactivate — restore a deactivated customer. */
import { useState, useEffect } from "react";
import api from "@/lib/api";
import { PageHeader } from "../_shared";
import { Pill, ConfirmReasonModal } from "./_shared";
import { Search, UserPlus, RefreshCw } from "lucide-react";
import { toast } from "sonner";

export default function CustomerReactivate() {
  const [q, setQ] = useState("");
  const [list, setList] = useState([]);
  const [reactivatedList, setReactivatedList] = useState([]);
  const [confirmRow, setConfirmRow] = useState(null);

  const loadDeactivated = async () => {
    try {
      const params = q ? { q } : {};
      const r = await api.get("/support-desk/deactivated-customers", { params });
      setList(r.data.rows || []);
    } catch (e) { /* silent */ }
  };
  const loadReactivated = async () => {
    try {
      const r = await api.get("/support-desk/reactivated-customers");
      setReactivatedList(r.data.rows || []);
    } catch (e) { /* silent */ }
  };
  useEffect(() => { loadDeactivated(); loadReactivated(); /* eslint-disable-next-line */ }, []);

  const reactivate = async (reason) => {
    if (!confirmRow) return;
    try {
      await api.post("/support-desk/customer-reactivate", { mobile: confirmRow.mobile, reason });
      toast.success("Customer reactivated");
      setConfirmRow(null);
      loadDeactivated();
      loadReactivated();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    }
  };

  return (
    <div data-testid="sd-reactivate-cust-page">
      <PageHeader title="Customer Reactivate" subtitle="SUPPORT DESK · LIFECYCLE" />
      <div className="p-8 space-y-6">
        <div className="chart-card p-5">
          <form onSubmit={(e) => { e.preventDefault(); loadDeactivated(); }} className="flex items-end gap-3 flex-wrap">
            <div className="flex-1 min-w-[260px]">
              <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Filter deactivated by mobile / name</label>
              <input value={q} onChange={(e) => setQ(e.target.value)} className="k-input w-full" data-testid="sd-react-q" />
            </div>
            <button type="submit" className="k-btn kazo-bg-burgundy text-white" data-testid="sd-react-search">
              <Search className="w-3.5 h-3.5" /> Find
            </button>
          </form>
        </div>

        <div className="chart-card p-5" data-accent="amber">
          <h3 className="font-display text-xl mb-3">Deactivated customers · {list.length}</h3>
          {list.length === 0 ? (
            <div className="text-sm text-neutral-500 py-6 text-center">No deactivated customers.</div>
          ) : (
            <table className="w-full text-sm" data-testid="sd-react-list">
              <thead className="border-b border-black/10 text-left">
                <tr>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Mobile</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Name</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Deactivated</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Reason</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Action</th>
                </tr>
              </thead>
              <tbody>
                {list.map((c) => (
                  <tr key={c.id || c.mobile} className="border-b border-black/5">
                    <td className="py-2 px-2 font-mono">{c.mobile}</td>
                    <td className="py-2 px-2">{c.name || "—"}</td>
                    <td className="py-2 px-2 text-xs text-neutral-600">{(c.deactivated_at || "").slice(0, 19).replace("T", " ")}</td>
                    <td className="py-2 px-2 text-xs text-neutral-600">{c.deactivation_reason || "—"}</td>
                    <td className="py-2 px-2">
                      <button
                        onClick={() => setConfirmRow(c)}
                        className="text-xs px-3 py-1 border border-emerald-300 text-emerald-700 hover:bg-emerald-50 flex items-center gap-1"
                        data-testid={`sd-react-action-${c.mobile}`}
                      >
                        <UserPlus className="w-3 h-3" /> Reactivate
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="chart-card p-5" data-accent="emerald" data-testid="sd-recent-reactivations">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-display text-xl">Recently reactivated · {reactivatedList.length}</h3>
            <button onClick={loadReactivated} className="text-xs px-2 py-1 border border-neutral-300 hover:bg-neutral-50 flex items-center gap-1">
              <RefreshCw className="w-3 h-3" /> Refresh
            </button>
          </div>
          {reactivatedList.length === 0 ? (
            <div className="text-sm text-neutral-500 py-6 text-center">No reactivations yet.</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="border-b border-black/10 text-left">
                <tr>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Mobile</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Name</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Reactivated</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">By</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Reason</th>
                </tr>
              </thead>
              <tbody>
                {reactivatedList.map((c) => (
                  <tr key={c.id || c.mobile} className="border-b border-black/5">
                    <td className="py-2 px-2 font-mono">{c.mobile}</td>
                    <td className="py-2 px-2">{c.name || "—"}</td>
                    <td className="py-2 px-2 text-xs text-neutral-600">{(c.reactivated_at || "").slice(0, 19).replace("T", " ")}</td>
                    <td className="py-2 px-2 text-xs">{c.reactivated_by || "—"}</td>
                    <td className="py-2 px-2 text-xs text-neutral-600">{c.reactivation_reason || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
      <ConfirmReasonModal
        open={!!confirmRow}
        title="Reactivate customer"
        description={confirmRow ? `${confirmRow.name || confirmRow.mobile} will be marked active again and start receiving campaigns.` : ""}
        confirmLabel="Reactivate"
        onConfirm={reactivate}
        onCancel={() => setConfirmRow(null)}
      />
    </div>
  );
}
