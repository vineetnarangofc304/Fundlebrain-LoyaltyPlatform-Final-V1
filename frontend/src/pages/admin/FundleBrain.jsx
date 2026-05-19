import { useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { PageHeader } from "./_shared";
import { Brain, Send, Loader2, Sparkles, Trash2 } from "lucide-react";
import { toast } from "sonner";

const MODELS = [
  { label: "GPT-5.2 (OpenAI)", value: "gpt-5.2" },
  { label: "Claude Sonnet 4.5", value: "claude-sonnet-4-5" },
  { label: "Gemini 2.5 Pro", value: "gemini-2.5-pro" },
];

export default function FundleBrain() {
  const [sessions, setSessions] = useState([]);
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [model, setModel] = useState("gpt-5.2");
  const [suggested, setSuggested] = useState([]);
  const bottomRef = useRef(null);

  useEffect(() => {
    api.get("/ai/sessions").then((r) => setSessions(r.data));
    api.get("/ai/suggested-prompts").then((r) => setSuggested(r.data));
  }, []);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const openSession = async (id) => {
    setSessionId(id);
    const r = await api.get(`/ai/sessions/${id}`);
    setMessages(r.data.messages);
  };

  const newChat = () => {
    setSessionId(null);
    setMessages([]);
    setInput("");
  };

  const deleteSession = async (id, e) => {
    e.stopPropagation();
    await api.delete(`/ai/sessions/${id}`);
    setSessions(sessions.filter(s => s.id !== id));
    if (sessionId === id) newChat();
  };

  const send = async (text) => {
    const msg = text || input;
    if (!msg.trim() || loading) return;
    setLoading(true);
    setMessages((m) => [...m, { role: "user", content: msg, timestamp: new Date().toISOString() }]);
    setInput("");
    try {
      const r = await api.post("/ai/chat", { session_id: sessionId, message: msg, model });
      setMessages((m) => [...m, { role: "assistant", content: r.data.reply, data: r.data.data_used, timestamp: new Date().toISOString() }]);
      if (!sessionId) {
        setSessionId(r.data.session_id);
        const sr = await api.get("/ai/sessions");
        setSessions(sr.data);
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "AI error");
      setMessages((m) => [...m, { role: "assistant", content: "Sorry, I encountered an error. Please try again.", timestamp: new Date().toISOString() }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div data-testid="fundle-brain-page">
      <PageHeader
        title="Fundle Brain"
        subtitle="AI ANALYTICS · QUERIES REAL DATA"
        actions={
          <>
            <select className="k-input !w-auto !py-1.5" value={model} onChange={(e) => setModel(e.target.value)} data-testid="model-selector">
              {MODELS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
            <button className="k-btn k-btn-outline k-btn-sm" onClick={newChat} data-testid="new-chat-btn">New chat</button>
          </>
        }
      />
      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-0 h-[calc(100vh-100px)]">
        {/* Session list */}
        <aside className="border-r border-black/10 bg-white p-3 overflow-y-auto">
          <div className="text-[11px] uppercase tracking-widest text-neutral-500 mb-3 px-2">HISTORY</div>
          {sessions.length === 0 && <div className="text-xs text-neutral-500 px-2">No conversations yet</div>}
          {sessions.map((s) => (
            <button key={s.id} onClick={() => openSession(s.id)} className={`w-full text-left p-3 text-sm border-l-2 mb-1 hover:bg-neutral-50 ${sessionId === s.id ? "border-l-[var(--kazo-burgundy)] bg-neutral-50" : "border-l-transparent"}`} data-testid={`session-${s.id}`}>
              <div className="flex justify-between items-start">
                <div className="line-clamp-1 flex-1 pr-2">{s.title}</div>
                <Trash2 className="w-3 h-3 text-neutral-400 hover:text-red-500" onClick={(e) => deleteSession(s.id, e)} />
              </div>
            </button>
          ))}
        </aside>

        {/* Chat area */}
        <div className="flex flex-col bg-[#FAFAF8]">
          <div className="flex-1 overflow-y-auto p-6 lg:p-8">
            {messages.length === 0 && (
              <div className="max-w-2xl mx-auto pt-12 fade-up">
                <Brain className="w-12 h-12 kazo-text-burgundy mb-4" />
                <h2 className="editorial-headline text-4xl mb-2">Fundle Brain</h2>
                <p className="text-neutral-600 mb-8 max-w-md">Ask anything about your loyalty, customers, sales, or campaigns. I query your live Kazo database — no hallucinations.</p>
                <div className="text-xs uppercase tracking-widest text-neutral-500 mb-3">SUGGESTED QUESTIONS</div>
                <div className="grid gap-2">
                  {suggested.map((s, i) => (
                    <button key={i} className="text-left p-3 bg-white border border-black/10 hover:border-[var(--kazo-burgundy)] text-sm" onClick={() => send(s)} data-testid={`suggested-${i}`}>
                      <Sparkles className="w-3.5 h-3.5 kazo-text-champagne inline mr-2" /> {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div className="max-w-3xl mx-auto space-y-5">
              {messages.map((m, i) => (
                <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"} fade-up`}>
                  <div className={`max-w-2xl ${m.role === "user" ? "kazo-bg-black text-white" : "bg-white border border-black/10"} p-4 leading-relaxed text-sm whitespace-pre-wrap`}>
                    {m.role === "assistant" && <div className="text-[10px] uppercase tracking-widest kazo-text-champagne mb-2 flex items-center gap-1"><Brain className="w-3 h-3" /> FUNDLE BRAIN</div>}
                    {m.content}
                  </div>
                </div>
              ))}
              {loading && (
                <div className="flex justify-start"><div className="bg-white border border-black/10 p-4 text-sm flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Analysing your data…</div></div>
              )}
              <div ref={bottomRef} />
            </div>
          </div>
          <div className="border-t border-black/10 bg-white p-4">
            <div className="max-w-3xl mx-auto flex gap-2">
              <input className="k-input" placeholder="Ask Fundle Brain anything about your data…" value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()} disabled={loading} data-testid="ai-input" />
              <button className="k-btn kazo-bg-burgundy" onClick={() => send()} disabled={loading || !input.trim()} data-testid="ai-send-btn"><Send className="w-4 h-4" /></button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
