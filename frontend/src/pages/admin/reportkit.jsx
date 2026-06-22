/* Shared report building blocks: column show/hide picker + a sortable, formatted
   table. Used by Store KPI / CRM Customer / Shopper Bill reports for consistency. */
import { useState, useRef, useEffect } from "react";
import { Columns3, ArrowUp, ArrowDown, Check } from "lucide-react";
import { fmtMoney2, fmtNum, fmtPct } from "@/lib/format";

export function useColumns(columns, storageKey) {
  const def = () => new Set(columns.filter((c) => c.default !== false).map((c) => c.key));
  const [visible, setVisible] = useState(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) || "null");
      if (Array.isArray(saved) && saved.length) return new Set(saved);
    } catch { /* ignore */ }
    return def();
  });
  useEffect(() => {
    try { localStorage.setItem(storageKey, JSON.stringify([...visible])); } catch { /* ignore */ }
  }, [visible, storageKey]);
  const toggle = (key) => setVisible((s) => {
    const n = new Set(s);
    n.has(key) ? n.delete(key) : n.add(key);
    return n;
  });
  const reset = () => setVisible(def());
  return { visible, toggle, reset };
}

export function ColumnPicker({ columns, visible, toggle, reset, testid = "col-picker" }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((o) => !o)} className="k-btn k-btn-outline k-btn-sm" data-testid={`${testid}-btn`}>
        <Columns3 className="w-3.5 h-3.5" /> Columns ({visible.size})
      </button>
      {open && (
        <div className="absolute right-0 mt-1 z-40 bg-white border border-black/10 shadow-xl p-2 w-60 max-h-80 overflow-auto rounded-md" data-testid={`${testid}-menu`}>
          <div className="flex items-center justify-between px-2 py-1 mb-1 border-b border-black/5">
            <span className="text-[10px] uppercase tracking-widest text-neutral-500">Show columns</span>
            <button onClick={reset} className="text-[10px] text-[#571326] hover:underline" data-testid={`${testid}-reset`}>Reset</button>
          </div>
          {columns.map((c) => (
            <label key={c.key} className="flex items-center gap-2 px-2 py-1.5 text-sm hover:bg-neutral-50 cursor-pointer rounded" data-testid={`${testid}-opt-${c.key}`}>
              <span className={`w-4 h-4 border rounded flex items-center justify-center ${visible.has(c.key) ? "kazo-bg-burgundy border-transparent" : "border-neutral-300"}`}>
                {visible.has(c.key) && <Check className="w-3 h-3 text-white" />}
              </span>
              <input type="checkbox" className="sr-only" checked={visible.has(c.key)} onChange={() => toggle(c.key)} />
              {c.label}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

function cell(c, r) {
  const v = r[c.key];
  if (c.render) return c.render(v, r);
  if (c.badge) return c.badge(v, r);
  if (v === "" || v === null || v === undefined) return "—";
  if (c.money) return fmtMoney2(v);
  if (c.pct) return v == null ? "—" : fmtPct(v);
  if (c.num) return fmtNum(v);
  return v;
}

export function ReportTable({ columns, rows, visible, sortBy, sortDir, onSort, testid = "report-table", rowKey }) {
  const cols = columns.filter((c) => visible.has(c.key));
  return (
    <table className="w-full text-sm whitespace-nowrap" data-testid={testid}>
      <thead className="border-b border-black/10 text-left">
        <tr>
          {cols.map((c) => (
            <th key={c.key}
              onClick={() => c.sort && onSort(c.sort)}
              className={`py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500 ${c.num || c.money || c.pct ? "text-right" : ""} ${c.sort ? "cursor-pointer hover:text-neutral-900 select-none" : ""}`}
              data-testid={`${testid}-th-${c.key}`}
            >
              <span className={`inline-flex items-center gap-1 ${c.num || c.money || c.pct ? "flex-row-reverse" : ""}`}>
                {c.label}
                {c.sort && sortBy === c.sort && (sortDir === "desc" ? <ArrowDown className="w-3 h-3" /> : <ArrowUp className="w-3 h-3" />)}
              </span>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={rowKey ? rowKey(r, i) : i} className="border-b border-black/5 hover:bg-amber-50/40">
            {cols.map((c) => (
              <td key={c.key} className={`py-2 px-2 ${c.mono ? "font-mono text-xs" : ""} ${c.num || c.money || c.pct ? "text-right font-mono" : ""}`}>
                {cell(c, r)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function GrowthCell(v) {
  if (v === null || v === undefined) return <span className="text-neutral-400">—</span>;
  const up = v >= 0;
  return (
    <span className={`inline-flex items-center gap-0.5 ${up ? "text-emerald-700" : "text-rose-700"}`}>
      {up ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />}
      {fmtPct(Math.abs(v))}
    </span>
  );
}
