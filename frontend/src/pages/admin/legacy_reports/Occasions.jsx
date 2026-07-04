/* Birthdays & Anniversaries Report — monthly occasion lists + bulk SMS to the audience. */
import { useState, useEffect, useRef } from "react";
import { LegacyReportShell, useReportParams } from "./_shell";
import { fmtMoney2, fmtNum, fmtDateISO } from "@/lib/format";
import api from "@/lib/api";
import { toast } from "sonner";
import { MessageSquare, Send, X } from "lucide-react";

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const CURRENT_YEAR = new Date().getFullYear();
const YEARS = Array.from({ length: 40 }, (_, i) => CURRENT_YEAR - i);

const LABEL = "text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1 block";

const cols = [
  { key: "mobile", label: "Mobile", cellClass: "font-mono" },
  { key: "name", label: "Name" },
  { key: "occasion_date", label: "Date", cellClass: "text-xs text-neutral-600", fmt: (v) => v || "—" },
  { key: "points_balance", label: "Points", cellClass: "text-right font-mono", fmt: fmtNum },
  { key: "last_visit_at", label: "Last Txn", cellClass: "text-xs text-neutral-600", fmt: fmtDateISO },
  { key: "lifetime_spend", label: "Lifetime ₹", cellClass: "text-right font-mono", fmt: fmtMoney2 },
  { key: "tier", label: "Tier", fmt: (v) => (v ? <span className="text-xs uppercase">{v}</span> : "—") },
  { key: "visit_count", label: "Visits", cellClass: "text-right font-mono", fmt: fmtNum },
  { key: "city", label: "City", cellClass: "text-xs" },
];

function SendSmsPanel({ total, params }) {
  const [open, setOpen] = useState(false);
  const [templates, setTemplates] = useState([]);
  const [templateId, setTemplateId] = useState("");
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [job, setJob] = useState(null);
  const pollRef = useRef(null);

  const occasionLabel = params.type === "anniversary" ? "anniversary" : "birthday";
  const monthLabel = MONTHS[(Number(params.month) || 1) - 1];
  const yearLabel = params.year && params.year !== "all" ? ` ${params.year}` : "";

  useEffect(() => () => clearInterval(pollRef.current), []);

  const openModal = async () => {
    setOpen(true);
    setPreview(null);
    setJob(null);
    try {
      const r = await api.get("/templates", { params: { channel: "sms" } });
      const active = (r.data.rows || []).filter((t) => t.status === "active");
      setTemplates(active);
      setTemplateId(active[0]?.id || "");
    } catch {
      toast.error("Could not load SMS templates");
    }
  };

  const sendReq = async (dry_run) =>
    api.post("/legacy-reports/occasions/send-sms", {
      type: params.type, month: Number(params.month), year: params.year || "all",
      tier: params.tier || null, template_id: templateId, dry_run, limit: 5000,
    });

  const doPreview = async () => {
    if (!templateId) return toast.error("Pick a template");
    setBusy(true);
    try {
      const r = await sendReq(true);
      setPreview(r.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Preview failed");
    } finally {
      setBusy(false);
    }
  };

  const pollJob = (jid) => {
    clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const r = await api.get(`/communications/bulk-jobs/${jid}`);
        setJob(r.data);
        if (["completed", "failed"].includes(r.data.status)) {
          clearInterval(pollRef.current);
          if (r.data.status === "completed")
            toast.success(`Sent ${r.data.sent || 0} · failed ${r.data.failed || 0}`);
          else toast.error("Campaign failed — check Communications");
        }
      } catch { /* keep polling */ }
    }, 2500);
  };

  const doSend = async () => {
    if (!templateId) return toast.error("Pick a template");
    const n = preview?.audience_size_capped ?? total;
    if (!window.confirm(`Send this SMS to ${Number(n).toLocaleString("en-IN")} customers now? This cannot be undone.`)) return;
    setBusy(true);
    try {
      const r = await sendReq(false);
      toast.success("SMS campaign queued");
      setJob({ id: r.data.job_id, status: "queued", sent: 0, failed: 0, processed: 0 });
      pollJob(r.data.job_id);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Send failed");
    } finally {
      setBusy(false);
    }
  };

  const selected = templates.find((t) => t.id === templateId);

  return (
    <>
      <button onClick={openModal} className="k-btn kazo-bg-burgundy text-white" data-testid="lr-occ-send-sms">
        <MessageSquare className="w-3.5 h-3.5" /> Send SMS
      </button>
      {open && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4" data-testid="lr-occ-sms-modal">
          <div className="bg-white w-full max-w-lg p-6 shadow-2xl rounded-sm">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-display text-xl">Send SMS · {occasionLabel} · {monthLabel}{yearLabel}</h3>
              <button onClick={() => setOpen(false)} className="text-neutral-400 hover:text-neutral-700" data-testid="lr-occ-sms-close">
                <X className="w-5 h-5" />
              </button>
            </div>
            <p className="text-sm text-neutral-600 mb-4">
              Message customers whose <b>{occasionLabel}</b> falls in <b>{monthLabel}{yearLabel}</b>{" "}
              (~<b>{fmtNum(total)}</b> in the current view · capped at 5,000 per send). Sent via Karix.
            </p>

            {templates.length === 0 ? (
              <div className="text-sm text-amber-800 bg-amber-50 border border-amber-200 p-3" data-testid="lr-occ-sms-no-templates">
                No active SMS templates found. Create a DLT-approved SMS template under
                <b> Communications → Templates</b> first, then come back here.
              </div>
            ) : (
              <>
                <label className={LABEL}>SMS template</label>
                <select
                  value={templateId}
                  onChange={(e) => { setTemplateId(e.target.value); setPreview(null); }}
                  className="k-input w-full mb-3"
                  data-testid="lr-occ-sms-template"
                >
                  {templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
                {selected && (
                  <div className="text-xs bg-neutral-50 border border-neutral-200 p-3 mb-3 whitespace-pre-wrap" data-testid="lr-occ-sms-body">
                    {selected.body}
                  </div>
                )}
                {preview && (
                  <div className="text-xs text-emerald-800 bg-emerald-50 border border-emerald-200 p-3 mb-3" data-testid="lr-occ-sms-preview">
                    Will send to <b>{fmtNum(preview.audience_size_capped)}</b> of {fmtNum(preview.audience_size_total)} matched customers.
                    {preview.sample?.length ? <> &nbsp;Sample: {preview.sample.map((s) => s.mobile).join(", ")}</> : null}
                  </div>
                )}
                {job && (
                  <div className="text-xs bg-indigo-50 border border-indigo-200 p-3 mb-3" data-testid="lr-occ-sms-job">
                    Campaign <b>{job.status}</b> — sent {fmtNum(job.sent || 0)}, failed {fmtNum(job.failed || 0)}, processed {fmtNum(job.processed || 0)}.
                  </div>
                )}
                <div className="flex items-center gap-2 justify-end">
                  <button onClick={doPreview} disabled={busy} className="k-btn k-btn-outline" data-testid="lr-occ-sms-preview-btn">
                    Preview audience
                  </button>
                  <button onClick={doSend} disabled={busy || !templateId} className="k-btn kazo-bg-burgundy text-white" data-testid="lr-occ-sms-send-btn">
                    <Send className="w-3.5 h-3.5" /> {busy ? "…" : "Send now"}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}

export default function OccasionsReport() {
  const now = new Date();
  const ps = useReportParams({
    type: "birthday", month: now.getMonth() + 1, year: "all",
    sort: "points_balance", dir: "desc", limit: 100, offset: 0,
  });
  return (
    <LegacyReportShell
      testid="lr-occasions"
      title="Birthdays & Anniversaries"
      subtitle="LEGACY REPORT · DETAILED"
      endpoint="/legacy-reports/occasions"
      paramsState={ps}
      actions={({ total, params }) => <SendSmsPanel total={total} params={params} />}
      filters={<>
        <div>
          <label className={LABEL}>Occasion</label>
          <select value={ps.params.type} onChange={(e) => ps.set("type", e.target.value)} className="k-input" data-testid="lr-occ-type">
            <option value="birthday">🎂 Birthday</option>
            <option value="anniversary">💍 Anniversary</option>
          </select>
        </div>
        <div>
          <label className={LABEL}>Month</label>
          <select value={ps.params.month} onChange={(e) => ps.set("month", e.target.value)} className="k-input" data-testid="lr-occ-month">
            {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
          </select>
        </div>
        <div>
          <label className={LABEL}>Year</label>
          <select value={ps.params.year} onChange={(e) => ps.set("year", e.target.value)} className="k-input" data-testid="lr-occ-year">
            <option value="all">All years</option>
            {YEARS.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
        <div>
          <label className={LABEL}>Sort by</label>
          <select value={ps.params.sort} onChange={(e) => ps.set("sort", e.target.value)} className="k-input" data-testid="lr-occ-sort">
            <option value="points_balance">Points balance</option>
            <option value="last_visit_at">Last transaction</option>
            <option value="lifetime_spend">Lifetime spend</option>
            <option value="name">Name</option>
          </select>
        </div>
        <div className="flex-1 min-w-[180px]">
          <label className={LABEL}>Search (mobile / name)</label>
          <input value={ps.params.q || ""} onChange={(e) => ps.set("q", e.target.value)} className="k-input w-full" data-testid="lr-occ-q" />
        </div>
      </>}
      columns={cols}
    />
  );
}
