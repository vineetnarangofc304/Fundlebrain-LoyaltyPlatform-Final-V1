/* Verify Load — one-glance reconciliation of the full historic data load.
   Confirms CRM / Billing / SKU all landed 100% before go-live: rows-in-file
   vs ingested vs skipped per dataset, plus live DB totals (customers, tiers,
   points liability, bills, SKU coverage, ledger breakdown). */
import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader, SectionHeading, KPICard, DashboardError } from "./_shared";
import { fmtDateTime } from "@/lib/format";
import {
  RefreshCw, CheckCircle2, AlertTriangle, Loader2, Users, Receipt,
  Coins, Package, Boxes, Layers,
} from "lucide-react";

const n = (v) => (v == null ? "—" : Number(v).toLocaleString("en-IN"));
const inr = (v) => (v == null ? "—" : "₹" + Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 }));

const DATASET_LABEL = {
  customers: "Customers (CRM)",
  transactions: "Bills (Billing)",
  sku_transactions: "SKU / Line items",
  stores: "Stores",
  items: "Items master",
  points_ledger: "Points ledger",
};

function VerdictBanner({ allBalanced, issues, generatedAt }) {
  if (allBalanced) {
    return (
      <div data-testid="vl-verdict" className="flex items-start gap-3 border border-emerald-200 bg-emerald-50/70 px-5 py-4 rounded-sm">
        <CheckCircle2 className="w-6 h-6 text-emerald-600 shrink-0 mt-0.5" />
        <div>
          <div className="font-display text-lg text-emerald-900">All data reconciled — load looks complete ✓</div>
          <div className="text-sm text-emerald-800/80">Every dataset's latest upload balances and the database snapshot is populated. Checked {generatedAt ? fmtDateTime(generatedAt) : "just now"}.</div>
        </div>
      </div>
    );
  }
  return (
    <div data-testid="vl-verdict" className="flex items-start gap-3 border border-amber-300 bg-amber-50/70 px-5 py-4 rounded-sm">
      <AlertTriangle className="w-6 h-6 text-amber-600 shrink-0 mt-0.5" />
      <div className="min-w-0">
        <div className="font-display text-lg text-amber-900">{issues.length} item{issues.length > 1 ? "s" : ""} need attention before go-live</div>
        <ul className="mt-1 space-y-1 text-sm text-amber-900/90 list-disc pl-5">
          {issues.map((it, i) => <li key={i} data-testid={`vl-issue-${i}`}>{it}</li>)}
        </ul>
      </div>
    </div>
  );
}

function ReconRow({ row }) {
  const ok = row.balanced;
  return (
    <tr className="border-b border-black/5 hover:bg-neutral-50" data-testid={`vl-job-row-${row.dataset}`}>
      <td className="py-2.5 px-3">
        <div className="font-medium text-neutral-900">{DATASET_LABEL[row.dataset] || row.dataset}</div>
        <div className="text-xs text-neutral-500 truncate max-w-[220px]" title={row.filename}>{row.filename || "—"}</div>
      </td>
      <td className="py-2.5 px-3 text-right font-mono tabular-nums">{n(row.csv_rows)}</td>
      <td className="py-2.5 px-3 text-right font-mono tabular-nums text-emerald-700">{n(row.inserted)}</td>
      <td className="py-2.5 px-3 text-right font-mono tabular-nums text-indigo-700">{n(row.updated)}</td>
      <td className="py-2.5 px-3 text-right font-mono tabular-nums text-rose-700">{n(row.skipped)}</td>
      <td className="py-2.5 px-3 text-right font-mono tabular-nums">{row.diff > 0 ? `+${n(row.diff)}` : n(row.diff)}</td>
      <td className="py-2.5 px-3 text-center">
        {ok
          ? <span className="pill pill-success" data-testid={`vl-balanced-${row.dataset}`}>balanced</span>
          : <span className="pill pill-warning" data-testid={`vl-unbalanced-${row.dataset}`}>check</span>}
      </td>
      <td className="py-2.5 px-3 text-xs text-neutral-500 whitespace-nowrap">{row.completed_at ? fmtDateTime(row.completed_at) : "—"}</td>
    </tr>
  );
}

export default function VerifyLoadPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await api.get("/historic-data/verify-load");
      setData(r.data);
    } catch (e) {
      setError(e?.response?.data?.detail || e.message || "Failed to load reconciliation");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (error && !data) {
    return (
      <div data-testid="verify-load-page">
        <PageHeader title="Verify Load" subtitle="Data · Reconciliation" />
        <DashboardError error={error} onRetry={load} title="the load reconciliation" />
      </div>
    );
  }

  const db = data?.db || {};
  // Order the per-dataset recon by the canonical load sequence
  const order = ["customers", "transactions", "sku_transactions", "items", "stores", "points_ledger"];
  const latest = data?.latest_by_dataset || {};
  const reconRows = order.filter((d) => latest[d]).map((d) => latest[d]);

  return (
    <div data-testid="verify-load-page">
      <PageHeader
        title="Verify Load"
        subtitle="Data · Reconciliation"
        actions={
          <button className="k-btn k-btn-outline" onClick={load} disabled={loading} data-testid="vl-refresh">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            <span className="ml-1.5">Refresh</span>
          </button>
        }
      />

      <div className="p-8 space-y-8">
        {data && (
          <VerdictBanner allBalanced={data.all_balanced} issues={data.issues || []} generatedAt={data.generated_at} />
        )}

        {/* Live DB snapshot KPIs */}
        <section>
          <SectionHeading eyebrow="Live database snapshot" title="What actually landed" accent="indigo" />
          <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
            <KPICard testid="vl-kpi-customers" label="Loyalty customers" value={n(db.loyalty_customers)} hint={`${n(db.customers_total)} total rows`} accent="burgundy" fullValue={db.loyalty_customers} />
            <KPICard testid="vl-kpi-bills" label="Bills ingested" value={n(db.transactions_total)} hint={`${n(db.loyalty_bills)} loyalty`} accent="indigo" fullValue={db.transactions_total} />
            <KPICard testid="vl-kpi-liability" label="Points liability" value={inr(db.outstanding_liability_inr)} hint={`${n(db.outstanding_points)} pts @ ₹${db.burn_ratio_inr_per_point}`} accent="amber" fullValue={db.outstanding_liability_inr} />
            <KPICard testid="vl-kpi-sku-coverage" label="SKU coverage" value={db.sku_coverage_pct != null ? `${db.sku_coverage_pct}%` : "—"} hint={`${n(db.bills_with_items)} bills w/ items`} accent="teal" fullValue={db.sku_coverage_pct} />
            <KPICard testid="vl-kpi-units" label="Units (UPT base)" value={n(db.total_units)} hint="sum of line-item qty" accent="rose" fullValue={db.total_units} />
            <KPICard testid="vl-kpi-items" label="Items master" value={n(db.items_master)} hint="distinct SKUs" accent="slate" fullValue={db.items_master} />
          </div>
        </section>

        {/* Per-dataset reconciliation */}
        <section>
          <SectionHeading eyebrow="File vs database" title="Reconciliation by dataset (latest upload)" accent="burgundy" />
          <div className="border border-black/10 bg-white overflow-x-auto rounded-sm">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wider text-neutral-500 border-b border-black/10 bg-neutral-50">
                  <th className="py-2.5 px-3">Dataset / File</th>
                  <th className="py-2.5 px-3 text-right">Rows in file</th>
                  <th className="py-2.5 px-3 text-right">New</th>
                  <th className="py-2.5 px-3 text-right">Updated</th>
                  <th className="py-2.5 px-3 text-right">Skipped</th>
                  <th className="py-2.5 px-3 text-right">Diff</th>
                  <th className="py-2.5 px-3 text-center">Status</th>
                  <th className="py-2.5 px-3">Completed</th>
                </tr>
              </thead>
              <tbody>
                {reconRows.length === 0 && (
                  <tr><td colSpan={8} className="py-8 text-center text-neutral-400" data-testid="vl-no-jobs">No completed ingest jobs yet.</td></tr>
                )}
                {reconRows.map((row) => <ReconRow key={row.job_id} row={row} />)}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-neutral-500">Diff = rows in file − (new + updated + skipped). “Updated” counts existing records touched on re-upload. Download skipped rows from the Historical Upload page to see exactly which rows didn’t match.</p>
        </section>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Tier distribution */}
          <section>
            <SectionHeading eyebrow="Loyalty" title="Tier distribution" accent="amber" />
            <div className="border border-black/10 bg-white rounded-sm">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wider text-neutral-500 border-b border-black/10 bg-neutral-50">
                    <th className="py-2.5 px-3">Tier</th>
                    <th className="py-2.5 px-3 text-right">Customers</th>
                    <th className="py-2.5 px-3 text-right">Points held</th>
                  </tr>
                </thead>
                <tbody>
                  {(db.tier_distribution || []).length === 0 && (
                    <tr><td colSpan={3} className="py-6 text-center text-neutral-400">No customers loaded.</td></tr>
                  )}
                  {(db.tier_distribution || []).map((t) => (
                    <tr key={t.tier} className="border-b border-black/5" data-testid={`vl-tier-row-${t.tier}`}>
                      <td className="py-2.5 px-3 capitalize font-medium">{t.tier}</td>
                      <td className="py-2.5 px-3 text-right font-mono tabular-nums">{n(t.count)}</td>
                      <td className="py-2.5 px-3 text-right font-mono tabular-nums text-neutral-600">{n(t.points)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {/* Ledger breakdown */}
          <section>
            <SectionHeading eyebrow="Points economics" title="Ledger entries by type" accent="teal" />
            <div className="border border-black/10 bg-white rounded-sm">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wider text-neutral-500 border-b border-black/10 bg-neutral-50">
                    <th className="py-2.5 px-3">Type</th>
                    <th className="py-2.5 px-3 text-right">Entries</th>
                    <th className="py-2.5 px-3 text-right">Net points</th>
                  </tr>
                </thead>
                <tbody>
                  {(db.ledger_by_type || []).length === 0 && (
                    <tr><td colSpan={3} className="py-6 text-center text-neutral-400">No ledger entries.</td></tr>
                  )}
                  {(db.ledger_by_type || []).map((l) => (
                    <tr key={l.type} className="border-b border-black/5" data-testid={`vl-ledger-row-${l.type}`}>
                      <td className="py-2.5 px-3 capitalize font-medium">{l.type}</td>
                      <td className="py-2.5 px-3 text-right font-mono tabular-nums">{n(l.count)}</td>
                      <td className={`py-2.5 px-3 text-right font-mono tabular-nums ${l.points < 0 ? "text-rose-700" : "text-emerald-700"}`}>{l.points > 0 ? `+${n(l.points)}` : n(l.points)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
