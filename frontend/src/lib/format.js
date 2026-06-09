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

// All date/time rendering is forced to IST (Asia/Kolkata) so the platform shows
// Indian Standard Time regardless of the viewer's machine timezone.
const IST_TZ = "Asia/Kolkata";

// Tolerant date parser. Handles ISO strings AND the day-first formats some POS
// terminals send (DD-MM-YYYY / DD/MM/YYYY, optional HH:MM[:SS]) which `new Date()`
// rejects as "Invalid Date". Day-first naive values are treated as IST (+05:30).
const parseDate = (s) => {
  if (s === null || s === undefined || s === "") return null;
  const str = String(s).trim();
  // ISO-like (YYYY-MM-DD…) — reliable, identical across all browsers.
  if (/^\d{4}-\d{1,2}-\d{1,2}/.test(str)) {
    const d = new Date(str);
    if (!Number.isNaN(d.getTime())) return d;
  }
  // Day-first DD-MM-YYYY / DD/MM/YYYY (optional HH:MM[:SS]) — what some POS send.
  // Treated as IST so it renders correctly. (Safari rejects these via new Date().)
  const m = str.match(
    /^(\d{1,2})[-/](\d{1,2})[-/](\d{4})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?/
  );
  if (m) {
    const [, dd, mm, yyyy, hh = "00", mi = "00", ss = "00"] = m;
    const iso = `${yyyy}-${mm.padStart(2, "0")}-${dd.padStart(2, "0")}T${hh.padStart(2, "0")}:${mi}:${ss}+05:30`;
    const d = new Date(iso);
    if (!Number.isNaN(d.getTime())) return d;
  }
  const fallback = new Date(str);
  return Number.isNaN(fallback.getTime()) ? null : fallback;
};

export const fmtDate = (s) => {
  const d = parseDate(s);
  if (!d) return s ? s : "—";
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric", timeZone: IST_TZ });
};

export const fmtDateTime = (s) => {
  const d = parseDate(s);
  if (!d) return s ? s : "—";
  return d.toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: IST_TZ });
};

export const tierClass = (t) => `pill pill-${(t || "silver").toLowerCase()}`;
