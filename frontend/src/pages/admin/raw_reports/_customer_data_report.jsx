import { useState, useEffect } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import {
  FilterBar, NarrativeCard, ExportMenu, ReportTable,
  ReportBarChart, DrillModal, fmtNum,
} from "./_shared";

const GROUPS = ["location", "city", "state", "zone", "month", "tier"];

export default function CustomerDataReport() {
  const [filters, setFilters] = useState({ start_date: "", end_date: "", group_by: "location" });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [drill, setDrill] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.post("/raw-reports/customer-data", filters);
      setData(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Load failed");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const groupLabel = filters.group_by[0].toUpperCase() + filters.group_by.slice(1);
  const columns = [
    { key: "group_key", label: groupLabel, sortable: true },
    {
      key: "total_customers", label: "Total Customers", align: "right",
      format: fmtNum,
    },
  ];

  return (
    <div>
      <FilterBar
        value={filters}
        onChange={setFilters}
        onApply={load}
        loading={loading}
        groupOptions={GROUPS}
      />

      <div className="flex justify-end mb-3">
        <ExportMenu
          report="Customer Data"
          group_by={filters.group_by}
          columns={columns}
          rows={data?.rows || []}
          totals={data?.totals}
        />
      </div>

      <NarrativeCard
        report="customer-data"
        group_by={filters.group_by}
        rows={data?.rows || []}
        totals={data?.totals || {}}
        filters={filters}
      />

      {data?.chart?.length > 0 && (
        <div className="mb-4">
          <ReportBarChart
            data={data.chart}
            dataKey="value"
            xKey="label"
            title={`Customer Count by ${groupLabel}`}
            color="#9b2c2c"
          />
        </div>
      )}

      <ReportTable
        columns={columns}
        rows={data?.rows || []}
        totals={data ? { group_key: "TOTAL", ...data.totals } : null}
        onCellClick={(c, r) => setDrill({ group_key: r.group_key, metric: c.key })}
      />

      <DrillModal
        open={!!drill}
        onClose={() => setDrill(null)}
        report="Customer Data"
        group_by={filters.group_by}
        group_key={drill?.group_key}
        metric={drill?.metric}
        filters={filters}
      />
    </div>
  );
}
