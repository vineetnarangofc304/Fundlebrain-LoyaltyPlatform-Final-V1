import { useEffect, useState, useRef } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import { Loader2, Send, Download, ChevronLeft, ChevronRight, Users, ArrowDownAZ } from "lucide-react";

const fmtNum = (v) => v == null ? "—" : Number(v).toLocaleString("en-IN");
const fmtINR = (v) => v == null ? "—" : `₹${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
const fmtDate = (s) => !s ? "—" : new Date(s).toLocaleDateString("en-IN", { year: "numeric", month: "short", day: "2-digit" });

export default function AudienceTable({ tree, segmentNameHint, onSegmentSaved }) {
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [sort, setSort] = useState({ by: "lifetime_spend", dir: -1 });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [sendOpen, setSendOpen] = useState(false);
  const debounceRef = useRef(null);
  const navigate = useNavigate();

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

  const exportCsv = () => {
    if (!data || !data.rows.length) { toast.error("Nothing to export"); return; }
    const headers = ["Mobile", "Name", "City", "Tier", "Bills", "Lifetime Spend", "Last Visit", "Points Balance", "Lifetime Earned", "Lifetime Redeemed"];
    const lines = [headers.join(",")];
    data.rows.forEach((r) => {
      lines.push([
        r.mobile || "", `"${(r.name || "").replace(/"/g, '""')}"`, r.city || "",
        r.tier || "", r.visit_count || 0, r.lifetime_spend || 0,
        r.last_visit_at ? r.last_visit_at.slice(0, 10) : "",
        r.points_balance || 0, r.lifetime_points_earned || 0, r.lifetime_points_redeemed || 0,
      ].join(","));
    });
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `audience_${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success(`Exported ${data.rows.length} rows (this page)`);
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
          <button type="button" onClick={exportCsv} className="text-xs flex items-center gap-1 px-3 py-1.5 border border-neutral-300 rounded hover:bg-neutral-50" data-testid="audience-export">
            <Download className="w-3.5 h-3.5" /> Export page
          </button>
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
              <th className="px-2 py-2">Mobile</th>
              <th className="px-2 py-2 cursor-pointer hover:text-neutral-800" onClick={() => toggleSort("name")}>Name <SortIcon col="name" /></th>
              <th className="px-2 py-2">City</th>
              <th className="px-2 py-2">Tier</th>
              <th className="px-2 py-2 text-right cursor-pointer hover:text-neutral-800" onClick={() => toggleSort("visit_count")}>Bills <SortIcon col="visit_count" /></th>
              <th className="px-2 py-2 text-right cursor-pointer hover:text-neutral-800" onClick={() => toggleSort("lifetime_spend")}>Lifetime Spend <SortIcon col="lifetime_spend" /></th>
              <th className="px-2 py-2 cursor-pointer hover:text-neutral-800" onClick={() => toggleSort("last_visit_at")}>Last Visit <SortIcon col="last_visit_at" /></th>
              <th className="px-2 py-2 text-right cursor-pointer hover:text-neutral-800" onClick={() => toggleSort("points_balance")}>Points <SortIcon col="points_balance" /></th>
            </tr>
          </thead>
          <tbody>
            {data && data.rows.map((r) => (
              <tr key={r.id || r.mobile} className="border-b border-neutral-100 hover:bg-neutral-50" data-testid={`audience-row-${r.mobile}`}>
                <td className="px-2 py-2 font-mono">{r.mobile || "—"}</td>
                <td className="px-2 py-2 truncate max-w-[180px]" title={r.name}>{r.name || <span className="text-neutral-400">—</span>}</td>
                <td className="px-2 py-2 text-neutral-600">{r.city || "—"}</td>
                <td className="px-2 py-2"><span className="inline-block px-1.5 py-0.5 bg-neutral-100 rounded text-[10px] uppercase">{r.tier || "—"}</span></td>
                <td className="px-2 py-2 text-right">{fmtNum(r.visit_count)}</td>
                <td className="px-2 py-2 text-right font-medium">{fmtINR(r.lifetime_spend)}</td>
                <td className="px-2 py-2 text-neutral-600">{fmtDate(r.last_visit_at)}</td>
                <td className="px-2 py-2 text-right">{fmtNum(r.points_balance)}</td>
              </tr>
            ))}
            {(!data || data.rows.length === 0) && !loading && (
              <tr><td colSpan={8} className="px-2 py-10 text-center text-neutral-400">No customers match this filter.</td></tr>
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
