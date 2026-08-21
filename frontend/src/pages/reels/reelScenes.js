// Scripted scene choreography for the vertical (9:16) /reel marketing films.
// Narration TEXT (voiceover + captions) comes from GET /api/reel/script/{clip} — the backend
// is the single source of truth. Here we only define the visual BEATS per scene, keyed by id.

export const CHART = ["#C7A76D", "#94A3B8", "#571326", "#0F172A"];

export const CLIP_META = {
  platform: { title: "The Platform", subtitle: "Loyalty, run by two AI agents", label: "Fundle · Product" },
  fundle: { title: "Fundle Brain", subtitle: "Your loyalty analyst", label: "Fundle · Agent" },
  master: { title: "Master Brain", subtitle: "Your loyalty executor", label: "Fundle · Agent" },
};

export const CLIP_ORDER = ["platform", "fundle", "master"];

const fbUnderperform = {
  id: "", kind: "chat", brain: "fundle",
  beats: [
    { k: "user", text: "Which stores are underperforming this quarter?" },
    { k: "tool", label: "Reading live sales · 64 stores", result: "0.8s" },
    { k: "assistant", text: "Six stores are trending below target:" },
    {
      k: "chart", kind: "bar", xKey: "store",
      series: [{ key: "revenue", name: "Revenue", color: CHART[0] }, { key: "target", name: "Target", color: CHART[1] }],
      data: [
        { store: "Jaipur", revenue: 42, target: 54 },
        { store: "Surat", revenue: 38, target: 46 },
        { store: "Kochi", revenue: 47, target: 52 },
        { store: "Bhopal", revenue: 49, target: 53 },
      ],
    },
    { k: "insight", text: "Jaipur & Surat are down 22% — driven by a fall in repeat customers, not footfall. Win back their lapsed Gold members." },
  ],
};

export const CLIPS = {
  // ── CLIP 1 · PLATFORM ──────────────────────────────────────────────
  platform: [
    { id: "p_hook", kind: "hook", lines: ["800,000+ shoppers.", "1.5M+ bills.", "One loyalty brain."] },
    {
      id: "p_what", kind: "hook", tone: "statement",
      lines: ["Two AI agents.", "Trained on your data.", "Run in plain English."],
      sub: "Fundle turns your loyalty operation into intelligence.",
    },
    {
      id: "p_fundle", kind: "chat", brain: "fundle",
      beats: [
        { k: "user", text: "Which stores are underperforming this quarter?" },
        { k: "tool", label: "Reading live sales · 64 stores", result: "0.8s" },
        { k: "assistant", text: "Six stores are below target. Jaipur & Surat lead the drop:" },
        {
          k: "kpis", items: [
            { label: "Below target", value: "6" },
            { label: "Revenue gap", value: "₹1.2 Cr" },
            { label: "Cause", value: "Repeat ↓" },
          ],
        },
        { k: "insight", text: "It's a fall in repeat customers, not footfall — win back their lapsed Gold members." },
      ],
    },
    {
      id: "p_master", kind: "chat", brain: "master",
      beats: [
        { k: "user", text: "Top up 500 points to every Gold customer lapsed 90+ days." },
        { k: "tool", label: "Finding matching customers", result: "4,120 matched" },
        {
          k: "confirm", title: "Preview — Bulk Top-up",
          rows: [["Matched", "4,120"], ["Points each", "+500"], ["Est. cost", "₹2.06 L"]],
          confirmLabel: "Confirm & apply", executed: "Applied to 4,120 · audit #A9F2 · reversible",
        },
        { k: "insight", text: "Previews first, applies on your yes, and undone in one click." },
      ],
    },
    {
      id: "p_scale", kind: "stats",
      items: [
        { value: "64", label: "Stores live" },
        { value: "1.5M+", label: "Bills reconciled" },
        { value: "₹2.7B", label: "Revenue tracked" },
      ],
      pills: ["eWards POS", "Karix SMS", "WhatsApp", "Points engine", "RFM & Churn", "Campaigns"],
    },
    { id: "p_close", kind: "cta", tagline: "Loyalty, run by intelligence.", sub: "Trained by fundle.ai" },
  ],

  // ── CLIP 2 · FUNDLE BRAIN ──────────────────────────────────────────
  fundle: [
    { id: "f_hook", kind: "hook", lines: ["Ask your", "loyalty data", "anything."], sub: "In plain English." },
    { id: "f_intro", kind: "agent", name: "Fundle Brain", role: "Your loyalty analyst", tagline: "Trained by fundle.ai" },
    { ...fbUnderperform, id: "f_stores" },
    {
      id: "f_churn", kind: "chat", brain: "fundle",
      beats: [
        { k: "user", text: "Show me customers about to churn — and what they're worth." },
        { k: "tool", label: "Scoring 8,42,000 customers · RFM", result: "1.2s" },
        { k: "assistant", text: "12,480 high-value customers are slipping away:" },
        {
          k: "kpis", items: [
            { label: "At-risk", value: "12,480" },
            { label: "Revenue at risk", value: "₹4.6 Cr" },
            { label: "Recoverable", value: "₹1.4 Cr" },
          ],
        },
        { k: "insight", text: "A single 2X-points win-back historically recovers 31% of them." },
      ],
    },
    {
      id: "f_upload", kind: "chat", brain: "fundle",
      beats: [
        { k: "user", text: "Analyse this — revenue by segment.", file: "sales_june.xlsx" },
        { k: "tool", label: "Reading sales_june.xlsx · 48,210 rows", result: "private" },
        { k: "assistant", text: "Analysed inside your private workspace:" },
        {
          k: "table",
          columns: ["Segment", "Bills", "Contribution"],
          rows: [["Platinum", "3,910", "41%"], ["Gold", "11,430", "34%"], ["Silver", "18,220", "18%"], ["New", "14,650", "7%"]],
        },
        { k: "insight", text: "Your top 8% drive 41% of revenue — and haven't been messaged in 60 days." },
      ],
    },
    { id: "f_close", kind: "cta", tagline: "Your analyst, on demand.", sub: "Trained by fundle.ai" },
  ],

  // ── CLIP 3 · MASTER BRAIN ──────────────────────────────────────────
  master: [
    { id: "m_hook", kind: "hook", lines: ["Say it.", "It's done."] },
    { id: "m_intro", kind: "agent", name: "Master Brain", role: "Your loyalty executor", tagline: "Trained by fundle.ai" },
    {
      id: "m_topup", kind: "chat", brain: "master",
      beats: [
        { k: "user", text: "Top up 500 points to every Gold customer lapsed 90+ days." },
        { k: "tool", label: "Finding matching customers", result: "4,120 matched" },
        { k: "assistant", text: "Here's the exact impact — nothing changes until you confirm:" },
        {
          k: "confirm", title: "Preview — Bulk Top-up",
          rows: [["Matched customers", "4,120"], ["Points each", "+500"], ["Total points", "20,60,000"]],
          confirmLabel: "Confirm & apply", executed: "Applied to 4,120 · audit #A9F2 · reversible",
        },
        { k: "insight", text: "Every action previews first, applies on your yes, and undoes in one click." },
      ],
    },
    {
      id: "m_campaign", kind: "chat", brain: "master",
      beats: [
        { k: "user", text: "Launch a win-back SMS to customers lapsed over 6 months." },
        { k: "tool", label: "Building audience", result: "18,340 recipients" },
        {
          k: "confirm", title: "Preview — Win-back SMS",
          rows: [["Recipients", "18,340"], ["DLT template", "WINBACK_2X"], ["Message", "\u201cWe miss you! 2X points…\u201d"]],
          confirmLabel: "Send now", executed: "Campaign live · via Karix DLT",
        },
        { k: "progress", label: "Delivering messages", total: 18340 },
      ],
    },
    {
      id: "m_safe", kind: "chat", brain: "master",
      beats: [
        { k: "user", text: "Reverse the duplicate bonus credits from yesterday." },
        { k: "tool", label: "Checking prior runs for this batch", result: "done" },
        { k: "assistant", tone: "warn", text: "Heads up — part of this was already reversed. I won't double-reverse." },
        {
          k: "confirm", title: "Idempotent adjustment", tone: "warn",
          rows: [["Already reversed", "1,204"], ["Still outstanding", "318"], ["Safe action", "Reverse 318 only"]],
          confirmLabel: "Apply safe fix", executed: "Adjusted 318 · zero double-deductions",
        },
      ],
    },
    { id: "m_close", kind: "cta", tagline: "Your executor, on command.", sub: "Trained by fundle.ai" },
  ],
};
