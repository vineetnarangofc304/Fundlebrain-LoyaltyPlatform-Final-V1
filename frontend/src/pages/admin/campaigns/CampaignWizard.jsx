import { useEffect, useMemo, useRef, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { fmtNum } from "@/lib/format";
import {
  Target, Users, MessageSquare, ClipboardCheck, ChevronLeft, ChevronRight,
  Check, Sparkles, Send, Loader2, X, Users2, Play, Save, Database, Ticket, CalendarClock,
} from "lucide-react";
import CampaignObjective from "./CampaignObjective";

const CHANNELS = ["whatsapp", "sms", "email", "push", "in_app"];
const STEPS = [
  { key: "objective", label: "Objective", icon: Target },
  { key: "audience", label: "Audience", icon: Users },
  { key: "message", label: "Message", icon: MessageSquare },
  { key: "review", label: "Review & Launch", icon: ClipboardCheck },
];

const BLANK = {
  name: "", description: "", channels: ["sms"], audience_type: "all",
  audience_filter: {}, message_template: "", template_id: "",
  coupon_code: "", coupon_batch_id: "", status: "draft", send_limit: 50000,
  objective: "generic", objective_params: {}, roi_window: "7d", cost: "",
};

export default function CampaignWizard({ onClose, onDone, templates = [], coupons = [], prefill }) {
  const [step, setStep] = useState(0);
  const [form, setForm] = useState({ ...BLANK, ...(prefill || {}) });
  const [audience, setAudience] = useState(null);      // { total_audience, sample }
  const [previewing, setPreviewing] = useState(false);
  const [submitting, setSubmitting] = useState(null);  // 'draft' | 'launch' | 'schedule'
  const [mdbs, setMdbs] = useState([]);
  const [batches, setBatches] = useState([]);
  const [scheduleAt, setScheduleAt] = useState("");
  const reqRef = useRef(0);

  useEffect(() => {
    api.get("/marketing-db").then((r) => setMdbs(r.data.rows || [])).catch(() => {});
    api.get("/coupons/unique/batches").then((r) => setBatches(r.data.rows || [])).catch(() => {});
  }, []);

  const toggleChannel = (ch) =>
    setForm((f) => ({ ...f, channels: f.channels.includes(ch) ? f.channels.filter((x) => x !== ch) : [...f.channels, ch] }));

  const compatibleTemplates = useMemo(
    () => templates.filter((t) => form.channels.length === 0 || form.channels.includes(t.channel) || (t.channel === "rcs" && form.channels.includes("whatsapp"))),
    [templates, form.channels]
  );

  const previewAudience = async () => {
    const rid = ++reqRef.current;
    setPreviewing(true);
    try {
      const r = await api.post("/campaigns/audience-preview", {
        audience_type: form.audience_type, audience_filter: form.audience_filter || {},
      });
      if (rid === reqRef.current) setAudience(r.data);  // ignore stale (out-of-order) responses
    } catch (e) {
      if (rid === reqRef.current) { toast.error(e?.response?.data?.detail || "Could not preview audience"); setAudience(null); }
    } finally {
      if (rid === reqRef.current) setPreviewing(false);
    }
  };

  // auto-preview (debounced) whenever we land on the audience/review step or the audience changes
  useEffect(() => {
    if (STEPS[step].key !== "audience" && STEPS[step].key !== "review") return;
    const t = setTimeout(() => { previewAudience(); }, 250);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, form.audience_type, JSON.stringify(form.audience_filter)]);

  const stepValid = () => {
    const k = STEPS[step].key;
    if (k === "objective") return !!form.name.trim();
    if (k === "audience") {
      if (form.audience_type === "segment") return !!form.audience_filter?.segment_id;
      if (form.audience_type === "marketing_db") return !!form.audience_filter?.marketing_db_id;
      if (form.audience_type === "tier") return !!form.audience_filter?.tier;
      if (form.audience_type === "city") return !!form.audience_filter?.city;
      if (form.audience_type === "cohort") return !!form.audience_filter?.cohort;
      return true;
    }
    if (k === "message") return form.channels.length > 0;
    return true;
  };

  const buildPayload = (mode) => {
    const payload = { ...form };
    if (!payload.template_id) delete payload.template_id;
    if (!payload.coupon_batch_id) delete payload.coupon_batch_id;
    if (!payload.message_template && !payload.template_id) payload.message_template = "(no body)";
    if (payload.cost === "" || payload.cost == null) delete payload.cost;
    else payload.cost = parseFloat(payload.cost);
    if (mode === "schedule") {
      payload.status = "scheduled";
      payload.schedule_at = new Date(scheduleAt).toISOString();
    }
    return payload;
  };

  const submit = async (mode) => {
    if (mode === "schedule") {
      if (!scheduleAt) { toast.error("Pick a date & time to schedule"); return; }
      if (new Date(scheduleAt).getTime() <= Date.now()) { toast.error("Schedule time must be in the future"); return; }
    }
    setSubmitting(mode);
    try {
      const r = await api.post("/campaigns", buildPayload(mode));
      const created = r.data;
      if (mode === "launch") {
        const lr = await api.post(`/campaigns/${created.id}/launch`);
        if (lr.data.mode === "karix") toast.success(`Real send via ${lr.data.channel?.toUpperCase()} queued · audience ${fmtNum(lr.data.audience)}`);
        else toast.success(`Simulated metrics generated · audience ${fmtNum(lr.data.audience)} (link a template for real send)`);
      } else if (mode === "schedule") {
        toast.success(`Campaign scheduled for ${new Date(scheduleAt).toLocaleString()} — it will fire automatically`);
      } else {
        toast.success("Campaign saved as draft");
      }
      onDone?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    } finally { setSubmitting(null); }
  };

  const next = () => { if (!stepValid()) { toast.error("Please complete this step"); return; } setStep((s) => Math.min(s + 1, STEPS.length - 1)); };
  const back = () => setStep((s) => Math.max(s - 1, 0));

  const key = STEPS[step].key;

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white w-full max-w-3xl max-h-[92vh] rounded flex flex-col" onClick={(e) => e.stopPropagation()} data-testid="campaign-wizard">
        {/* header + stepper */}
        <div className="p-5 border-b border-black/10">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-display text-2xl">New Campaign</h3>
            <button onClick={onClose} className="k-btn k-btn-ghost" data-testid="wizard-close"><X className="w-4 h-4" /></button>
          </div>
          <div className="flex items-center gap-1">
            {STEPS.map((s, i) => {
              const Icon = s.icon; const done = i < step; const active = i === step;
              return (
                <div key={s.key} className="flex items-center flex-1 last:flex-none">
                  <button type="button" onClick={() => i < step && setStep(i)} data-testid={`wizard-step-${s.key}`}
                    className={`flex items-center gap-2 px-2.5 py-1.5 rounded transition ${active ? "kazo-bg-burgundy text-white" : done ? "text-emerald-700" : "text-neutral-400"}`}>
                    <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] ${active ? "bg-white/20" : done ? "bg-emerald-100" : "bg-neutral-100"}`}>
                      {done ? <Check className="w-3 h-3" /> : <Icon className="w-3 h-3" />}
                    </span>
                    <span className="text-xs font-medium hidden sm:block">{s.label}</span>
                  </button>
                  {i < STEPS.length - 1 && <div className={`h-px flex-1 mx-1 ${done ? "bg-emerald-300" : "bg-neutral-200"}`} />}
                </div>
              );
            })}
          </div>
        </div>

        {/* body */}
        <div className="p-5 overflow-y-auto flex-1 space-y-4">
          {key === "objective" && (
            <div className="space-y-3" data-testid="wizard-body-objective">
              <input className="k-input" placeholder="Campaign name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="campaign-name-input" />
              <textarea className="k-input" placeholder="Description (optional)" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
              <CampaignObjective form={form} setForm={setForm} />
            </div>
          )}

          {key === "audience" && (
            <div className="space-y-3" data-testid="wizard-body-audience">
              <div className="grid grid-cols-2 gap-3">
                <select className="k-input" value={form.audience_type} onChange={(e) => setForm({ ...form, audience_type: e.target.value, audience_filter: {} })} data-testid="audience-type-select">
                  <option value="all">Entire base</option>
                  <option value="segment">From Segment Builder</option>
                  <option value="marketing_db">From Marketing Database</option>
                  <option value="tier">By tier</option>
                  <option value="city">By city</option>
                  <option value="cohort">By cohort</option>
                </select>
                {form.audience_type === "segment" && (
                  <div className="k-input flex items-center gap-2 bg-amber-50 border-amber-300">
                    <Sparkles className="w-3.5 h-3.5 text-amber-600" />
                    <span className="text-xs font-medium">{form.audience_filter?.segment_name || form.audience_filter?.segment_id || "No segment selected"}</span>
                  </div>
                )}
                {form.audience_type === "marketing_db" && (
                  <select className="k-input" value={form.audience_filter?.marketing_db_id || ""}
                    onChange={(e) => { const m = mdbs.find((x) => x.id === e.target.value); setForm({ ...form, audience_filter: { marketing_db_id: e.target.value, marketing_db_name: m?.name } }); }}
                    data-testid="audience-mdb-select">
                    <option value="">Select a database</option>
                    {mdbs.map((m) => <option key={m.id} value={m.id}>{`${m.name} · ${m.total} numbers (${m.member_count} members)`}</option>)}
                  </select>
                )}
                {form.audience_type === "tier" && (
                  <select className="k-input" value={form.audience_filter?.tier || ""} onChange={(e) => setForm({ ...form, audience_filter: { tier: e.target.value } })} data-testid="audience-tier-select">
                    <option value="">Select tier</option>
                    <option value="silver">Silver</option><option value="gold">Gold</option><option value="platinum">Platinum</option><option value="diamond">Diamond</option>
                  </select>
                )}
                {form.audience_type === "city" && (
                  <input className="k-input" placeholder="City" value={form.audience_filter?.city || ""} onChange={(e) => setForm({ ...form, audience_filter: { city: e.target.value } })} data-testid="audience-city-input" />
                )}
                {form.audience_type === "cohort" && (
                  <select className="k-input" value={form.audience_filter?.cohort || ""} onChange={(e) => setForm({ ...form, audience_filter: { cohort: e.target.value } })} data-testid="audience-cohort-select">
                    <option value="">Select cohort</option>
                    <option value="high_value">High-value</option><option value="churn_risk">Churn risk</option><option value="new">New customers</option><option value="vip">VIP (Platinum/Diamond)</option>
                  </select>
                )}
              </div>

              <div className="border border-black/10 rounded p-4 bg-neutral-50" data-testid="audience-preview-box">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-sm text-neutral-600"><Users2 className="w-4 h-4" /> Estimated dataset</div>
                  <button type="button" className="k-btn k-btn-sm k-btn-ghost" onClick={previewAudience} disabled={previewing} data-testid="audience-refresh">
                    {previewing ? <Loader2 className="w-3 h-3 animate-spin" /> : "Refresh"}
                  </button>
                </div>
                {previewing && !audience ? (
                  <div className="text-neutral-400 text-sm py-3 flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Counting…</div>
                ) : audience ? (
                  <>
                    <div className="text-3xl font-display mt-2" data-testid="audience-count">{fmtNum(audience.total_audience)}</div>
                    <div className="text-[11px] text-neutral-500">customers match · capped at your send limit · blacklisted numbers auto-excluded ({fmtNum(audience.blacklisted_total || 0)} on blacklist)</div>
                    {audience.sample?.length > 0 && (
                      <div className="flex gap-1.5 flex-wrap mt-2">
                        {audience.sample.slice(0, 8).map((s, i) => (
                          <span key={i} className="pill pill-neutral text-[10px]">{s.name || s.mobile} · {s.tier || "—"}</span>
                        ))}
                      </div>
                    )}
                  </>
                ) : (
                  <div className="text-neutral-400 text-sm py-3">No preview yet</div>
                )}
              </div>
            </div>
          )}

          {key === "message" && (
            <div className="space-y-3" data-testid="wizard-body-message">
              <div>
                <label className="text-[10px] uppercase tracking-widest text-neutral-500 mb-2 block">Channels</label>
                <div className="flex gap-2 flex-wrap">
                  {CHANNELS.map((ch) => (
                    <button key={ch} type="button" onClick={() => toggleChannel(ch)} className={`pill ${form.channels.includes(ch) ? "kazo-bg-burgundy text-white" : "pill-neutral"}`} data-testid={`channel-${ch}`}>{ch}</button>
                  ))}
                </div>
              </div>

              <div className="border border-neutral-200 rounded p-3 bg-neutral-50" data-testid="campaign-template-select">
                <div className="flex items-center justify-between mb-2">
                  <label className="text-[10px] uppercase tracking-widest text-neutral-700 font-medium flex items-center gap-1"><Send className="w-3 h-3" /> Send via Karix template (real send)</label>
                  {form.template_id && <button type="button" onClick={() => setForm({ ...form, template_id: "" })} className="text-[10px] text-rose-600 hover:underline">Clear</button>}
                </div>
                {compatibleTemplates.length === 0 ? (
                  <div className="text-xs text-neutral-500" data-testid="campaign-template-empty">
                    No active templates for selected channels — create one in <a href="/admin/communications/templates" className="underline text-burgundy">Templates</a>. Without a template the campaign only generates simulated metrics.
                  </div>
                ) : (
                  <select className="k-input" value={form.template_id} onChange={(e) => setForm({ ...form, template_id: e.target.value })} data-testid="campaign-template-dropdown">
                    <option value="">— Simulated metrics only (no real send) —</option>
                    {compatibleTemplates.map((t) => (
                      <option key={t.id} value={t.id}>{`${t.name} · ${t.channel.toUpperCase()}${t.channel !== "sms" ? ` · WABA ${t.waba_approval_status || "pending"}` : ""}`}</option>
                    ))}
                  </select>
                )}
                {form.template_id && <div className="text-[10px] text-emerald-700 mt-1">✓ This campaign will actually send messages via Karix when launched.</div>}
              </div>

              <textarea className="k-input" placeholder="Optional preview / fallback body (only used if no Karix template above)" value={form.message_template} onChange={(e) => setForm({ ...form, message_template: e.target.value })} data-testid="message-template-input" />

              <div className="grid grid-cols-3 gap-3">
                <select className="k-input" value={form.coupon_code} onChange={(e) => setForm({ ...form, coupon_code: e.target.value })} data-testid="coupon-select">
                  <option value="">No coupon</option>
                  {coupons.map((c) => <option key={c.id} value={c.code}>{`${c.code} · ${c.name}`}</option>)}
                </select>
                <input className="k-input" type="number" min="1" max="500000" placeholder="Send limit" value={form.send_limit} onChange={(e) => setForm({ ...form, send_limit: parseInt(e.target.value, 10) || 50000 })} data-testid="send-limit-input" />
                <input className="k-input" type="number" min="0" placeholder="Spend / cost (₹)" value={form.cost} onChange={(e) => setForm({ ...form, cost: e.target.value })} data-testid="campaign-cost-input" />
              </div>

              <div className="border border-neutral-200 rounded p-3 bg-neutral-50">
                <label className="text-[10px] uppercase tracking-widest text-neutral-700 font-medium flex items-center gap-1 mb-2"><Ticket className="w-3 h-3" /> Attach unique coupon batch (per-recipient code)</label>
                <select className="k-input" value={form.coupon_batch_id} onChange={(e) => setForm({ ...form, coupon_batch_id: e.target.value })} data-testid="coupon-batch-select">
                  <option value="">None</option>
                  {batches.map((b) => <option key={b.id} value={b.id}>{`${b.name} · ${b.total} codes (${b.total - (b.redeemed || 0)} left)`}</option>)}
                </select>
                {form.coupon_batch_id && <div className="text-[10px] text-emerald-700 mt-1">✓ Each recipient gets THEIR own code — include <code className="bg-neutral-100 px-1">{"{{coupon_code}}"}</code> in the template body.</div>}
              </div>
            </div>
          )}

          {key === "review" && (
            <div className="space-y-4" data-testid="wizard-body-review">
              <div className="grid grid-cols-2 gap-3">
                <ReviewItem label="Name" value={form.name} testid="review-name" />
                <ReviewItem label="Objective" value={`${form.objective} · ROI ${form.roi_window}`} testid="review-objective" />
                <ReviewItem label="Audience" value={audience ? `${fmtNum(audience.total_audience)} customers · ${form.audience_type}` : form.audience_type} testid="review-audience" />
                <ReviewItem label="Channels" value={form.channels.join(", ") || "—"} testid="review-channels" />
                <ReviewItem label="Send mode" value={form.template_id ? "Real Karix send" : "Simulated metrics"} testid="review-sendmode" accent={form.template_id ? "text-emerald-700" : "text-neutral-500"} />
                <ReviewItem label="Send limit" value={fmtNum(form.send_limit)} testid="review-limit" />
                {form.coupon_code && <ReviewItem label="Coupon" value={form.coupon_code} testid="review-coupon" />}
                {form.coupon_batch_id && <ReviewItem label="Unique coupons" value="Per-recipient codes attached" testid="review-coupon-batch" accent="text-emerald-700" />}
                {form.cost !== "" && form.cost != null && <ReviewItem label="Spend" value={`₹${form.cost}`} testid="review-cost" />}
              </div>

              <div className="border border-black/10 rounded p-3 bg-white" data-testid="review-schedule">
                <label className="text-[10px] uppercase tracking-widest text-neutral-700 font-medium flex items-center gap-1 mb-2"><CalendarClock className="w-3 h-3" /> Schedule for later (optional)</label>
                <input type="datetime-local" className="k-input" value={scheduleAt} onChange={(e) => setScheduleAt(e.target.value)} data-testid="schedule-at-input" />
                {scheduleAt && <div className="text-[11px] text-emerald-700 mt-1">Will auto-fire at {new Date(scheduleAt).toLocaleString()} — no manual action needed.</div>}
              </div>

              <div className="text-[11px] text-neutral-500 bg-amber-50 border border-amber-200 rounded p-2.5">
                Launching freezes this exact audience as the ROI dataset (t₀ = launch). Real Karix sends go via the bulk campaign account; simulated campaigns generate demo metrics.
              </div>
            </div>
          )}
        </div>

        {/* footer */}
        <div className="p-4 border-t border-black/10 flex items-center justify-between">
          <button className="k-btn k-btn-ghost disabled:opacity-40" onClick={back} disabled={step === 0} data-testid="wizard-back"><ChevronLeft className="w-4 h-4" /> Back</button>
          {key !== "review" ? (
            <button className="k-btn kazo-bg-burgundy" onClick={next} data-testid="wizard-next">Next <ChevronRight className="w-4 h-4" /></button>
          ) : (
            <div className="flex gap-2">
              <button className="k-btn k-btn-ghost disabled:opacity-50" onClick={() => submit("draft")} disabled={!!submitting} data-testid="wizard-create-draft">
                {submitting === "draft" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Save draft
              </button>
              {scheduleAt ? (
                <button className="k-btn kazo-bg-burgundy disabled:opacity-50" onClick={() => submit("schedule")} disabled={!!submitting} data-testid="wizard-create-schedule">
                  {submitting === "schedule" ? <Loader2 className="w-4 h-4 animate-spin" /> : <CalendarClock className="w-4 h-4" />} Schedule
                </button>
              ) : (
                <button className="k-btn kazo-bg-burgundy disabled:opacity-50" onClick={() => submit("launch")} disabled={!!submitting} data-testid="wizard-create-launch">
                  {submitting === "launch" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />} Create & Launch
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ReviewItem({ label, value, testid, accent }) {
  return (
    <div className="border border-black/10 rounded p-3 bg-neutral-50" data-testid={testid}>
      <div className="text-[10px] uppercase tracking-widest text-neutral-500">{label}</div>
      <div className={`text-sm mt-0.5 font-medium ${accent || ""}`}>{value || "—"}</div>
    </div>
  );
}
