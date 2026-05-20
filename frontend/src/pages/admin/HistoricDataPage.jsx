/* Historic Data Upload — CSV ingest UI for KAZO loading customer + transaction history. */
import { useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { PageHeader, SectionHeading } from "./_shared";
import { fmtDateTime } from "@/lib/format";
import {
  Upload, FileText, RefreshCw, Database, AlertTriangle,
  CheckCircle2, AlertCircle, Loader2, Clock, Trash2,
} from "lucide-react";

const DATASETS = [
  { key: "customers", label: "Customers", desc: "CRM master — mobile, points, lifetime billing.", accent: "#571326" },
  { key: "transactions", label: "Transactions", desc: "Bill-level history with outlet + tax + revenue.", accent: "#1E3A8A" },
  { key: "stores", label: "Stores", desc: "Outlet master (auto-created from transaction uploads).", accent: "#0E7C7B" },
  { key: "items", label: "Items / SKUs", desc: "Optional SKU master if you have it.", accent: "#B45309" },
];

const STATUS_STYLES = {
  uploading: { bg: "#E0E7FF", color: "#3730A3", border: "#C7D2FE", icon: Upload, label: "Uploading" },
  queued: { bg: "#FEF3C7", color: "#92400E", border: "#FDE68A", icon: Clock, label: "Queued" },
  running: { bg: "#DBEAFE", color: "#1E40AF", border: "#BFDBFE", icon: Loader2, label: "Running", spin: true },
  previewed: { bg: "#FAE8FF", color: "#86198F", border: "#F5D0FE", icon: FileText, label: "Previewed" },
  completed: { bg: "#ECFDF5", color: "#047857", border: "#A7F3D0", icon: CheckCircle2, label: "Completed" },
  failed: { bg: "#FEF2F2", color: "#B91C1C", border: "#FECACA", icon: AlertCircle, label: "Failed" },
};

export default function HistoricDataPage() {
  const [dataset, setDataset] = useState("customers");
  const [schema, setSchema] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [file, setFile] = useState(null);
  const [dryRun, setDryRun] = useState(true);
  const [duplicateMode, setDuplicateMode] = useState("upsert");
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(null); // {phase, percent, message}
  const [activeJobId, setActiveJobId] = useState(null);
  const [purgeOpen, setPurgeOpen] = useState(false);
  const fileRef = useRef(null);

  const loadSchema = async () => {
    try {
      const r = await api.get(`/historic-data/schema/${dataset}`);
      setSchema(r.data);
    } catch (e) { setSchema(null); }
  };
  const loadJobs = async () => {
    try {
      const r = await api.get("/historic-data/jobs", { params: { limit: 30 } });
      setJobs(r.data.rows || []);
    } catch (e) { /* ignore */ }
  };

  useEffect(() => { loadSchema(); /* eslint-disable-next-line */ }, [dataset]);
  useEffect(() => {
    loadJobs();
    const t = setInterval(loadJobs, 4000);
    return () => clearInterval(t);
  }, []);

  const handleFile = (e) => {
    const f = e.target.files?.[0];
    if (f) {
      if (!f.name.toLowerCase().endsWith(".csv")) {
        toast.error("Please pick a .csv file");
        e.target.value = "";
        return;
      }
      setFile(f);
    }
  };
  const handleDrop = (e) => {
    e.preventDefault();
    const f = e.dataTransfer.files?.[0];
    if (f) {
      if (!f.name.toLowerCase().endsWith(".csv")) { toast.error("Only .csv supported"); return; }
      setFile(f);
    }
  };

  const upload = async () => {
    if (!file) { toast.error("Pick a CSV file first"); return; }
    setUploading(true);
    setUploadProgress({ phase: "reading", percent: 0, message: "Reading file…" });
    let jobId = null;
    try {
      // Chunk by raw bytes (~1.5MB per chunk) so we stay well below ingress limits.
      // Slicing a Blob is zero-copy, so 33MB is no issue.
      const CHUNK_BYTES = 1_500_000; // 1.5 MB
      const totalChunks = Math.max(1, Math.ceil(file.size / CHUNK_BYTES));

      // Step 1 — init job
      setUploadProgress({ phase: "init", percent: 0, message: "Creating ingest job…" });
      const initRes = await api.post("/historic-data/ingest/init", {
        dataset,
        duplicate_mode: duplicateMode,
        dry_run: dryRun,
        filename: file.name,
        total_chunks: totalChunks,
        total_bytes: file.size,
      });
      jobId = initRes.data.id;
      setActiveJobId(jobId);

      // Step 2 — upload chunks sequentially (retry up to 3x per chunk)
      for (let i = 0; i < totalChunks; i++) {
        const start = i * CHUNK_BYTES;
        const end = Math.min(start + CHUNK_BYTES, file.size);
        const blob = file.slice(start, end);

        let attempt = 0;
        // eslint-disable-next-line no-constant-condition
        while (true) {
          try {
            const fd = new FormData();
            fd.append("job_id", jobId);
            fd.append("chunk_index", String(i));
            fd.append("chunk", blob, `chunk-${i}.csv`);
            await api.post("/historic-data/ingest/chunk", fd, {
              headers: { "Content-Type": "multipart/form-data" },
              timeout: 60_000,
            });
            break;
          } catch (err) {
            attempt += 1;
            if (attempt >= 3) throw err;
            await new Promise((r) => setTimeout(r, 1000 * attempt));
          }
        }
        const pct = ((i + 1) / totalChunks) * 100;
        setUploadProgress({
          phase: "uploading",
          percent: pct,
          message: `Uploading chunk ${i + 1} of ${totalChunks} (${pct.toFixed(0)}%)`,
        });
      }

      // Step 3 — finalize → triggers background ingest
      setUploadProgress({ phase: "finalizing", percent: 100, message: "Stitching & queuing ingest…" });
      const fin = await api.post("/historic-data/ingest/finalize", { job_id: jobId }, { timeout: 120_000 });
      toast.success(
        dryRun
          ? `Previewing ${fin.data.row_count_estimated?.toLocaleString() || ""} rows from ${file.name}…`
          : `Queued ${fin.data.row_count_estimated?.toLocaleString() || ""} rows for ingest`
      );
      loadJobs();
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
    } catch (e) {
      const detail = e?.response?.data?.detail || e?.message || "Upload failed";
      toast.error(`Upload failed: ${detail}`);
      if (jobId) {
        // best-effort abort to clean up server-side temp chunks
        api.post(`/historic-data/ingest/abort/${jobId}`).catch(() => {});
      }
    } finally {
      setUploading(false);
      setUploadProgress(null);
    }
  };

  const activeDataset = DATASETS.find((d) => d.key === dataset);

  return (
    <div data-testid="historic-data-page">
      <PageHeader
        title="Historical Data Upload"
        subtitle="LOAD MANY YEARS OF KAZO POS DATA · CSV · BACKGROUND INGEST"
        actions={
          <>
            <button onClick={loadJobs} className="k-btn k-btn-outline k-btn-sm" data-testid="hist-refresh"><RefreshCw className="w-3.5 h-3.5" /> Refresh</button>
            <button onClick={() => setPurgeOpen(true)} className="k-btn k-btn-outline k-btn-sm" style={{ borderColor: "#B91C1C", color: "#B91C1C" }} data-testid="hist-purge-btn">
              <Trash2 className="w-3.5 h-3.5" /> Purge demo data
            </button>
          </>
        }
      />

      <div className="p-8 space-y-6">
        {/* Dataset selector */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3" data-testid="dataset-tiles">
          {DATASETS.map((d) => (
            <button
              key={d.key}
              onClick={() => setDataset(d.key)}
              className={`text-left p-4 border-l-2 transition-all ${dataset === d.key ? "bg-white shadow" : "bg-neutral-50 hover:bg-white"}`}
              style={{ borderLeftColor: d.accent }}
              data-testid={`dataset-${d.key}`}
            >
              <div className="text-[10px] uppercase tracking-[0.22em]" style={{ color: d.accent }}>{d.key}</div>
              <div className="font-display text-xl mt-1">{d.label}</div>
              <div className="text-xs text-neutral-600 mt-1.5 leading-relaxed">{d.desc}</div>
            </button>
          ))}
        </div>

        {/* Upload + schema panels */}
        <div className="grid lg:grid-cols-[1fr_1fr] gap-6">
          {/* Upload card */}
          <div className="chart-card p-5" data-accent="burgundy">
            <SectionHeading eyebrow="UPLOAD CSV" title={`Ingest ${activeDataset?.label}`} accent="burgundy" />

            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleDrop}
              className="border-2 border-dashed border-neutral-300 p-8 text-center bg-neutral-50 cursor-pointer hover:border-[var(--kazo-burgundy)] transition"
              onClick={() => fileRef.current?.click()}
              data-testid="hist-dropzone"
            >
              <input ref={fileRef} type="file" accept=".csv" onChange={handleFile} className="hidden" data-testid="hist-file-input" />
              <Upload className="w-8 h-8 mx-auto text-neutral-400 mb-2" />
              {file ? (
                <div>
                  <div className="font-medium text-sm">{file.name}</div>
                  <div className="text-[11px] text-neutral-500">{(file.size / (1024 * 1024)).toFixed(2)} MB · click to change</div>
                </div>
              ) : (
                <>
                  <div className="text-sm font-medium">Drop your CSV here or click to browse</div>
                  <div className="text-[11px] text-neutral-500 mt-1">Max 250 MB · UTF-8 · uploaded in 1.5 MB chunks</div>
                </>
              )}
            </div>

            {uploadProgress && (
              <div className="mt-4 p-3 border border-indigo-200 bg-indigo-50/40" data-testid="upload-progress">
                <div className="flex items-center justify-between text-[11px] text-indigo-800 mb-1.5">
                  <span className="uppercase tracking-widest font-medium">{uploadProgress.phase}</span>
                  <span className="font-mono tabular-nums">{uploadProgress.percent.toFixed(0)}%</span>
                </div>
                <div className="h-1.5 bg-indigo-100 overflow-hidden">
                  <div
                    className="h-full bg-indigo-600 transition-all duration-200"
                    style={{ width: `${uploadProgress.percent}%` }}
                  />
                </div>
                <div className="text-[11px] text-neutral-600 mt-1.5">{uploadProgress.message}</div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3 mt-4 text-xs">
              <label className="block">
                <div className="text-neutral-500 uppercase tracking-widest text-[10px] mb-1">Duplicate handling</div>
                <select className="k-input" value={duplicateMode} onChange={(e) => setDuplicateMode(e.target.value)} data-testid="hist-dupmode">
                  <option value="upsert">Upsert (update if exists)</option>
                  <option value="skip">Skip existing</option>
                  <option value="fail">Fail on first duplicate</option>
                </select>
              </label>
              <label className="block">
                <div className="text-neutral-500 uppercase tracking-widest text-[10px] mb-1">Mode</div>
                <select className="k-input" value={dryRun ? "dry" : "live"} onChange={(e) => setDryRun(e.target.value === "dry")} data-testid="hist-mode">
                  <option value="dry">Dry-run (preview only)</option>
                  <option value="live">Live ingest (write to MongoDB)</option>
                </select>
              </label>
            </div>

            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => { setFile(null); if (fileRef.current) fileRef.current.value = ""; }} disabled={!file || uploading} className="k-btn k-btn-ghost k-btn-sm">Clear</button>
              <button onClick={upload} disabled={!file || uploading} className="k-btn kazo-bg-burgundy" data-testid="hist-upload-btn">
                <Upload className="w-4 h-4" /> {uploading ? "Uploading…" : dryRun ? "Preview" : "Ingest now"}
              </button>
            </div>
          </div>

          {/* Schema panel */}
          <div className="chart-card p-5" data-accent="indigo" data-testid="schema-panel">
            <SectionHeading
              eyebrow={schema?.primary_key ? `PK · ${schema.primary_key}` : "SCHEMA"}
              title="Expected columns"
              accent="indigo"
            />
            {!schema ? (
              <div className="py-6 text-neutral-500 text-sm">Loading…</div>
            ) : (
              <>
                <div className="text-xs space-y-3">
                  <div>
                    <div className="text-neutral-500 uppercase tracking-widest text-[10px] mb-1">REQUIRED</div>
                    <div className="flex flex-wrap gap-1.5">
                      {schema.required_columns.map((c) => (
                        <span key={c} className="font-mono text-[11px] px-2 py-0.5 bg-rose-50 border border-rose-200 text-rose-800">{c}</span>
                      ))}
                    </div>
                  </div>
                  <div>
                    <div className="text-neutral-500 uppercase tracking-widest text-[10px] mb-1">RECOGNISED ({schema.recognised_columns.length})</div>
                    <div className="flex flex-wrap gap-1">
                      {schema.recognised_columns.map((c) => (
                        <span key={c} className="font-mono text-[10px] px-1.5 py-0.5 bg-neutral-50 border border-neutral-200 text-neutral-700">{c}</span>
                      ))}
                    </div>
                  </div>
                  <div>
                    <div className="text-neutral-500 uppercase tracking-widest text-[10px] mb-1">SAMPLE ROW</div>
                    <div className="bg-neutral-900 text-emerald-200 p-3 font-mono text-[10px] overflow-x-auto whitespace-nowrap">
                      {Object.entries(schema.sample_row).map(([k, v]) => `${k}=${v}`).join(" | ")}
                    </div>
                  </div>
                  {schema.notes?.length > 0 && (
                    <div className="border-t border-black/10 pt-3">
                      <div className="text-neutral-500 uppercase tracking-widest text-[10px] mb-1.5">NOTES</div>
                      <ul className="text-[11px] text-neutral-600 leading-relaxed list-disc list-inside space-y-1">
                        {schema.notes.map((n, i) => <li key={i}>{n}</li>)}
                      </ul>
                    </div>
                  )}
                </div>
                <div className="mt-3 pt-3 border-t border-black/10 text-[11px] text-neutral-600">
                  <strong>Duplicate strategy:</strong> {schema.duplicate_strategy}
                </div>
              </>
            )}
          </div>
        </div>

        {/* Job history */}
        <div className="chart-card p-5" data-accent="teal" data-testid="hist-jobs-panel">
          <SectionHeading eyebrow={`${jobs.length} JOBS`} title="Ingest history" accent="teal" />
          {jobs.length === 0 ? (
            <div className="py-10 text-center text-neutral-500 text-sm">No uploads yet. Drop a CSV above to begin.</div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Dataset</th><th>Filename</th><th>Status</th><th>Mode</th>
                  <th className="text-right">Rows</th>
                  <th className="text-right">Inserted</th>
                  <th className="text-right">Updated</th>
                  <th className="text-right">Skipped</th>
                  <th>Queued</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((j) => {
                  const st = STATUS_STYLES[j.status] || STATUS_STYLES.queued;
                  const Icon = st.icon;
                  return (
                    <tr key={j.id} data-testid={`hist-job-${j.id}`}>
                      <td className="text-xs uppercase tracking-widest font-medium">{j.dataset}</td>
                      <td className="text-xs font-mono">{j.filename}</td>
                      <td>
                        <span className="pill inline-flex items-center gap-1" style={{ background: st.bg, color: st.color, border: `1px solid ${st.border}` }}>
                          <Icon className={`w-3 h-3 ${st.spin ? "animate-spin" : ""}`} /> {st.label}
                        </span>
                      </td>
                      <td className="text-[11px]">
                        {j.dry_run ? <span className="pill" style={{ background: "#FAE8FF", color: "#86198F", border: "1px solid #F5D0FE" }}>dry-run</span> : <span className="pill" style={{ background: "#ECFDF5", color: "#047857", border: "1px solid #A7F3D0" }}>live</span>}
                        <span className="ml-1 text-neutral-500 text-[10px]">{j.duplicate_mode}</span>
                      </td>
                      <td className="text-right tabular-nums">{j.processed?.toLocaleString() ?? 0} / {j.row_count_estimated?.toLocaleString() ?? "?"}</td>
                      <td className="text-right tabular-nums text-emerald-700 font-medium">{j.inserted?.toLocaleString() ?? 0}</td>
                      <td className="text-right tabular-nums text-indigo-700">{j.updated?.toLocaleString() ?? 0}</td>
                      <td className="text-right tabular-nums text-amber-700">{j.skipped?.toLocaleString() ?? 0}</td>
                      <td className="text-xs text-neutral-500">{fmtDateTime(j.queued_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
          {activeJobId && jobs.find((j) => j.id === activeJobId)?.errors_sample?.length > 0 && (
            <div className="mt-4 p-3 border border-amber-200 bg-amber-50/40">
              <div className="text-[10px] uppercase tracking-widest text-amber-700 mb-1.5 flex items-center gap-1"><AlertTriangle className="w-3 h-3" /> SAMPLE ERRORS</div>
              <ul className="text-[11px] text-neutral-700 font-mono space-y-1">
                {jobs.find((j) => j.id === activeJobId).errors_sample.slice(0, 5).map((e, i) => (
                  <li key={i}>Row {e.row}: {e.reason}</li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="text-xs text-neutral-500 leading-relaxed">
          <strong>How it works:</strong> The file is uploaded, parsed in the background, and each row is upserted into MongoDB using its primary key. For transactions, stores referenced in the <code className="font-mono">Outlet</code> column are auto-created if missing. All dashboards (Command Center, RFM, Cohorts, Campaign ROI, Executive Summary) recompute live from the new data immediately — no manual refresh required.
        </div>
      </div>

      {purgeOpen && <PurgeModal onClose={() => setPurgeOpen(false)} onDone={() => { setPurgeOpen(false); loadJobs(); }} />}
    </div>
  );
}


function PurgeModal({ onClose, onDone }) {
  const [preview, setPreview] = useState(null);
  const [confirmText, setConfirmText] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/historic-data/purge-preview").then((r) => setPreview(r.data)).catch(() => {});
  }, []);

  const purge = async () => {
    if (confirmText !== "PURGE") { toast.error("Type PURGE to confirm"); return; }
    setBusy(true);
    try {
      const r = await api.post("/historic-data/purge-demo", { confirm: true });
      toast.success(`Purged. Total deleted: ${Object.values(r.data.deleted_counts).reduce((a, b) => a + b, 0).toLocaleString()} rows`);
      onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Purge failed"); }
    finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white w-full max-w-lg" onClick={(e) => e.stopPropagation()} data-testid="purge-modal">
        <div className="p-5 border-b border-black/10 flex items-center gap-3">
          <AlertTriangle className="w-6 h-6" style={{ color: "#B91C1C" }} />
          <div>
            <div className="text-[10px] uppercase tracking-[0.22em] text-rose-700 mb-0.5">DANGER ZONE</div>
            <h3 className="font-display text-2xl">Purge all demo data</h3>
          </div>
        </div>
        <div className="p-5 space-y-4">
          <p className="text-sm text-neutral-700 leading-relaxed">
            This will delete <strong>all customers, transactions, stores, campaigns, coupons, points ledger, NPS, tickets, AI chats, message log, audit logs, bulk send jobs, and digest reports</strong>. Users, loyalty config, communication templates, and provider settings are kept intact.
          </p>
          {preview && (
            <div className="border border-rose-200 bg-rose-50/40 p-3" data-testid="purge-preview-counts">
              <div className="text-[10px] uppercase tracking-widest text-rose-700 mb-2">CURRENT COUNTS — WILL BE DELETED</div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] font-mono">
                {Object.entries(preview.current_counts).map(([k, v]) => (
                  <div key={k} className="flex justify-between"><span className="text-neutral-600">{k}</span><span className="tabular-nums text-rose-700">{(v || 0).toLocaleString()}</span></div>
                ))}
              </div>
            </div>
          )}
          <label className="block text-xs">
            <div className="text-neutral-500 uppercase tracking-widest text-[10px] mb-1">Type <span className="font-mono text-rose-700">PURGE</span> to confirm</div>
            <input className="k-input" value={confirmText} onChange={(e) => setConfirmText(e.target.value)} placeholder="PURGE" data-testid="purge-confirm-input" />
          </label>
        </div>
        <div className="p-5 border-t border-black/10 flex justify-end gap-2">
          <button onClick={onClose} className="k-btn k-btn-ghost">Cancel</button>
          <button onClick={purge} disabled={busy || confirmText !== "PURGE"} className="k-btn" style={{ background: "#B91C1C", color: "white" }} data-testid="purge-confirm-btn">
            <Trash2 className="w-4 h-4" /> {busy ? "Purging…" : "Purge all demo data"}
          </button>
        </div>
      </div>
    </div>
  );
}
