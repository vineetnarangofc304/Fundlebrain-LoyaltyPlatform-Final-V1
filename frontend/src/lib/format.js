export const fmtINR = (n) => {
  if (n === null || n === undefined || Number.isNaN(n)) return "N/A";
  if (n >= 10000000) return `₹${(n / 10000000).toFixed(2)}Cr`;
  if (n >= 100000) return `₹${(n / 100000).toFixed(2)}L`;
  if (n >= 1000) return `₹${(n / 1000).toFixed(1)}K`;
  return `₹${Number(n).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
};

// Full ₹ amount with Indian commas — no Cr/L compaction. Useful for tooltips.
export const fmtINRFull = (n) => {
  if (n === null || n === undefined || Number.isNaN(n)) return "N/A";
  return `₹${Number(n).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
};

export const fmtNum = (n) => {
  if (n === null || n === undefined || Number.isNaN(n)) return "N/A";
  return Number(n).toLocaleString("en-IN");
};

// Compact unitless number: 12.68L / 2.25Cr / 12.5K. Used on KPI tiles where space is tight.
export const fmtCompactNum = (n) => {
  if (n === null || n === undefined || Number.isNaN(n)) return "N/A";
  const v = Number(n);
  const sign = v < 0 ? "-" : "";
  const abs = Math.abs(v);
  if (abs >= 10000000) return `${sign}${(abs / 10000000).toFixed(2)}Cr`;
  if (abs >= 100000)   return `${sign}${(abs / 100000).toFixed(2)}L`;
  if (abs >= 1000)     return `${sign}${(abs / 1000).toFixed(1)}K`;
  return `${sign}${abs.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
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
