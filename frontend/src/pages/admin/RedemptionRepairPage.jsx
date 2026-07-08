import { useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import {
  ShieldAlert, RefreshCw, AlertTriangle, CheckCircle2, Wrench, Undo2, Search,
} from "lucide-react";
import { PageHeader, SectionHeading, KPICard } from "./_shared";

const fmtNum = (v) => (v == null ? "—" : Number(v).toLocaleString("en-IN"));

export default function RedemptionRepairPage() {
  const [audit, setAudit] = useState(null);
  const [loading, setLoading] = useState(false);
  // fix flow: { scope: "all" | mobile, preview, reason, applying, result }
  const [fix, setFix] = useState(null);
  const [undoing, setUndoing] = useState(false);

  const runAudit = async () => {
    setLoading(true);
    try {
      const r = await api.get("/master-brain/redemption-repair/audit", { params: { sample_limit: 200 } });
      setAudit(r.data);
      if (r.data?.computed === false) toast.warning("Scan is under load — please retry in a few seconds.");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to run audit");
    } finally {
      setLoading(false);
    }
  };

  // Step 1 — preview (confirm=false). scope = "all" or a mobile string.
  const startFix = async (scope) => {
    const mobile = scope === "all" ? "" : scope;
    setFix({ scope, preview: null, reason: "", applying: false, result: null });
    try {
      const r = await api.post("/master-brain/redemption-repair/fix", { mobile, confirm: false });
      if (!r.data?.preview && !r.data?.live_bills_to_fix) {
        toast.info(r.data?.message || "Nothing to fix for this scope.");
        setFix(null);
        return;
      }
      setFix((f) => ({ ...f, preview: r.data }));
    } catch (e) {
      toast.error(e.response?.data?.detail || "Preview failed");
      setFix(null);
    }
  };

  // Step 2 — apply (confirm=true + reason).
  const applyFix = async () => {
    if (!fix?.reason?.trim()) { toast.error("A reason is required to apply the fix."); return; }
    const mobile = fix.scope === "all" ? "" : fix.scope;
    setFix((f) => ({ ...f, applying: true }));
    try {
      const r = await api.post("/master-brain/redemption-repair/fix", { mobile, confirm: true, reason: fix.reason.trim() });
      toast.success(r.data?.message || "Redemption ledger repaired.");
      setFix((f) => ({ ...f, applying: false, result: r.data }));
      await runAudit();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Fix failed");
      setFix((f) => ({ ...f, applying: false }));
    }
  };

  const undo = async (auditId) => {
    setUndoing(true);
    try {
      await api.post(`/master-brain/undo/${auditId}`, { reason: "Undo redemption-ledger repair" });
      toast.success("Reversed — balances restored and backfilled rows voided.");
      setFix(null);
      await runAudit();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Undo failed");
    } finally {
      setUndoing(false);
    }
  };

  const live = audit?.live_post_cutoff || {};
  const hist = audit?.historic_pre_cutoff || {};
  const hasLive = (live.bills || 0) > 0;

  return (
    <div data-testid="redemption-repair-page">
      <PageHeader
        title="Redemption Repair"
        subtitle="MISSING REDEEM LEDGER · BALANCE OVER-STATED"
        actions={
          <button onClick={runAudit} className="k-btn flex items-center gap-2" disabled={loading} data-testid="redemption-audit-btn">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> {loading ? "Scanning…" : (audit ? "Re-run audit" : "Run audit")}
          </button>
        }
      />

      <div className="p-4 md:p-8 space-y-6">
        <div className="chart-card p-5" data-accent="burgundy">
          <SectionHeading eyebrow="WHAT THIS FIXES" title="Bills that redeemed points but never wrote a redeem ledger row" accent="burgundy" />
          <p className="text-sm text-neutral-600 mt-2 leading-relaxed">
            When a live POS bill records <code>points_redeemed &gt; 0</code> but no matching <code>redeem</code> ledger row exists
            (a DB timeout mid-transaction), the customer's balance was never reduced — they keep points they already spent and could
            redeem them again. This tool writes the missing <code>redeem</code> row and deducts the never-debited points. Every fix is
            <strong> previewed, needs a reason, is audit-logged, and is fully undoable</strong>. Historical (pre-cutoff) bills are an
            audit-trail gap only (balance is authoritative there) and are left untouched.
          </p>
        </div>

        {!audit && !loading && (
          <div className="chart-card p-5 flex items-center justify-between gap-3" data-accent="slate" data-testid="run-audit-prompt">
            <div>
              <SectionHeading eyebrow="START HERE" title="Scan for missing redemption ledger entries" accent="slate" />
              <p className="text-xs text-neutral-500 mt-1">Runs the exact deterministic scan across all redemption bills. No AI — always completes with real numbers.</p>
            </div>
            <button onClick={runAudit} className="k-btn kazo-bg-burgundy text-white shrink-0" data-testid="run-audit-btn">
              <Search className="w-4 h-4" /> Run audit
            </button>
          </div>
        )}

        {loading && !audit && <div className="text-neutral-500" data-testid="audit-running">Scanning redemption bills…</div>}

        {audit && audit.computed === false && (
          <div className="flex items-start gap-3 p-4 rounded-lg border bg-amber-50 border-amber-200 text-amber-900" data-testid="audit-under-load">
            <AlertTriangle className="w-5 h-5 mt-0.5" />
            <div className="text-sm">{audit.message}</div>
          </div>
        )}

        {audit && audit.computed !== false && (
          <>
            {/* status banner */}
            <div
              className={`flex items-start gap-3 p-4 rounded-lg border ${
                hasLive ? "bg-amber-50 border-amber-200 text-amber-900" : "bg-emerald-50 border-emerald-200 text-emerald-900"
              }`}
              data-testid="audit-status"
            >
              {hasLive ? <AlertTriangle className="w-5 h-5 mt-0.5" /> : <CheckCircle2 className="w-5 h-5 mt-0.5" />}
              <div className="flex-1 text-sm">
                <div className="font-medium uppercase tracking-widest mb-1">
                  {hasLive
                    ? `${fmtNum(live.bills)} live bill(s) need repair — ${fmtNum(live.points)} pts never deducted`
                    : "Clean — every live redemption bill has its ledger row"}
                </div>
                <div className="opacity-80">Cutoff: {audit.cutoff_date} · {fmtNum(hist.bills)} historic bill(s) are audit-gap only (balance authoritative).</div>
              </div>
              {hasLive && (
                <button
                  onClick={() => startFix("all")}
                  className="k-btn kazo-bg-burgundy text-white shrink-0 flex items-center gap-2"
                  data-testid="fix-all-btn"
                >
                  <Wrench className="w-4 h-4" /> Fix all live ({fmtNum(live.bills)})
                </button>
              )}
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <KPICard label="Bills with a redemption" value={fmtNum(audit.total_bills_with_redemption)} accent="slate" testid="kpi-total-redemption" />
              <KPICard label="Live · missing ledger" value={fmtNum(live.bills)} accent={hasLive ? "burgundy" : "teal"} testid="kpi-live-missing" />
              <KPICard label="Live · customers affected" value={fmtNum(live.customers)} accent={hasLive ? "burgundy" : "teal"} testid="kpi-live-custs" />
              <KPICard label="Live · pts never deducted" value={fmtNum(live.points)} accent={hasLive ? "burgundy" : "teal"} testid="kpi-live-points" />
            </div>

            {/* fix confirmation panel */}
            {fix && fix.preview && !fix.result && (
              <div className="chart-card p-5 border-2 kazo-border-burgundy" data-accent="burgundy" data-testid="fix-confirm-panel">
                <SectionHeading
                  eyebrow="CONFIRM REPAIR"
                  title={fix.scope === "all" ? "Fix ALL live missing redemptions" : `Fix customer ${fix.scope}`}
                  accent="burgundy"
                />
                <p className="text-sm text-neutral-600 mt-2">
                  This will write <strong>{fmtNum(fix.preview.live_bills_to_fix)}</strong> missing redeem ledger row(s) and deduct{" "}
                  <strong>{fmtNum(fix.preview.points_to_deduct)}</strong> point(s) from{" "}
                  <strong>{fmtNum(fix.preview.customers_affected)}</strong> customer(s) whose balance was never reduced. Undoable.
                </p>
                <textarea
                  value={fix.reason}
                  onChange={(e) => setFix((f) => ({ ...f, reason: e.target.value }))}
                  placeholder="Reason (required) — e.g. 'Backfill POS-timeout missing redemptions, approved by ops'"
                  className="w-full mt-3 p-3 border border-neutral-300 rounded-lg text-sm min-h-[70px]"
                  data-testid="fix-reason-input"
                />
                <div className="flex items-center gap-3 mt-3">
                  <button onClick={applyFix} disabled={fix.applying} className="k-btn kazo-bg-burgundy text-white flex items-center gap-2 disabled:opacity-50" data-testid="fix-apply-btn">
                    <Wrench className="w-4 h-4" /> {fix.applying ? "Applying…" : "Confirm & apply"}
                  </button>
                  <button onClick={() => setFix(null)} disabled={fix.applying} className="k-btn" data-testid="fix-cancel-btn">Cancel</button>
                </div>
              </div>
            )}

            {/* applied result + undo */}
            {fix && fix.result && (
              <div className="chart-card p-5 border-2 border-emerald-300" data-accent="teal" data-testid="fix-result-panel">
                <SectionHeading eyebrow="DONE" title="Redemption ledger repaired" accent="teal" />
                <p className="text-sm text-neutral-700 mt-2">{fix.result.message}</p>
                <div className="flex items-center gap-3 mt-3">
                  {fix.result.audit_id && (
                    <button onClick={() => undo(fix.result.audit_id)} disabled={undoing} className="k-btn flex items-center gap-2 disabled:opacity-50" data-testid="fix-undo-btn">
                      <Undo2 className="w-4 h-4" /> {undoing ? "Undoing…" : "Undo this repair"}
                    </button>
                  )}
                  <button onClick={() => setFix(null)} className="k-btn" data-testid="fix-dismiss-btn">Dismiss</button>
                </div>
              </div>
            )}

            {/* affected bills table */}
            {(audit.sample || []).length > 0 && (
              <div className="chart-card p-5" data-accent="slate">
                <SectionHeading eyebrow="AFFECTED BILLS" title={`Sample (${(audit.sample || []).length})`} accent="slate" />
                <div className="overflow-x-auto mt-4">
                  <table className="w-full text-sm" data-testid="affected-bills-table">
                    <thead>
                      <tr className="text-left text-[11px] uppercase tracking-widest text-neutral-500 border-b">
                        <th className="py-2 pr-4">Mobile</th>
                        <th className="py-2 pr-4">Bill #</th>
                        <th className="py-2 pr-4">Bill date</th>
                        <th className="py-2 pr-4 text-right">Pts redeemed</th>
                        <th className="py-2 pr-4">Bucket</th>
                        <th className="py-2 pr-4 text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(audit.sample || []).map((b, i) => (
                        <tr key={`${b.bill}-${i}`} className="border-b last:border-0" data-testid={`bill-row-${i}`}>
                          <td className="py-2 pr-4 font-mono">{b.mobile}</td>
                          <td className="py-2 pr-4 font-mono">{b.bill}</td>
                          <td className="py-2 pr-4">{b.bill_date}</td>
                          <td className="py-2 pr-4 text-right font-medium">{fmtNum(b.points_redeemed)}</td>
                          <td className="py-2 pr-4">
                            <span className={`text-[11px] px-2 py-0.5 rounded-full ${b.bucket === "live" ? "bg-amber-100 text-amber-800" : "bg-neutral-100 text-neutral-600"}`}>
                              {b.bucket}
                            </span>
                          </td>
                          <td className="py-2 pr-4 text-right">
                            {b.bucket === "live" ? (
                              <button
                                onClick={() => startFix(b.mobile)}
                                className="k-btn text-xs flex items-center gap-1 ml-auto"
                                data-testid={`fix-row-btn-${i}`}
                              >
                                <Wrench className="w-3 h-3" /> Fix
                              </button>
                            ) : (
                              <span className="text-xs text-neutral-400">audit-gap only</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
