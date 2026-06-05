/* Customer Deactivate — search for a customer by mobile and deactivate.
   Also shows the list of currently-deactivated customers. */
import { useState, useEffect } from "react";
import api from "@/lib/api";
import { PageHeader } from "../_shared";
import { Pill, ConfirmReasonModal } from "./_shared";
import { Search, UserMinus, RefreshCw } from "lucide-react";
import { toast } from "sonner";

export default function CustomerDeactivate() {
  const [mobile, setMobile] = useState("");
  const [results, setResults] = useState(null);
  const [deactivatedList, setDeactivatedList] = useState([]);
  const [confirmRow, setConfirmRow] = useState(null);

  const loadDeactivated = async () => {
    try {
      const r = await api.get("/support-desk/deactivated-customers");
      setDeactivatedList(r.data.rows || []);
    } catch (e) { /* silent */ }
  };
  useEffect(() => { loadDeactivated(); }, []);

  const searchCustomer = async (e) => {
    e?.preventDefault?.();
    if (!mobile) return;
    try {
      const r = await api.get(`/customers?q=${encodeURIComponent(mobile)}&limit=10`);
      setResults(r.data.items || []);
    } catch (err) {
      toast.error("Search failed");
    }
  };

  const deactivate = async (reason) => {
    if (!confirmRow) return;
    try {
      await api.post("/support-desk/customer-deactivate", { mobile: confirmRow.mobile, reason });
      toast.success("Customer deactivated");
      setConfirmRow(null);
      setResults(null);
      setMobile("");
      loadDeactivated();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed");
    }
  };

  return (
    <div data-testid="sd-deactivate-page">
      <PageHeader title="Customer Deactivate" subtitle="SUPPORT DESK · LIFECYCLE" />
      <div className="p-8 space-y-6">
        <div className="chart-card p-5">
          <form onSubmit={searchCustomer} className="flex items-end gap-3 flex-wrap">
            <div className="flex-1 min-w-[260px]">
              <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Search by mobile / name / email</label>
              <input value={mobile} onChange={(e) => setMobile(e.target.value)} className="k-input w-full" data-testid="sd-deact-input" />
            </div>
            <button type="submit" className="k-btn kazo-bg-burgundy text-white" data-testid="sd-deact-search">
              <Search className="w-3.5 h-3.5" /> Search
            </button>
          </form>
        </div>

        {results !== null && (
          <div className="chart-card p-5" data-accent="rose">
            <h3 className="font-display text-xl mb-3">Matches · {results.length}</h3>
            {results.length === 0 ? (
              <div className="text-sm text-neutral-500 py-6 text-center">No customer matched.</div>
            ) : (
              <table className="w-full text-sm">
                <thead className="border-b border-black/10 text-left">
                  <tr>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Mobile</th>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Name</th>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Tier</th>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Status</th>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {results.map((c) => (
                    <tr key={c.id || c.mobile} className="border-b border-black/5">
                      <td className="py-2 px-2 font-mono">{c.mobile}</td>
                      <td className="py-2 px-2">{c.name || "—"}</td>
                      <td className="py-2 px-2"><span className="text-xs uppercase">{c.tier}</span></td>
                      <td className="py-2 px-2">
                        {c.is_active === false ? <Pill tone="danger">Deactivated</Pill> : <Pill tone="success">Active</Pill>}
                      </td>
                      <td className="py-2 px-2">
                        <button
                          onClick={() => setConfirmRow(c)}
                          disabled={c.is_active === false}
                          className="text-xs px-3 py-1 border border-rose-300 text-rose-700 hover:bg-rose-50 disabled:opacity-30 disabled:cursor-not-allowed flex items-center gap-1"
                          data-testid={`sd-deact-action-${c.mobile}`}
                        >
                          <UserMinus className="w-3 h-3" /> Deactivate
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        <div className="chart-card p-5" data-accent="slate" data-testid="sd-deactivated-list">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-display text-xl">Currently Deactivated · {deactivatedList.length}</h3>
            <button onClick={loadDeactivated} className="text-xs px-2 py-1 border border-neutral-300 hover:bg-neutral-50 flex items-center gap-1">
              <RefreshCw className="w-3 h-3" /> Refresh
            </button>
          </div>
          {deactivatedList.length === 0 ? (
            <div className="text-sm text-neutral-500 py-6 text-center">No deactivated customers.</div>
          ) : (
            <table className="w-full text-sm">
              <thead className="border-b border-black/10 text-left">
                <tr>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Mobile</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Name</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Deactivated</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">By</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Reason</th>
                </tr>
              </thead>
              <tbody>
                {deactivatedList.map((c) => (
                  <tr key={c.id || c.mobile} className="border-b border-black/5">
                    <td className="py-2 px-2 font-mono">{c.mobile}</td>
                    <td className="py-2 px-2">{c.name || "—"}</td>
                    <td className="py-2 px-2 text-xs text-neutral-600">{(c.deactivated_at || "").slice(0, 19).replace("T", " ")}</td>
                    <td className="py-2 px-2 text-xs">{c.deactivated_by || "—"}</td>
                    <td className="py-2 px-2 text-xs text-neutral-600">{c.deactivation_reason || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
      <ConfirmReasonModal
        open={!!confirmRow}
        title="Deactivate customer"
        description={confirmRow ? `${confirmRow.name || confirmRow.mobile} will be marked inactive. They won't receive campaigns until reactivated.` : ""}
        confirmLabel="Deactivate"
        onConfirm={deactivate}
        onCancel={() => setConfirmRow(null)}
      />
    </div>
  );
}
