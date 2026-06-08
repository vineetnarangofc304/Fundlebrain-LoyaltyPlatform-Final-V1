/**
 * Fundle product-demo script.
 * Each step drives the LIVE app: navigate to `route`, spotlight the sidebar nav
 * item `nav` (its data-testid), show the branded caption card and play the
 * narration `say` (OpenAI TTS). The full tour ≈ 5 min; each section demo ≈ 2 min.
 *
 * `nav` is optional — when null we skip the spotlight and just narrate over the page.
 */

// ---- Section catalogue (also rendered as the "Tutorials" grid on /demo) ----
// icon = lucide-react component name (mapped in DemoLanding.jsx)

export const SECTIONS = [
  {
    id: "command-center",
    title: "Command Center",
    icon: "LayoutDashboard",
    blurb: "The single-screen pulse of the business — sales, customers, points liability and an AI intelligence report, all live.",
    steps: [
      {
        id: "cc-1", route: "/admin", nav: "nav-command-center",
        title: "Command Center",
        say: "This is the Command Center — the living pulse of your loyalty programme. Net sales, average order value, active customers, points liability and API health are computed live, the moment a bill lands.",
      },
      {
        id: "cc-2", route: "/admin", nav: null,
        title: "Fundle Brain · AI Intelligence Report",
        say: "At the top, Fundle Brain writes a plain-English intelligence report from the live numbers — surfacing what changed, what's at risk, and where the next rupee of growth is hiding. No analyst required.",
      },
      {
        id: "cc-3", route: "/admin", nav: null,
        title: "Trends & acquisition cohorts",
        say: "Below, the revenue trend and acquisition cohorts show how customers flow in over time. Every card is filterable by city and store, so leadership can slice the business in seconds.",
      },
    ],
  },
  {
    id: "live-monitor",
    title: "Live Bill Monitor",
    icon: "Radio",
    blurb: "Watch bills, points and redemptions stream in from every store in real time.",
    steps: [
      {
        id: "lm-1", route: "/admin/live-monitor", nav: "nav-live-monitor",
        title: "Live Bill Monitor",
        say: "Every transaction from every POS terminal streams in here in real time. As a store rings up a sale, the bill, the points earned and the customer appear instantly — your nerve centre for live operations.",
      },
    ],
  },
  {
    id: "sales",
    title: "Sales Analytics",
    icon: "TrendingUp",
    blurb: "Revenue, bills, AOV and units — trended and broken down by store, city and time.",
    steps: [
      {
        id: "sl-1", route: "/admin/dashboards/sales", nav: "nav-dash-sales",
        title: "Sales Analytics",
        say: "The Sales dashboard turns raw bills into decisions — revenue, order counts, average order value and units per transaction, trended over any period and broken down by store and city.",
      },
      {
        id: "sl-2", route: "/admin/dashboards/sales", nav: null,
        title: "Loyalty-attributed revenue",
        say: "Crucially, it separates loyalty-attributed revenue from the rest — so you can prove, in rupees, exactly what the programme is contributing to the top line.",
      },
    ],
  },
  {
    id: "customer-analytics",
    title: "Customer Analytics",
    icon: "UserRound",
    blurb: "New vs repeat, tier movement, recency and lifetime value across your whole base.",
    steps: [
      {
        id: "ca-1", route: "/admin/dashboards/customers", nav: "nav-dash-customers",
        title: "Customer Analytics",
        say: "Here you understand who your customers really are — new versus repeat, how they move between tiers, their recency, and their lifetime value. This is the difference between a database and a relationship.",
      },
    ],
  },
  {
    id: "loyalty",
    title: "Loyalty & Points",
    icon: "Award",
    blurb: "Earn, burn, bonus and expiry — plus the points liability sitting on your books.",
    steps: [
      {
        id: "ly-1", route: "/admin/dashboards/loyalty", nav: "nav-dash-loyalty",
        title: "Loyalty & Points Health",
        say: "The Loyalty dashboard tracks the full points economy — earned, redeemed, bonus and expired — and the outstanding liability sitting on your books, valued in rupees. Finance and marketing finally see the same number.",
      },
    ],
  },
  {
    id: "campaign-performance",
    title: "Campaign Performance",
    icon: "BarChart3",
    blurb: "Sends, opens, clicks and conversions for every campaign you run.",
    steps: [
      {
        id: "cp-1", route: "/admin/dashboards/campaigns", nav: "nav-dash-campaigns",
        title: "Campaign Performance",
        say: "Every campaign you send — SMS, WhatsApp or RCS — is measured end to end: delivered, opened, clicked and converted. You see what's working while it's still running.",
      },
    ],
  },
  {
    id: "campaign-roi",
    title: "Campaign ROI",
    icon: "BarChart3",
    blurb: "Attributed sales and return-on-investment for each campaign and coupon.",
    steps: [
      {
        id: "roi-1", route: "/admin/dashboards/campaign-roi", nav: "nav-dash-campaign-roi",
        title: "Campaign ROI",
        say: "And this is where marketing earns its budget — attributed sales and true return on investment for every campaign and coupon, so you can double down on the winners and cut the rest.",
      },
    ],
  },
  {
    id: "rfm-churn",
    title: "RFM & Churn",
    icon: "Layers",
    blurb: "Recency-Frequency-Monetary segments and the customers quietly slipping away.",
    steps: [
      {
        id: "rf-1", route: "/admin/dashboards/rfm", nav: "nav-dash-rfm",
        title: "RFM & Churn",
        say: "The RFM and Churn view automatically scores every customer on recency, frequency and spend — pinpointing your champions, your loyalists, and the customers quietly slipping away so you can win them back before they're gone.",
      },
    ],
  },
  {
    id: "cohorts",
    title: "Cohorts & Segments",
    icon: "Users",
    blurb: "Retention curves by signup window — see how each cohort behaves over time.",
    steps: [
      {
        id: "co-1", route: "/admin/dashboards/cohorts", nav: "nav-dash-cohorts",
        title: "Cohorts & Retention",
        say: "Cohort analysis shows how each group of customers behaves month after month from the day they joined — the truest measure of whether your loyalty programme is building lasting habits.",
      },
    ],
  },
  {
    id: "points-economics",
    title: "Points Economics",
    icon: "Award",
    blurb: "Breakage, liability and the real cost-of-rewards behind your programme.",
    steps: [
      {
        id: "pe-1", route: "/admin/dashboards/points", nav: "nav-dash-points",
        title: "Points Economics",
        say: "Points Economics exposes the financial engine of the programme — issuance, breakage and liability — so you can tune your earn and burn rates with confidence, not guesswork.",
      },
    ],
  },
  {
    id: "fundle-brain",
    title: "Fundle Brain (AI)",
    icon: "Brain",
    blurb: "Ask anything in plain English — Fundle Brain queries your live data and answers instantly.",
    steps: [
      {
        id: "fb-1", route: "/admin/ai", nav: "nav-ai",
        title: "Fundle Brain — your AI analyst",
        say: "This is Fundle Brain, your built-in AI analyst. Ask anything in plain English — who are my top customers in Mumbai, which campaign drove the most revenue, how much points liability do I carry — and it queries your live data and answers in seconds.",
      },
      {
        id: "fb-2", route: "/admin/ai", nav: null,
        title: "From insight to action",
        say: "Fundle Brain doesn't just report — with the right permissions it can act, running support tasks and pulling any report on command. It's like hiring a data team that never sleeps.",
      },
    ],
  },
  {
    id: "segment-builder",
    title: "Segment Builder",
    icon: "Filter",
    blurb: "Build precise audiences with point-and-click rules — no SQL required.",
    steps: [
      {
        id: "sb-1", route: "/admin/segments", nav: "nav-segments",
        title: "Segment Builder",
        say: "The Segment Builder lets anyone craft precise audiences with simple point-and-click rules — high-value customers in Delhi who haven't shopped in ninety days, for example — and push them straight into a campaign. No SQL, no waiting on IT.",
      },
    ],
  },
  {
    id: "campaigns",
    title: "Campaign Manager",
    icon: "Send",
    blurb: "Design and launch SMS, WhatsApp and RCS journeys to any segment.",
    steps: [
      {
        id: "cm-1", route: "/admin/campaigns", nav: "nav-campaigns",
        title: "Campaign Manager",
        say: "From here you design and launch campaigns across SMS, WhatsApp and RCS — to a hand-built segment or an automated trigger like a birthday or a lapsing customer. Personalised, measurable, and live in minutes.",
      },
    ],
  },
  {
    id: "coupons",
    title: "Coupon Engine",
    icon: "Ticket",
    blurb: "Issue, track and redeem coupons with full fraud-safe OTP validation.",
    steps: [
      {
        id: "cn-1", route: "/admin/coupons", nav: "nav-coupons",
        title: "Coupon Engine",
        say: "The Coupon Engine issues and tracks every offer with fraud-safe OTP validation at the till — so you reward genuine customers, capture the redemption data, and never leak margin to misuse.",
      },
    ],
  },
  {
    id: "support-desk",
    title: "Support Desk",
    icon: "ShieldCheck",
    blurb: "L1 operations — OTP lookups, reactivations, unsubscribes — all audit-logged.",
    steps: [
      {
        id: "sd-1", route: "/admin/support-desk/audit-log", nav: "nav-sd-audit",
        title: "Support Desk & Audit Trail",
        say: "The Support Desk gives your front-line team safe, one-click tools — look up an OTP, reactivate a coupon, unsubscribe a customer — and every single action is captured in a tamper-evident audit log for full compliance.",
      },
    ],
  },
  {
    id: "legacy-reports",
    title: "Reports Hub",
    icon: "FileBarChart",
    blurb: "Every legacy report — fraud, top customers, pending bills and more — with filters and exports.",
    steps: [
      {
        id: "lr-1", route: "/admin/legacy-reports", nav: "nav-legacy-reports",
        title: "Reports Hub",
        say: "Everything your team relied on in the old system lives here and more — customer, transaction and fraud reports, top customers, pending bills and expiring points — each filterable and exportable to CSV, Excel or PDF in a click.",
      },
    ],
  },
  {
    id: "user-management",
    title: "User Management",
    icon: "UserCog",
    blurb: "Role-based access for every team — from super admins to store staff.",
    steps: [
      {
        id: "um-1", route: "/admin/users", nav: "nav-users",
        title: "Users & Role-Based Access",
        say: "Finally, granular role-based access control means the right people see the right things — leadership, marketing, analysts, regional managers and store staff each get a tailored, secure view of the platform.",
      },
    ],
  },
  {
    id: "api-monitor",
    title: "API Monitor",
    icon: "Activity",
    blurb: "Live health of every POS integration — uptime, latency and errors.",
    steps: [
      {
        id: "am-1", route: "/admin/api-monitor", nav: "nav-api",
        title: "API & Integration Monitor",
        say: "And under the hood, the API Monitor tracks the health of every POS integration in real time — uptime, latency and errors — so your data pipeline is always trustworthy and any issue is caught instantly.",
      },
    ],
  },
];

// Quick lookup by id (used by section "tutorials")
export const SECTION_MAP = SECTIONS.reduce((m, s) => { m[s.id] = s; return m; }, {});

// ---- Welcome + closing bookends for the full tour ----
const WELCOME = {
  id: "welcome", route: "/admin", nav: null,
  title: "Welcome to KAZO · Powered by Fundle",
  say: "Welcome to the KAZO loyalty and customer-intelligence platform, powered by Fundle. Over the next few minutes I'll walk you through the live platform — the dashboards, the AI, campaigns, support and reporting. Sit back and watch it run.",
};

const CLOSING = {
  id: "closing", route: "/admin", nav: null,
  title: "That's the Fundle platform",
  say: "That's a whirlwind tour of the platform — one connected system for loyalty, analytics, campaigns, support and reporting, with Fundle Brain tying it all together. Explore any section on your own, or get in touch to see it with your own data. Thank you for watching.",
};

// ---- The full ~5-minute tour: welcome → first step of every section → closing ----
export const FULL_TOUR = [
  WELCOME,
  ...SECTIONS.map((s) => s.steps[0]),
  CLOSING,
];

// Build a 2-min section demo (its own steps, bookended lightly)
export function sectionTour(sectionId) {
  const s = SECTION_MAP[sectionId];
  if (!s) return [];
  return s.steps;
}

export const DEFAULT_VOICE = "nova";
