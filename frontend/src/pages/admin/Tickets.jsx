import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { PageHeader, StatusPill } from "./_shared";
import { fmtDateTime } from "@/lib/format";
import { toast } from "sonner";
import { ExternalLink } from "lucide-react";

export default function TicketsPage() {
  const [items, setItems] = useState([]);
  const [filter, setFilter] = useState({ status: "" });

  const load = async () => {
    const r = await api.get("/tickets", { params: filter });
    setItems(r.data);
  };
  useEffect(() => { load(); }, [filter]);

  const setStatus = async (id, status) => {
    await api.patch(`/tickets/${id}`, { status });
    toast.success(`Ticket ${status}`);
    load();
  };

  return (
    <div data-testid="tickets-page">
      <PageHeader title="Support Tickets" subtitle="CUSTOMER ISSUES" />
      <div className="p-8">
        <div className="flex gap-2 mb-4 flex-wrap">
          {["", "open", "in_progress", "escalated", "resolved", "closed"].map((s) => (
            <button key={s} className={`pill ${filter.status === s ? "kazo-bg-burgundy text-white" : "pill-neutral"}`} onClick={() => setFilter({ status: s })} data-testid={`tickets-filter-${s || "all"}`}>{s || "All"}</button>
          ))}
        </div>
        <div className="bg-white border border-black/10 overflow-x-auto">
          <table className="data-table">
            <thead><tr><th>Subject</th><th>Customer</th><th>Category</th><th>Priority</th><th>Status</th><th>Created</th><th></th></tr></thead>
            <tbody>
              {items.map((t) => (
                <tr key={t.id}>
                  <td>
                    <Link to={`/admin/tickets/${t.id}`} className="font-medium hover:underline kazo-text-burgundy flex items-center gap-1" data-testid={`ticket-link-${t.id}`}>
                      {t.subject} <ExternalLink className="w-3 h-3" />
                    </Link>
                    <div className="text-xs text-neutral-500 line-clamp-1">{t.description}</div>
                  </td>
                  <td className="font-mono text-xs">{t.customer_mobile}</td>
                  <td><span className="pill pill-neutral">{t.category}</span></td>
                  <td><StatusPill status={t.priority} /></td>
                  <td><StatusPill status={t.status} /></td>
                  <td className="text-xs">{fmtDateTime(t.created_at)}</td>
                  <td>
                    <select className="k-input !py-1 !text-xs !w-32" value={t.status} onChange={(e) => setStatus(t.id, e.target.value)} data-testid={`ticket-status-${t.id}`}>
                      <option value="open">open</option><option value="in_progress">in_progress</option><option value="escalated">escalated</option><option value="resolved">resolved</option><option value="closed">closed</option>
                    </select>
                  </td>
                </tr>
              ))}
              {items.length === 0 && <tr><td colSpan={7} className="text-center py-10 text-neutral-500">No tickets</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
