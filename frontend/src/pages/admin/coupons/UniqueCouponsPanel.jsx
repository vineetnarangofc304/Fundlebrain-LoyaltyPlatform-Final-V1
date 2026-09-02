import { BRAND } from "@/brand.config";
import { useCallback, useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { fmtNum, fmtDate } from "@/lib/format";
import {
  Plus, Ticket, Loader2, X, Trash2, DownloadCloud, ArrowLeft, Search, Users, Database, ClipboardPaste,
} from "lucide-react";

function CreateBatchModal({ segments, mdbs, onClose, onDone }) {
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState({
    name: "", coupon_type: "flat", discount_value: 100, min_bill_amount: 0, max_discount: "",
    valid_from: new Date().toISOString().slice(0, 16),
    valid_to: new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 16),
    prefix: BRAND.couponPrefix,
  });
  const [src, setSrc] = useState("marketing_db");
  const [segId, setSegId] = useState("");
  const [mdbId, setMdbId] = useState("");
  const [mobilesText, setMobilesText] = useState("");

  const submit = async () => {
    if (!f.name.trim()) { toast.error("Enter an offer name"); return; }
    const audience = { source: src };
    if (src === "segment") { if (!segId) { toast.error("Pick a segment"); return; } audience.segment_id = segId; }
    else if (src === "marketing_db") { if (!mdbId) { toast.error("Pick a marketing database"); return; } audience.marketing_db_id = mdbId; }
    else { const mobiles = (mobilesText.match(/\d{10,}/g) || []).map((m) => m.slice(-10)); if (!mobiles.length) { toast.error("Paste some mobile numbers"); return; } audience.mobiles = mobiles; }
    setBusy(true);
    try {
      const r = await api.post("/coupons/unique/allocate", {
        name: f.name, coupon_type: f.coupon_type, discount_value: parseFloat(f.discount_value),
        min_bill_amount: parseFloat(f.min_bill_amount) || 0,
        max_discount: f.max_discount ? parseFloat(f.max_discount) : null,
        valid_from: new Date(f.valid_from).toISOString(), valid_to: new Date(f.valid_to).toISOString(),
        prefix: f.prefix, audience,
      });
      toast.success(`Allocated ${fmtNum(r.data.total)} unique coupons`);
      onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Allocation failed");
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white w-full max-w-2xl max-h-[92vh] overflow-y-auto rounded" onClick={(e) => e.stopPropagation()} data-testid="unique-create-modal">
        <div className="flex items-center justify-between p-5 border-b border-black/10">
          <h3 className="font-display text-xl">Create & Allocate Unique Coupons</h3>
          <button onClick={onClose} className="k-btn k-btn-ghost" data-testid="unique-create-close"><X className="w-4 h-4" /></button>
        </div>
        <div className="p-5 space-y-4">
          <div className="text-[10px] uppercase tracking-widest text-neutral-500">1 · Define the offer</div>
          <div className="grid grid-cols-2 gap-3">
            <input className="k-input col-span-2" placeholder="Offer name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} data-testid="unique-name-input" />
            <select className="k-input" value={f.coupon_type} onChange={(e) => setF({ ...f, coupon_type: e.target.value })} data-testid="unique-type-select">
              <option value="flat">Flat ₹ off</option>
              <option value="percentage">Percentage %</option>
            </select>
            <input className="k-input" type="number" placeholder={f.coupon_type === "percentage" ? "% discount" : "₹ discount"} value={f.discount_value} onChange={(e) => setF({ ...f, discount_value: e.target.value })} data-testid="unique-value-input" />
            <input className="k-input" type="number" placeholder="Min bill ₹" value={f.min_bill_amount} onChange={(e) => setF({ ...f, min_bill_amount: e.target.value })} data-testid="unique-minbill-input" />
            <input className="k-input" type="number" placeholder="Max discount ₹ (optional)" value={f.max_discount} onChange={(e) => setF({ ...f, max_discount: e.target.value })} data-testid="unique-maxdisc-input" />
            <input className="k-input" type="datetime-local" value={f.valid_from} onChange={(e) => setF({ ...f, valid_from: e.target.value })} data-testid="unique-from-input" />
            <input className="k-input" type="datetime-local" value={f.valid_to} onChange={(e) => setF({ ...f, valid_to: e.target.value })} data-testid="unique-to-input" />
            <input className="k-input col-span-2" placeholder={`Code prefix (e.g. ${BRAND.couponPrefix})`} value={f.prefix} onChange={(e) => setF({ ...f, prefix: e.target.value })} data-testid="unique-prefix-input" />
          </div>

          <div className="text-[10px] uppercase tracking-widest text-neutral-500 pt-2">2 · Who gets a unique code</div>
          <div className="flex gap-2">
            <button onClick={() => setSrc("marketing_db")} className={`pill flex items-center gap-1 ${src === "marketing_db" ? "kazo-bg-burgundy text-white" : "pill-neutral"}`} data-testid="unique-src-mdb"><Database className="w-3 h-3" /> Marketing DB</button>
            <button onClick={() => setSrc("segment")} className={`pill flex items-center gap-1 ${src === "segment" ? "kazo-bg-burgundy text-white" : "pill-neutral"}`} data-testid="unique-src-segment"><Users className="w-3 h-3" /> Segment</button>
            <button onClick={() => setSrc("mobiles")} className={`pill flex items-center gap-1 ${src === "mobiles" ? "kazo-bg-burgundy text-white" : "pill-neutral"}`} data-testid="unique-src-mobiles"><ClipboardPaste className="w-3 h-3" /> Paste numbers</button>
          </div>
          {src === "marketing_db" && (
            <select className="k-input" value={mdbId} onChange={(e) => setMdbId(e.target.value)} data-testid="unique-mdb-select">
              <option value="">Select a marketing database</option>
              {mdbs.map((m) => <option key={m.id} value={m.id}>{`${m.name} · ${m.total} numbers`}</option>)}
            </select>
          )}
          {src === "segment" && (
            <select className="k-input" value={segId} onChange={(e) => setSegId(e.target.value)} data-testid="unique-segment-select">
              <option value="">Select a segment</option>
              {segments.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          )}
          {src === "mobiles" && (
            <textarea className="k-input font-mono text-xs" rows={5} placeholder="Paste mobile numbers (comma / space / newline separated)" value={mobilesText} onChange={(e) => setMobilesText(e.target.value)} data-testid="unique-mobiles-input" />
          )}
        </div>
        <div className="p-4 border-t border-black/10 flex justify-end gap-2">
          <button onClick={onClose} className="k-btn k-btn-ghost">Cancel</button>
          <button onClick={submit} disabled={busy} className="k-btn kazo-bg-burgundy disabled:opacity-50" data-testid="unique-allocate-btn">
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Ticket className="w-4 h-4" />} Allocate coupons
          </button>
        </div>
      </div>
    </div>
  );
}

function BatchDetail({ batch, onBack }) {
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get(`/coupons/unique/batches/${batch.id}`, { params: { page, page_size: 50, status: status || undefined, q: q || undefined } });
      setData(r.data);
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
    finally { setLoading(false); }
  }, [batch.id, page, status, q]);
  useEffect(() => { load(); }, [load]);

  const download = async () => {
    try {
      const r = await api.get(`/coupons/unique/batches/${batch.id}/export`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([r.data]));
      const a = document.createElement("a");
      a.href = url; a.download = `unique_coupons_${batch.name}.csv`; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Export failed"); }
  };

  const pages = data ? Math.max(1, Math.ceil(data.total / 50)) : 1;

  return (
    <div data-testid="unique-batch-detail">
      <div className="flex items-center justify-between mb-4">
        <button onClick={onBack} className="k-btn k-btn-ghost" data-testid="unique-back"><ArrowLeft className="w-4 h-4" /> All batches</button>
        <button onClick={download} className="k-btn k-btn-ghost" data-testid="unique-export"><DownloadCloud className="w-4 h-4" /> Export codes CSV</button>
      </div>
      <h2 className="font-display text-2xl">{batch.name}</h2>
      <div className="text-sm text-neutral-500 mb-4">
        {batch.coupon_type === "percentage" ? `${batch.discount_value}% off` : `₹${batch.discount_value} off`} · min ₹{batch.min_bill_amount || 0} · prefix {batch.prefix} · {fmtNum(batch.total)} codes · {fmtNum(batch.redeemed || 0)} redeemed
      </div>
      <div className="flex gap-2 items-center mb-3">
        <select className="k-input w-40" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} data-testid="unique-status-filter">
          <option value="">All codes</option>
          <option value="allocated">Allocated</option>
          <option value="redeemed">Redeemed</option>
        </select>
        <div className="relative flex-1 max-w-xs">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-3 text-neutral-400" />
          <input className="k-input pl-8" placeholder="Search code / mobile" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} data-testid="unique-search" />
        </div>
      </div>
      <div className="bg-white border border-black/10 rounded overflow-hidden">
        <table className="data-table">
          <thead><tr><th>Code</th><th>Mobile</th><th>Status</th><th>Redeemed</th><th>Bill #</th><th className="text-right">Discount</th></tr></thead>
          <tbody>
            {loading ? <tr><td colSpan={6} className="text-center py-8 text-neutral-400"><Loader2 className="w-5 h-5 animate-spin inline" /></td></tr>
              : (data?.rows || []).map((r) => (
                <tr key={r.code} data-testid={`unique-code-${r.code}`}>
                  <td><span className="font-mono font-semibold px-2 py-0.5 bg-amber-50 border border-amber-200 text-amber-800 rounded-sm">{r.code}</span></td>
                  <td className="font-mono">{r.mobile}</td>
                  <td>{r.status === "redeemed" ? <span className="pill" style={{ background: "#dcfce7", color: "#166534" }}>redeemed</span> : <span className="pill pill-neutral">allocated</span>}</td>
                  <td className="text-xs text-neutral-500">{r.redeemed_at ? fmtDate(r.redeemed_at) : "—"}</td>
                  <td className="font-mono text-xs">{r.bill_number || "—"}</td>
                  <td className="text-right font-mono">{r.discount != null ? `₹${r.discount}` : "—"}</td>
                </tr>
              ))}
            {!loading && (!data?.rows || data.rows.length === 0) && <tr><td colSpan={6} className="text-center py-8 text-neutral-400">No codes match</td></tr>}
          </tbody>
        </table>
      </div>
      {data && data.total > 50 && (
        <div className="flex items-center justify-between mt-3 text-sm">
          <div className="text-neutral-500">{fmtNum(data.total)} codes</div>
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

export default function UniqueCouponsPanel() {
  const [batches, setBatches] = useState([]);
  const [segments, setSegments] = useState([]);
  const [mdbs, setMdbs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [detail, setDetail] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const [b, s, m] = await Promise.all([
        api.get("/coupons/unique/batches"),
        api.get("/segments/").catch(() => ({ data: { rows: [] } })),
        api.get("/marketing-db").catch(() => ({ data: { rows: [] } })),
      ]);
      setBatches(b.data.rows || []);
      setSegments(s.data.rows || s.data || []);
      setMdbs(m.data.rows || []);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const del = async (b) => {
    if (!window.confirm(`Delete batch "${b.name}" and all its codes?`)) return;
    try { await api.delete(`/coupons/unique/batches/${b.id}`); toast.success("Deleted"); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Delete failed"); }
  };

  if (detail) return <BatchDetail batch={detail} onBack={() => { setDetail(null); load(); }} />;

  return (
    <div data-testid="unique-coupons-panel">
      <div className="flex justify-end mb-4">
        <button className="k-btn kazo-bg-burgundy" onClick={() => setShowCreate(true)} data-testid="unique-new-btn"><Plus className="w-4 h-4" /> New unique batch</button>
      </div>
      <div className="bg-white border border-black/10 overflow-x-auto">
        <table className="data-table">
          <thead><tr><th>Batch</th><th>Offer</th><th>Source</th><th className="text-right">Codes</th><th className="text-right">Redeemed</th><th>Created</th><th></th></tr></thead>
          <tbody>
            {loading ? <tr><td colSpan={7} className="text-center py-10 text-neutral-400"><Loader2 className="w-5 h-5 animate-spin inline" /></td></tr>
              : batches.map((b) => (
                <tr key={b.id} data-testid={`unique-batch-${b.id}`}>
                  <td><button className="font-medium text-burgundy hover:underline flex items-center gap-1.5" onClick={() => setDetail(b)} data-testid={`unique-open-${b.id}`}><Ticket className="w-3.5 h-3.5" /> {b.name}</button></td>
                  <td className="font-mono text-sm">{b.coupon_type === "percentage" ? `${b.discount_value}%` : `₹${b.discount_value}`}</td>
                  <td><span className="pill pill-neutral">{b.source}</span></td>
                  <td className="text-right font-mono">{fmtNum(b.total)}</td>
                  <td className="text-right font-mono text-emerald-700">{fmtNum(b.redeemed || 0)}</td>
                  <td className="text-xs text-neutral-500">{fmtDate(b.created_at)}</td>
                  <td><div className="flex gap-1 justify-end">
                    <button className="k-btn k-btn-sm k-btn-ghost text-rose-600" onClick={() => del(b)} data-testid={`unique-delete-${b.id}`}><Trash2 className="w-3.5 h-3.5" /></button>
                  </div></td>
                </tr>
              ))}
            {!loading && batches.length === 0 && <tr><td colSpan={7} className="text-center py-10 text-neutral-500">No unique-coupon batches yet — click “New unique batch”</td></tr>}
          </tbody>
        </table>
      </div>
      {showCreate && <CreateBatchModal segments={segments} mdbs={mdbs} onClose={() => setShowCreate(false)} onDone={() => { setShowCreate(false); load(); }} />}
    </div>
  );
}
