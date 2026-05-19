import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth, hasRole } from "@/lib/auth";
import {
  LayoutDashboard, Users, Award, Ticket, Send, Brain, Activity,
  UserCog, Store as StoreIcon, MessageCircle, MessageSquare, FileBarChart, LogOut, Sparkles
} from "lucide-react";

const nav = [
  { to: "/admin", end: true, icon: LayoutDashboard, label: "Executive Cockpit", testid: "nav-cockpit" },
  { to: "/admin/customers", icon: Users, label: "Customer 360", testid: "nav-customers" },
  { to: "/admin/loyalty", icon: Award, label: "Loyalty Configurator", testid: "nav-loyalty" },
  { to: "/admin/coupons", icon: Ticket, label: "Coupon Engine", testid: "nav-coupons" },
  { to: "/admin/campaigns", icon: Send, label: "Campaign Manager", testid: "nav-campaigns" },
  { to: "/admin/ai", icon: Brain, label: "Fundle Brain AI", testid: "nav-ai" },
  { to: "/admin/api-monitor", icon: Activity, label: "Live API Monitor", testid: "nav-api" },
  { to: "/admin/stores", icon: StoreIcon, label: "Stores", testid: "nav-stores" },
  { to: "/admin/nps", icon: MessageCircle, label: "NPS & Feedback", testid: "nav-nps" },
  { to: "/admin/tickets", icon: MessageSquare, label: "Support Tickets", testid: "nav-tickets" },
  { to: "/admin/reports", icon: FileBarChart, label: "Reports", testid: "nav-reports" },
];

const adminOnly = [
  { to: "/admin/users", icon: UserCog, label: "User Management", testid: "nav-users", roles: ["super_admin", "brand_admin"] },
];

export default function AdminLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex" style={{ background: "var(--workspace-bg)" }}>
      {/* Sidebar */}
      <aside className="admin-sidebar w-64 m-3 flex flex-col" data-testid="admin-sidebar">
        <div className="p-5 border-b border-white/10">
          <div className="font-display text-2xl tracking-tight text-white">KAZO</div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-white/40 mt-1 flex items-center gap-1">
            <Sparkles className="w-3 h-3" /> Powered by Fundle
          </div>
        </div>
        <nav className="flex-1 py-4 overflow-y-auto">
          {nav.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              data-testid={n.testid}
              className={({ isActive }) =>
                `flex items-center gap-3 px-5 py-2.5 text-sm font-medium hover:bg-white/5 ${isActive ? "active" : "text-white/70"}`
              }
            >
              <n.icon className="w-4 h-4" />
              <span>{n.label}</span>
            </NavLink>
          ))}
          {adminOnly.map((n) => hasRole(user, ...n.roles) && (
            <NavLink
              key={n.to}
              to={n.to}
              data-testid={n.testid}
              className={({ isActive }) =>
                `flex items-center gap-3 px-5 py-2.5 text-sm font-medium hover:bg-white/5 ${isActive ? "active" : "text-white/70"}`
              }
            >
              <n.icon className="w-4 h-4" />
              <span>{n.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="p-4 border-t border-white/10">
          <div className="text-xs text-white/60 mb-2">{user?.name}</div>
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

      {/* Workspace */}
      <main className="flex-1 overflow-x-hidden">
        <Outlet />
      </main>
    </div>
  );
}
