import { useRef, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import {
  Award, Upload, FileText, RefreshCw, CheckCircle2, AlertTriangle, Undo2, Users, Coins, Download,
} from "lucide-react";
import { PageHeader, SectionHeading, KPICard } from "./_shared";

const fmtNum = (v) => (v == null ? "—" : Number(v).toLocaleString("en-IN"));

const downloadMobilesCsv = (mobiles, filename) => {
  const rows = ["Mobile", ...(mobiles || []).map((m) => String(m))];
  const blob = new Blob([rows.join("\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
};

export default function BulkBonusPage() {
  const fileRef = useRef(null);
  const [attachment, setAttachment] = useState(null); // {id, filename, mobiles_detected}
  const [uploading, setUploading] = useState(false);
  const [mode, setMode] = useState("flat"); // "flat" | "topup"
  const [value, setValue] = useState("");
  const [expiryDate, setExpiryDate] = useState("");
  const [expiryDays, setExpiryDays] = useState("");
  const [reason, setReason] = useState("");
  const [force, setForce] = useState(false);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const resetRun = () => { setPreview(null); setResult(null); setForce(false); };

  const onUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true); resetRun(); setAttachment(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await api.post("/master-brain/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      const detected = r.data?.mobiles_detected || 0;
      if (!detected) {
        toast.error("No mobile numbers detected in that file. Ensure a mobile column (CSV/Excel) or 10-digit numbers (PDF).");
        setAttachment(null);
      } else {
        setAttachment({ id: r.data.id, filename: r.data.filename, mobiles_detected: detected });
        toast.success(`${fmtNum(detected)} mobile number(s) detected.`);
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || "Upload failed");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const payload = (confirm) => ({
    attachment_id: attachment?.id,
    mode,
    value: parseInt(value || "0", 10),
    expiry_date: expiryDate || "",
    expiry_days: parseInt(expiryDays || "0", 10) || 0,
    reason: reason.trim(),
    confirm,
    force,
  });

  const runPreview = async () => {
    if (!attachment) { toast.error("Upload a file first."); return; }
    if (!(parseInt(value || "0", 10) > 0)) {
      toast.error(mode === "flat" ? "Enter the points to add." : "Enter the target balance to top up to.");
      return;
    }
    setBusy(true); setResult(null);
    try {
      const r = await api.post("/master-brain/bulk-bonus/run", payload(false));
      setPreview(r.data);
      if (!r.data?.customers_to_credit) toast.info("No matched customer needs points for this batch.");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Preview failed");
    } finally {
      setBusy(false);
    }
  };

  const runAward = async () => {
    if (!reason.trim()) { toast.error("A reason is required to award points."); return; }
    setBusy(true);
    try {
      const r = await api.post("/master-brain/bulk-bonus/run", payload(true));
      if (r.data?.blocked) {
        setPreview(r.data);
        toast.warning("Duplicate batch blocked — tick 'award again (force)' if you really intend a second award.");
      } else if (r.data?.applied) {
        setResult(r.data);
        setPreview(null);
        toast.success(r.data.message || "Bonus points awarded.");
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || "Award failed");
    } finally {
      setBusy(false);
    }
  };

  const undo = async (auditId) => {
    setBusy(true);
    try {
      await api.post(`/master-brain/undo/${auditId}`, { reason: "Undo bulk bonus award" });
      toast.success("Reversed — points removed and ledger rows voided.");
      resetRun();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Undo failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div data-testid="bulk-bonus-page">
      <PageHeader title="Bulk Bonus Points" subtitle="AWARD LOYALTY POINTS FROM A FILE" />

      <div className="p-4 md:p-8 space-y-6">
        {/* Step 1 — upload */}
        <div className="chart-card p-5" data-accent="burgundy">
          <SectionHeading eyebrow="STEP 1" title="Upload customer mobile numbers" accent="burgundy" />
          <p className="text-sm text-neutral-600 mt-1">CSV, Excel (.xlsx) or PDF. We auto-detect the mobile column / 10-digit numbers.</p>
          <div className="flex flex-wrap items-center gap-3 mt-3">
            <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls,.pdf" onChange={onUpload} className="hidden" data-testid="bonus-file-input" />
            <button onClick={() => fileRef.current?.click()} disabled={uploading} className="k-btn kazo-bg-burgundy text-white flex items-center gap-2" data-testid="bonus-upload-btn">
              {uploading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />} {uploading ? "Uploading…" : "Choose file"}
            </button>
            {attachment && (
              <span className="flex items-center gap-2 text-sm text-neutral-700" data-testid="bonus-file-detected">
                <FileText className="w-4 h-4 text-neutral-500" /> {attachment.filename}
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800">{fmtNum(attachment.mobiles_detected)} mobiles</span>
              </span>
            )}
          </div>
        </div>

        {/* Step 2 — configure */}
        {attachment && (
          <div className="chart-card p-5" data-accent="slate" data-testid="bonus-config">
            <SectionHeading eyebrow="STEP 2" title="How many points, and how long are they valid?" accent="slate" />
            <div className="grid md:grid-cols-2 gap-5 mt-4">
              <div>
                <label className="text-xs font-medium uppercase tracking-widest text-neutral-500">Award type</label>
                <div className="flex gap-2 mt-2">
                  <button onClick={() => { setMode("flat"); resetRun(); }} className={`k-btn flex-1 ${mode === "flat" ? "kazo-bg-burgundy text-white" : ""}`} data-testid="mode-flat">
                    <Coins className="w-4 h-4" /> Flat points
                  </button>
                  <button onClick={() => { setMode("topup"); resetRun(); }} className={`k-btn flex-1 ${mode === "topup" ? "kazo-bg-burgundy text-white" : ""}`} data-testid="mode-topup">
                    <Award className="w-4 h-4" /> Top-up to value
                  </button>
                </div>
                <p className="text-[11px] text-neutral-500 mt-2">
                  {mode === "flat"
                    ? "Adds the same number of points to every customer in the file."
                    : "Tops each customer UP TO the target — awards only the difference (target − current balance)."}
                </p>
              </div>
              <div>
                <label className="text-xs font-medium uppercase tracking-widest text-neutral-500">
                  {mode === "flat" ? "Points to add" : "Top up each customer to (target balance)"}
                </label>
                <input type="number" min="1" value={value} onChange={(e) => { setValue(e.target.value); setPreview(null); }}
                  placeholder={mode === "flat" ? "e.g. 500" : "e.g. 1000"}
                  className="w-full mt-2 p-2.5 border border-neutral-300 rounded-lg text-sm" data-testid="bonus-value-input" />
              </div>
              <div>
                <label className="text-xs font-medium uppercase tracking-widest text-neutral-500">Points valid until (optional)</label>
                <input type="date" value={expiryDate} onChange={(e) => { setExpiryDate(e.target.value); setPreview(null); }}
                  className="w-full mt-2 p-2.5 border border-neutral-300 rounded-lg text-sm" data-testid="bonus-expiry-date" />
                <p className="text-[11px] text-neutral-500 mt-1">Or valid for a number of days below. Leave both blank = never expires.</p>
              </div>
              <div>
                <label className="text-xs font-medium uppercase tracking-widest text-neutral-500">Valid for (days, optional)</label>
                <input type="number" min="1" value={expiryDays} onChange={(e) => { setExpiryDays(e.target.value); setPreview(null); }}
                  placeholder="e.g. 90" disabled={!!expiryDate}
                  className="w-full mt-2 p-2.5 border border-neutral-300 rounded-lg text-sm disabled:bg-neutral-100" data-testid="bonus-expiry-days" />
              </div>
            </div>
            <div className="mt-4">
              <label className="text-xs font-medium uppercase tracking-widest text-neutral-500">Reason (required to award)</label>
              <input value={reason} onChange={(e) => setReason(e.target.value)}
                placeholder="e.g. Diwali bonus campaign, approved by marketing"
                className="w-full mt-2 p-2.5 border border-neutral-300 rounded-lg text-sm" data-testid="bonus-reason-input" />
            </div>
            <div className="mt-4">
              <button onClick={runPreview} disabled={busy} className="k-btn kazo-bg-burgundy text-white flex items-center gap-2 disabled:opacity-50" data-testid="bonus-preview-btn">
                <Users className="w-4 h-4" /> {busy ? "Working…" : "Preview award"}
              </button>
            </div>
          </div>
        )}

        {/* Step 3 — preview + confirm */}
        {preview && !result && (
          <div className="chart-card p-5 border-2 kazo-border-burgundy" data-accent="burgundy" data-testid="bonus-preview-panel">
            <SectionHeading eyebrow="STEP 3 · CONFIRM" title="Review before awarding" accent="burgundy" />
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
              <KPICard label="Mobiles in file" value={fmtNum(preview.mobiles_in_file)} accent="slate" testid="kpi-mobiles" />
              <KPICard label="Matched customers" value={fmtNum(preview.matched_customers)} accent="teal" testid="kpi-matched" />
              <KPICard label="Will be credited" value={fmtNum(preview.customers_to_credit)} accent="burgundy" testid="kpi-credited" />
              <KPICard label="Total points" value={fmtNum(preview.total_points)} accent="burgundy" testid="kpi-points" />
            </div>
            <p className="text-xs text-neutral-500 mt-3">
              {fmtNum(preview.not_found)} mobile(s) not found · {fmtNum(preview.skipped_zero)} already at/above target ·{" "}
              {preview.expires_at ? `expires ${String(preview.expires_at).slice(0, 10)}` : "no expiry"}
            </p>

            {preview.not_found > 0 && (preview.not_found_mobiles || []).length > 0 && (
              <button
                onClick={() => downloadMobilesCsv(preview.not_found_mobiles, "bulk_bonus_not_found_mobiles.csv")}
                className="k-btn k-btn-outline flex items-center gap-2 mt-3"
                data-testid="bonus-download-notfound-btn">
                <Download className="w-4 h-4" /> Download {fmtNum(preview.not_found)} not-found mobile(s) (CSV)
              </button>
            )}

            {preview.warning && (
              <div className="flex items-start gap-3 p-3 mt-4 rounded-lg border bg-amber-50 border-amber-200 text-amber-900" data-testid="bonus-dup-warning">
                <AlertTriangle className="w-5 h-5 mt-0.5" />
                <div className="text-sm flex-1">{preview.warning}</div>
              </div>
            )}
            {(preview.blocked_prior || preview.blocked) && (
              <label className="flex items-center gap-2 mt-3 text-sm text-amber-900" data-testid="bonus-force-label">
                <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} data-testid="bonus-force-checkbox" />
                Yes, award this batch AGAIN (I understand it will add the points a second time)
              </label>
            )}

            {(preview.sample || []).length > 0 && (
              <div className="overflow-x-auto mt-4">
                <table className="w-full text-sm" data-testid="bonus-sample-table">
                  <thead>
                    <tr className="text-left text-[11px] uppercase tracking-widest text-neutral-500 border-b">
                      <th className="py-2 pr-4">Mobile</th><th className="py-2 pr-4">Name</th>
                      <th className="py-2 pr-4 text-right">Balance now</th><th className="py-2 pr-4 text-right">Points to add</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.sample.map((s, i) => (
                      <tr key={i} className="border-b last:border-0">
                        <td className="py-2 pr-4 font-mono">{s.mobile}</td>
                        <td className="py-2 pr-4">{s.name || "—"}</td>
                        <td className="py-2 pr-4 text-right">{fmtNum(s.balance_before)}</td>
                        <td className="py-2 pr-4 text-right font-medium text-emerald-700">+{fmtNum(s.points_to_add)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="flex items-center gap-3 mt-4">
              <button onClick={runAward} disabled={busy || !preview.customers_to_credit || ((preview.blocked_prior || preview.blocked) && !force)}
                className="k-btn kazo-bg-burgundy text-white flex items-center gap-2 disabled:opacity-50" data-testid="bonus-award-btn">
                <Award className="w-4 h-4" /> {busy ? "Awarding…" : `Award ${fmtNum(preview.total_points)} pts`}
              </button>
              <button onClick={resetRun} disabled={busy} className="k-btn" data-testid="bonus-preview-cancel">Cancel</button>
            </div>
          </div>
        )}

        {/* Step 4 — result */}
        {result && (
          <div className="chart-card p-5 border-2 border-emerald-300" data-accent="teal" data-testid="bonus-result-panel">
            <SectionHeading eyebrow="DONE" title="Bonus points awarded" accent="teal" />
            <div className="flex items-start gap-2 mt-2 text-sm text-neutral-700">
              <CheckCircle2 className="w-5 h-5 text-emerald-600 mt-0.5" /> <span>{result.message}</span>
            </div>
            <div className="flex items-center gap-3 mt-3">
              {result.audit_id && (
                <button onClick={() => undo(result.audit_id)} disabled={busy} className="k-btn flex items-center gap-2 disabled:opacity-50" data-testid="bonus-undo-btn">
                  <Undo2 className="w-4 h-4" /> {busy ? "Undoing…" : "Undo this award"}
                </button>
              )}
              {result.not_found > 0 && (result.not_found_mobiles || []).length > 0 && (
                <button onClick={() => downloadMobilesCsv(result.not_found_mobiles, "bulk_bonus_not_found_mobiles.csv")}
                  className="k-btn k-btn-outline flex items-center gap-2" data-testid="bonus-result-download-notfound-btn">
                  <Download className="w-4 h-4" /> Download {fmtNum(result.not_found)} not-found (CSV)
                </button>
              )}
              <button onClick={() => { resetRun(); setAttachment(null); setValue(""); }} className="k-btn" data-testid="bonus-done-btn">Award another batch</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
