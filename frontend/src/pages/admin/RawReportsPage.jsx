import { useState } from "react";
import { PageHeader } from "./_shared";
import { BarChart3, Users, Receipt, Repeat, Coins, TrendingUp } from "lucide-react";
import CustomerDataReport from "./raw_reports/_customer_data_report";
import TransactionDataReport from "./raw_reports/_transaction_data_report";
import RepeatPurchasesReport from "./raw_reports/_repeat_purchases_report";
import EarnRedeemReport from "./raw_reports/_earn_redeem_report";
import CustomersByVisitReport from "./raw_reports/_customers_by_visit_report";

const TABS = [
  { key: "customer-data",       label: "Customer Data",       icon: Users,      Comp: CustomerDataReport },
  { key: "transaction-data",    label: "Transaction Data",    icon: Receipt,    Comp: TransactionDataReport },
  { key: "repeat-purchases",    label: "Repeat Purchases",    icon: Repeat,     Comp: RepeatPurchasesReport },
  { key: "earn-redeem",         label: "Earn-Redeem",         icon: Coins,      Comp: EarnRedeemReport },
  { key: "customers-by-visit",  label: "Customers by Visit",  icon: TrendingUp, Comp: CustomersByVisitReport },
];

export default function RawReportsPage() {
  const [activeTab, setActiveTab] = useState("customer-data");
  const tab = TABS.find((t) => t.key === activeTab);
  const Comp = tab.Comp;

  return (
    <div data-testid="raw-reports-page">
      <PageHeader
        title="Raw Data Reports"
        subtitle="HIGH-DENSITY OPERATIONAL REPORTS · AI-CURATED · DRILL-DOWN ENABLED"
      />
      <div className="px-8 pt-4">
        <div className="flex gap-1 border-b border-neutral-200 overflow-x-auto" data-testid="raw-reports-tabs">
          {TABS.map((t) => {
            const Icon = t.icon;
            const isActive = activeTab === t.key;
            return (
              <button
                key={t.key}
                onClick={() => setActiveTab(t.key)}
                data-testid={`tab-${t.key}`}
                className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-medium border-b-2 transition whitespace-nowrap ${
                  isActive
                    ? "border-burgundy text-burgundy bg-amber-50/30"
                    : "border-transparent text-neutral-500 hover:text-neutral-800 hover:bg-neutral-50"
                }`}
                style={isActive ? { borderColor: "#9b2c2c", color: "#9b2c2c" } : {}}
              >
                <Icon className="w-3.5 h-3.5" />
                {t.label}
              </button>
            );
          })}
        </div>
      </div>
      <div className="px-8 py-6">
        <Comp />
      </div>
    </div>
  );
}
