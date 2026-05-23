import { useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { X, Loader2 } from "lucide-react";

/* Async multi-select for typeahead facets */
export function FacetMultiSelect({ source, value = [], onChange, placeholder = "Type to search…" }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [opts, setOpts] = useState([]);
  const [loading, setLoading] = useState(false);
  const fetchTimer = useRef(null);

  useEffect(() => {
    if (!open) return;
    if (fetchTimer.current) clearTimeout(fetchTimer.current);
    fetchTimer.current = setTimeout(async () => {
      setLoading(true);
      try {
        const r = await api.post("/segments/facets", { source, query: q, limit: 30 });
        setOpts(r.data.values || []);
      } catch {
        setOpts([]);
      } finally {
        setLoading(false);
      }
    }, 250);
  }, [open, q, source]);

  const toggle = (v) => {
    const set = new Set(value);
    if (set.has(v)) set.delete(v); else set.add(v);
    onChange([...set]);
  };

  return (
    <div className="relative w-full">
      <div
        className="border border-neutral-300 rounded-md p-1.5 min-h-9 flex flex-wrap items-center gap-1 cursor-text bg-white"
        onClick={() => setOpen(true)}
        data-testid="facet-multi"
      >
        {value.map((v) => (
          <span key={v} className="inline-flex items-center gap-1 bg-neutral-900 text-white text-xs px-2 py-0.5 rounded">
            {v}
            <button type="button" onClick={(e) => { e.stopPropagation(); toggle(v); }} className="hover:opacity-70">
              <X className="w-3 h-3" />
            </button>
          </span>
        ))}
        <input
          className="flex-1 outline-none text-sm bg-transparent min-w-[120px] px-1"
          placeholder={value.length ? "" : placeholder}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => setOpen(true)}
        />
      </div>
      {open && (
        <div className="absolute z-30 mt-1 w-full max-h-72 overflow-y-auto bg-white border border-neutral-200 rounded-md shadow-lg">
          {loading && (
            <div className="p-2 text-xs text-neutral-400 flex items-center gap-2">
              <Loader2 className="w-3 h-3 animate-spin" /> Loading…
            </div>
          )}
          {!loading && opts.length === 0 && <div className="p-2 text-xs text-neutral-400">No matches</div>}
          {opts.map((o) => (
            <button
              type="button"
              key={o.value}
              className={`w-full text-left text-sm px-3 py-1.5 hover:bg-neutral-100 ${value.includes(o.value) ? "bg-neutral-50 font-medium" : ""}`}
              onClick={() => toggle(o.value)}
            >
              {o.label}
            </button>
          ))}
          <button type="button" onClick={() => setOpen(false)} className="w-full text-center text-xs text-neutral-500 py-2 hover:bg-neutral-100 border-t">
            Close
          </button>
        </div>
      )}
    </div>
  );
}

/* Render the right input control based on field type */
export function ValueInput({ field, op, value, onChange }) {
  if (!field) return <span className="text-xs text-neutral-400">Pick a field first</span>;

  if (field.type === "boolean") {
    return (
      <select
        value={value === true ? "true" : value === false ? "false" : ""}
        onChange={(e) => onChange(e.target.value === "true")}
        className="border border-neutral-300 rounded px-2 py-1.5 text-sm bg-white"
        data-testid="val-bool"
      >
        <option value="">—</option>
        <option value="true">Yes</option>
        <option value="false">No</option>
      </select>
    );
  }

  if (field.type === "multi") {
    const opts = field.options || [];
    const sel = Array.isArray(value) ? value : [];
    return (
      <div className="flex flex-wrap gap-1">
        {opts.map((o) => {
          const on = sel.includes(o);
          return (
            <button
              key={o}
              type="button"
              onClick={() => onChange(on ? sel.filter((x) => x !== o) : [...sel, o])}
              className={`text-xs px-2 py-1 rounded border ${on ? "bg-neutral-900 text-white border-neutral-900" : "bg-white border-neutral-300 text-neutral-700 hover:border-neutral-900"}`}
            >
              {o}
            </button>
          );
        })}
      </div>
    );
  }

  if (field.type === "multi_async") {
    return <FacetMultiSelect source={field.facet} value={Array.isArray(value) ? value : []} onChange={onChange} />;
  }

  if (field.type === "date") {
    if (op === "between") {
      const v = Array.isArray(value) ? value : ["", ""];
      return (
        <div className="flex items-center gap-1">
          <input type="date" value={(v[0] || "").slice(0, 10)} onChange={(e) => onChange([e.target.value ? `${e.target.value}T00:00:00Z` : "", v[1]])}
                 className="border border-neutral-300 rounded px-2 py-1 text-sm" />
          <span className="text-xs text-neutral-400">to</span>
          <input type="date" value={(v[1] || "").slice(0, 10)} onChange={(e) => onChange([v[0], e.target.value ? `${e.target.value}T23:59:59Z` : ""])}
                 className="border border-neutral-300 rounded px-2 py-1 text-sm" />
        </div>
      );
    }
    return (
      <input type="date" value={(value || "").slice(0, 10)} onChange={(e) => onChange(e.target.value ? `${e.target.value}T00:00:00Z` : "")}
             className="border border-neutral-300 rounded px-2 py-1 text-sm" />
    );
  }

  if (field.type === "number" || field.type === "currency" || field.type === "windowed_count") {
    if (op === "between") {
      const v = Array.isArray(value) ? value : ["", ""];
      return (
        <div className="flex items-center gap-1">
          <input type="number" value={v[0] ?? ""} onChange={(e) => onChange([Number(e.target.value), v[1]])}
                 placeholder="min" className="border border-neutral-300 rounded px-2 py-1 text-sm w-24" />
          <span className="text-xs text-neutral-400">to</span>
          <input type="number" value={v[1] ?? ""} onChange={(e) => onChange([v[0], Number(e.target.value)])}
                 placeholder="max" className="border border-neutral-300 rounded px-2 py-1 text-sm w-24" />
        </div>
      );
    }
    return (
      <input type="number" value={value ?? ""} onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
             placeholder={field.type === "currency" ? "₹" : ""} className="border border-neutral-300 rounded px-2 py-1 text-sm w-32" />
    );
  }
  return null;
}
