import { useEffect, useState, useRef } from "react";
import api, { API_URL } from "@/lib/api";
import { PageHeader } from "./_shared";
import { fmtDate } from "@/lib/format";
import { Plus, Upload, Download, Edit2 } from "lucide-react";
import { toast } from "sonner";

export default function StoresPage() {
  const [stores, setStores] = useState([]);
  const [show, setShow] = useState(null);
  const [form, setForm] = useState({});
  const fileRef = useRef();

  const load = async () => { const r = await api.get("/stores"); setStores(r.data); };
  useEffect(() => { load(); }, []);

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
        <div className="bg-white border border-black/10 overflow-x-auto">
          <table className="data-table">
            <thead><tr><th>Code</th><th>Name</th><th>City</th><th>State</th><th>Region</th><th>Manager</th><th>Phone</th><th></th></tr></thead>
            <tbody>
              {stores.map((s) => (
                <tr key={s.id} data-testid={`store-row-${s.code}`}>
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
            </tbody>
          </table>
        </div>
      </div>
      {show && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setShow(null)}>
          <div className="bg-white p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-display text-2xl mb-4">{show === "create" ? "New Store" : "Edit Store"}</h3>
            <div className="grid grid-cols-2 gap-3">
              <input className="k-input" placeholder="Code (e.g., KZO-MUM-01)" value={form.code || ""} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} data-testid="store-code" />
              <input className="k-input" placeholder="Name" value={form.name || ""} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="store-name" />
              <input className="k-input" placeholder="City" value={form.city || ""} onChange={(e) => setForm({ ...form, city: e.target.value })} data-testid="store-city" />
              <input className="k-input" placeholder="State" value={form.state || ""} onChange={(e) => setForm({ ...form, state: e.target.value })} />
              <input className="k-input" placeholder="Region (e.g., West)" value={form.region || ""} onChange={(e) => setForm({ ...form, region: e.target.value })} />
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
