import { Link, NavLink, Outlet } from "react-router-dom";
import { Instagram, Facebook, Youtube } from "lucide-react";
import { useEffect, useState } from "react";
import api from "@/lib/api";

const navItems = [
  { to: "/about-program", label: "About Program" },
  { to: "/loyalty-benefits", label: "Benefits" },
  { to: "/how-it-works", label: "How It Works" },
  { to: "/rewards", label: "Rewards" },
  { to: "/referral-program", label: "Refer & Earn" },
  { to: "/store-locator", label: "Find a Store" },
  { to: "/faqs", label: "FAQs" },
];

export default function PublicLayout() {
  const [cms, setCms] = useState(null);
  useEffect(() => { api.get("/cms/content").then((r) => setCms(r.data)).catch(() => {}); }, []);
  const topbar = cms?.home?.topbar_text || "EXCLUSIVE LOYALTY PROGRAM · EARN ON EVERY PURCHASE · BIRTHDAY PRIVILEGES INSIDE";
  const tagline = cms?.footer?.tagline || "The official loyalty programme for KAZO — where every purchase becomes a privilege. Designed for the modern Indian woman.";
  const poweredBy = cms?.footer?.powered_by || "Powered by Fundle";

  return (
    <div className="min-h-screen flex flex-col" style={{ background: "var(--kazo-cream)" }}>
      {/* Top utility bar */}
      <div className="kazo-bg-black text-xs tracking-widest text-white py-2 text-center font-medium" style={{ letterSpacing: "0.15em" }}>
        {topbar}
      </div>

      {/* Main header */}
      <header className="border-b border-black/10 bg-[#F9F8F6] sticky top-0 z-40 backdrop-blur" data-testid="public-header">
        <div className="max-w-[1400px] mx-auto px-6 lg:px-12 py-5 flex items-center justify-between">
          <Link to="/" className="flex items-baseline gap-3" data-testid="public-logo-link">
            <span className="font-display text-3xl tracking-tight" style={{ fontWeight: 600, letterSpacing: "-0.04em" }}>KAZO</span>
            <span className="text-[10px] uppercase tracking-[0.3em] text-neutral-500 hidden sm:inline">Rewards</span>
          </Link>

          <nav className="hidden lg:flex items-center gap-7 text-[13px] tracking-wide">
            {navItems.map((n) => (
              <NavLink key={n.to} to={n.to} className={({isActive}) => `editorial-link ${isActive ? 'kazo-text-burgundy font-semibold' : ''}`} data-testid={`nav-${n.to.slice(1)}`}>
                {n.label}
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            <Link to="/enterprise/login" className="k-btn k-btn-outline k-btn-sm hidden md:inline-flex" data-testid="header-enterprise-login">Enterprise Login</Link>
            <Link to="/" className="k-btn k-btn-sm kazo-bg-burgundy text-white" data-testid="header-join-now">Join Free</Link>
          </div>
        </div>
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      {/* Footer */}
      <footer className="kazo-bg-black text-white mt-20">
        <div className="max-w-[1400px] mx-auto px-6 lg:px-12 py-16 grid grid-cols-2 lg:grid-cols-5 gap-10">
          <div className="col-span-2">
            <div className="font-display text-3xl tracking-tight" style={{ fontWeight: 500 }}>KAZO</div>
            <p className="mt-3 text-sm text-white/60 max-w-xs leading-relaxed">
              {tagline}
            </p>
            <div className="mt-6 flex gap-4">
              <a href="https://instagram.com/kazo_brand" className="text-white/70 hover:text-white"><Instagram className="w-5 h-5" /></a>
              <a href="https://facebook.com" className="text-white/70 hover:text-white"><Facebook className="w-5 h-5" /></a>
              <a href="https://youtube.com" className="text-white/70 hover:text-white"><Youtube className="w-5 h-5" /></a>
            </div>
          </div>
          <div>
            <h4 className="text-[11px] uppercase tracking-[0.2em] text-white/40 mb-4">Programme</h4>
            <ul className="space-y-2 text-sm text-white/70">
              <li><Link to="/about-program" className="hover:text-white">About Program</Link></li>
              <li><Link to="/loyalty-benefits" className="hover:text-white">Benefits</Link></li>
              <li><Link to="/how-it-works" className="hover:text-white">How It Works</Link></li>
              <li><Link to="/rewards" className="hover:text-white">Rewards</Link></li>
            </ul>
          </div>
          <div>
            <h4 className="text-[11px] uppercase tracking-[0.2em] text-white/40 mb-4">Engage</h4>
            <ul className="space-y-2 text-sm text-white/70">
              <li><Link to="/earn-points" className="hover:text-white">Earn Points</Link></li>
              <li><Link to="/redeem-points" className="hover:text-white">Redeem Points</Link></li>
              <li><Link to="/referral-program" className="hover:text-white">Refer & Earn</Link></li>
              <li><Link to="/store-locator" className="hover:text-white">Find a Store</Link></li>
            </ul>
          </div>
          <div>
            <h4 className="text-[11px] uppercase tracking-[0.2em] text-white/40 mb-4">Portals</h4>
            <ul className="space-y-2 text-sm text-white/70">
              <li><Link to="/enterprise/login" className="hover:text-white" data-testid="footer-enterprise-login">Enterprise Login</Link></li>
              <li><Link to="/store/login" className="hover:text-white" data-testid="footer-store-login">Store Login</Link></li>
              <li><Link to="/crm/login" className="hover:text-white" data-testid="footer-crm-login">CRM Login</Link></li>
              <li><Link to="/contact" className="hover:text-white">Customer Support</Link></li>
              <li><Link to="/privacy" className="hover:text-white">Privacy Policy</Link></li>
              <li><Link to="/terms" className="hover:text-white">Terms</Link></li>
            </ul>
          </div>
        </div>
        <div className="border-t border-white/10 py-5 px-6 lg:px-12 max-w-[1400px] mx-auto flex flex-col md:flex-row items-center justify-between text-xs text-white/40 gap-2">
          <div>© {new Date().getFullYear()} KAZO. All rights reserved.</div>
          <div className="tracking-[0.15em] uppercase">{poweredBy}</div>
        </div>
      </footer>
    </div>
  );
}
