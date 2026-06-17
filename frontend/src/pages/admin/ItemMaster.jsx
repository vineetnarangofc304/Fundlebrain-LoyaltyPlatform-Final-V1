import { useEffect, useState, useRef } from "react";
import api, { API_URL } from "@/lib/api";
import { PageHeader } from "./_shared";
import { toast } from "sonner";
import { fmtMoney2, fmtNum, fmtDate } from "@/lib/format";
import { Plus, Upload, Download, Search, Edit2, Trash2, FolderPlus } from "lucide-react";

export default function ItemMaster() {
  const [items, setItems] = useState({ total: 0, items: [] });
  const [categories, setCategories] = useState([]);
  const [q, setQ] = useState("");
  const [catFilter, setCatFilter] = useState("");
  const [showItemModal, setShowItemModal] = useState(null);
  const [showCatModal, setShowCatModal] = useState(false);
  const [form, setForm] = useState({});
  const [catForm, setCatForm] = useState({ name: "", code: "", description: "" });
  const fileRef = useRef();

  const load = async () => {
    const [i, c] = await Promise.all([
      api.get("/items", { params: { q, category: catFilter, limit: 200 } }),
      api.get("/items/categories"),
    ]);
    setItems(i.data);
    setCategories(c.data);
  };
  useEffect(() => { load(); }, [catFilter]);

  const openCreate = () => { setForm({ sku: "", name: "", category: categories[0]?.name || "", mrp: 0 }); setShowItemModal("create"); };
  const openEdit = (it) => { setForm({ ...it }); setShowItemModal("edit"); };

  const submit = async () => {
    try {
      if (showItemModal === "create") {
        await api.post("/items", form);
        toast.success("Item created");
      } else {
        await api.patch(`/items/${form.id}`, form);
        toast.success("Item updated");
      }
      setShowItemModal(null);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const removeItem = async (id) => {
    if (!window.confirm("Delete this SKU?")) return;
    await api.delete(`/items/${id}`);
    toast.success("Deleted");
    load();
  };

  const submitCategory = async () => {
    try {
      await api.post("/items/categories", catForm);
      toast.success("Category created");
      setShowCatModal(false);
      setCatForm({ name: "", code: "", description: "" });
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const handleUpload = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f);
    try {
      const r = await api.post("/items/bulk-upload", fd);
      toast.success(`Imported ${r.data.inserted}, skipped ${r.data.skipped}`);
      if (r.data.errors?.length) toast.warning(`${r.data.errors.length} rows had errors — check console`);
      console.log(r.data.errors);
      load();
    } catch (e) { toast.error("Upload failed"); }
    if (fileRef.current) fileRef.current.value = "";
  };

  const downloadSample = () => {
    const token = localStorage.getItem("kazo_token");
    fetch(`${API_URL}/items/sample-csv`, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.blob())
      .then(b => { const u = URL.createObjectURL(b); const a = document.createElement("a"); a.href = u; a.download = "items_sample.csv"; a.click(); URL.revokeObjectURL(u); });
  };

  return (
    <div data-testid="item-master-page">
      <PageHeader title="Item Master" subtitle="SKU & CATEGORY MANAGEMENT"
        actions={
          <>
            <button className="k-btn k-btn-outline k-btn-sm" onClick={downloadSample} data-testid="item-sample-csv"><Download className="w-3.5 h-3.5" /> Sample CSV</button>
            <input type="file" ref={fileRef} accept=".csv" className="hidden" onChange={handleUpload} data-testid="item-bulk-file" />
            <button className="k-btn k-btn-outline k-btn-sm" onClick={() => fileRef.current?.click()} data-testid="item-bulk-upload"><Upload className="w-3.5 h-3.5" /> Bulk upload</button>
            <button className="k-btn k-btn-outline k-btn-sm" onClick={() => setShowCatModal(true)} data-testid="add-category-btn"><FolderPlus className="w-3.5 h-3.5" /> New category</button>
            <button className="k-btn kazo-bg-burgundy" onClick={openCreate} data-testid="new-item-btn"><Plus className="w-4 h-4" /> New item</button>
          </>
        } />
      <div className="p-8 space-y-4">
        <div className="bg-white border border-black/10 p-4 flex flex-wrap gap-3">
          <div className="relative flex-1 min-w-[220px]">
            <Search className="w-4 h-4 absolute left-3 top-3 text-neutral-400" />
            <input className="k-input !pl-9" placeholder="Search by SKU, name, ERP ID" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()} data-testid="item-search" />
          </div>
          <select className="k-input !w-auto" value={catFilter} onChange={(e) => setCatFilter(e.target.value)} data-testid="item-cat-filter">
            <option value="">All categories</option>
            {categories.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
          </select>
          <button className="k-btn" onClick={load}>Search</button>
        </div>

        <div className="bg-white border border-black/10 p-3">
          <div className="text-xs uppercase tracking-widest text-neutral-500 mb-2 px-1">CATEGORIES</div>
          <div className="flex gap-2 flex-wrap">
            {categories.length === 0 && <span className="text-xs text-neutral-500">No categories yet · click "New category"</span>}
            {categories.map((c) => (
              <span key={c.id} className="pill pill-neutral" data-testid={`cat-${c.code}`}>{c.name}</span>
            ))}
          </div>
        </div>

        <div className="bg-white border border-black/10 overflow-x-auto">
          <div className="px-4 py-3 text-xs text-neutral-500 border-b">Showing {items.items.length} of {fmtNum(items.total)}</div>
          <table className="data-table">
            <thead><tr><th>SKU</th><th>Name</th><th>Category</th><th>ERP ID</th><th>Color/Size</th><th className="text-right">MRP</th><th>Created</th><th></th></tr></thead>
            <tbody>
              {items.items.map((it) => (
                <tr key={it.id} data-testid={`item-row-${it.sku}`}>
                  <td className="font-mono text-xs">{it.sku}</td>
                  <td className="font-medium">{it.name}</td>
                  <td><span className="pill pill-neutral">{it.category}</span></td>
                  <td className="font-mono text-xs">{it.erp_id || "—"}</td>
                  <td className="text-xs">{[it.color, it.size].filter(Boolean).join(" / ") || "—"}</td>
                  <td className="text-right font-mono">{fmtMoney2(it.mrp)}</td>
                  <td className="text-xs">{fmtDate(it.created_at)}</td>
                  <td>
                    <div className="flex gap-1">
                      <button className="k-btn k-btn-ghost k-btn-sm" onClick={() => openEdit(it)} data-testid={`edit-${it.sku}`}><Edit2 className="w-3.5 h-3.5" /></button>
                      <button className="k-btn k-btn-ghost k-btn-sm" onClick={() => removeItem(it.id)}><Trash2 className="w-3.5 h-3.5" /></button>
                    </div>
                  </td>
                </tr>
              ))}
              {items.items.length === 0 && <tr><td colSpan={8} className="text-center py-10 text-neutral-500">No items yet · bulk upload or add manually</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {showItemModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setShowItemModal(null)}>
          <div className="bg-white p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-display text-2xl mb-4">{showItemModal === "create" ? "New Item" : "Edit Item"}</h3>
            <div className="grid grid-cols-2 gap-3">
              <input className="k-input col-span-2" placeholder="SKU (e.g., K10001)" value={form.sku || ""} onChange={(e) => setForm({ ...form, sku: e.target.value.toUpperCase() })} data-testid="item-sku" />
              <input className="k-input col-span-2" placeholder="Name" value={form.name || ""} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="item-name" />
              <select className="k-input" value={form.category || ""} onChange={(e) => setForm({ ...form, category: e.target.value })} data-testid="item-category">
                <option value="">Category</option>
                {categories.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
              </select>
              <input className="k-input" placeholder="Subcategory" value={form.subcategory || ""} onChange={(e) => setForm({ ...form, subcategory: e.target.value })} />
              <input className="k-input" placeholder="ERP ID" value={form.erp_id || ""} onChange={(e) => setForm({ ...form, erp_id: e.target.value })} />
              <input className="k-input" placeholder="Barcode" value={form.barcode || ""} onChange={(e) => setForm({ ...form, barcode: e.target.value })} />
              <input className="k-input" type="number" placeholder="MRP (₹)" value={form.mrp || ""} onChange={(e) => setForm({ ...form, mrp: parseFloat(e.target.value) || 0 })} data-testid="item-mrp" />
              <input className="k-input" placeholder="Season (e.g., SS26)" value={form.season || ""} onChange={(e) => setForm({ ...form, season: e.target.value })} />
              <input className="k-input" placeholder="Color" value={form.color || ""} onChange={(e) => setForm({ ...form, color: e.target.value })} />
              <input className="k-input" placeholder="Size" value={form.size || ""} onChange={(e) => setForm({ ...form, size: e.target.value })} />
              <textarea className="k-input col-span-2" rows={3} placeholder="Description" value={form.description || ""} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <button className="k-btn k-btn-ghost" onClick={() => setShowItemModal(null)}>Cancel</button>
              <button className="k-btn kazo-bg-burgundy" onClick={submit} data-testid="item-submit">{showItemModal === "create" ? "Create" : "Update"}</button>
            </div>
          </div>
        </div>
      )}

      {showCatModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setShowCatModal(false)}>
          <div className="bg-white p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-display text-2xl mb-4">New Category</h3>
            <div className="space-y-3">
              <input className="k-input" placeholder="Name (e.g., DRESSES)" value={catForm.name} onChange={(e) => setCatForm({ ...catForm, name: e.target.value.toUpperCase() })} data-testid="cat-name" />
              <input className="k-input" placeholder="Code (e.g., DRS)" value={catForm.code} onChange={(e) => setCatForm({ ...catForm, code: e.target.value.toUpperCase() })} />
              <textarea className="k-input" rows={2} placeholder="Description (optional)" value={catForm.description} onChange={(e) => setCatForm({ ...catForm, description: e.target.value })} />
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <button className="k-btn k-btn-ghost" onClick={() => setShowCatModal(false)}>Cancel</button>
              <button className="k-btn kazo-bg-burgundy" onClick={submitCategory} data-testid="cat-submit">Create</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
