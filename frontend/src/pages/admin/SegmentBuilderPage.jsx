import { useEffect, useMemo, useRef, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Sparkles, Save, RefreshCw, Trash2, Loader2 } from "lucide-react";
import { PageHeader, SectionHeading } from "./_shared";
import { FilterGroup, newRule } from "./_segment_group";
import CohortLibrary from "./_cohort_library";
import AudienceTable from "./_audience_table";

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

function wrapTree(node) {
  if (!node) return { kind: "group", op: "AND", rules: [newRule()] };
  if (node.rules) {
    return { kind: "group", op: node.op || "AND", rules: node.rules.map(wrapTree) };
  }
  return { kind: "rule", field: node.field, operator: node.operator, value: node.value };
}

function ensureGroupRoot(tree) {
  let wrapped = wrapTree(tree);
  if (wrapped.kind !== "group") wrapped = { kind: "group", op: "AND", rules: [wrapped] };
  return wrapped;
}

export default function SegmentBuilderPage() {
  const [schema, setSchema] = useState(null);
  const [root, setRoot] = useState({ kind: "group", op: "AND", rules: [newRule()] });
  const [saved, setSaved] = useState([]);
  const [saving, setSaving] = useState(false);
  const [nameDialog, setNameDialog] = useState(false);
  const [segmentName, setSegmentName] = useState("");
  const [segmentDescription, setSegmentDescription] = useState("");
  const [activeCohortName, setActiveCohortName] = useState("");

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

  const compiledTree = useMemo(() => compile(root), [root]);

  const saveSegment = async () => {
    if (!segmentName.trim()) { toast.error("Name required"); return; }
    setSaving(true);
    try {
      await api.post("/segments/", { name: segmentName, description: segmentDescription, tree: compiledTree });
      toast.success(`Segment "${segmentName}" saved`);
      setNameDialog(false); setSegmentName(""); setSegmentDescription("");
      reloadSaved();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const loadCohortIntoEditor = ({ name, tree }) => {
    setRoot(ensureGroupRoot(tree));
    setSegmentName(name);
    setActiveCohortName(name);
  };

  const loadSavedSegment = (s) => {
    setRoot(ensureGroupRoot(s.tree));
    setSegmentName(s.name);
    setActiveCohortName(s.name);
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
          <button onClick={() => setNameDialog(true)} className="k-btn flex items-center gap-2 text-xs" data-testid="save-segment">
            <Save className="w-3.5 h-3.5" /> Save segment
          </button>
        }
      />

      <div className="p-4 md:p-8 space-y-6">
        {/* Top row — library + editor side by side */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-1">
            <div className="chart-card p-4" data-accent="amber">
              <SectionHeading eyebrow="COHORT LIBRARY" title="Pre-built segments" accent="amber" />
              <div className="mt-3">
                <CohortLibrary onLoad={loadCohortIntoEditor} />
              </div>
            </div>
          </div>

          <div className="lg:col-span-2 space-y-4">
            <div className="chart-card p-5" data-accent="indigo">
              <SectionHeading eyebrow={activeCohortName ? `EDITING · ${activeCohortName}` : "FILTERS"} title="Build your audience" accent="indigo" />
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
                        {(s.matched_total ?? 0).toLocaleString("en-IN")} matched · {(s.reach && s.reach.whatsapp || 0).toLocaleString("en-IN")} WA · {s.created_by_name || s.created_by}
                      </div>
                    </div>
                    <div className="flex items-center gap-1 ml-3 shrink-0">
                      <button type="button" onClick={() => loadSavedSegment(s)} className="text-xs px-2 py-1 border border-neutral-300 rounded hover:bg-neutral-50" data-testid={`load-${s.id}`}>Load</button>
                      <button type="button" onClick={() => deleteSegment(s)} className="text-xs px-2 py-1 text-rose-600 hover:bg-rose-50 rounded" data-testid={`delete-${s.id}`}>
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Audience table — full width below */}
        <AudienceTable
          tree={compiledTree}
          segmentNameHint={segmentName || activeCohortName}
          onSegmentSaved={reloadSaved}
        />
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
