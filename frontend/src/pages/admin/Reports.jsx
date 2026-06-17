import { useEffect, useState } from "react";
import api, { API_URL } from "@/lib/api";
import { PageHeader } from "./_shared";
import { fmtMoney2, fmtNum, fmtDate } from "@/lib/format";
import { Download } from "lucide-react";
import TransactionDrillModal from "./_TransactionDrill";

export default function ReportsPage() {
  const [period, setPeriod] = useState(30);
  const [data, setData] = useState({ total: 0, items: [] });
  const [audit, setAudit] = useState([]);
  const [drillTxn, setDrillTxn] = useState(null);

  const load = async () => {
    const [t, a] = await Promise.all([api.get("/reports/transactions", { params: { period_days: period, limit: 100 } }), api.get("/reports/audit-logs", { params: { limit: 50 } })]);
    setData(t.data);
    setAudit(a.data);
  };
  useEffect(() => { load(); }, [period]);

  const exportCsv = (path) => {
    const url = `${API_URL}${path}`;
    const token = localStorage.getItem("kazo_token");
    fetch(url, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.blob()).then(b => {
      const u = URL.createObjectURL(b); const a = document.createElement("a"); a.href = u; a.download = "export.csv"; a.click(); URL.revokeObjectURL(u);
    });
  };

  return (
    <div data-testid="reports-page">
      <PageHeader title="Reports" subtitle="DATA EXPORTS · AUDIT"
        actions={
          <>
            <select className="k-input !w-auto !py-1.5" value={period} onChange={(e) => setPeriod(parseInt(e.target.value))} data-testid="reports-period">
              <option value={7}>7 days</option><option value={30}>30 days</option><option value={90}>90 days</option><option value={365}>365 days</option>
            </select>
            <button className="k-btn k-btn-outline k-btn-sm" onClick={() => exportCsv(`/reports/transactions/export?period_days=${period}`)} data-testid="export-txns-csv"><Download className="w-3.5 h-3.5" /> Transactions CSV</button>
            <button className="k-btn k-btn-outline k-btn-sm" onClick={() => exportCsv("/reports/customers/export")} data-testid="export-customers-csv"><Download className="w-3.5 h-3.5" /> Customers CSV</button>
          </>
        }
      />
      <div className="p-8 space-y-6">
        <div className="bg-white border border-black/10 p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500">TRANSACTIONS · {fmtNum(data.total)} TOTAL</div>
          </div>
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead><tr><th>Bill #</th><th>Date</th><th>Mobile</th><th>Store</th><th className="text-right">Gross</th><th className="text-right">Discount</th><th className="text-right">Net</th><th className="text-right">Points</th><th>Coupon</th></tr></thead>
              <tbody>
                {data.items.slice(0, 50).map((t) => (
                  <tr key={t.id} className="cursor-pointer hover:bg-neutral-50" onClick={() => setDrillTxn(t.id)} data-testid={`txn-row-${t.id}`}>
                    <td className="font-mono text-xs kazo-text-burgundy">{t.bill_number}</td>
                    <td className="text-xs">{fmtDate(t.bill_date)}</td>
                    <td className="font-mono text-xs">{t.customer_mobile}</td>
                    <td className="text-xs">{t.store_id?.slice(0, 8)}</td>
                    <td className="text-right font-mono">{fmtMoney2(t.gross_amount)}</td>
                    <td className="text-right font-mono text-red-600">{fmtMoney2(t.discount_amount)}</td>
                    <td className="text-right font-mono font-semibold">{fmtMoney2(t.net_amount)}</td>
                    <td className="text-right font-mono">{t.points_earned}</td>
                    <td className="text-xs">{t.coupon_code || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="bg-white border border-black/10 p-5">
          <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-3">AUDIT LOG</div>
          <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
            <table className="data-table">
              <thead><tr><th>Timestamp</th><th>User</th><th>Action</th><th>Entity</th><th>Entity ID</th></tr></thead>
              <tbody>
                {audit.map((a) => (
                  <tr key={a.id}>
                    <td className="text-xs">{fmtDate(a.timestamp)}</td>
                    <td className="text-xs">{a.user_email}</td>
                    <td><span className="pill pill-info">{a.action}</span></td>
                    <td>{a.entity}</td>
                    <td className="font-mono text-xs">{a.entity_id?.slice(0, 12)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
      <TransactionDrillModal txnId={drillTxn} onClose={() => setDrillTxn(null)} />
    </div>
  );
}
