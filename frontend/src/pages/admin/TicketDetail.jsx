import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import api from "@/lib/api";
import { PageHeader, StatusPill } from "./_shared";
import { fmtDateTime, fmtDate } from "@/lib/format";
import { ArrowLeft, MessageSquarePlus, AlertCircle, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

export default function TicketDetail() {
  const { id } = useParams();
  const [t, setT] = useState(null);
  const [note, setNote] = useState("");
  const [savingNote, setSavingNote] = useState(false);

  const load = async () => {
    const r = await api.get(`/tickets/${id}`);
    setT(r.data);
  };
  useEffect(() => { load(); }, [id]);

  const setStatus = async (status) => {
    try {
      await api.patch(`/tickets/${id}`, { status });
      toast.success(`Marked ${status}`);
      load();
    } catch (e) { toast.error("Failed"); }
  };

  const setPriority = async (priority) => {
    try {
      await api.patch(`/tickets/${id}`, { priority });
      toast.success(`Priority ${priority}`);
      load();
    } catch (e) { toast.error("Failed"); }
  };

  const addNote = async () => {
    if (!note.trim()) return;
    setSavingNote(true);
    try {
      await api.post(`/tickets/${id}/notes`, { content: note });
      toast.success("Note added");
      setNote("");
      load();
    } catch (e) { toast.error("Failed"); } finally { setSavingNote(false); }
  };

  if (!t) return <div className="p-10 text-neutral-500">Loading ticket…</div>;

  return (
    <div data-testid="ticket-detail-page">
      <PageHeader
        title={t.subject}
        subtitle={`TICKET · ${t.id?.slice(0, 8)}`}
        actions={<Link to="/admin/tickets" className="k-btn k-btn-outline k-btn-sm"><ArrowLeft className="w-3.5 h-3.5" /> All tickets</Link>}
      />
      <div className="p-8 grid lg:grid-cols-[2fr_1fr] gap-6">
        <div className="space-y-6">
          <div className="bg-white border border-black/10 p-6">
            <div className="flex items-center gap-2 mb-4">
              <StatusPill status={t.status} />
              <StatusPill status={t.priority} />
              <span className="pill pill-neutral">{t.category}</span>
            </div>
            <h2 className="font-display text-3xl mb-3">{t.subject}</h2>
            <p className="text-neutral-700 whitespace-pre-wrap">{t.description}</p>
            <div className="text-xs text-neutral-500 mt-6 pt-4 border-t border-black/5 flex flex-wrap gap-4">
              <span>Created: {fmtDateTime(t.created_at)}</span>
              <span>Updated: {fmtDateTime(t.updated_at)}</span>
              {t.resolved_at && <span>Resolved: {fmtDateTime(t.resolved_at)}</span>}
            </div>
          </div>

          <div className="bg-white border border-black/10 p-6">
            <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-3">CONVERSATION · {t.notes?.length || 0} NOTES</div>
            <div className="space-y-3 max-h-[400px] overflow-y-auto mb-4">
              {(t.notes || []).map((n) => (
                <div key={n.id} className="border-l-2 border-l-[var(--kazo-burgundy)] bg-neutral-50 px-4 py-3" data-testid={`note-${n.id}`}>
                  <div className="flex items-center justify-between mb-1">
                    <div className="text-xs font-medium kazo-text-burgundy">{n.author_email}</div>
                    <div className="text-xs text-neutral-500">{fmtDateTime(n.created_at)}</div>
                  </div>
                  <div className="text-sm text-neutral-700 whitespace-pre-wrap">{n.content}</div>
                </div>
              ))}
              {(!t.notes || t.notes.length === 0) && <div className="text-sm text-neutral-500">No internal notes yet</div>}
            </div>
            <div className="flex gap-2">
              <textarea className="k-input flex-1" rows={2} placeholder="Add an internal note (visible to staff only)…" value={note} onChange={(e) => setNote(e.target.value)} data-testid="ticket-note-input" />
              <button className="k-btn kazo-bg-burgundy" onClick={addNote} disabled={savingNote || !note.trim()} data-testid="ticket-add-note"><MessageSquarePlus className="w-4 h-4" /></button>
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="bg-white border border-black/10 p-5">
            <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-3">CUSTOMER</div>
            <div className="font-mono text-sm">{t.customer_mobile}</div>
            {t.customer_id && <Link to={`/admin/customers/${t.customer_id}`} className="text-xs kazo-text-burgundy hover:underline mt-2 inline-block">Open customer 360 →</Link>}
          </div>

          <div className="bg-white border border-black/10 p-5">
            <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-3">CHANGE STATUS</div>
            <div className="grid grid-cols-2 gap-2">
              {["open", "in_progress", "escalated", "resolved", "closed"].map((s) => (
                <button key={s} className={`pill ${t.status === s ? "kazo-bg-burgundy text-white" : "pill-neutral"} text-center`} onClick={() => setStatus(s)} data-testid={`set-status-${s}`}>{s.replace(/_/g, " ")}</button>
              ))}
            </div>
          </div>

          <div className="bg-white border border-black/10 p-5">
            <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-3">CHANGE PRIORITY</div>
            <div className="grid grid-cols-3 gap-2">
              {["low", "medium", "high"].map((p) => (
                <button key={p} className={`pill ${t.priority === p ? "kazo-bg-burgundy text-white" : "pill-neutral"} text-center`} onClick={() => setPriority(p)} data-testid={`set-priority-${p}`}>{p}</button>
              ))}
            </div>
          </div>

          <div className="bg-white border border-black/10 p-5">
            <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-3">QUICK ACTIONS</div>
            <button className="k-btn k-btn-outline k-btn-sm w-full justify-center mb-2" onClick={() => setStatus("resolved")} data-testid="quick-resolve"><CheckCircle2 className="w-3.5 h-3.5" /> Mark Resolved</button>
            <button className="k-btn k-btn-outline k-btn-sm w-full justify-center" onClick={() => setStatus("escalated")} data-testid="quick-escalate"><AlertCircle className="w-3.5 h-3.5" /> Escalate</button>
          </div>
        </div>
      </div>
    </div>
  );
}
