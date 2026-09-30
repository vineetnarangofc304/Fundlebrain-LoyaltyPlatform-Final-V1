import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Store, Ticket, Package, Target, Search, X, Clock, Coins, Plus } from "lucide-react";

const OBJECTIVES = [
  { k: "generic", label: "Generic", icon: Target, hint: "Anyone who shops again after the send" },
  { k: "points", label: "Points", icon: Coins, hint: "Show live points & drive redemption" },
  { k: "store", label: "Store-wise", icon: Store, hint: "Drive footfall to specific stores" },
  { k: "coupon", label: "Coupon", icon: Ticket, hint: "Track coupon redemptions" },
  { k: "sku", label: "Product / SKU", icon: Package, hint: "Push categories or specific SKUs" },
];

const WINDOWS = [
  { k: "72h", label: "72 hours" }, { k: "3d", label: "3 days" }, { k: "5d", label: "5 days" },
  { k: "7d", label: "7 days" }, { k: "14d", label: "14 days" }, { k: "30d", label: "30 days" },
];

function Pill({ active, onClick, children, testid }) {
  return (
    <button type="button" onClick={onClick} data-testid={testid}
      className={`pill ${active ? "kazo-bg-burgundy text-white" : "pill-neutral"}`}>{children}</button>
  );
}

export default function CampaignObjective({ form, setForm, templates = [] }) {
  const [stores, setStores] = useState([]);
  const [storeQ, setStoreQ] = useState("");
  const [facets, setFacets] = useState({ categories: [], subcategories_by_category: {} });
  const [skuQ, setSkuQ] = useState("");
  const [skuResults, setSkuResults] = useState([]);

  const obj = form.objective || "generic";
  const p = form.objective_params || {};
  const setObj = (k) => setForm((f) => ({ ...f, objective: k, objective_params: {}, ...(k !== "points" ? { tiered: false } : {}) }));
  const setP = (patch) => setForm((f) => ({ ...f, objective_params: { ...(f.objective_params || {}), ...patch } }));
  const toggleArr = (key, val) => {
    const cur = p[key] || [];
    setP({ [key]: cur.includes(val) ? cur.filter((x) => x !== val) : [...cur, val] });
  };

  const smsTemplates = (templates || []).filter((t) => t.channel === "sms");
  const bands = form.points_bands || [];
  const setBand = (i, patch) => setForm((f) => {
    const arr = [...(f.points_bands || [])]; arr[i] = { ...arr[i], ...patch }; return { ...f, points_bands: arr };
  });
  const addBand = () => setForm((f) => ({ ...f, points_bands: [...(f.points_bands || []), { label: "", min_points: 1000, max_points: "", template_id: "" }] }));
  const removeBand = (i) => setForm((f) => ({ ...f, points_bands: (f.points_bands || []).filter((_, x) => x !== i) }));
  const toggleTiered = (on) => setForm((f) => ({
    ...f, tiered: on,
    points_bands: on && !(f.points_bands || []).length
      ? [{ label: "", min_points: 100, max_points: 499, template_id: "" }, { label: "", min_points: 500, max_points: "", template_id: "" }]
      : (f.points_bands || []),
  }));

  useEffect(() => {
    api.get("/stores").then((r) => {
      const d = r.data;
      setStores(Array.isArray(d) ? d : (d.stores || d.items || []));
    }).catch(() => {});
    api.get("/items/facets").then((r) => setFacets(r.data || {})).catch(() => {});
  }, []);

  useEffect(() => {
    if (obj !== "sku" || skuQ.trim().length < 2) { setSkuResults([]); return; }
    const t = setTimeout(() => {
      api.get("/items", { params: { q: skuQ.trim(), limit: 20 } })
        .then((r) => setSkuResults(r.data.items || [])).catch(() => setSkuResults([]));
    }, 300);
    return () => clearTimeout(t);
  }, [skuQ, obj]);

  const selectedCats = p.categories || [];
  const subOptions = [...new Set(selectedCats.flatMap((c) => (facets.subcategories_by_category || {})[c] || []))];
  const filteredStores = stores.filter((s) => {
    const hay = `${s.code || ""} ${s.name || ""}`.toLowerCase();
    return !storeQ || hay.includes(storeQ.toLowerCase());
  }).slice(0, 60);

  return (
    <div className="border border-neutral-200 rounded p-3 bg-neutral-50 space-y-3" data-testid="campaign-objective">
      <div>
        <label className="text-[10px] uppercase tracking-widest text-neutral-700 font-medium block mb-2">Campaign objective — what should this drive? (defines ROI)</label>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {OBJECTIVES.map((o) => {
            const Icon = o.icon; const active = obj === o.k;
            return (
              <button key={o.k} type="button" onClick={() => setObj(o.k)} data-testid={`objective-${o.k}`}
                className={`text-left border rounded p-2.5 transition ${active ? "border-burgundy bg-white ring-1 ring-burgundy" : "border-neutral-200 bg-white hover:border-neutral-300"}`}>
                <div className="flex items-center gap-1.5 font-medium text-sm"><Icon className="w-3.5 h-3.5" />{o.label}</div>
                <div className="text-[10px] text-neutral-500 mt-0.5 leading-tight">{o.hint}</div>
              </button>
            );
          })}
        </div>
      </div>

      {obj === "store" && (
        <div data-testid="objective-store-params">
          <label className="text-[10px] uppercase tracking-widest text-neutral-500 block mb-1">Target stores</label>
          <div className="relative mb-2">
            <Search className="w-3.5 h-3.5 absolute left-2 top-2.5 text-neutral-400" />
            <input className="k-input pl-7" placeholder="Search store code / name" value={storeQ} onChange={(e) => setStoreQ(e.target.value)} data-testid="store-search" />
          </div>
          <div className="flex gap-1.5 flex-wrap max-h-32 overflow-y-auto p-1 bg-white border rounded">
            {filteredStores.map((s) => (
              <Pill key={s.code || s.id} active={(p.store_codes || []).includes(s.code)} onClick={() => toggleArr("store_codes", s.code)} testid={`store-opt-${s.code}`}>
                {s.code} · {s.name}
              </Pill>
            ))}
            {filteredStores.length === 0 && <span className="text-xs text-neutral-400 p-1">No stores</span>}
          </div>
          <div className="text-[10px] text-neutral-500 mt-1">{(p.store_codes || []).length} store(s) selected</div>
        </div>
      )}

      {obj === "points" && (
        <div className="space-y-3" data-testid="objective-points-params">
          <div className="text-xs text-neutral-600" data-testid="objective-points-note">
            Each recipient's <b>live points balance</b> is injected via the{" "}
            <code className="bg-white px-1 rounded border font-mono">{"{{points}}"}</code> variable —
            looked up by mobile number at send time. ROI tracks the points this audience actually
            redeems within the window below. Tip: use the <b>"By points balance"</b> or{" "}
            <b>"Points expiring soon"</b> audience so you only message customers who hold points.
          </div>

          <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
            <input type="checkbox" checked={!!form.tiered} onChange={(e) => toggleTiered(e.target.checked)} data-testid="tiered-toggle" />
            <span className="font-medium">Split into tiered points bands</span>
            <span className="text-[11px] text-neutral-500">— each band becomes its own campaign with its own message</span>
          </label>

          {form.tiered && (
            <div className="border border-neutral-200 rounded p-2.5 bg-white space-y-2" data-testid="bands-editor">
              <div className="hidden md:grid grid-cols-12 gap-2 text-[10px] uppercase tracking-widest text-neutral-400 px-0.5">
                <div className="col-span-3">Label</div>
                <div className="col-span-2">Min pts</div>
                <div className="col-span-2">Max pts</div>
                <div className="col-span-4">SMS template</div>
                <div className="col-span-1" />
              </div>
              {bands.map((b, i) => (
                <BandRow key={i} band={b} idx={i} smsTemplates={smsTemplates} canRemove={bands.length > 1}
                  onChange={(patch) => setBand(i, patch)} onRemove={() => removeBand(i)} />
              ))}
              {bands.length < 4 && (
                <button type="button" className="k-btn k-btn-sm k-btn-ghost" onClick={addBand} data-testid="band-add">
                  <Plus className="w-3 h-3" /> Add band
                </button>
              )}
              <div className="text-[10px] text-neutral-500 pt-1 border-t border-neutral-100">
                Leave <b>Max</b> blank for "and above". Bands with no template send simulated metrics only.
              </div>
            </div>
          )}
        </div>
      )}

      {obj === "coupon" && (
        <div className="text-xs text-neutral-600" data-testid="objective-coupon-note">
          Redemptions of the coupon selected below will be tracked as this campaign's ROI. Pick the coupon in the "coupon" field further down.
        </div>
      )}

      {obj === "sku" && (
        <div className="space-y-2" data-testid="objective-sku-params">
          <div>
            <label className="text-[10px] uppercase tracking-widest text-neutral-500 block mb-1">Categories</label>
            <div className="flex gap-1.5 flex-wrap max-h-24 overflow-y-auto p-1 bg-white border rounded">
              {(facets.categories || []).map((c) => (
                <Pill key={c} active={selectedCats.includes(c)} onClick={() => toggleArr("categories", c)} testid={`cat-${c}`}>{c}</Pill>
              ))}
              {(facets.categories || []).length === 0 && <span className="text-xs text-neutral-400 p-1">No item master data</span>}
            </div>
          </div>
          {subOptions.length > 0 && (
            <div>
              <label className="text-[10px] uppercase tracking-widest text-neutral-500 block mb-1">Subcategories</label>
              <div className="flex gap-1.5 flex-wrap max-h-24 overflow-y-auto p-1 bg-white border rounded">
                {subOptions.map((s) => (
                  <Pill key={s} active={(p.subcategories || []).includes(s)} onClick={() => toggleArr("subcategories", s)} testid={`sub-${s}`}>{s}</Pill>
                ))}
              </div>
            </div>
          )}
          <div>
            <label className="text-[10px] uppercase tracking-widest text-neutral-500 block mb-1">Specific SKUs (optional)</label>
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-2 top-2.5 text-neutral-400" />
              <input className="k-input pl-7" placeholder="Search SKU / name to add" value={skuQ} onChange={(e) => setSkuQ(e.target.value)} data-testid="sku-search" />
            </div>
            {skuResults.length > 0 && (
              <div className="border rounded mt-1 bg-white max-h-32 overflow-y-auto">
                {skuResults.map((it) => (
                  <button key={it.sku} type="button" onClick={() => { toggleArr("skus", it.sku); setSkuQ(""); setSkuResults([]); }}
                    className="w-full text-left px-2 py-1.5 text-xs hover:bg-neutral-50 flex justify-between" data-testid={`sku-opt-${it.sku}`}>
                    <span>{it.sku} · {it.name}</span><span className="text-neutral-400">{it.category}</span>
                  </button>
                ))}
              </div>
            )}
            {(p.skus || []).length > 0 && (
              <div className="flex gap-1.5 flex-wrap mt-2">
                {(p.skus || []).map((s) => (
                  <span key={s} className="pill kazo-bg-burgundy text-white flex items-center gap-1" data-testid={`sku-chip-${s}`}>
                    {s} <X className="w-3 h-3 cursor-pointer" onClick={() => toggleArr("skus", s)} />
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      <div>
        <label className="text-[10px] uppercase tracking-widest text-neutral-500 block mb-1"><Clock className="w-3 h-3 inline mr-1" />Default ROI window (bill within this time after send counts)</label>
        <div className="flex gap-1.5 flex-wrap">
          {WINDOWS.map((w) => (
            <Pill key={w.k} active={(form.roi_window || "7d") === w.k} onClick={() => setForm((f) => ({ ...f, roi_window: w.k }))} testid={`roiwin-${w.k}`}>{w.label}</Pill>
          ))}
        </div>
      </div>
    </div>
  );
}

export { WINDOWS };

function BandRow({ band, idx, smsTemplates, canRemove, onChange, onRemove }) {
  const [count, setCount] = useState(null);
  useEffect(() => {
    const t = setTimeout(async () => {
      const mn = parseInt(band.min_points, 10);
      if (!mn && mn !== 0) { setCount(null); return; }
      const af = { min_points: mn || 1 };
      if (band.max_points !== "" && band.max_points != null) af.max_points = parseInt(band.max_points, 10);
      try {
        const r = await api.post("/campaigns/audience-preview", { audience_type: "points", audience_filter: af });
        setCount(r.data.total_audience);
      } catch { setCount(null); }
    }, 400);
    return () => clearTimeout(t);
  }, [band.min_points, band.max_points]);

  return (
    <div className="grid grid-cols-12 gap-2 items-center" data-testid={`band-row-${idx}`}>
      <input className="k-input col-span-3" placeholder="Label" value={band.label || ""} onChange={(e) => onChange({ label: e.target.value })} data-testid={`band-label-${idx}`} />
      <input className="k-input col-span-2" type="number" min="1" placeholder="Min" value={band.min_points ?? ""} onChange={(e) => onChange({ min_points: e.target.value })} data-testid={`band-min-${idx}`} />
      <input className="k-input col-span-2" type="number" placeholder="∞" value={band.max_points ?? ""} onChange={(e) => onChange({ max_points: e.target.value })} data-testid={`band-max-${idx}`} />
      <select className="k-input col-span-4" value={band.template_id || ""} onChange={(e) => onChange({ template_id: e.target.value })} data-testid={`band-template-${idx}`}>
        <option value="">— Simulated (no send) —</option>
        {smsTemplates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
      </select>
      <button type="button" className="col-span-1 flex justify-center text-rose-600 disabled:opacity-25" onClick={onRemove} disabled={!canRemove} data-testid={`band-remove-${idx}`} title="Remove band">
        <X className="w-4 h-4" />
      </button>
      <div className="col-span-12 text-[10px] text-neutral-500 -mt-1" data-testid={`band-count-${idx}`}>
        {count == null ? "…" : `${count.toLocaleString()} customers in this band`}
      </div>
    </div>
  );
}

