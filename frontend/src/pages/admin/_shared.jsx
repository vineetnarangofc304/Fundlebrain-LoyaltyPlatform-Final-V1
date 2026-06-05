import { Link } from "react-router-dom";

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="border-b border-black/10 px-8 py-6 flex items-center justify-between bg-white">
      <div>
        <div className="text-[11px] uppercase tracking-[0.25em] text-neutral-500 mb-1">{subtitle}</div>
        <h1 className="font-display text-3xl tracking-tight">{title}</h1>
      </div>
      <div className="flex items-center gap-2 flex-wrap justify-end">{actions}</div>
    </div>
  );
}

export function KPICard({ label, value, delta, hint, info, onClick, mono = true, testid, accent, fullValue }) {
  const deltaColor = delta == null ? "" : delta >= 0 ? "text-emerald-700" : "text-rose-700";
  return (
    <div
      className="kpi-card"
      data-accent={accent}
      onClick={onClick}
      data-testid={testid}
      title={info || (fullValue != null ? String(fullValue) : undefined)}
    >
      <div className="text-[10px] uppercase tracking-[0.2em] text-neutral-500 mb-2 font-medium truncate flex items-center gap-1">
        <span className="truncate">{label}</span>
        {info && (
          <span
            className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full border border-neutral-300 text-[9px] text-neutral-500 cursor-help shrink-0"
            title={info}
            aria-label={info}
            onClick={(e) => e.stopPropagation()}
          >?</span>
        )}
      </div>
      <div className={`kpi-value ${mono ? "font-mono" : "font-display"} text-neutral-900 tabular-nums`} title={fullValue != null ? String(fullValue) : undefined}>{value}</div>
      <div className="mt-1 flex items-center gap-2 text-xs">
        {delta != null && (
          <span className={`font-mono ${deltaColor}`}>
            {delta >= 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(1)}%
          </span>
        )}
        {hint && <span className="text-neutral-400 truncate">{hint}</span>}
      </div>
    </div>
  );
}

export function StatusPill({ status }) {
  const map = {
    open: "pill-warning", in_progress: "pill-info", resolved: "pill-success",
    closed: "pill-neutral", escalated: "pill-danger",
    draft: "pill-neutral", scheduled: "pill-info", running: "pill-success", completed: "pill-info", cancelled: "pill-danger",
    active: "pill-success", inactive: "pill-neutral",
    high: "pill-danger", medium: "pill-warning", low: "pill-info",
    promoter: "pill-success", passive: "pill-warning", detractor: "pill-danger",
  };
  return <span className={`pill ${map[status] || "pill-neutral"}`}>{status?.replace(/_/g, " ")}</span>;
}

/* Shared chart palette — used consistently across all dashboards */
export const CHART_PALETTE = {
  burgundy: "#571326",
  indigo: "#1E3A8A",
  teal: "#0E7C7B",
  amber: "#B45309",
  rose: "#9F1239",
  slate: "#334155",
  emerald: "#047857",
  champagne: "#C7A76D",
};

export const CHART_SERIES = [
  "#1E3A8A", // indigo
  "#571326", // burgundy
  "#0E7C7B", // teal
  "#B45309", // amber
  "#9F1239", // rose
  "#334155", // slate
  "#C7A76D", // champagne
  "#047857", // emerald
];

/* Section heading with thin coloured underline — for consistent visual rhythm */
export function SectionHeading({ eyebrow, title, accent = "burgundy", right }) {
  const color = CHART_PALETTE[accent] || "#571326";
  return (
    <div className="flex items-end justify-between mb-3 pb-2 border-b border-black/5">
      <div className="flex items-center gap-3">
        <span className="inline-block w-6 h-px" style={{ background: color }} />
        <div>
          {eyebrow && (
            <div className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-0.5">
              {eyebrow}
            </div>
          )}
          <h3 className="font-display text-xl tracking-tight">{title}</h3>
        </div>
      </div>
      {right}
    </div>
  );
}

/* Lightweight breadcrumb back-to-link used on detail pages */
export function BackLink({ to, label }) {
  return (
    <Link to={to} className="text-xs text-neutral-500 hover:text-black uppercase tracking-widest">
      ← {label}
    </Link>
  );
}
