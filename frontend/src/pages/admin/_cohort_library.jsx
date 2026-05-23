import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Loader2, ChevronDown, ChevronRight, Sparkles } from "lucide-react";

const fmtNum = (v) => v == null || v < 0 ? "—" : Number(v).toLocaleString("en-IN");

export default function CohortLibrary({ onLoad }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [openCats, setOpenCats] = useState({});
  const [busyId, setBusyId] = useState(null);

  const loadCatalog = async () => {
    setLoading(true);
    try {
      const r = await api.get("/segments/cohort-library/?include_counts=true");
      setData(r.data);
      // Open the first 4 categories by default
      const next = {};
      r.data.categories.slice(0, 4).forEach((c) => { next[c.name] = true; });
      setOpenCats(next);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to load cohort library");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadCatalog(); }, []);

  const loadCohort = async (cohort) => {
    setBusyId(cohort.id);
    try {
      const r = await api.get(`/segments/cohort-library/${cohort.id}`);
      onLoad && onLoad({ name: r.data.name, tree: r.data.tree });
      toast.success(`Loaded "${r.data.name}" into the editor`);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Load failed");
    } finally {
      setBusyId(null);
    }
  };

  if (loading && !data) {
    return (
      <div className="text-xs text-neutral-500 flex items-center gap-2">
        <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading library…
      </div>
    );
  }
  if (!data) return null;

  return (
    <div data-testid="cohort-library">
      <div className="text-[11px] text-neutral-500 mb-3 flex items-center gap-2">
        <Sparkles className="w-3 h-3 text-amber-500" />
        Live ATV: <strong>₹{data.context.atv}</strong> · {fmtNum(data.context.total_loyalty_customers)} loyalty members · {fmtNum(data.context.total_bills)} bills
      </div>
      <div className="space-y-2 max-h-[560px] overflow-y-auto pr-1">
        {data.categories.map((cat) => {
          const open = !!openCats[cat.name];
          return (
            <div key={cat.name} className="border border-neutral-200 rounded">
              <button
                type="button"
                onClick={() => setOpenCats((s) => ({ ...s, [cat.name]: !s[cat.name] }))}
                className="w-full flex items-center justify-between px-3 py-2 hover:bg-neutral-50"
                data-testid={`cohort-cat-${cat.name.replace(/\s+/g, "-").toLowerCase()}`}
              >
                <div className="text-left">
                  <div className="text-[11px] uppercase tracking-widest text-neutral-700">{cat.name}</div>
                  <div className="text-[10px] text-neutral-400">{cat.cohorts.length} cohorts</div>
                </div>
                {open ? <ChevronDown className="w-3.5 h-3.5 text-neutral-400" /> : <ChevronRight className="w-3.5 h-3.5 text-neutral-400" />}
              </button>
              {open && (
                <div className="border-t border-neutral-100 p-2 space-y-1">
                  {cat.cohorts.map((c) => (
                    <div
                      key={c.id}
                      className="flex items-start justify-between gap-2 p-2 rounded hover:bg-neutral-50"
                      data-testid={`cohort-${c.id}`}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium truncate">{c.name}</div>
                        <div className="text-[11px] text-neutral-500 line-clamp-2">{c.description}</div>
                        <div className="text-[10px] text-neutral-400 mt-0.5">{fmtNum(c.matched_total)} matched</div>
                      </div>
                      <button
                        type="button"
                        onClick={() => loadCohort(c)}
                        disabled={busyId === c.id}
                        className="text-[11px] px-2 py-1 border border-neutral-300 rounded hover:bg-neutral-900 hover:text-white transition disabled:opacity-50 shrink-0"
                        data-testid={`load-cohort-${c.id}`}
                      >
                        {busyId === c.id ? <Loader2 className="w-3 h-3 animate-spin" /> : "Use"}
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
