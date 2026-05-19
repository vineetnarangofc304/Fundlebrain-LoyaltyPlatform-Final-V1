import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader, StatusPill } from "./_shared";
import { toast } from "sonner";
import { fmtINR, fmtNum, fmtDate } from "@/lib/format";
import { Plus, Play } from "lucide-react";

const CHANNELS = ["whatsapp", "sms", "email", "push", "in_app"];

export default function CampaignManager() {
  const [items, setItems] = useState([]);
  const [show, setShow] = useState(false);
  const [coupons, setCoupons] = useState([]);
  const [form, setForm] = useState({
    name: "", description: "", channels: ["whatsapp"], audience_type: "all",
    audience_filter: {}, message_template: "", coupon_code: "", status: "draft",
  });

  const load = async () => {
    const [c, co] = await Promise.all([api.get("/campaigns"), api.get("/coupons", { params: { is_active: true } })]);
    setItems(c.data);
    setCoupons(co.data);
  };
  useEffect(() => { load(); }, []);

  const toggleChannel = (ch) => {
    setForm((f) => ({ ...f, channels: f.channels.includes(ch) ? f.channels.filter(x => x !== ch) : [...f.channels, ch] }));
  };

  const create = async () => {
    try {
      await api.post("/campaigns", form);
      toast.success("Campaign created");
      setShow(false);
      setForm({ name: "", description: "", channels: ["whatsapp"], audience_type: "all", audience_filter: {}, message_template: "", coupon_code: "", status: "draft" });
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  const launch = async (id) => {
    try {
      const r = await api.post(`/campaigns/${id}/launch`);
      toast.success(`Launched · audience ${r.data.audience}`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Launch failed");
    }
  };

  return (
    <div data-testid="campaign-manager">
      <PageHeader title="Campaign Manager" subtitle="MULTI-CHANNEL ORCHESTRATION"
        actions={<button className="k-btn kazo-bg-burgundy" onClick={() => setShow(true)} data-testid="new-campaign-btn"><Plus className="w-4 h-4" /> New campaign</button>} />
      <div className="p-8">
        <div className="bg-white border border-black/10 overflow-x-auto">
          <table className="data-table">
            <thead><tr><th>Campaign</th><th>Channels</th><th>Audience</th><th className="text-right">Sent</th><th className="text-right">Delivered</th><th className="text-right">Redeemed</th><th className="text-right">Revenue</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {items.map((c) => (
                <tr key={c.id} data-testid={`campaign-row-${c.id}`}>
                  <td><div className="font-medium">{c.name}</div><div className="text-xs text-neutral-500">{fmtDate(c.created_at)}</div></td>
                  <td><div className="flex gap-1 flex-wrap">{c.channels?.map((ch) => <span key={ch} className="pill pill-neutral">{ch}</span>)}</div></td>
                  <td><span className="pill pill-info">{c.audience_type}</span></td>
                  <td className="text-right font-mono">{fmtNum(c.sent)}</td>
                  <td className="text-right font-mono">{fmtNum(c.delivered)}</td>
                  <td className="text-right font-mono">{fmtNum(c.redeemed)}</td>
                  <td className="text-right font-mono">{fmtINR(c.revenue_generated)}</td>
                  <td><StatusPill status={c.status} /></td>
                  <td>{c.status === "draft" && <button className="k-btn k-btn-sm kazo-bg-burgundy" onClick={() => launch(c.id)} data-testid={`launch-${c.id}`}><Play className="w-3 h-3" /> Launch</button>}</td>
                </tr>
              ))}
              {items.length === 0 && <tr><td colSpan={9} className="text-center py-10 text-neutral-500">No campaigns yet</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {show && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setShow(false)}>
          <div className="bg-white p-6 w-full max-w-3xl max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()} data-testid="new-campaign-modal">
            <h3 className="font-display text-2xl mb-4">New Campaign</h3>
            <div className="space-y-3">
              <input className="k-input" placeholder="Campaign name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="campaign-name-input" />
              <textarea className="k-input" placeholder="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
              <div>
                <label className="text-[10px] uppercase tracking-widest text-neutral-500 mb-2 block">Channels</label>
                <div className="flex gap-2 flex-wrap">
                  {CHANNELS.map((ch) => (
                    <button key={ch} type="button" onClick={() => toggleChannel(ch)} className={`pill ${form.channels.includes(ch) ? "kazo-bg-burgundy text-white" : "pill-neutral"}`} data-testid={`channel-${ch}`}>{ch}</button>
                  ))}
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <select className="k-input" value={form.audience_type} onChange={(e) => setForm({ ...form, audience_type: e.target.value, audience_filter: {} })} data-testid="audience-type-select">
                  <option value="all">Entire base</option>
                  <option value="tier">By tier</option>
                  <option value="city">By city</option>
                  <option value="cohort">By cohort</option>
                </select>
                {form.audience_type === "tier" && (
                  <select className="k-input" value={form.audience_filter?.tier || ""} onChange={(e) => setForm({ ...form, audience_filter: { tier: e.target.value } })}>
                    <option value="">Select tier</option>
                    <option value="silver">Silver</option><option value="gold">Gold</option><option value="platinum">Platinum</option><option value="diamond">Diamond</option>
                  </select>
                )}
                {form.audience_type === "city" && (
                  <input className="k-input" placeholder="City" value={form.audience_filter?.city || ""} onChange={(e) => setForm({ ...form, audience_filter: { city: e.target.value } })} />
                )}
                {form.audience_type === "cohort" && (
                  <select className="k-input" value={form.audience_filter?.cohort || ""} onChange={(e) => setForm({ ...form, audience_filter: { cohort: e.target.value } })}>
                    <option value="">Select cohort</option>
                    <option value="high_value">High-value</option><option value="churn_risk">Churn risk</option><option value="new">New customers</option><option value="vip">VIP (Platinum/Diamond)</option>
                  </select>
                )}
              </div>
              <textarea className="k-input" placeholder="Message template (use {name} for personalization)" value={form.message_template} onChange={(e) => setForm({ ...form, message_template: e.target.value })} data-testid="message-template-input" />
              <select className="k-input" value={form.coupon_code} onChange={(e) => setForm({ ...form, coupon_code: e.target.value })} data-testid="coupon-select">
                <option value="">No coupon</option>
                {coupons.map((c) => <option key={c.id} value={c.code}>{c.code} · {c.name}</option>)}
              </select>
              <div className="flex justify-end gap-2 mt-2">
                <button className="k-btn k-btn-ghost" onClick={() => setShow(false)}>Cancel</button>
                <button className="k-btn kazo-bg-burgundy" onClick={create} data-testid="campaign-create-btn">Create as draft</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
