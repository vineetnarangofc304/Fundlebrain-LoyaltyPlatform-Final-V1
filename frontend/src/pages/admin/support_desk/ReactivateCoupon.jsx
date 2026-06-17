/* Reactivate Coupon — find a redeemed coupon and reverse it. */
import { useState } from "react";
import api from "@/lib/api";
import { PageHeader } from "../_shared";
import { Pill, ConfirmReasonModal } from "./_shared";
import { Search, RotateCcw } from "lucide-react";
import { fmtMoney2 } from "@/lib/format";
import { toast } from "sonner";

export default function ReactivateCoupon() {
  const [mobile, setMobile] = useState("");
  const [code, setCode] = useState("");
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
      if (code) params.coupon_code = code;
      if (startDate && endDate) { params.start_date = startDate; params.end_date = endDate; }
      const r = await api.get("/support-desk/redeemed-coupons", { params });
      setRows(r.data.rows || []);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Search failed");
    } finally { setLoading(false); }
  };

  const reactivate = async (reason) => {
    if (!confirmRow) return;
    try {
      await api.post("/support-desk/reactivate-coupon", { redemption_id: confirmRow.id, reason });
      toast.success("Coupon reactivated");
      setConfirmRow(null);
      search();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Reactivation failed");
    }
  };

  return (
    <div data-testid="sd-reactivate-coupon-page">
      <PageHeader title="Reactivate Coupon" subtitle="SUPPORT DESK · REVERSE REDEMPTION" />
      <div className="p-8 space-y-6">
        <div className="chart-card p-5">
          <div className="grid md:grid-cols-2 lg:grid-cols-5 gap-3 items-end">
            <div>
              <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Mobile</label>
              <input value={mobile} onChange={(e) => setMobile(e.target.value)} className="k-input w-full" data-testid="sd-rac-mobile" />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Coupon code</label>
              <input value={code} onChange={(e) => setCode(e.target.value)} className="k-input w-full" data-testid="sd-rac-code" />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">Start date</label>
              <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="k-input w-full" />
            </div>
            <div>
              <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block">End date</label>
              <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="k-input w-full" />
            </div>
            <button onClick={search} disabled={loading} className="k-btn kazo-bg-burgundy text-white" data-testid="sd-rac-search">
              <Search className="w-3.5 h-3.5" /> {loading ? "…" : "Search"}
            </button>
          </div>
        </div>

        {rows !== null && (
          <div className="chart-card p-5 overflow-x-auto" data-accent="amber">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-display text-xl">Recent redemptions · {rows.length}</h3>
            </div>
            {rows.length === 0 ? (
              <div className="text-sm text-neutral-500 py-8 text-center">No redeemed coupons matched.</div>
            ) : (
              <table className="w-full text-sm" data-testid="sd-rac-results">
                <thead className="border-b border-black/10 text-left">
                  <tr>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">When</th>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Code</th>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Mobile</th>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Bill</th>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Discount</th>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Status</th>
                    <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={r.id || i} className="border-b border-black/5 hover:bg-amber-50/40">
                      <td className="py-2 px-2 text-xs text-neutral-600">{(r.redeemed_at || r.created_at || "").replace("T", " ").slice(0, 19)}</td>
                      <td className="py-2 px-2 font-mono"><span className="px-2 py-0.5 bg-amber-100 text-amber-900 rounded text-xs">{r.code}</span></td>
                      <td className="py-2 px-2 font-mono">{r.customer_mobile}</td>
                      <td className="py-2 px-2 font-mono text-xs">{r.bill_number || "—"}</td>
                      <td className="py-2 px-2 font-mono text-right">{fmtMoney2(r.discount_amount || r.value || 0)}</td>
                      <td className="py-2 px-2">
                        {r.reversed ? <Pill tone="danger">Reversed</Pill> : <Pill tone="success">Active</Pill>}
                      </td>
                      <td className="py-2 px-2">
                        <button
                          onClick={() => setConfirmRow(r)}
                          disabled={r.reversed}
                          className="text-xs px-3 py-1 border border-rose-300 text-rose-700 hover:bg-rose-50 disabled:opacity-30 disabled:cursor-not-allowed flex items-center gap-1"
                          data-testid={`sd-rac-reverse-${r.id}`}
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
        title="Reactivate coupon"
        description={confirmRow ? `Reverse redemption of ${confirmRow.code} for ${confirmRow.customer_mobile}? The coupon will become available for reuse.` : ""}
        confirmLabel="Reactivate"
        onConfirm={reactivate}
        onCancel={() => setConfirmRow(null)}
      />
    </div>
  );
}
