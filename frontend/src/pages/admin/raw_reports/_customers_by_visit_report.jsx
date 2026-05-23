import { useState, useEffect, useRef } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import {
  FilterBar, NarrativeCard, ExportMenu, ReportTable, ColumnPicker,
  DrillModal, fmtNum, fmtINR,
} from "./_shared";

const ALL_COLUMNS = [
  { key: "sno",                label: "S.No.",            sortable: false, drillable: false },
  { key: "visits",             label: "Visits",           align: "right", format: fmtNum, drillable: false },
  { key: "total_customers",    label: "Total Customers",  align: "right", format: fmtNum },
  { key: "total_purchase",     label: "Total Purchase",   align: "right", format: fmtINR },
  { key: "avg_customer_spend", label: "Avg Customer Spend", align: "right", format: fmtINR, drillable: false },
];

const DEFAULT_VISIBLE = ALL_COLUMNS.map((c) => c.key);

export default function CustomersByVisitReport() {
  const [filters, setFilters] = useState({ start_date: "", end_date: "", tier: "", location: "" });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [drill, setDrill] = useState(null);
  const [tiers, setTiers] = useState([]);
  const [locations, setLocations] = useState([]);
  const [visibleKeys, setVisibleKeys] = useState(DEFAULT_VISIBLE);
  const debounceRef = useRef(null);

  // Load lookups for tier + location dropdowns
  useEffect(() => {
    api.get("/dashboard/stores", { params: { limit: 1000 } })
      .then((r) => {
        const d = r.data;
        const list = Array.isArray(d) ? d : (d?.rows || d?.stores || []);
        setLocations(list.map((s) => s.name).filter(Boolean).sort());
      })
      .catch(() => setLocations([]));
    setTiers(["silver", "gold", "platinum", "diamond", "bronze"]);
  }, []);

  const load = async (override = filters) => {
    setLoading(true);
    try {
      const r = await api.post("/raw-reports/customers-by-visit", override);
      setData(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Load failed");
    } finally {
      setLoading(false);
    }
  };

  const onChange = (newFilters, autoRefetch = false) => {
    setFilters(newFilters);
    if (autoRefetch) {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => load(newFilters), 250);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const rows = (data?.rows || []).map((r, i) => ({ sno: i + 1, ...r }));
  const columns = ALL_COLUMNS.filter((c) => visibleKeys.includes(c.key));

  const extraSlot = (
    <>
      <div className="flex flex-col">
        <label className="text-[10px] uppercase tracking-widest text-neutral-500 mb-1">Tier</label>
        <select
          value={filters.tier || ""}
          onChange={(e) => onChange({ ...filters, tier: e.target.value }, true)}
          className="border border-neutral-300 rounded px-2 py-1.5 text-sm w-40"
          data-testid="filter-tier"
        >
          <option value="">— All Tiers —</option>
          {tiers.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>
      <div className="flex flex-col">
        <label className="text-[10px] uppercase tracking-widest text-neutral-500 mb-1">Location</label>
        <select
          value={filters.location || ""}
          onChange={(e) => onChange({ ...filters, location: e.target.value }, true)}
          className="border border-neutral-300 rounded px-2 py-1.5 text-sm w-56"
          data-testid="filter-location"
        >
          <option value="">— All Locations —</option>
          {locations.map((l) => <option key={l} value={l}>{l}</option>)}
        </select>
      </div>
    </>
  );

  return (
    <div>
      <FilterBar value={filters} onChange={onChange} onApply={() => load()} loading={loading}
                   extraSlot={extraSlot} />

      <div className="flex justify-between items-center mb-3 gap-2 flex-wrap">
        <div className="text-xs text-neutral-500">Click any customer count to drill into the list · Use Columns to add/remove fields</div>
        <div className="flex gap-2">
          <ColumnPicker allColumns={ALL_COLUMNS} visibleKeys={visibleKeys}
                          onChange={setVisibleKeys} requiredKeys={["sno", "visits"]} />
          <ExportMenu report="Customers by Visit" group_by="visits"
                       columns={columns} rows={rows} totals={data?.totals} />
        </div>
      </div>

      <ReportTable
        columns={columns}
        rows={rows}
        totals={data ? { sno: "TOTAL", visits: data.totals.visits, total_customers: data.totals.total_customers,
                          total_purchase: data.totals.total_purchase, avg_customer_spend: data.totals.avg_customer_spend } : null}
        onCellClick={(c, r) => setDrill({ group_key: `${r.visits} visits`, visits: r.visits, metric: c.key })}
      />

      <NarrativeCard report="customers-by-visit" group_by="visits"
                       rows={rows} totals={data?.totals || {}} filters={filters} />

      <DrillModal open={!!drill} onClose={() => setDrill(null)}
                    report="Customers by Visit" group_by="visits"
                    group_key={drill?.group_key} visits={drill?.visits} metric={drill?.metric} filters={filters} />
    </div>
  );
}
