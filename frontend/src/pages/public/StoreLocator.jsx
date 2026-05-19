import { useEffect, useState } from "react";
import api from "@/lib/api";
import { MapPin, Phone } from "lucide-react";

export default function StoreLocator() {
  const [stores, setStores] = useState([]);
  const [cities, setCities] = useState([]);
  const [filter, setFilter] = useState({ city: "", q: "" });
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    const [s, c] = await Promise.all([
      api.get("/public/stores", { params: filter }),
      api.get("/public/store-cities"),
    ]);
    setStores(s.data);
    setCities(c.data);
    setLoading(false);
  };
  useEffect(() => { load(); }, [filter.city]);

  return (
    <div className="max-w-[1300px] mx-auto px-6 lg:px-12 py-20" data-testid="page-store-locator">
      <div className="text-[11px] uppercase tracking-[0.3em] kazo-text-burgundy mb-4">STORE LOCATOR</div>
      <h1 className="editorial-headline text-5xl lg:text-7xl mb-12">Find your<br /><em className="font-light">nearest KAZO.</em></h1>

      <div className="flex flex-col md:flex-row gap-3 mb-8 max-w-2xl">
        <select className="k-input" value={filter.city} onChange={(e) => setFilter({ ...filter, city: e.target.value })} data-testid="store-filter-city">
          <option value="">All cities</option>
          {cities.map((c) => <option key={c.city} value={c.city}>{c.city} ({c.count})</option>)}
        </select>
        <input className="k-input" placeholder="Search by store name or mall" value={filter.q} onChange={(e) => setFilter({ ...filter, q: e.target.value })} onKeyDown={(e) => e.key === "Enter" && load()} data-testid="store-search" />
        <button className="k-btn" onClick={load}>Search</button>
      </div>

      {loading ? <div className="text-neutral-500">Loading stores…</div> : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
          {stores.map((s) => (
            <div key={s.id} className="bg-white border border-black/10 p-6" data-testid={`store-card-${s.id}`}>
              <div className="text-[11px] uppercase tracking-widest text-neutral-500 mb-1">{s.code}</div>
              <h3 className="font-display text-xl mb-3">{s.name}</h3>
              <div className="text-sm text-neutral-600 space-y-1.5">
                <div className="flex items-start gap-2"><MapPin className="w-4 h-4 mt-0.5 flex-shrink-0" /><span>{s.address}</span></div>
                {s.phone && <div className="flex items-center gap-2"><Phone className="w-4 h-4" /><span>{s.phone}</span></div>}
              </div>
              <div className="mt-4 text-xs text-neutral-400">Manager · {s.manager_name}</div>
            </div>
          ))}
          {stores.length === 0 && <div className="col-span-full text-neutral-500">No stores match your search.</div>}
        </div>
      )}
    </div>
  );
}
