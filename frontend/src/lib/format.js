export const fmtINR = (n) => {
  if (n === null || n === undefined || Number.isNaN(n)) return "N/A";
  if (n >= 10000000) return `₹${(n / 10000000).toFixed(2)}Cr`;
  if (n >= 100000) return `₹${(n / 100000).toFixed(2)}L`;
  if (n >= 1000) return `₹${(n / 1000).toFixed(2)}K`;
  return `₹${Number(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

// Exact ₹ amount with Indian commas and ALWAYS 2 decimals — NO Cr/L/K compaction.
// Use this for every report / table / detail / drill-down amount cell where the
// exact purchase value (paise included) must be shown — never rounded.
export const fmtMoney2 = (n) => {
  if (n === null || n === undefined || n === "" || Number.isNaN(Number(n))) return "—";
  const v = Number(n);
  const sign = v < 0 ? "-" : "";
  return `${sign}₹${Math.abs(v).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

// Full ₹ amount with Indian commas — no Cr/L compaction, exact 2 decimals. Used for tooltips/hover.
export const fmtINRFull = (n) => {
  if (n === null || n === undefined || Number.isNaN(n)) return "N/A";
  return `₹${Number(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
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

// Tolerant date parser. Handles ISO strings AND the formats some POS terminals send:
//  - year-first "YYYY-MM-DD[ T]HH:MM[:SS][tz]"  (space-separated naive form is what
//    Safari rejects via new Date(); we rebuild it as proper ISO)
//  - day-first  "DD-MM-YYYY / DD/MM/YYYY[ HH:MM[:SS]]"
// A value with NO timezone is treated as IST (+05:30); an explicit tz is preserved.
const parseDate = (s) => {
  if (s === null || s === undefined || s === "") return null;
  const str = String(s).trim();
  // Year-first / ISO: YYYY-MM-DD optionally with time and timezone.
  const iso = str.match(
    /^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})?)?/
  );
  if (iso) {
    const [, y, mo, d, hh = "00", mi = "00", ss = "00", tz] = iso;
    const tzPart = tz ? tz.replace(/([+-]\d{2})(\d{2})$/, "$1:$2") : "+05:30";
    const norm = `${y}-${mo.padStart(2, "0")}-${d.padStart(2, "0")}T${hh.padStart(2, "0")}:${mi}:${ss}${tzPart}`;
    const dt = new Date(norm);
    if (!Number.isNaN(dt.getTime())) return dt;
  }
  // Day-first DD-MM-YYYY / DD/MM/YYYY (optional HH:MM[:SS]) — treated as IST.
  const m = str.match(
    /^(\d{1,2})[-/](\d{1,2})[-/](\d{4})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?/
  );
  if (m) {
    const [, dd, mm, yyyy, hh = "00", mi = "00", ss = "00"] = m;
    const norm = `${yyyy}-${mm.padStart(2, "0")}-${dd.padStart(2, "0")}T${hh.padStart(2, "0")}:${mi}:${ss}+05:30`;
    const d = new Date(norm);
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

// Year-month-date format in IST: "YYYY-MM-DD HH:MM" (24-hour).
export const fmtDateTimeISO = (s) => {
  const d = parseDate(s);
  if (!d) return s ? s : "—";
  const parts = new Intl.DateTimeFormat("en-CA", {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: IST_TZ,
  }).formatToParts(d).reduce((a, p) => ((a[p.type] = p.value), a), {});
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`;
};

// Year-month-date in IST: "YYYY-MM-DD" (keeps the report's sortable ISO date format
// but converts to Asia/Kolkata so it matches the dashboard — no more off-by-one).
export const fmtDateISO = (s) => {
  const d = parseDate(s);
  if (!d) return s ? s : "—";
  const parts = new Intl.DateTimeFormat("en-CA", {
    year: "numeric", month: "2-digit", day: "2-digit", timeZone: IST_TZ,
  }).formatToParts(d).reduce((a, p) => ((a[p.type] = p.value), a), {});
  return `${parts.year}-${parts.month}-${parts.day}`;
};


export const tierClass = (t) => `pill pill-${(t || "silver").toLowerCase()}`;
