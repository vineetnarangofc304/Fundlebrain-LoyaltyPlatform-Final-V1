import { useState, useEffect, useRef } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import {
  FilterBar, NarrativeCard, ExportMenu, ReportTable, ColumnPicker,
  DrillModal, fmtNum, fmtINR,
} from "./_shared";

const GROUPS = ["location", "city", "state", "zone", "month"];

const ALL_COLUMNS = [
  { key: "sno",                              label: "S.No.",                       sortable: false, drillable: false },
  { key: "group_key",                        label: "Location",                    sortable: true, drillable: false },
  // Purchase
  { key: "purchase_unique_customers",        label: "Unique Loyalty Customers",    align: "right", format: fmtNum, group: "Purchase" },
  { key: "purchase_total_bills",             label: "Total Loyalty Bills",         align: "right", format: fmtNum, group: "Purchase" },
  { key: "purchase_total_purchase",          label: "Total Loyalty Purchase",      align: "right", format: fmtINR, group: "Purchase" },
  // Repeat Total
  { key: "repeat_total_unique_customers",    label: "Repeat · Unique Customers",   align: "right", format: fmtNum, group: "Repeat Total" },
  { key: "repeat_total_bills",               label: "Repeat · Total Bills",        align: "right", format: fmtNum, group: "Repeat Total" },
  { key: "repeat_total_purchase",            label: "Repeat · Total Purchase",     align: "right", format: fmtINR, group: "Repeat Total" },
  // Repeat Current
  { key: "repeat_current_unique_customers",  label: "Current · Unique Customers",  align: "right", format: fmtNum, group: "Current 90d" },
  { key: "repeat_current_bills",             label: "Current · Total Bills",       align: "right", format: fmtNum, group: "Current 90d" },
  { key: "repeat_current_purchase",          label: "Current · Repeat Purchase",   align: "right", format: fmtINR, group: "Current 90d" },
  // Repeat Earlier
  { key: "repeat_earlier_unique_customers",  label: "Earlier · Unique Customers",  align: "right", format: fmtNum, group: "Earlier" },
  { key: "repeat_earlier_bills",             label: "Earlier · Total Bills",       align: "right", format: fmtNum, group: "Earlier" },
  { key: "repeat_earlier_purchase",          label: "Earlier · Repeat Purchase",   align: "right", format: fmtINR, group: "Earlier" },
];

const DEFAULT_VISIBLE = ALL_COLUMNS.map((c) => c.key);

export default function RepeatPurchasesReport() {
  const [filters, setFilters] = useState({ start_date: "", end_date: "", group_by: "location" });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [drill, setDrill] = useState(null);
  const [visibleKeys, setVisibleKeys] = useState(DEFAULT_VISIBLE);
  const [showMultiHeader, setShowMultiHeader] = useState(true);
  const debounceRef = useRef(null);

  const load = async (override = filters) => {
    setLoading(true);
    setData(null);
    try {
      const r = await api.post("/raw-reports/repeat-purchases", override);
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
  const groupLabel = filters.group_by[0].toUpperCase() + filters.group_by.slice(1);
  const columns = ALL_COLUMNS
    .filter((c) => visibleKeys.includes(c.key))
    .map((c) => c.key === "group_key" ? { ...c, label: groupLabel } : c);

  // Build dynamic multi-header from visible columns
  const purchaseCols = columns.filter((c) => c.group === "Purchase");
  const totalCols = columns.filter((c) => c.group === "Repeat Total");
  const currentCols = columns.filter((c) => c.group === "Current 90d");
  const earlierCols = columns.filter((c) => c.group === "Earlier");
  const fixedCols = columns.filter((c) => !c.group);
  const repeatColCount = totalCols.length + currentCols.length + earlierCols.length;

  const multiHeader = showMultiHeader && repeatColCount > 0 ? (
    <>
      <tr className="bg-neutral-100 text-neutral-800">
        {fixedCols.map((c) => (
          <th key={c.key} rowSpan={3} className="px-3 py-2 text-left text-[10px] uppercase tracking-widest border-r border-neutral-200">
            {c.label}
          </th>
        ))}
        {purchaseCols.length > 0 && (
          <th colSpan={purchaseCols.length} className="px-3 py-2 text-center text-[10px] uppercase tracking-widest border-r border-neutral-200">Purchase</th>
        )}
        {repeatColCount > 0 && (
          <th colSpan={repeatColCount} className="px-3 py-2 text-center text-[10px] uppercase tracking-widest">Repeat Purchase</th>
        )}
      </tr>
      <tr className="bg-neutral-50 text-neutral-700">
        {purchaseCols.map((c) => (
          <th key={c.key} rowSpan={2} className="px-3 py-1 text-right text-[10px] uppercase tracking-widest border-r border-neutral-200">
            {c.label.replace(/^Purchase · /, "")}
          </th>
        ))}
        {totalCols.length > 0 && (
          <th colSpan={totalCols.length} className="px-3 py-1 text-center text-[10px] uppercase tracking-widest border-r border-neutral-200">Total</th>
        )}
        {currentCols.length > 0 && (
          <th colSpan={currentCols.length} className="px-3 py-1 text-center text-[10px] uppercase tracking-widest border-r border-neutral-200">Current ({data?.current_window_days || 90}d)</th>
        )}
        {earlierCols.length > 0 && (
          <th colSpan={earlierCols.length} className="px-3 py-1 text-center text-[10px] uppercase tracking-widest">Earlier</th>
        )}
      </tr>
      <tr className="bg-neutral-50 text-neutral-700">
        {totalCols.map((c) => (
          <th key={c.key} className="px-3 py-1 text-right text-[10px] uppercase tracking-widest">
            {c.label.replace(/^Repeat · /, "").replace(/^Total · /, "")}
          </th>
        ))}
        {currentCols.map((c) => (
          <th key={c.key} className="px-3 py-1 text-right text-[10px] uppercase tracking-widest">
            {c.label.replace(/^Current · /, "")}
          </th>
        ))}
        {earlierCols.map((c) => (
          <th key={c.key} className="px-3 py-1 text-right text-[10px] uppercase tracking-widest">
            {c.label.replace(/^Earlier · /, "")}
          </th>
        ))}
      </tr>
    </>
  ) : null;

  return (
    <div>
      <FilterBar value={filters} onChange={onChange} onApply={() => load()} loading={loading} groupOptions={GROUPS} />

      <div className="flex justify-between items-center mb-3 gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <label className="text-xs text-neutral-600 flex items-center gap-1 cursor-pointer">
            <input type="checkbox" checked={showMultiHeader} onChange={(e) => setShowMultiHeader(e.target.checked)} />
            Show grouped header
          </label>
        </div>
        <div className="flex gap-2">
          <ColumnPicker allColumns={ALL_COLUMNS} visibleKeys={visibleKeys}
                          onChange={setVisibleKeys} requiredKeys={["sno", "group_key"]} />
          <ExportMenu report="Repeat Purchases" group_by={filters.group_by}
                       columns={columns} rows={rows} totals={data?.totals} />
        </div>
      </div>

      <ReportTable
        columns={columns}
        rows={rows}
        totals={data ? { sno: "", group_key: "TOTAL", ...data.totals } : null}
        multiHeader={multiHeader}
        onCellClick={(c, r) => setDrill({ group_key: r.group_key, metric: c.key })}
        loading={loading}
      />

      <NarrativeCard report="repeat-purchases" group_by={filters.group_by}
                       rows={rows} totals={data?.totals || {}} filters={filters} />

      <DrillModal open={!!drill} onClose={() => setDrill(null)}
                    report="Repeat Purchases" group_by={filters.group_by}
                    group_key={drill?.group_key} metric={drill?.metric} filters={filters} />
    </div>
  );
}
