/* Daily Reco — add ONLY the missing bills from the daily reconciliation file.
   Reuses the transaction ingest in skip mode (existing bills untouched). Two paths:
   manual upload, and an email auto-pull (configured via RECO_IMAP_* env). */
import { useState, useEffect, useCallback, useRef } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { PageHeader } from "./_shared";
import { fmtNum } from "@/lib/format";
import { UploadCloud, Mail, RefreshCw, CheckCircle2, AlertTriangle, Clock, Info } from "lucide-react";

const STATUS_ICON = {
  done: <CheckCircle2 className="w-4 h-4 text-emerald-600" />,
  running: <Clock className="w-4 h-4 text-amber-600 animate-pulse" />,
  error: <AlertTriangle className="w-4 h-4 text-rose-600" />,
};

export default function DailyReco() {
  const [cfg, setCfg] = useState(null);
  const [runs, setRuns] = useState([]);
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const pollRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const r = await api.get("/reco/status");
      setCfg(r.data.config);
      setRuns(r.data.runs || []);
      return r.data.runs || [];
    } catch (e) {
      return [];
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Poll every 4s while any run is still processing.
  useEffect(() => {
    const anyRunning = runs.some((r) => r.status === "running");
    if (anyRunning && !pollRef.current) {
      pollRef.current = setInterval(load, 4000);
    } else if (!anyRunning && pollRef.current) {
      clearInterval(pollRef.current); pollRef.current = null;
    }
    return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } };
  }, [runs, load]);

  const upload = async () => {
    if (!file) { toast.error("Choose a Reco file first"); return; }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      await api.post("/reco/upload", fd, { headers: { "Content-Type": "multipart/form-data" }, timeout: 120_000 });
      toast.success("Reco file queued", { description: "Adding only the missing bills — watch the runs below." });
      setFile(null);
      await load();
    } catch (e) {
      toast.error("Upload failed", { description: e.response?.data?.detail || e.message });
    } finally { setBusy(false); }
  };

  const runEmail = async () => {
    setBusy(true);
    try {
      await api.post("/reco/run-email");
      toast.success("Pulling latest Reco email", { description: "Ingesting missing bills — watch the runs below." });
      await load();
    } catch (e) {
      toast.error("Email pull failed", { description: e.response?.data?.detail || e.message });
    } finally { setBusy(false); }
  };

  const fmtTime = (iso) => { try { return new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" }); } catch { return iso; } };

  return (
    <div data-testid="daily-reco-page">
      <PageHeader title="Daily Reco" subtitle="DATA · MISSING-BILL RECONCILIATION"
        actions={
          <button onClick={load} className="k-btn k-btn-outline" data-testid="reco-refresh">
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </button>
        }
      />
      <div className="p-8 space-y-6 max-w-5xl">
        <p className="text-sm text-neutral-600 max-w-3xl">
          Upload the daily reconciliation file (or pull it straight from the mailbox) to add
          <b> only the bills that are missing</b> from the portal. Bills already present are skipped —
          nothing is duplicated or overwritten, so it is safe to run repeatedly.
        </p>

        <div className="grid md:grid-cols-2 gap-6">
          {/* Manual upload */}
          <div className="chart-card p-5 space-y-4" data-accent="burgundy" data-testid="reco-upload-card">
            <div className="flex items-center gap-2">
              <UploadCloud className="w-4 h-4 kazo-text-burgundy" />
              <h3 className="font-display text-lg">Upload Reco file</h3>
            </div>
            <p className="text-xs text-neutral-500">CSV or Excel. Same columns as the Billing/Transactions export (Bill Number, Date, Store code, amounts, Customer Mobile…).</p>
            <input type="file" accept=".csv,.xlsx,.xls" data-testid="reco-file-input"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="block w-full text-sm text-neutral-600 file:mr-3 file:py-2 file:px-4 file:border-0 file:text-sm file:bg-neutral-900 file:text-white hover:file:bg-neutral-700 file:cursor-pointer" />
            <button onClick={upload} disabled={busy || !file} className="k-btn kazo-bg-burgundy text-white w-full justify-center" data-testid="reco-upload-btn">
              <UploadCloud className="w-3.5 h-3.5" /> {busy ? "Working…" : "Add missing bills"}
            </button>
          </div>

          {/* Email auto-pull */}
          <div className="chart-card p-5 space-y-4" data-accent="indigo" data-testid="reco-email-card">
            <div className="flex items-center gap-2">
              <Mail className="w-4 h-4 text-indigo-600" />
              <h3 className="font-display text-lg">Email auto-pull</h3>
            </div>
            {cfg?.configured ? (
              <div className="text-xs text-neutral-600 space-y-1">
                <div>Mailbox: <b>{cfg.user}</b> @ {cfg.host}:{cfg.port} · folder <b>{cfg.folder}</b> · auth <b>{cfg.auth}</b></div>
                <div>Daily pull: <b>{cfg.daily_enabled ? `ON at ${cfg.daily_time_ist} IST` : "OFF"}</b> · looks back {cfg.since_days} day(s){cfg.sender ? ` · from ${cfg.sender}` : ""}</div>
              </div>
            ) : (
              <div className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded p-3 flex gap-2">
                <Info className="w-4 h-4 shrink-0 mt-0.5" />
                <span>
                  This mailbox is on <b>Microsoft 365</b> (<code>outlook.office365.com</code>), where Microsoft
                  has <b>disabled basic-auth IMAP</b>. To automate, either set <code>RECO_IMAP_PASSWORD</code> to an
                  <b> app password</b> (needs MFA on the account), or use OAuth2:
                  set <code>RECO_IMAP_AUTH=xoauth2</code>, <code>RECO_IMAP_HOST=outlook.office365.com</code>,
                  <code>RECO_IMAP_USER</code>=mailbox, and <code>RECO_OAUTH_TENANT_ID</code> / <code>RECO_OAUTH_CLIENT_ID</code> /
                  <code>RECO_OAUTH_CLIENT_SECRET</code> from an Azure app (IMAP.AccessAsApp, admin-consented).
                  Until then, the manual upload on the left works immediately.
                </span>
              </div>
            )}
            <button onClick={runEmail} disabled={busy || !cfg?.configured} className="k-btn k-btn-outline w-full justify-center" data-testid="reco-email-btn">
              <Mail className="w-3.5 h-3.5" /> {busy ? "Working…" : "Pull latest Reco email now"}
            </button>
          </div>
        </div>

        {/* Runs */}
        <div className="chart-card p-5" data-accent="teal" data-testid="reco-runs-card">
          <h3 className="font-display text-lg mb-3">Recent runs</h3>
          {runs.length === 0 ? (
            <div className="text-sm text-neutral-500 py-8 text-center">No Reco runs yet.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="reco-runs-table">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-[0.15em] text-neutral-500 border-b">
                    <th className="py-2 pr-4">When (IST)</th>
                    <th className="py-2 pr-4">Source</th>
                    <th className="py-2 pr-4">File</th>
                    <th className="py-2 pr-4">Status</th>
                    <th className="py-2 pr-4 text-right">Added</th>
                    <th className="py-2 pr-4 text-right">Skipped (existing)</th>
                    <th className="py-2 pr-4 text-right">Errors</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((r) => (
                    <tr key={r.id} className="border-b border-neutral-100" data-testid={`reco-run-${r.id}`}>
                      <td className="py-2 pr-4 whitespace-nowrap">{fmtTime(r.started_at)}</td>
                      <td className="py-2 pr-4">{r.source}</td>
                      <td className="py-2 pr-4 max-w-[220px] truncate" title={r.filename}>{r.filename}</td>
                      <td className="py-2 pr-4"><span className="inline-flex items-center gap-1.5">{STATUS_ICON[r.status] || null}{r.status}</span></td>
                      <td className="py-2 pr-4 text-right font-medium text-emerald-700">{r.status === "running" ? "—" : fmtNum(r.added)}</td>
                      <td className="py-2 pr-4 text-right text-neutral-600">{r.status === "running" ? "—" : fmtNum(r.skipped_existing)}</td>
                      <td className="py-2 pr-4 text-right">{r.status === "running" ? "—" : (r.errors > 0 ? <span className="text-rose-600">{fmtNum(r.errors)}</span> : "0")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
