import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Sparkles, Crown, Gift, Star, ChevronDown } from "lucide-react";
import api from "@/lib/api";
import { toast } from "sonner";

const heroImg = "https://static.prod-images.emergentagent.com/jobs/e79d70f1-3e69-4d31-89bd-3394bf0b0e8f/images/78c63bea378c62b7998687065d6e72a793a918832cab75549bf67f8c89f11216.png";
const fabric = "https://static.prod-images.emergentagent.com/jobs/e79d70f1-3e69-4d31-89bd-3394bf0b0e8f/images/a4dd983df23375d64a8141f5a63c1af5c10acb725b7ce0279647c84ec4772a05.png";
const editorial = "https://images.pexels.com/photos/7778893/pexels-photo-7778893.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=900&w=1200";
const boutique = "https://images.pexels.com/photos/33327425/pexels-photo-33327425.png?auto=compress&cs=tinysrgb&dpr=2&h=900&w=1200";

const tiers = [
  { name: "Silver", minSpend: "₹0", multiplier: "1x", birthday: "200 pts", colorClass: "pill-silver" },
  { name: "Gold", minSpend: "₹25,000", multiplier: "1.25x", birthday: "500 pts", colorClass: "pill-gold" },
  { name: "Platinum", minSpend: "₹75,000", multiplier: "1.5x", birthday: "1000 pts", colorClass: "pill-platinum" },
  { name: "Diamond", minSpend: "₹1,50,000", multiplier: "2x", birthday: "2000 pts", colorClass: "pill-diamond" },
];

export default function Home() {
  const [form, setForm] = useState({ name: "", mobile: "", email: "", city: "" });
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    document.title = "KAZO Rewards — Where Style Earns You More";
    const m = document.querySelector('meta[name="description"]');
    const desc = "Join the official KAZO loyalty programme. Earn points on every purchase, unlock exclusive tier privileges, birthday bonuses, and access VIP collections across India.";
    if (m) m.setAttribute("content", desc);
    else {
      const meta = document.createElement("meta");
      meta.name = "description";
      meta.content = desc;
      document.head.appendChild(meta);
    }
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.mobile || form.mobile.length < 10) {
      toast.error("Please enter a valid 10-digit mobile number");
      return;
    }
    setSubmitting(true);
    try {
      const r = await api.post("/public/register-interest", form);
      setResult(r.data);
      if (r.data.already_registered) {
        toast.success(`Welcome back! You're a ${r.data.tier?.toUpperCase()} member with ${r.data.points} points.`);
      } else {
        toast.success(`Welcome to KAZO Rewards! 100 bonus points credited.`);
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Registration failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div>
      {/* HERO */}
      <section className="relative kazo-bg-black text-white overflow-hidden">
        <div className="grid lg:grid-cols-2 min-h-[80vh]">
          <div className="relative order-2 lg:order-1 px-6 lg:px-16 py-16 lg:py-24 flex flex-col justify-center">
            <div className="text-[11px] uppercase tracking-[0.3em] text-white/50 mb-6 fade-up">An Exclusive Programme · Powered by Fundle</div>
            <h1 className="editorial-headline text-5xl md:text-6xl lg:text-7xl xl:text-8xl mb-6 fade-up" style={{ animationDelay: "0.1s" }}>
              Where style<br />
              <em className="kazo-text-champagne font-light">earns</em> you<br />
              more.
            </h1>
            <p className="text-white/70 text-lg max-w-md mb-10 leading-relaxed fade-up" style={{ animationDelay: "0.2s" }}>
              The official KAZO loyalty programme. Every purchase reveals new privileges — from welcome bonuses and birthday gifts to private VIP previews.
            </p>

            <form onSubmit={submit} className="space-y-3 max-w-md fade-up" style={{ animationDelay: "0.3s" }}>
              <div className="grid grid-cols-2 gap-3">
                <input style={{background:"rgba(255,255,255,0.08)",border:"1px solid rgba(255,255,255,0.2)",color:"#fff"}} className="px-3 py-2.5 text-sm placeholder:text-white/40 rounded-[2px] focus:outline-none focus:border-white/60" placeholder="Full name" value={form.name} onChange={(e)=>setForm({...form,name:e.target.value})} data-testid="hero-input-name" />
                <input style={{background:"rgba(255,255,255,0.08)",border:"1px solid rgba(255,255,255,0.2)",color:"#fff"}} className="px-3 py-2.5 text-sm placeholder:text-white/40 rounded-[2px] focus:outline-none focus:border-white/60" placeholder="Mobile number" value={form.mobile} onChange={(e)=>setForm({...form,mobile:e.target.value})} data-testid="hero-input-mobile" />
              </div>
              <input style={{background:"rgba(255,255,255,0.08)",border:"1px solid rgba(255,255,255,0.2)",color:"#fff"}} className="w-full px-3 py-2.5 text-sm placeholder:text-white/40 rounded-[2px] focus:outline-none focus:border-white/60" placeholder="Email (optional)" value={form.email} onChange={(e)=>setForm({...form,email:e.target.value})} data-testid="hero-input-email" />
              <input style={{background:"rgba(255,255,255,0.08)",border:"1px solid rgba(255,255,255,0.2)",color:"#fff"}} className="w-full px-3 py-2.5 text-sm placeholder:text-white/40 rounded-[2px] focus:outline-none focus:border-white/60" placeholder="City" value={form.city} onChange={(e)=>setForm({...form,city:e.target.value})} data-testid="hero-input-city" />
              <button type="submit" disabled={submitting} className="k-btn kazo-bg-champagne text-black w-full justify-center font-semibold text-sm uppercase tracking-widest" data-testid="hero-submit-btn">
                {submitting ? "Joining…" : "Join KAZO Rewards Free"} <ArrowUpRight className="w-4 h-4" />
              </button>
            </form>
            {result && (
              <div className="mt-4 text-sm text-champagne kazo-text-champagne fade-up">
                {result.already_registered ? `Welcome back. Tier: ${result.tier?.toUpperCase()} · Balance: ${result.points} pts` : `You're in! +${result.welcome_bonus} welcome points credited.`}
              </div>
            )}

            <div className="mt-10 flex items-center gap-8 text-xs text-white/40 fade-up" style={{ animationDelay: "0.4s" }}>
              <div><span className="text-2xl font-display text-white">1.5L+</span><div className="uppercase tracking-widest mt-1">Members</div></div>
              <div className="h-8 w-px bg-white/20" />
              <div><span className="text-2xl font-display text-white">15+</span><div className="uppercase tracking-widest mt-1">Cities</div></div>
              <div className="h-8 w-px bg-white/20" />
              <div><span className="text-2xl font-display text-white">25+</span><div className="uppercase tracking-widest mt-1">Stores</div></div>
            </div>
          </div>

          <div className="relative order-1 lg:order-2 min-h-[50vh] lg:min-h-0 overflow-hidden">
            <img src={heroImg} alt="KAZO premium women's western fashion editorial" className="w-full h-full object-cover" />
            <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-transparent" />
            <div className="absolute bottom-8 left-8 right-8 lg:hidden text-white">
              <div className="text-[11px] uppercase tracking-[0.3em] opacity-60">Spring · Summer 2026</div>
            </div>
          </div>
        </div>
      </section>

      {/* INTRO STRIP */}
      <section className="py-12 px-6 lg:px-12 max-w-[1400px] mx-auto border-b border-black/10">
        <div className="grid md:grid-cols-3 gap-12">
          <div className="flex gap-4">
            <Sparkles className="w-6 h-6 kazo-text-burgundy flex-shrink-0 mt-1" />
            <div>
              <h3 className="font-display text-2xl mb-2">Earn 1 Point per ₹1</h3>
              <p className="text-sm text-neutral-600 leading-relaxed">Across every store, every collection. Doubled at the Diamond tier.</p>
            </div>
          </div>
          <div className="flex gap-4">
            <Crown className="w-6 h-6 kazo-text-burgundy flex-shrink-0 mt-1" />
            <div>
              <h3 className="font-display text-2xl mb-2">Four Tiers, One Wardrobe</h3>
              <p className="text-sm text-neutral-600 leading-relaxed">Silver to Diamond. Each tier unlocks deeper privileges and earlier access.</p>
            </div>
          </div>
          <div className="flex gap-4">
            <Gift className="w-6 h-6 kazo-text-burgundy flex-shrink-0 mt-1" />
            <div>
              <h3 className="font-display text-2xl mb-2">Birthday Privileges</h3>
              <p className="text-sm text-neutral-600 leading-relaxed">Up to 2,000 bonus points on your birthday, plus an exclusive look book.</p>
            </div>
          </div>
        </div>
      </section>

      {/* TIERS */}
      <section className="py-24 px-6 lg:px-12 max-w-[1400px] mx-auto">
        <div className="max-w-3xl mb-16">
          <div className="text-[11px] uppercase tracking-[0.3em] kazo-text-burgundy mb-4">THE TIERS</div>
          <h2 className="editorial-headline text-5xl lg:text-7xl">Four tiers.<br /><em className="font-light">Endless</em> privileges.</h2>
        </div>
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
          {tiers.map((t, i) => (
            <div key={t.name} className="border border-black/10 p-8 bg-white relative overflow-hidden fade-up" style={{ animationDelay: `${i * 0.1}s` }} data-testid={`tier-card-${t.name.toLowerCase()}`}>
              <span className={t.colorClass + " mb-6 inline-block"}>{t.name}</span>
              <div className="font-display text-4xl mb-2">{t.multiplier}</div>
              <div className="text-xs uppercase tracking-widest text-neutral-500 mb-6">Earn rate</div>
              <div className="space-y-2 text-sm text-neutral-700">
                <div className="flex justify-between border-b border-black/5 pb-1.5"><span className="text-neutral-500">Min. spend</span><span className="font-medium">{t.minSpend}</span></div>
                <div className="flex justify-between border-b border-black/5 pb-1.5"><span className="text-neutral-500">Birthday bonus</span><span className="font-medium">{t.birthday}</span></div>
                <div className="flex justify-between"><span className="text-neutral-500">Early access</span><span className="font-medium">{t.name === "Silver" ? "—" : "✓"}</span></div>
              </div>
            </div>
          ))}
        </div>
        <div className="mt-10">
          <Link to="/loyalty-benefits" className="editorial-link text-sm font-medium uppercase tracking-widest inline-flex items-center gap-2">Compare all benefits <ArrowUpRight className="w-4 h-4" /></Link>
        </div>
      </section>

      {/* EDITORIAL SPLIT */}
      <section className="kazo-bg-black text-white py-24">
        <div className="max-w-[1400px] mx-auto px-6 lg:px-12 grid lg:grid-cols-2 gap-16 items-center">
          <div className="relative aspect-[4/5] overflow-hidden">
            <img src={editorial} alt="Model wearing KAZO collection" className="w-full h-full object-cover" />
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-[0.3em] kazo-text-champagne mb-4">VIP PREVIEW</div>
            <h2 className="editorial-headline text-5xl lg:text-7xl mb-6">Before<br />the world<br /><em className="kazo-text-champagne font-light">sees it.</em></h2>
            <p className="text-white/70 text-lg leading-relaxed mb-8 max-w-md">
              Platinum and Diamond members receive private collection previews — 72 hours before public launch. Reserve your size, your shade, your story.
            </p>
            <Link to="/loyalty-benefits" className="k-btn kazo-bg-champagne text-black uppercase tracking-widest text-xs font-semibold" data-testid="cta-vip-learn-more">
              Learn the privileges <ArrowUpRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </section>

      {/* HOW IT WORKS strip */}
      <section className="py-24 px-6 lg:px-12 max-w-[1400px] mx-auto">
        <div className="grid lg:grid-cols-2 gap-16">
          <div>
            <div className="text-[11px] uppercase tracking-[0.3em] kazo-text-burgundy mb-4">SIMPLY</div>
            <h2 className="editorial-headline text-5xl lg:text-7xl mb-8">Three steps.<br />A lifetime<br /><em className="font-light">of rewards.</em></h2>
            <Link to="/how-it-works" className="editorial-link uppercase tracking-widest text-sm font-medium inline-flex items-center gap-2">See full guide <ArrowUpRight className="w-4 h-4" /></Link>
          </div>
          <div className="space-y-8">
            {[
              { step: "01", title: "Join free", body: "Sign up at any KAZO store or online with your mobile number. Receive 100 welcome points instantly." },
              { step: "02", title: "Earn effortlessly", body: "Quote your mobile at checkout. Points accrue automatically on every ₹1 spent." },
              { step: "03", title: "Redeem your way", body: "1 point = ₹0.25. Use them on your next purchase, in any store, online or off." },
            ].map((s) => (
              <div key={s.step} className="flex gap-8 border-b border-black/10 pb-8 last:border-0">
                <div className="font-display text-5xl kazo-text-champagne" style={{ fontWeight: 300 }}>{s.step}</div>
                <div>
                  <h3 className="font-display text-2xl mb-1">{s.title}</h3>
                  <p className="text-sm text-neutral-600 leading-relaxed max-w-md">{s.body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* FINAL CTA */}
      <section className="relative overflow-hidden" style={{ minHeight: 480 }}>
        <img src={boutique} alt="KAZO boutique interior" className="absolute inset-0 w-full h-full object-cover" />
        <div className="absolute inset-0 bg-black/70" />
        <div className="relative max-w-3xl mx-auto px-6 py-24 text-center text-white">
          <div className="text-[11px] uppercase tracking-[0.3em] text-white/60 mb-6">JOIN TODAY</div>
          <h2 className="editorial-headline text-5xl lg:text-7xl mb-8">Your wardrobe.<br /><em className="kazo-text-champagne font-light">Rewarded.</em></h2>
          <p className="text-white/80 mb-10 max-w-xl mx-auto">Membership is free. Privileges are forever.</p>
          <Link to="/" className="k-btn kazo-bg-champagne text-black uppercase tracking-widest text-xs font-semibold" data-testid="cta-final-join">
            Become a member <ArrowUpRight className="w-4 h-4" />
          </Link>
        </div>
      </section>
    </div>
  );
}
