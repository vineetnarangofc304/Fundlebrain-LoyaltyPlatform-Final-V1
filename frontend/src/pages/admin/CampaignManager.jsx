import { useEffect, useState, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import { PageHeader, StatusPill } from "./_shared";
import { toast } from "sonner";
import { fmtINR, fmtNum, fmtDate } from "@/lib/format";
import { Plus, Play, Sparkles, Send, MessageSquare, Mail, Smartphone, Loader2 } from "lucide-react";

const CHANNELS = ["whatsapp", "sms", "email", "push", "in_app"];

const CHANNEL_ICON = {
  whatsapp: MessageSquare,
  sms: Smartphone,
  rcs: MessageSquare,
  email: Mail,
};

export default function CampaignManager() {
  const [items, setItems] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [show, setShow] = useState(false);
  const [coupons, setCoupons] = useState([]);
  const [searchParams, setSearchParams] = useSearchParams();
  const [launching, setLaunching] = useState(null);  // campaign id being launched
  const [form, setForm] = useState({
    name: "", description: "", channels: ["whatsapp"], audience_type: "all",
    audience_filter: {}, message_template: "", template_id: "",
    coupon_code: "", status: "draft", send_limit: 50000,
  });
  const pollRef = useRef(null);

  const load = async () => {
    const [c, co, tpl] = await Promise.all([
      api.get("/campaigns"),
      api.get("/coupons", { params: { is_active: true } }),
      api.get("/templates", { params: { status: "active" } }).catch(() => ({ data: [] })),
    ]);
    setItems(c.data);
    setCoupons(co.data);
    setTemplates(Array.isArray(tpl.data) ? tpl.data : []);
  };
  useEffect(() => { load(); }, []);

  // Prefill from Segment Builder
  useEffect(() => {
    const segmentId = searchParams.get("segment_id");
    const segmentName = searchParams.get("segment_name");
    if (segmentId) {
      setForm((f) => ({
        ...f,
        name: segmentName ? `Campaign · ${segmentName}` : f.name,
        audience_type: "segment",
        audience_filter: { segment_id: segmentId, segment_name: segmentName },
      }));
      setShow(true);
      setSearchParams({}, { replace: true });
      toast.info(`Campaign prefilled with segment "${segmentName || segmentId}"`);
    }
  }, [searchParams, setSearchParams]);

  // Poll any running campaigns that have a bulk_job_id for progress updates
  useEffect(() => {
    const runningWithJob = items.filter((c) => c.status === "running" && c.bulk_job_id);
    if (runningWithJob.length === 0) {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
      return;
    }
    const tick = async () => {
      try {
        const updates = await Promise.all(
          runningWithJob.map((c) =>
            api.get(`/communications/bulk-jobs/${c.bulk_job_id}`).then((r) => ({ id: c.id, job: r.data })).catch(() => null)
          )
        );
        setItems((prev) => prev.map((c) => {
          const u = updates.find((x) => x && x.id === c.id);
          if (!u || !u.job) return c;
          const j = u.job;
          return { ...c, _job: j, sent: j.sent || c.sent, status: j.status === "completed" ? "completed" : (j.status === "failed" ? "cancelled" : c.status) };
        }));
      } catch { /* ignore */ }
    };
    tick();
    pollRef.current = setInterval(tick, 4000);
    return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } };
  }, [items.map((c) => c.id + ":" + c.status).join("|")]); // re-arm when statuses change

  const toggleChannel = (ch) => {
    setForm((f) => ({ ...f, channels: f.channels.includes(ch) ? f.channels.filter(x => x !== ch) : [...f.channels, ch] }));
  };

  const create = async () => {
    try {
      const payload = { ...form };
      if (!payload.template_id) delete payload.template_id;
      if (!payload.message_template && !payload.template_id) payload.message_template = "(no body)";
      await api.post("/campaigns", payload);
      toast.success("Campaign created");
      setShow(false);
      setForm({ name: "", description: "", channels: ["whatsapp"], audience_type: "all", audience_filter: {}, message_template: "", template_id: "", coupon_code: "", status: "draft", send_limit: 50000 });
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  const launch = async (id) => {
    setLaunching(id);
    try {
      const r = await api.post(`/campaigns/${id}/launch`);
      if (r.data.mode === "karix") {
        toast.success(`Real send via ${r.data.channel.toUpperCase()} queued · audience ${fmtNum(r.data.audience)}`);
      } else {
        toast.success(`Simulated metrics generated · audience ${fmtNum(r.data.audience)} (link a template for real send)`);
      }
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Launch failed");
    } finally {
      setLaunching(null);
    }
  };

  // Filter templates by selected channels so users only pick compatible ones
  const compatibleTemplates = templates.filter((t) =>
    form.channels.length === 0 || form.channels.includes(t.channel) || (t.channel === "rcs" && form.channels.includes("whatsapp"))
  );

  return (
    <div data-testid="campaign-manager">
      <PageHeader title="Campaign Manager" subtitle="MULTI-CHANNEL ORCHESTRATION · KARIX-POWERED"
        actions={<button className="k-btn kazo-bg-burgundy" onClick={() => setShow(true)} data-testid="new-campaign-btn"><Plus className="w-4 h-4" /> New campaign</button>} />
      <div className="p-8">
        <div className="bg-white border border-black/10 overflow-x-auto">
          <table className="data-table">
            <thead><tr><th>Campaign</th><th>Channels</th><th>Audience</th><th>Send Mode</th><th className="text-right">Sent</th><th className="text-right">Delivered</th><th className="text-right">Redeemed</th><th className="text-right">Revenue</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {items.map((c) => {
                const job = c._job;
                const ChannelIcon = CHANNEL_ICON[c.channels?.[0]] || MessageSquare;
                return (
                  <tr key={c.id} data-testid={`campaign-row-${c.id}`}>
                    <td>
                      <div className="font-medium">{c.name}</div>
                      <div className="text-xs text-neutral-500">{fmtDate(c.created_at)}{c.bulk_job_id ? ` · job ${c.bulk_job_id.slice(0,8)}` : ""}</div>
                    </td>
                    <td><div className="flex gap-1 flex-wrap">{c.channels?.map((ch) => <span key={ch} className="pill pill-neutral">{ch}</span>)}</div></td>
                    <td><span className="pill pill-info">{c.audience_type}</span></td>
                    <td>
                      {c.send_mode === "karix" ? (
                        <span className="pill" style={{ background: "#dcfce7", color: "#166534" }} data-testid={`send-mode-${c.id}`}><ChannelIcon className="w-3 h-3 inline mr-1" /> Real Karix</span>
                      ) : c.send_mode === "simulated" ? (
                        <span className="pill pill-neutral" data-testid={`send-mode-${c.id}`}>Simulated</span>
                      ) : c.template_id ? (
                        <span className="pill pill-info">Karix · ready</span>
                      ) : (
                        <span className="pill pill-warning">No template</span>
                      )}
                    </td>
                    <td className="text-right font-mono">
                      {fmtNum(c.sent)}
                      {job && job.status === "running" && (
                        <div className="text-[10px] text-neutral-400">{job.processed || 0}/{job.audience_size_total || "?"}</div>
                      )}
                    </td>
                    <td className="text-right font-mono">{fmtNum(c.delivered)}</td>
                    <td className="text-right font-mono">{fmtNum(c.redeemed)}</td>
                    <td className="text-right font-mono">{fmtINR(c.revenue_generated)}</td>
                    <td>
                      <StatusPill status={c.status} />
                      {job && job.failed > 0 && <div className="text-[10px] text-rose-600 mt-0.5">{job.failed} failed</div>}
                    </td>
                    <td>
                      {c.status === "draft" && (
                        <button
                          className="k-btn k-btn-sm kazo-bg-burgundy disabled:opacity-50"
                          onClick={() => launch(c.id)}
                          disabled={launching === c.id}
                          data-testid={`launch-${c.id}`}
                        >
                          {launching === c.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
                          {launching === c.id ? "Launching…" : "Launch"}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
              {items.length === 0 && <tr><td colSpan={10} className="text-center py-10 text-neutral-500">No campaigns yet</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {show && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setShow(false)}>
          <div className="bg-white p-6 w-full max-w-3xl max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()} data-testid="new-campaign-modal">
            <h3 className="font-display text-2xl mb-4">New Campaign</h3>
            <div className="space-y-3">
              <input className="k-input" placeholder="Campaign name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="campaign-name-input" />
              <textarea className="k-input" placeholder="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
              <div>
                <label className="text-[10px] uppercase tracking-widest text-neutral-500 mb-2 block">Channels</label>
                <div className="flex gap-2 flex-wrap">
                  {CHANNELS.map((ch) => (
                    <button key={ch} type="button" onClick={() => toggleChannel(ch)} className={`pill ${form.channels.includes(ch) ? "kazo-bg-burgundy text-white" : "pill-neutral"}`} data-testid={`channel-${ch}`}>{ch}</button>
                  ))}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <select className="k-input" value={form.audience_type} onChange={(e) => setForm({ ...form, audience_type: e.target.value, audience_filter: {} })} data-testid="audience-type-select">
                  <option value="all">Entire base</option>
                  <option value="segment">From Segment Builder</option>
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
                {form.audience_type === "tier" && (
                  <select className="k-input" value={form.audience_filter?.tier || ""} onChange={(e) => setForm({ ...form, audience_filter: { tier: e.target.value } })}>
                    <option value="">Select tier</option>
                    <option value="silver">Silver</option><option value="gold">Gold</option><option value="platinum">Platinum</option><option value="diamond">Diamond</option>
                  </select>
                )}
                {form.audience_type === "city" && (
                  <input className="k-input" placeholder="City" value={form.audience_filter?.city || ""} onChange={(e) => setForm({ ...form, audience_filter: { city: e.target.value } })} />
                )}
                {form.audience_type === "cohort" && (
                  <select className="k-input" value={form.audience_filter?.cohort || ""} onChange={(e) => setForm({ ...form, audience_filter: { cohort: e.target.value } })}>
                    <option value="">Select cohort</option>
                    <option value="high_value">High-value</option><option value="churn_risk">Churn risk</option><option value="new">New customers</option><option value="vip">VIP (Platinum/Diamond)</option>
                  </select>
                )}
              </div>

              {/* Karix Template picker for real sends */}
              <div className="border border-neutral-200 rounded p-3 bg-neutral-50" data-testid="campaign-template-select">
                <div className="flex items-center justify-between mb-2">
                  <label className="text-[10px] uppercase tracking-widest text-neutral-700 font-medium flex items-center gap-1">
                    <Send className="w-3 h-3" /> Send via Karix template (real send)
                  </label>
                  {form.template_id && (
                    <button type="button" onClick={() => setForm({ ...form, template_id: "" })} className="text-[10px] text-rose-600 hover:underline">Clear</button>
                  )}
                </div>
                {compatibleTemplates.length === 0 ? (
                  <div className="text-xs text-neutral-500" data-testid="campaign-template-empty">
                    No active templates for selected channels — create one in <a href="/admin/communications/templates" className="underline text-burgundy">Templates</a>. Without a template the campaign will only generate simulated metrics.
                  </div>
                ) : (
                  <select className="k-input" value={form.template_id} onChange={(e) => setForm({ ...form, template_id: e.target.value })} data-testid="campaign-template-dropdown">
                    <option value="">— Simulated metrics only (no real send) —</option>
                    {compatibleTemplates.map((t) => (
                      <option key={t.id} value={t.id}>
                        {`${t.name} · ${t.channel.toUpperCase()}${t.channel !== "sms" ? ` · WABA ${t.waba_approval_status || "pending"}` : ""}`}
                      </option>
                    ))}
                  </select>
                )}
                {form.template_id && (
                  <div className="text-[10px] text-emerald-700 mt-1">
                    ✓ This campaign will actually send messages via Karix when launched.
                  </div>
                )}
              </div>

              <textarea className="k-input" placeholder="Optional preview / fallback body (only used if no Karix template above)" value={form.message_template} onChange={(e) => setForm({ ...form, message_template: e.target.value })} data-testid="message-template-input" />

              <div className="grid grid-cols-2 gap-3">
                <select className="k-input" value={form.coupon_code} onChange={(e) => setForm({ ...form, coupon_code: e.target.value })} data-testid="coupon-select">
                  <option value="">No coupon</option>
                  {coupons.map((c) => <option key={c.id} value={c.code}>{`${c.code} · ${c.name}`}</option>)}
                </select>
                <input
                  className="k-input"
                  type="number"
                  min="1"
                  max="500000"
                  placeholder="Send limit (safety cap)"
                  value={form.send_limit}
                  onChange={(e) => setForm({ ...form, send_limit: parseInt(e.target.value, 10) || 50000 })}
                  data-testid="send-limit-input"
                />
              </div>

              <div className="flex justify-end gap-2 mt-2">
                <button className="k-btn k-btn-ghost" onClick={() => setShow(false)}>Cancel</button>
                <button className="k-btn kazo-bg-burgundy" onClick={create} data-testid="campaign-create-btn">Create as draft</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
