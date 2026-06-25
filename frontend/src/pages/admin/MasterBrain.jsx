import { useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { PageHeader } from "./_shared";
import { ShieldAlert, Send, Loader2, Sparkles, Trash2, Wrench, ScrollText, Lock, Paperclip, X, FileText, Image as ImageIcon, Undo2, Megaphone, Database, RefreshCw, Search, ChevronLeft, ChevronRight, ArrowLeft, History, Zap } from "lucide-react";
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
  if (m.points !== undefined && m.delta === undefined) bits.push(`${m.points} pts`);
  if (m.balance_before !== undefined) bits.push(`${m.balance_before} → ${m.balance_after}`);
  if (m.customers_affected !== undefined) bits.push(`${m.customers_affected} customers`);
  if (m.matched !== undefined) bits.push(`${m.matched} matched`);
  if (m.changed !== undefined) bits.push(`${m.changed} changed`);
  if (m.updated !== undefined) bits.push(`${m.updated} updated`);
  if (m.points_restored !== undefined) bits.push(`${m.points_restored} restored`);
  if (m.recipients !== undefined) bits.push(`${m.recipients} recipients`);
  if (m.changes_reversed !== undefined) bits.push(`${m.changes_reversed} reversed`);
  return bits.length ? bits.join(" · ") : JSON.stringify(m).slice(0, 80);
};

const STATUS_PILL = {
  queued: "pill-warning", running: "pill-info", completed: "pill-success",
  cancelled: "pill-neutral", failed: "pill-danger",
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
  const [attachments, setAttachments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  // undo
  const [undoTarget, setUndoTarget] = useState(null);
  const [undoReason, setUndoReason] = useState("");
  const [undoing, setUndoing] = useState(false);

  // campaigns
  const [campaigns, setCampaigns] = useState([]);

  // datasets
  const [datasets, setDatasets] = useState([]);
  const [dsView, setDsView] = useState(null); // selected dataset detail
  const [dsQuery, setDsQuery] = useState("");
  const [dsPage, setDsPage] = useState(1);

  // query log
  const [queryLog, setQueryLog] = useState([]);
  const [qlUsers, setQlUsers] = useState([]);
  const [qlIsGlobal, setQlIsGlobal] = useState(false);
  const [qlUser, setQlUser] = useState("");
  const [qlSearch, setQlSearch] = useState("");

  const isMaster = !!user?.is_master_admin;
  const isQueryAdmin = !!user?.is_master_query_admin;
  const canAccess = isMaster || isQueryAdmin;

  useEffect(() => {
    if (!isMaster) return;
    api.get("/master-brain/sessions").then((r) => setSessions(r.data)).catch(() => {});
    api.get("/master-brain/suggested-prompts").then((r) => setSuggested(r.data)).catch(() => {});
  }, [isMaster]);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  // Auto-grow the multiline chat box (and shrink back after sending clears it)
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [input]);

  const loadLog = async () => {
    try { const r = await api.get("/master-brain/action-log"); setLog(r.data.actions || []); }
    catch { /* ignore */ }
  };
  const loadCampaigns = async () => {
    try { const r = await api.get("/master-brain/campaigns"); setCampaigns(r.data.campaigns || []); }
    catch { /* ignore */ }
  };
  const loadDatasets = async () => {
    try { const r = await api.get("/master-brain/datasets"); setDatasets(r.data.datasets || []); }
    catch { /* ignore */ }
  };
  const loadQueryLog = async () => {
    try {
      const r = await api.get("/master-brain/query-log", { params: { user_email: qlUser, q: qlSearch, days: 30 } });
      setQueryLog(r.data.queries || []);
      setQlIsGlobal(!!r.data.is_global);
      setQlUsers(r.data.users || []);
    } catch { /* ignore */ }
  };
  useEffect(() => { if (tab === "log" && isMaster) loadLog(); }, [tab, isMaster]);
  useEffect(() => { if (tab === "campaigns" && isMaster) loadCampaigns(); }, [tab, isMaster]);
  useEffect(() => { if (tab === "datasets" && isMaster) loadDatasets(); }, [tab, isMaster]);
  useEffect(() => { if (tab === "querylog" && canAccess) loadQueryLog(); }, [tab, canAccess]);
  // A query-only overseer (no write rights) lands straight on the Query Log.
  useEffect(() => { if (!isMaster && isQueryAdmin) setTab("querylog"); }, [isMaster, isQueryAdmin]);

  // auto-refresh campaigns while any is in-flight
  useEffect(() => {
    if (tab !== "campaigns") return;
    const anyLive = campaigns.some((c) => ["queued", "running"].includes(c.status));
    if (!anyLive) return;
    const t = setInterval(loadCampaigns, 4000);
    return () => clearInterval(t);
  }, [tab, campaigns]);

  const openDataset = async (id, q = "", page = 1) => {
    try {
      const r = await api.get(`/master-brain/datasets/${id}`, { params: { q, page, page_size: 50 } });
      setDsView(r.data); setDsQuery(q); setDsPage(page);
    } catch { toast.error("Couldn't open dataset"); }
  };

  const openSession = async (id) => {
    setSessionId(id);
    const r = await api.get(`/master-brain/sessions/${id}`);
    setMessages(r.data.messages);
  };
  const newChat = () => { setSessionId(null); setMessages([]); setInput(""); setAttachments([]); };

  const handleUpload = async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    setUploading(true);
    for (const file of files) {
      try {
        const fd = new FormData();
        fd.append("file", file);
        if (sessionId) fd.append("session_id", sessionId);
        const r = await api.post("/master-brain/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
        setAttachments((a) => [...a, r.data]);
      } catch (err) {
        toast.error(err?.response?.data?.detail || `Couldn't upload ${file.name}`);
      }
    }
    setUploading(false);
    if (fileRef.current) fileRef.current.value = "";
  };

  const removeAttachment = (id) => setAttachments((a) => a.filter((x) => x.id !== id));
  const deleteSession = async (id, e) => {
    e.stopPropagation();
    await api.delete(`/master-brain/sessions/${id}`);
    setSessions(sessions.filter((s) => s.id !== id));
    if (sessionId === id) newChat();
  };

  const confirmUndo = async () => {
    if (!undoTarget) return;
    if (!undoReason.trim()) { toast.error("A reason is required to undo."); return; }
    setUndoing(true);
    try {
      const r = await api.post(`/master-brain/undo/${undoTarget.id}`, { reason: undoReason });
      toast.success(r.data?.message || "Action undone");
      setUndoTarget(null); setUndoReason("");
      loadLog();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Undo failed");
    } finally { setUndoing(false); }
  };

  const cancelCampaign = async (c) => {
    const reason = window.prompt(`Cancel campaign to ${c.recipients_total} recipients? Enter a reason (required):`, "");
    if (reason === null) return;
    if (!reason.trim()) { toast.error("A reason is required to cancel."); return; }
    try {
      const r = await api.post(`/master-brain/campaigns/${c.id}/cancel`, { reason });
      toast.success(r.data?.message || "Cancellation requested");
      loadCampaigns();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Cancel failed");
    }
  };

  const executeSuggestion = (a) => {
    if (loading || !a) return;
    setTab("chat");
    send(`Execute: ${a.label}`, { tool: a.tool, args: a.args || {}, label: a.label });
  };

  const send = async (text, forceAction = null) => {
    const msg = text || input;
    if ((!msg.trim() && attachments.length === 0 && !forceAction) || loading) return;
    const atts = attachments;
    setLoading(true);
    setMessages((m) => [...m, { role: "user", content: msg, attachments: atts, timestamp: new Date().toISOString() }]);
    setInput("");
    setAttachments([]);
    try {
      const r = await api.post("/master-brain/chat", {
        session_id: sessionId, message: msg, attachment_ids: atts.map((a) => a.id),
        force_action: forceAction || undefined,
      });
      setMessages((m) => [...m, {
        role: "assistant", content: r.data.reply, tool_trace: r.data.tool_trace || [],
        suggested_actions: r.data.suggested_actions || [],
        timestamp: new Date().toISOString(),
      }]);
      if (!sessionId) {
        setSessionId(r.data.session_id);
        const sr = await api.get("/master-brain/sessions");
        setSessions(sr.data);
      }
      if (tab === "log") loadLog();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Master Brain error");
      setMessages((m) => [...m, { role: "assistant", content: "Sorry, I encountered an error. Please try again.", timestamp: new Date().toISOString() }]);
    } finally {
      setLoading(false);
    }
  };

  if (!canAccess) {
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

  const TabBtn = ({ id, icon: Icon, children }) => (
    <button className={`k-btn k-btn-sm ${tab === id ? "kazo-bg-burgundy" : "k-btn-outline"}`}
      onClick={() => setTab(id)} data-testid={`mb-tab-${id}`}>
      {Icon && <Icon className="w-4 h-4" />} {children}
    </button>
  );

  return (
    <div data-testid="master-brain-page">
      <PageHeader
        title="Master Brain"
        subtitle="ACTION-ENABLED · LIVE DATABASE · FULLY AUDITED"
        actions={
          <div className="flex gap-2 flex-wrap">
            {isMaster && <TabBtn id="chat">Chat</TabBtn>}
            {isMaster && <TabBtn id="log" icon={ScrollText}>Action Log</TabBtn>}
            {isMaster && <TabBtn id="campaigns" icon={Megaphone}>Campaigns</TabBtn>}
            {isMaster && <TabBtn id="datasets" icon={Database}>Datasets</TabBtn>}
            <TabBtn id="querylog" icon={History}>Query Log</TabBtn>
            {tab === "chat" && <button className="k-btn k-btn-outline k-btn-sm" onClick={newChat} data-testid="mb-new-chat">New chat</button>}
          </div>
        }
      />

      <div className="mx-3 mb-2 px-4 py-2 text-[12px] flex items-center gap-2 border-l-4 border-red-500 bg-red-50 text-red-800" data-testid="mb-warning">
        <ShieldAlert className="w-4 h-4 shrink-0" />
        <span>Actions here are <b>live</b>. Master Brain always previews first and requires your confirmation + a reason; every change is logged with your name &amp; timestamp.</span>
      </div>

      {/* ---------------- ACTION LOG ---------------- */}
      {tab === "log" && (
        <div className="p-4" data-testid="mb-action-log">
          <div className="flex justify-end mb-2">
            <button className="k-btn k-btn-outline k-btn-sm" onClick={loadLog} data-testid="mb-log-refresh"><RefreshCw className="w-4 h-4" /> Refresh</button>
          </div>
          <div className="bg-white border border-black/10 overflow-x-auto">
            <table className="data-table">
              <thead><tr><th>When (IST)</th><th>Who</th><th>Action</th><th>Reason</th><th>Details</th><th>Undo</th></tr></thead>
              <tbody>
                {log.length === 0 && <tr><td colSpan={6} className="text-center text-neutral-500 py-8">No actions logged yet.</td></tr>}
                {log.map((a) => (
                  <tr key={a.id} data-testid={`mb-log-${a.id}`} className={a.undone ? "opacity-60" : ""}>
                    <td className="text-xs whitespace-nowrap">{fmtTime(a.timestamp)}</td>
                    <td className="text-xs">{a.user_name || a.user_email || "—"}</td>
                    <td><span className="pill pill-neutral">{(a.action || "").replace("master_brain.", "")}</span></td>
                    <td className="text-xs max-w-[280px]">{a.reason || "—"}</td>
                    <td className="text-xs font-mono">{detailFrom(a.metadata)}</td>
                    <td className="text-xs whitespace-nowrap">
                      {a.undone ? (
                        <span className="pill pill-neutral" data-testid={`mb-undone-${a.id}`}>Undone</span>
                      ) : a.undoable ? (
                        <button className="k-btn k-btn-outline k-btn-sm" onClick={() => { setUndoTarget(a); setUndoReason(""); }} data-testid={`mb-undo-btn-${a.id}`}>
                          <Undo2 className="w-3.5 h-3.5" /> Undo
                        </button>
                      ) : <span className="text-neutral-400">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ---------------- CAMPAIGNS ---------------- */}
      {tab === "campaigns" && (
        <div className="p-4" data-testid="mb-campaigns">
          <div className="flex justify-between items-center mb-2">
            <p className="text-xs text-neutral-600">Bulk SMS campaigns sent via Karix. Create one by asking Master Brain in <b>Chat</b> (e.g. "Send an SMS to all Gold customers…").</p>
            <button className="k-btn k-btn-outline k-btn-sm" onClick={loadCampaigns} data-testid="mb-campaigns-refresh"><RefreshCw className="w-4 h-4" /> Refresh</button>
          </div>
          <div className="bg-white border border-black/10 overflow-x-auto">
            <table className="data-table">
              <thead><tr><th>When (IST)</th><th>Message / Template</th><th>Audience</th><th>Status</th><th>Sent / Failed / Total</th><th>By</th><th></th></tr></thead>
              <tbody>
                {campaigns.length === 0 && <tr><td colSpan={7} className="text-center text-neutral-500 py-8">No campaigns yet.</td></tr>}
                {campaigns.map((c) => (
                  <tr key={c.id} data-testid={`mb-campaign-${c.id}`}>
                    <td className="text-xs whitespace-nowrap">{fmtTime(c.created_at)}</td>
                    <td className="text-xs max-w-[280px] truncate">{c.template_name || c.message || "—"}</td>
                    <td className="text-xs">{c.audience_label || c.audience_type}</td>
                    <td><span className={`pill ${STATUS_PILL[c.status] || "pill-neutral"}`} data-testid={`mb-campaign-status-${c.id}`}>{c.status}{c.cancel_requested && c.status === "running" ? " (cancelling)" : ""}</span></td>
                    <td className="text-xs font-mono">{c.sent || 0} / {c.failed || 0} / {c.recipients_total || 0}</td>
                    <td className="text-xs">{c.created_by_name || c.created_by || "—"}</td>
                    <td className="text-xs">
                      {["queued", "running"].includes(c.status) && !c.cancel_requested && (
                        <button className="k-btn k-btn-outline k-btn-sm" onClick={() => cancelCampaign(c)} data-testid={`mb-campaign-cancel-${c.id}`}>Cancel</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ---------------- DATASETS ---------------- */}
      {tab === "datasets" && (
        <div className="p-4" data-testid="mb-datasets">
          {!dsView ? (
            <>
              <div className="flex justify-between items-center mb-2">
                <p className="text-xs text-neutral-600">Every report (CSV/Excel/PDF) you upload in Chat is saved here as a searchable dataset.</p>
                <button className="k-btn k-btn-outline k-btn-sm" onClick={loadDatasets} data-testid="mb-datasets-refresh"><RefreshCw className="w-4 h-4" /> Refresh</button>
              </div>
              <div className="bg-white border border-black/10 overflow-x-auto">
                <table className="data-table">
                  <thead><tr><th>Uploaded (IST)</th><th>File</th><th>Type</th><th>Rows</th><th>Mobiles</th><th>Columns</th></tr></thead>
                  <tbody>
                    {datasets.length === 0 && <tr><td colSpan={6} className="text-center text-neutral-500 py-8">No datasets yet. Upload a report in Chat.</td></tr>}
                    {datasets.map((d) => (
                      <tr key={d.id} className="cursor-pointer hover:bg-neutral-50" onClick={() => openDataset(d.id)} data-testid={`mb-dataset-${d.id}`}>
                        <td className="text-xs whitespace-nowrap">{fmtTime(d.created_at)}</td>
                        <td className="text-xs font-medium flex items-center gap-1.5"><FileText className="w-3.5 h-3.5 text-red-600" /> {d.filename}</td>
                        <td className="text-xs uppercase">{d.report_type}</td>
                        <td className="text-xs">{d.row_count ?? "—"}</td>
                        <td className="text-xs">{(d.mobiles || []).length}</td>
                        <td className="text-xs max-w-[260px] truncate">{(d.columns || []).join(", ") || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <div data-testid="mb-dataset-view">
              <div className="flex items-center gap-3 mb-3 flex-wrap">
                <button className="k-btn k-btn-outline k-btn-sm" onClick={() => setDsView(null)} data-testid="mb-dataset-back"><ArrowLeft className="w-4 h-4" /> Back</button>
                <div className="font-display text-lg flex items-center gap-2"><FileText className="w-4 h-4 text-red-600" /> {dsView.filename}</div>
                <span className="text-xs text-neutral-500">{dsView.row_count} rows{dsView.rows_truncated ? ` (first ${dsView.rows_stored} stored)` : ""} · {dsView.mobiles_detected} mobiles</span>
                <div className="ml-auto flex items-center gap-2">
                  <div className="relative">
                    <Search className="w-3.5 h-3.5 text-neutral-400 absolute left-2 top-1/2 -translate-y-1/2" />
                    <input className="k-input pl-7 h-9 text-sm" placeholder="Search rows…" value={dsQuery}
                      onChange={(e) => setDsQuery(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && openDataset(dsView.id, dsQuery, 1)}
                      data-testid="mb-dataset-search" />
                  </div>
                  <button className="k-btn k-btn-outline k-btn-sm" onClick={() => openDataset(dsView.id, dsQuery, 1)} data-testid="mb-dataset-search-btn">Search</button>
                </div>
              </div>
              {dsView.report_type === "pdf" ? (
                <pre className="bg-white border border-black/10 p-4 text-xs whitespace-pre-wrap max-h-[60vh] overflow-auto" data-testid="mb-dataset-pdf-text">{dsView.extracted_text || "No text extracted."}</pre>
              ) : (
                <>
                  <div className="bg-white border border-black/10 overflow-x-auto max-h-[60vh]">
                    <table className="data-table">
                      <thead><tr>{(dsView.columns || []).map((c) => <th key={c}>{c}</th>)}</tr></thead>
                      <tbody>
                        {(dsView.rows || []).length === 0 && <tr><td colSpan={(dsView.columns || []).length || 1} className="text-center text-neutral-500 py-8">No matching rows.</td></tr>}
                        {(dsView.rows || []).map((r, i) => (
                          <tr key={i} data-testid={`mb-dataset-row-${i}`}>
                            {(dsView.columns || []).map((c) => <td key={c} className="text-xs">{r[c]}</td>)}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="flex items-center justify-between mt-2 text-xs">
                    <span>{dsView.total_matched} matched · page {dsView.page}</span>
                    <div className="flex gap-2">
                      <button className="k-btn k-btn-outline k-btn-sm" disabled={dsView.page <= 1} onClick={() => openDataset(dsView.id, dsQuery, dsView.page - 1)} data-testid="mb-dataset-prev"><ChevronLeft className="w-4 h-4" /></button>
                      <button className="k-btn k-btn-outline k-btn-sm" disabled={dsView.page * dsView.page_size >= dsView.total_matched} onClick={() => openDataset(dsView.id, dsQuery, dsView.page + 1)} data-testid="mb-dataset-next"><ChevronRight className="w-4 h-4" /></button>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {/* ---------------- QUERY LOG ---------------- */}
      {tab === "querylog" && (
        <div className="p-4" data-testid="mb-querylog">
          <div className="flex justify-between items-center mb-2 gap-2 flex-wrap">
            <p className="text-xs text-neutral-600" data-testid="mb-ql-scope">
              {qlIsGlobal
                ? "Overseer view — Master Brain queries from ALL users (last 30 days)."
                : "Your Master Brain query history (last 30 days). You only see your own queries."}
            </p>
            <div className="flex items-center gap-2 flex-wrap">
              {qlIsGlobal && (
                <select className="k-input h-9 text-sm" value={qlUser} onChange={(e) => { setQlUser(e.target.value); }} data-testid="mb-ql-user-filter">
                  <option value="">All users</option>
                  {qlUsers.map((u) => <option key={u} value={u}>{u}</option>)}
                </select>
              )}
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-neutral-400 absolute left-2 top-1/2 -translate-y-1/2" />
                <input className="k-input pl-7 h-9 text-sm" placeholder="Search queries…" value={qlSearch}
                  onChange={(e) => setQlSearch(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && loadQueryLog()} data-testid="mb-ql-search" />
              </div>
              <button className="k-btn k-btn-outline k-btn-sm" onClick={loadQueryLog} data-testid="mb-ql-refresh"><RefreshCw className="w-4 h-4" /> Refresh</button>
            </div>
          </div>
          <div className="bg-white border border-black/10 overflow-x-auto">
            <table className="data-table">
              <thead><tr><th>When (IST)</th>{qlIsGlobal && <th>User</th>}<th>Query</th><th>Tools used</th></tr></thead>
              <tbody>
                {queryLog.length === 0 && <tr><td colSpan={qlIsGlobal ? 4 : 3} className="text-center text-neutral-500 py-8">No queries yet.</td></tr>}
                {queryLog.map((row) => (
                  <tr key={row.id} data-testid={`mb-ql-${row.id}`}>
                    <td className="text-xs whitespace-nowrap">{fmtTime(row.created_at)}</td>
                    {qlIsGlobal && <td className="text-xs">{row.user_name || row.user_email}</td>}
                    <td className="text-xs max-w-[460px]">{row.query}{row.attachments?.length ? <span className="text-neutral-400"> · 📎 {row.attachments.length}</span> : null}</td>
                    <td className="text-xs">
                      {(row.tools_used || []).length === 0 ? <span className="text-neutral-400">—</span> :
                        (row.tools_used || []).slice(0, 6).map((t, i) => (
                          <span key={i} className="inline-block px-1.5 py-0.5 mr-1 mb-1 text-[10px] font-mono bg-neutral-100 border border-black/10">{t}</span>
                        ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ---------------- CHAT ---------------- */}
      {tab === "chat" && (
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
                  <b> act</b>: grant/adjust points, fix negative balances, re-tier customers, send bulk SMS campaigns
                  and <b>undo</b> any action. I always show you a preview and ask <b>"Shall I go ahead?"</b> before
                  changing anything, and I log every action.</p>
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
                      {m.attachments && m.attachments.length > 0 && (
                        <div className="mb-2 flex flex-wrap gap-1.5" data-testid={`mb-msg-attach-${i}`}>
                          {m.attachments.map((a) => (
                            <span key={a.id} className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] bg-white/15 border border-white/25 rounded">
                              {a.kind === "image" ? <ImageIcon className="w-2.5 h-2.5" /> : <FileText className="w-2.5 h-2.5" />} {a.filename}
                            </span>
                          ))}
                        </div>
                      )}
                      {m.role === "assistant" ? <MarkdownMessage content={m.content} /> : m.content}
                      {m.role === "assistant" && m.suggested_actions && m.suggested_actions.length > 0 && (
                        <div className="mt-3 border-t border-black/10 pt-3 space-y-2" data-testid={`mb-suggestions-${i}`}>
                          <div className="text-[10px] uppercase tracking-widest text-red-600 flex items-center gap-1"><Zap className="w-3 h-3" /> Execute a recommendation</div>
                          {m.suggested_actions.map((a, k) => (
                            <div key={k} className="flex items-start justify-between gap-3 bg-red-50/70 border border-red-200 p-2.5">
                              <div className="min-w-0">
                                <div className="text-sm font-medium leading-tight">{a.label}</div>
                                {a.description && <div className="text-xs text-neutral-600 mt-0.5">{a.description}</div>}
                                <div className="text-[10px] font-mono text-neutral-400 mt-0.5">{a.tool}</div>
                              </div>
                              <button className="k-btn kazo-bg-burgundy k-btn-sm shrink-0" onClick={() => executeSuggestion(a)} disabled={loading} data-testid={`mb-execute-${i}-${k}`} title="Preview this action, then confirm with a reason">
                                <Zap className="w-3.5 h-3.5" /> Execute
                              </button>
                            </div>
                          ))}
                          <div className="text-[10px] text-neutral-400">Each Execute previews first and asks you to confirm + give a reason. Nothing changes until you approve.</div>
                        </div>
                      )}
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
              <div className="max-w-3xl mx-auto">
                {attachments.length > 0 && (
                  <div className="flex flex-wrap gap-2 mb-2" data-testid="mb-pending-attachments">
                    {attachments.map((a) => (
                      <span key={a.id} className="inline-flex items-center gap-1.5 px-2 py-1 text-xs bg-neutral-100 border border-black/10 rounded" data-testid={`mb-attach-chip-${a.id}`}>
                        {a.kind === "image" ? <ImageIcon className="w-3 h-3 text-red-600" /> : <FileText className="w-3 h-3 text-red-600" />}
                        <span className="max-w-[180px] truncate">{a.filename}</span>
                        {a.kind === "report" && a.mobiles_detected != null && (
                          <span className="text-neutral-500">· {a.mobiles_detected} mobiles</span>
                        )}
                        <X className="w-3 h-3 cursor-pointer text-neutral-400 hover:text-red-600" onClick={() => removeAttachment(a.id)} data-testid={`mb-attach-remove-${a.id}`} />
                      </span>
                    ))}
                  </div>
                )}
                <div className="flex gap-2 items-end">
                  <input ref={fileRef} type="file" multiple accept=".png,.jpg,.jpeg,.webp,.csv,.xlsx,.xls,.pdf,image/*" onChange={handleUpload} className="hidden" data-testid="mb-file-input" />
                  <button className="k-btn k-btn-outline shrink-0" title="Attach a screenshot or report (PNG/JPG · CSV/Excel/PDF)" onClick={() => fileRef.current?.click()} disabled={loading || uploading} data-testid="mb-attach-btn">
                    {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Paperclip className="w-4 h-4" />}
                  </button>
                  <textarea
                    ref={inputRef}
                    rows={1}
                    className="k-input flex-1 resize-none leading-snug max-h-40 overflow-y-auto"
                    placeholder="Ask Master Brain to analyse — or take an action…  (Enter to send · Shift+Enter for a new line)"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
                    }}
                    disabled={loading}
                    data-testid="mb-input"
                  />
                  <button className="k-btn kazo-bg-burgundy shrink-0" onClick={() => send()} disabled={loading || (!input.trim() && attachments.length === 0)} data-testid="mb-send-btn"><Send className="w-4 h-4" /></button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ---------------- UNDO MODAL ---------------- */}
      {undoTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" data-testid="mb-undo-modal">
          <div className="bg-white border border-black/10 max-w-md w-full p-6">
            <div className="flex items-center gap-2 mb-2 text-red-700"><Undo2 className="w-5 h-5" /><span className="font-display text-lg">Undo action</span></div>
            <p className="text-sm text-neutral-600 mb-1">You're about to reverse:</p>
            <div className="text-sm bg-neutral-50 border border-black/10 p-3 mb-3">
              <div><b>{(undoTarget.action || "").replace("master_brain.", "")}</b> — {detailFrom(undoTarget.metadata)}</div>
              {undoTarget.reason && <div className="text-xs text-neutral-500 mt-1">Original reason: {undoTarget.reason}</div>}
            </div>
            <label className="text-xs uppercase tracking-widest text-neutral-500">Reason for undo (required)</label>
            <textarea className="k-input w-full mt-1 mb-4" rows={3} value={undoReason} onChange={(e) => setUndoReason(e.target.value)} placeholder="e.g. Reverted — awarded to the wrong customer." data-testid="mb-undo-reason" />
            <div className="flex justify-end gap-2">
              <button className="k-btn k-btn-outline" onClick={() => { setUndoTarget(null); setUndoReason(""); }} data-testid="mb-undo-cancel">Cancel</button>
              <button className="k-btn kazo-bg-burgundy" onClick={confirmUndo} disabled={undoing || !undoReason.trim()} data-testid="mb-undo-confirm">
                {undoing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Undo2 className="w-4 h-4" />} Confirm undo
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
