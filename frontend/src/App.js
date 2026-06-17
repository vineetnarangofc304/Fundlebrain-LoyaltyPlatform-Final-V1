import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { useEffect } from "react";
import { AuthProvider, useAuth } from "@/lib/auth";
import { TourProvider } from "@/components/tour/TourProvider";
import { BRAND } from "@/brand.config";
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
import TemplatesPage from "@/pages/admin/communications/TemplatesPage";
import ProviderSettingsPage from "@/pages/admin/communications/ProviderSettingsPage";
import BulkJobsPage from "@/pages/admin/communications/BulkJobsPage";
import MessageLogPage from "@/pages/admin/communications/MessageLogPage";
import AutoCampaignsPage from "@/pages/admin/AutoCampaignsPage";
import RawReportsPage from "@/pages/admin/RawReportsPage";
import DigestsPage from "@/pages/admin/DigestsPage";
import HistoricDataPage from "@/pages/admin/HistoricDataPage";
import VerifyLoadPage from "@/pages/admin/VerifyLoadPage";
import ReconciliationPage from "@/pages/admin/ReconciliationPage";
import SegmentBuilderPage from "@/pages/admin/SegmentBuilderPage";
import LiveMonitorPage from "@/pages/admin/LiveMonitorPage";
import POSCredentialsPage from "@/pages/admin/POSCredentialsPage";
import SearchRedeemPointsOTP from "@/pages/admin/support_desk/SearchRedeemPointsOTP";
import SearchRedeemCouponOTP from "@/pages/admin/support_desk/SearchRedeemCouponOTP";
import ReactivateCoupon from "@/pages/admin/support_desk/ReactivateCoupon";
import ReactivateRedeemPoints from "@/pages/admin/support_desk/ReactivateRedeemPoints";
import CustomerDeactivate from "@/pages/admin/support_desk/CustomerDeactivate";
import CustomerReactivate from "@/pages/admin/support_desk/CustomerReactivate";
import UnsubscribeCustomer from "@/pages/admin/support_desk/UnsubscribeCustomer";
import SupportDeskAuditLog from "@/pages/admin/support_desk/SupportDeskAuditLog";
import LegacyReportsHub from "@/pages/admin/legacy_reports/LegacyReportsHub";
import ShopperBillReport from "@/pages/admin/ShopperBillReport";
import LRCustomerData from "@/pages/admin/legacy_reports/CustomerData";
import LRTransactionData from "@/pages/admin/legacy_reports/TransactionData";
import LRRepeatCustomers from "@/pages/admin/legacy_reports/RepeatCustomers";
import LRTopCustomers from "@/pages/admin/legacy_reports/TopCustomers";
import LRFraudReport from "@/pages/admin/legacy_reports/FraudReport";
import LRPendingBills from "@/pages/admin/legacy_reports/PendingBills";
import LRFeedbackData from "@/pages/admin/legacy_reports/FeedbackData";
import LRMissedCalls from "@/pages/admin/legacy_reports/MissedCalls";
import LRLocationWise from "@/pages/admin/legacy_reports/LocationWiseCustomers";
import LRExpiryPoints from "@/pages/admin/legacy_reports/ExpiryPoints";
import LRActiveCoupons from "@/pages/admin/legacy_reports/ActiveCoupons";
import StoreOps from "@/pages/store/StoreOps";
import DemoLanding from "@/pages/public/DemoLanding";

function ProtectedRoute({ children, roles }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="min-h-screen flex items-center justify-center"><div className="font-display text-2xl">Loading…</div></div>;
  if (!user) return <Navigate to="/enterprise/login" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/admin" replace />;
  return children;
}

function App() {
  // Inject brand colour palette as CSS variables once at mount.
  // Changing values in brand.config.js will reflect everywhere using
  // the existing --kazo-* CSS variables — no per-component edits.
  useEffect(() => {
    const r = document.documentElement.style;
    r.setProperty("--kazo-black", BRAND.colors.black);
    r.setProperty("--kazo-cream", BRAND.colors.cream);
    r.setProperty("--kazo-burgundy", BRAND.colors.burgundy);
    r.setProperty("--kazo-burgundy-deep", BRAND.colors.burgundyDeep);
    r.setProperty("--kazo-champagne", BRAND.colors.champagne);
    r.setProperty("--kazo-champagne-light", BRAND.colors.champagneLight);
  }, []);

  return (
    <AuthProvider>
      <BrowserRouter>
        <TourProvider>
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

          {/* Public self-running product demo */}
          <Route path="/demo" element={<DemoLanding />} />

          {/* Admin */}
          <Route path="/admin" element={<ProtectedRoute><AdminLayout /></ProtectedRoute>}>
            <Route index element={<CommandCenter />} />
            <Route path="dashboards" element={<CommandCenter />} />
            <Route path="dashboards/command-center" element={<CommandCenter />} />
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
            <Route path="communications/templates" element={<TemplatesPage />} />
            <Route path="communications/message-log" element={<MessageLogPage />} />
            <Route path="communications/bulk-jobs" element={<BulkJobsPage />} />
            <Route path="communications/settings" element={<ProviderSettingsPage />} />
            <Route path="customers" element={<Customer360 />} />
            <Route path="customers/:id" element={<CustomerDetail />} />
            <Route path="loyalty" element={<LoyaltyConfigurator />} />
            <Route path="coupons" element={<CouponEngine />} />
            <Route path="campaigns" element={<CampaignManager />} />
            <Route path="auto-campaigns" element={<ProtectedRoute roles={["super_admin","brand_admin","crm_manager","marketing_manager"]}><AutoCampaignsPage /></ProtectedRoute>} />
            <Route path="raw-reports" element={<RawReportsPage />} />
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
            <Route path="reports/digests" element={<DigestsPage />} />
            <Route path="historic-data" element={<ProtectedRoute roles={["super_admin","brand_admin","crm_manager","marketing_manager"]}><HistoricDataPage /></ProtectedRoute>} />
            <Route path="verify-load" element={<ProtectedRoute roles={["super_admin","brand_admin","crm_manager","marketing_manager"]}><VerifyLoadPage /></ProtectedRoute>} />
            <Route path="reconciliation" element={<ProtectedRoute roles={["super_admin","brand_admin"]}><ReconciliationPage /></ProtectedRoute>} />
            <Route path="segments" element={<ProtectedRoute roles={["super_admin","brand_admin","crm_manager","marketing_manager"]}><SegmentBuilderPage /></ProtectedRoute>} />
            <Route path="live-monitor" element={<LiveMonitorPage />} />
            <Route path="pos-credentials" element={<ProtectedRoute roles={["super_admin","brand_admin"]}><POSCredentialsPage /></ProtectedRoute>} />

            {/* Support Desk — L1 operations */}
            <Route path="support-desk/search-redeem-points-otp" element={<ProtectedRoute roles={["super_admin","brand_admin","support_agent","crm_manager"]}><SearchRedeemPointsOTP /></ProtectedRoute>} />
            <Route path="support-desk/search-redeem-coupon-otp" element={<ProtectedRoute roles={["super_admin","brand_admin","support_agent","crm_manager"]}><SearchRedeemCouponOTP /></ProtectedRoute>} />
            <Route path="support-desk/reactivate-coupon" element={<ProtectedRoute roles={["super_admin","brand_admin","support_agent"]}><ReactivateCoupon /></ProtectedRoute>} />
            <Route path="support-desk/reactivate-redeem-points" element={<ProtectedRoute roles={["super_admin","brand_admin","support_agent"]}><ReactivateRedeemPoints /></ProtectedRoute>} />
            <Route path="support-desk/customer-deactivate" element={<ProtectedRoute roles={["super_admin","brand_admin","support_agent"]}><CustomerDeactivate /></ProtectedRoute>} />
            <Route path="support-desk/customer-reactivate" element={<ProtectedRoute roles={["super_admin","brand_admin","support_agent"]}><CustomerReactivate /></ProtectedRoute>} />
            <Route path="support-desk/unsubscribe" element={<ProtectedRoute roles={["super_admin","brand_admin","support_agent"]}><UnsubscribeCustomer /></ProtectedRoute>} />
            <Route path="support-desk/audit-log" element={<ProtectedRoute roles={["super_admin","brand_admin","support_agent","crm_manager"]}><SupportDeskAuditLog /></ProtectedRoute>} />

            {/* Legacy Reports — mirrors fundlezone.com Analytics */}
            <Route path="legacy-reports" element={<ProtectedRoute><LegacyReportsHub /></ProtectedRoute>} />
            <Route path="legacy-reports/customer-data" element={<ProtectedRoute><LRCustomerData /></ProtectedRoute>} />
            <Route path="legacy-reports/transaction-data" element={<ProtectedRoute><LRTransactionData /></ProtectedRoute>} />
            <Route path="legacy-reports/repeat-customers" element={<ProtectedRoute><LRRepeatCustomers /></ProtectedRoute>} />
            <Route path="legacy-reports/top-customers" element={<ProtectedRoute><LRTopCustomers /></ProtectedRoute>} />
            <Route path="legacy-reports/fraud-report" element={<ProtectedRoute><LRFraudReport /></ProtectedRoute>} />
            <Route path="legacy-reports/pending-bills" element={<ProtectedRoute><LRPendingBills /></ProtectedRoute>} />
            <Route path="legacy-reports/feedback-data" element={<ProtectedRoute><LRFeedbackData /></ProtectedRoute>} />
            <Route path="legacy-reports/missed-calls" element={<ProtectedRoute><LRMissedCalls /></ProtectedRoute>} />
            <Route path="legacy-reports/location-wise-customers" element={<ProtectedRoute><LRLocationWise /></ProtectedRoute>} />
            <Route path="legacy-reports/expiry-points" element={<ProtectedRoute><LRExpiryPoints /></ProtectedRoute>} />
            <Route path="legacy-reports/active-coupons" element={<ProtectedRoute><LRActiveCoupons /></ProtectedRoute>} />
            <Route path="reports/shopper-bills" element={<ProtectedRoute><ShopperBillReport /></ProtectedRoute>} />
          </Route>

          {/* Store ops portal */}
          <Route path="/store" element={<ProtectedRoute roles={["store_manager","store_staff","super_admin","brand_admin"]}><StoreOps /></ProtectedRoute>} />

          <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </TourProvider>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
