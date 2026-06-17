// Reusable transaction detail modal
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { fmtMoney2, fmtDate, fmtDateTime, tierClass } from "@/lib/format";
import { X, ExternalLink } from "lucide-react";
import { Link } from "react-router-dom";

export default function TransactionDrillModal({ txnId, onClose }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    if (!txnId) return;
    api.get(`/analytics/transaction/${txnId}`).then((r) => setData(r.data));
  }, [txnId]);
  if (!txnId) return null;
  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white w-full max-w-3xl max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()} data-testid="txn-drill-modal">
        <div className="p-5 border-b border-black/10 flex items-center justify-between">
          <div>
            <div className="text-[11px] uppercase tracking-widest text-neutral-500">TRANSACTION DETAIL</div>
            <h3 className="font-display text-2xl">{data?.transaction?.bill_number || "Loading…"}</h3>
          </div>
          <button onClick={onClose} className="text-neutral-500 hover:text-black" data-testid="close-txn-modal"><X className="w-5 h-5" /></button>
        </div>
        {data && (
          <div className="p-5 space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
              <Stat label="Bill Date" value={fmtDateTime(data.transaction.bill_date)} />
              <Stat label="Gross" value={fmtMoney2(data.transaction.gross_amount)} />
              <Stat label="Discount" value={fmtMoney2(data.transaction.discount_amount)} />
              <Stat label="Net" value={fmtMoney2(data.transaction.net_amount)} accent />
              <Stat label="Points Earned" value={`+${data.transaction.points_earned}`} />
              <Stat label="Payment" value={data.transaction.payment_mode} />
              <Stat label="Coupon" value={data.transaction.coupon_code || "—"} />
              <Stat label="Items" value={data.transaction.items?.length || 0} />
            </div>

            {data.customer && (
              <div className="bg-neutral-50 border border-black/10 p-4">
                <div className="text-[11px] uppercase tracking-widest text-neutral-500 mb-2">CUSTOMER</div>
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium">{data.customer.name || data.customer.mobile}</div>
                    <div className="text-xs text-neutral-500 font-mono">{data.customer.mobile} · {data.customer.city}</div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={tierClass(data.customer.tier)}>{data.customer.tier?.toUpperCase()}</span>
                    <Link to={`/admin/customers/${data.customer.id}`} className="text-xs kazo-text-burgundy font-medium hover:underline flex items-center gap-1" onClick={onClose}>
                      Open profile <ExternalLink className="w-3 h-3" />
                    </Link>
                  </div>
                </div>
              </div>
            )}

            {data.store && (
              <div className="bg-neutral-50 border border-black/10 p-4">
                <div className="text-[11px] uppercase tracking-widest text-neutral-500 mb-2">STORE</div>
                <div className="font-medium">{data.store.name}</div>
                <div className="text-xs text-neutral-500">{data.store.code} · {data.store.address}</div>
              </div>
            )}

            <div>
              <div className="text-[11px] uppercase tracking-widest text-neutral-500 mb-2">LINE ITEMS</div>
              <table className="data-table">
                <thead><tr><th>SKU</th><th>Item</th><th>Category</th><th className="text-right">Qty</th><th className="text-right">Unit ₹</th><th className="text-right">Total</th></tr></thead>
                <tbody>
                  {data.transaction.items?.map((it, i) => (
                    <tr key={i}>
                      <td className="font-mono text-xs">{it.sku}</td>
                      <td>{it.name}</td>
                      <td><span className="pill pill-neutral">{it.category}</span></td>
                      <td className="text-right font-mono">{it.quantity}</td>
                      <td className="text-right font-mono">{fmtMoney2(it.unit_price)}</td>
                      <td className="text-right font-mono">{fmtMoney2(it.total)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, accent }) {
  return (
    <div className="border border-black/10 p-3">
      <div className="text-[10px] uppercase tracking-widest text-neutral-500 mb-1">{label}</div>
      <div className={`font-mono text-base ${accent ? "kazo-text-burgundy font-semibold" : ""}`}>{value}</div>
    </div>
  );
}
