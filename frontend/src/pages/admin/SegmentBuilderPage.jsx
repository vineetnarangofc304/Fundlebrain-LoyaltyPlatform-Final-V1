import { useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Sparkles, Save, RefreshCw, Trash2, Loader2 } from "lucide-react";
import { PageHeader, SectionHeading, KPICard } from "./_shared";
import { FilterGroup, newRule } from "./_segment_group";
import CohortLibrary from "./_cohort_library";

const fmtNum = (v) => v == null ? "—" : Number(v).toLocaleString("en-IN");
const fmtINR = (v) => v == null ? "—" : `₹${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

function compile(group) {
  const out = { op: group.op, rules: [] };
  for (const r of group.rules) {
    if (r.kind === "group") {
      out.rules.push(compile(r));
    } else if (r.field && r.value != null && (Array.isArray(r.value) ? r.value.length : true)) {
      out.rules.push({ field: r.field, operator: r.operator, value: r.value });
    }
  }
  return out;
}

export default function SegmentBuilderPage() {
  const [schema, setSchema] = useState(null);
  const [root, setRoot] = useState({ kind: "group", op: "AND", rules: [newRule()] });
  const [preview, setPreview] = useState(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState([]);
  const [nameDialog, setNameDialog] = useState(false);
  const [segmentName, setSegmentName] = useState("");
  const [segmentDescription, setSegmentDescription] = useState("");
  const debounceRef = useRef(null);

  useEffect(() => {
    api.get("/segments/filter-schema")
      .then((r) => setSchema(r.data.schema))
      .catch(() => toast.error("Failed to load filter schema"));
    reloadSaved();
  }, []);

  const reloadSaved = async () => {
    try {
      const r = await api.get("/segments/");
      setSaved(r.data.rows || []);
    } catch { /* ignore */ }
  };

  const runPreview = async () => {
    setLoadingPreview(true);
    try {
      const compiled = compile(root);
      const r = await api.post("/segments/preview", { tree: compiled });
      setPreview(r.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Preview failed");
    } finally {
      setLoadingPreview(false);
    }
  };

  useEffect(() => {
    if (!schema) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(runPreview, 500);
    return () => debounceRef.current && clearTimeout(debounceRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [root, schema]);

  const saveSegment = async () => {
    if (!segmentName.trim()) { toast.error("Name required"); return; }
    setSaving(true);
    try {
      const compiled = compile(root);
      await api.post("/segments/", { name: segmentName, description: segmentDescription, tree: compiled });
      toast.success(`Segment "${segmentName}" saved`);
      setNameDialog(false);
      setSegmentName("");
      setSegmentDescription("");
      reloadSaved();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const loadSegment = (s) => {
    const wrap = (node) => {
      if (!node) return { kind: "group", op: "AND", rules: [newRule()] };
      if (node.rules) {
        return { kind: "group", op: node.op || "AND", rules: node.rules.map(wrap) };
      }
      return { kind: "rule", field: node.field, operator: node.operator, value: node.value };
    };
    let wrapped = wrap(s.tree);
    if (wrapped.kind !== "group") {
      wrapped = { kind: "group", op: "AND", rules: [wrapped] };
    }
    setRoot(wrapped);
    toast.success(`Loaded "${s.name}"`);
  };

  const deleteSegment = async (s) => {
    if (!window.confirm(`Delete segment "${s.name}"?`)) return;
    try {
      await api.delete(`/segments/${s.id}`);
      toast.success("Deleted");
      reloadSaved();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Delete failed");
    }
  };

  if (!schema) return <div className="p-10 text-neutral-500">Loading filter schema…</div>;

  return (
    <div data-testid="segment-builder">
      <PageHeader
        title="Segment Builder"
        subtitle="CAMPAIGN MANAGER · COHORTS · AND/OR LOGIC"
        actions={
          <>
            <button onClick={runPreview} className="k-btn-outline flex items-center gap-2 text-xs" data-testid="recalc">
              <RefreshCw className={`w-3.5 h-3.5 ${loadingPreview ? "animate-spin" : ""}`} /> Recalc
            </button>
            <button onClick={() => setNameDialog(true)} className="k-btn flex items-center gap-2 text-xs" data-testid="save-segment">
              <Save className="w-3.5 h-3.5" /> Save segment
            </button>
          </>
        }
      />

      <div className="p-4 md:p-8 grid grid-cols-1 lg:grid-cols-4 gap-6">
        <div className="lg:col-span-1 space-y-4">
          <div className="chart-card p-4" data-accent="amber">
            <SectionHeading eyebrow="COHORT LIBRARY" title="Pre-built segments" accent="amber" />
            <div className="mt-3">
              <CohortLibrary
                onLoad={({ name, tree }) => {
                  const wrap = (node) => {
                    if (!node) return { kind: "group", op: "AND", rules: [newRule()] };
                    if (node.rules) {
                      return { kind: "group", op: node.op || "AND", rules: node.rules.map(wrap) };
                    }
                    return { kind: "rule", field: node.field, operator: node.operator, value: node.value };
                  };
                  // Ensure root is always a group, wrap bare rule in AND-group
                  let wrapped = wrap(tree);
                  if (wrapped.kind !== "group") {
                    wrapped = { kind: "group", op: "AND", rules: [wrapped] };
                  }
                  setRoot(wrapped);
                  setSegmentName(name);
                }}
              />
            </div>
          </div>
        </div>

        <div className="lg:col-span-2 space-y-4">
          <div className="chart-card p-5" data-accent="indigo">
            <SectionHeading eyebrow="FILTERS" title="Build your audience" accent="indigo" />
            <div className="mt-4">
              <FilterGroup group={root} schema={schema} onChange={setRoot} />
            </div>
          </div>

          <div className="chart-card p-5" data-accent="slate">
            <SectionHeading eyebrow="SAVED SEGMENTS" title="Reusable cohorts" accent="slate" />
            {saved.length === 0 && <div className="text-xs text-neutral-500 mt-3">No saved segments yet</div>}
            <div className="mt-3 space-y-2">
              {saved.map((s) => (
                <div key={s.id} className="flex items-center justify-between p-3 border border-neutral-200 rounded-md hover:border-neutral-900 transition" data-testid={`saved-${s.id}`}>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium truncate">{s.name}</div>
                    {s.description && <div className="text-xs text-neutral-500 truncate">{s.description}</div>}
                    <div className="text-[11px] text-neutral-400 mt-1">
                      {fmtNum(s.matched_total)} matched · {fmtNum(s.reach && s.reach.whatsapp)} WA · {fmtNum(s.reach && s.reach.sms)} SMS · {s.created_by_name || s.created_by}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 ml-3 shrink-0">
                    <button type="button" onClick={() => loadSegment(s)} className="text-xs px-2 py-1 border border-neutral-300 rounded hover:bg-neutral-50" data-testid={`load-${s.id}`}>Load</button>
                    <button type="button" onClick={() => deleteSegment(s)} className="text-xs px-2 py-1 text-rose-600 hover:bg-rose-50 rounded" data-testid={`delete-${s.id}`}>
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="chart-card p-5 lg:sticky lg:top-4" data-accent="burgundy">
            <SectionHeading eyebrow="LIVE PREVIEW" title="Audience snapshot" accent="burgundy" />
            <div className="mt-4 grid grid-cols-2 gap-3">
              <KPICard label="Matched" value={fmtNum(preview && preview.matched_total)} accent="burgundy" testid="kpi-matched" />
              <KPICard label="WhatsApp" value={fmtNum(preview && preview.reach && preview.reach.whatsapp)} accent="teal" testid="kpi-wa" />
              <KPICard label="SMS" value={fmtNum(preview && preview.reach && preview.reach.sms)} accent="indigo" testid="kpi-sms" />
              <KPICard label="Email" value={fmtNum(preview && preview.reach && preview.reach.email)} accent="slate" testid="kpi-email" />
            </div>
            {preview && preview.reach && preview.reach.opted_out > 0 && (
              <div className="text-xs text-amber-700 mt-3">⚠ {fmtNum(preview.reach.opted_out)} opted out — excluded from sends</div>
            )}

            {preview && preview.sample && preview.sample.length > 0 && (
              <div className="mt-5">
                <div className="text-[10px] uppercase tracking-widest text-neutral-500 mb-2">SAMPLE MATCHES</div>
                <div className="space-y-1">
                  {preview.sample.map((c) => (
                    <div key={c.id} className="text-xs flex items-center justify-between p-1.5 hover:bg-neutral-50 rounded">
                      <div>
                        <div className="font-medium truncate">{c.name || c.mobile}</div>
                        <div className="text-neutral-500">{c.tier} · {c.visit_count}v · {fmtINR(c.lifetime_spend)}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div className="text-[10px] text-neutral-400 mt-3 italic">Preview updates 500ms after the last edit. Click <strong>Save segment</strong> to persist.</div>
          </div>
        </div>
      </div>

      {nameDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={() => setNameDialog(false)}>
          <div className="bg-white rounded-lg p-6 w-full max-w-md mx-4" onClick={(e) => e.stopPropagation()}>
            <div className="font-display text-xl mb-4 flex items-center gap-2"><Sparkles className="w-5 h-5" /> Save this segment</div>
            <label className="block text-xs uppercase tracking-widest text-neutral-500 mb-1">Name *</label>
            <input value={segmentName} onChange={(e) => setSegmentName(e.target.value)}
                    className="w-full border border-neutral-300 rounded px-3 py-2 text-sm mb-4"
                    placeholder="e.g. Gold + Lucknow + 90d-active"
                    data-testid="segment-name-input" />
            <label className="block text-xs uppercase tracking-widest text-neutral-500 mb-1">Description</label>
            <textarea value={segmentDescription} onChange={(e) => setSegmentDescription(e.target.value)}
                        className="w-full border border-neutral-300 rounded px-3 py-2 text-sm mb-4 h-24"
                        placeholder="optional context for other admins" />
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setNameDialog(false)} className="text-sm px-4 py-2 border border-neutral-300 rounded hover:bg-neutral-50">Cancel</button>
              <button type="button" onClick={saveSegment} disabled={saving} className="k-btn flex items-center gap-2 text-sm disabled:opacity-50" data-testid="confirm-save">
                {saving && <Loader2 className="w-3.5 h-3.5 animate-spin" />} Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
