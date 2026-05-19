export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="border-b border-black/10 px-8 py-6 flex items-center justify-between bg-white">
      <div>
        <div className="text-[11px] uppercase tracking-[0.25em] text-neutral-500 mb-1">{subtitle}</div>
        <h1 className="font-display text-3xl tracking-tight">{title}</h1>
      </div>
      <div className="flex items-center gap-2">{actions}</div>
    </div>
  );
}

export function KPICard({ label, value, delta, hint, onClick, mono = true, testid }) {
  const deltaColor = delta == null ? "" : delta >= 0 ? "text-green-600" : "text-red-600";
  return (
    <div className="kpi-card" onClick={onClick} data-testid={testid}>
      <div className="text-[10px] uppercase tracking-[0.2em] text-neutral-500 mb-2">{label}</div>
      <div className={`text-3xl ${mono ? "font-mono" : "font-display"} text-neutral-900 leading-tight`}>{value}</div>
      <div className="mt-1 flex items-center gap-2 text-xs">
        {delta != null && <span className={`font-mono ${deltaColor}`}>{delta >= 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(1)}%</span>}
        {hint && <span className="text-neutral-400">{hint}</span>}
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
