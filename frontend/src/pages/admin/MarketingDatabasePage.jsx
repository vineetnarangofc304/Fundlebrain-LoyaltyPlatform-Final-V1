import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { PageHeader } from "./_shared";
import { toast } from "sonner";
import { fmtNum, fmtDate } from "@/lib/format";
import {
  Plus, Database, Users, UserCheck, UserX, Trash2, Eye, Send, Loader2, X,
  Upload, ClipboardPaste, Search, RefreshCw, ArrowLeft,
} from "lucide-react";

function StatCard({ icon: Icon, label, value, accent, testid }) {
  return (
    <div className="border border-black/10 rounded p-4 bg-white" data-testid={testid}>
      <div className="text-[10px] uppercase tracking-widest text-neutral-500 flex items-center gap-1"><Icon className="w-3.5 h-3.5" /> {label}</div>
      <div className={`text-3xl font-display mt-1 ${accent || ""}`}>{value}</div>
    </div>
  );
}

function CreateModal({ onClose, onDone }) {
  const [tab, setTab] = useState("paste");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [storeCode, setStoreCode] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef();

  const submit = async () => {
    if (!name.trim()) { toast.error("Enter a dataset name"); return; }
    setBusy(true);
    try {
      let r;
      if (tab === "upload") {
        if (!file) { toast.error("Choose a CSV/Excel file"); setBusy(false); return; }
        const fd = new FormData();
        fd.append("file", file);
        fd.append("name", name);
        fd.append("description", description);
        fd.append("store_code", storeCode);
        r = await api.post("/marketing-db/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      } else {
        if (!text.trim()) { toast.error("Paste some mobile numbers"); setBusy(false); return; }
        r = await api.post("/marketing-db", { name, description, store_code: storeCode, mobiles_text: text });
      }
      toast.success(`Created "${r.data.name}" · ${fmtNum(r.data.total)} numbers (${fmtNum(r.data.member_count)} members)`);
      onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to create dataset");
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white w-full max-w-lg rounded" onClick={(e) => e.stopPropagation()} data-testid="mdb-create-modal">
        <div className="flex items-center justify-between p-5 border-b border-black/10">
          <h3 className="font-display text-xl">New Marketing Database</h3>
          <button onClick={onClose} className="k-btn k-btn-ghost" data-testid="mdb-create-close"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-5 space-y-3">
          <input className="k-input" placeholder="Dataset name" value={name} onChange={(e) => setName(e.target.value)} data-testid="mdb-name-input" />
          <input className="k-input" placeholder="Description (optional)" value={description} onChange={(e) => setDescription(e.target.value)} data-testid="mdb-desc-input" />
          <input className="k-input" placeholder="Store code (optional)" value={storeCode} onChange={(e) => setStoreCode(e.target.value)} data-testid="mdb-store-input" />
          <div className="flex gap-2">
            <button onClick={() => setTab("paste")} className={`pill flex items-center gap-1 ${tab === "paste" ? "kazo-bg-burgundy text-white" : "pill-neutral"}`} data-testid="mdb-tab-paste"><ClipboardPaste className="w-3 h-3" /> Paste numbers</button>
            <button onClick={() => setTab("upload")} className={`pill flex items-center gap-1 ${tab === "upload" ? "kazo-bg-burgundy text-white" : "pill-neutral"}`} data-testid="mdb-tab-upload"><Upload className="w-3 h-3" /> Upload CSV/Excel</button>
          </div>
          {tab === "paste" ? (
            <textarea className="k-input font-mono text-xs" rows={7} placeholder="Paste mobile numbers — separated by comma, space or new line" value={text} onChange={(e) => setText(e.target.value)} data-testid="mdb-paste-input" />
          ) : (
            <div className="border-2 border-dashed border-black/15 rounded p-6 text-center cursor-pointer hover:bg-neutral-50" onClick={() => fileRef.current?.click()} data-testid="mdb-upload-drop">
              <Upload className="w-6 h-6 mx-auto text-neutral-400" />
              <div className="text-sm mt-2">{file ? file.name : "Click to choose a .csv or .xlsx file"}</div>
              <div className="text-[11px] text-neutral-400 mt-1">A column named mobile / phone / number is auto-detected</div>
              <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls,.txt" className="hidden" onChange={(e) => setFile(e.target.files?.[0] || null)} data-testid="mdb-file-input" />
            </div>
          )}
        </div>
        <div className="p-4 border-t border-black/10 flex justify-end gap-2">
          <button onClick={onClose} className="k-btn k-btn-ghost">Cancel</button>
          <button onClick={submit} disabled={busy} className="k-btn kazo-bg-burgundy disabled:opacity-50" data-testid="mdb-create-submit">
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />} Create dataset
          </button>
        </div>
      </div>
    </div>
  );
}

function DetailView({ mdb, onBack }) {
  const [page, setPage] = useState(1);
  const [member, setMember] = useState("");   // "", "true", "false"
  const [q, setQ] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get(`/marketing-db/${mdb.id}/customers`, { params: { page, page_size: 50, member: member || undefined, q: q || undefined } });
      setData(r.data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load");
    } finally { setLoading(false); }
  }, [mdb.id, page, member, q]);

  useEffect(() => { load(); }, [load]);

  const runCampaign = () => navigate(`/admin/campaigns?marketing_db_id=${mdb.id}&marketing_db_name=${encodeURIComponent(mdb.name)}`);

  const pages = data ? Math.max(1, Math.ceil(data.total / 50)) : 1;

  return (
    <div className="p-8" data-testid="mdb-detail">
      <button onClick={onBack} className="k-btn k-btn-ghost mb-4" data-testid="mdb-back"><ArrowLeft className="w-4 h-4" /> All datasets</button>
      <div className="flex items-start justify-between mb-4">
        <div>
          <h2 className="font-display text-2xl">{mdb.name}</h2>
          <div className="text-sm text-neutral-500">{mdb.description || "—"}{mdb.store_code ? ` · store ${mdb.store_code}` : ""} · created {fmtDate(mdb.created_at)}</div>
        </div>
        <button className="k-btn kazo-bg-burgundy" onClick={runCampaign} data-testid="mdb-run-campaign"><Send className="w-4 h-4" /> Run campaign on this dataset</button>
      </div>
      <div className="grid grid-cols-3 gap-3 mb-5">
        <StatCard icon={Users} label="Total numbers" value={fmtNum(mdb.total)} testid="mdb-stat-total" />
        <StatCard icon={UserCheck} label="Members" value={fmtNum(mdb.member_count)} accent="text-emerald-700" testid="mdb-stat-members" />
        <StatCard icon={UserX} label="Non-members" value={fmtNum(mdb.non_member_count)} accent="text-amber-600" testid="mdb-stat-nonmembers" />
      </div>
      <div className="flex gap-2 items-center mb-3">
        <select className="k-input w-48" value={member} onChange={(e) => { setMember(e.target.value); setPage(1); }} data-testid="mdb-member-filter">
          <option value="">All numbers</option>
          <option value="true">Members only</option>
          <option value="false">Non-members only</option>
        </select>
        <div className="relative flex-1 max-w-xs">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-3 text-neutral-400" />
          <input className="k-input pl-8" placeholder="Search number" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} data-testid="mdb-search" />
        </div>
      </div>
      <div className="bg-white border border-black/10 rounded overflow-hidden">
        <table className="data-table">
          <thead><tr><th>Mobile</th><th>Status</th><th>Name</th><th>Tier</th><th>City</th><th className="text-right">Points</th></tr></thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} className="text-center py-8 text-neutral-400"><Loader2 className="w-5 h-5 animate-spin inline" /></td></tr>
            ) : (data?.rows || []).map((r) => (
              <tr key={r.mobile} data-testid={`mdb-cust-${r.mobile}`}>
                <td className="font-mono">{r.mobile}</td>
                <td>{r.is_member ? <span className="pill" style={{ background: "#dcfce7", color: "#166534" }}>Member</span> : <span className="pill pill-warning">Non-member</span>}</td>
                <td>{r.name || "—"}</td>
                <td>{r.tier ? <span className="pill pill-neutral">{r.tier}</span> : "—"}</td>
                <td>{r.city || "—"}</td>
                <td className="text-right font-mono">{r.is_member ? fmtNum(r.points_balance || 0) : "—"}</td>
              </tr>
            ))}
            {!loading && (!data?.rows || data.rows.length === 0) && <tr><td colSpan={6} className="text-center py-8 text-neutral-400">No numbers match</td></tr>}
          </tbody>
        </table>
      </div>
      {data && data.total > 50 && (
        <div className="flex items-center justify-between mt-3 text-sm">
          <div className="text-neutral-500">{fmtNum(data.total)} numbers</div>
          <div className="flex gap-2 items-center">
            <button className="k-btn k-btn-sm k-btn-ghost disabled:opacity-40" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Prev</button>
            <span>{page} / {pages}</span>
            <button className="k-btn k-btn-sm k-btn-ghost disabled:opacity-40" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>Next</button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function MarketingDatabasePage() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [detail, setDetail] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get("/marketing-db");
      setRows(r.data.rows || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to load");
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const del = async (m) => {
    if (!window.confirm(`Delete marketing database "${m.name}"?`)) return;
    try { await api.delete(`/marketing-db/${m.id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Delete failed"); }
  };

  if (detail) return <DetailView mdb={detail} onBack={() => { setDetail(null); load(); }} />;

  return (
    <div data-testid="marketing-database-page">
      <PageHeader title="Marketing Database" subtitle="EXTERNAL AUDIENCE LISTS · MEMBER MATCHING · CAMPAIGN-READY"
        actions={<button className="k-btn kazo-bg-burgundy" onClick={() => setShowCreate(true)} data-testid="mdb-new-btn"><Plus className="w-4 h-4" /> New database</button>} />
      <div className="p-8">
        <div className="bg-white border border-black/10 overflow-x-auto">
          <table className="data-table">
            <thead><tr><th>Dataset</th><th className="text-right">Total</th><th className="text-right">Members</th><th className="text-right">Non-members</th><th>Source</th><th>Created</th><th></th></tr></thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={7} className="text-center py-10 text-neutral-400"><Loader2 className="w-5 h-5 animate-spin inline" /></td></tr>
              ) : rows.map((m) => (
                <tr key={m.id} data-testid={`mdb-row-${m.id}`}>
                  <td>
                    <button className="font-medium text-burgundy hover:underline flex items-center gap-1.5" onClick={() => setDetail(m)} data-testid={`mdb-open-${m.id}`}>
                      <Database className="w-3.5 h-3.5" /> {m.name}
                    </button>
                    {m.description && <div className="text-xs text-neutral-500">{m.description}</div>}
                  </td>
                  <td className="text-right font-mono">{fmtNum(m.total)}</td>
                  <td className="text-right font-mono text-emerald-700">{fmtNum(m.member_count)}</td>
                  <td className="text-right font-mono text-amber-600">{fmtNum(m.non_member_count)}</td>
                  <td><span className="pill pill-neutral">{(m.source || "").split(":")[0]}</span></td>
                  <td className="text-xs text-neutral-500">{fmtDate(m.created_at)}</td>
                  <td>
                    <div className="flex gap-1 justify-end">
                      <button className="k-btn k-btn-sm k-btn-ghost" onClick={() => setDetail(m)} data-testid={`mdb-view-${m.id}`}><Eye className="w-3.5 h-3.5" /></button>
                      <button className="k-btn k-btn-sm k-btn-ghost text-rose-600" onClick={() => del(m)} data-testid={`mdb-delete-${m.id}`}><Trash2 className="w-3.5 h-3.5" /></button>
                    </div>
                  </td>
                </tr>
              ))}
              {!loading && rows.length === 0 && <tr><td colSpan={7} className="text-center py-10 text-neutral-500">No datasets yet — click “New database” to upload numbers</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
      {showCreate && <CreateModal onClose={() => setShowCreate(false)} onDone={() => { setShowCreate(false); load(); }} />}
    </div>
  );
}
