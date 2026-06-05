import { useState, useEffect, useRef } from "react";
import { Calendar, ChevronDown } from "lucide-react";

/**
 * Shared Date Range Picker — emits { from, to, period_days, label } whenever the
 * user changes it. Used across every dashboard so the filter is consistent.
 *
 * Two modes:
 *   PRESET — "All time", "Last 7d", "Last 30d", "Last 90d", "Last 365d", "MTD", "YTD"
 *   CUSTOM — explicit from / to date inputs
 *
 * Output contract (passed to backend):
 *   period_days  → integer days (legacy, still honoured by every endpoint)
 *   start_date   → ISO date string YYYY-MM-DD (custom mode only)
 *   end_date     → ISO date string YYYY-MM-DD (custom mode only)
 *
 * Backend logic (added in this iteration to every dashboard endpoint):
 *   if start_date+end_date present → filter bill_date between those
 *   else if period_days > 0 → filter bill_date >= now - period_days
 *   else → all time
 */

const PRESETS = [
  { value: "0", label: "All time", days: 0 },
  { value: "7", label: "Last 7 days", days: 7 },
  { value: "30", label: "Last 30 days", days: 30 },
  { value: "90", label: "Last 90 days", days: 90 },
  { value: "180", label: "Last 180 days", days: 180 },
  { value: "365", label: "Last 365 days", days: 365 },
  { value: "mtd", label: "Month to date" },
  { value: "ytd", label: "Year to date" },
  { value: "custom", label: "Custom range…" },
];

function toIso(d) {
  if (!d) return "";
  const dt = d instanceof Date ? d : new Date(d);
  return dt.toISOString().slice(0, 10);
}

function computeRange(presetValue, customFrom, customTo) {
  const today = new Date();
  const todayIso = toIso(today);

  if (presetValue === "custom") {
    if (!customFrom || !customTo) return { period_days: 0, start_date: "", end_date: "", label: "Custom" };
    const diffMs = new Date(customTo).getTime() - new Date(customFrom).getTime();
    const days = Math.max(1, Math.ceil(diffMs / 86400000) + 1);
    return {
      period_days: days,
      start_date: customFrom,
      end_date: customTo,
      label: `${customFrom} → ${customTo}`,
    };
  }

  if (presetValue === "mtd") {
    const first = new Date(today.getFullYear(), today.getMonth(), 1);
    return {
      period_days: Math.ceil((today - first) / 86400000) + 1,
      start_date: toIso(first),
      end_date: todayIso,
      label: "Month to date",
    };
  }
  if (presetValue === "ytd") {
    const first = new Date(today.getFullYear(), 0, 1);
    return {
      period_days: Math.ceil((today - first) / 86400000) + 1,
      start_date: toIso(first),
      end_date: todayIso,
      label: "Year to date",
    };
  }
  const preset = PRESETS.find((p) => p.value === presetValue);
  return {
    period_days: preset?.days ?? 0,
    start_date: "",
    end_date: "",
    label: preset?.label ?? "All time",
  };
}

export default function DateRangePicker({ value, onChange, testid = "date-range-picker" }) {
  const [open, setOpen] = useState(false);
  const [preset, setPreset] = useState(value?.preset || "0");
  const [from, setFrom] = useState(value?.start_date || "");
  const [to, setTo] = useState(value?.end_date || toIso(new Date()));
  const ref = useRef(null);

  // Close on outside click
  useEffect(() => {
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const applyPreset = (p) => {
    setPreset(p);
    if (p !== "custom") {
      const r = computeRange(p, "", "");
      onChange?.({ preset: p, ...r });
      setOpen(false);
    }
  };

  const applyCustom = () => {
    if (!from || !to) return;
    if (new Date(from) > new Date(to)) return;
    const r = computeRange("custom", from, to);
    onChange?.({ preset: "custom", ...r });
    setOpen(false);
  };

  const currentLabel = computeRange(preset, from, to).label;

  return (
    <div className="relative" ref={ref} data-testid={testid}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="k-input k-input-sm flex items-center gap-2 !w-auto !py-1.5 hover:border-amber-400 transition-colors"
        data-testid={`${testid}-toggle`}
      >
        <Calendar className="w-3.5 h-3.5 text-neutral-500" />
        <span className="font-medium text-neutral-800">{currentLabel}</span>
        <ChevronDown className="w-3.5 h-3.5 text-neutral-400" />
      </button>
      {open && (
        <div className="absolute right-0 top-full mt-1 z-40 bg-white border border-black/10 shadow-2xl min-w-[280px] p-2" data-testid={`${testid}-menu`}>
          {PRESETS.filter((p) => p.value !== "custom").map((p) => (
            <button
              key={p.value}
              type="button"
              onClick={() => applyPreset(p.value)}
              className={`w-full text-left px-3 py-1.5 text-sm hover:bg-amber-50 ${preset === p.value ? "bg-amber-50 font-medium text-amber-900" : "text-neutral-700"}`}
              data-testid={`${testid}-preset-${p.value}`}
            >
              {p.label}
            </button>
          ))}
          <div className="border-t border-black/5 mt-2 pt-2">
            <button
              type="button"
              onClick={() => setPreset("custom")}
              className={`w-full text-left px-3 py-1.5 text-sm hover:bg-amber-50 ${preset === "custom" ? "bg-amber-50 font-medium text-amber-900" : "text-neutral-700"}`}
              data-testid={`${testid}-preset-custom`}
            >
              Custom range…
            </button>
            {preset === "custom" && (
              <div className="px-3 py-2 space-y-2">
                <div>
                  <label className="text-[10px] uppercase tracking-[0.2em] text-neutral-500 block mb-1">From</label>
                  <input
                    type="date"
                    value={from}
                    max={to || toIso(new Date())}
                    onChange={(e) => setFrom(e.target.value)}
                    className="k-input k-input-sm w-full"
                    data-testid={`${testid}-from`}
                  />
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-[0.2em] text-neutral-500 block mb-1">To</label>
                  <input
                    type="date"
                    value={to}
                    min={from || undefined}
                    max={toIso(new Date())}
                    onChange={(e) => setTo(e.target.value)}
                    className="k-input k-input-sm w-full"
                    data-testid={`${testid}-to`}
                  />
                </div>
                <button
                  type="button"
                  onClick={applyCustom}
                  disabled={!from || !to || new Date(from) > new Date(to)}
                  className="k-btn k-btn-sm w-full kazo-bg-burgundy text-white disabled:opacity-40"
                  data-testid={`${testid}-apply`}
                >
                  Apply
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
