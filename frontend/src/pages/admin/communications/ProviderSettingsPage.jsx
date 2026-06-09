/* Karix Provider Settings — editable from frontend. */
import { useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { PageHeader, SectionHeading } from "../_shared";
import { Save, RefreshCw, Eye, EyeOff } from "lucide-react";

const SECTIONS = [
  {
    title: "SMS (Karix Transactional)",
    accent: "indigo",
    fields: [
      { key: "sms_endpoint", label: "Endpoint URL", placeholder: "https://pod2-japi.instaalerts.zone/httpapi/QueryStringReceiver" },
      { key: "sms_api_key", label: "API Key", secret: true },
      { key: "sms_sender_id", label: "Sender ID (DLT registered)", placeholder: "KAZOIN" },
      { key: "sms_dlt_entity_id", label: "DLT Entity ID (Principal Entity ID)" },
      { key: "sms_dlt_template_id", label: "Default DLT Content Template ID (fallback)" },
      { key: "sms_dlt_tm_id", label: "DLT Telemarketer / Chain ID (optional)" },
    ],
  },
  {
    title: "WhatsApp (Karix WABA)",
    accent: "emerald",
    fields: [
      { key: "whatsapp_endpoint", label: "Endpoint URL", placeholder: "https://rcmapi.instaalerts.zone/services/rcm/sendMessage" },
      { key: "whatsapp_from_number", label: "Sender number (without +)", placeholder: "919133325826" },
      { key: "whatsapp_api_key", label: "API Key (Authentication header)", secret: true },
      { key: "whatsapp_version", label: "API Version", placeholder: "v1.0.9" },
    ],
  },
  {
    title: "RCS",
    accent: "amber",
    fields: [
      { key: "rcs_endpoint", label: "Endpoint URL" },
      { key: "rcs_from_number", label: "Sender number" },
      { key: "rcs_api_key", label: "API Key", secret: true },
    ],
  },
];

export default function ProviderSettingsPage() {
  const [cfg, setCfg] = useState(null);
  const [edits, setEdits] = useState({});
  const [reveal, setReveal] = useState({});
  const [saving, setSaving] = useState(false);

  const load = async () => {
    const r = await api.get("/provider-config");
    setCfg(r.data);
    setEdits({});
  };
  useEffect(() => { load(); }, []);

  if (!cfg) return <div className="p-10 text-neutral-500">Loading provider settings…</div>;

  const save = async () => {
    if (Object.keys(edits).length === 0) return;
    setSaving(true);
    try {
      const r = await api.patch("/provider-config", edits);
      setCfg(r.data);
      setEdits({});
      toast.success("Provider settings saved");
    } catch (e) { toast.error(e?.response?.data?.detail || "Save failed"); }
    finally { setSaving(false); }
  };

  return (
    <div data-testid="provider-settings">
      <PageHeader
        title="Provider Settings"
        subtitle="KARIX SMS · WHATSAPP · RCS · API CONFIGURATION"
        actions={
          <>
            <button className="k-btn k-btn-outline k-btn-sm" onClick={load}><RefreshCw className="w-3.5 h-3.5" /> Reload</button>
            <button className="k-btn kazo-bg-burgundy k-btn-sm" onClick={save} disabled={saving || Object.keys(edits).length === 0} data-testid="save-config">
              <Save className="w-3.5 h-3.5" /> {saving ? "Saving…" : `Save (${Object.keys(edits).length})`}
            </button>
          </>
        }
      />

      <div className="p-8 space-y-6">
        <div className="bg-amber-50 border border-amber-200 p-4 text-sm">
          <strong>Note:</strong> Secrets are stored in MongoDB <code className="font-mono text-xs">provider_config</code>.
          Masked display shows only first/last 3 chars. Replace the masked value to update; leave untouched to keep current.
        </div>

        {SECTIONS.map((s) => (
          <div key={s.title} className="chart-card p-5" data-accent={s.accent}>
            <SectionHeading eyebrow="PROVIDER" title={s.title} accent={s.accent} />
            <div className="grid md:grid-cols-2 gap-3">
              {s.fields.map((f) => {
                const live = edits[f.key] !== undefined ? edits[f.key] : (cfg[f.key] || "");
                const isSecret = f.secret && !reveal[f.key];
                return (
                  <label key={f.key} className="text-xs">
                    <div className="flex justify-between items-center mb-1">
                      <span className="text-neutral-500 uppercase tracking-widest text-[10px]">{f.label}</span>
                      {f.secret && (
                        <button
                          onClick={() => setReveal({ ...reveal, [f.key]: !reveal[f.key] })}
                          className="text-[10px] text-neutral-500 hover:text-black flex items-center gap-1"
                          data-testid={`reveal-${f.key}`}
                        >
                          {reveal[f.key] ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                          {reveal[f.key] ? "Hide" : "Show"}
                        </button>
                      )}
                    </div>
                    <input
                      type={isSecret ? "password" : "text"}
                      className="k-input font-mono text-xs"
                      placeholder={f.placeholder || ""}
                      value={live}
                      onChange={(e) => setEdits({ ...edits, [f.key]: e.target.value })}
                      data-testid={`field-${f.key}`}
                    />
                  </label>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
