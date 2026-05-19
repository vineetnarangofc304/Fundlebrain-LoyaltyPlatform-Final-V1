import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import api from "@/lib/api";
import { PageHeader, KPICard } from "./_shared";
import { fmtINR, fmtNum, fmtDate, fmtDateTime, tierClass } from "@/lib/format";
import { toast } from "sonner";
import { ArrowLeft, Plus, Minus, Gift, MessageSquare } from "lucide-react";

export default function CustomerDetail() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  const [pointsModal, setPointsModal] = useState(null); // 'award' | 'deduct' | null
  const [pointsAmt, setPointsAmt] = useState(0);
  const [note, setNote] = useState("");

  const load = async () => {
    const r = await api.get(`/customers/${id}`);
    setData(r.data);
  };
  useEffect(() => { load(); }, [id]);

  const doPoints = async () => {
    try {
      const path = pointsModal === "award" ? "award-points" : "deduct-points";
      await api.post(`/customers/${id}/${path}`, null, { params: { points: pointsAmt, note } });
      toast.success(`${pointsModal === "award" ? "Awarded" : "Deducted"} ${pointsAmt} points`);
      setPointsModal(null); setPointsAmt(0); setNote("");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  if (!data) return <div className="p-10 text-neutral-500">Loading…</div>;
  const c = data.customer;

  return (
    <div data-testid="customer-detail-page">
      <PageHeader
        title={c.name || c.mobile}
        subtitle="CUSTOMER PROFILE · 360°"
        actions={<Link to="/admin/customers" className="k-btn k-btn-outline k-btn-sm"><ArrowLeft className="w-3.5 h-3.5" /> Back</Link>}
      />
      <div className="p-8 space-y-6">
        {/* Hero */}
        <div className="bg-white border border-black/10 p-6 grid lg:grid-cols-[2fr_3fr] gap-6">
          <div>
            <div className="flex items-center gap-3 mb-3">
              <span className={tierClass(c.tier)}>{c.tier?.toUpperCase()}</span>
              <span className={`pill pill-${c.churn_risk === "high" ? "danger" : c.churn_risk === "medium" ? "warning" : "success"}`}>{c.churn_risk} risk</span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div className="text-neutral-500">Mobile</div><div className="font-mono">{c.mobile}</div>
              <div className="text-neutral-500">Email</div><div className="font-mono text-xs">{c.email || "—"}</div>
              <div className="text-neutral-500">City</div><div>{c.city || "—"}</div>
              <div className="text-neutral-500">Birthday</div><div>{c.birthday || "—"}</div>
              <div className="text-neutral-500">First purchase</div><div>{fmtDate(c.first_purchase_at)}</div>
              <div className="text-neutral-500">Last visit</div><div>{fmtDate(c.last_visit_at)}</div>
            </div>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KPICard label="Points Balance" value={fmtNum(c.points_balance)} testid="cust-points" />
            <KPICard label="Lifetime Spend" value={fmtINR(c.lifetime_spend)} testid="cust-lts" />
            <KPICard label="Visits" value={fmtNum(c.visit_count)} testid="cust-visits" />
            <KPICard label="Earned ▸ Redeemed" value={`${fmtNum(c.lifetime_points_earned)} / ${fmtNum(c.lifetime_points_redeemed)}`} testid="cust-loyalty" />
          </div>
        </div>

        {/* Actions */}
        <div className="flex flex-wrap gap-2">
          <button className="k-btn k-btn-outline k-btn-sm" onClick={() => setPointsModal("award")} data-testid="award-points-btn"><Plus className="w-3.5 h-3.5" /> Award points</button>
          <button className="k-btn k-btn-outline k-btn-sm" onClick={() => setPointsModal("deduct")} data-testid="deduct-points-btn"><Minus className="w-3.5 h-3.5" /> Deduct points</button>
          <button className="k-btn k-btn-outline k-btn-sm"><Gift className="w-3.5 h-3.5" /> Issue coupon</button>
          <button className="k-btn k-btn-outline k-btn-sm"><MessageSquare className="w-3.5 h-3.5" /> Raise ticket</button>
        </div>

        {/* Side-by-side info */}
        <div className="grid lg:grid-cols-2 gap-4">
          <div className="bg-white border border-black/10 p-5">
            <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-3">FAVOURITE CATEGORIES</div>
            <div className="space-y-2">
              {data.favourite_categories.map((c) => (
                <div key={c.category} className="flex items-center justify-between border-b border-black/5 pb-2">
                  <span className="pill pill-neutral">{c.category}</span>
                  <div className="text-sm font-mono">{fmtINR(c.spend)} · {c.qty} units</div>
                </div>
              ))}
              {data.favourite_categories.length === 0 && <div className="text-sm text-neutral-500">N/A</div>}
            </div>
          </div>

          <div className="bg-white border border-black/10 p-5">
            <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-3">FAVOURITE PRODUCTS</div>
            <div className="space-y-2">
              {data.favourite_products.map((p) => (
                <div key={p.sku} className="flex items-center justify-between border-b border-black/5 pb-2">
                  <div>
                    <div className="text-sm font-medium">{p.name}</div>
                    <div className="text-xs text-neutral-500 font-mono">{p.sku}</div>
                  </div>
                  <div className="text-sm font-mono">{fmtINR(p.spend)} · {p.qty}</div>
                </div>
              ))}
              {data.favourite_products.length === 0 && <div className="text-sm text-neutral-500">N/A</div>}
            </div>
          </div>
        </div>

        {/* Transactions */}
        <div className="bg-white border border-black/10 p-5">
          <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-3">TRANSACTIONS</div>
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead><tr><th>Bill #</th><th>Date</th><th className="text-right">Gross</th><th className="text-right">Net</th><th className="text-right">Points</th><th>Payment</th><th>Coupon</th></tr></thead>
              <tbody>
                {data.transactions.map((t) => (
                  <tr key={t.id}>
                    <td className="font-mono text-xs">{t.bill_number}</td>
                    <td className="text-xs">{fmtDate(t.bill_date)}</td>
                    <td className="text-right font-mono">{fmtINR(t.gross_amount)}</td>
                    <td className="text-right font-mono">{fmtINR(t.net_amount)}</td>
                    <td className="text-right font-mono">+{t.points_earned}</td>
                    <td><span className="pill pill-neutral">{t.payment_mode}</span></td>
                    <td className="text-xs">{t.coupon_code || "—"}</td>
                  </tr>
                ))}
                {data.transactions.length === 0 && <tr><td colSpan={7} className="text-center py-6 text-neutral-500">No transactions</td></tr>}
              </tbody>
            </table>
          </div>
        </div>

        {/* Points ledger */}
        <div className="grid lg:grid-cols-2 gap-4">
          <div className="bg-white border border-black/10 p-5">
            <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-3">POINTS LEDGER</div>
            <div className="space-y-2 max-h-[400px] overflow-y-auto">
              {data.points_ledger.map((l) => (
                <div key={l.id} className="flex items-center justify-between border-b border-black/5 pb-2 text-sm">
                  <div>
                    <div className="font-medium">{l.type.toUpperCase()}</div>
                    <div className="text-xs text-neutral-500">{fmtDateTime(l.created_at)} · {l.note || l.reference_type}</div>
                  </div>
                  <div className={`font-mono ${l.points >= 0 ? "text-green-600" : "text-red-600"}`}>
                    {l.points >= 0 ? "+" : ""}{l.points}
                  </div>
                </div>
              ))}
              {data.points_ledger.length === 0 && <div className="text-sm text-neutral-500">No ledger entries</div>}
            </div>
          </div>

          <div className="bg-white border border-black/10 p-5">
            <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-3">SUPPORT & FEEDBACK</div>
            <div className="space-y-3">
              <div>
                <div className="text-xs uppercase text-neutral-500 mb-1">Tickets</div>
                {data.tickets.length === 0 ? <div className="text-sm text-neutral-500">No tickets</div> :
                  data.tickets.slice(0, 5).map((t) => (
                    <div key={t.id} className="text-sm border-b border-black/5 py-1.5">
                      <div className="font-medium">{t.subject}</div>
                      <div className="text-xs text-neutral-500">{t.status} · {fmtDate(t.created_at)}</div>
                    </div>
                  ))
                }
              </div>
              <div>
                <div className="text-xs uppercase text-neutral-500 mb-1 mt-3">NPS Responses</div>
                {data.nps_responses.length === 0 ? <div className="text-sm text-neutral-500">N/A</div> :
                  data.nps_responses.slice(0, 5).map((n) => (
                    <div key={n.id} className="text-sm border-b border-black/5 py-1.5 flex justify-between">
                      <div>
                        <div className="font-medium">{n.sentiment} ({n.score}/10)</div>
                        <div className="text-xs text-neutral-500">{n.feedback || "—"}</div>
                      </div>
                      <div className="text-xs text-neutral-400">{fmtDate(n.created_at)}</div>
                    </div>
                  ))
                }
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Points Modal */}
      {pointsModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setPointsModal(null)}>
          <div className="bg-white p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()} data-testid="points-modal">
            <h3 className="font-display text-2xl mb-4">{pointsModal === "award" ? "Award" : "Deduct"} Points</h3>
            <div className="space-y-3">
              <input type="number" placeholder="Points amount" className="k-input" value={pointsAmt} onChange={(e) => setPointsAmt(parseInt(e.target.value) || 0)} data-testid="points-amount-input" />
              <input placeholder="Note (optional)" className="k-input" value={note} onChange={(e) => setNote(e.target.value)} data-testid="points-note-input" />
              <div className="flex gap-2 justify-end">
                <button className="k-btn k-btn-ghost" onClick={() => setPointsModal(null)}>Cancel</button>
                <button className="k-btn kazo-bg-burgundy" onClick={doPoints} data-testid="points-confirm-btn">Confirm</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
