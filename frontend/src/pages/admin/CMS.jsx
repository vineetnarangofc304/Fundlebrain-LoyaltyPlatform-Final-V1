import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader } from "./_shared";
import { toast } from "sonner";
import { Save, Image as ImageIcon } from "lucide-react";

export default function CMSPage() {
  const [content, setContent] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => { api.get("/cms/content").then((r) => setContent(r.data)); }, []);

  const upd = (section, key, val) => setContent({ ...content, [section]: { ...content[section], [key]: val } });

  const save = async () => {
    setSaving(true);
    try {
      await api.put("/cms/content", content);
      toast.success("Site content saved");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    } finally { setSaving(false); }
  };

  if (!content) return <div className="p-10 text-neutral-500">Loading…</div>;

  return (
    <div data-testid="cms-page">
      <PageHeader title="Public Site CMS" subtitle="EDIT HOMEPAGE · IMAGES · COPY"
        actions={<button className="k-btn kazo-bg-burgundy" onClick={save} disabled={saving} data-testid="cms-save"><Save className="w-4 h-4" /> {saving ? "Saving…" : "Save changes"}</button>} />
      <div className="p-8 space-y-6 max-w-4xl">
        <Section title="ANNOUNCEMENT BAR">
          <Input label="Top bar text" value={content.home?.topbar_text || ""} onChange={(v) => upd("home", "topbar_text", v)} testid="cms-topbar" />
        </Section>

        <Section title="HERO SECTION">
          <Input label="Eyebrow tag" value={content.home?.hero_eyebrow || ""} onChange={(v) => upd("home", "hero_eyebrow", v)} testid="cms-hero-eyebrow" />
          <div className="grid grid-cols-3 gap-3">
            <Input label="Headline part 1" value={content.home?.hero_headline_1 || ""} onChange={(v) => upd("home", "hero_headline_1", v)} testid="cms-h1" />
            <Input label="Italic accent" value={content.home?.hero_headline_em || ""} onChange={(v) => upd("home", "hero_headline_em", v)} testid="cms-h-em" />
            <Input label="Headline part 2" value={content.home?.hero_headline_2 || ""} onChange={(v) => upd("home", "hero_headline_2", v)} testid="cms-h2" />
          </div>
          <Textarea label="Subtext" value={content.home?.hero_subtext || ""} onChange={(v) => upd("home", "hero_subtext", v)} />
          <ImageField label="Hero image URL" value={content.home?.hero_image_url || ""} onChange={(v) => upd("home", "hero_image_url", v)} testid="cms-hero-img" />
        </Section>

        <Section title="STATS BAR">
          <div className="grid grid-cols-3 gap-3">
            <Input label="Members number" value={content.home?.stats_members || ""} onChange={(v) => upd("home", "stats_members", v)} />
            <Input label="Cities number" value={content.home?.stats_cities || ""} onChange={(v) => upd("home", "stats_cities", v)} />
            <Input label="Stores number" value={content.home?.stats_stores || ""} onChange={(v) => upd("home", "stats_stores", v)} />
          </div>
        </Section>

        <Section title="EDITORIAL VIP SECTION">
          <Input label="Eyebrow" value={content.home?.editorial_eyebrow || ""} onChange={(v) => upd("home", "editorial_eyebrow", v)} />
          <Input label="Headline" value={content.home?.editorial_headline || ""} onChange={(v) => upd("home", "editorial_headline", v)} />
          <Textarea label="Body" value={content.home?.editorial_body || ""} onChange={(v) => upd("home", "editorial_body", v)} />
          <ImageField label="Image URL" value={content.home?.editorial_image_url || ""} onChange={(v) => upd("home", "editorial_image_url", v)} />
        </Section>

        <Section title="FINAL CTA">
          <Input label="Headline" value={content.home?.final_cta_headline || ""} onChange={(v) => upd("home", "final_cta_headline", v)} />
          <Input label="Body" value={content.home?.final_cta_body || ""} onChange={(v) => upd("home", "final_cta_body", v)} />
          <ImageField label="Background image URL" value={content.home?.boutique_image_url || ""} onChange={(v) => upd("home", "boutique_image_url", v)} />
        </Section>

        <Section title="FOOTER">
          <Textarea label="Tagline" value={content.footer?.tagline || ""} onChange={(v) => upd("footer", "tagline", v)} />
          <Input label="Powered by line" value={content.footer?.powered_by || ""} onChange={(v) => upd("footer", "powered_by", v)} />
        </Section>

        <Section title="CUSTOMER SUPPORT INFO">
          <Input label="Email" value={content.support?.email || ""} onChange={(v) => upd("support", "email", v)} />
          <Input label="Phone" value={content.support?.phone || ""} onChange={(v) => upd("support", "phone", v)} />
          <Input label="Phone hours" value={content.support?.phone_hours || ""} onChange={(v) => upd("support", "phone_hours", v)} />
          <Input label="Address" value={content.support?.address || ""} onChange={(v) => upd("support", "address", v)} />
        </Section>
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div className="bg-white border border-black/10 p-5 space-y-3">
      <div className="text-[11px] uppercase tracking-[0.2em] kazo-text-burgundy mb-1">{title}</div>
      {children}
    </div>
  );
}
function Input({ label, value, onChange, testid }) {
  return (
    <div>
      <label className="text-[10px] uppercase tracking-widest text-neutral-500 mb-1.5 block">{label}</label>
      <input className="k-input" value={value} onChange={(e) => onChange(e.target.value)} data-testid={testid} />
    </div>
  );
}
function Textarea({ label, value, onChange }) {
  return (
    <div>
      <label className="text-[10px] uppercase tracking-widest text-neutral-500 mb-1.5 block">{label}</label>
      <textarea rows={3} className="k-input" value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}
function ImageField({ label, value, onChange, testid }) {
  return (
    <div>
      <label className="text-[10px] uppercase tracking-widest text-neutral-500 mb-1.5 block">{label}</label>
      <div className="flex gap-3 items-start">
        <input className="k-input flex-1" value={value} onChange={(e) => onChange(e.target.value)} data-testid={testid} placeholder="https://…" />
        {value && <img src={value} alt="" className="w-20 h-20 object-cover border border-black/10" />}
      </div>
    </div>
  );
}
