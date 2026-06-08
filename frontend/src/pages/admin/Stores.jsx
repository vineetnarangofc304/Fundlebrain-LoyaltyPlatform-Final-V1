import { useEffect, useState, useRef, useMemo } from "react";
import api, { API_URL } from "@/lib/api";
import { PageHeader } from "./_shared";
import { fmtDate } from "@/lib/format";
import { Plus, Upload, Download, Edit2, ChevronLeft, ChevronRight } from "lucide-react";
import { toast } from "sonner";

// Canonical Indian states + union territories (for the State dropdown)
const INDIAN_STATES = [
  "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa",
  "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala",
  "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland",
  "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
  "Uttar Pradesh", "Uttarakhand", "West Bengal",
  "Andaman and Nicobar Islands", "Chandigarh",
  "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Jammu and Kashmir",
  "Ladakh", "Lakshadweep", "Puducherry",
];
// Sales zones (mapped to the store `region` field)
const ZONES = ["North", "South", "East", "West", "Central", "North-East"];
const PAGE_SIZES = [20, 50, 100];

// Build a <select> option list that always includes the current value (so legacy /
// non-standard values like "Unknown" or "Not identified" still display + persist).
function withCurrent(options, value) {
  if (value && !options.includes(value)) return [value, ...options];
  return options;
}

export default function StoresPage() {
  const [stores, setStores] = useState([]);
  const [show, setShow] = useState(null);
  const [form, setForm] = useState({});
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const fileRef = useRef();

  const load = () => api.get("/stores").then((r) => setStores(r.data));
  useEffect(() => { load(); }, []);

  // Distinct existing cities (powers the City combobox suggestions)
  const cityOptions = useMemo(
    () => Array.from(new Set(stores.map((s) => (s.city || "").trim()).filter(Boolean))).sort(),
    [stores]
  );

  // Pagination (client-side — the store master is a bounded list)
  const totalPages = Math.max(1, Math.ceil(stores.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const pagedStores = stores.slice((safePage - 1) * pageSize, safePage * pageSize);
  const changePageSize = (n) => { setPageSize(n); setPage(1); };

  const openCreate = () => { setForm({ code: "", name: "", city: "", state: "", region: "", address: "", phone: "", manager_name: "" }); setShow("create"); };
  const openEdit = (s) => { setForm({ ...s }); setShow("edit"); };

  const submit = async () => {
    try {
      if (show === "create") {
        await api.post("/stores", form);
        toast.success("Store created");
      } else {
        await api.patch(`/stores/${form.id}`, form);
        toast.success("Store updated");
      }
      setShow(null); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const upload = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const fd = new FormData(); fd.append("file", f);
    try {
      const r = await api.post("/stores/bulk-upload", fd);
      toast.success(`Imported ${r.data.inserted}, skipped ${r.data.skipped}`);
      load();
    } catch { toast.error("Upload failed"); }
    if (fileRef.current) fileRef.current.value = "";
  };

  const downloadSample = () => {
    const token = localStorage.getItem("kazo_token");
    fetch(`${API_URL}/stores/sample-csv/download`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.blob())
      .then(b => { const u = URL.createObjectURL(b); const a = document.createElement("a"); a.href = u; a.download = "stores_sample.csv"; a.click(); URL.revokeObjectURL(u); });
  };

  return (
    <div data-testid="stores-page">
      <PageHeader title="Stores" subtitle="RETAIL FOOTPRINT"
        actions={
          <>
            <button className="k-btn k-btn-outline k-btn-sm" onClick={downloadSample} data-testid="stores-sample"><Download className="w-3.5 h-3.5" /> Sample CSV</button>
            <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={upload} data-testid="stores-bulk-file" />
            <button className="k-btn k-btn-outline k-btn-sm" onClick={() => fileRef.current?.click()} data-testid="stores-bulk"><Upload className="w-3.5 h-3.5" /> Bulk upload</button>
            <button className="k-btn kazo-bg-burgundy" onClick={openCreate} data-testid="new-store-btn"><Plus className="w-4 h-4" /> New store</button>
          </>
        } />
      <div className="p-8">
        {/* Top bar — count + page-size selector */}
        <div className="flex items-center justify-between mb-3">
          <div className="text-xs text-neutral-500 font-mono" data-testid="stores-count">
            {stores.length.toLocaleString("en-IN")} store{stores.length === 1 ? "" : "s"}
          </div>
          <div className="flex items-center gap-2 text-xs text-neutral-500">
            <span className="uppercase tracking-widest text-[10px]">Rows per page</span>
            <select
              className="k-input !w-auto !py-1"
              value={pageSize}
              onChange={(e) => changePageSize(parseInt(e.target.value))}
              data-testid="stores-page-size"
            >
              {PAGE_SIZES.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>
        </div>
        <div className="bg-white border border-black/10 overflow-x-auto">
          <table className="data-table">
            <thead><tr><th className="text-right w-12">S.No</th><th>Code</th><th>Name</th><th>City</th><th>State</th><th>Zone</th><th>Manager</th><th>Phone</th><th></th></tr></thead>
            <tbody>
              {pagedStores.map((s, i) => (
                <tr key={s.id} data-testid={`store-row-${s.code}`}>
                  <td className="text-right font-mono text-xs text-neutral-500" data-testid={`store-sno-${s.code}`}>{(safePage - 1) * pageSize + i + 1}</td>
                  <td className="font-mono text-xs">{s.code}</td>
                  <td className="font-medium">{s.name}</td>
                  <td>{s.city}</td>
                  <td>{s.state}</td>
                  <td><span className="pill pill-neutral">{s.region}</span></td>
                  <td>{s.manager_name}</td>
                  <td className="text-xs">{s.phone}</td>
                  <td><button className="k-btn k-btn-ghost k-btn-sm" onClick={() => openEdit(s)} data-testid={`edit-store-${s.code}`}><Edit2 className="w-3.5 h-3.5" /></button></td>
                </tr>
              ))}
              {pagedStores.length === 0 && (
                <tr><td colSpan={9} className="text-center text-sm text-neutral-500 py-10">No stores yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
        {/* Pagination controls */}
        {stores.length > 0 && (
          <div className="flex items-center justify-between mt-3 text-sm">
            <span className="text-neutral-500 font-mono text-xs">
              Showing {(safePage - 1) * pageSize + 1}–{Math.min(safePage * pageSize, stores.length)} of {stores.length.toLocaleString("en-IN")}
            </span>
            <div className="flex items-center gap-2">
              <button className="k-btn k-btn-outline k-btn-sm" disabled={safePage <= 1} onClick={() => setPage(safePage - 1)} data-testid="stores-prev"><ChevronLeft className="w-3.5 h-3.5" /> Prev</button>
              <span className="text-xs font-mono text-neutral-500" data-testid="stores-page-indicator">Page {safePage} of {totalPages}</span>
              <button className="k-btn k-btn-outline k-btn-sm" disabled={safePage >= totalPages} onClick={() => setPage(safePage + 1)} data-testid="stores-next">Next <ChevronRight className="w-3.5 h-3.5" /></button>
            </div>
          </div>
        )}
      </div>
      {show && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setShow(null)}>
          <div className="bg-white p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-display text-2xl mb-4">{show === "create" ? "New Store" : "Edit Store"}</h3>
            <div className="grid grid-cols-2 gap-3">
              <input className="k-input" placeholder="Code (e.g., KZO-MUM-01)" value={form.code || ""} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} data-testid="store-code" />
              <input className="k-input" placeholder="Name" value={form.name || ""} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="store-name" />
              <input className="k-input" list="store-city-options" placeholder="City" value={form.city || ""} onChange={(e) => setForm({ ...form, city: e.target.value })} data-testid="store-city" />
              <datalist id="store-city-options">
                {cityOptions.map((c) => <option key={c} value={c} />)}
              </datalist>
              <select className="k-input" value={form.state || ""} onChange={(e) => setForm({ ...form, state: e.target.value })} data-testid="store-state">
                <option value="">Select state…</option>
                {withCurrent(INDIAN_STATES, form.state).map((st) => <option key={st} value={st}>{st}</option>)}
              </select>
              <select className="k-input" value={form.region || ""} onChange={(e) => setForm({ ...form, region: e.target.value })} data-testid="store-zone">
                <option value="">Select zone…</option>
                {withCurrent(ZONES, form.region).map((z) => <option key={z} value={z}>{z}</option>)}
              </select>
              <input className="k-input" placeholder="Phone" value={form.phone || ""} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
              <input className="k-input col-span-2" placeholder="Address" value={form.address || ""} onChange={(e) => setForm({ ...form, address: e.target.value })} data-testid="store-address" />
              <input className="k-input" placeholder="Manager name" value={form.manager_name || ""} onChange={(e) => setForm({ ...form, manager_name: e.target.value })} />
              <input className="k-input" type="number" step="0.0001" placeholder="Latitude" value={form.latitude || ""} onChange={(e) => setForm({ ...form, latitude: parseFloat(e.target.value) || null })} />
              <input className="k-input" type="number" step="0.0001" placeholder="Longitude" value={form.longitude || ""} onChange={(e) => setForm({ ...form, longitude: parseFloat(e.target.value) || null })} />
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <button className="k-btn k-btn-ghost" onClick={() => setShow(null)}>Cancel</button>
              <button className="k-btn kazo-bg-burgundy" onClick={submit} data-testid="store-submit">{show === "create" ? "Create" : "Update"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
