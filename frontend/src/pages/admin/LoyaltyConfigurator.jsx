import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader } from "./_shared";
import { toast } from "sonner";
import { fmtNum, fmtINR } from "@/lib/format";

export default function LoyaltyConfigurator() {
  const [cfg, setCfg] = useState(null);
  const [stats, setStats] = useState([]);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    const [c, s] = await Promise.all([api.get("/loyalty/config"), api.get("/loyalty/tier-stats")]);
    setCfg(c.data);
    setStats(s.data);
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    setSaving(true);
    try {
      await api.put("/loyalty/config", cfg);
      toast.success("Loyalty configuration updated");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Update failed");
    } finally {
      setSaving(false);
    }
  };

  if (!cfg) return <div className="p-10 text-neutral-500">Loading…</div>;

  const updTier = (i, key, val) => {
    const arr = [...cfg.tier_rules];
    arr[i] = { ...arr[i], [key]: val };
    setCfg({ ...cfg, tier_rules: arr });
  };

  return (
    <div data-testid="loyalty-configurator">
      <PageHeader
        title="Loyalty Configurator"
        subtitle="DIY RULE ENGINE"
        actions={<button className="k-btn kazo-bg-burgundy" onClick={save} disabled={saving} data-testid="save-loyalty-btn">{saving ? "Saving…" : "Save changes"}</button>}
      />
      <div className="p-8 space-y-6">
        {/* Tier Stats */}
        <div className="bg-white border border-black/10 p-5">
          <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-3">CURRENT DISTRIBUTION</div>
          <div className="grid md:grid-cols-4 gap-3">
            {stats.map((s) => (
              <div key={s.tier} className="border border-black/10 p-4">
                <div className={`pill pill-${s.tier}`}>{s.tier?.toUpperCase()}</div>
                <div className="font-mono text-2xl mt-3">{fmtNum(s.count)}</div>
                <div className="text-xs text-neutral-500 mt-1">customers · {fmtINR(s.total_spend)} LTS</div>
              </div>
            ))}
          </div>
        </div>

        {/* Core ratios */}
        <div className="bg-white border border-black/10 p-5">
          <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-3">CORE RATIOS</div>
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-4">
            <Field label="Earn Ratio (pts / ₹)" value={cfg.earn_ratio} onChange={(v) => setCfg({ ...cfg, earn_ratio: parseFloat(v) || 0 })} testid="cfg-earn-ratio" />
            <Field label="Burn Ratio (₹ / pt)" value={cfg.burn_ratio} onChange={(v) => setCfg({ ...cfg, burn_ratio: parseFloat(v) || 0 })} testid="cfg-burn-ratio" />
            <Field label="Min Redeem Points" value={cfg.min_redeem_points} type="int" onChange={(v) => setCfg({ ...cfg, min_redeem_points: parseInt(v) || 0 })} testid="cfg-min-redeem" />
            <Field label="Point Expiry (days)" value={cfg.point_expiry_days} type="int" onChange={(v) => setCfg({ ...cfg, point_expiry_days: parseInt(v) || 0 })} testid="cfg-expiry" />
            <Field label="Welcome Bonus (pts)" value={cfg.welcome_bonus} type="int" onChange={(v) => setCfg({ ...cfg, welcome_bonus: parseInt(v) || 0 })} testid="cfg-welcome" />
            <Field label="Birthday Bonus (pts)" value={cfg.birthday_bonus} type="int" onChange={(v) => setCfg({ ...cfg, birthday_bonus: parseInt(v) || 0 })} testid="cfg-birthday" />
            <Field label="Anniversary Bonus (pts)" value={cfg.anniversary_bonus} type="int" onChange={(v) => setCfg({ ...cfg, anniversary_bonus: parseInt(v) || 0 })} testid="cfg-anniversary" />
            <Field label="Referrer Points" value={cfg.referral_points_referrer} type="int" onChange={(v) => setCfg({ ...cfg, referral_points_referrer: parseInt(v) || 0 })} testid="cfg-ref-referrer" />
            <Field label="Referee Points" value={cfg.referral_points_referee} type="int" onChange={(v) => setCfg({ ...cfg, referral_points_referee: parseInt(v) || 0 })} testid="cfg-ref-referee" />
            <Field label="Min Bill for Earn (₹)" value={cfg.min_bill_for_earn} onChange={(v) => setCfg({ ...cfg, min_bill_for_earn: parseFloat(v) || 0 })} testid="cfg-min-bill" />
            <Toggle label="Require OTP for redeem" value={cfg.require_otp_for_redeem} onChange={(v) => setCfg({ ...cfg, require_otp_for_redeem: v })} testid="cfg-otp" />
            <Toggle label="Allow coupon stacking" value={cfg.allow_coupon_stacking} onChange={(v) => setCfg({ ...cfg, allow_coupon_stacking: v })} testid="cfg-stacking" />
          </div>
        </div>

        {/* Tier rules */}
        <div className="bg-white border border-black/10 p-5">
          <div className="text-[11px] uppercase tracking-[0.2em] text-neutral-500 mb-3">TIER RULES</div>
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead><tr><th>Tier</th><th>Min Lifetime Spend (₹)</th><th>Earn Multiplier</th><th>Welcome Bonus</th><th>Birthday Bonus</th></tr></thead>
              <tbody>
                {cfg.tier_rules.map((t, i) => (
                  <tr key={t.tier}>
                    <td><span className={`pill pill-${t.tier}`}>{t.tier?.toUpperCase()}</span></td>
                    <td><input className="k-input !py-1 !text-sm" type="number" value={t.min_lifetime_spend} onChange={(e) => updTier(i, "min_lifetime_spend", parseFloat(e.target.value) || 0)} data-testid={`tier-${t.tier}-spend`} /></td>
                    <td><input className="k-input !py-1 !text-sm" type="number" step="0.01" value={t.earn_multiplier} onChange={(e) => updTier(i, "earn_multiplier", parseFloat(e.target.value) || 0)} data-testid={`tier-${t.tier}-mult`} /></td>
                    <td><input className="k-input !py-1 !text-sm" type="number" value={t.welcome_bonus} onChange={(e) => updTier(i, "welcome_bonus", parseInt(e.target.value) || 0)} data-testid={`tier-${t.tier}-welcome`} /></td>
                    <td><input className="k-input !py-1 !text-sm" type="number" value={t.birthday_bonus} onChange={(e) => updTier(i, "birthday_bonus", parseInt(e.target.value) || 0)} data-testid={`tier-${t.tier}-birthday`} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, type = "number", testid }) {
  return (
    <div>
      <label className="text-[10px] uppercase tracking-widest text-neutral-500 mb-1.5 block">{label}</label>
      <input type="number" className="k-input" value={value} onChange={(e) => onChange(e.target.value)} data-testid={testid} />
    </div>
  );
}

function Toggle({ label, value, onChange, testid }) {
  return (
    <div>
      <label className="text-[10px] uppercase tracking-widest text-neutral-500 mb-1.5 block">{label}</label>
      <button type="button" onClick={() => onChange(!value)} className={`flex items-center gap-2 px-3 py-2 border ${value ? "kazo-bg-burgundy text-white border-transparent" : "border-black/20 bg-white"}`} data-testid={testid}>
        {value ? "Enabled" : "Disabled"}
      </button>
    </div>
  );
}
