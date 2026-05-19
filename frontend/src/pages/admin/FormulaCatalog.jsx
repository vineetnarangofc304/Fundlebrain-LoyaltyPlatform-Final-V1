/* Formula Catalog — auto-generated audit reference for every KPI. */
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader, SectionHeading } from "./_shared";
import { Search } from "lucide-react";

const CAT_COLORS = {
  Revenue: "#571326",
  Customer: "#1E3A8A",
  RFM: "#0E7C7B",
  Cohort: "#B45309",
  Loyalty: "#C7A76D",
  Campaign: "#9F1239",
  Experience: "#047857",
  Operations: "#334155",
};

export default function FormulaCatalog() {
  const [data, setData] = useState(null);
  const [search, setSearch] = useState("");
  const [activeCat, setActiveCat] = useState(null);

  useEffect(() => {
    api.get("/dashboard/formula-catalog").then((r) => setData(r.data));
  }, []);

  if (!data) return <div className="p-10 text-neutral-500">Loading formula catalog…</div>;

  const filteredCategories = data.categories.map((cat) => ({
    ...cat,
    formulas: cat.formulas.filter((f) =>
      !search ||
      f.name.toLowerCase().includes(search.toLowerCase()) ||
      f.description.toLowerCase().includes(search.toLowerCase()) ||
      f.formula.toLowerCase().includes(search.toLowerCase())
    ),
  })).filter((c) => (!activeCat || c.category === activeCat) && c.formulas.length > 0);

  return (
    <div data-testid="formula-catalog">
      <PageHeader
        title="Formula Catalog"
        subtitle={`${data.total} LIVE KPI DEFINITIONS · SINGLE SOURCE OF TRUTH`}
      />

      <div className="p-8 space-y-6">
        <div className="bg-white border border-black/10 p-4 flex items-center gap-3">
          <Search className="w-4 h-4 text-neutral-500" />
          <input
            type="text"
            placeholder="Search formulas, fields, descriptions…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1 outline-none text-sm"
            data-testid="fc-search"
          />
          <div className="flex gap-2 flex-wrap">
            <button
              onClick={() => setActiveCat(null)}
              className={`px-3 py-1 text-[10px] uppercase tracking-widest border transition-colors ${
                !activeCat ? "bg-neutral-900 text-white border-neutral-900" : "bg-white border-black/10 text-neutral-600 hover:border-black/40"
              }`}
              data-testid="fc-cat-all"
            >
              All ({data.total})
            </button>
            {data.categories.map((c) => (
              <button
                key={c.category}
                onClick={() => setActiveCat(c.category)}
                className={`px-3 py-1 text-[10px] uppercase tracking-widest border transition-colors ${
                  activeCat === c.category ? "text-white" : "bg-white text-neutral-600 hover:opacity-80"
                }`}
                style={activeCat === c.category ? { background: CAT_COLORS[c.category], borderColor: CAT_COLORS[c.category] } : { borderColor: `${CAT_COLORS[c.category]}40` }}
                data-testid={`fc-cat-${c.category.toLowerCase()}`}
              >
                {c.category} ({c.count})
              </button>
            ))}
          </div>
        </div>

        {filteredCategories.length === 0 && (
          <div className="bg-white border border-black/10 p-10 text-center text-neutral-500">
            No formulas match "{search}"
          </div>
        )}

        {filteredCategories.map((cat) => (
          <div key={cat.category} className="bg-white border border-black/10 p-5" data-testid={`fc-section-${cat.category.toLowerCase()}`}>
            <SectionHeading
              eyebrow={`${cat.count} FORMULAS`}
              title={cat.category}
              accent="indigo"
              right={<span className="text-[10px] uppercase tracking-widest" style={{ color: CAT_COLORS[cat.category] }}>—</span>}
            />
            <div className="grid md:grid-cols-2 gap-3">
              {cat.formulas.map((f) => (
                <div
                  key={f.key}
                  className="border p-4 relative overflow-hidden"
                  style={{ borderColor: `${CAT_COLORS[cat.category]}25`, background: `${CAT_COLORS[cat.category]}05` }}
                  data-testid={`fc-formula-${f.key}`}
                >
                  <div className="absolute top-0 left-0 bottom-0 w-1" style={{ background: CAT_COLORS[cat.category] }} />
                  <div className="pl-2">
                    <div className="font-display text-lg mb-1">{f.name}</div>
                    <div className="text-xs text-neutral-600 mb-3">{f.description}</div>
                    <div className="bg-neutral-900 text-emerald-300 font-mono text-[11px] p-2 leading-relaxed">
                      {f.formula}
                    </div>
                    <div className="text-[10px] text-neutral-400 mt-2 uppercase tracking-widest">
                      SOURCE · {f.live_source}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}

        <div className="text-[10px] text-neutral-400 uppercase tracking-widest">
          Catalog auto-generated from <span className="font-mono">/app/backend/routes/fundlebrain_routes.py · FORMULA_CATALOG</span>
        </div>
      </div>
    </div>
  );
}
