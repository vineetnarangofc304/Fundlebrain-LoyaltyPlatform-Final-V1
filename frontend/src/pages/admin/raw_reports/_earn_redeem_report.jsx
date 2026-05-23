import { useState, useEffect, useRef } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import {
  FilterBar, NarrativeCard, ExportMenu, ReportTable, ColumnPicker,
  ReportComposedChart, DrillModal, fmtNum, fmtPct,
} from "./_shared";

const GROUPS = ["location", "city", "state", "zone", "month"];

const ALL_COLUMNS = [
  { key: "sno",                  label: "S.No.",                sortable: false, drillable: false },
  { key: "group_key",            label: "Location",             drillable: false },
  { key: "total_earn_points",    label: "Total Earn Points",    align: "right", format: fmtNum },
  { key: "total_bonus_points",   label: "Total Bonus Points",   align: "right", format: fmtNum },
  { key: "gross_points_earned",  label: "Gross Points Earned",  align: "right", format: fmtNum, drillable: false },
  { key: "total_redeem_points",  label: "Total Redeem Points",  align: "right", format: fmtNum },
  { key: "total_expired_points", label: "Total Expired Points", align: "right", format: fmtNum, drillable: false },
  { key: "redemption_rate_pct",  label: "Redemption Rate",      align: "right", format: fmtPct, drillable: false },
  { key: "total_liability",      label: "Total Liability",      align: "right", format: fmtNum, drillable: false },
];

const DEFAULT_VISIBLE = ["sno", "group_key", "total_earn_points", "total_redeem_points",
                            "total_bonus_points", "total_expired_points", "total_liability"];

export default function EarnRedeemReport() {
  const [filters, setFilters] = useState({ start_date: "", end_date: "", group_by: "location" });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [drill, setDrill] = useState(null);
  const [visibleKeys, setVisibleKeys] = useState(DEFAULT_VISIBLE);
  const debounceRef = useRef(null);

  const load = async (override = filters) => {
    setLoading(true);
    try {
      const r = await api.post("/raw-reports/earn-redeem", override);
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
  const rows = (data?.rows || []).map((r, i) => ({ sno: i + 1, ...r }));
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
                          onChange={setVisibleKeys} requiredKeys={["sno", "group_key"]} />
          <ExportMenu report="Earn Redeem" group_by={filters.group_by}
                       columns={columns} rows={rows} totals={data?.totals} />
        </div>
      </div>

      {data?.chart?.length > 0 && (
        <div className="mb-4">
          <ReportComposedChart
            data={data.chart}
            bars={[
              { key: "earn",   label: "Total Earn",   color: "#3b82f6" },
              { key: "redeem", label: "Total Redeem", color: "#84cc16" },
            ]}
            lines={[
              { key: "bonus",   label: "Total Bonus",   color: "#f59e0b" },
              { key: "expired", label: "Total Expired", color: "#dc2626", dashed: true },
            ]}
            title={`${groupLabel}-wise Earn, Redeem, Bonus & Expired Points`}
          />
        </div>
      )}

      <ReportTable
        columns={columns}
        rows={rows}
        totals={data ? { sno: "", group_key: "TOTAL", ...data.totals } : null}
        onCellClick={(c, r) => setDrill({ group_key: r.group_key, metric: c.key })}
      />

      <NarrativeCard report="earn-redeem" group_by={filters.group_by}
                       rows={rows} totals={data?.totals || {}} filters={filters} />

      <DrillModal open={!!drill} onClose={() => setDrill(null)}
                    report="Earn Redeem" group_by={filters.group_by}
                    group_key={drill?.group_key} metric={drill?.metric} filters={filters} />
    </div>
  );
}
