/* Re-tier old (pre-POS) customers from the configured tier ranges.
   Lives inside the Loyalty Rules page. Reads each old customer's Total Billing
   (lifetime_spend) and assigns the tier whose configured band they fall in —
   using the live configured tier names. Live POS customers are never touched. */
import { useState, useEffect, useRef, useCallback } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { fmtNum } from "@/lib/format";
import { Layers, Eye, Play, ArrowRight, CheckCircle2, AlertTriangle, Loader2 } from "lucide-react";

const fmtMoney = (v) => (v == null ? "∞" : `₹${Number(v).toLocaleString("en-IN")}`);

export default function RetierSection() {
  const [cutoff, setCutoff] = useState("2026-06-08");
  const [mode, setMode] = useState("source");
  const [preview, setPreview] = useState(null);
  const [previewing, setPreviewing] = useState(false);
  const [job, setJob] = useState(null);
  const [starting, setStarting] = useState(false);
  const timer = useRef(null);

  const pollStatus = useCallback(async () => {
    try {
      const r = await api.get("/loyalty/retier/status");
      setJob(r.data?.status && r.data.status !== "none" ? r.data : null);
      return r.data;
    } catch { return null; }
  }, []);

  useEffect(() => { pollStatus(); }, [pollStatus]);

  useEffect(() => {
    if (job?.status === "running") {
      timer.current = setInterval(async () => {
        const d = await pollStatus();
        if (d?.status !== "running") {
          clearInterval(timer.current);
          if (d?.status === "done") toast.success(`Re-tier complete — ${fmtNum(d.updated)} customers updated`);
          if (d?.status === "failed") toast.error("Re-tier failed: " + (d.error || "unknown error"));
        }
      }, 2000);
      return () => clearInterval(timer.current);
    }
  }, [job?.status, pollStatus]);

  const runPreview = async () => {
    setPreviewing(true);
    try {
      const r = await api.post("/loyalty/retier/preview", { mode, cutoff_date: cutoff });
      setPreview(r.data);
      if (!r.data.total_old_customers) toast.info("No matching old customers found");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Preview failed");
    } finally { setPreviewing(false); }
  };

  const runApply = async () => {
    const n = preview?.changed;
    const scope = mode === "date" ? `created before ${cutoff}` : "historical (not from live POS)";
    const msg = n != null
      ? `Re-tier ${fmtNum(n)} old customers (${scope}) using the configured tier ranges? This updates their tier in place.`
      : `Re-tier old customers (${scope}) using the configured tier ranges?`;
    if (!window.confirm(msg)) return;
    setStarting(true);
    try {
      const r = await api.post("/loyalty/retier/apply", { mode, cutoff_date: cutoff });
      toast.success("Re-tier started");
      setJob({ status: "running", total: r.data.total, updated: 0, processed: 0, per_tier: {} });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not start re-tier");
    } finally { setStarting(false); }
  };

  const running = job?.status === "running";
  const pct = running && job?.total ? Math.min(100, Math.round(((job.processed || 0) / job.total) * 100)) : 0;

  return (
    <div className="bg-white border border-black/10 p-5" data-testid="retier-section">
      <div className="flex items-center gap-3 mb-1">
        <div className="w-8 h-8 bg-neutral-100 flex items-center justify-center"><Layers className="w-4 h-4" /></div>
        <div>
          <div className="font-display text-base">UPDATE OLD DATA · RE-TIER CUSTOMERS</div>
          <div className="text-xs text-neutral-500">Re-assign pre-POS customers to the configured tiers, based on their Total Billing</div>
        </div>
      </div>

      <div className="mt-4 flex flex-col gap-1.5" data-testid="retier-mode">
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input type="radio" name="retier-mode" checked={mode === "source"} onChange={() => setMode("source")} disabled={running} data-testid="retier-mode-source" />
          Historical customers — everyone <b>not</b> created by the live POS <span className="text-neutral-400">(recommended)</span>
        </label>
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input type="radio" name="retier-mode" checked={mode === "date"} onChange={() => setMode("date")} disabled={running} data-testid="retier-mode-date" />
          Customers created before a specific date
        </label>
      </div>

      <div className="flex items-end gap-3 flex-wrap mt-3">
        {mode === "date" && (
          <div>
            <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1.5 block">Created before</label>
            <input type="date" value={cutoff} onChange={(e) => setCutoff(e.target.value)}
              className="k-input" data-testid="retier-cutoff" disabled={running} />
          </div>
        )}
        <button onClick={runPreview} disabled={previewing || running} className="k-btn k-btn-outline" data-testid="retier-preview-btn">
          {previewing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Eye className="w-3.5 h-3.5" />} Preview changes
        </button>
        <button onClick={runApply} disabled={starting || running} className="k-btn kazo-bg-burgundy text-white" data-testid="retier-apply-btn">
          {starting || running ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />} Apply re-tier
        </button>
      </div>

      <p className="text-xs text-neutral-500 mt-2 flex items-start gap-1.5">
        <AlertTriangle className="w-3.5 h-3.5 text-amber-500 shrink-0 mt-0.5" />
        Live POS customers are never changed. Tier names are read from your configured Tier Management above. No points are awarded — only the tier label changes. Safe to re-run.
      </p>

      {/* Live job progress */}
      {job && (
        <div className="mt-4 border border-black/10 rounded p-4" data-testid="retier-job">
          {running ? (
            <>
              <div className="flex items-center justify-between text-sm mb-2">
                <span className="flex items-center gap-2 font-medium"><Loader2 className="w-4 h-4 animate-spin" /> Re-tiering in progress…</span>
                <span className="font-mono text-neutral-600">{fmtNum(job.processed || 0)} / {fmtNum(job.total || 0)} scanned · {fmtNum(job.updated || 0)} re-tiered · {pct}%</span>
              </div>
              <div className="h-2 bg-neutral-100 rounded overflow-hidden">
                <div className="h-full kazo-bg-burgundy transition-all" style={{ width: `${pct}%` }} />
              </div>
            </>
          ) : job.status === "done" ? (
            <div className="text-sm" data-testid="retier-done">
              <div className="flex items-center gap-2 text-emerald-700 font-medium mb-2"><CheckCircle2 className="w-4 h-4" /> Last run complete — {fmtNum(job.updated || 0)} customers re-tiered</div>
              <div className="flex flex-wrap gap-2">
                {Object.entries(job.per_tier || {}).map(([slug, n]) => (
                  <span key={slug} className="text-xs bg-neutral-100 rounded px-2 py-1 font-mono">{slug}: +{fmtNum(n)}</span>
                ))}
              </div>
            </div>
          ) : job.status === "failed" ? (
            <div className="text-sm text-rose-700 flex items-center gap-2"><AlertTriangle className="w-4 h-4" /> Last run failed: {job.error}</div>
          ) : null}
        </div>
      )}

      {/* Preview before → after */}
      {preview && (
        <div className="mt-4" data-testid="retier-preview">
          <div className="text-sm mb-3">
            <span className="font-display text-lg">{fmtNum(preview.changed)}</span>
            <span className="text-neutral-600"> of {fmtNum(preview.total_old_customers)} old customers will be re-tiered</span>
            <span className="text-neutral-400"> · {fmtNum(preview.unchanged)} unchanged</span>
          </div>
          {preview.source_breakdown && (
            <div className="mb-3" data-testid="retier-sources">
              <div className="text-[10px] uppercase tracking-widest text-neutral-500 mb-1.5">Customer sources (struck-through = live POS, excluded)</div>
              <div className="flex flex-wrap gap-2">
                {preview.source_breakdown.map((s) => (
                  <span key={s.source}
                    className={`text-xs rounded px-2 py-1 font-mono ${s.is_pos ? "bg-neutral-100 text-neutral-400 line-through" : "bg-amber-50 text-amber-900"}`}
                    title={s.is_pos ? "Live POS — excluded from re-tier" : "Historical — included"}>
                    {s.source}: {fmtNum(s.count)}
                  </span>
                ))}
              </div>
            </div>
          )}
          <div className="grid md:grid-cols-2 gap-4">
            <DistTable title="Current tiers" rows={preview.current} testid="retier-current" />
            <DistTable title="After re-tier" rows={preview.proposed} testid="retier-proposed" highlight />
          </div>
          <div className="mt-3 text-xs text-neutral-500">
            Configured bands:{" "}
            {preview.configured_tiers.map((t, i) => (
              <span key={t.tier} className="font-mono">
                {i > 0 && " · "}{t.name} ({fmtMoney(t.min_lifetime_spend)}–{fmtMoney(t.max_lifetime_spend)})
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function DistTable({ title, rows, testid, highlight }) {
  return (
    <div className={`border rounded ${highlight ? "kazo-border-burgundy" : "border-black/10"}`} data-testid={testid}>
      <div className="px-3 py-2 text-[10px] uppercase tracking-widest text-neutral-500 border-b border-black/5 flex items-center gap-1.5">
        {highlight && <ArrowRight className="w-3 h-3" />}{title}
      </div>
      <table className="w-full text-sm">
        <tbody>
          {(rows || []).map((r) => (
            <tr key={r.tier} className="border-b border-black/5 last:border-0">
              <td className="py-1.5 px-3">{r.name}</td>
              <td className="py-1.5 px-3 text-right font-mono">{fmtNum(r.count)}</td>
            </tr>
          ))}
          {(!rows || rows.length === 0) && <tr><td className="py-3 px-3 text-neutral-400 text-xs">No data</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
