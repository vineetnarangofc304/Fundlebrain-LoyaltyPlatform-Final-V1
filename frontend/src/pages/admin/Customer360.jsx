import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import { PageHeader } from "./_shared";
import { fmtMoney2, fmtNum, fmtDate, tierClass } from "@/lib/format";
import { Search, Download, ChevronLeft, ChevronRight } from "lucide-react";

const PAGE_SIZE = 100;

export default function Customer360() {
  const [searchParams] = useSearchParams();
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState({ tier: searchParams.get("tier") || "", churn_risk: searchParams.get("churn_risk") || "" });
  const [data, setData] = useState({ total: 0, items: [] });
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);

  const load = async (p = 1) => {
    setLoading(true);
    try {
      const r = await api.get("/customers", { params: { q, ...filter, limit: PAGE_SIZE, skip: (p - 1) * PAGE_SIZE } });
      setData(r.data);
      setPage(p);
    } finally {
      setLoading(false);
    }
  };
  // Reset to page 1 whenever a filter changes
  useEffect(() => { load(1); /* eslint-disable-next-line */ }, [filter]);

  // total can be -1 when a heavy name-search count times out server-side
  const totalKnown = (data.total ?? -1) >= 0;
  const totalPages = totalKnown ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : null;
  const startIdx = data.items.length ? (page - 1) * PAGE_SIZE + 1 : 0;
  const endIdx = (page - 1) * PAGE_SIZE + data.items.length;
  const canPrev = page > 1;
  const canNext = totalKnown ? page < totalPages : data.items.length === PAGE_SIZE;

  const exportCsv = () => {
    const header = ["Location", "Loc Code", "Mobile", "Name", "Total Bills", "Total Purchase", "Total Visits", "Last Purchase", "Total Earn", "Total Burn", "Points Balance", "Email", "Birthday", "Anniversary", "Tier", "Churn"];
    const lines = [header.join(",")];
    for (const c of data.items) {
      const row = [
        (c.city || "").replace(/,/g, " "),
        (c.home_store_code || "—").replace(/,/g, " "),
        c.mobile || "",
        (c.name || "").replace(/,/g, " "),
        c.visit_count || 0,
        c.lifetime_spend || 0,
        c.visit_count || 0,
        c.last_visit_at ? c.last_visit_at.slice(0, 10) : "",
        c.lifetime_points_earned || 0,
        c.lifetime_points_redeemed || 0,
        c.points_balance || 0,
        (c.email || "").replace(/,/g, " "),
        c.birthday || "",
        c.anniversary || "",
        c.tier || "",
        c.churn_risk || "",
      ];
      lines.push(row.join(","));
    }
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `customer-data-page${page}-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <div data-testid="customer-360-page">
      <PageHeader
        title="Raw Customer Data"
        subtitle="DEEP CUSTOMER INTELLIGENCE · ALL FIELDS"
        actions={
          <button className="k-btn k-btn-outline k-btn-sm" onClick={exportCsv} data-testid="cust-export-csv">
            <Download className="w-3.5 h-3.5" /> Export page CSV
          </button>
        }
      />
      <div className="p-8">
        <div className="flex flex-wrap gap-3 mb-5">
          <div className="relative flex-1 max-w-md">
            <Search className="w-4 h-4 absolute left-3 top-3 text-neutral-400" />
            <input className="k-input !pl-9" placeholder="Search by mobile, email or name" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load(1)} data-testid="customer-search-input" />
          </div>
          <select className="k-input !w-auto" value={filter.tier} onChange={(e) => setFilter({ ...filter, tier: e.target.value })} data-testid="filter-tier">
            <option value="">All tiers</option>
            <option value="silver">Silver</option>
            <option value="gold">Gold</option>
            <option value="platinum">Platinum</option>
            <option value="diamond">Diamond</option>
          </select>
          <select className="k-input !w-auto" value={filter.churn_risk} onChange={(e) => setFilter({ ...filter, churn_risk: e.target.value })} data-testid="filter-churn">
            <option value="">All churn</option>
            <option value="low">Low risk</option>
            <option value="medium">Medium risk</option>
            <option value="high">High risk</option>
          </select>
          <button className="k-btn" onClick={() => load(1)} data-testid="customer-search-btn">Search</button>
        </div>

        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <div className="text-xs text-neutral-500" data-testid="customer-count-summary">
            Showing {fmtNum(startIdx)}–{fmtNum(endIdx)}{totalKnown ? <> of {fmtNum(data.total)} customers</> : <> customers</>}
            {loading && <span className="ml-2 text-amber-700">loading…</span>}
          </div>
          <Pagination page={page} totalPages={totalPages} canPrev={canPrev} canNext={canNext} loading={loading} onPage={load} />
        </div>

        <div className="bg-white border border-black/10 overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Location</th>
                <th>Loc Code</th>
                <th>Mobile</th>
                <th>Name</th>
                <th className="text-right">Total Bills</th>
                <th className="text-right">Total Purchase</th>
                <th className="text-right">Total Visits</th>
                <th>Last Purchase</th>
                <th className="text-right">Total Earn</th>
                <th className="text-right">Total Burn</th>
                <th className="text-right">Points Balance</th>
                <th>Email</th>
                <th>Birthday</th>
                <th>Anniversary</th>
                <th>Tier</th>
                <th>Churn</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((c) => (
                <tr key={c.id} data-testid={`customer-row-${c.id}`}>
                  <td className="whitespace-nowrap">{c.city || "—"}</td>
                  <td className="font-mono text-xs text-neutral-600">{c.home_store_code || "—"}</td>
                  <td className="font-mono text-xs">{c.mobile}</td>
                  <td className="font-medium">{c.name || "—"}</td>
                  <td className="text-right font-mono">{fmtNum(c.visit_count)}</td>
                  <td className="text-right font-mono">{fmtMoney2(c.lifetime_spend)}</td>
                  <td className="text-right font-mono">{fmtNum(c.visit_count)}</td>
                  <td className="text-xs whitespace-nowrap">{fmtDate(c.last_visit_at)}</td>
                  <td className="text-right font-mono text-emerald-700">{fmtNum(c.lifetime_points_earned)}</td>
                  <td className="text-right font-mono text-rose-700">{fmtNum(c.lifetime_points_redeemed)}</td>
                  <td className="text-right font-mono font-semibold text-indigo-800" data-testid={`cust-points-balance-${c.id}`}>{fmtNum(c.points_balance)}</td>
                  <td className="text-xs whitespace-nowrap truncate max-w-[160px]" title={c.email}>{c.email || "—"}</td>
                  <td className="text-xs whitespace-nowrap">{c.birthday || "—"}</td>
                  <td className="text-xs whitespace-nowrap">{c.anniversary || "—"}</td>
                  <td><span className={tierClass(c.tier)}>{c.tier?.toUpperCase()}</span></td>
                  <td><span className={`pill pill-${c.churn_risk === "high" ? "danger" : c.churn_risk === "medium" ? "warning" : "success"}`}>{c.churn_risk || "—"}</span></td>
                  <td><Link to={`/admin/customers/${c.id}`} className="text-xs kazo-text-burgundy font-medium hover:underline whitespace-nowrap">View →</Link></td>
                </tr>
              ))}
              {data.items.length === 0 && !loading && (
                <tr><td colSpan={17} className="text-center py-10 text-neutral-500">No customers found</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Bottom pagination */}
        <div className="flex items-center justify-between mt-3 flex-wrap gap-2">
          <div className="text-xs text-neutral-500">
            Showing {fmtNum(startIdx)}–{fmtNum(endIdx)}{totalKnown ? <> of {fmtNum(data.total)} customers</> : null}
          </div>
          <Pagination page={page} totalPages={totalPages} canPrev={canPrev} canNext={canNext} loading={loading} onPage={load} />
        </div>
      </div>
    </div>
  );
}

function Pagination({ page, totalPages, canPrev, canNext, loading, onPage }) {
  return (
    <div className="flex items-center gap-2" data-testid="customer-pagination">
      <button
        className="k-btn k-btn-outline k-btn-sm disabled:opacity-40"
        disabled={!canPrev || loading}
        onClick={() => onPage(page - 1)}
        data-testid="page-prev"
      >
        <ChevronLeft className="w-3.5 h-3.5" /> Prev
      </button>
      <span className="text-xs text-neutral-600 font-mono px-1" data-testid="page-indicator">
        Page {fmtNum(page)}{totalPages ? <> / {fmtNum(totalPages)}</> : null}
      </span>
      <button
        className="k-btn k-btn-outline k-btn-sm disabled:opacity-40"
        disabled={!canNext || loading}
        onClick={() => onPage(page + 1)}
        data-testid="page-next"
      >
        Next <ChevronRight className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
