import { useState, useEffect } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import {
  FilterBar, NarrativeCard, ExportMenu, ReportTable,
  DrillModal, fmtNum,
} from "./_shared";

export default function CustomersByVisitReport() {
  const [filters, setFilters] = useState({ start_date: "", end_date: "", tier: "", location: "" });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [drill, setDrill] = useState(null);
  const [tiers, setTiers] = useState([]);
  const [locations, setLocations] = useState([]);

  // Load lookups for tier + location dropdowns
  useEffect(() => {
    api.get("/dashboard/stores", { params: { limit: 1000 } })
      .then((r) => {
        const data = r.data;
        const list = Array.isArray(data) ? data : (data?.rows || data?.stores || []);
        setLocations(list.map((s) => s.name).filter(Boolean).sort());
      })
      .catch(() => setLocations([]));
    setTiers(["silver", "gold", "platinum", "diamond", "bronze"]);
  }, []);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.post("/raw-reports/customers-by-visit", filters);
      setData(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Load failed");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const rows = (data?.rows || []).map((r, i) => ({ sno: i + 1, ...r }));
  const columns = [
    { key: "sno", label: "S.No.", sortable: false, drillable: false },
    { key: "visits", label: "Visits", align: "right", format: fmtNum, drillable: false },
    { key: "total_customers", label: "Total Customers", align: "right", format: fmtNum },
  ];

  const extraSlot = (
    <>
      <div className="flex flex-col">
        <label className="text-[10px] uppercase tracking-widest text-neutral-500 mb-1">Tier</label>
        <select
          value={filters.tier || ""}
          onChange={(e) => setFilters({ ...filters, tier: e.target.value })}
          className="border border-neutral-300 rounded px-2 py-1.5 text-sm w-40"
          data-testid="filter-tier"
        >
          <option value="">— Select Tier —</option>
          {tiers.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>
      <div className="flex flex-col">
        <label className="text-[10px] uppercase tracking-widest text-neutral-500 mb-1">Location</label>
        <select
          value={filters.location || ""}
          onChange={(e) => setFilters({ ...filters, location: e.target.value })}
          className="border border-neutral-300 rounded px-2 py-1.5 text-sm w-56"
          data-testid="filter-location"
        >
          <option value="">— Select Location —</option>
          {locations.map((l) => <option key={l} value={l}>{l}</option>)}
        </select>
      </div>
    </>
  );

  return (
    <div>
      <FilterBar value={filters} onChange={setFilters} onApply={load} loading={loading}
                   extraSlot={extraSlot} />

      <div className="flex justify-end mb-3">
        <ExportMenu report="Customers by Visit" group_by="visits"
                     columns={columns} rows={rows} totals={data?.totals} />
      </div>

      <NarrativeCard report="customers-by-visit" group_by="visits"
                       rows={rows} totals={data?.totals || {}} filters={filters} />

      <ReportTable
        columns={columns}
        rows={rows}
        totals={data ? { sno: "", visits: data.totals.visits, total_customers: data.totals.total_customers } : null}
        onCellClick={(c, r) => setDrill({ group_key: `${r.visits} visits`, visits: r.visits, metric: c.key })}
      />

      <DrillModal open={!!drill} onClose={() => setDrill(null)}
                    report="Customers by Visit" group_by="visits"
                    group_key={drill?.group_key} visits={drill?.visits} metric={drill?.metric} filters={filters} />
    </div>
  );
}
