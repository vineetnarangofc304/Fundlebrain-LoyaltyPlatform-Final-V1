import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth, hasRole } from "@/lib/auth";
import {
  LayoutDashboard, TrendingUp, UserRound, Award, BarChart3, Store as StoreIcon, MessageCircle,
  Users, Ticket, Send, Brain, Activity, UserCog, MessageSquare, FileBarChart, LogOut, Sparkles,
  Settings, Package, Layers, FileText, Image as ImageIcon, ChevronRight
} from "lucide-react";
import { useState } from "react";

const SECTIONS = [
  {
    label: "DASHBOARDS",
    items: [
      { to: "/admin", end: true, icon: LayoutDashboard, label: "Command Center", testid: "nav-command-center" },
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
      { to: "/admin/campaigns", icon: Send, label: "Campaigns", testid: "nav-campaigns" },
      { to: "/admin/coupons", icon: Ticket, label: "Coupons", testid: "nav-coupons" },
    ],
  },
  {
    label: "AI TOOLS",
    items: [
      { to: "/admin/ai", icon: Brain, label: "Fundle Brain", testid: "nav-ai" },
    ],
  },
  {
    label: "OPERATIONS",
    items: [
      { to: "/admin/stores", icon: StoreIcon, label: "Stores", testid: "nav-stores" },
      { to: "/admin/items", icon: Package, label: "Item Master", testid: "nav-items" },
      { to: "/admin/api-monitor", icon: Activity, label: "API Monitor", testid: "nav-api" },
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
  const [collapsed, setCollapsed] = useState({});

  const toggleSection = (label) => setCollapsed((c) => ({ ...c, [label]: !c[label] }));

  return (
    <div className="min-h-screen flex" style={{ background: "var(--workspace-bg)" }}>
      <aside className="admin-sidebar w-64 m-3 flex flex-col" data-testid="admin-sidebar">
        <div className="p-5 border-b border-white/10">
          <div className="font-display text-2xl tracking-tight text-white">KAZO</div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-white/40 mt-1 flex items-center gap-1">
            <Sparkles className="w-3 h-3" /> Powered by Fundle
          </div>
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

      <main className="flex-1 overflow-x-hidden">
        <Outlet />
      </main>
    </div>
  );
}
