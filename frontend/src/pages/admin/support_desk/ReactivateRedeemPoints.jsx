/* Reactivate Redeem Points — reverse a point-redemption ledger entry. */
import { useState } from "react";
import api from "@/lib/api";
import { PageHeader } from "../_shared";
import { Pill, ConfirmReasonModal } from "./_shared";
import { Search, RotateCcw } from "lucide-react";
import { fmtNum } from "@/lib/format";
import { toast } from "sonner";

export default function ReactivateRedeemPoints() {
  const [mobile, setMobile] = useState("");
  const [billNumber, setBillNumber] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [rows, setRows] = useState(null);
  const [loading, setLoading] = useState(false);
  const [confirmRow, setConfirmRow] = useState(null);

  const search = async () => {
    setLoading(true);
    try {
      const params = {};
      if (mobile) params.mobile = mobile;
      if (billNumber) params.bill_number = billNumber;
      if (startDate && endDate) { params.start_date = startDate; params.end_date = endDate; }
      const r = await api.get("/support-desk/redeemed-points", { params });
      setRows(r.data.rows || []);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Search failed");
    } finally { setLoading(false); }
  };

  const reactivate = async (reason) => {
    if (!confirmRow) return;
    try {
      const r = await api.post("/support-desk/reactivate-redeem-points", { ledger_id: confirmRow.id, reason });
      toast.success(`${r.data.points_restored} points restored to ${r.data.ledger_id?.slice(0, 8)}…`);
      setConfirmRow(null);
      search();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Reactivation failed");
    }
  };

  return (
    <div data-testid="sd-reactivate-points-page">
      <PageHeader title="Reactivate Redeem Points" subtitle="SUPPORT DESK · REVERSE REDEMPTION" />
      <div className="p-8 space-y-6">
        <div className="chart-card p-5">
          <div className="grid md:grid-cols-2 lg:grid-cols-5 gap-3 items-end">
            <div>
              <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Mobile</label>
              <input value={mobile} onChange={(e) => setMobile(e.target.value)} className="k-input w-full" data-testid="sd-rrp-mobile" />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Bill number</label>
              <input value={billNumber} onChange={(e) => setBillNumber(e.target.value)} className="k-input w-full" data-testid="sd-rrp-bill" />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Start date</label>
              <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="k-input w-full" />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">End date</label>
              <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="k-input w-full" />
            </div>
            <button onClick={search} disabled={loading} className="k-btn kazo-bg-burgundy text-white" data-testid="sd-rrp-search">
              <Search className="w-3.5 h-3.5" /> {loading ? "…" : "Search"}
            </button>
          </div>
        </div>

        {rows !== null && (
          <div className="chart-card p-5 overflow-x-auto" data-accent="rose">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-display text-xl">Recent point redemptions · {rows.length}</h3>
            </div>
            {rows.length === 0 ? (
              <div className="text-sm text-neutral-500 py-8 text-center">No redemptions matched.</div>
            ) : (
              <table className="w-full text-sm" data-testid="sd-rrp-results">
                <thead className="border-b border-black/10 text-left">
                  <tr>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">When</th>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Mobile</th>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Bill</th>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Points</th>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Reason</th>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Status</th>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={r.id || i} className="border-b border-black/5 hover:bg-amber-50/40">
                      <td className="py-2 px-2 text-xs text-neutral-600">{(r.created_at || "").replace("T", " ").slice(0, 19)}</td>
                      <td className="py-2 px-2 font-mono">{r.customer_mobile}</td>
                      <td className="py-2 px-2 font-mono text-xs">{r.bill_number || "—"}</td>
                      <td className="py-2 px-2 font-mono text-right">{fmtNum(Math.abs(r.points || 0))}</td>
                      <td className="py-2 px-2 text-xs text-neutral-600">{r.reason || "—"}</td>
                      <td className="py-2 px-2">
                        {r.reversed ? <Pill tone="danger">Reversed</Pill> : <Pill tone="success">Active</Pill>}
                      </td>
                      <td className="py-2 px-2">
                        <button
                          onClick={() => setConfirmRow(r)}
                          disabled={r.reversed}
                          className="text-xs px-3 py-1 border border-rose-300 text-rose-700 hover:bg-rose-50 disabled:opacity-30 disabled:cursor-not-allowed flex items-center gap-1"
                          data-testid={`sd-rrp-reverse-${r.id}`}
                        >
                          <RotateCcw className="w-3 h-3" /> Reactivate
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>
      <ConfirmReasonModal
        open={!!confirmRow}
        title="Reactivate redeem points"
        description={confirmRow ? `Restore ${Math.abs(confirmRow.points || 0)} points to ${confirmRow.customer_mobile}? This adds a compensating ledger entry.` : ""}
        confirmLabel="Restore Points"
        onConfirm={reactivate}
        onCancel={() => setConfirmRow(null)}
      />
    </div>
  );
}
