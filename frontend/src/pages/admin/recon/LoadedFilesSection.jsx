import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { RefreshCw, FileSpreadsheet, CheckCircle2, AlertTriangle, Wand2, Save, CalendarClock, Loader2, RotateCw } from "lucide-react";
import { SectionHeading } from "../_shared";

const fmtNum = (v) => (v == null ? "—" : Number(v).toLocaleString("en-IN"));
const fmtTime = (iso) => {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-IN", {
      timeZone: "Asia/Kolkata", day: "2-digit", month: "short", year: "2-digit",
      hour: "2-digit", minute: "2-digit", hour12: true,
    });
  } catch { return iso; }
};

const STATUS_CLS = {
  completed: "bg-emerald-100 text-emerald-800",
  failed: "bg-rose-100 text-rose-800",
  ingesting: "bg-amber-100 text-amber-800",
  pending_ingest: "bg-amber-100 text-amber-800",
  uploading: "bg-slate-100 text-slate-700",
  previewed: "bg-indigo-100 text-indigo-800",
};

export default function LoadedFilesSection() {
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [cutoff, setCutoff] = useState("");
  const [cutoffSaving, setCutoffSaving] = useState(false);
  const [healing, setHealing] = useState({});           // job_id -> true
  const [recompute, setRecompute] = useState(null);      // status doc

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get("/historic-data/jobs", { params: { limit: 100 } });
      setJobs(r.data.rows || []);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load files");
    } finally {
      setLoading(false);
    }
  };

  const loadCutoff = async () => {
    try { const r = await api.get("/historic-data/points-cutoff"); setCutoff(r.data.cutoff || ""); } catch { /* */ }
  };
  const loadRecompute = async () => {
    try { const r = await api.get("/historic-data/recompute-status"); setRecompute(r.data?.status === "none" ? null : r.data); } catch { /* */ }
  };

  useEffect(() => { load(); loadCutoff(); loadRecompute(); }, []);

  // poll while a recompute is running
  useEffect(() => {
    if (recompute?.status !== "running") return;
    const t = setInterval(loadRecompute, 4000);
    return () => clearInterval(t);
  }, [recompute]);

  const saveCutoff = async () => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(cutoff)) { toast.error("Use an ISO date, e.g. 2025-06-08"); return; }
    setCutoffSaving(true);
    try {
      await api.put("/historic-data/points-cutoff", { cutoff });
      toast.success(`Points cutoff saved — only bills on/after ${cutoff} earn points.`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to save cutoff");
    } finally { setCutoffSaving(false); }
  };

  const healFile = async (j) => {
    if (!window.confirm(`Re-check & heal "${j.filename}"?\n\nThis re-ingests the file (inserts any missing rows) and recomputes each customer's spend, tier and cutoff-aware points. Idempotent — it won't duplicate anything.`)) return;
    setHealing((h) => ({ ...h, [j.id]: true }));
    try {
      const r = await api.post(`/historic-data/jobs/${j.id}/heal`);
      if (r.data.queued === false) { toast.info(r.data.message); }
      else { toast.success("Re-check queued — refreshing as it runs."); }
      // poll the job a few times
      for (let i = 0; i < 8; i++) {
        await new Promise((res) => setTimeout(res, 4000));
        await load();
        const cur = (await api.get("/historic-data/jobs", { params: { limit: 100 } })).data.rows.find((x) => x.id === j.id);
        if (cur && cur.status === "completed") break;
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || "Heal failed");
    } finally {
      setHealing((h) => { const n = { ...h }; delete n[j.id]; return n; });
      load();
    }
  };

  const runRecompute = async () => {
    if (!window.confirm(`Recompute spend, tier and cutoff-aware points for EVERY customer from their bills?\n\nPoints are counted only for bills on/after ${cutoff}. Manual point adjustments / opening balances are preserved.`)) return;
    try {
      const r = await api.post("/historic-data/recompute-points-tiers");
      if (r.data.queued === false) toast.info(r.data.message);
      else toast.success(r.data.message);
      loadRecompute();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to start recompute");
    }
  };

  const csvRows = (j) => Number(j.total_rows || j.row_count_estimated || 0);
  const accounted = (j) => Number(j.inserted || 0) + Number(j.updated || 0) + Number(j.skipped || 0);
  const diffOf = (j) => csvRows(j) - accounted(j);

  return (
    <div className="chart-card p-5" data-accent="indigo" data-testid="loaded-files-section">
      <div className="flex items-start justify-between gap-3">
        <SectionHeading eyebrow="FILES LOADED" title="Every CSV / Excel ingested — with row counts" accent="indigo" />
        <button className="k-btn k-btn-outline k-btn-sm shrink-0" onClick={load} disabled={loading} data-testid="loaded-files-refresh">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
        </button>
      </div>
      <p className="text-xs text-neutral-500 mt-1">
        <b>Rows</b> = rows in the file · <b>Inserted/Updated</b> = landed in the database · <b>Skipped</b> = rows the
        loader rejected · <b>Diff</b> = file rows minus everything accounted for. A non-zero Skipped or Diff means
        that file did not fully land. <b>Check & Heal</b> re-ingests a file (inserts missing rows) and recomputes
        spend, tier and cutoff-aware points.
      </p>

      {/* Cutoff + global recompute controls */}
      <div className="mt-4 flex flex-wrap items-end gap-4 p-3 bg-neutral-50 border border-black/5">
        <div>
          <label className="text-[11px] uppercase tracking-wide text-neutral-500 flex items-center gap-1">
            <CalendarClock className="w-3.5 h-3.5" /> Points cutoff (loyalty go-live)
          </label>
          <div className="flex items-center gap-2 mt-1">
            <input type="date" value={cutoff} onChange={(e) => setCutoff(e.target.value)}
              className="border border-black/15 px-2 py-1 text-sm" data-testid="cutoff-input" />
            <button onClick={saveCutoff} disabled={cutoffSaving} className="k-btn k-btn-outline k-btn-sm" data-testid="cutoff-save">
              {cutoffSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />} Save
            </button>
          </div>
          <p className="text-[11px] text-neutral-400 mt-1">Only bills on/after this date earn points.</p>
        </div>
        <div className="ml-auto text-right">
          <button onClick={runRecompute} disabled={recompute?.status === "running"} className="k-btn kazo-bg-burgundy text-white k-btn-sm" data-testid="recompute-btn">
            {recompute?.status === "running" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RotateCw className="w-3.5 h-3.5" />}
            Recompute points &amp; tiers (all)
          </button>
          {recompute && (
            <p className="text-[11px] text-neutral-500 mt-1" data-testid="recompute-status">
              {recompute.status === "running"
                ? `Recomputing… ${Number(recompute.processed || 0).toLocaleString("en-IN")} customers updated`
                : `Last recompute: ${recompute.status} · ${Number(recompute.processed || 0).toLocaleString("en-IN")} customers · cutoff ${recompute.cutoff || "—"}`}
            </p>
          )}
        </div>
      </div>

      {loading && jobs.length === 0 && <div className="text-sm text-neutral-500 mt-4">Loading files…</div>}
      {!loading && jobs.length === 0 && <div className="text-sm text-neutral-500 mt-4">No files have been loaded yet.</div>}

      {jobs.length > 0 && (
        <div className="overflow-x-auto border border-black/5 mt-4">
          <table className="w-full text-xs" data-testid="loaded-files-table">
            <thead className="bg-neutral-50">
              <tr>
                <th className="text-left px-2 py-1.5">File</th>
                <th className="text-left px-2 py-1.5">Dataset</th>
                <th className="text-left px-2 py-1.5">Status</th>
                <th className="text-right px-2 py-1.5">Rows</th>
                <th className="text-right px-2 py-1.5">Inserted</th>
                <th className="text-right px-2 py-1.5">Updated</th>
                <th className="text-right px-2 py-1.5">Skipped</th>
                <th className="text-right px-2 py-1.5">Diff</th>
                <th className="text-left px-2 py-1.5">Loaded (IST)</th>
                <th className="text-center px-2 py-1.5">Landed?</th>
                <th className="text-center px-2 py-1.5">Check</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => {
                const d = diffOf(j);
                const skipped = Number(j.skipped || 0);
                const clean = j.status === "completed" && d === 0 && skipped === 0;
                return (
                  <tr key={j.id} className="border-t border-black/5" data-testid={`loaded-file-${j.id}`}>
                    <td className="px-2 py-1 font-medium flex items-center gap-1.5">
                      <FileSpreadsheet className="w-3.5 h-3.5 text-indigo-600 shrink-0" />
                      <span className="max-w-[220px] truncate" title={j.filename}>{j.filename || "—"}</span>
                    </td>
                    <td className="px-2 py-1">{j.dataset}</td>
                    <td className="px-2 py-1">
                      <span className={`px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${STATUS_CLS[j.status] || "bg-slate-100 text-slate-700"}`}>
                        {(j.status || "").replace(/_/g, " ")}
                      </span>
                    </td>
                    <td className="px-2 py-1 text-right">{fmtNum(csvRows(j))}</td>
                    <td className="px-2 py-1 text-right">{fmtNum(j.inserted)}</td>
                    <td className="px-2 py-1 text-right">{fmtNum(j.updated)}</td>
                    <td className={`px-2 py-1 text-right ${skipped ? "text-rose-700 font-semibold" : ""}`}>{fmtNum(skipped)}</td>
                    <td className={`px-2 py-1 text-right ${d ? "text-rose-700 font-semibold" : ""}`}>{fmtNum(d)}</td>
                    <td className="px-2 py-1 text-neutral-500 whitespace-nowrap">{fmtTime(j.completed_at || j.queued_at)}</td>
                    <td className="px-2 py-1 text-center">
                      {clean
                        ? <CheckCircle2 className="w-4 h-4 text-emerald-600 inline" data-testid={`landed-ok-${j.id}`} />
                        : <AlertTriangle className="w-4 h-4 text-amber-600 inline" data-testid={`landed-warn-${j.id}`} />}
                    </td>
                    <td className="px-2 py-1 text-center">
                      {j.chunks_retained ? (
                        <button
                          onClick={() => healFile(j)}
                          disabled={!!healing[j.id] || j.status !== "completed"}
                          className="k-btn k-btn-outline k-btn-sm"
                          title="Re-ingest this file (insert missing rows) and recompute spend/tier/points"
                          data-testid={`heal-btn-${j.id}`}
                        >
                          {healing[j.id] ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Wand2 className="w-3.5 h-3.5" />}
                          {healing[j.id] ? "Healing…" : "Check & Heal"}
                        </button>
                      ) : (
                        <span className="text-[11px] text-neutral-400" title="Loaded before file-retention — re-upload it below to heal">re-upload to heal</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
