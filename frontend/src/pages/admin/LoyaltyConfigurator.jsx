/* Loyalty Configurator v2 — full-featured logic editor.

   Matches Fundle Logic Configuration + extends:
     - Earn mode (Points per ₹ | % of Spend) toggle
     - Custom tier names + max amount + tier type + active flag
     - Per-tier: bonuses · coupon discount · free shipping · point expiry override · visit threshold · color
     - Tier reset cadence (never / annual / rolling 12m)
     - Category & Store-type earn multipliers
     - Festival boosters (date-range earn multiplier)
     - Live point earn simulator
     - Compliance toggles (OTP, stacking, min bill, returns)
*/
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader } from "./_shared";
import { toast } from "sonner";
import { fmtNum, fmtMoney2 } from "@/lib/format";
import { Plus, Trash2, Power, Calculator, Sparkles, Coins, Calendar, Tag, Building2, ShieldCheck, RefreshCcw } from "lucide-react";
import RetierSection from "./_retier_section";

const TIER_TYPES = [
  { value: "entry", label: "Entry" },
  { value: "standard", label: "Standard" },
  { value: "premium", label: "Premium" },
  { value: "vip", label: "VIP" },
  { value: "partner", label: "Partner" },
];

export default function LoyaltyConfigurator() {
  const [cfg, setCfg] = useState(null);
  const [stats, setStats] = useState([]);
  const [saving, setSaving] = useState(false);

  const load = () =>
    Promise.all([api.get("/loyalty/config"), api.get("/loyalty/tier-stats")])
      .then(([c, s]) => { setCfg(c.data); setStats(s.data); });
  useEffect(() => { load(); }, []);

  const save = async () => {
    setSaving(true);
    try {
      await api.put("/loyalty/config", cfg);
      toast.success("Loyalty configuration updated");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Update failed");
    } finally { setSaving(false); }
  };

  if (!cfg) return <div className="p-10 text-neutral-500">Loading…</div>;

  const setField = (k, v) => setCfg({ ...cfg, [k]: v });
  const updTier = (i, k, v) => {
    const arr = [...cfg.tier_rules];
    arr[i] = { ...arr[i], [k]: v };
    setCfg({ ...cfg, tier_rules: arr });
  };
  const removeTier = async (slug) => {
    try {
      await api.delete(`/loyalty/tiers/${slug}`);
      setCfg((c) => ({ ...c, tier_rules: c.tier_rules.filter((t) => t.tier !== slug) }));
      toast.success(`Tier "${slug}" deleted`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Delete failed");
    }
  };

  return (
    <div data-testid="loyalty-configurator">
      <PageHeader
        title="Loyalty Logic Editor"
        subtitle="EARN · TIERS · BONUSES · FESTIVAL BOOSTERS · COMPLIANCE"
        actions={<button className="k-btn kazo-bg-burgundy text-white" onClick={save} disabled={saving} data-testid="save-loyalty-btn">{saving ? "Saving…" : "Save Changes"}</button>}
      />
      <div className="p-8 space-y-6">

        {/* Distribution */}
        <SectionCard title="CURRENT DISTRIBUTION" subtitle="Live customer counts per tier">
          <div className="grid md:grid-cols-2 lg:grid-cols-5 gap-3">
            {stats.length === 0 && <div className="col-span-full text-sm text-neutral-500">No tiers populated yet.</div>}
            {stats.map((s) => (
              <div key={s.tier} className="border border-black/10 p-4">
                <div className="text-[10px] uppercase tracking-[0.22em] text-neutral-500">{s.tier?.toUpperCase()}</div>
                <div className="font-display kpi-value mt-2">{fmtNum(s.count)}</div>
                <div className="text-xs text-neutral-500 mt-1">{fmtMoney2(s.total_spend)} lifetime</div>
              </div>
            ))}
          </div>
        </SectionCard>

        {/* Earn engine */}
        <SectionCard title="EARN ENGINE" subtitle="How customers accumulate points" icon={Coins}>
          <div className="grid lg:grid-cols-3 gap-6">
            <div>
              <Label>Earn mode</Label>
              <div className="flex border border-black/15" data-testid="cfg-earn-mode">
                <button
                  onClick={() => setField("earn_mode", "points_per_spend")}
                  className={`flex-1 py-2 text-sm ${cfg.earn_mode === "points_per_spend" ? "kazo-bg-burgundy text-white" : "bg-white"}`}
                  data-testid="cfg-mode-pps"
                >Points per ₹</button>
                <button
                  onClick={() => setField("earn_mode", "percent_of_spend")}
                  className={`flex-1 py-2 text-sm ${cfg.earn_mode === "percent_of_spend" ? "kazo-bg-burgundy text-white" : "bg-white"}`}
                  data-testid="cfg-mode-pos"
                >% of Spend</button>
              </div>
              <p className="text-xs text-neutral-500 mt-2">
                {cfg.earn_mode === "points_per_spend"
                  ? "Each rupee spent earns N points (tier multiplier applies)."
                  : "Each bill earns N% of its value as points (tier multiplier applies)."}
              </p>
              <p className="text-xs text-amber-700 mt-1" data-testid="cfg-tier-driven-hint">
                💡 Tier-driven: leave the rate at <b>0</b> and each tier's <b>multiplier</b> becomes
                its <b>% of the bill</b> (e.g. mult 2 → 2%, 3 → 3%). No Earn Engine value needed.
              </p>
            </div>
            {cfg.earn_mode === "points_per_spend" ? (
              <NumField label="Points per ₹" value={cfg.earn_ratio} step="0.05"
                        onChange={(v) => setField("earn_ratio", parseFloat(v) || 0)}
                        testid="cfg-earn-ratio" />
            ) : (
              <NumField label="% of Spend earned (e.g. 5 = 5%)" value={cfg.percent_of_spend} step="0.5"
                        onChange={(v) => setField("percent_of_spend", parseFloat(v) || 0)}
                        testid="cfg-percent-of-spend" />
            )}
            <NumField label="Min bill for earn (₹)" value={cfg.min_bill_for_earn} step="50"
                      onChange={(v) => setField("min_bill_for_earn", parseFloat(v) || 0)}
                      testid="cfg-min-bill" />
          </div>
        </SectionCard>

        {/* Tier Management */}
        <SectionCard title="TIER MANAGEMENT" subtitle="Define progression bands + per-tier perks" icon={Sparkles}
                      actions={<AddTierButton onAdd={(t) => setCfg({ ...cfg, tier_rules: [...cfg.tier_rules, t] })} existing={cfg.tier_rules} />}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="tier-table">
              <thead className="border-b border-black/10 text-left">
                <tr>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Tier</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Display Name</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Min ₹</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Max ₹</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Mult.</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Type</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Welcome</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">B&apos;day</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Anniv.</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Coupon %</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Ship ≥ ₹</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Expiry (d)</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Visits</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Active</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500"></th>
                </tr>
              </thead>
              <tbody>
                {cfg.tier_rules.map((t, i) => (
                  <tr key={t.tier} className={`border-b border-black/5 ${t.is_active === false ? "opacity-50" : ""}`}>
                    <td className="py-2 px-2 font-mono">
                      <span className="px-2 py-0.5 text-[11px] uppercase rounded" style={{ background: t.color || "#e5e7eb", color: "#111" }}>{t.tier}</span>
                    </td>
                    <td className="py-2 px-2">
                      <input className="k-input k-input-sm w-28" value={t.name || ""} placeholder={t.tier} onChange={(e) => updTier(i, "name", e.target.value)} data-testid={`tier-${t.tier}-name`} />
                    </td>
                    <td className="py-2 px-2">
                      <input type="number" className="k-input k-input-sm w-24 text-right font-mono" value={t.min_lifetime_spend ?? 0} onChange={(e) => updTier(i, "min_lifetime_spend", parseFloat(e.target.value) || 0)} data-testid={`tier-${t.tier}-min`} />
                    </td>
                    <td className="py-2 px-2">
                      <input type="number" className="k-input k-input-sm w-24 text-right font-mono" value={t.max_lifetime_spend ?? ""} placeholder="∞" onChange={(e) => updTier(i, "max_lifetime_spend", e.target.value === "" ? null : parseFloat(e.target.value))} data-testid={`tier-${t.tier}-max`} />
                    </td>
                    <td className="py-2 px-2">
                      <input type="number" step="0.05" className="k-input k-input-sm w-16 text-right font-mono" value={t.earn_multiplier ?? 1} onChange={(e) => updTier(i, "earn_multiplier", parseFloat(e.target.value) || 0)} data-testid={`tier-${t.tier}-mult`} />
                    </td>
                    <td className="py-2 px-2">
                      <select className="k-input k-input-sm w-24" value={t.tier_type || "standard"} onChange={(e) => updTier(i, "tier_type", e.target.value)} data-testid={`tier-${t.tier}-type`}>
                        {TIER_TYPES.map((tt) => <option key={tt.value} value={tt.value}>{tt.label}</option>)}
                      </select>
                    </td>
                    <td className="py-2 px-2"><MiniNum value={t.welcome_bonus ?? 0} onChange={(v) => updTier(i, "welcome_bonus", v)} /></td>
                    <td className="py-2 px-2"><MiniNum value={t.birthday_bonus ?? 0} onChange={(v) => updTier(i, "birthday_bonus", v)} /></td>
                    <td className="py-2 px-2"><MiniNum value={t.anniversary_bonus ?? 0} onChange={(v) => updTier(i, "anniversary_bonus", v)} /></td>
                    <td className="py-2 px-2"><MiniNum value={t.coupon_discount_pct ?? 0} onChange={(v) => updTier(i, "coupon_discount_pct", v)} step="0.5" /></td>
                    <td className="py-2 px-2"><MiniNum value={t.free_shipping_min_bill ?? ""} placeholder="—" onChange={(v) => updTier(i, "free_shipping_min_bill", v === "" ? null : v)} /></td>
                    <td className="py-2 px-2"><MiniNum value={t.point_expiry_override_days ?? ""} placeholder="—" onChange={(v) => updTier(i, "point_expiry_override_days", v === "" ? null : v)} /></td>
                    <td className="py-2 px-2"><MiniNum value={t.visit_threshold ?? ""} placeholder="—" onChange={(v) => updTier(i, "visit_threshold", v === "" ? null : v)} /></td>
                    <td className="py-2 px-2 text-center">
                      <button onClick={() => updTier(i, "is_active", !(t.is_active !== false))} className={`text-xs px-2 py-0.5 ${t.is_active === false ? "bg-neutral-100 text-neutral-500" : "bg-emerald-100 text-emerald-700"}`} data-testid={`tier-${t.tier}-active`}>
                        {t.is_active === false ? "Off" : "On"}
                      </button>
                    </td>
                    <td className="py-2 px-2">
                      <button onClick={() => { if (window.confirm(`Delete tier "${t.tier}"?`)) removeTier(t.tier); }} className="text-rose-600 hover:bg-rose-50 p-1" data-testid={`tier-${t.tier}-delete`}>
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-neutral-500 mt-3">
            Mult. = earn multiplier · Welcome / B&apos;day / Anniv. = one-shot bonuses · Coupon % = auto applied on every bill · Ship ≥ ₹ = free-shipping threshold · Expiry (d) = override of global point expiry · Visits = alternative tier-promotion path
          </p>
        </SectionCard>

        {/* Update old data — re-tier pre-POS customers from configured ranges */}
        <RetierSection />

        {/* Slab-wise tier-upgrade bonuses */}
        <SectionCard title="TIER UPGRADE BONUSES (SLAB-WISE)" subtitle="One-time bonus points awarded when a customer crosses UP into each tier (slab)" icon={Sparkles}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-black/10 text-left">
                <tr>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Tier (Slab)</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Spend Band</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Upgrade Bonus (pts)</th>
                </tr>
              </thead>
              <tbody>
                {cfg.tier_rules.map((t, i) => (
                  <tr key={t.tier} className={`border-b border-black/5 ${t.is_active === false ? "opacity-50" : ""}`}>
                    <td className="py-2 px-2 font-mono">
                      <span className="px-2 py-0.5 text-[11px] uppercase rounded" style={{ background: t.color || "#e5e7eb", color: "#111" }}>{t.name || t.tier}</span>
                    </td>
                    <td className="py-2 px-2 text-neutral-600 font-mono text-xs">
                      ₹{Number(t.min_lifetime_spend ?? 0).toLocaleString("en-IN")} – {t.max_lifetime_spend != null ? `₹${Number(t.max_lifetime_spend).toLocaleString("en-IN")}` : "∞"}
                    </td>
                    <td className="py-2 px-2">
                      <input type="number" min="0" className="k-input k-input-sm w-28 text-right font-mono" value={t.upgrade_bonus ?? 0} onChange={(e) => updTier(i, "upgrade_bonus", parseInt(e.target.value) || 0)} data-testid={`tier-${t.tier}-upgrade-bonus`} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-neutral-500 mt-3">
            Awarded once when a bill pushes a customer&apos;s lifetime spend past this slab&apos;s minimum and promotes them into this tier. The entry tier (lowest slab) is usually 0.
          </p>
        </SectionCard>


        {/* Tier reset cadence */}
        <SectionCard title="TIER RESET CADENCE" subtitle="When do customers get re-evaluated against tier bands?" icon={RefreshCcw}>
          <div className="grid md:grid-cols-3 gap-4">
            <div>
              <Label>Cadence</Label>
              <div className="flex flex-col gap-2 mt-1">
                {[
                  { v: "never", l: "Never (lifetime tier)" },
                  { v: "annual", l: "Annual (calendar / anchor date)" },
                  { v: "rolling_12m", l: "Rolling 12 months" },
                ].map((opt) => (
                  <label key={opt.v} className="flex items-center gap-2 text-sm cursor-pointer">
                    <input type="radio" name="reset" checked={cfg.tier_reset_cadence === opt.v} onChange={() => setField("tier_reset_cadence", opt.v)} data-testid={`reset-${opt.v}`} />
                    {opt.l}
                  </label>
                ))}
              </div>
            </div>
            {cfg.tier_reset_cadence === "annual" && (
              <div>
                <Label>Anchor date (MM-DD)</Label>
                <input className="k-input w-32" value={cfg.tier_reset_anchor_date || "01-01"} onChange={(e) => setField("tier_reset_anchor_date", e.target.value)} data-testid="reset-anchor" />
                <p className="text-xs text-neutral-500 mt-1">e.g. 04-01 = financial year</p>
              </div>
            )}
          </div>
        </SectionCard>

        {/* Multipliers */}
        <SectionCard title="EARN MULTIPLIERS" subtitle="Category & Store-type earn boosts (stack on top of tier multiplier)" icon={Tag}>
          <div className="grid lg:grid-cols-2 gap-8">
            <MultiplierEditor
              label="Category multipliers"
              data={cfg.category_multipliers || {}}
              setData={(d) => setField("category_multipliers", d)}
              placeholderKey="Kurtas, Sarees, etc."
              testid="cat-mult"
            />
            <MultiplierEditor
              label="Store-type multipliers"
              data={cfg.store_type_multipliers || {}}
              setData={(d) => setField("store_type_multipliers", d)}
              placeholderKey="online, offline, marketplace"
              testid="store-mult"
            />
          </div>
        </SectionCard>

        {/* Festival boosters */}
        <SectionCard title="FESTIVAL BOOSTERS" subtitle="Date-range earn multipliers — Diwali, Republic Day, anniversaries" icon={Calendar}
                      actions={<AddFestivalBooster onAdd={() => load()} />}>
          {(cfg.festival_boosters || []).length === 0 ? (
            <div className="text-sm text-neutral-500 py-4 text-center">No active boosters. Click &quot;Add booster&quot; to launch one.</div>
          ) : (
            <table className="w-full text-sm" data-testid="festival-table">
              <thead className="border-b border-black/10 text-left">
                <tr>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Name</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Start</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">End</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Multiplier</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">Applies to</th>
                  <th className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500"></th>
                </tr>
              </thead>
              <tbody>
                {cfg.festival_boosters.map((b) => (
                  <tr key={b.id} className="border-b border-black/5">
                    <td className="py-2 px-2 font-medium">{b.name}</td>
                    <td className="py-2 px-2 font-mono text-xs">{b.start_date}</td>
                    <td className="py-2 px-2 font-mono text-xs">{b.end_date}</td>
                    <td className="py-2 px-2 font-mono">{b.multiplier}×</td>
                    <td className="py-2 px-2 text-xs">{b.applies_to}</td>
                    <td className="py-2 px-2">
                      <button onClick={async () => {
                        await api.delete(`/loyalty/festival-boosters/${b.id}`);
                        load();
                      }} className="text-rose-600 hover:bg-rose-50 p-1" data-testid={`fb-del-${b.id}`}>
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </SectionCard>

        {/* Global bonuses */}
        <SectionCard title="GLOBAL BONUSES" subtitle="Fallback values used when a tier doesn't override" icon={Sparkles}>
          <div className="grid lg:grid-cols-4 md:grid-cols-2 gap-4">
            <NumField label="Welcome (pts)" value={cfg.welcome_bonus} onChange={(v) => setField("welcome_bonus", parseInt(v) || 0)} testid="cfg-welcome" />
            <NumField label="Birthday (pts)" value={cfg.birthday_bonus} onChange={(v) => setField("birthday_bonus", parseInt(v) || 0)} testid="cfg-birthday" />
            <NumField label="Anniversary (pts)" value={cfg.anniversary_bonus} onChange={(v) => setField("anniversary_bonus", parseInt(v) || 0)} testid="cfg-anniversary" />
            <NumField label="Referrer (pts)" value={cfg.referral_points_referrer} onChange={(v) => setField("referral_points_referrer", parseInt(v) || 0)} testid="cfg-ref-er" />
            <NumField label="Referee (pts)" value={cfg.referral_points_referee} onChange={(v) => setField("referral_points_referee", parseInt(v) || 0)} testid="cfg-ref-ee" />
          </div>
        </SectionCard>

        {/* Redeem engine */}
        <SectionCard title="REDEEM ENGINE" subtitle="How points convert back to value" icon={Coins}>
          <div className="grid lg:grid-cols-4 md:grid-cols-2 gap-4">
            <NumField label="₹ value per point" value={cfg.burn_ratio} step="0.05" onChange={(v) => setField("burn_ratio", parseFloat(v) || 0)} testid="cfg-burn" />
            <NumField label="Min redeem points" value={cfg.min_redeem_points} onChange={(v) => setField("min_redeem_points", parseInt(v) || 0)} testid="cfg-min-redeem" />
            <NumField label="Max redeem % of bill" value={cfg.max_redeem_pct_of_bill} step="5" onChange={(v) => setField("max_redeem_pct_of_bill", parseFloat(v) || 0)} testid="cfg-max-redeem-pct" />
            <NumField label="Point expiry (days, global)" value={cfg.point_expiry_days} onChange={(v) => setField("point_expiry_days", parseInt(v) || 0)} testid="cfg-expiry" />
          </div>
        </SectionCard>

        {/* Earn & Burn control */}
        <EarnBurnControl cfg={cfg} reload={load} />

        {/* Compliance */}
        <SectionCard title="COMPLIANCE & RESTRICTIONS" subtitle="Operational guards" icon={ShieldCheck}>
          <div className="grid lg:grid-cols-2 md:grid-cols-2 gap-4">
            <Toggle label="OTP required for redeem" value={cfg.require_otp_for_redeem} onChange={(v) => setField("require_otp_for_redeem", v)} testid="cfg-otp" />
            <Toggle label="Allow coupon stacking" value={cfg.allow_coupon_stacking} onChange={(v) => setField("allow_coupon_stacking", v)} testid="cfg-stacking" />
            <Toggle label="Block earn on returns" value={cfg.block_earn_on_returns} onChange={(v) => setField("block_earn_on_returns", v)} testid="cfg-returns" />
          </div>
        </SectionCard>

        {/* Simulator */}
        <Simulator cfg={cfg} />
      </div>
    </div>
  );
}

// ============= Sub-components =============

function SectionCard({ title, subtitle, children, actions, icon: Icon }) {
  return (
    <div className="bg-white border border-black/10 p-5">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="flex items-center gap-3">
          {Icon && <div className="w-8 h-8 bg-neutral-100 flex items-center justify-center"><Icon className="w-4 h-4" /></div>}
          <div>
            <div className="font-display text-base">{title}</div>
            {subtitle && <div className="text-xs text-neutral-500">{subtitle}</div>}
          </div>
        </div>
        {actions}
      </div>
      {children}
    </div>
  );
}

function Label({ children }) {
  return <label className="text-[10px] uppercase tracking-[0.22em] text-neutral-500 mb-1.5 block">{children}</label>;
}

function NumField({ label, value, onChange, step = "1", testid }) {
  return (
    <div>
      <Label>{label}</Label>
      <input type="number" step={step} className="k-input w-full" value={value ?? 0} onChange={(e) => onChange(e.target.value)} data-testid={testid} />
    </div>
  );
}

function MiniNum({ value, onChange, placeholder = "", step = "1" }) {
  return (
    <input type="number" step={step} className="k-input k-input-sm w-16 text-right font-mono" value={value ?? ""} placeholder={placeholder}
      onChange={(e) => onChange(e.target.value === "" ? "" : (parseFloat(e.target.value) || 0))} />
  );
}

function Toggle({ label, value, onChange, testid }) {
  return (
    <div>
      <Label>{label}</Label>
      <button type="button" onClick={() => onChange(!value)} className={`flex items-center gap-2 px-3 py-2 border ${value ? "kazo-bg-burgundy text-white border-transparent" : "border-black/20 bg-white"}`} data-testid={testid}>
        {value ? "Enabled" : "Disabled"}
      </button>
    </div>
  );
}

function MultiplierEditor({ label, data, setData, placeholderKey, testid }) {
  const [newKey, setNewKey] = useState("");
  const [newVal, setNewVal] = useState("1.5");
  const entries = Object.entries(data || {});
  return (
    <div>
      <Label>{label}</Label>
      <div className="border border-black/10">
        {entries.length === 0 && <div className="text-sm text-neutral-500 p-3 text-center">No multipliers yet.</div>}
        {entries.map(([k, v]) => (
          <div key={k} className="flex items-center gap-2 px-3 py-2 border-b border-black/5">
            <span className="flex-1 text-sm font-mono">{k}</span>
            <input type="number" step="0.05" className="k-input k-input-sm w-20 text-right font-mono" value={v}
              onChange={(e) => setData({ ...data, [k]: parseFloat(e.target.value) || 1 })} data-testid={`${testid}-val-${k}`} />
            <span className="text-xs text-neutral-500">×</span>
            <button onClick={() => { const nd = { ...data }; delete nd[k]; setData(nd); }} className="text-rose-600 hover:bg-rose-50 p-1" data-testid={`${testid}-del-${k}`}>
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
        <div className="flex items-center gap-2 px-3 py-2 bg-neutral-50">
          <input className="k-input k-input-sm flex-1" placeholder={placeholderKey} value={newKey} onChange={(e) => setNewKey(e.target.value)} data-testid={`${testid}-newkey`} />
          <input type="number" step="0.05" className="k-input k-input-sm w-20 text-right font-mono" value={newVal} onChange={(e) => setNewVal(e.target.value)} />
          <button
            onClick={() => {
              if (!newKey.trim()) return;
              setData({ ...data, [newKey.trim()]: parseFloat(newVal) || 1 });
              setNewKey(""); setNewVal("1.5");
            }}
            disabled={!newKey.trim()}
            className="k-btn kazo-bg-burgundy text-white k-btn-sm disabled:opacity-30"
            data-testid={`${testid}-add`}
          >
            <Plus className="w-3 h-3" /> Add
          </button>
        </div>
      </div>
    </div>
  );
}

function AddTierButton({ onAdd, existing }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ tier: "", name: "", min_lifetime_spend: 0, max_lifetime_spend: "", earn_multiplier: 1, welcome_bonus: 0, birthday_bonus: 0, anniversary_bonus: 0, tier_type: "standard", color: "", coupon_discount_pct: 0, free_shipping_min_bill: "", point_expiry_override_days: "" });
  if (!open) return <button onClick={() => setOpen(true)} className="k-btn k-btn-outline" data-testid="add-tier-btn"><Plus className="w-3.5 h-3.5" /> Add Tier</button>;
  const submit = async () => {
    if (!form.tier.trim()) return toast.error("Tier slug required");
    try {
      const payload = { ...form };
      ["max_lifetime_spend", "free_shipping_min_bill", "point_expiry_override_days"].forEach((k) => {
        if (payload[k] === "" || payload[k] === null) delete payload[k];
        else payload[k] = parseFloat(payload[k]);
      });
      const r = await api.post("/loyalty/tiers", payload);
      onAdd?.(r.data.tier);
      toast.success(`Tier "${form.name || form.tier}" added`);
      setOpen(false);
      window.location.reload(); // simplest way to reload tier_stats too
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to add tier");
    }
  };
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white shadow-2xl max-w-2xl w-full p-6 border border-black/10" data-testid="add-tier-modal">
        <h3 className="font-display text-xl mb-3">Add new tier</h3>
        <div className="grid md:grid-cols-2 gap-3">
          <Mini label="Slug (e.g. founders)" v={form.tier} onChange={(v) => setForm({ ...form, tier: v.toLowerCase() })} testid="newtier-slug" />
          <Mini label="Display name" v={form.name} onChange={(v) => setForm({ ...form, name: v })} testid="newtier-name" />
          <Mini label="Min ₹ spend" v={form.min_lifetime_spend} type="number" onChange={(v) => setForm({ ...form, min_lifetime_spend: parseFloat(v) || 0 })} />
          <Mini label="Max ₹ spend (blank = ∞)" v={form.max_lifetime_spend} type="number" onChange={(v) => setForm({ ...form, max_lifetime_spend: v })} />
          <Mini label="Earn multiplier" v={form.earn_multiplier} type="number" onChange={(v) => setForm({ ...form, earn_multiplier: parseFloat(v) || 1 })} />
          <div>
            <Label>Tier type</Label>
            <select className="k-input w-full" value={form.tier_type} onChange={(e) => setForm({ ...form, tier_type: e.target.value })}>
              {TIER_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
          <Mini label="Welcome bonus" v={form.welcome_bonus} type="number" onChange={(v) => setForm({ ...form, welcome_bonus: parseInt(v) || 0 })} />
          <Mini label="Birthday bonus" v={form.birthday_bonus} type="number" onChange={(v) => setForm({ ...form, birthday_bonus: parseInt(v) || 0 })} />
          <Mini label="Anniversary bonus" v={form.anniversary_bonus} type="number" onChange={(v) => setForm({ ...form, anniversary_bonus: parseInt(v) || 0 })} />
          <Mini label="Color (hex)" v={form.color} onChange={(v) => setForm({ ...form, color: v })} />
          <Mini label="Auto coupon %" v={form.coupon_discount_pct} type="number" onChange={(v) => setForm({ ...form, coupon_discount_pct: parseFloat(v) || 0 })} />
          <Mini label="Free shipping ≥ ₹" v={form.free_shipping_min_bill} type="number" onChange={(v) => setForm({ ...form, free_shipping_min_bill: v })} />
          <Mini label="Point expiry override (d)" v={form.point_expiry_override_days} type="number" onChange={(v) => setForm({ ...form, point_expiry_override_days: v })} />
        </div>
        <div className="flex justify-end gap-2 mt-4">
          <button onClick={() => setOpen(false)} className="k-btn k-btn-outline" data-testid="newtier-cancel">Cancel</button>
          <button onClick={submit} className="k-btn kazo-bg-burgundy text-white" data-testid="newtier-submit">Add Tier</button>
        </div>
      </div>
    </div>
  );
}

function Mini({ label, v, onChange, type = "text", testid }) {
  return (
    <div>
      <Label>{label}</Label>
      <input type={type} className="k-input w-full" value={v ?? ""} onChange={(e) => onChange(e.target.value)} data-testid={testid} />
    </div>
  );
}

function AddFestivalBooster({ onAdd }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", start_date: "", end_date: "", multiplier: 2.0, applies_to: "all" });
  if (!open) return <button onClick={() => setOpen(true)} className="k-btn k-btn-outline" data-testid="add-booster-btn"><Plus className="w-3.5 h-3.5" /> Add Booster</button>;
  const submit = async () => {
    if (!form.name || !form.start_date || !form.end_date) return toast.error("All fields required");
    try {
      await api.post("/loyalty/festival-boosters", form);
      toast.success("Booster added");
      setOpen(false);
      onAdd?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white shadow-2xl max-w-lg w-full p-6 border border-black/10" data-testid="booster-modal">
        <h3 className="font-display text-xl mb-3">Add festival booster</h3>
        <div className="grid grid-cols-2 gap-3">
          <Mini label="Name (Diwali, Republic Day)" v={form.name} onChange={(v) => setForm({ ...form, name: v })} testid="newfb-name" />
          <Mini label="Multiplier" v={form.multiplier} type="number" onChange={(v) => setForm({ ...form, multiplier: parseFloat(v) || 1 })} />
          <Mini label="Start date" v={form.start_date} type="date" onChange={(v) => setForm({ ...form, start_date: v })} />
          <Mini label="End date" v={form.end_date} type="date" onChange={(v) => setForm({ ...form, end_date: v })} />
          <div className="col-span-2">
            <Label>Applies to</Label>
            <select className="k-input w-full" value={form.applies_to} onChange={(e) => setForm({ ...form, applies_to: e.target.value })}>
              <option value="all">All customers</option>
              <option value="tier:silver">Silver tier only</option>
              <option value="tier:gold">Gold tier only</option>
              <option value="tier:platinum">Platinum tier only</option>
              <option value="tier:diamond">Diamond tier only</option>
            </select>
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-4">
          <button onClick={() => setOpen(false)} className="k-btn k-btn-outline">Cancel</button>
          <button onClick={submit} className="k-btn kazo-bg-burgundy text-white" data-testid="newfb-submit">Add Booster</button>
        </div>
      </div>
    </div>
  );
}

// ============= Earn & Burn control =============
function EarnBurnControl({ cfg, reload }) {
  const [busy, setBusy] = useState(false);
  const pauses = cfg.earn_burn_pauses || [];

  const setMaster = async (kind, val) => {
    setBusy(true);
    try {
      await api.put("/loyalty/earn-burn-control", { [`${kind}_enabled`]: val });
      toast.success(`${kind === "earn" ? "Earning" : "Redemption"} ${val ? "resumed" : "stopped"}`);
      reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    } finally { setBusy(false); }
  };

  const togglePause = async (id) => {
    try { await api.patch(`/loyalty/pauses/${id}/toggle`); reload(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };
  const delPause = async (id) => {
    try { await api.delete(`/loyalty/pauses/${id}`); toast.success("Pause window removed"); reload(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  return (
    <SectionCard
      title="EARN & BURN CONTROL"
      subtitle="Turn points earning / redemption on or off — instantly, or for scheduled date ranges (blackout periods)"
      icon={Power}
      actions={<AddPauseWindow onAdd={reload} />}
    >
      <div className="grid md:grid-cols-2 gap-4 mb-5">
        <MasterSwitch label="Earning of points" enabled={cfg.earn_enabled !== false} busy={busy}
                      onToggle={(v) => setMaster("earn", v)} testid="ebc-earn-master" />
        <MasterSwitch label="Redemption (burning) of points" enabled={cfg.burn_enabled !== false} busy={busy}
                      onToggle={(v) => setMaster("burn", v)} testid="ebc-burn-master" />
      </div>

      <Label>Scheduled pause windows (blackout dates)</Label>
      {pauses.length === 0 ? (
        <div className="text-sm text-neutral-500 py-3">No scheduled pause windows. A bill dated inside an active window earns no points; redemptions are blocked during it.</div>
      ) : (
        <table className="w-full text-sm mt-2" data-testid="pauses-table">
          <thead className="border-b border-black/10 text-left">
            <tr>
              {["Label", "Start", "End", "Pauses", "Status", ""].map((h) => (
                <th key={h} className="py-2 px-2 text-[10px] uppercase tracking-widest text-neutral-500">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pauses.map((p) => (
              <tr key={p.id} className={`border-b border-black/5 ${p.active === false ? "opacity-50" : ""}`} data-testid={`pause-row-${p.id}`}>
                <td className="py-2 px-2 font-medium">{p.label || "—"}</td>
                <td className="py-2 px-2 font-mono text-xs">{p.start_date}</td>
                <td className="py-2 px-2 font-mono text-xs">{p.end_date}</td>
                <td className="py-2 px-2 text-xs">
                  {p.pause_earn && <span className="pill pill-warning mr-1">Earn</span>}
                  {p.pause_burn && <span className="pill" style={{ background: "#E0E7FF", color: "#3730A3", border: "1px solid #C7D2FE" }}>Burn</span>}
                </td>
                <td className="py-2 px-2">
                  <button onClick={() => togglePause(p.id)} className={`text-xs px-2 py-1 border ${p.active === false ? "border-neutral-300 text-neutral-500" : "border-emerald-300 text-emerald-700 bg-emerald-50"}`} data-testid={`pause-toggle-${p.id}`}>
                    {p.active === false ? "Inactive" : "Active"}
                  </button>
                </td>
                <td className="py-2 px-2">
                  <button onClick={() => delPause(p.id)} className="text-rose-600 hover:bg-rose-50 p-1" data-testid={`pause-del-${p.id}`}>
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </SectionCard>
  );
}

function MasterSwitch({ label, enabled, onToggle, busy, testid }) {
  return (
    <div className={`border p-4 flex items-center justify-between ${enabled ? "border-emerald-200 bg-emerald-50/40" : "border-rose-200 bg-rose-50/40"}`}>
      <div>
        <div className="font-medium text-sm">{label}</div>
        <div className={`text-xs ${enabled ? "text-emerald-700" : "text-rose-700"}`} data-testid={`${testid}-state`}>
          {enabled ? "Currently ACTIVE" : "Currently STOPPED"}
        </div>
      </div>
      <button type="button" disabled={busy} onClick={() => onToggle(!enabled)}
              className={`k-btn ${enabled ? "k-btn-outline" : "kazo-bg-burgundy text-white"}`} data-testid={testid}>
        {enabled ? "Stop" : "Start"}
      </button>
    </div>
  );
}

function AddPauseWindow({ onAdd }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ label: "", start_date: "", end_date: "", pause_earn: true, pause_burn: false });
  if (!open) return <button onClick={() => setOpen(true)} className="k-btn k-btn-outline" data-testid="add-pause-btn"><Plus className="w-3.5 h-3.5" /> Add Pause Window</button>;
  const submit = async () => {
    if (!form.start_date || !form.end_date) return toast.error("Start and end dates are required");
    if (form.start_date > form.end_date) return toast.error("Start date must be on or before end date");
    if (!form.pause_earn && !form.pause_burn) return toast.error("Select Earn and/or Burn to pause");
    try {
      await api.post("/loyalty/pauses", form);
      toast.success("Pause window added");
      setOpen(false);
      onAdd?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white shadow-2xl max-w-lg w-full p-6 border border-black/10" data-testid="pause-modal">
        <h3 className="font-display text-xl mb-3">Add pause window</h3>
        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <Mini label="Label (e.g. System upgrade, Sale blackout)" v={form.label} onChange={(v) => setForm({ ...form, label: v })} testid="newpause-label" />
          </div>
          <Mini label="Start date" v={form.start_date} type="date" onChange={(v) => setForm({ ...form, start_date: v })} testid="newpause-start" />
          <Mini label="End date" v={form.end_date} type="date" onChange={(v) => setForm({ ...form, end_date: v })} testid="newpause-end" />
        </div>
        <div className="flex items-center gap-6 mt-4">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.pause_earn} onChange={(e) => setForm({ ...form, pause_earn: e.target.checked })} data-testid="newpause-earn" />
            Stop earning
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.pause_burn} onChange={(e) => setForm({ ...form, pause_burn: e.target.checked })} data-testid="newpause-burn" />
            Stop burning (redemption)
          </label>
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button onClick={() => setOpen(false)} className="k-btn k-btn-outline">Cancel</button>
          <button onClick={submit} className="k-btn kazo-bg-burgundy text-white" data-testid="newpause-submit">Add Window</button>
        </div>
      </div>
    </div>
  );
}

function Simulator({ cfg }) {
  const [bill, setBill] = useState(5000);
  const [tier, setTier] = useState((cfg.tier_rules?.[1]?.tier) || "gold");
  const [storeType, setStoreType] = useState("");
  const [category, setCategory] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  const simulate = async () => {
    setBusy(true);
    try {
      const r = await api.post("/loyalty/simulate", {
        bill_amount: bill, tier, store_type: storeType || undefined, category: category || undefined,
      });
      setResult(r.data);
    } catch (e) {
      toast.error("Simulator failed");
    } finally { setBusy(false); }
  };

  return (
    <SectionCard title="EARN SIMULATOR" subtitle="Preview how many points a bill would earn under the current config" icon={Calculator}>
      <div className="grid lg:grid-cols-5 gap-3 items-end">
        <NumField label="Bill (₹)" value={bill} onChange={(v) => setBill(parseFloat(v) || 0)} testid="sim-bill" />
        <div>
          <Label>Customer tier</Label>
          <select className="k-input w-full" value={tier} onChange={(e) => setTier(e.target.value)} data-testid="sim-tier">
            {cfg.tier_rules.map((t) => <option key={t.tier} value={t.tier}>{(t.name || t.tier).toUpperCase()}</option>)}
          </select>
        </div>
        <div>
          <Label>Store type</Label>
          <select className="k-input w-full" value={storeType} onChange={(e) => setStoreType(e.target.value)} data-testid="sim-store">
            <option value="">—</option>
            {Object.keys(cfg.store_type_multipliers || {}).map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
        </div>
        <div>
          <Label>Category</Label>
          <select className="k-input w-full" value={category} onChange={(e) => setCategory(e.target.value)} data-testid="sim-cat">
            <option value="">—</option>
            {Object.keys(cfg.category_multipliers || {}).map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
        </div>
        <button onClick={simulate} disabled={busy} className="k-btn kazo-bg-burgundy text-white" data-testid="sim-run">
          <Calculator className="w-3.5 h-3.5" /> {busy ? "…" : "Simulate"}
        </button>
      </div>
      {result && (
        <div className="mt-4 border border-emerald-200 bg-emerald-50/40 p-4" data-testid="sim-result">
          <div className="text-[10px] uppercase tracking-[0.22em] text-emerald-800 mb-1">RESULT</div>
          <div className="font-display hero-number-md text-emerald-900">{fmtNum(result.points)} pts</div>
          <p className="text-sm text-neutral-700 mt-1">{result.explanation}</p>
          <table className="w-full text-xs mt-3">
            <thead className="border-b border-emerald-200">
              <tr><th className="text-left py-1">Step</th><th className="text-left py-1">Detail</th><th className="text-right py-1">+pts</th></tr>
            </thead>
            <tbody>
              {result.breakdown.map((b, i) => (
                <tr key={i} className="border-b border-emerald-100">
                  <td className="py-1">{b.step}</td>
                  <td className="py-1 text-neutral-600">{b.detail}</td>
                  <td className="py-1 text-right font-mono">{fmtNum(b.points)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </SectionCard>
  );
}
