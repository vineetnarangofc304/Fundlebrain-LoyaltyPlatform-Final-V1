import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import { PageHeader } from "./_shared";
import { fmtINR, fmtNum, fmtDate, tierClass } from "@/lib/format";
import { Search } from "lucide-react";

export default function Customer360() {
  const [searchParams] = useSearchParams();
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState({ tier: searchParams.get("tier") || "", churn_risk: searchParams.get("churn_risk") || "" });
  const [data, setData] = useState({ total: 0, items: [] });
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    const r = await api.get("/customers", { params: { q, ...filter, limit: 100 } });
    setData(r.data);
    setLoading(false);
  };
  useEffect(() => { load(); }, [filter]);

  return (
    <div data-testid="customer-360-page">
      <PageHeader title="Customer 360" subtitle="DEEP CUSTOMER INTELLIGENCE" />
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

        <div className="text-xs text-neutral-500 mb-3">Showing {data.items.length} of {fmtNum(data.total)}</div>

        <div className="bg-white border border-black/10 overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Customer</th>
                <th>Mobile</th>
                <th>City</th>
                <th>Tier</th>
                <th className="text-right">Lifetime Spend</th>
                <th className="text-right">Points</th>
                <th className="text-right">Visits</th>
                <th>Last visit</th>
                <th>Churn</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((c) => (
                <tr key={c.id} data-testid={`customer-row-${c.id}`}>
                  <td className="font-medium">{c.name || "—"}</td>
                  <td className="font-mono text-xs">{c.mobile}</td>
                  <td>{c.city}</td>
                  <td><span className={tierClass(c.tier)}>{c.tier?.toUpperCase()}</span></td>
                  <td className="text-right font-mono">{fmtINR(c.lifetime_spend)}</td>
                  <td className="text-right font-mono">{fmtNum(c.points_balance)}</td>
                  <td className="text-right font-mono">{c.visit_count}</td>
                  <td className="text-xs">{fmtDate(c.last_visit_at)}</td>
                  <td><span className={`pill pill-${c.churn_risk === "high" ? "danger" : c.churn_risk === "medium" ? "warning" : "success"}`}>{c.churn_risk}</span></td>
                  <td><Link to={`/admin/customers/${c.id}`} className="text-xs kazo-text-burgundy font-medium hover:underline">View →</Link></td>
                </tr>
              ))}
              {data.items.length === 0 && !loading && (
                <tr><td colSpan={10} className="text-center py-10 text-neutral-500">No customers found</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
