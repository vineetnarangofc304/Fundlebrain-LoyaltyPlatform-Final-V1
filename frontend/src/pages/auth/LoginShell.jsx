import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/lib/auth";
import { toast } from "sonner";
import { ArrowRight } from "lucide-react";
import { BRAND } from "@/brand.config";

export default function LoginShell({ title, subtitle, portal, allowedRoles, redirectTo, dataTestPrefix }) {
  const { login } = useAuth();
  const nav = useNavigate();
  const [form, setForm] = useState({ email: "", password: "" });
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const u = await login(form.email, form.password, portal);
      if (allowedRoles && !allowedRoles.includes(u.role)) {
        toast.error(`Your account (${u.role}) cannot access this portal.`);
        setLoading(false);
        return;
      }
      toast.success(`Welcome, ${u.name}`);
      nav(redirectTo || "/admin");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      <div className="kazo-bg-black text-white relative overflow-hidden hidden lg:block">
        <img src="https://images.unsplash.com/photo-1617551307578-7f5160d6615e?auto=format&fit=crop&w=1400&q=80" alt={BRAND.loginCopy.imageAlt} className="absolute inset-0 w-full h-full object-cover opacity-60" />
        <div className="absolute inset-0 bg-gradient-to-br from-black via-black/70 to-transparent" />
        <div className="relative h-full flex flex-col p-12">
          <Link to="/" className="font-display text-3xl tracking-tight" style={{ fontWeight: 600 }}>{BRAND.name}</Link>
          <div className="mt-auto">
            <div className="text-[11px] uppercase tracking-[0.3em] kazo-text-champagne mb-4">{portal.toUpperCase()} PORTAL</div>
            <h2 className="editorial-headline text-5xl xl:text-6xl mb-4">Command<br /><em className="font-light kazo-text-champagne">your kingdom.</em></h2>
            <p className="text-white/60 max-w-md leading-relaxed">{BRAND.loginCopy.descriptor}</p>
          </div>
          <div className="mt-12 flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-[0.2em] text-white/40">Powered by</span>
            <img src={BRAND.platformLogoUrl} alt={BRAND.platform} className="h-4 w-auto opacity-90" />
          </div>
        </div>
      </div>
      <div className="flex items-center justify-center p-8 bg-[#F9F8F6]">
        <div className="w-full max-w-md">
          <Link to="/" className="font-display text-2xl mb-12 inline-block lg:hidden">{BRAND.name}</Link>
          <div className="text-[11px] uppercase tracking-[0.3em] kazo-text-burgundy mb-3">{title}</div>
          <h1 className="editorial-headline text-4xl mb-2">{subtitle}</h1>
          <p className="text-sm text-neutral-500 mb-10">Sign in with your credentials.</p>
          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="text-xs uppercase tracking-widest text-neutral-500 mb-2 block">Email</label>
              <input type="email" required className="k-input" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid={`${dataTestPrefix}-email`} />
            </div>
            <div>
              <label className="text-xs uppercase tracking-widest text-neutral-500 mb-2 block">Password</label>
              <input type="password" required className="k-input" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} data-testid={`${dataTestPrefix}-password`} />
            </div>
            <button type="submit" disabled={loading} className="k-btn kazo-bg-burgundy w-full justify-center uppercase tracking-widest text-xs font-semibold" data-testid={`${dataTestPrefix}-submit`}>
              {loading ? "Signing in…" : "Sign in"} <ArrowRight className="w-4 h-4" />
            </button>
          </form>
          <div className="text-xs text-neutral-500 mt-10 leading-relaxed border-t border-black/10 pt-6">
            <div className="uppercase tracking-widest mb-2 text-neutral-400">Other portals</div>
            <div className="flex flex-wrap gap-4">
              <Link to="/enterprise/login" className="editorial-link">Enterprise</Link>
              <Link to="/store/login" className="editorial-link">Store</Link>
              <Link to="/crm/login" className="editorial-link">CRM</Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
