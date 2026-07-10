/* Points Integrity Center — one place to identify & reverse each class of points error the
   client reported, as Scan → Reverse buttons (deterministic, audited, undoable):
     A. Duplicate bonus credits (Master Brain bulk award ran twice)
     B. Wrong tier-upgrade bonus given during legacy→KAZO migration
     C. Auto-calculated loyalty points on historic lifetime purchase (should be opening-balance only)
     D. Double redemption → negative balances (undo the bad redemption-repair + correct negatives)
     E. Re-tier legacy-tier customers to KAZO slabs (reuses the existing re-tier tool)
*/
import { useState, useEffect } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { SectionHeading } from "./_shared";
import RetierSection from "./_retier_section";
import { fmtNum } from "@/lib/format";
import { ShieldAlert, Search, Wrench, RotateCcw, AlertTriangle, RefreshCw } from "lucide-react";

const ACCENTS = { A: "burgundy", B: "amber", C: "indigo", D: "rose", E: "teal" };

function Stat({ label, value }) {
  return (
    <div className="px-3 py-2 rounded-lg bg-neutral-50 border border-neutral-200">
      <div className="text-[10px] uppercase tracking-[0.15em] text-neutral-500">{label}</div>
      <div className="text-lg font-semibold text-neutral-900">{value}</div>
    </div>
  );
}

/* Generic Scan → Reverse panel. Parent supplies the filter inputs (children), the request
   body, the endpoints and how to summarise the preview. */
function RepairPanel({ code, title, description, children, buildBody, previewUrl, applyUrl,
  summarise, applyVerb = "Reverse now", testid }) {
  const accent = ACCENTS[code];
  const [preview, setPreview] = useState(null);
  const [reason, setReason] = useState("");
  const [scanning, setScanning] = useState(false);
  const [applying, setApplying] = useState(false);
  const [done, setDone] = useState(null);

  const scan = async () => {
    setScanning(true); setDone(null);
    try {
      const r = await api.post(previewUrl, buildBody());
      setPreview(r.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Scan failed"); }
    finally { setScanning(false); }
  };
  const apply = async () => {
    if (!reason.trim()) { toast.error("A reason is required."); return; }
    setApplying(true);
    try {
      const r = await api.post(applyUrl, { ...buildBody(), reason: reason.trim() });
      toast.success(r.data?.message || "Done.");
      setDone(r.data); setPreview(null); setReason("");
    } catch (e) { toast.error(e.response?.data?.detail || "Action failed"); }
    finally { setApplying(false); }
  };

  const s = preview ? summarise(preview) : null;
  const hasWork = s && s.count > 0;

  return (
    <div className="chart-card p-6" data-accent={accent} data-testid={testid}>
      <SectionHeading eyebrow={`ISSUE ${code}`} title={title} accent={accent} />
      <p className="text-sm text-neutral-600 mt-2 leading-relaxed">{description}</p>
      <div className="mt-4 flex flex-wrap items-end gap-3">
        {children}
        <button onClick={scan} disabled={scanning} className="k-btn k-btn-outline flex items-center gap-2 disabled:opacity-50" data-testid={`${testid}-scan`}>
          <Search className={`w-4 h-4 ${scanning ? "animate-pulse" : ""}`} /> {scanning ? "Scanning…" : "Scan"}
        </button>
      </div>

      {preview && (
        <div className="mt-4 space-y-3" data-testid={`${testid}-preview`}>
          <div className={`flex items-start gap-3 p-4 rounded-lg border ${hasWork ? "bg-amber-50 border-amber-200 text-amber-900" : "bg-emerald-50 border-emerald-200 text-emerald-900"}`}>
            <AlertTriangle className="w-5 h-5 mt-0.5 shrink-0" />
            <div className="flex-1">
              <div className="font-medium">{s.headline}</div>
              {s.stats && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-3">
                  {s.stats.map((st) => <Stat key={st.label} label={st.label} value={st.value} />)}
                </div>
              )}
            </div>
          </div>
          {hasWork && (
            <div className="flex flex-wrap items-center gap-3">
              <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason (required)"
                className="p-2.5 border border-neutral-300 rounded-lg text-sm flex-1 min-w-[260px]" data-testid={`${testid}-reason`} />
              <button onClick={apply} disabled={applying} className="k-btn kazo-bg-burgundy text-white flex items-center gap-2 disabled:opacity-50" data-testid={`${testid}-apply`}>
                <Wrench className="w-4 h-4" /> {applying ? "Applying…" : applyVerb}
              </button>
            </div>
          )}
        </div>
      )}
      {done && (
        <div className="mt-4 p-4 rounded-lg border bg-emerald-50 border-emerald-200 text-emerald-900 text-sm" data-testid={`${testid}-done`}>
          {done.message} {done.audit_id ? <span className="opacity-70">· audit {done.audit_id}</span> : null}
        </div>
      )}
    </div>
  );
}

const inputCls = "p-2 border border-neutral-300 rounded-lg text-sm";
const lblCls = "text-[10px] uppercase tracking-[0.15em] text-neutral-500 mb-1 block";

export default function PointsIntegrityPage() {
  // Issue B filters
  const [b, setB] = useState({ start: "2026-06-08", end: "", migrated_only: true, mobile: "" });
  // Issue A filters
  const [a, setA] = useState({ since: "", window_hours: 72 });
  // Issue D negative-balance scope
  const [d, setD] = useState({ mobile: "" });

  return (
    <div className="p-8 max-w-5xl mx-auto space-y-6" data-testid="points-integrity-page">
      <div className="flex items-center gap-3">
        <ShieldAlert className="w-7 h-7 kazo-text-burgundy" />
        <div>
          <h1 className="font-display text-3xl">Points Integrity Center</h1>
          <p className="text-sm text-neutral-500">Identify and safely reverse points errors. Every action is audited and undoable.</p>
        </div>
      </div>

      <RepairPanel
        code="A" testid="repair-dup-bonus"
        title="Duplicate bonus credits (bulk award ran more than once)"
        description="Finds customers who were awarded the SAME bonus amount more than once within a short window (e.g. a Master Brain / bulk award that got executed twice) and reverses the surplus, keeping ONE credit per customer."
        previewUrl="/master-brain/reverse-duplicate-credits/preview"
        applyUrl="/master-brain/reverse-duplicate-credits/apply"
        buildBody={() => ({ since: a.since || "", window_hours: Number(a.window_hours) || 72 })}
        summarise={(p) => ({
          count: p.customers_affected || 0,
          headline: (p.customers_affected || 0) > 0
            ? `${fmtNum(p.customers_affected)} customer(s) got duplicate bonus credits — ${fmtNum(p.total_excess_points || 0)} surplus points can be reversed.`
            : "No duplicate bonus credits found for this window.",
          stats: [
            { label: "Customers", value: fmtNum(p.customers_affected || 0) },
            { label: "Duplicate rows", value: fmtNum(p.duplicate_rows || 0) },
            { label: "Surplus points", value: fmtNum(p.total_excess_points || 0) },
          ],
        })}
      >
        <div><label className={lblCls}>Since (optional)</label><input type="date" value={a.since} onChange={(e) => setA({ ...a, since: e.target.value })} className={inputCls} data-testid="dup-bonus-since" /></div>
        <div><label className={lblCls}>Window (hrs)</label><input type="number" value={a.window_hours} onChange={(e) => setA({ ...a, window_hours: e.target.value })} className={`${inputCls} w-24`} data-testid="dup-bonus-window" /></div>
      </RepairPanel>

      <RepairPanel
        code="B" testid="repair-tier-bonus"
        title="Wrong tier-upgrade bonus during legacy → KAZO migration"
        description="Migrated customers (historic tiers like silver/gold/platinum) who transacted after go-live were re-tiered onto a KAZO slab by their already-high lifetime spend and wrongly got a tier-upgrade bonus. This voids those tier-upgrade bonus rows and deducts the points. Use the go-live→re-tier date window; keep 'migrated only' on."
        previewUrl="/points-integrity/tier-upgrade-bonus/preview"
        applyUrl="/points-integrity/tier-upgrade-bonus/apply"
        buildBody={() => ({ start: b.start || "", end: b.end || "", migrated_only: b.migrated_only, mobile: b.mobile || "" })}
        summarise={(p) => ({
          count: p.bonus_rows || 0,
          headline: (p.bonus_rows || 0) > 0
            ? `${fmtNum(p.customers_affected)} customer(s) have ${fmtNum(p.bonus_rows)} wrong tier-upgrade bonus row(s) — ${fmtNum(p.points_to_reverse)} points to reverse.`
            : "No tier-upgrade bonus rows match this scope.",
          stats: [
            { label: "Customers", value: fmtNum(p.customers_affected || 0) },
            { label: "Bonus rows", value: fmtNum(p.bonus_rows || 0) },
            { label: "Points", value: fmtNum(p.points_to_reverse || 0) },
            { label: "Migrated only", value: p.migrated_only ? "Yes" : "No" },
          ],
        })}
      >
        <div><label className={lblCls}>From (go-live)</label><input type="date" value={b.start} onChange={(e) => setB({ ...b, start: e.target.value })} className={inputCls} data-testid="tier-bonus-start" /></div>
        <div><label className={lblCls}>To (re-tier date)</label><input type="date" value={b.end} onChange={(e) => setB({ ...b, end: e.target.value })} className={inputCls} data-testid="tier-bonus-end" /></div>
        <div><label className={lblCls}>Mobile (optional)</label><input value={b.mobile} onChange={(e) => setB({ ...b, mobile: e.target.value })} placeholder="one customer" className={`${inputCls} w-40 font-mono`} data-testid="tier-bonus-mobile" /></div>
        <label className="flex items-center gap-2 text-sm text-neutral-700 pb-1"><input type="checkbox" checked={b.migrated_only} onChange={(e) => setB({ ...b, migrated_only: e.target.checked })} data-testid="tier-bonus-migrated" /> Migrated only</label>
      </RepairPanel>

      <RepairPanel
        code="C" testid="repair-historic-earn"
        title="Auto-calculated loyalty points on historic lifetime purchase"
        description="For migrated customers the balance we imported IS the opening balance. In some cases the system also auto-earned points from their historic bills — double counting. This voids those historic-derived earn/bonus rows and keeps the imported balance as the single source of truth (balance is not changed)."
        previewUrl="/points-integrity/historic-earn/preview"
        applyUrl="/points-integrity/historic-earn/apply"
        buildBody={() => ({})}
        summarise={(p) => ({
          count: (p.derived_earned_ledger_rows_to_void || 0) + (p.historic_customers_to_reset || 0),
          headline: (p.derived_earned_ledger_rows_to_void || 0) > 0
            ? `${fmtNum(p.derived_earned_ledger_rows_to_void)} historic-derived earn row(s) across ${fmtNum(p.historic_customers_to_reset)} customer(s) can be normalized.`
            : "No historic-derived earn rows to normalize.",
          stats: [
            { label: "Historic customers", value: fmtNum(p.historic_customers_to_reset || 0) },
            { label: "Derived earn rows", value: fmtNum(p.derived_earned_ledger_rows_to_void || 0) },
            { label: "Derived points", value: fmtNum(p.derived_earned_ledger_points || 0) },
          ],
        })}
        applyVerb="Normalize now"
      />

      <RepairPanel
        code="D" testid="repair-negative"
        title="Correct negative point balances"
        description="Corrects customers whose balance went negative (usually from double redemption entries). This restores each negative balance to 0 with a compensating ledger entry. TIP: for double redemptions caused by the redemption-repair, first UNDO that run below — it restores the exact points and voids the duplicate rows."
        previewUrl="/points-integrity/negative-balances/preview"
        applyUrl="/points-integrity/negative-balances/apply"
        buildBody={() => ({ mobile: d.mobile || "" })}
        summarise={(p) => ({
          count: p.customers_affected || 0,
          headline: (p.customers_affected || 0) > 0
            ? `${fmtNum(p.customers_affected)} customer(s) with negative balance — ${fmtNum(p.points_to_restore || 0)} points to restore.`
            : "No negative balances found.",
          stats: [
            { label: "Customers", value: fmtNum(p.customers_affected || 0) },
            { label: "Points to restore", value: fmtNum(p.points_to_restore || 0) },
          ],
        })}
        applyVerb="Correct now"
      >
        <div><label className={lblCls}>Mobile (optional)</label><input value={d.mobile} onChange={(e) => setD({ ...d, mobile: e.target.value })} placeholder="blank = all" className={`${inputCls} w-44 font-mono`} data-testid="neg-mobile" /></div>
      </RepairPanel>

      <RepairRuns />

      <div className="chart-card p-6" data-accent="teal" data-testid="repair-retier">
        <SectionHeading eyebrow="ISSUE E" title="Re-tier legacy customers onto KAZO tiers" accent="teal" />
        <p className="text-sm text-neutral-600 mt-2 leading-relaxed">Identify customers still on legacy tiers (silver/gold/platinum…) and re-tier them to KAZO's actual tiers based on lifetime purchase. This awards NO bonus points.</p>
        <div className="mt-4"><RetierSection /></div>
      </div>
    </div>
  );
}

/* Recent repair runs + one-click undo — used to reverse the redemption-repair backfill that
   created the duplicate deductions. */
function RepairRuns() {
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(false);
  const [undoing, setUndoing] = useState(null);

  const load = async () => {
    setLoading(true);
    try { const r = await api.get("/points-integrity/repair-runs", { params: { limit: 30 } }); setRuns(r.data.runs || []); }
    catch (e) { toast.error(e.response?.data?.detail || "Failed to load runs"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const undo = async (id) => {
    const reason = window.prompt("Reason for undoing this repair run?");
    if (!reason || !reason.trim()) return;
    setUndoing(id);
    try {
      const r = await api.post(`/points-integrity/undo/${id}`, { reason: reason.trim() });
      toast.success(r.data?.message || "Undone.");
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Undo failed"); }
    finally { setUndoing(null); }
  };

  return (
    <div className="chart-card p-6" data-accent="slate" data-testid="repair-runs">
      <div className="flex items-center justify-between">
        <SectionHeading eyebrow="UNDO" title="Recent repair runs (reverse a bad run, e.g. the redemption-repair backfill)" accent="slate" />
        <button onClick={load} className="text-xs px-2 py-1 border border-neutral-300 hover:bg-neutral-50 flex items-center gap-1"><RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} /> Refresh</button>
      </div>
      <div className="mt-4 divide-y divide-neutral-100">
        {runs.length === 0 && <div className="text-sm text-neutral-500 py-6 text-center">{loading ? "Loading…" : "No repair runs yet."}</div>}
        {runs.map((r) => (
          <div key={r.id} className="flex items-center justify-between py-2.5 gap-3" data-testid={`run-${r.id}`}>
            <div className="min-w-0">
              <div className="text-sm font-medium text-neutral-800">{r.action} {r.undone && <span className="text-xs text-neutral-400">(undone)</span>}</div>
              <div className="text-xs text-neutral-500 truncate">{(r.created_at || "").slice(0, 16).replace("T", " ")} · {r.user_email || "—"} · {r.reason || "—"}</div>
            </div>
            <button onClick={() => undo(r.id)} disabled={r.undone || undoing === r.id}
              className="k-btn k-btn-outline k-btn-sm flex items-center gap-1 disabled:opacity-40 shrink-0" data-testid={`run-undo-${r.id}`}>
              <RotateCcw className="w-3.5 h-3.5" /> {undoing === r.id ? "Undoing…" : "Undo"}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
