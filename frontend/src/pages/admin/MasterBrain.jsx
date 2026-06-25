import { useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { PageHeader } from "./_shared";
import { ShieldAlert, Send, Loader2, Sparkles, Trash2, Wrench, ScrollText, Lock } from "lucide-react";
import { toast } from "sonner";
import MarkdownMessage from "./_markdown_message";

const fmtTime = (iso) => {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-IN", {
      timeZone: "Asia/Kolkata", day: "2-digit", month: "short",
      hour: "2-digit", minute: "2-digit", hour12: true,
    });
  } catch { return iso; }
};

const detailFrom = (m) => {
  if (!m || typeof m !== "object") return "—";
  const bits = [];
  if (m.mobile) bits.push(m.mobile);
  if (m.from || m.to) bits.push(`${m.from || "?"} → ${m.to || "?"}`);
  if (m.delta !== undefined) bits.push(`Δ ${m.delta > 0 ? "+" : ""}${m.delta}`);
  if (m.points !== undefined) bits.push(`${m.points} pts`);
  if (m.balance_before !== undefined) bits.push(`${m.balance_before} → ${m.balance_after}`);
  if (m.customers_affected !== undefined) bits.push(`${m.customers_affected} customers`);
  if (m.updated !== undefined) bits.push(`${m.updated} updated`);
  if (m.points_restored !== undefined) bits.push(`${m.points_restored} restored`);
  return bits.length ? bits.join(" · ") : JSON.stringify(m).slice(0, 80);
};

export default function MasterBrain() {
  const { user } = useAuth();
  const [tab, setTab] = useState("chat");
  const [sessions, setSessions] = useState([]);
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [suggested, setSuggested] = useState([]);
  const [log, setLog] = useState([]);
  const bottomRef = useRef(null);

  const isMaster = !!user?.is_master_admin;

  useEffect(() => {
    if (!isMaster) return;
    api.get("/master-brain/sessions").then((r) => setSessions(r.data)).catch(() => {});
    api.get("/master-brain/suggested-prompts").then((r) => setSuggested(r.data)).catch(() => {});
  }, [isMaster]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const loadLog = async () => {
    try { const r = await api.get("/master-brain/action-log"); setLog(r.data.actions || []); }
    catch { /* ignore */ }
  };
  useEffect(() => { if (tab === "log" && isMaster) loadLog(); }, [tab, isMaster]);

  const openSession = async (id) => {
    setSessionId(id);
    const r = await api.get(`/master-brain/sessions/${id}`);
    setMessages(r.data.messages);
  };
  const newChat = () => { setSessionId(null); setMessages([]); setInput(""); };
  const deleteSession = async (id, e) => {
    e.stopPropagation();
    await api.delete(`/master-brain/sessions/${id}`);
    setSessions(sessions.filter((s) => s.id !== id));
    if (sessionId === id) newChat();
  };

  const send = async (text) => {
    const msg = text || input;
    if (!msg.trim() || loading) return;
    setLoading(true);
    setMessages((m) => [...m, { role: "user", content: msg, timestamp: new Date().toISOString() }]);
    setInput("");
    try {
      const r = await api.post("/master-brain/chat", { session_id: sessionId, message: msg });
      setMessages((m) => [...m, {
        role: "assistant", content: r.data.reply, tool_trace: r.data.tool_trace || [],
        timestamp: new Date().toISOString(),
      }]);
      if (!sessionId) {
        setSessionId(r.data.session_id);
        const sr = await api.get("/master-brain/sessions");
        setSessions(sr.data);
      }
      // a write tool may have run → refresh log if open
      if (tab === "log") loadLog();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Master Brain error");
      setMessages((m) => [...m, { role: "assistant", content: "Sorry, I encountered an error. Please try again.", timestamp: new Date().toISOString() }]);
    } finally {
      setLoading(false);
    }
  };

  if (!isMaster) {
    return (
      <div data-testid="master-brain-denied" className="p-10">
        <PageHeader title="Master Brain" subtitle="MASTER ADMIN ONLY" />
        <div className="max-w-lg mt-8 bg-white border border-red-200 p-6 flex items-start gap-3">
          <Lock className="w-5 h-5 text-red-600 mt-0.5" />
          <div>
            <div className="font-display text-xl mb-1">Master Admin access required</div>
            <p className="text-sm text-neutral-600">Master Brain can take live actions on the database, so it is
            restricted to Master Admins. Ask a Super Admin to grant you <b>Master Admin</b> rights in
            User Management.</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div data-testid="master-brain-page">
      <PageHeader
        title="Master Brain"
        subtitle="ACTION-ENABLED · LIVE DATABASE · FULLY AUDITED"
        actions={
          <div className="flex gap-2">
            <button className={`k-btn k-btn-sm ${tab === "chat" ? "kazo-bg-burgundy" : "k-btn-outline"}`} onClick={() => setTab("chat")} data-testid="mb-tab-chat">Chat</button>
            <button className={`k-btn k-btn-sm ${tab === "log" ? "kazo-bg-burgundy" : "k-btn-outline"}`} onClick={() => setTab("log")} data-testid="mb-tab-log"><ScrollText className="w-4 h-4" /> Action Log</button>
            {tab === "chat" && <button className="k-btn k-btn-outline k-btn-sm" onClick={newChat} data-testid="mb-new-chat">New chat</button>}
          </div>
        }
      />

      {/* Live-action warning banner */}
      <div className="mx-3 mb-2 px-4 py-2 text-[12px] flex items-center gap-2 border-l-4 border-red-500 bg-red-50 text-red-800" data-testid="mb-warning">
        <ShieldAlert className="w-4 h-4 shrink-0" />
        <span>Actions here are <b>live</b>. Master Brain always previews first and requires your confirmation + a reason; every change is logged with your name &amp; timestamp.</span>
      </div>

      {tab === "log" ? (
        <div className="p-4" data-testid="mb-action-log">
          <div className="bg-white border border-black/10 overflow-x-auto">
            <table className="data-table">
              <thead><tr><th>When (IST)</th><th>Who</th><th>Action</th><th>Reason</th><th>Details</th></tr></thead>
              <tbody>
                {log.length === 0 && <tr><td colSpan={5} className="text-center text-neutral-500 py-8">No actions logged yet.</td></tr>}
                {log.map((a) => (
                  <tr key={a.id} data-testid={`mb-log-${a.id}`}>
                    <td className="text-xs whitespace-nowrap">{fmtTime(a.timestamp)}</td>
                    <td className="text-xs">{a.user_name || a.user_email || "—"}</td>
                    <td><span className="pill pill-neutral">{(a.action || "").replace("master_brain.", "")}</span></td>
                    <td className="text-xs max-w-[280px]">{a.reason || "—"}</td>
                    <td className="text-xs font-mono">{detailFrom(a.metadata)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-0 h-[calc(100vh-160px)]">
          <aside className="border-r border-black/10 bg-white p-3 overflow-y-auto">
            <div className="text-[11px] uppercase tracking-widest text-neutral-500 mb-3 px-2">HISTORY</div>
            {sessions.length === 0 && <div className="text-xs text-neutral-500 px-2">No conversations yet</div>}
            {sessions.map((s) => (
              <button key={s.id} onClick={() => openSession(s.id)} className={`w-full text-left p-3 text-sm border-l-2 mb-1 hover:bg-neutral-50 ${sessionId === s.id ? "border-l-red-500 bg-neutral-50" : "border-l-transparent"}`} data-testid={`mb-session-${s.id}`}>
                <div className="flex justify-between items-start">
                  <div className="line-clamp-1 flex-1 pr-2">{s.title}</div>
                  <Trash2 className="w-3 h-3 text-neutral-400 hover:text-red-500" onClick={(e) => deleteSession(s.id, e)} />
                </div>
              </button>
            ))}
          </aside>

          <div className="flex flex-col bg-[#FAFAF8]">
            <div className="flex-1 overflow-y-auto p-6 lg:p-8">
              {messages.length === 0 && (
                <div className="max-w-2xl mx-auto pt-8 fade-up">
                  <ShieldAlert className="w-12 h-12 text-red-600 mb-4" />
                  <h2 className="editorial-headline text-4xl mb-2">Master Brain</h2>
                  <p className="text-neutral-600 mb-8 max-w-md">Everything Fundle Brain does — plus the authority to
                  <b> act</b>: grant/adjust points, fix negative balances, and re-tier customers. I always show you a
                  preview and ask <b>"Shall I go ahead?"</b> before changing anything, and I log every action.</p>
                  <div className="text-xs uppercase tracking-widest text-neutral-500 mb-3">TRY</div>
                  <div className="grid gap-2">
                    {suggested.map((s, i) => (
                      <button key={i} className="text-left p-3 bg-white border border-black/10 hover:border-red-500 text-sm" onClick={() => send(s)} data-testid={`mb-suggested-${i}`}>
                        <Sparkles className="w-3.5 h-3.5 text-red-500 inline mr-2" /> {s}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <div className="max-w-3xl mx-auto space-y-5">
                {messages.map((m, i) => (
                  <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"} fade-up`}>
                    <div className={`max-w-2xl ${m.role === "user" ? "kazo-bg-black text-white whitespace-pre-wrap" : "bg-white border border-black/10"} p-4 leading-relaxed text-sm`}>
                      {m.role === "assistant" && <div className="text-[10px] uppercase tracking-widest text-red-600 mb-2 flex items-center gap-1"><ShieldAlert className="w-3 h-3" /> MASTER BRAIN</div>}
                      {m.tool_trace && m.tool_trace.length > 0 && (
                        <div className="mb-2 -mt-1 flex flex-wrap gap-1.5" data-testid={`mb-tool-trace-${i}`}>
                          {m.tool_trace.map((t, j) => (
                            <span key={j} className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-mono bg-red-50 border border-red-200 text-red-800">
                              <Wrench className="w-2.5 h-2.5" /> {t.tool}
                            </span>
                          ))}
                        </div>
                      )}
                      {m.role === "assistant" ? <MarkdownMessage content={m.content} /> : m.content}
                    </div>
                  </div>
                ))}
                {loading && (
                  <div className="flex justify-start"><div className="bg-white border border-black/10 p-4 text-sm flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Thinking & checking the database…</div></div>
                )}
                <div ref={bottomRef} />
              </div>
            </div>
            <div className="border-t border-black/10 bg-white p-4">
              <div className="max-w-3xl mx-auto flex gap-2">
                <input className="k-input" placeholder="Ask Master Brain to analyse — or take an action…" value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()} disabled={loading} data-testid="mb-input" />
                <button className="k-btn kazo-bg-burgundy" onClick={() => send()} disabled={loading || !input.trim()} data-testid="mb-send-btn"><Send className="w-4 h-4" /></button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
