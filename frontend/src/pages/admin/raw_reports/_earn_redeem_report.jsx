import { useState, useEffect } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import {
  FilterBar, NarrativeCard, ExportMenu, ReportTable,
  ReportComposedChart, DrillModal, fmtNum,
} from "./_shared";

const GROUPS = ["location", "city", "state", "zone", "month"];

export default function EarnRedeemReport() {
  const [filters, setFilters] = useState({ start_date: "", end_date: "", group_by: "location" });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [drill, setDrill] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.post("/raw-reports/earn-redeem", filters);
      setData(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Load failed");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const groupLabel = filters.group_by[0].toUpperCase() + filters.group_by.slice(1);
  const rows = (data?.rows || []).map((r, i) => ({ sno: i + 1, ...r }));
  const columns = [
    { key: "sno", label: "S.No.", sortable: false, drillable: false },
    { key: "group_key", label: groupLabel, drillable: false },
    { key: "total_earn_points",    label: "Total Earn Points",    align: "right", format: fmtNum },
    { key: "total_redeem_points",  label: "Total Redeem Points",  align: "right", format: fmtNum },
    { key: "total_bonus_points",   label: "Total Bonus Points",   align: "right", format: fmtNum },
    { key: "total_expired_points", label: "Total Expired Points", align: "right", format: fmtNum },
    { key: "total_liability",      label: "Total Liability",      align: "right", format: fmtNum },
  ];

  return (
    <div>
      <FilterBar value={filters} onChange={setFilters} onApply={load} loading={loading} groupOptions={GROUPS} />

      <div className="flex justify-end mb-3">
        <ExportMenu report="Earn Redeem" group_by={filters.group_by}
                     columns={columns} rows={rows} totals={data?.totals} />
      </div>

      <NarrativeCard report="earn-redeem" group_by={filters.group_by}
                       rows={rows} totals={data?.totals || {}} filters={filters} />

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

      <DrillModal open={!!drill} onClose={() => setDrill(null)}
                    report="Earn Redeem" group_by={filters.group_by}
                    group_key={drill?.group_key} metric={drill?.metric} filters={filters} />
    </div>
  );
}
