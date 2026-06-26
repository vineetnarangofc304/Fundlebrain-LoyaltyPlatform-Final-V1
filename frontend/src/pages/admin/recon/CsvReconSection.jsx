import { useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Upload, FileSearch, Download, RefreshCw, CheckCircle2, AlertTriangle } from "lucide-react";
import { SectionHeading, KPICard } from "../_shared";

const fmtNum = (v) => (v == null ? "—" : Number(v).toLocaleString("en-IN"));
const CHUNK_BYTES = 1_500_000;

const DATASET_OPTIONS = [
  { value: "transactions", label: "Transactions (Billing Report)" },
  { value: "customers", label: "Customers (CRM Export)" },
  { value: "items", label: "Items (SKU Master)" },
];

function SampleTable({ title, rows }) {
  if (!rows?.length) return null;
  return (
    <div className="mt-4">
      <div className="text-xs uppercase tracking-widest text-neutral-500 mb-2">{title} · first {rows.length}</div>
      <div className="overflow-x-auto border border-black/5">
        <table className="w-full text-xs">
          <thead className="bg-neutral-50">
            <tr>
              <th className="text-left px-2 py-1.5">Key</th>
              <th className="text-right px-2 py-1.5">CSV value</th>
              <th className="text-right px-2 py-1.5">DB value</th>
              <th className="text-left px-2 py-1.5">Detail</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 25).map((r, i) => (
              <tr key={i} className="border-t border-black/5">
                <td className="px-2 py-1 font-mono">{r.key}</td>
                <td className="px-2 py-1 text-right">{r.csv_value ?? "—"}</td>
                <td className="px-2 py-1 text-right">{r.db_value ?? "—"}</td>
                <td className="px-2 py-1 text-neutral-500">{r.detail || ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ReconReport({ job }) {
  const rep = job.report;
  if (!rep) return null;
  const clean = (rep.missing_in_db || 0) === 0 && (rep.amount_mismatches || 0) === 0;
  const backendBase = process.env.REACT_APP_BACKEND_URL;
  return (
    <div className="mt-4" data-testid="recon-csv-report">
      <div className={`flex items-center gap-2 text-sm p-3 border ${clean ? "bg-emerald-50 border-emerald-200 text-emerald-900" : "bg-amber-50 border-amber-200 text-amber-900"}`}>
        {clean ? <CheckCircle2 className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
        {clean
          ? "CSV fully reconciled — every CSV row exists in the database with matching amounts."
          : `Differences found — ${fmtNum(rep.missing_in_db)} missing in DB, ${fmtNum(rep.amount_mismatches ?? 0)} amount mismatches.`}
        <a
          className="ml-auto k-btn k-btn-outline k-btn-sm"
          href={`${backendBase}/api/recon/jobs/${job.id}/mismatches.csv`}
          target="_blank" rel="noreferrer"
          data-testid="recon-download-mismatches"
        >
          <Download className="w-3.5 h-3.5" /> Mismatch CSV
        </a>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
        <KPICard label="CSV rows" value={fmtNum(rep.csv?.rows)} accent="indigo" testid="recon-kpi-csv-rows" />
        <KPICard label="Parse failed" value={fmtNum(rep.csv?.parse_failed)} accent={rep.csv?.parse_failed ? "burgundy" : "slate"} testid="recon-kpi-parse-failed" />
        <KPICard label="Matched in DB" value={fmtNum(rep.matched)} accent="teal" testid="recon-kpi-matched" />
        <KPICard label="Missing in DB" value={fmtNum(rep.missing_in_db)} accent={rep.missing_in_db ? "burgundy" : "teal"} testid="recon-kpi-missing" />
        {"amount_mismatches" in rep && (
          <KPICard label="Amount mismatches" value={fmtNum(rep.amount_mismatches)} accent={rep.amount_mismatches ? "burgundy" : "teal"} testid="recon-kpi-amount-mm" />
        )}
        {"mobile_mismatches" in rep && (
          <KPICard label="Mobile mismatches" value={fmtNum(rep.mobile_mismatches)} accent={rep.mobile_mismatches ? "burgundy" : "teal"} testid="recon-kpi-mobile-mm" />
        )}
        <KPICard label="Extra in DB (not in CSV)" value={rep.extra_in_db == null ? "Not scanned" : fmtNum(rep.extra_in_db)} accent="slate" testid="recon-kpi-extra" />
        {rep.csv?.net_sum != null && (
          <KPICard label="CSV net ₹ sum" value={`₹${fmtNum(rep.csv.net_sum)}`} accent="indigo" testid="recon-kpi-csv-sum" />
        )}
        {rep.db?.net_sum != null && (
          <KPICard label="DB net ₹ sum (all)" value={`₹${fmtNum(rep.db.net_sum)}`} accent="indigo" testid="recon-kpi-db-sum" />
        )}
      </div>
      <SampleTable title="Missing in DB" rows={rep.samples?.missing_in_db} />
      <SampleTable title="Amount mismatches" rows={rep.samples?.amount_mismatches} />
      <SampleTable title="Lifetime spend mismatches" rows={rep.samples?.lifetime_spend_mismatches} />
      <SampleTable title="Extra in DB" rows={rep.samples?.extra_in_db} />
    </div>
  );
}

export default function CsvReconSection() {
  const [dataset, setDataset] = useState("transactions");
  const [deepScan, setDeepScan] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [jobs, setJobs] = useState([]);
  const [activeJob, setActiveJob] = useState(null);
  const [cancelling, setCancelling] = useState({});
  const fileRef = useRef(null);
  const pollRef = useRef(null);

  const loadJobs = async () => {
    try {
      const r = await api.get("/recon/jobs");
      setJobs(r.data.jobs || []);
      const running = (r.data.jobs || []).find((j) => j.status === "running");
      if (running) startPolling(running.id);
    } catch { /* ignore */ }
  };

  useEffect(() => { loadJobs(); return () => clearInterval(pollRef.current); }, []);

  const startPolling = (jobId) => {
    clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const r = await api.get(`/recon/jobs/${jobId}`);
        setActiveJob(r.data);
        if (r.data.status === "done" || r.data.status === "failed") {
          clearInterval(pollRef.current);
          loadJobs();
          if (r.data.status === "done") toast.success("Reconciliation complete");
          else toast.error(`Reconciliation failed: ${r.data.error || "unknown error"}`);
        }
      } catch { clearInterval(pollRef.current); }
    }, 2500);
  };

  const cancelJob = async (jobId) => {
    setCancelling((s) => ({ ...s, [jobId]: true }));
    try {
      await api.post(`/recon/jobs/${jobId}/cancel`);
      toast.success("Recon job cancelled");
      clearInterval(pollRef.current);
      if (activeJob?.id === jobId) setActiveJob((j) => (j ? { ...j, status: "failed", error: "Cancelled" } : j));
      await loadJobs();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Cancel failed");
    } finally {
      setCancelling((s) => ({ ...s, [jobId]: false }));
    }
  };

  const upload = async (file) => {
    if (!file) return;
    setUploading(true);
    setProgress(0);
    try {
      const totalChunks = Math.max(1, Math.ceil(file.size / CHUNK_BYTES));
      const init = await api.post("/recon/init", {
        dataset, filename: file.name, total_chunks: totalChunks, total_bytes: file.size,
        deep_scan: deepScan,
      });
      const jobId = init.data.id;
      for (let i = 0; i < totalChunks; i++) {
        const blob = file.slice(i * CHUNK_BYTES, Math.min((i + 1) * CHUNK_BYTES, file.size));
        const fd = new FormData();
        fd.append("job_id", jobId);
        fd.append("chunk_index", String(i));
        fd.append("chunk", blob, `${file.name}.part${i}`);
        await api.post("/recon/chunk", fd, { headers: { "Content-Type": "multipart/form-data" } });
        setProgress(Math.round(((i + 1) / totalChunks) * 100));
      }
      await api.post("/recon/finalize", { job_id: jobId });
      toast.info("Reconciliation running — comparing CSV against the database…");
      setActiveJob({ id: jobId, status: "running", dataset });
      startPolling(jobId);
      loadJobs();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Recon upload failed");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <div className="chart-card p-5" data-accent="teal" data-testid="csv-recon-section">
      <SectionHeading eyebrow="CSV ↔ DATABASE RECON" title="Re-upload a source CSV to verify every row landed" accent="teal" />
      <p className="text-xs text-neutral-500 mt-1">
        Uses the exact same column mapping as the historic loader — a row counts as "missing" only if
        ingest itself would have keyed it the same way and it is absent from MongoDB.
      </p>
      <div className="flex flex-wrap items-center gap-3 mt-4">
        <select className="k-input !w-auto" value={dataset} onChange={(e) => setDataset(e.target.value)} data-testid="recon-dataset-select">
          {DATASET_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <input ref={fileRef} type="file" accept=".csv,.xlsx" className="hidden"
          onChange={(e) => upload(e.target.files?.[0])} data-testid="recon-file-input" />
        <button className="k-btn kazo-bg-burgundy text-white" disabled={uploading}
          onClick={() => fileRef.current?.click()} data-testid="recon-upload-btn">
          <Upload className="w-3.5 h-3.5" /> {uploading ? `Uploading ${progress}%` : "Upload CSV & Reconcile"}
        </button>
        <button className="k-btn k-btn-outline" onClick={loadJobs} data-testid="recon-jobs-refresh">
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
        <label className="flex items-center gap-1.5 text-xs text-neutral-600 cursor-pointer select-none" data-testid="recon-deepscan-label">
          <input type="checkbox" checked={deepScan} onChange={(e) => setDeepScan(e.target.checked)}
            className="accent-current" data-testid="recon-deepscan-checkbox" />
          Deep DB-side scan (also find rows in DB not in the CSV — slower)
        </label>
      </div>

      {activeJob?.status === "running" && (
        <div className="mt-4 flex items-center gap-3 text-sm text-indigo-700" data-testid="recon-running">
          <RefreshCw className="w-4 h-4 animate-spin shrink-0" />
          <span>
            {activeJob.phase === "parsing" ? "Parsing the CSV…"
              : activeJob.phase === "deep-scan" ? "Deep DB-side scan…"
              : "Comparing…"} {fmtNum(activeJob.processed || 0)} rows processed
          </span>
          <button className="k-btn k-btn-outline k-btn-sm ml-auto text-rose-700 border-rose-200"
            disabled={!!cancelling[activeJob.id]}
            onClick={() => cancelJob(activeJob.id)} data-testid="recon-cancel-active">
            {cancelling[activeJob.id] ? "Cancelling…" : "Cancel"}
          </button>
        </div>
      )}
      {activeJob?.status === "failed" && (
        <div className="mt-4 text-sm text-rose-700" data-testid="recon-failed">Failed: {activeJob.error}</div>
      )}
      {activeJob?.status === "done" && <ReconReport job={activeJob} />}

      {jobs.length > 0 && (
        <div className="mt-6">
          <div className="text-xs uppercase tracking-widest text-neutral-500 mb-2">Recent recon runs</div>
          <div className="overflow-x-auto border border-black/5">
            <table className="w-full text-xs" data-testid="recon-jobs-table">
              <thead className="bg-neutral-50">
                <tr>
                  <th className="text-left px-2 py-1.5">File</th>
                  <th className="text-left px-2 py-1.5">Dataset</th>
                  <th className="text-left px-2 py-1.5">Status</th>
                  <th className="text-right px-2 py-1.5">Matched</th>
                  <th className="text-right px-2 py-1.5">Missing</th>
                  <th className="text-left px-2 py-1.5">When</th>
                  <th className="px-2 py-1.5" />
                </tr>
              </thead>
              <tbody>
                {jobs.map((j) => (
                  <tr key={j.id} className="border-t border-black/5">
                    <td className="px-2 py-1">{j.filename}</td>
                    <td className="px-2 py-1">{j.dataset}</td>
                    <td className="px-2 py-1">
                      <span className={`px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${
                        j.status === "done" ? "bg-emerald-100 text-emerald-800"
                          : j.status === "failed" ? "bg-rose-100 text-rose-800"
                          : "bg-amber-100 text-amber-800"}`}>{j.status}</span>
                    </td>
                    <td className="px-2 py-1 text-right">{fmtNum(j.report?.matched)}</td>
                    <td className="px-2 py-1 text-right">{fmtNum(j.report?.missing_in_db)}</td>
                    <td className="px-2 py-1 text-neutral-500">{j.queued_at ? new Date(j.queued_at).toLocaleString() : "—"}</td>
                    <td className="px-2 py-1 text-right">
                      <div className="flex items-center justify-end gap-2">
                        {(j.status === "running" || j.status === "uploading") && (
                          <button className="text-rose-700 hover:underline"
                            disabled={!!cancelling[j.id]}
                            onClick={() => cancelJob(j.id)}
                            data-testid={`recon-cancel-${j.id}`}>
                            {cancelling[j.id] ? "Cancelling…" : "Cancel"}
                          </button>
                        )}
                        <button className="text-indigo-700 hover:underline flex items-center gap-1"
                          onClick={async () => {
                            const r = await api.get(`/recon/jobs/${j.id}`);
                            setActiveJob(r.data);
                          }}
                          data-testid={`recon-view-${j.id}`}>
                          <FileSearch className="w-3 h-3" /> View
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
