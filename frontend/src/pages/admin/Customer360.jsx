import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import { PageHeader } from "./_shared";
import { fmtINR, fmtNum, fmtDate, tierClass } from "@/lib/format";
import { Search, Download } from "lucide-react";

const PAGE_SIZE = 100;

export default function Customer360() {
  const [searchParams] = useSearchParams();
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState({ tier: searchParams.get("tier") || "", churn_risk: searchParams.get("churn_risk") || "" });
  const [data, setData] = useState({ total: 0, items: [] });
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get("/customers", { params: { q, ...filter, limit: PAGE_SIZE } });
      setData(r.data);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [filter]);

  const exportCsv = () => {
    const header = ["Location","Loc Code","Mobile","Name","Total Bills","Total Purchase","Total Visits","Last Purchase","Total Earn","Total Burn","Email","Birthday","Anniversary","Tier","Points Balance","Churn"];
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
        c.last_visit_at ? c.last_visit_at.slice(0,10) : "",
        c.lifetime_points_earned || 0,
        c.lifetime_points_redeemed || 0,
        (c.email || "").replace(/,/g, " "),
        c.birthday || "",
        c.anniversary || "",
        c.tier || "",
        c.points_balance || 0,
        c.churn_risk || "",
      ];
      lines.push(row.join(","));
    }
    const blob = new Blob([lines.join("\n")], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `customer-data-${new Date().toISOString().slice(0,10)}.csv`;
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
            <Download className="w-3.5 h-3.5" /> Export CSV
          </button>
        }
      />
      <div className="p-8">
        <div className="flex flex-wrap gap-3 mb-5">
          <div className="relative flex-1 max-w-md">
            <Search className="w-4 h-4 absolute left-3 top-3 text-neutral-400" />
            <input className="k-input !pl-9" placeholder="Search by mobile, email or name" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()} data-testid="customer-search-input" />
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
          <button className="k-btn" onClick={load}>Search</button>
        </div>

        <div className="text-xs text-neutral-500 mb-3">
          Showing {data.items.length} of {fmtNum(data.total)} customers
          {loading && <span className="ml-2 text-amber-700">loading…</span>}
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
                <th>Email</th>
                <th>Birthday</th>
                <th>Anniversary</th>
                <th>Tier</th>
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
                  <td className="text-right font-mono">{fmtINR(c.lifetime_spend)}</td>
                  <td className="text-right font-mono">{fmtNum(c.visit_count)}</td>
                  <td className="text-xs whitespace-nowrap">{fmtDate(c.last_visit_at)}</td>
                  <td className="text-right font-mono text-emerald-700">{fmtNum(c.lifetime_points_earned)}</td>
                  <td className="text-right font-mono text-rose-700">{fmtNum(c.lifetime_points_redeemed)}</td>
                  <td className="text-xs whitespace-nowrap truncate max-w-[160px]" title={c.email}>{c.email || "—"}</td>
                  <td className="text-xs whitespace-nowrap">{c.birthday || "—"}</td>
                  <td className="text-xs whitespace-nowrap">{c.anniversary || "—"}</td>
                  <td><span className={tierClass(c.tier)}>{c.tier?.toUpperCase()}</span></td>
                  <td><Link to={`/admin/customers/${c.id}`} className="text-xs kazo-text-burgundy font-medium hover:underline whitespace-nowrap">View →</Link></td>
                </tr>
              ))}
              {data.items.length === 0 && !loading && (
                <tr><td colSpan={15} className="text-center py-10 text-neutral-500">No customers found</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
