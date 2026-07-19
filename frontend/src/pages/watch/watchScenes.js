// Scripted scene choreography for the /watch cinematic demo reel.
// Narration TEXT (voiceover + captions) is fetched from GET /api/watch/script — the backend is
// the single source of truth. Here we only define the visual BEATS per scene, keyed by scene id.

export const CHART = ["#C7A76D", "#571326", "#94A3B8", "#0F172A"];

export const SCENES = [
  {
    id: "open",
    kind: "title",
    variant: "hero",
    brandLine: "FUNDLE",
    subtitle: "The intelligence behind your loyalty program",
    kicker: "A film in two acts",
  },
  {
    id: "act1",
    kind: "title",
    eyebrow: "Act One",
    title: "Fundle Brain",
    subtitle: "The Analyst — think, ask, understand.",
    accent: "champagne",
  },
  {
    id: "fb_underperform",
    kind: "chat",
    brain: "fundle",
    beats: [
      { k: "user", text: "Which of my stores are underperforming this quarter?" },
      { k: "tool", label: "Reading live sales · 64 stores", result: "0.8s" },
      { k: "assistant", text: "Six stores are trending below target this quarter. Here's the picture:" },
      {
        k: "chart", kind: "bar", xKey: "store",
        series: [{ key: "revenue", name: "Revenue (₹L)", color: CHART[0] }, { key: "target", name: "Target (₹L)", color: CHART[2] }],
        data: [
          { store: "Jaipur", revenue: 42, target: 54 },
          { store: "Surat", revenue: 38, target: 46 },
          { store: "Nagpur", revenue: 51, target: 58 },
          { store: "Kochi", revenue: 47, target: 52 },
          { store: "Indore", revenue: 55, target: 60 },
          { store: "Bhopal", revenue: 49, target: 53 },
        ],
      },
      { k: "insight", text: "Jaipur and Surat are down 22% and 18% vs last quarter — driven by a fall in repeat customers, not footfall. Recommend a targeted win-back for their lapsed Gold members." },
    ],
  },
  {
    id: "fb_churn",
    kind: "chat",
    brain: "fundle",
    beats: [
      { k: "user", text: "Show me customers at risk of churning — and what they're worth." },
      { k: "tool", label: "Scoring 8,42,000 customers · RFM + recency", result: "1.2s" },
      { k: "assistant", text: "12,480 high-value customers are slipping into churn:" },
      {
        k: "kpis", items: [
          { label: "At-risk customers", value: "12,480" },
          { label: "Revenue at risk", value: "₹4.6 Cr" },
          { label: "Avg days since visit", value: "142" },
        ],
      },
      { k: "insight", text: "Mostly Gold & Platinum members who used to shop every 6 weeks. A single 2X-points win-back historically recovers 31% of them — around ₹1.4 Cr back in play." },
    ],
  },
  {
    id: "fb_diagnose",
    kind: "chat",
    brain: "fundle",
    beats: [
      { k: "user", text: "Why did loyalty redemptions drop in June?" },
      { k: "tool", label: "Tracing redemptions · Apr–Jun", result: "done" },
      { k: "assistant", text: "Redemptions fell 34% in June. The cause isn't demand — it's friction:" },
      {
        k: "chart", kind: "line", xKey: "week",
        series: [{ key: "redemptions", name: "Redemptions", color: CHART[0] }],
        data: [
          { week: "Apr W1", redemptions: 9200 }, { week: "Apr W3", redemptions: 9600 },
          { week: "May W1", redemptions: 9400 }, { week: "May W3", redemptions: 9100 },
          { week: "Jun W1", redemptions: 7200 }, { week: "Jun W3", redemptions: 5100 },
        ],
      },
      { k: "insight", text: "Two things line up with the drop: OTP delivery failures spiked mid-June, and the ₹500 reward tier sold out in 11 stores. Fix the OTP gateway and restock that tier to recover most of it." },
    ],
  },
  {
    id: "fb_upload",
    kind: "chat",
    brain: "fundle",
    beats: [
      { k: "user", text: "Analyse this — break down revenue by segment.", file: "sales_export_june.xlsx" },
      { k: "tool", label: "Reading sales_export_june.xlsx · 48,210 rows", result: "private" },
      { k: "assistant", text: "Done — analysed 48,210 bills, entirely inside your private workspace:" },
      {
        k: "table",
        columns: ["Segment", "Bills", "ATV", "Contribution"],
        rows: [
          ["Platinum", "3,910", "₹9,240", "41%"],
          ["Gold", "11,430", "₹4,180", "34%"],
          ["Silver", "18,220", "₹2,110", "18%"],
          ["New", "14,650", "₹1,540", "7%"],
        ],
      },
      { k: "insight", text: "Your top 8% of customers drive 41% of revenue — but haven't been messaged in 60 days. That's your fastest win this month." },
    ],
  },
  {
    id: "act2",
    kind: "title",
    eyebrow: "Act Two",
    title: "Master Brain",
    subtitle: "The Executor — say it, and it's done.",
    accent: "burgundy",
  },
  {
    id: "mb_topup",
    kind: "chat",
    brain: "master",
    beats: [
      { k: "user", text: "Top up 500 points to every Gold customer who hasn't shopped in 90 days." },
      { k: "tool", label: "Finding matching customers", result: "4,120 matched" },
      { k: "assistant", text: "Here's the exact impact — nothing changes until you confirm:" },
      {
        k: "confirm", title: "Preview — Bulk Top-up",
        rows: [["Matched customers", "4,120"], ["Points each", "+500"], ["Total points", "20,60,000"], ["Est. reward cost", "₹2.06 L"]],
        confirmLabel: "Confirm & apply", executed: "Applied to 4,120 customers · audit #A9F2 · reversible",
      },
      { k: "insight", text: "Every action previews first, applies only on your yes, and can be undone in one click. Nothing happens without your approval." },
    ],
  },
  {
    id: "mb_campaign",
    kind: "chat",
    brain: "master",
    beats: [
      { k: "user", text: "Launch a win-back SMS campaign to customers lapsed over 6 months." },
      { k: "tool", label: "Building audience", result: "18,340 recipients" },
      { k: "assistant", text: "Audience ready and message drafted. Approve to send:" },
      {
        k: "confirm", title: "Preview — Win-back SMS",
        rows: [["Recipients", "18,340"], ["DLT template", "WINBACK_2X"], ["Message", "\u201cWe miss you! 2X points this week…\u201d"]],
        confirmLabel: "Send now", executed: "Campaign live · delivering via Karix DLT",
      },
      { k: "progress", label: "Delivering messages", total: 18340 },
      { k: "insight", text: "Sent to 18,340 lapsed customers in minutes — no marketing team, no manual list, no waiting." },
    ],
  },
  {
    id: "mb_reconcile",
    kind: "chat",
    brain: "master",
    beats: [
      { k: "user", text: "The point balances for these 3,000 customers are corrupted. Fix them." },
      { k: "tool", label: "Reading true ledger · 3,000 customers", result: "done" },
      { k: "assistant", text: "I recomputed each balance from the genuine ledger — wrong vs correct:" },
      {
        k: "table",
        columns: ["Mobile", "Wrong", "Genuine"],
        rows: [
          ["98•••••210", "875", "500"],
          ["98•••••442", "1,240", "760"],
          ["97•••••889", "−320", "0"],
          ["99•••••015", "2,050", "1,500"],
        ],
      },
      {
        k: "confirm", title: "Move all to genuine points",
        rows: [["Customers to fix", "2,884"], ["Already correct", "116"], ["Net change", "−9,42,600"]],
        confirmLabel: "Move to genuine", executed: "Corrected 2,884 · audit #B7C1 · reversible",
      },
      { k: "insight", text: "It only ever corrects once — run it again and it does nothing. Safe to use on live data." },
    ],
  },
  {
    id: "mb_rule",
    kind: "chat",
    brain: "master",
    beats: [
      { k: "user", text: "Make it double points — 10 per ₹100 — for the whole festive weekend." },
      { k: "tool", label: "Updating earn engine", result: "done" },
      {
        k: "confirm", title: "Preview — Loyalty Rule Change",
        rows: [["Earn rate", "5 → 10 pts / ₹100"], ["Window", "Fri–Sun · festive"], ["Scope", "All 64 stores"]],
        confirmLabel: "Go live", executed: "Rule live across 64 stores instantly",
      },
      { k: "insight", text: "Change the logic of your program yourself — instantly, without engineering — and roll it back the same way." },
    ],
  },
  {
    id: "mb_error",
    kind: "chat",
    brain: "master",
    beats: [
      { k: "user", text: "Reverse the duplicate bonus credits from yesterday's campaign." },
      { k: "tool", label: "Checking prior runs for this batch", result: "done" },
      { k: "assistant", tone: "warn", text: "Heads up — part of this was already reversed earlier today. I won't double-reverse." },
      {
        k: "confirm", title: "Idempotent adjustment", tone: "warn",
        rows: [["Already reversed", "1,204 customers"], ["Still outstanding", "318 customers"], ["Safe action", "Reverse the 318 only"]],
        confirmLabel: "Apply safe fix", executed: "Adjusted 318 · zero double-deductions",
      },
      { k: "insight", text: "This is the difference: Master Brain knows what's already happened and applies only the exact adjustment needed — so mistakes can't compound." },
    ],
  },
  {
    id: "close",
    kind: "title",
    variant: "cta",
    brandLine: "FUNDLE",
    subtitle: "Loyalty, run by intelligence.",
    tagline: "Lower cost · higher profit · fully in your control.",
  },
];
