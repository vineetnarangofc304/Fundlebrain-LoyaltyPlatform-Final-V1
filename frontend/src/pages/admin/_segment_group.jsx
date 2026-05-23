import { Plus, Trash2 } from "lucide-react";
import React from "react";
import { ValueInput } from "./_segment_inputs";

const OP_LABELS = {
  in: "is one of", not_in: "is NOT one of",
  eq: "equals", neq: "not equals",
  gte: "≥", lte: "≤", between: "between",
};

const newRule = () => ({ kind: "rule", field: "", operator: "in", value: null });
const newGroup = () => ({ kind: "group", op: "OR", rules: [newRule()] });

/* One rule row */
function RuleRow({ rule, schema, onChange, onRemove }) {
  let fieldMeta = null;
  for (const cat of Object.values(schema)) {
    const found = cat.fields.find((f) => f.key === rule.field);
    if (found) { fieldMeta = found; break; }
  }

  return (
    <div className="flex flex-wrap items-start gap-2 p-2 bg-neutral-50 rounded border border-neutral-200" data-testid="rule-row">
      <select
        value={rule.field}
        onChange={(e) => onChange({ ...rule, field: e.target.value, operator: "in", value: null })}
        className="border border-neutral-300 rounded px-2 py-1.5 text-sm bg-white min-w-[200px]"
        data-testid="rule-field"
      >
        <option value="">Pick a field…</option>
        {Object.entries(schema).map(([catKey, cat]) => (
          <optgroup key={catKey} label={cat.label}>
            {cat.fields.map((f) => (
              <option key={f.key} value={f.key}>{f.label}</option>
            ))}
          </optgroup>
        ))}
      </select>

      {fieldMeta && (
        <select
          value={rule.operator}
          onChange={(e) => onChange({ ...rule, operator: e.target.value, value: null })}
          className="border border-neutral-300 rounded px-2 py-1.5 text-sm bg-white"
          data-testid="rule-op"
        >
          {fieldMeta.operators.map((o) => (
            <option key={o} value={o}>{OP_LABELS[o] || o}</option>
          ))}
        </select>
      )}

      <div className="flex-1 min-w-[200px]">
        <ValueInput field={fieldMeta} op={rule.operator} value={rule.value} onChange={(v) => onChange({ ...rule, value: v })} />
        {fieldMeta && fieldMeta.hint && (
          <div className="text-[10px] text-neutral-500 mt-1">{fieldMeta.hint}</div>
        )}
      </div>

      <button type="button" onClick={onRemove} className="text-neutral-400 hover:text-rose-600 p-1.5" data-testid="rule-remove">
        <Trash2 className="w-4 h-4" />
      </button>
    </div>
  );
}

/* Recursive filter group with max depth 2 */
export function FilterGroup({ group, schema, onChange, depth = 0, onRemove }) {
  const setOp = (op) => onChange({ ...group, op });
  const updateRule = (i, next) => {
    const rules = group.rules.slice();
    rules[i] = next;
    onChange({ ...group, rules });
  };
  const removeRule = (i) => {
    onChange({ ...group, rules: group.rules.filter((_, j) => j !== i) });
  };

  return (
    <div className={`border-l-4 p-3 rounded-r-md ${depth === 0 ? "border-l-neutral-900 bg-white" : "border-l-amber-400 bg-amber-50/40"}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="inline-flex items-center bg-white border border-neutral-300 rounded overflow-hidden">
          {["AND", "OR"].map((o) => (
            <button
              key={o}
              type="button"
              onClick={() => setOp(o)}
              className={`px-3 py-1 text-xs font-medium ${group.op === o ? "bg-neutral-900 text-white" : "text-neutral-600 hover:bg-neutral-100"}`}
              data-testid={`op-${o}-${depth}`}
            >
              {o}
            </button>
          ))}
        </div>
        {depth > 0 && (
          <button type="button" onClick={onRemove} className="text-xs text-rose-600 hover:underline">
            Remove group
          </button>
        )}
      </div>

      <div className="space-y-2">
        {group.rules.map((r, i) => {
          if (r.kind === "group") {
            // React.createElement (not JSX) — avoids visual-edits babel-plugin
            // infinite-loop on self-referencing JSX components.
            return React.createElement(FilterGroup, {
              key: i,
              group: r,
              schema,
              depth: depth + 1,
              onChange: (next) => updateRule(i, next),
              onRemove: () => removeRule(i),
            });
          }
          return (
            <RuleRow
              key={i}
              rule={r}
              schema={schema}
              onChange={(next) => updateRule(i, next)}
              onRemove={() => removeRule(i)}
            />
          );
        })}
      </div>

      <div className="flex flex-wrap gap-2 mt-3">
        <button
          type="button"
          onClick={() => onChange({ ...group, rules: [...group.rules, newRule()] })}
          className="text-xs flex items-center gap-1 px-3 py-1.5 border border-neutral-300 rounded hover:border-neutral-900"
          data-testid={`add-rule-${depth}`}
        >
          <Plus className="w-3.5 h-3.5" /> Add rule
        </button>
        {depth < 1 && (
          <button
            type="button"
            onClick={() => onChange({ ...group, rules: [...group.rules, newGroup()] })}
            className="text-xs flex items-center gap-1 px-3 py-1.5 border border-amber-400 text-amber-700 rounded hover:bg-amber-50"
            data-testid={`add-group-${depth}`}
          >
            <Plus className="w-3.5 h-3.5" /> Add nested group
          </button>
        )}
      </div>
    </div>
  );
}

export { newRule, newGroup };
