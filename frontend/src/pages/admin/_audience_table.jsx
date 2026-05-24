import { useEffect, useState, useRef } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import { Loader2, Send, Download, ChevronLeft, ChevronRight, Users, ArrowDownAZ, FileSpreadsheet, FileText, FileType2, ChevronDown, Columns3, Check } from "lucide-react";
import CustomerDetailDrawer from "./_customer_drawer";

const fmtNum = (v) => v == null ? "—" : Number(v).toLocaleString("en-IN");
const fmtINR = (v) => v == null ? "—" : `₹${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
const fmtDate = (s) => !s ? "—" : new Date(s).toLocaleDateString("en-IN", { year: "numeric", month: "short", day: "2-digit" });
const fmtTier = (v) => v ? <span className="inline-block px-1.5 py-0.5 bg-neutral-100 rounded text-[10px] uppercase">{v}</span> : "—";

const EXPORT_FORMATS = [
  { key: "csv",  label: "CSV (.csv)",   icon: FileText,        mime: "text/csv" },
  { key: "xlsx", label: "Excel (.xlsx)", icon: FileSpreadsheet, mime: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" },
  { key: "pdf",  label: "PDF (.pdf)",   icon: FileType2,       mime: "application/pdf" },
];

/* ============================================================
 * Column catalog — every field /api/segments/audience can return.
 * Each column: key, label, sortKey (server-side sort), align, format, required (locked on).
 * ============================================================ */
const ALL_COLUMNS = [
  { key: "mobile",                    label: "Mobile",              align: "left",  sortKey: null,              required: true,
    render: (v) => <span className="font-mono text-indigo-700 underline-offset-2 hover:underline">{v || "—"}</span> },
  { key: "name",                      label: "Name",                align: "left",  sortKey: "name",            required: true,
    render: (v, r) => <span className="truncate max-w-[180px] inline-block" title={r.name}>{v || <span className="text-neutral-400">—</span>}</span> },
  { key: "email",                     label: "Email",               align: "left",  sortKey: null,              format: (v) => v || "—" },
  { key: "city",                      label: "City",                align: "left",  sortKey: null,              format: (v) => v || "—" },
  { key: "state",                     label: "State",               align: "left",  sortKey: null,              format: (v) => v || "—" },
  { key: "tier",                      label: "Tier",                align: "left",  sortKey: null,              render: (v) => fmtTier(v) },
  { key: "gender",                    label: "Gender",              align: "left",  sortKey: null,              format: (v) => v || "—" },
  { key: "visit_count",               label: "Bills",               align: "right", sortKey: "visit_count",     format: fmtNum },
  { key: "lifetime_spend",            label: "Lifetime Spend",      align: "right", sortKey: "lifetime_spend",  format: fmtINR },
  { key: "first_purchase_at",         label: "First Purchase",      align: "left",  sortKey: "first_purchase_at", format: fmtDate },
  { key: "last_visit_at",             label: "Last Visit",          align: "left",  sortKey: "last_visit_at",   format: fmtDate },
  { key: "points_balance",            label: "Points Balance",      align: "right", sortKey: "points_balance",  format: fmtNum },
  { key: "lifetime_points_earned",    label: "Lifetime Earned",     align: "right", sortKey: null,              format: fmtNum },
  { key: "lifetime_points_redeemed",  label: "Lifetime Redeemed",   align: "right", sortKey: null,              format: fmtNum },
  { key: "churn_risk",                label: "Churn Risk",          align: "left",  sortKey: null,              format: (v) => v || "—" },
  { key: "home_store_id",             label: "Home Store",          align: "left",  sortKey: null,              format: (v) => v || "—" },
  { key: "birthday",                  label: "Birthday",            align: "left",  sortKey: null,              format: fmtDate },
];

const DEFAULT_VISIBLE = ["mobile", "name", "city", "tier", "visit_count", "lifetime_spend", "last_visit_at", "points_balance"];
const REQUIRED_KEYS = ALL_COLUMNS.filter((c) => c.required).map((c) => c.key);

const STORAGE_KEY = "kazo_audience_visible_cols";

export default function AudienceTable({ tree, segmentNameHint, onSegmentSaved }) {
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [sort, setSort] = useState({ by: "lifetime_spend", dir: -1 });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [sendOpen, setSendOpen] = useState(false);
  const [drawerMobile, setDrawerMobile] = useState(null);
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const [exporting, setExporting] = useState(null);  // 'csv' | 'xlsx' | 'pdf' | null
  const [colMenuOpen, setColMenuOpen] = useState(false);
  const [visibleKeys, setVisibleKeys] = useState(() => {
    try {
      const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
      if (Array.isArray(stored) && stored.length > 0) {
        // Always make sure required keys are present
        const merged = Array.from(new Set([...REQUIRED_KEYS, ...stored]));
        return merged;
      }
    } catch (e) { /* ignore */ }
    return DEFAULT_VISIBLE;
  });
  const debounceRef = useRef(null);
  const exportMenuRef = useRef(null);
  const colMenuRef = useRef(null);
  const navigate = useNavigate();

  // Persist column choices
  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(visibleKeys)); } catch (e) { /* ignore */ }
  }, [visibleKeys]);

  // Close menus on outside click
  useEffect(() => {
    if (!exportMenuOpen && !colMenuOpen) return;
    const handler = (e) => {
      if (exportMenuOpen && exportMenuRef.current && !exportMenuRef.current.contains(e.target)) {
        setExportMenuOpen(false);
      }
      if (colMenuOpen && colMenuRef.current && !colMenuRef.current.contains(e.target)) {
        setColMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [exportMenuOpen, colMenuOpen]);

  const toggleColumn = (key) => {
    if (REQUIRED_KEYS.includes(key)) return;
    setVisibleKeys((cur) => cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key]);
  };

  const visibleColumns = ALL_COLUMNS.filter((c) => visibleKeys.includes(c.key));

  // Count of non-empty leaves
  const hasFilter = (() => {
    if (!tree || !tree.rules) return false;
    const walk = (n) => {
      if (n.rules) return n.rules.some(walk);
      return !!(n.field && n.value != null && (Array.isArray(n.value) ? n.value.length : true));
    };
    return tree.rules.some(walk);
  })();

  const fetchAudience = async () => {
    if (!hasFilter) { setData(null); return; }
    setLoading(true);
    try {
      const r = await api.post("/segments/audience", {
        tree, page, page_size: pageSize,
        sort_by: sort.by, sort_dir: sort.dir,
      });
      setData(r.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Audience load failed");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(fetchAudience, 400);
    return () => debounceRef.current && clearTimeout(debounceRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tree, page, sort]);

  const toggleSort = (col) => {
    if (sort.by === col) setSort((s) => ({ ...s, dir: -s.dir }));
    else setSort({ by: col, dir: -1 });
    setPage(1);
  };

  const sendCampaign = async (saveAs) => {
    if (!hasFilter) { toast.error("Build a filter first"); return; }
    if (!saveAs || !saveAs.trim()) { toast.error("Segment name required"); return; }
    try {
      const s = await api.post("/segments/", { name: saveAs.trim(), tree });
      toast.success(`Saved "${saveAs}" — opening Campaign Manager`);
      if (onSegmentSaved) onSegmentSaved(s.data);
      // Navigate to Campaign Manager with the segment id prefilled
      navigate(`/admin/campaigns?segment_id=${s.data.id}&segment_name=${encodeURIComponent(saveAs)}`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Save failed");
    }
  };

  const exportFullReport = async (fmt) => {
    if (!hasFilter) { toast.error("Build a filter first"); return; }
    if (!data || data.total === 0) { toast.error("Nothing to export"); return; }
    setExporting(fmt);
    setExportMenuOpen(false);
    const tid = toast.loading(`Preparing ${fmt.toUpperCase()} for ${fmtNum(data.total)} customers…`);
    try {
      const resp = await api.post("/segments/audience/export", {
        tree,
        sort_by: sort.by,
        sort_dir: sort.dir,
        format: fmt,
        segment_name: (segmentNameHint || "audience").slice(0, 60),
      }, { responseType: "blob", timeout: 300000 });
      // Filename from Content-Disposition
      const cd = resp.headers["content-disposition"] || resp.headers["Content-Disposition"] || "";
      let filename = `audience_${Date.now()}.${fmt}`;
      const m = /filename="?([^";]+)"?/.exec(cd);
      if (m) filename = m[1];
      const blob = new Blob([resp.data], { type: EXPORT_FORMATS.find(f => f.key === fmt)?.mime });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success(`Exported ${fmtNum(data.total)} customers as ${fmt.toUpperCase()}`, { id: tid });
    } catch (e) {
      let msg = "Export failed";
      // Blob error → try to read JSON detail
      if (e.response?.data instanceof Blob) {
        try {
          const text = await e.response.data.text();
          const parsed = JSON.parse(text);
          msg = parsed.detail || msg;
        } catch { msg = e.message || msg; }
      } else {
        msg = e.response?.data?.detail || e.message || msg;
      }
      toast.error(msg, { id: tid });
    } finally {
      setExporting(null);
    }
  };

  if (!hasFilter) {
    return (
      <div className="chart-card p-8 text-center" data-accent="slate">
        <Users className="w-10 h-10 mx-auto text-neutral-300 mb-3" />
        <div className="text-sm text-neutral-500">Add a filter rule or pick a cohort to see your audience here.</div>
      </div>
    );
  }

  const total = data ? data.total : 0;
  const pages = data ? data.pages : 0;
  const SortIcon = ({ col }) => sort.by === col ? (
    <ArrowDownAZ className={`w-3 h-3 inline ${sort.dir === 1 ? "rotate-180" : ""}`} />
  ) : null;

  return (
    <div className="chart-card p-5" data-accent="burgundy" data-testid="audience-table">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-neutral-500">AUDIENCE</div>
          <div className="font-display text-2xl">{fmtNum(total)} <span className="text-sm font-normal text-neutral-500">matched customers</span></div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative" ref={colMenuRef}>
            <button
              type="button"
              onClick={() => setColMenuOpen((o) => !o)}
              className="text-xs flex items-center gap-1 px-3 py-1.5 border border-neutral-300 rounded hover:bg-neutral-50"
              data-testid="audience-columns"
            >
              <Columns3 className="w-3.5 h-3.5" /> Columns ({visibleKeys.length}/{ALL_COLUMNS.length}) <ChevronDown className="w-3 h-3" />
            </button>
            {colMenuOpen && (
              <div className="absolute right-0 mt-1 w-64 bg-white border border-neutral-200 rounded-md shadow-lg z-30 max-h-80 overflow-y-auto" data-testid="audience-columns-menu">
                <div className="px-3 py-2 text-[10px] uppercase tracking-widest text-neutral-400 border-b border-neutral-100 bg-neutral-50 sticky top-0">
                  Show / hide columns
                </div>
                {ALL_COLUMNS.map((c) => {
                  const isVisible = visibleKeys.includes(c.key);
                  const isLocked = REQUIRED_KEYS.includes(c.key);
                  return (
                    <button
                      key={c.key}
                      type="button"
                      onClick={() => toggleColumn(c.key)}
                      className={`w-full flex items-center gap-2 px-3 py-1.5 text-xs text-left hover:bg-amber-50 ${isLocked ? "opacity-60 cursor-not-allowed" : ""}`}
                      data-testid={`audience-col-toggle-${c.key}`}
                    >
                      <div className={`w-3.5 h-3.5 border rounded flex items-center justify-center ${isVisible ? "bg-emerald-600 border-emerald-600" : "border-neutral-300 bg-white"}`}>
                        {isVisible && <Check className="w-2.5 h-2.5 text-white" />}
                      </div>
                      <span className="flex-1">{c.label}</span>
                      {isLocked && <span className="text-[9px] text-neutral-400">locked</span>}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
          <div className="relative" ref={exportMenuRef}>
            <button
              type="button"
              onClick={() => setExportMenuOpen((o) => !o)}
              disabled={!!exporting || !data || data.total === 0}
              className="text-xs flex items-center gap-1 px-3 py-1.5 border border-neutral-300 rounded hover:bg-neutral-50 disabled:opacity-50 disabled:cursor-not-allowed"
              data-testid="audience-export"
            >
              {exporting ? (
                <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Exporting {exporting.toUpperCase()}…</>
              ) : (
                <><Download className="w-3.5 h-3.5" /> Export full report <ChevronDown className="w-3 h-3" /></>
              )}
            </button>
            {exportMenuOpen && (
              <div
                className="absolute right-0 mt-1 w-56 bg-white border border-neutral-200 rounded-md shadow-lg z-20 overflow-hidden"
                data-testid="audience-export-menu"
              >
                <div className="px-3 py-2 text-[10px] uppercase tracking-widest text-neutral-400 border-b border-neutral-100">
                  Export {fmtNum(data?.total || 0)} matched
                </div>
                {EXPORT_FORMATS.map(({ key, label, icon: Icon }) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => exportFullReport(key)}
                    className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-amber-50 text-left"
                    data-testid={`audience-export-${key}`}
                  >
                    <Icon className="w-3.5 h-3.5 text-neutral-500" />
                    <span className="flex-1">{label}</span>
                    <span className="text-[10px] text-neutral-400">full</span>
                  </button>
                ))}
                {data?.total > 50000 && (
                  <div className="px-3 py-1.5 text-[10px] text-amber-700 bg-amber-50 border-t border-amber-100">
                    Large export — may take 10–60 seconds
                  </div>
                )}
              </div>
            )}
          </div>
          <button type="button" onClick={() => setSendOpen(true)} className="text-xs flex items-center gap-1 px-3 py-1.5 bg-neutral-900 text-white rounded hover:bg-neutral-800" data-testid="send-campaign-btn">
            <Send className="w-3.5 h-3.5" /> Send Campaign
          </button>
        </div>
      </div>

      {loading && (
        <div className="text-xs text-neutral-500 flex items-center gap-2 mb-2">
          <Loader2 className="w-3 h-3 animate-spin" /> Loading…
        </div>
      )}

      <div className="overflow-x-auto -mx-2">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-neutral-200 text-left text-[10px] uppercase tracking-widest text-neutral-500">
              {visibleColumns.map((c) => (
                <th
                  key={c.key}
                  className={`px-2 py-2 ${c.align === "right" ? "text-right" : ""} ${c.sortKey ? "cursor-pointer hover:text-neutral-800" : ""}`}
                  onClick={() => c.sortKey && toggleSort(c.sortKey)}
                >
                  {c.label} {c.sortKey && <SortIcon col={c.sortKey} />}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data && data.rows.map((r) => (
              <tr
                key={r.id || r.mobile}
                className="border-b border-neutral-100 hover:bg-amber-50 cursor-pointer"
                onClick={() => r.mobile && setDrawerMobile(r.mobile)}
                data-testid={`audience-row-${r.mobile}`}
              >
                {visibleColumns.map((c) => {
                  const val = r[c.key];
                  const content = c.render ? c.render(val, r) : (c.format ? c.format(val) : (val ?? "—"));
                  return (
                    <td key={c.key} className={`px-2 py-2 ${c.align === "right" ? "text-right" : ""} ${c.key === "lifetime_spend" ? "font-medium" : ""} ${["city", "last_visit_at", "first_purchase_at", "birthday", "home_store_id"].includes(c.key) ? "text-neutral-600" : ""}`}>
                      {content}
                    </td>
                  );
                })}
              </tr>
            ))}
            {(!data || data.rows.length === 0) && !loading && (
              <tr><td colSpan={visibleColumns.length} className="px-2 py-10 text-center text-neutral-400">No customers match this filter.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {pages > 1 && (
        <div className="flex items-center justify-between mt-4 text-xs">
          <div className="text-neutral-500">
            Page {page} of {fmtNum(pages)} · showing {data ? data.rows.length : 0} of {fmtNum(total)}
          </div>
          <div className="flex items-center gap-1">
            <button type="button" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}
                    className="px-2 py-1 border border-neutral-300 rounded hover:bg-neutral-50 disabled:opacity-50">
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
            <button type="button" onClick={() => setPage((p) => Math.min(pages, p + 1))} disabled={page === pages}
                    className="px-2 py-1 border border-neutral-300 rounded hover:bg-neutral-50 disabled:opacity-50">
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

      {sendOpen && (
        <SendCampaignDialog
          audienceTotal={total}
          defaultName={segmentNameHint || ""}
          onClose={() => setSendOpen(false)}
          onConfirm={(name) => { setSendOpen(false); sendCampaign(name); }}
        />
      )}

      {drawerMobile && (
        <CustomerDetailDrawer
          mobile={drawerMobile}
          onClose={() => setDrawerMobile(null)}
        />
      )}
    </div>
  );
}

function SendCampaignDialog({ audienceTotal, defaultName, onClose, onConfirm }) {
  const [name, setName] = useState(defaultName || `Segment ${new Date().toLocaleString()}`);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className="bg-white rounded-lg p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <div className="font-display text-xl mb-1 flex items-center gap-2"><Send className="w-5 h-5" /> Send Campaign</div>
        <div className="text-xs text-neutral-500 mb-4">
          This will save the segment with <strong>{fmtNum(audienceTotal)}</strong> customers and open the Campaign Manager prefilled with this audience. You'll choose channels, template, and timing there.
        </div>
        <label className="block text-xs uppercase tracking-widest text-neutral-500 mb-1">Segment name *</label>
        <input value={name} onChange={(e) => setName(e.target.value)} autoFocus
                className="w-full border border-neutral-300 rounded px-3 py-2 text-sm mb-4"
                data-testid="send-campaign-name" />
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="text-sm px-4 py-2 border border-neutral-300 rounded hover:bg-neutral-50">Cancel</button>
          <button type="button" onClick={() => onConfirm(name)} className="bg-neutral-900 text-white text-sm px-4 py-2 rounded hover:bg-neutral-800 flex items-center gap-1" data-testid="send-campaign-confirm">
            <Send className="w-3.5 h-3.5" /> Save & open Campaign Manager
          </button>
        </div>
      </div>
    </div>
  );
}
