/* POS Credentials — admin UI to view / create / rotate the x-api-key + merchant_id + customer_key
   that KAZO's eWards-style POS uses to authenticate against our /api/pos/* endpoints. */
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader, SectionHeading } from "./_shared";
import { toast } from "sonner";
import {
  KeyRound, Plus, RotateCw, Copy, EyeOff, Eye, ShieldCheck, Power, X,
} from "lucide-react";

export default function POSCredentialsPage() {
  const [creds, setCreds] = useState([]);
  const [reveal, setReveal] = useState({});
  const [newOpen, setNewOpen] = useState(false);

  const load = async () => {
    try {
      const r = await api.get("/admin/pos-credentials");
      setCreds(r.data.credentials || []);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not load credentials");
    }
  };
  useEffect(() => { load(); }, []);

  const rotate = async (id) => {
    if (!window.confirm("Rotate this api_key? KAZO's POS will need the new key.")) return;
    try {
      await api.post(`/admin/pos-credentials/${id}/rotate`);
      toast.success("Key rotated");
      load();
    } catch (e) { toast.error("Rotate failed"); }
  };
  const deactivate = async (id) => {
    if (!window.confirm("Deactivate this credential? It will stop working immediately.")) return;
    try {
      await api.post(`/admin/pos-credentials/${id}/deactivate`);
      toast.success("Deactivated");
      load();
    } catch (e) { toast.error("Deactivate failed"); }
  };
  const copy = async (text) => {
    try { await navigator.clipboard.writeText(text); toast.success("Copied"); }
    catch (e) { toast.error("Copy failed"); }
  };

  return (
    <div data-testid="pos-credentials-page">
      <PageHeader
        title="POS API Credentials"
        subtitle="x-api-key · merchant_id · customer_key · KAZO POS integration"
        actions={
          <button onClick={() => setNewOpen(true)} className="k-btn kazo-bg-burgundy k-btn-sm" data-testid="pos-cred-new-btn">
            <Plus className="w-3.5 h-3.5" /> New credential
          </button>
        }
      />

      <div className="p-8 space-y-6">
        <div className="chart-card p-5" data-accent="burgundy">
          <SectionHeading
            eyebrow={`${creds.length} TOTAL · ${creds.filter((c) => c.is_active).length} ACTIVE`}
            title="Issued credentials"
            accent="burgundy"
          />
          <div className="text-xs text-neutral-600 mb-4">
            Share <strong>merchant_id</strong>, <strong>customer_key</strong>, and <strong>api_key</strong> with the KAZO POS team.
            They send all three on every <code className="font-mono">/api/pos/*</code> call —
            <strong> x-api-key</strong> goes in the request header; the other two in the JSON body.
          </div>

          <div className="space-y-3">
            {creds.length === 0 ? (
              <div className="py-10 text-center text-neutral-500 text-sm">No credentials yet.</div>
            ) : creds.map((c) => (
              <div key={c.id} className={`p-4 border ${c.is_active ? "border-emerald-200 bg-emerald-50/30" : "border-neutral-200 bg-neutral-50 opacity-70"}`} data-testid={`pos-cred-${c.id}`}>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <KeyRound className="w-4 h-4 text-emerald-700" />
                    <span className="font-display text-lg">{c.label}</span>
                    {c.is_active
                      ? <span className="pill" style={{ background: "#ECFDF5", color: "#047857", border: "1px solid #A7F3D0" }}>ACTIVE</span>
                      : <span className="pill" style={{ background: "#FEF2F2", color: "#B91C1C", border: "1px solid #FECACA" }}>DISABLED</span>}
                  </div>
                  {c.is_active && (
                    <div className="flex gap-2">
                      <button onClick={() => rotate(c.id)} className="k-btn k-btn-ghost k-btn-sm" data-testid={`pos-cred-rotate-${c.id}`}>
                        <RotateCw className="w-3 h-3" /> Rotate
                      </button>
                      <button onClick={() => deactivate(c.id)} className="k-btn k-btn-ghost k-btn-sm text-rose-700" data-testid={`pos-cred-disable-${c.id}`}>
                        <Power className="w-3 h-3" /> Disable
                      </button>
                    </div>
                  )}
                </div>
                <div className="grid md:grid-cols-3 gap-2 text-xs">
                  <CredField label="merchant_id" value={c.merchant_id} onCopy={() => copy(c.merchant_id)} />
                  <CredField label="customer_key" value={c.customer_key} onCopy={() => copy(c.customer_key)} />
                  <CredField label="x-api-key" value={c.api_key} secret hidden={!reveal[c.id]}
                              onToggle={() => setReveal({ ...reveal, [c.id]: !reveal[c.id] })}
                              onCopy={() => copy(c.api_key)} />
                </div>
                {c.note && <div className="mt-2 text-[11px] text-neutral-500 italic">{c.note}</div>}
                <div className="mt-2 text-[10px] text-neutral-500">Created {new Date(c.created_at).toLocaleString()} {c.created_by ? `by ${c.created_by}` : ""}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Quick-reference doc */}
        <div className="chart-card p-5" data-accent="indigo" data-testid="pos-cred-quickref">
          <SectionHeading eyebrow="QUICK REFERENCE" title="How KAZO POS authenticates" accent="indigo" />
          <pre className="bg-neutral-900 text-emerald-200 p-3 font-mono text-[11px] overflow-x-auto whitespace-pre">
{`POST /api/pos/posCustomerCheck
Headers:
  x-api-key: <api_key from above>
  Content-Type: application/json

Body:
{
  "merchant_id": "<merchant_id>",
  "customer_key": "<customer_key>",
  "customer_mobile": "966681235",
  "country_code": "91",
  "bill_amount": "2000"
}`}
          </pre>
          <div className="mt-3 text-xs text-neutral-600">
            All 14 eWards-spec endpoints are mounted under <code className="font-mono">/api/pos/*</code> with the exact same JSON contract.
            See <strong>Live Bill Monitor</strong> + <strong>API Monitor</strong> to watch each call land in real time.
          </div>
        </div>
      </div>

      {newOpen && <NewCredentialModal onClose={() => setNewOpen(false)} onCreated={() => { setNewOpen(false); load(); }} />}
    </div>
  );
}

function CredField({ label, value, onCopy, secret = false, hidden = false, onToggle }) {
  return (
    <div className="bg-white p-2 border border-black/10">
      <div className="text-[10px] uppercase tracking-widest text-neutral-500 mb-1">{label}</div>
      <div className="flex items-center gap-2">
        <code className="font-mono text-[11px] truncate" title={value}>
          {secret && hidden ? "••••••••••••••••••••••••" : value}
        </code>
        <div className="ml-auto flex items-center gap-1">
          {secret && (
            <button onClick={onToggle} className="text-neutral-500 hover:text-neutral-900" title="Toggle">
              {hidden ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
            </button>
          )}
          <button onClick={onCopy} className="text-neutral-500 hover:text-neutral-900" title="Copy">
            <Copy className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}

function NewCredentialModal({ onClose, onCreated }) {
  const [form, setForm] = useState({ label: "", merchant_id: "KAZO_FUNDLE", customer_key: "", note: "" });
  const [busy, setBusy] = useState(false);
  const [created, setCreated] = useState(null);

  const submit = async () => {
    if (!form.label || !form.merchant_id || !form.customer_key) {
      toast.error("Label, merchant_id and customer_key are required");
      return;
    }
    setBusy(true);
    try {
      const r = await api.post("/admin/pos-credentials", form);
      setCreated(r.data);
      toast.success("Credential created");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Create failed");
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white w-full max-w-lg" onClick={(e) => e.stopPropagation()} data-testid="pos-cred-new-modal">
        <div className="p-5 border-b border-black/10 flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.22em] text-burgundy-800">NEW CREDENTIAL</div>
            <h3 className="font-display text-2xl">Issue POS API key</h3>
          </div>
          <button onClick={onClose} className="k-btn k-btn-ghost k-btn-sm"><X className="w-4 h-4" /></button>
        </div>
        {created ? (
          <div className="p-5 space-y-3">
            <div className="text-sm text-emerald-700 font-medium flex items-center gap-2"><ShieldCheck className="w-4 h-4" /> Credential created — copy now, the key won't be hidden later but can be rotated.</div>
            <CredField label="merchant_id" value={created.merchant_id} onCopy={async () => { await navigator.clipboard.writeText(created.merchant_id); toast.success("Copied"); }} />
            <CredField label="customer_key" value={created.customer_key} onCopy={async () => { await navigator.clipboard.writeText(created.customer_key); toast.success("Copied"); }} />
            <CredField label="x-api-key" value={created.api_key} onCopy={async () => { await navigator.clipboard.writeText(created.api_key); toast.success("Copied"); }} />
            <button onClick={onCreated} className="k-btn kazo-bg-burgundy w-full">Done</button>
          </div>
        ) : (
          <div className="p-5 space-y-3 text-xs">
            <Input label="Label *" value={form.label} onChange={(v) => setForm({ ...form, label: v })} placeholder="e.g. kazo_phoenix_mum01" testid="cred-label" />
            <Input label="merchant_id *" value={form.merchant_id} onChange={(v) => setForm({ ...form, merchant_id: v })} placeholder="KAZO_FUNDLE" testid="cred-merchant" />
            <Input label="customer_key *" value={form.customer_key} onChange={(v) => setForm({ ...form, customer_key: v })} placeholder="kazo_phoenix_mum01" testid="cred-ckey" />
            <Input label="Note (optional)" value={form.note} onChange={(v) => setForm({ ...form, note: v })} placeholder="For Phoenix Marketcity outlet" testid="cred-note" />
            <div className="pt-3 flex justify-end gap-2">
              <button onClick={onClose} className="k-btn k-btn-ghost">Cancel</button>
              <button onClick={submit} disabled={busy} className="k-btn kazo-bg-burgundy" data-testid="cred-submit">Create</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Input({ label, value, onChange, placeholder, testid }) {
  return (
    <label className="block">
      <div className="text-neutral-500 uppercase tracking-widest text-[10px] mb-1">{label}</div>
      <input className="k-input" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} data-testid={testid} />
    </label>
  );
}
