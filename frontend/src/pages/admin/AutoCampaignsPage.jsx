import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import {
  Cake, RotateCcw, ZapOff, Sparkles, Save, Loader2, Play,
  Eye, CheckCircle2, AlertCircle, Calendar,
} from "lucide-react";
import { PageHeader } from "./_shared";
import { fmtNum, fmtDate } from "@/lib/format";

const CAT_ICON = {
  lifecycle: Cake,
  winback: RotateCcw,
  default: Sparkles,
};

const CAT_LABEL = {
  lifecycle: "Lifecycle",
  winback: "Win-back",
};

const CAT_ORDER = ["lifecycle", "winback"];

function RuleCard({ rule, templates, onUpdate, onPreview, onRunNow }) {
  const Icon = CAT_ICON[rule.category] || CAT_ICON.default;
  const [enabled, setEnabled] = useState(rule.enabled);
  const [templateId, setTemplateId] = useState(rule.template_id || "");
  const [dailyCap, setDailyCap] = useState(rule.daily_cap || 1000);
  const [saving, setSaving] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [previewData, setPreviewData] = useState(null);
  const [running, setRunning] = useState(false);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    setEnabled(rule.enabled);
    setTemplateId(rule.template_id || "");
    setDailyCap(rule.daily_cap || 1000);
    setDirty(false);
  }, [rule.rule_key, rule.enabled, rule.template_id, rule.daily_cap]);

  const onChange = (fn) => {
    fn();
    setDirty(true);
  };

  const save = async () => {
    setSaving(true);
    try {
      await api.patch(`/auto-campaigns/rules/${rule.key}`, {
        enabled,
        template_id: templateId || null,
        daily_cap: dailyCap,
      });
      toast.success(`"${rule.label}" updated`);
      setDirty(false);
      onUpdate && onUpdate();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const preview = async () => {
    setPreviewing(true);
    setPreviewData(null);
    try {
      const r = await api.post(`/auto-campaigns/rules/${rule.key}/preview`);
      setPreviewData(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Preview failed");
    } finally {
      setPreviewing(false);
    }
  };

  const runNow = async (dryRun) => {
    if (!templateId && !dryRun) { toast.error("Pick a template first"); return; }
    if (!dryRun && !window.confirm(`Run "${rule.label}" now? This will send REAL messages via Karix.`)) return;
    setRunning(true);
    try {
      const r = await api.post(`/auto-campaigns/rules/${rule.key}/run`, null, { params: { dry_run: dryRun } });
      const d = r.data;
      if (d.skipped) {
        toast.info(`Skipped: ${d.skipped}`);
      } else {
        toast.success(`${dryRun ? "DRY-RUN: " : ""}Fired ${fmtNum(d.fired || 0)} · skipped ${fmtNum(d.skipped_cooldown || 0)} · failed ${fmtNum(d.failed || 0)}`);
      }
      onUpdate && onUpdate();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Run failed");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className={`border rounded-lg p-4 ${enabled ? "border-emerald-200 bg-emerald-50/30" : "border-neutral-200 bg-white"}`} data-testid={`rule-card-${rule.key}`}>
      <div className="flex items-start gap-3">
        <div className={`p-2 rounded ${enabled ? "bg-emerald-100" : "bg-neutral-100"}`}>
          <Icon className={`w-4 h-4 ${enabled ? "text-emerald-700" : "text-neutral-500"}`} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <div className="font-display text-base font-medium">{rule.label}</div>
            {enabled ? (
              <span className="text-[10px] uppercase tracking-widest text-emerald-700 bg-emerald-100 border border-emerald-200 px-1.5 py-0.5 rounded">ON</span>
            ) : (
              <span className="text-[10px] uppercase tracking-widest text-neutral-500 bg-neutral-100 border border-neutral-200 px-1.5 py-0.5 rounded">OFF</span>
            )}
          </div>
          <div className="text-xs text-neutral-600 mb-3">{rule.description}</div>

          <div className="space-y-2">
            <label className="flex items-center gap-2 text-xs cursor-pointer">
              <input
                type="checkbox"
                checked={enabled}
                onChange={() => onChange(() => setEnabled((v) => !v))}
                data-testid={`rule-enable-${rule.key}`}
              />
              <span>Enabled (will fire every day at 10:00 IST)</span>
            </label>

            <div>
              <label className="text-[10px] uppercase tracking-widest text-neutral-500">Karix Template</label>
              <select
                className="w-full border border-neutral-300 rounded px-2 py-1.5 text-xs mt-0.5"
                value={templateId}
                onChange={(e) => onChange(() => setTemplateId(e.target.value))}
                data-testid={`rule-template-${rule.key}`}
              >
                <option value="">— Pick a template —</option>
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} · {t.channel.toUpperCase()}
                    {t.channel !== "sms" ? ` · WABA ${t.waba_approval_status || "pending"}` : ""}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex items-center gap-2">
              <div className="flex-1">
                <label className="text-[10px] uppercase tracking-widest text-neutral-500">Daily Cap</label>
                <input
                  type="number"
                  min="1"
                  max="100000"
                  className="w-full border border-neutral-300 rounded px-2 py-1.5 text-xs mt-0.5"
                  value={dailyCap}
                  onChange={(e) => onChange(() => setDailyCap(parseInt(e.target.value, 10) || 1000))}
                />
              </div>
              <div className="flex-1">
                <label className="text-[10px] uppercase tracking-widest text-neutral-500">Cooldown</label>
                <div className="text-xs text-neutral-700 mt-1.5">{rule.cooldown_days} days per customer</div>
              </div>
            </div>

            {rule.last_run_at && (
              <div className="text-[10px] text-neutral-500 border-t border-neutral-100 pt-2 mt-2">
                <Calendar className="w-3 h-3 inline mr-1" />
                Last ran {fmtDate(rule.last_run_at)} · fired {fmtNum(rule.last_run_fired)} · skipped {fmtNum(rule.last_run_skipped)}
              </div>
            )}

            <div className="flex gap-1.5 pt-2 flex-wrap">
              <button
                onClick={save}
                disabled={!dirty || saving}
                className="text-xs flex items-center gap-1 px-3 py-1.5 bg-neutral-900 text-white rounded disabled:opacity-40"
                data-testid={`rule-save-${rule.key}`}
              >
                {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
                Save
              </button>
              <button
                onClick={preview}
                disabled={previewing}
                className="text-xs flex items-center gap-1 px-3 py-1.5 border border-neutral-300 rounded hover:bg-neutral-50 disabled:opacity-40"
                data-testid={`rule-preview-${rule.key}`}
              >
                {previewing ? <Loader2 className="w-3 h-3 animate-spin" /> : <Eye className="w-3 h-3" />}
                Preview audience
              </button>
              <button
                onClick={() => runNow(true)}
                disabled={running || !enabled}
                className="text-xs flex items-center gap-1 px-3 py-1.5 border border-amber-300 text-amber-700 rounded hover:bg-amber-50 disabled:opacity-40"
                data-testid={`rule-dryrun-${rule.key}`}
              >
                <Play className="w-3 h-3" />
                Dry run
              </button>
              <button
                onClick={() => runNow(false)}
                disabled={running || !enabled || !templateId}
                className="text-xs flex items-center gap-1 px-3 py-1.5 bg-burgundy text-white border border-burgundy rounded disabled:opacity-40"
                style={{ backgroundColor: "#9b2c2c" }}
                data-testid={`rule-run-${rule.key}`}
              >
                {running ? <Loader2 className="w-3 h-3 animate-spin" /> : <ZapOff className="w-3 h-3" />}
                Run live now
              </button>
            </div>

            {previewData && (
              <div className="mt-3 p-3 bg-white border border-neutral-200 rounded text-xs">
                <div className="font-medium mb-1.5">
                  Audience: <span className="text-emerald-700">{fmtNum(previewData.fireable_now)}</span> fireable
                  · <span className="text-neutral-500">{fmtNum(previewData.on_cooldown)} on cooldown</span>
                  · {fmtNum(previewData.audience_total)} total matched
                </div>
                {previewData.samples?.length > 0 && (
                  <div className="text-[10px] text-neutral-600">
                    Sample: {previewData.samples.slice(0, 5).map((s) => `${s.name || s.mobile} (${s.tier || "—"})`).join(" · ")}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function AutoCampaignsPage() {
  const [rules, setRules] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [runningAll, setRunningAll] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [r, t] = await Promise.all([
        api.get("/auto-campaigns/rules"),
        api.get("/templates", { params: { status: "active" } }).catch(() => ({ data: [] })),
      ]);
      setRules(r.data.rules || []);
      setTemplates(Array.isArray(t.data) ? t.data : []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Load failed");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const runAll = async (dryRun) => {
    if (!dryRun && !window.confirm("Run ALL enabled auto-campaigns now? This will send REAL messages via Karix.")) return;
    setRunningAll(true);
    try {
      const r = await api.post("/auto-campaigns/run-all", null, { params: { dry_run: dryRun } });
      const total = r.data.total_fired || 0;
      toast.success(`${dryRun ? "DRY-RUN: " : ""}Total fired ${fmtNum(total)} across ${r.data.rules?.length || 0} rules`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Run failed");
    } finally {
      setRunningAll(false);
    }
  };

  const enabledCount = rules.filter((r) => r.enabled).length;
  const groupedRules = CAT_ORDER.map((cat) => ({
    cat,
    label: CAT_LABEL[cat] || cat,
    items: rules.filter((r) => r.category === cat),
  })).filter((g) => g.items.length > 0);

  return (
    <div data-testid="auto-campaigns-page">
      <PageHeader
        title="Auto Campaigns"
        subtitle="DAILY TRIGGERS · KARIX-POWERED"
        actions={
          <div className="flex gap-2">
            <button
              onClick={() => runAll(true)}
              disabled={runningAll || enabledCount === 0}
              className="k-btn k-btn-ghost"
              data-testid="run-all-dryrun"
            >
              {runningAll ? <Loader2 className="w-4 h-4 animate-spin" /> : <Eye className="w-4 h-4" />}
              Dry-run all
            </button>
            <button
              onClick={() => runAll(false)}
              disabled={runningAll || enabledCount === 0}
              className="k-btn kazo-bg-burgundy"
              data-testid="run-all-live"
            >
              {runningAll ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              Run all now
            </button>
          </div>
        }
      />
      <div className="p-8 space-y-6">
        <div className="bg-white border border-neutral-200 rounded-lg p-4 flex items-center justify-between flex-wrap gap-3">
          <div>
            <div className="font-display text-lg">
              {enabledCount > 0 ? (
                <><CheckCircle2 className="w-5 h-5 inline text-emerald-600 mr-1" /> {enabledCount} of {rules.length} rules enabled</>
              ) : (
                <><AlertCircle className="w-5 h-5 inline text-amber-600 mr-1" /> No rules enabled yet</>
              )}
            </div>
            <div className="text-xs text-neutral-500 mt-1">
              Scheduler runs every day at 10:00 IST. Each rule respects its per-customer cooldown.
            </div>
          </div>
          {enabledCount === 0 && (
            <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
              Enable at least one rule + pick an approved Karix template to start auto-sending.
            </div>
          )}
        </div>

        {loading && (
          <div className="text-center py-10 text-neutral-500 flex items-center justify-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading rules…
          </div>
        )}

        {!loading && groupedRules.map((g) => (
          <div key={g.cat}>
            <div className="text-[10px] uppercase tracking-[0.18em] text-neutral-500 mb-3">{g.label}</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {g.items.map((r) => (
                <RuleCard
                  key={r.key}
                  rule={r}
                  templates={templates}
                  onUpdate={load}
                  data-testid={`rule-${r.key}`}
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
