import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader, StatusPill } from "./_shared";
import { toast } from "sonner";
import { fmtDate, fmtNum } from "@/lib/format";
import { Plus } from "lucide-react";

const COUPON_TYPES = ["flat", "percentage", "sku", "category", "store", "city", "referral", "birthday", "anniversary", "winback", "new_customer", "festival", "vip"];

export default function CouponEngine() {
  const [coupons, setCoupons] = useState([]);
  const [period, setPeriod] = useState(0);
  const [show, setShow] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(emptyForm());

  function emptyForm() {
    return {
      code: "", name: "", coupon_type: "percentage", discount_value: 10,
      min_bill_amount: 0, max_discount: null,
      valid_from: new Date().toISOString().slice(0, 16),
      valid_to: new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 16),
      usage_limit: 1000, usage_limit_per_customer: 1, require_otp: false, is_active: true,
      description: "",
    };
  }

  const load = async () => {
    const r = await api.get("/coupons");
    setCoupons(r.data);
  };
  useEffect(() => { load(); }, []);

  // Filter coupons by issuance-date window. Doing this client-side keeps the
  // API contract stable; full coupons list is small enough (typically <500
  // active templates per brand) for in-memory filtering.
  const filteredCoupons = (() => {
    if (!period) return coupons;
    const cutoff = Date.now() - period * 86400000;
    return coupons.filter((c) => {
      if (!c.created_at) return false;
      return new Date(c.created_at).getTime() >= cutoff;
    });
  })();

  const genCode = async () => {
    const r = await api.post("/coupons/generate-code", null, { params: { prefix: "KAZO" } });
    setForm((f) => ({ ...f, code: r.data.code }));
  };

  const submit = async () => {
    try {
      const payload = {
        ...form,
        valid_from: new Date(form.valid_from).toISOString(),
        valid_to: new Date(form.valid_to).toISOString(),
      };
      if (editingId) {
        await api.patch(`/coupons/${editingId}`, payload);
        toast.success("Coupon updated");
      } else {
        await api.post("/coupons", payload);
        toast.success("Coupon created");
      }
      setShow(false); setEditingId(null); setForm(emptyForm()); load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    }
  };

  const openEdit = (c) => {
    setEditingId(c.id);
    setForm({
      ...c,
      valid_from: new Date(c.valid_from).toISOString().slice(0, 16),
      valid_to: new Date(c.valid_to).toISOString().slice(0, 16),
    });
    setShow(true);
  };

  return (
    <div data-testid="coupon-engine">
      <PageHeader
        title="Coupon Engine"
        subtitle="DYNAMIC COUPON BUILDER"
        actions={
          <>
            <select className="k-input !w-auto !py-1.5" value={period} onChange={(e) => setPeriod(parseInt(e.target.value))} data-testid="cp-period">
              <option value={0}>All time</option>
              <option value={7}>Issued · 7d</option>
              <option value={30}>Issued · 30d</option>
              <option value={90}>Issued · 90d</option>
              <option value={365}>Issued · 365d</option>
            </select>
            <button className="k-btn kazo-bg-burgundy" onClick={() => { setEditingId(null); setForm(emptyForm()); setShow(true); }} data-testid="new-coupon-btn"><Plus className="w-4 h-4" /> New coupon</button>
          </>
        }
      />

      <div className="p-8">
        <div className="bg-white border border-black/10 overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr><th>Code</th><th>Name</th><th>Type</th><th>Value</th><th>Min Bill</th><th>Issued On</th><th>Valid To</th><th className="text-right">Used / Issued</th><th>Status</th><th></th></tr>
            </thead>
            <tbody>
              {filteredCoupons.map((c) => (
                <tr key={c.id} data-testid={`coupon-row-${c.code}`}>
                  <td><span className="font-mono font-semibold inline-block px-2 py-0.5 bg-amber-50 border border-amber-200 text-amber-800 rounded-sm" data-testid={`coupon-code-${c.code}`}>{c.code}</span></td>
                  <td>{c.name}</td>
                  <td><span className="pill pill-neutral">{c.coupon_type}</span></td>
                  <td className="font-mono">{c.coupon_type === "percentage" ? `${c.discount_value}%` : `₹${c.discount_value}`}</td>
                  <td className="font-mono">₹{c.min_bill_amount || 0}</td>
                  <td className="text-xs text-neutral-600">{c.created_at ? fmtDate(c.created_at) : "—"}</td>
                  <td className="text-xs">{fmtDate(c.valid_to)}</td>
                  <td className="text-right font-mono">{fmtNum(c.times_used)} / {fmtNum(c.times_issued)}</td>
                  <td><StatusPill status={c.is_active ? "active" : "inactive"} /></td>
                  <td><button className="k-btn k-btn-ghost k-btn-sm" onClick={() => openEdit(c)} data-testid={`edit-coupon-${c.code}`}>Edit</button></td>
                </tr>
              ))}
              {filteredCoupons.length === 0 && <tr><td colSpan={10} className="text-center py-10 text-neutral-500">{period ? "No coupons issued in this window" : "No coupons yet"}</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {show && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setShow(false)}>
          <div className="bg-white p-6 w-full max-w-3xl max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()} data-testid="new-coupon-modal">
            <h3 className="font-display text-2xl mb-4">{editingId ? "Edit Coupon" : "New Coupon"}</h3>
            <div className="grid grid-cols-2 gap-3">
              <div className="flex gap-2 col-span-2">
                <input className="k-input" placeholder="Code (e.g., KAZOWELCOME20)" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} data-testid="coupon-code-input" />
                <button type="button" className="k-btn k-btn-outline" onClick={genCode} data-testid="generate-code-btn">Generate</button>
              </div>
              <input className="k-input col-span-2" placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="coupon-name-input" />
              <select className="k-input" value={form.coupon_type} onChange={(e) => setForm({ ...form, coupon_type: e.target.value })} data-testid="coupon-type-input">
                {COUPON_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              <input className="k-input" type="number" placeholder="Discount value" value={form.discount_value} onChange={(e) => setForm({ ...form, discount_value: parseFloat(e.target.value) || 0 })} data-testid="coupon-value-input" />
              <input className="k-input" type="number" placeholder="Min bill ₹" value={form.min_bill_amount} onChange={(e) => setForm({ ...form, min_bill_amount: parseFloat(e.target.value) || 0 })} data-testid="coupon-minbill-input" />
              <input className="k-input" type="number" placeholder="Max discount ₹ (optional)" value={form.max_discount || ""} onChange={(e) => setForm({ ...form, max_discount: e.target.value ? parseFloat(e.target.value) : null })} data-testid="coupon-maxdiscount-input" />
              <input className="k-input" type="datetime-local" value={form.valid_from} onChange={(e) => setForm({ ...form, valid_from: e.target.value })} data-testid="coupon-validfrom-input" />
              <input className="k-input" type="datetime-local" value={form.valid_to} onChange={(e) => setForm({ ...form, valid_to: e.target.value })} data-testid="coupon-validto-input" />
              <input className="k-input" type="number" placeholder="Usage limit" value={form.usage_limit} onChange={(e) => setForm({ ...form, usage_limit: parseInt(e.target.value) || 0 })} data-testid="coupon-usagelimit-input" />
              <input className="k-input" type="number" placeholder="Per customer" value={form.usage_limit_per_customer} onChange={(e) => setForm({ ...form, usage_limit_per_customer: parseInt(e.target.value) || 1 })} data-testid="coupon-percust-input" />
              <textarea className="k-input col-span-2" placeholder="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} data-testid="coupon-desc-input" />
            </div>
            <div className="flex justify-end gap-2 mt-4">
              <button className="k-btn k-btn-ghost" onClick={() => { setShow(false); setEditingId(null); }}>Cancel</button>
              <button className="k-btn kazo-bg-burgundy" onClick={submit} data-testid="coupon-create-btn">{editingId ? "Update" : "Create"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
