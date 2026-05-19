/* Communication Templates — SMS / WhatsApp / RCS with AI suggest + test send. */
import { useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { PageHeader, SectionHeading, StatusPill } from "../_shared";
import { fmtDateTime } from "@/lib/format";
import {
  Plus, Edit, Trash2, Send, Sparkles, X, Wand2, MessageSquare, Smartphone, Radio,
} from "lucide-react";

const CHANNELS = [
  { key: "sms", label: "SMS", icon: Smartphone, color: "#1E3A8A" },
  { key: "whatsapp", label: "WhatsApp", icon: MessageSquare, color: "#047857" },
  { key: "rcs", label: "RCS", icon: Radio, color: "#B45309" },
];

const EVENTS = [
  { key: "none", label: "On-demand only" },
  { key: "purchase", label: "On purchase" },
  { key: "coupon_issued", label: "Coupon issued" },
  { key: "points_earned", label: "Points earned" },
  { key: "tier_upgrade", label: "Tier upgrade" },
  { key: "birthday", label: "Birthday" },
  { key: "win_back", label: "Win-back" },
  { key: "abandoned_visit", label: "Abandoned visit" },
  { key: "campaign_bulk", label: "Campaign bulk" },
];

const COMMON_VARS = [
  { key: "name", label: "Name" }, { key: "amount", label: "Amount" },
  { key: "bill_no", label: "Bill #" }, { key: "store_name", label: "Store" },
  { key: "coupon_code", label: "Coupon" }, { key: "points_earned", label: "Points earned" },
  { key: "points_balance", label: "Points balance" }, { key: "tier", label: "Tier" },
];

export default function TemplatesPage() {
  const [activeCh, setActiveCh] = useState("sms");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get("/templates", { params: { channel: activeCh } });
      setRows(r.data.rows);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [activeCh]);

  const remove = async (id) => {
    if (!confirm("Delete this template?")) return;
    await api.delete(`/templates/${id}`);
    toast.success("Template deleted");
    load();
  };

  const channel = CHANNELS.find((c) => c.key === activeCh);

  return (
    <div data-testid="templates-page">
      <PageHeader
        title="Communication Templates"
        subtitle="SMS · WHATSAPP · RCS · POWERED BY KARIX"
        actions={
          <button
            className="k-btn kazo-bg-burgundy k-btn-sm"
            onClick={() => setEditing({ channel: activeCh, body: "", event_trigger: "none", status: "draft", variables: [] })}
            data-testid="new-template-btn"
          >
            <Plus className="w-3.5 h-3.5" /> New {channel.label} Template
          </button>
        }
      />

      <div className="p-8 space-y-6">
        <div className="k-tabs" data-testid="channel-tabs">
          {CHANNELS.map((c) => (
            <button
              key={c.key}
              onClick={() => setActiveCh(c.key)}
              className={activeCh === c.key ? "active" : ""}
              data-testid={`tab-${c.key}`}
            >
              <span className="inline-flex items-center gap-2">
                <c.icon className="w-3.5 h-3.5" /> {c.label}
              </span>
            </button>
          ))}
        </div>

        <div className="chart-card p-5" data-accent="indigo">
          <SectionHeading
            eyebrow={`${rows.length} TEMPLATES`}
            title={`${channel.label} templates`}
            accent="indigo"
          />
          {loading ? <div className="py-10 text-neutral-500 text-sm">Loading…</div> :
            rows.length === 0 ? (
              <div className="py-12 text-center text-neutral-500 text-sm">
                No {channel.label} templates yet.<br/>
                <button className="k-btn k-btn-outline mt-4" onClick={() => setEditing({ channel: activeCh, body: "", event_trigger: "none", status: "draft", variables: [] })}>
                  <Plus className="w-3.5 h-3.5" /> Create your first
                </button>
              </div>
            ) : (
              <table className="data-table">
                <thead>
                  <tr><th>Name</th><th>Event Trigger</th><th>Status</th><th>Last updated</th><th>Body preview</th><th></th></tr>
                </thead>
                <tbody>
                  {rows.map((t) => (
                    <tr key={t.id} className="hover:bg-neutral-50 cursor-pointer" onClick={() => setEditing(t)} data-testid={`row-${t.id}`}>
                      <td className="font-medium">{t.name}</td>
                      <td className="text-xs"><span className="pill pill-neutral">{(EVENTS.find(e=>e.key===t.event_trigger)?.label) || t.event_trigger}</span></td>
                      <td><StatusPill status={t.status} /></td>
                      <td className="text-xs text-neutral-500">{fmtDateTime(t.updated_at)}</td>
                      <td className="text-xs text-neutral-700 max-w-xl truncate">{t.body}</td>
                      <td className="text-right">
                        <button onClick={(e) => { e.stopPropagation(); remove(t.id); }} className="text-rose-700 hover:text-rose-900" data-testid={`del-${t.id}`}>
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
        </div>

        <div className="text-xs text-neutral-500">
          <strong>Mustache variables</strong>: use {"{{name}}"}, {"{{amount}}"}, {"{{bill_no}}"}, etc. They will be replaced live at send time.
        </div>
      </div>

      {editing && (
        <TemplateEditor
          template={editing}
          onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); load(); }}
        />
      )}
    </div>
  );
}

function TemplateEditor({ template, onClose, onSaved }) {
  const isNew = !template.id;
  const [form, setForm] = useState({ ...template });
  const [saving, setSaving] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [brief, setBrief] = useState("");
  const [testMobile, setTestMobile] = useState("");
  const [testParams, setTestParams] = useState({});
  const [testSending, setTestSending] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const update = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const insertVar = (key) => {
    const tag = `{{${key}}}`;
    update("body", (form.body || "") + tag);
  };

  const aiSuggest = async () => {
    if (!brief.trim()) return toast.error("Add a brief first");
    setAiBusy(true);
    try {
      const res = await api.post("/templates/ai-suggest", {
        channel: form.channel, event_trigger: form.event_trigger, brief,
      });
      update("body", res.data.body);
      update("variables", res.data.variables || []);
      toast.success("AI draft inserted");
    } catch (e) { toast.error(e?.response?.data?.detail || "AI failed"); }
    finally { setAiBusy(false); }
  };

  const aiImprove = async () => {
    if (!form.body) return toast.error("Body is empty");
    setAiBusy(true);
    try {
      const res = await api.post("/templates/ai-improve", {
        channel: form.channel, current_body: form.body,
        intent: brief || "make crisper, more conversion-focused",
      });
      update("body", res.data.body);
      toast.success("AI improved");
    } catch (e) { toast.error(e?.response?.data?.detail || "AI failed"); }
    finally { setAiBusy(false); }
  };

  const save = async () => {
    if (!form.name?.trim()) return toast.error("Name required");
    if (!form.body?.trim()) return toast.error("Body required");
    setSaving(true);
    try {
      if (isNew) await api.post("/templates", form);
      else await api.patch(`/templates/${form.id}`, form);
      toast.success(isNew ? "Created" : "Saved");
      onSaved();
    } catch (e) { toast.error(e?.response?.data?.detail || "Save failed"); }
    finally { setSaving(false); }
  };

  const testSend = async () => {
    if (!form.id) return toast.error("Save the template first");
    if (!testMobile) return toast.error("Mobile number required");
    setTestSending(true);
    setTestResult(null);
    try {
      const r = await api.post(`/templates/${form.id}/test-send`, {
        mobile: testMobile, params: testParams,
      });
      setTestResult(r.data);
      if (r.data.ok) toast.success("Sent");
      else toast.error("Provider returned error");
    } catch (e) { toast.error(e?.response?.data?.detail || "Send failed"); }
    finally { setTestSending(false); }
  };

  // Live preview
  const preview = (form.body || "").replace(/\{\{\s*([\w_]+)\s*\}\}/g, (_, k) => {
    const found = (form.variables || []).find((v) => v.key === k);
    return found?.example || `[${k}]`;
  });

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white w-full max-w-5xl max-h-[92vh] overflow-y-auto" onClick={(e) => e.stopPropagation()} data-testid="template-editor">
        <div className="p-5 border-b border-black/10 flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-0.5">
              {isNew ? "NEW" : "EDIT"} · {form.channel.toUpperCase()}
            </div>
            <h3 className="font-display text-2xl">{isNew ? "New template" : form.name}</h3>
          </div>
          <button onClick={onClose} className="text-neutral-500 hover:text-black" data-testid="editor-close"><X className="w-5 h-5" /></button>
        </div>

        <div className="p-5 grid lg:grid-cols-[2fr_1fr] gap-5">
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <label className="text-xs">
                <div className="text-neutral-500 uppercase tracking-widest mb-1 text-[10px]">Name</div>
                <input className="k-input" value={form.name || ""} onChange={(e) => update("name", e.target.value)} data-testid="t-name" />
              </label>
              <label className="text-xs">
                <div className="text-neutral-500 uppercase tracking-widest mb-1 text-[10px]">Event Trigger</div>
                <select className="k-input" value={form.event_trigger} onChange={(e) => update("event_trigger", e.target.value)} data-testid="t-event">
                  {EVENTS.map((e) => <option key={e.key} value={e.key}>{e.label}</option>)}
                </select>
              </label>
              {form.channel !== "sms" && (
                <label className="text-xs col-span-2">
                  <div className="text-neutral-500 uppercase tracking-widest mb-1 text-[10px]">Karix Approved Template ID (waba/rcs)</div>
                  <input className="k-input" value={form.waba_template_id || ""} onChange={(e) => update("waba_template_id", e.target.value)} placeholder="e.g. testing_fundle" data-testid="t-waba-id" />
                </label>
              )}
              {form.channel === "sms" && (
                <>
                  <label className="text-xs">
                    <div className="text-neutral-500 uppercase tracking-widest mb-1 text-[10px]">Sender ID</div>
                    <input className="k-input" value={form.sender_id || ""} onChange={(e) => update("sender_id", e.target.value)} placeholder="KAZOIN" data-testid="t-sender" />
                  </label>
                  <label className="text-xs">
                    <div className="text-neutral-500 uppercase tracking-widest mb-1 text-[10px]">DLT Entity ID (optional)</div>
                    <input className="k-input" value={form.dlt_entity_id || ""} onChange={(e) => update("dlt_entity_id", e.target.value)} data-testid="t-dlt" />
                  </label>
                </>
              )}
              <label className="text-xs">
                <div className="text-neutral-500 uppercase tracking-widest mb-1 text-[10px]">Status</div>
                <select className="k-input" value={form.status} onChange={(e) => update("status", e.target.value)} data-testid="t-status">
                  <option value="draft">Draft</option>
                  <option value="active">Active</option>
                  <option value="archived">Archived</option>
                </select>
              </label>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1">
                <div className="text-neutral-500 uppercase tracking-widest text-[10px]">Message body</div>
                <div className="text-[10px] text-neutral-400 font-mono">{(form.body || "").length} chars</div>
              </div>
              <textarea
                className="k-input"
                rows={5}
                value={form.body || ""}
                onChange={(e) => update("body", e.target.value)}
                placeholder="Hi {{name}}, ..."
                data-testid="t-body"
              />
              <div className="flex flex-wrap gap-1.5 mt-2">
                {COMMON_VARS.map((v) => (
                  <button key={v.key} onClick={() => insertVar(v.key)} className="px-2 py-0.5 text-[10px] uppercase tracking-widest border border-black/15 hover:border-black/40 font-mono">
                    +{v.key}
                  </button>
                ))}
              </div>
            </div>

            {/* AI panel */}
            <div className="bg-gradient-to-br from-[#1E3A8A]/5 to-white border border-[#1E3A8A]/20 p-4" data-testid="ai-panel">
              <div className="flex items-center gap-2 mb-2">
                <Sparkles className="w-4 h-4" style={{ color: "#1E3A8A" }} />
                <div className="text-[10px] uppercase tracking-[0.2em] text-[#1E3A8A] font-semibold">FUNDLE BRAIN · COPYWRITER</div>
              </div>
              <textarea className="k-input mb-2" rows={2} placeholder="Brief: e.g. 'thank for purchase, suggest matching accessories'" value={brief} onChange={(e) => setBrief(e.target.value)} data-testid="ai-brief" />
              <div className="flex gap-2">
                <button onClick={aiSuggest} disabled={aiBusy} className="k-btn k-btn-outline k-btn-sm" data-testid="ai-generate">
                  <Wand2 className="w-3.5 h-3.5" /> {aiBusy ? "Generating…" : "Generate from brief"}
                </button>
                <button onClick={aiImprove} disabled={aiBusy || !form.body} className="k-btn k-btn-outline k-btn-sm" data-testid="ai-improve">
                  <Sparkles className="w-3.5 h-3.5" /> Improve current
                </button>
              </div>
            </div>
          </div>

          <div className="space-y-4">
            {/* Preview */}
            <div className="border border-black/10" data-testid="preview-panel">
              <div className="bg-neutral-900 text-white px-3 py-2 text-[10px] uppercase tracking-widest">LIVE PREVIEW</div>
              <div className="bg-neutral-50 p-4 text-sm font-mono whitespace-pre-wrap min-h-[120px]">{preview || <span className="text-neutral-400">Empty</span>}</div>
            </div>

            {/* Test send */}
            <div className="border border-emerald-200 bg-emerald-50/40 p-4" data-testid="test-send-panel">
              <div className="text-[10px] uppercase tracking-[0.2em] text-emerald-800 font-semibold mb-2">TEST SEND</div>
              <input className="k-input mb-2" placeholder="Mobile e.g. 9876543210" value={testMobile} onChange={(e) => setTestMobile(e.target.value)} data-testid="test-mobile" />
              {(form.variables || []).map((v) => (
                <input key={v.key} className="k-input mb-2 text-xs" placeholder={`${v.label} (e.g. ${v.example})`} value={testParams[v.key] || ""} onChange={(e) => setTestParams({ ...testParams, [v.key]: e.target.value })} />
              ))}
              <button onClick={testSend} disabled={testSending || !form.id} className="k-btn kazo-bg-burgundy k-btn-sm w-full" data-testid="test-send-btn">
                <Send className="w-3.5 h-3.5" /> {testSending ? "Sending…" : "Send test now"}
              </button>
              {!form.id && <div className="text-[10px] text-neutral-500 mt-1">Save the template before testing</div>}
              {testResult && (
                <div className={`mt-2 p-2 text-xs font-mono ${testResult.ok ? "bg-emerald-100" : "bg-rose-100"}`}>
                  {testResult.ok ? "✓ " : "✗ "}{testResult.response || testResult.error || JSON.stringify(testResult)}
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="p-5 border-t border-black/10 flex justify-end gap-2">
          <button onClick={onClose} className="k-btn k-btn-ghost">Cancel</button>
          <button onClick={save} disabled={saving} className="k-btn kazo-bg-burgundy" data-testid="save-template-btn">
            {saving ? "Saving…" : isNew ? "Create template" : "Save changes"}
          </button>
        </div>
      </div>
    </div>
  );
}
