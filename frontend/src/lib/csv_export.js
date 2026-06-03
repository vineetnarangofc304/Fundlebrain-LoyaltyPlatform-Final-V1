/** Client-side CSV exporter — used by dashboards that don't (yet) have a
 *  server-side export endpoint. For audience/segment/customer/raw-reports
 *  we still call the server export endpoints because those operate on the
 *  full filtered dataset, not just what's currently on screen.
 */
export function downloadCsv(filename, header, rows) {
  if (!Array.isArray(rows) || rows.length === 0) {
    // Still generate an empty header so the user sees the CSV shape
    rows = [];
  }
  const escape = (v) => {
    if (v == null) return "";
    const s = String(v);
    if (s.includes(",") || s.includes("\"") || s.includes("\n")) {
      return `"${s.replace(/"/g, '""')}"`;
    }
    return s;
  };
  const lines = [header.map(escape).join(",")];
  for (const row of rows) lines.push(row.map(escape).join(","));
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename.endsWith(".csv") ? filename : `${filename}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(a.href);
}
