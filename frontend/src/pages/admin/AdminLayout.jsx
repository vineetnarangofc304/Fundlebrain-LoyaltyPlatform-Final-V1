import { NavLink, Outlet, useNavigate, useLocation } from "react-router-dom";
import { useAuth, hasRole } from "@/lib/auth";
import {
  LayoutDashboard, TrendingUp, UserRound, Award, BarChart3, Store as StoreIcon, MessageCircle,
  Users, Ticket, Send, Brain, Activity, UserCog, MessageSquare, FileBarChart, LogOut, Sparkles,
  Settings, Package, Layers, FileText, Image as ImageIcon, ChevronRight, Database, Upload, Radio, KeyRound,
  Menu as MenuIcon, X as CloseIcon, ShieldCheck, Filter, Cake
} from "lucide-react";
import { useState, useEffect } from "react";
import { BRAND } from "@/brand.config";
import FundleBrainFAB from "./_fundle_brain_fab";

const SECTIONS = [
  {
    label: "DASHBOARDS",
    items: [
      { to: "/admin", end: true, icon: LayoutDashboard, label: "Command Center", testid: "nav-command-center" },
      { to: "/admin/live-monitor", icon: Radio, label: "Live Bill Monitor", testid: "nav-live-monitor" },
      { to: "/admin/dashboards/sales", icon: TrendingUp, label: "Sales", testid: "nav-dash-sales" },
      { to: "/admin/dashboards/customers", icon: UserRound, label: "Customer Analytics", testid: "nav-dash-customers" },
      { to: "/admin/dashboards/loyalty", icon: Award, label: "Loyalty", testid: "nav-dash-loyalty" },
      { to: "/admin/dashboards/campaigns", icon: BarChart3, label: "Campaign Performance", testid: "nav-dash-campaigns" },
      { to: "/admin/dashboards/stores", icon: StoreIcon, label: "Store Performance", testid: "nav-dash-stores" },
      { to: "/admin/dashboards/rfm", icon: Layers, label: "RFM & Churn", testid: "nav-dash-rfm" },
      { to: "/admin/dashboards/cohorts", icon: Users, label: "Cohorts & Segments", testid: "nav-dash-cohorts" },
      { to: "/admin/dashboards/points", icon: Award, label: "Points Economics", testid: "nav-dash-points" },
      { to: "/admin/dashboards/campaign-roi", icon: BarChart3, label: "Campaign ROI", testid: "nav-dash-campaign-roi" },
      { to: "/admin/dashboards/executive-summary", icon: FileText, label: "Executive Summary", testid: "nav-dash-exec" },
      { to: "/admin/dashboards/nps", icon: MessageCircle, label: "NPS & Feedback", testid: "nav-dash-nps" },
    ],
  },
  {
    label: "CUSTOMERS",
    items: [
      { to: "/admin/customers", icon: Users, label: "Customer 360", testid: "nav-customers" },
    ],
  },
  {
    label: "MARKETING",
    items: [
      { to: "/admin/segments", icon: Filter, label: "Segment Builder", testid: "nav-segments" },
      { to: "/admin/campaigns", icon: Send, label: "Campaigns", testid: "nav-campaigns" },
      { to: "/admin/auto-campaigns", icon: Cake, label: "Auto Campaigns", testid: "nav-auto-campaigns" },
      { to: "/admin/coupons", icon: Ticket, label: "Coupons", testid: "nav-coupons" },
    ],
  },
  {
    label: "COMMUNICATIONS",
    items: [
      { to: "/admin/communications/templates", icon: MessageSquare, label: "Templates", testid: "nav-comm-templates" },
      { to: "/admin/communications/bulk-jobs", icon: Send, label: "Bulk Send Jobs", testid: "nav-comm-jobs" },
      { to: "/admin/communications/settings", icon: Settings, label: "Provider Settings", testid: "nav-comm-settings" },
    ],
  },
  {
    label: "AI TOOLS",
    items: [
      // Fundle Brain moved out of this section — surfaced as a dedicated hero
      // entry at the top of the sidebar so it stands apart visually.
    ],
  },
  {
    label: "DATA",
    items: [
      { to: "/admin/raw-reports", icon: BarChart3, label: "Raw Data Reports", testid: "nav-raw-reports" },
      { to: "/admin/historic-data", icon: Database, label: "Historical Upload", testid: "nav-historic-data" },
      { to: "/admin/reconciliation", icon: ShieldCheck, label: "Data Reconciliation", testid: "nav-reconciliation" },
    ],
  },
  {
    label: "OPERATIONS",
    items: [
      { to: "/admin/stores", icon: StoreIcon, label: "Stores", testid: "nav-stores" },
      { to: "/admin/items", icon: Package, label: "Item Master", testid: "nav-items" },
      { to: "/admin/api-monitor", icon: Activity, label: "API Monitor", testid: "nav-api" },
      { to: "/admin/pos-credentials", icon: KeyRound, label: "POS Credentials", testid: "nav-pos-creds" },
    ],
  },
  {
    label: "SUPPORT",
    items: [
      { to: "/admin/tickets", icon: MessageSquare, label: "Tickets", testid: "nav-tickets" },
      { to: "/admin/nps", icon: MessageCircle, label: "NPS Inbox", testid: "nav-nps" },
    ],
  },
  {
    label: "SUPPORT DESK",
    items: [
      { to: "/admin/support-desk/search-redeem-points-otp", icon: KeyRound, label: "Search Redeem Points OTP", testid: "nav-sd-rpo" },
      { to: "/admin/support-desk/search-redeem-coupon-otp", icon: KeyRound, label: "Search Redeem Coupon OTP", testid: "nav-sd-rco" },
      { to: "/admin/support-desk/reactivate-coupon", icon: Ticket, label: "Reactivate Coupon", testid: "nav-sd-rac" },
      { to: "/admin/support-desk/reactivate-redeem-points", icon: Award, label: "Reactivate Redeem Points", testid: "nav-sd-rrp" },
      { to: "/admin/support-desk/customer-deactivate", icon: UserCog, label: "Customer Deactivate", testid: "nav-sd-deact" },
      { to: "/admin/support-desk/customer-reactivate", icon: UserCog, label: "Customer Reactivate", testid: "nav-sd-react" },
      { to: "/admin/support-desk/unsubscribe", icon: MessageSquare, label: "Unsubscribe Customer", testid: "nav-sd-unsub" },
      { to: "/admin/support-desk/audit-log", icon: ShieldCheck, label: "Support Desk Audit", testid: "nav-sd-audit" },
    ],
  },
  {
    label: "REPORTS",
    items: [
      { to: "/admin/legacy-reports", icon: FileBarChart, label: "Reports (Legacy)", testid: "nav-legacy-reports" },
      { to: "/admin/reports", icon: FileBarChart, label: "Reports & Exports", testid: "nav-reports" },
      { to: "/admin/reports/digests", icon: FileText, label: "Exec Digests", testid: "nav-reports-digests" },
      { to: "/admin/formula-catalog", icon: FileText, label: "Formula Catalog", testid: "nav-formula" },
    ],
  },
  {
    label: "CONFIGURATION",
    items: [
      { to: "/admin/loyalty", icon: Award, label: "Loyalty Rules", testid: "nav-loyalty" },
      { to: "/admin/cms", icon: ImageIcon, label: "Public Site CMS", testid: "nav-cms" },
    ],
  },
  {
    label: "ADMINISTRATION",
    adminOnly: true,
    items: [
      { to: "/admin/users", icon: UserCog, label: "User Management", testid: "nav-users" },
    ],
  },
];

export default function AdminLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState({});
  // Mobile sidebar drawer state — closed by default on small screens
  const [drawerOpen, setDrawerOpen] = useState(false);

  // Close drawer whenever route changes (so a nav-click on mobile dismisses it)
  useEffect(() => { setDrawerOpen(false); }, [location.pathname]);

  const toggleSection = (label) => setCollapsed((c) => ({ ...c, [label]: !c[label] }));

  return (
    <div className="min-h-screen flex relative" style={{ background: "var(--workspace-bg)" }}>
      {/* Mobile hamburger — fixed top-left, only on small screens */}
      <button
        type="button"
        onClick={() => setDrawerOpen(true)}
        className="md:hidden fixed top-3 left-3 z-40 w-10 h-10 rounded-full flex items-center justify-center bg-black/85 text-white shadow-lg backdrop-blur"
        aria-label="Open menu"
        data-testid="mobile-menu-open"
      >
        <MenuIcon className="w-5 h-5" />
      </button>

      {/* Backdrop — only when drawer is open on mobile */}
      {drawerOpen && (
        <button
          type="button"
          onClick={() => setDrawerOpen(false)}
          className="md:hidden fixed inset-0 z-40 bg-black/50 backdrop-blur-sm"
          aria-label="Close menu"
          data-testid="mobile-menu-backdrop"
        />
      )}

      <aside
        className={`admin-sidebar w-64 m-3 flex flex-col z-50 transition-transform duration-300
          md:relative md:translate-x-0
          fixed top-0 left-0 bottom-0 max-h-screen
          ${drawerOpen ? "translate-x-0" : "-translate-x-[110%] md:translate-x-0"}`}
        data-testid="admin-sidebar"
      >
        <div className="p-5 border-b border-white/10 flex items-start justify-between">
          <div>
            <div className="font-display text-2xl tracking-tight text-white">{BRAND.name}</div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-white/40 mt-1 flex items-center gap-1">
              <Sparkles className="w-3 h-3" /> {BRAND.poweredBy}
            </div>
          </div>
          {/* Close button — mobile only */}
          <button
            type="button"
            onClick={() => setDrawerOpen(false)}
            className="md:hidden text-white/70 hover:text-white"
            aria-label="Close menu"
            data-testid="mobile-menu-close"
          >
            <CloseIcon className="w-5 h-5" />
          </button>
        </div>
        <nav className="flex-1 py-3 overflow-y-auto">
          {/* Fundle Brain hero entry — sits above every section so it stands
              apart. Champagne-on-burgundy treatment matches the AI accent
              colour used elsewhere in the app. */}
          <NavLink
            to="/admin/ai"
            data-testid="nav-ai"
            className={({ isActive }) =>
              `mx-3 mb-3 flex items-center gap-3 px-4 py-3 rounded-sm relative overflow-hidden transition-all group ${
                isActive
                  ? "ring-2 ring-amber-300/60"
                  : "hover:ring-2 hover:ring-amber-300/30"
              }`
            }
            style={{
              background:
                "linear-gradient(135deg, var(--kazo-burgundy) 0%, var(--kazo-burgundy-deep) 60%, #2A0814 100%)",
            }}
          >
            <div className="absolute inset-0 opacity-20 pointer-events-none"
                  style={{ background: "radial-gradient(circle at 80% 0%, var(--kazo-champagne) 0%, transparent 50%)" }} />
            <div className="relative w-9 h-9 rounded-full bg-gradient-to-br from-amber-300/30 to-amber-100/10 border border-amber-200/40 flex items-center justify-center shrink-0">
              <Brain className="w-4 h-4 kazo-text-champagne" />
            </div>
            <div className="relative flex-1 min-w-0">
              <div className="font-display text-[15px] tracking-tight text-white flex items-center gap-1.5">
                Fundle Brain
                <Sparkles className="w-3 h-3 kazo-text-champagne" />
              </div>
              <div className="text-[10px] uppercase tracking-[0.2em] kazo-text-champagne/80 mt-0.5">
                ASK ANYTHING · LIVE DATA
              </div>
            </div>
          </NavLink>

          {SECTIONS.map((section) => {
            if (section.adminOnly && !hasRole(user, "super_admin", "brand_admin")) return null;
            if (!section.items || section.items.length === 0) return null;
            const isCollapsed = !!collapsed[section.label];
            return (
              <div key={section.label} className="mb-1">
                <button
                  onClick={() => toggleSection(section.label)}
                  className="w-full flex items-center justify-between px-5 py-1.5 text-[10px] uppercase tracking-[0.18em] text-white/35 hover:text-white/60"
                  data-testid={`section-${section.label}`}
                >
                  <span>{section.label}</span>
                  <ChevronRight className={`w-3 h-3 transition-transform ${isCollapsed ? "" : "rotate-90"}`} />
                </button>
                {!isCollapsed && section.items.map((n) => (
                  <NavLink
                    key={n.to}
                    to={n.to}
                    end={n.end}
                    data-testid={n.testid}
                    className={({ isActive }) =>
                      `flex items-center gap-3 px-5 py-2 text-[13px] hover:bg-white/5 ${isActive ? "active" : "text-white/75"}`
                    }
                  >
                    <n.icon className="w-3.5 h-3.5" />
                    <span>{n.label}</span>
                  </NavLink>
                ))}
              </div>
            );
          })}
        </nav>
        <div className="p-4 border-t border-white/10">
          <div className="text-xs text-white/70 mb-1 truncate">{user?.name}</div>
          <div className="text-[10px] uppercase tracking-widest text-white/40 mb-3">{user?.role?.replace(/_/g, " ")}</div>
          <button
            onClick={async () => { await logout(); navigate("/enterprise/login"); }}
            className="text-xs text-white/70 hover:text-white flex items-center gap-2"
            data-testid="logout-btn"
          >
            <LogOut className="w-3.5 h-3.5" /> Sign out
          </button>
        </div>
      </aside>

      <main className="flex-1 overflow-x-hidden min-w-0">
        <Outlet />
      </main>
      <FundleBrainFAB />
    </div>
  );
}
