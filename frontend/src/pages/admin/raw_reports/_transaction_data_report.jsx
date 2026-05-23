import { useState, useEffect, useRef } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import {
  FilterBar, NarrativeCard, ExportMenu, ReportTable, ColumnPicker,
  ReportComposedChart, DrillModal, fmtNum, fmtINR, fmtPct,
} from "./_shared";

const GROUPS = ["location", "city", "state", "zone", "month"];

const ALL_COLUMNS = [
  { key: "group_key",             label: "Location",             drillable: false },
  { key: "total_customers",       label: "Total Customers",      align: "right", format: fmtNum },
  { key: "total_bills",           label: "Total Bills",          align: "right", format: fmtNum },
  { key: "total_purchase",        label: "Total Purchase",       align: "right", format: fmtINR },
  { key: "total_gross_purchase",  label: "Total Gross Purchase", align: "right", format: fmtINR },
  { key: "total_discount",        label: "Total Discount",       align: "right", format: fmtINR },
  { key: "discount_pct",          label: "Discount %",           align: "right", format: fmtPct, drillable: false },
  { key: "avg_bill_value",        label: "Avg Bill Value (AOV)", align: "right", format: fmtINR, drillable: false },
  { key: "avg_customer_spend",    label: "Avg Customer Spend",   align: "right", format: fmtINR, drillable: false },
  { key: "total_earn_points",     label: "Total Earn Points",    align: "right", format: fmtNum },
];

const DEFAULT_VISIBLE = ["group_key", "total_customers", "total_bills", "total_purchase",
                            "avg_bill_value", "total_earn_points"];

export default function TransactionDataReport() {
  const [filters, setFilters] = useState({ start_date: "", end_date: "", group_by: "location" });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [drill, setDrill] = useState(null);
  const [visibleKeys, setVisibleKeys] = useState(DEFAULT_VISIBLE);
  const debounceRef = useRef(null);

  const load = async (override = filters) => {
    setLoading(true);
    setData(null);
    try {
      const r = await api.post("/raw-reports/transaction-data", override);
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
  const columns = ALL_COLUMNS
    .filter((c) => visibleKeys.includes(c.key))
    .map((c) => c.key === "group_key" ? { ...c, label: groupLabel } : c);

  return (
    <div>
      <FilterBar value={filters} onChange={onChange} onApply={() => load()} loading={loading} groupOptions={GROUPS} />

      <div className="flex justify-between items-center mb-3 gap-2 flex-wrap">
        <div className="text-xs text-neutral-500">Click any number to drill · Use Columns to add/remove fields</div>
        <div className="flex gap-2">
          <ColumnPicker allColumns={ALL_COLUMNS} visibleKeys={visibleKeys}
                          onChange={setVisibleKeys} requiredKeys={["group_key"]} />
          <ExportMenu report="Transaction Data" group_by={filters.group_by}
                       columns={columns} rows={data?.rows || []} totals={data?.totals} />
        </div>
      </div>

      {data?.chart?.length > 0 && (
        <div className="mb-4">
          <ReportComposedChart
            data={data.chart}
            bars={[
              { key: "total_purchase",     label: "Total Purchase",   color: "#84cc16" },
              { key: "total_earn_points",  label: "Total Earn Points", color: "#f59e0b" },
              { key: "total_bills",        label: "Total Bills",       color: "#0e7c7b" },
            ]}
            lines={[
              { key: "total_customers",    label: "Unique Customers",  color: "#9b2c2c" },
            ]}
            title={`${groupLabel}-wise Transactions Summary`}
          />
        </div>
      )}

      <ReportTable
        columns={columns}
        rows={data?.rows || []}
        totals={data ? { group_key: "TOTAL", ...data.totals } : null}
        onCellClick={(c, r) => setDrill({ group_key: r.group_key, metric: c.key })}
        loading={loading}
      />

      <NarrativeCard report="transaction-data" group_by={filters.group_by}
                       rows={data?.rows || []} totals={data?.totals || {}} filters={filters} />

      <DrillModal open={!!drill} onClose={() => setDrill(null)}
                    report="Transaction Data" group_by={filters.group_by}
                    group_key={drill?.group_key} metric={drill?.metric} filters={filters} />
    </div>
  );
}
