/* Legacy Reports Hub — mirrors newu.fundlezone.com Analytics structure.
   Provides a single launcher for all 24 reports across Summary / Detailed / Campaign ROI. */
import { Link } from "react-router-dom";
import { PageHeader } from "../_shared";
import {
  Users, Receipt, RefreshCw, TrendingUp, Activity, AlertTriangle, FileClock,
  MessageCircle, PhoneIncoming, MapPin, Clock, Ticket, BarChart3, Coins,
  Send, Megaphone, MessageSquare, Radio,
} from "lucide-react";

const SECTIONS = [
  {
    label: "SUMMARY",
    description: "High-level rollups by Location / City / State / Zone / Month / Tier",
    items: [
      { to: "/admin/raw-reports?tab=customer-data", icon: Users, label: "Customer Data Summary",
        desc: "Customer counts grouped by location / tier / month — bar chart + table" },
      { to: "/admin/raw-reports?tab=transaction-data", icon: Receipt, label: "Transaction Summary",
        desc: "Total Points / Purchase / Bills / Unique Customers by location group" },
      { to: "/admin/raw-reports?tab=repeat-purchases", icon: RefreshCw, label: "Repeat Purchase Summary",
        desc: "Repeat-purchase counts split as Total / Current (90d) / Earlier per location" },
      { to: "/admin/raw-reports?tab=earn-redeem", icon: Coins, label: "Earn Burn Summary",
        desc: "Earn / Redeem / Bonus / Expired / Liability per location" },
      { to: "/admin/raw-reports?tab=customers-by-visit", icon: BarChart3, label: "Customers by Visits",
        desc: "Frequency distribution — how many customers visited N times" },
    ],
  },
  {
    label: "DETAILED",
    description: "Raw-level operational reports — drill-down filters and CSV exports",
    items: [
      { to: "/admin/live-monitor", icon: Activity, label: "Live Monitor",
        desc: "8 KPI cards + bill-by-bill stream — see new bills as they arrive" },
      { to: "/admin/legacy-reports/customer-data", icon: Users, label: "Customer Data",
        desc: "Raw customer list — full filter set (mobile / name / tier / location / date)" },
      { to: "/admin/legacy-reports/transaction-data", icon: Receipt, label: "Transaction Data",
        desc: "Raw bill list across all customers — date / mobile / store filters" },
      { to: "/admin/legacy-reports/repeat-customers", icon: RefreshCw, label: "Repeat Customers",
        desc: "All customers with 2 or more visits — sorted by visit count" },
      { to: "/admin/legacy-reports/top-customers", icon: TrendingUp, label: "Top Customers",
        desc: "Top N by Purchase / Visits / Points Balance" },
      { to: "/admin/legacy-reports/fraud-report", icon: AlertTriangle, label: "Fraud Report",
        desc: "Rapid-fire bills, large redemptions, suspicious patterns" },
      { to: "/admin/legacy-reports/pending-bills", icon: FileClock, label: "Pending Bills",
        desc: "Bills uploaded but not yet awarded points" },
      { to: "/admin/legacy-reports/feedback-data", icon: MessageCircle, label: "Feedback Data",
        desc: "Customer feedback responses — bucket / comment filters" },
      { to: "/admin/legacy-reports/missed-calls", icon: PhoneIncoming, label: "Missed Call Requests",
        desc: "IVR / missed-call captures (integration-ready)" },
      { to: "/admin/legacy-reports/location-wise-customers", icon: MapPin, label: "Location Wise Customer",
        desc: "Customer counts per store with city / state / zone filter" },
      { to: "/admin/legacy-reports/expiry-points", icon: Clock, label: "Expiry Points Report",
        desc: "Points expiring within N days — per customer with earliest expiry" },
      { to: "/admin/legacy-reports/active-coupons", icon: Ticket, label: "Active Coupon Report",
        desc: "Currently-issued unused coupons — code / customer / expiry filter" },
    ],
  },
  {
    label: "CAMPAIGN ROI",
    description: "Channel-wise ROI and send-level reports for marketing operations",
    items: [
      { to: "/admin/dashboards/campaigns", icon: Megaphone, label: "M'ktg Campaign ROI",
        desc: "Campaign-level ROI summary — uses existing Campaign Performance dashboard" },
      { to: "/admin/campaigns", icon: Send, label: "M'ktg Campaign Data",
        desc: "Per-campaign data — recipients, opens, clicks, conversions" },
      { to: "/admin/dashboards/campaign-roi", icon: BarChart3, label: "Coupon Campaign ROI",
        desc: "Coupon-driven sales attribution — uses existing Campaign ROI dashboard" },
      { to: "/admin/legacy-reports/active-coupons", icon: Ticket, label: "Coupon Redemption",
        desc: "Redeemed coupons with discount + bill linkage" },
      { to: "/admin/coupons", icon: Ticket, label: "Coupon Campaign",
        desc: "Coupon catalog + issuance manager" },
      { to: "/admin/dashboards/campaigns", icon: MessageSquare, label: "WhatsApp Campaign ROI",
        desc: "WhatsApp channel breakdown — coming soon as a dedicated view" },
      { to: "/admin/dashboards/campaigns", icon: Radio, label: "RCS Campaign ROI",
        desc: "RCS channel breakdown — coming soon as a dedicated view" },
    ],
  },
];

export default function LegacyReportsHub() {
  return (
    <div data-testid="legacy-reports-hub">
      <PageHeader
        title="Reports"
        subtitle="LEGACY-STYLE ANALYTICS · MIRRORS FUNDLE STRUCTURE"
      />
      <div className="p-8 space-y-8">
        {SECTIONS.map((section) => (
          <div key={section.label} data-testid={`lr-section-${section.label.toLowerCase().replace(/\s+/g, "-")}`}>
            <div className="mb-3">
              <h2 className="font-display text-2xl mb-1">{section.label}</h2>
              <p className="text-sm text-neutral-500">{section.description}</p>
            </div>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {section.items.map((item) => {
                const Icon = item.icon;
                return (
                  <Link
                    key={item.to + item.label}
                    to={item.to}
                    className="group block p-4 bg-white border border-black/10 hover:border-[var(--kazo-burgundy)] hover:shadow-md transition-all"
                    data-testid={`lr-card-${item.label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}
                  >
                    <div className="flex items-start gap-3">
                      <div className="w-9 h-9 flex items-center justify-center bg-neutral-100 group-hover:bg-[var(--kazo-burgundy)] group-hover:text-white transition-colors">
                        <Icon className="w-4 h-4" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-neutral-900 mb-0.5">{item.label}</div>
                        <p className="text-xs text-neutral-500 leading-snug line-clamp-2">{item.desc}</p>
                      </div>
                    </div>
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
