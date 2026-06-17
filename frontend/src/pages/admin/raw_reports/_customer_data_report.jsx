import { useState, useEffect, useRef } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import {
  FilterBar, NarrativeCard, ExportMenu, ReportTable, ColumnPicker,
  ReportBarChart, DrillModal, fmtNum, fmtMoney2, fmtPct, fmtDecimal,
} from "./_shared";

const GROUPS = ["location", "city", "state", "zone", "month", "tier"];

const ALL_COLUMNS = [
  { key: "group_key",                    label: "Location",             sortable: true,  drillable: false },
  { key: "total_customers",              label: "Total Customers",      align: "right", format: fmtNum },
  { key: "total_bills",                  label: "Total Bills",          align: "right", format: fmtNum },
  { key: "repeat_customers",             label: "Repeat Customers",     align: "right", format: fmtNum },
  { key: "one_timer_customers",          label: "One-Timer Customers",  align: "right", format: fmtNum },
  { key: "repeat_pct",                   label: "Repeat %",             align: "right", format: fmtPct, drillable: false },
  { key: "total_purchase",               label: "Total Purchase",       align: "right", format: fmtMoney2 },
  { key: "avg_lifetime_spend",           label: "Avg Lifetime Spend",   align: "right", format: fmtMoney2, drillable: false },
  { key: "avg_bills_per_customer",       label: "Avg Bills / Customer", align: "right", format: fmtDecimal, drillable: false },
  { key: "total_earn_points",            label: "Total Earn Points",    align: "right", format: fmtNum },
  { key: "total_lifetime_spend",         label: "Total Lifetime Spend", align: "right", format: fmtMoney2 },
  { key: "total_lifetime_points_earned", label: "Total Lifetime Points",align: "right", format: fmtNum },
  { key: "total_points_balance",         label: "Total Points Balance", align: "right", format: fmtNum },
  { key: "avg_visit_count",              label: "Avg Visit Count",      align: "right", format: fmtDecimal, drillable: false },
];

const DEFAULT_VISIBLE = ["group_key", "total_customers", "total_bills", "repeat_customers",
                            "total_purchase", "avg_lifetime_spend", "repeat_pct"];

export default function CustomerDataReport() {
  const [filters, setFilters] = useState({ start_date: "", end_date: "", group_by: "location" });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [drill, setDrill] = useState(null);
  const [visibleKeys, setVisibleKeys] = useState(DEFAULT_VISIBLE);
  const debounceRef = useRef(null);

  const load = async (override = filters) => {
    setLoading(true);
    // Clear data so user sees an explicit loading state — fixes "month filter not working" perception
    setData(null);
    try {
      const r = await api.post("/raw-reports/customer-data", override);
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

  const groupLabel = filters.group_by[0].toUpperCase() + filters.group_by.slice(1);
  // Update first column label dynamically
  const columns = ALL_COLUMNS
    .filter((c) => visibleKeys.includes(c.key))
    .map((c) => c.key === "group_key" ? { ...c, label: groupLabel } : c);

  // Filter available columns by which actually exist in the data
  const availableColumns = data && data.rows.length > 0
    ? ALL_COLUMNS.filter((c) => c.key === "group_key" || (c.key in data.rows[0]))
    : ALL_COLUMNS;

  return (
    <div>
      <FilterBar value={filters} onChange={onChange} onApply={() => load()} loading={loading} groupOptions={GROUPS} />

      <div className="flex justify-between items-center mb-3 gap-2 flex-wrap">
        <div className="text-xs text-neutral-500">
          Click any number to drill into the customers · Use Columns to add/remove fields
        </div>
        <div className="flex gap-2">
          <ColumnPicker
            allColumns={availableColumns}
            visibleKeys={visibleKeys.filter((k) => availableColumns.some((c) => c.key === k))}
            onChange={setVisibleKeys}
            requiredKeys={["group_key"]}
          />
          <ExportMenu report="Customer Data" group_by={filters.group_by}
                       columns={columns} rows={data?.rows || []} totals={data?.totals} />
        </div>
      </div>

      {data?.chart?.length > 0 && (
        <div className="mb-4">
          <ReportBarChart data={data.chart} dataKey="value" xKey="label"
                           title={`Customer Count by ${groupLabel}`} color="#9b2c2c" />
        </div>
      )}

      <ReportTable
        columns={columns}
        rows={data?.rows || []}
        totals={data ? { group_key: "TOTAL", ...data.totals } : null}
        onCellClick={(c, r) => setDrill({ group_key: r.group_key, metric: c.key })}
        loading={loading}
      />

      <NarrativeCard report="customer-data" group_by={filters.group_by}
                       rows={data?.rows || []} totals={data?.totals || {}} filters={filters} />

      <DrillModal open={!!drill} onClose={() => setDrill(null)}
                    report="Customer Data" group_by={filters.group_by}
                    group_key={drill?.group_key} metric={drill?.metric} filters={filters} />
    </div>
  );
}
