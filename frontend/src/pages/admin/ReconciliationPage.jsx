import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { ShieldCheck, AlertTriangle, CheckCircle2, RefreshCw, Coins, Users } from "lucide-react";
import { PageHeader, SectionHeading, KPICard } from "./_shared";
import CsvReconSection from "./recon/CsvReconSection";
import LoadedFilesSection from "./recon/LoadedFilesSection";

const fmtMoney2 = (v) => v == null ? "—" : `₹${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
const fmtNum = (v) => v == null ? "—" : Number(v).toLocaleString("en-IN");

export default function ReconciliationPage() {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState({});

  const fetchReport = async () => {
    setLoading(true);
    try {
      const r = await api.get("/historic-data/reconcile");
      setReport(r.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load reconciliation");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { /* heavy integrity report is loaded on demand to keep the page responsive */ }, []);

  const runAction = async (key, url, label) => {
    setRunning((s) => ({ ...s, [key]: true }));
    try {
      const r = await api.post(url);
      toast.success(`${label} complete`);
      console.info(label, r.data);
      // Refresh report
      await fetchReport();
    } catch (e) {
      toast.error(e.response?.data?.detail || `${label} failed`);
    } finally {
      setRunning((s) => ({ ...s, [key]: false }));
    }
  };

  const status = report?.status;
  const clean = status === "clean";

  return (
    <div data-testid="reconciliation-page">
      <PageHeader
        title="Data Reconciliation"
        subtitle="CSV ↔ DATABASE INTEGRITY · BILL-DATE TRUTH"
        actions={
          <button onClick={fetchReport} className="k-btn flex items-center gap-2" disabled={loading} data-testid="recon-refresh">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> {loading ? "Checking…" : "Recheck"}
          </button>
        }
      />
      <div className="p-4 md:p-8 space-y-6">
        {/* All files loaded — fast, always visible (answers "what did we load and did it land") */}
        <LoadedFilesSection />

        {/* CSV ↔ DB row-level reconciliation (re-upload a source CSV) */}
        <CsvReconSection />

        {/* Heavy DB-wide integrity report — loaded on demand so the page never hangs */}
        {!report && !loading && (
          <div className="chart-card p-5 flex items-center justify-between gap-3" data-accent="slate" data-testid="run-integrity-prompt">
            <div>
              <SectionHeading eyebrow="FULL INTEGRITY REPORT" title="DB-wide reconciliation (heavy)" accent="slate" />
              <p className="text-xs text-neutral-500 mt-1">Scans the whole database (sums, ledger coverage, orphans, duplicates). Can take up to a minute at full scale, so it runs only when you ask.</p>
            </div>
            <button onClick={fetchReport} className="k-btn kazo-bg-burgundy text-white shrink-0" data-testid="run-integrity-btn">
              <ShieldCheck className="w-4 h-4" /> Run full report
            </button>
          </div>
        )}
        {!report && loading && <div className="text-neutral-500" data-testid="integrity-running">Running full integrity report… this can take up to a minute.</div>}

        {report && (
          <>
            {/* Status banner */}
            <div
              className={`flex items-start gap-3 p-4 rounded-lg border ${
                clean
                  ? "bg-emerald-50 border-emerald-200 text-emerald-900"
                  : "bg-amber-50 border-amber-200 text-amber-900"
              }`}
              data-testid="recon-status"
            >
              {clean ? <CheckCircle2 className="w-5 h-5 mt-0.5" /> : <AlertTriangle className="w-5 h-5 mt-0.5" />}
              <div className="flex-1">
                <div className="font-medium text-sm uppercase tracking-widest mb-1">
                  {clean ? "Clean — all integrity checks passed" : `Issues found (${report.issues.length})`}
                </div>
                {!clean && (
                  <ul className="text-sm space-y-0.5 list-disc list-inside">
                    {report.issues.map((iss, i) => <li key={i} data-testid={`recon-issue-${i}`}>{iss}</li>)}
                  </ul>
                )}
                <div className="text-xs opacity-70 mt-2">Checked at {new Date(report.checked_at).toLocaleString()}</div>
              </div>
            </div>

            {/* Last ingest job */}
            <div className="chart-card p-5" data-accent="indigo">
              <SectionHeading eyebrow="LAST INGEST JOB" title="CSV vs Processed reconciliation" accent="indigo" />
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mt-4">
                <KPICard label="CSV rows" value={fmtNum(report.job_summary.csv_total_rows)} accent="indigo" testid="kpi-csv-rows" />
                <KPICard label="Inserted" value={fmtNum(report.job_summary.inserted)} accent="teal" testid="kpi-inserted" />
                <KPICard label="Updated" value={fmtNum(report.job_summary.updated)} accent="slate" testid="kpi-updated" />
                <KPICard label="Skipped" value={fmtNum(report.job_summary.skipped)} accent={report.job_summary.skipped ? "burgundy" : "slate"} testid="kpi-skipped" />
                <KPICard label="Diff (CSV − processed)" value={fmtNum(report.job_summary.diff)} accent={report.job_summary.match ? "teal" : "burgundy"} testid="kpi-diff" />
              </div>
              <div className="text-xs text-neutral-500 mt-3">
                Job ID <code>{report.job_summary.job_id}</code> · Completed {report.job_summary.completed_at ? new Date(report.job_summary.completed_at).toLocaleString() : "—"}
              </div>
            </div>

            {/* DB state */}
            <div className="chart-card p-5" data-accent="burgundy">
              <SectionHeading eyebrow="DATABASE STATE" title="Live MongoDB counts" accent="burgundy" />
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
                <KPICard label="Transactions · total" value={fmtNum(report.db_state.transactions_total)} accent="burgundy" testid="kpi-txn-total" />
                <KPICard label="Loyalty bills (w/ mobile)" value={fmtNum(report.db_state.transactions_loyalty)} accent="teal" testid="kpi-txn-loyalty" />
                <KPICard label="Non-loyalty bills" value={fmtNum(report.db_state.transactions_non_loyalty)} accent="slate" testid="kpi-txn-nonloyalty" />
                <KPICard label="Stores" value={fmtNum(report.db_state.stores_total)} accent="indigo" testid="kpi-stores" />
                <KPICard label="Customers · total" value={fmtNum(report.db_state.customers_total)} accent="indigo" testid="kpi-cust-total" />
                <KPICard label="With home store" value={fmtNum(report.db_state.customers_with_home_store)} accent="teal" testid="kpi-cust-home" />
                <KPICard label="With first_purchase_at" value={fmtNum(report.db_state.customers_with_first_purchase)} accent="teal" testid="kpi-cust-first" />
                <KPICard label="Distinct mobiles in txns" value={fmtNum(report.db_state.distinct_mobiles_in_txns)} accent="slate" testid="kpi-distinct-mob" />
              </div>
            </div>

            {/* Sums */}
            <div className="chart-card p-5" data-accent="teal">
              <SectionHeading eyebrow="MONETARY + POINTS SUMS" title="Loyalty bills · txn columns vs ledger" accent="teal" />
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mt-4">
                <KPICard label="Net amount (loyalty)" value={fmtMoney2(report.sums.net_amount_loyalty)} accent="burgundy" testid="sum-net" />
                <KPICard label="Tax (loyalty)" value={fmtMoney2(report.sums.tax_loyalty)} accent="slate" testid="sum-tax" />
                <KPICard label="Discount (loyalty)" value={fmtMoney2(report.sums.discount_loyalty)} accent="slate" testid="sum-discount" />
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mt-4">
                <KPICard label="Earn (txn col)" value={fmtNum(report.sums.points_earned_from_txns)} accent="teal" testid="sum-earn-txn" />
                <KPICard label="Earn (ledger)" value={fmtNum(report.sums.ledger_earn_total)} accent="teal" testid="sum-earn-ledger" />
                <KPICard label="Δ ledger − txns" value={fmtNum(report.sums.ledger_vs_txns_earn_diff)} accent={report.sums.ledger_vs_txns_earn_diff ? "burgundy" : "teal"} testid="sum-earn-diff" />
                <KPICard label="Redeem (txn col)" value={fmtNum(report.sums.points_redeemed_from_txns)} accent="indigo" testid="sum-redeem-txn" />
                <KPICard label="Redeem (ledger)" value={fmtNum(report.sums.ledger_redeem_total)} accent="indigo" testid="sum-redeem-ledger" />
                <KPICard label="Δ ledger − txns" value={fmtNum(report.sums.ledger_vs_txns_redeem_diff)} accent={report.sums.ledger_vs_txns_redeem_diff ? "burgundy" : "teal"} testid="sum-redeem-diff" />
              </div>
            </div>

            {/* Integrity */}
            <div className="chart-card p-5" data-accent="slate">
              <SectionHeading eyebrow="INTEGRITY CHECKS" title="Orphans · duplicates · ledger coverage" accent="slate" />
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
                <KPICard label="Txns missing store_id" value={fmtNum(report.integrity.orphan_store_txns)} accent={report.integrity.orphan_store_txns ? "burgundy" : "teal"} testid="int-orphan-store" />
                <KPICard label="Mobiles missing customer doc" value={fmtNum(report.integrity.loyalty_mobiles_missing_customer_doc)} accent={report.integrity.loyalty_mobiles_missing_customer_doc ? "burgundy" : "teal"} testid="int-missing-cust" />
                <KPICard label="Duplicate mobile customers" value={fmtNum(report.integrity.duplicate_mobile_customers)} accent={report.integrity.duplicate_mobile_customers ? "burgundy" : "teal"} testid="int-dup-mob" />
                <KPICard label="Ledger coverage" value={`${report.integrity.ledger_coverage_loyalty_bills_pct}%`} accent={report.integrity.ledger_coverage_loyalty_bills_pct >= 95 ? "teal" : "burgundy"} testid="int-ledger-cov" />
              </div>
            </div>

            {/* Repair toolbox */}
            <div className="chart-card p-5" data-accent="indigo">
              <SectionHeading eyebrow="REPAIR TOOLBOX" title="One-shot, idempotent fixes" accent="indigo" />
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-4">
                <button
                  type="button"
                  className="text-left p-4 border border-neutral-200 rounded-lg hover:border-neutral-900 hover:bg-neutral-50 transition disabled:opacity-50 disabled:cursor-not-allowed"
                  onClick={() => runAction("loyalty", "/historic-data/backfill-loyalty-model", "Loyalty backfill")}
                  disabled={!!running.loyalty}
                  data-testid="btn-backfill-loyalty"
                >
                  <div className="font-medium text-sm flex items-center gap-2 mb-1"><ShieldCheck className="w-4 h-4" /> Loyalty Backfill</div>
                  <div className="text-xs text-neutral-500">R1+R2+R3+R4 · home_store_id, first_purchase_at, visit_count, unique indices</div>
                  {running.loyalty && <div className="text-xs text-indigo-700 mt-2">Running…</div>}
                </button>

                <button
                  type="button"
                  className="text-left p-4 border border-neutral-200 rounded-lg hover:border-neutral-900 hover:bg-neutral-50 transition disabled:opacity-50 disabled:cursor-not-allowed"
                  onClick={() => runAction("ledger", "/historic-data/backfill-points-ledger", "Points ledger backfill")}
                  disabled={!!running.ledger}
                  data-testid="btn-backfill-ledger"
                >
                  <div className="font-medium text-sm flex items-center gap-2 mb-1"><Coins className="w-4 h-4" /> Points Ledger Backfill</div>
                  <div className="text-xs text-neutral-500">R6 · write earn / redeem / bonus entries for any loyalty bill that doesn't yet have them</div>
                  {running.ledger && <div className="text-xs text-indigo-700 mt-2">Running…</div>}
                </button>

                <button
                  type="button"
                  className="text-left p-4 border border-neutral-200 rounded-lg hover:border-neutral-900 hover:bg-neutral-50 transition disabled:opacity-50 disabled:cursor-not-allowed"
                  onClick={async () => {
                    setRunning((s) => ({ ...s, dedupe: true }));
                    try {
                      const r = await api.get("/historic-data/dedupe/mobiles");
                      const n = r.data.duplicate_mobiles;
                      if (!n) toast.success("No duplicate mobiles in customers");
                      else toast.warning(`${n} duplicate mobile groups — see console`);
                      console.warn("Dedupe report", r.data);
                    } catch (e) {
                      toast.error(e.response?.data?.detail || "Dedupe failed");
                    } finally {
                      setRunning((s) => ({ ...s, dedupe: false }));
                    }
                  }}
                  disabled={!!running.dedupe}
                  data-testid="btn-dedupe"
                >
                  <div className="font-medium text-sm flex items-center gap-2 mb-1"><Users className="w-4 h-4" /> Dedupe Report</div>
                  <div className="text-xs text-neutral-500">R4 · surface any non-empty mobile held by more than one customer doc</div>
                  {running.dedupe && <div className="text-xs text-indigo-700 mt-2">Scanning…</div>}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
