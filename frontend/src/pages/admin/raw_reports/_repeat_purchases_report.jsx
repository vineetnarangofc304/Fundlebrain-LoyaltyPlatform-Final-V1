import { useState, useEffect } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import {
  FilterBar, NarrativeCard, ExportMenu, ReportTable,
  DrillModal, fmtNum, fmtINR,
} from "./_shared";

const GROUPS = ["location", "city", "state", "zone", "month"];

const COLUMNS = [
  { key: "sno", label: "S.No.", align: "left", sortable: false, drillable: false },
  { key: "group_key", label: "Location", sortable: true, drillable: false },
  // Purchase
  { key: "purchase_unique_customers",  label: "Unique Loyalty Customers", align: "right", format: fmtNum, group: "Purchase" },
  { key: "purchase_total_bills",       label: "Total Loyalty Bills",      align: "right", format: fmtNum, group: "Purchase" },
  { key: "purchase_total_purchase",    label: "Total Loyalty Purchase",   align: "right", format: fmtINR, group: "Purchase" },
  // Repeat - Total
  { key: "repeat_total_unique_customers", label: "Unique Customers",      align: "right", format: fmtNum, group: "Repeat · Total" },
  { key: "repeat_total_bills",            label: "Total Bills",           align: "right", format: fmtNum, group: "Repeat · Total" },
  { key: "repeat_total_purchase",         label: "Repeat Loyalty Purchase", align: "right", format: fmtINR, group: "Repeat · Total" },
  // Repeat - Current
  { key: "repeat_current_unique_customers", label: "Unique Customers",    align: "right", format: fmtNum, group: "Repeat · Current" },
  { key: "repeat_current_bills",            label: "Total Bills",         align: "right", format: fmtNum, group: "Repeat · Current" },
  { key: "repeat_current_purchase",         label: "Repeat Loyalty Purchase", align: "right", format: fmtINR, group: "Repeat · Current" },
  // Repeat - Earlier
  { key: "repeat_earlier_unique_customers", label: "Unique Customers",    align: "right", format: fmtNum, group: "Repeat · Earlier" },
  { key: "repeat_earlier_bills",            label: "Total Bills",         align: "right", format: fmtNum, group: "Repeat · Earlier" },
  { key: "repeat_earlier_purchase",         label: "Repeat Loyalty Purchase", align: "right", format: fmtINR, group: "Repeat · Earlier" },
];

export default function RepeatPurchasesReport() {
  const [filters, setFilters] = useState({ start_date: "", end_date: "", group_by: "location" });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [drill, setDrill] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.post("/raw-reports/repeat-purchases", filters);
      setData(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Load failed");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  // Add S.No.
  const rows = (data?.rows || []).map((r, i) => ({ sno: i + 1, ...r }));

  // Build multi-header — 3 grouped clusters above the leaf columns
  const multiHeader = (
    <>
      <tr className="bg-neutral-100 text-neutral-800">
        <th rowSpan={3} className="px-3 py-2 text-left text-[10px] uppercase tracking-widest border-r border-neutral-200">S.No.</th>
        <th rowSpan={3} className="px-3 py-2 text-left text-[10px] uppercase tracking-widest border-r border-neutral-200">{filters.group_by[0].toUpperCase() + filters.group_by.slice(1)}</th>
        <th colSpan={3} className="px-3 py-2 text-center text-[10px] uppercase tracking-widest border-r border-neutral-200">Purchase</th>
        <th colSpan={9} className="px-3 py-2 text-center text-[10px] uppercase tracking-widest">Repeat Purchase</th>
      </tr>
      <tr className="bg-neutral-50 text-neutral-700">
        <th rowSpan={2} className="px-3 py-1 text-right text-[10px] uppercase tracking-widest border-r border-neutral-200">Unique Loyalty Customers</th>
        <th rowSpan={2} className="px-3 py-1 text-right text-[10px] uppercase tracking-widest border-r border-neutral-200">Total Loyalty Bills</th>
        <th rowSpan={2} className="px-3 py-1 text-right text-[10px] uppercase tracking-widest border-r border-neutral-200">Total Loyalty Purchase</th>
        <th colSpan={3} className="px-3 py-1 text-center text-[10px] uppercase tracking-widest border-r border-neutral-200">Total</th>
        <th colSpan={3} className="px-3 py-1 text-center text-[10px] uppercase tracking-widest border-r border-neutral-200">Current ({data?.current_window_days || 90}d)</th>
        <th colSpan={3} className="px-3 py-1 text-center text-[10px] uppercase tracking-widest">Earlier</th>
      </tr>
      <tr className="bg-neutral-50 text-neutral-700">
        {["Total", "Current", "Earlier"].map((seg) => (
          [
            <th key={`uc-${seg}`} className="px-3 py-1 text-right text-[10px] uppercase tracking-widest">Unique Customers</th>,
            <th key={`tb-${seg}`} className="px-3 py-1 text-right text-[10px] uppercase tracking-widest">Total Bills</th>,
            <th key={`rp-${seg}`} className="px-3 py-1 text-right text-[10px] uppercase tracking-widest border-r border-neutral-200 last:border-r-0">Repeat Loyalty Purchase</th>,
          ]
        ))}
      </tr>
    </>
  );

  return (
    <div>
      <FilterBar value={filters} onChange={setFilters} onApply={load} loading={loading} groupOptions={GROUPS} />

      <div className="flex justify-end mb-3">
        <ExportMenu report="Repeat Purchases" group_by={filters.group_by}
                     columns={COLUMNS} rows={rows} totals={data?.totals} />
      </div>

      <NarrativeCard report="repeat-purchases" group_by={filters.group_by}
                       rows={rows} totals={data?.totals || {}} filters={filters} />

      <ReportTable
        columns={COLUMNS}
        rows={rows}
        totals={data ? { sno: "", group_key: "TOTAL", ...data.totals } : null}
        multiHeader={multiHeader}
        onCellClick={(c, r) => setDrill({ group_key: r.group_key, metric: c.key })}
      />

      <DrillModal open={!!drill} onClose={() => setDrill(null)}
                    report="Repeat Purchases" group_by={filters.group_by}
                    group_key={drill?.group_key} metric={drill?.metric} filters={filters} />
    </div>
  );
}
