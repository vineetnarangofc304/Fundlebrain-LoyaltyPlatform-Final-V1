import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "@/lib/auth";
import "@/App.css";

// Public pages
import PublicLayout from "@/pages/public/PublicLayout";
import Home from "@/pages/public/Home";
import LoyaltyBenefits from "@/pages/public/LoyaltyBenefits";
import HowItWorks from "@/pages/public/HowItWorks";
import Rewards from "@/pages/public/Rewards";
import ReferralProgram from "@/pages/public/ReferralProgram";
import StoreLocator from "@/pages/public/StoreLocator";
import FAQs from "@/pages/public/FAQs";
import Privacy from "@/pages/public/Privacy";
import Terms from "@/pages/public/Terms";
import Contact from "@/pages/public/Contact";
import EarnPoints from "@/pages/public/EarnPoints";
import RedeemPoints from "@/pages/public/RedeemPoints";
import AboutProgram from "@/pages/public/AboutProgram";

// Auth
import EnterpriseLogin from "@/pages/auth/EnterpriseLogin";
import StoreLogin from "@/pages/auth/StoreLogin";
import CRMLogin from "@/pages/auth/CRMLogin";

// Admin
import AdminLayout from "@/pages/admin/AdminLayout";
import ExecutiveCockpit from "@/pages/admin/ExecutiveCockpit";
import CommandCenter from "@/pages/admin/dashboards/CommandCenter";
import Customer360 from "@/pages/admin/Customer360";
import CustomerDetail from "@/pages/admin/CustomerDetail";
import LoyaltyConfigurator from "@/pages/admin/LoyaltyConfigurator";
import CouponEngine from "@/pages/admin/CouponEngine";
import CampaignManager from "@/pages/admin/CampaignManager";
import FundleBrain from "@/pages/admin/FundleBrain";
import APIMonitor from "@/pages/admin/APIMonitor";
import UserManagement from "@/pages/admin/UserManagement";
import StoresPage from "@/pages/admin/Stores";
import NPSPage from "@/pages/admin/NPS";
import TicketsPage from "@/pages/admin/Tickets";
import TicketDetail from "@/pages/admin/TicketDetail";
import ReportsPage from "@/pages/admin/Reports";
import ItemMaster from "@/pages/admin/ItemMaster";
import CMSPage from "@/pages/admin/CMS";
import SalesDashboard from "@/pages/admin/dashboards/SalesDashboard";
import CustomerDashboard from "@/pages/admin/dashboards/CustomerDashboard";
import LoyaltyDashboard from "@/pages/admin/dashboards/LoyaltyDashboard";
import CampaignDashboard from "@/pages/admin/dashboards/CampaignDashboard";
import StoreDashboard from "@/pages/admin/dashboards/StoreDashboard";
import NPSDashboard from "@/pages/admin/dashboards/NPSDashboard";
import RFMDashboard from "@/pages/admin/dashboards/RFMDashboard";
import CohortsDashboard from "@/pages/admin/dashboards/CohortsDashboard";
import PointsDashboard from "@/pages/admin/dashboards/PointsDashboard";
import CampaignROIDashboard from "@/pages/admin/dashboards/CampaignROIDashboard";
import ExecutiveSummary from "@/pages/admin/dashboards/ExecutiveSummary";
import FormulaCatalog from "@/pages/admin/FormulaCatalog";
import StoreOps from "@/pages/store/StoreOps";

function ProtectedRoute({ children, roles }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="min-h-screen flex items-center justify-center"><div className="font-display text-2xl">Loading…</div></div>;
  if (!user) return <Navigate to="/enterprise/login" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/admin" replace />;
  return children;
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Toaster position="top-right" richColors />
        <Routes>
          {/* Public site */}
          <Route element={<PublicLayout />}>
            <Route path="/" element={<Home />} />
            <Route path="/about-program" element={<AboutProgram />} />
            <Route path="/loyalty-benefits" element={<LoyaltyBenefits />} />
            <Route path="/rewards" element={<Rewards />} />
            <Route path="/how-it-works" element={<HowItWorks />} />
            <Route path="/earn-points" element={<EarnPoints />} />
            <Route path="/redeem-points" element={<RedeemPoints />} />
            <Route path="/referral-program" element={<ReferralProgram />} />
            <Route path="/store-locator" element={<StoreLocator />} />
            <Route path="/faqs" element={<FAQs />} />
            <Route path="/privacy" element={<Privacy />} />
            <Route path="/terms" element={<Terms />} />
            <Route path="/contact" element={<Contact />} />
          </Route>

          {/* Auth */}
          <Route path="/enterprise/login" element={<EnterpriseLogin />} />
          <Route path="/store/login" element={<StoreLogin />} />
          <Route path="/crm/login" element={<CRMLogin />} />

          {/* Admin */}
          <Route path="/admin" element={<ProtectedRoute><AdminLayout /></ProtectedRoute>}>
            <Route index element={<CommandCenter />} />
            <Route path="cockpit" element={<ExecutiveCockpit />} />
            <Route path="dashboards/sales" element={<SalesDashboard />} />
            <Route path="dashboards/customers" element={<CustomerDashboard />} />
            <Route path="dashboards/loyalty" element={<LoyaltyDashboard />} />
            <Route path="dashboards/campaigns" element={<CampaignDashboard />} />
            <Route path="dashboards/stores" element={<StoreDashboard />} />
            <Route path="dashboards/nps" element={<NPSDashboard />} />
            <Route path="dashboards/rfm" element={<RFMDashboard />} />
            <Route path="dashboards/cohorts" element={<CohortsDashboard />} />
            <Route path="dashboards/points" element={<PointsDashboard />} />
            <Route path="dashboards/campaign-roi" element={<CampaignROIDashboard />} />
            <Route path="dashboards/executive-summary" element={<ExecutiveSummary />} />
            <Route path="formula-catalog" element={<FormulaCatalog />} />
            <Route path="customers" element={<Customer360 />} />
            <Route path="customers/:id" element={<CustomerDetail />} />
            <Route path="loyalty" element={<LoyaltyConfigurator />} />
            <Route path="coupons" element={<CouponEngine />} />
            <Route path="campaigns" element={<CampaignManager />} />
            <Route path="ai" element={<FundleBrain />} />
            <Route path="api-monitor" element={<APIMonitor />} />
            <Route path="users" element={<ProtectedRoute roles={["super_admin","brand_admin"]}><UserManagement /></ProtectedRoute>} />
            <Route path="stores" element={<StoresPage />} />
            <Route path="items" element={<ItemMaster />} />
            <Route path="cms" element={<CMSPage />} />
            <Route path="nps" element={<NPSPage />} />
            <Route path="tickets" element={<TicketsPage />} />
            <Route path="tickets/:id" element={<TicketDetail />} />
            <Route path="reports" element={<ReportsPage />} />
          </Route>

          {/* Store ops portal */}
          <Route path="/store" element={<ProtectedRoute roles={["store_manager","store_staff","super_admin","brand_admin"]}><StoreOps /></ProtectedRoute>} />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
