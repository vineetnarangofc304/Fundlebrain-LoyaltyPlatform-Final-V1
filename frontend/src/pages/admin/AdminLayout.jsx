import { NavLink, Outlet, useNavigate, useLocation } from "react-router-dom";
import { useAuth, hasRole } from "@/lib/auth";
import {
  LayoutDashboard, TrendingUp, UserRound, Award, BarChart3, Store as StoreIcon, MessageCircle,
  Users, Ticket, Send, Brain, Activity, UserCog, MessageSquare, FileBarChart, LogOut, Sparkles,
  Settings, Package, Layers, FileText, Image as ImageIcon, ChevronRight, Database, Upload, Radio, KeyRound,
  Menu as MenuIcon, X as CloseIcon, ShieldCheck, Filter, Cake
} from "lucide-react";
import { useState, useEffect } from "react";

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
      { to: "/admin/ai", icon: Brain, label: "Fundle Brain", testid: "nav-ai" },
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
    label: "REPORTS",
    items: [
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
            <div className="font-display text-2xl tracking-tight text-white">KAZO</div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-white/40 mt-1 flex items-center gap-1">
              <Sparkles className="w-3 h-3" /> Powered by Fundle
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
          {SECTIONS.map((section) => {
            if (section.adminOnly && !hasRole(user, "super_admin", "brand_admin")) return null;
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
    </div>
  );
}
