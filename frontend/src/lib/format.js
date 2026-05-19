export const fmtINR = (n) => {
  if (n === null || n === undefined || Number.isNaN(n)) return "N/A";
  if (n >= 10000000) return `₹${(n / 10000000).toFixed(2)}Cr`;
  if (n >= 100000) return `₹${(n / 100000).toFixed(2)}L`;
  if (n >= 1000) return `₹${(n / 1000).toFixed(1)}K`;
  return `₹${Number(n).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
};

export const fmtNum = (n) => {
  if (n === null || n === undefined || Number.isNaN(n)) return "N/A";
  return Number(n).toLocaleString("en-IN");
};

export const fmtPct = (n, digits = 1) => {
  if (n === null || n === undefined || Number.isNaN(n)) return "N/A";
  return `${Number(n).toFixed(digits)}%`;
};

export const fmtDate = (s) => {
  if (!s) return "—";
  try {
    const d = new Date(s);
    return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
  } catch { return s; }
};

export const fmtDateTime = (s) => {
  if (!s) return "—";
  try {
    const d = new Date(s);
    return d.toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch { return s; }
};

export const tierClass = (t) => `pill pill-${(t || "silver").toLowerCase()}`;
