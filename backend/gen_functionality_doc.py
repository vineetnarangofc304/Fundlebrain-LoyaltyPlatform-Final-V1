"""Generate the FundleBrain FUNCTIONALITY & FEATURES catalogue PDF (reportlab).
A module-by-module catalogue of everything actually built in the platform —
enumerated from the running backend route packages and frontend pages."""
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                HRFlowable, ListFlowable, ListItem, PageBreak)

OUT = "/app/frontend/public/FundleBrain_Functionality_Catalogue.pdf"
LOGO = "/app/backend/fundle_logo_black.png"
BURG = colors.HexColor("#6b1220")
BURG2 = colors.HexColor("#8a1a2b")
INK = colors.HexColor("#1a1a1a")
GREY = colors.HexColor("#555555")
LIGHT = colors.HexColor("#f3eaec")
LINE = colors.HexColor("#d9c3c8")

styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=styles["Heading1"], fontName="Helvetica-Bold",
                    fontSize=15, textColor=BURG, spaceBefore=14, spaceAfter=6, leading=19)
H2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName="Helvetica-Bold",
                    fontSize=11, textColor=BURG2, spaceBefore=9, spaceAfter=2, leading=14)
BODY = ParagraphStyle("BODY", parent=styles["BodyText"], fontName="Helvetica",
                      fontSize=9.2, textColor=INK, leading=13.2, spaceAfter=4, alignment=TA_LEFT)
SMALL = ParagraphStyle("SMALL", parent=BODY, fontSize=8, textColor=GREY, leading=11)
CELL = ParagraphStyle("CELL", parent=BODY, fontSize=8.4, leading=11.2, spaceAfter=0)
CELLB = ParagraphStyle("CELLB", parent=CELL, fontName="Helvetica-Bold")
TITLE = ParagraphStyle("TITLE", parent=styles["Title"], fontName="Helvetica-Bold",
                       fontSize=25, textColor=BURG, leading=29, alignment=TA_LEFT)
SUB = ParagraphStyle("SUB", parent=BODY, fontSize=12, textColor=GREY, leading=16)

story = []


def p(t, s=BODY):
    story.append(Paragraph(t, s))


def bullets(items, s=BODY):
    story.append(ListFlowable(
        [ListItem(Paragraph(x, s), leftIndent=6, value="•") for x in items],
        bulletType="bullet", start="•", leftIndent=12, bulletColor=BURG2, spaceAfter=6))


def table(header, rows, widths):
    data = [[Paragraph(h, CELLB) for h in header]]
    for r in rows:
        data.append([Paragraph(str(c), CELL) for c in r])
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BURG),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8.6),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))


def rule():
    story.append(Spacer(1, 2))
    story.append(HRFlowable(width="100%", thickness=0.8, color=LINE, spaceAfter=8))


def sec(title):
    p(title, H1)
    rule()


# ───────────────────────── COVER ─────────────────────────
story.append(Spacer(1, 40))
story.append(HRFlowable(width="100%", thickness=3, color=BURG, spaceAfter=18))
p("FundleBrain", TITLE)
p("Loyalty, CRM &amp; Customer-Intelligence Platform", SUB)
story.append(Spacer(1, 6))
p("Functionality &amp; Features Catalogue", ParagraphStyle(
    "t2", parent=SUB, textColor=BURG2, fontSize=13, fontName="Helvetica-Bold"))
story.append(Spacer(1, 24))
story.append(HRFlowable(width="100%", thickness=0.8, color=LINE, spaceAfter=10))
meta = Table([
    [Paragraph("<b>Document</b>", CELL), Paragraph("Complete catalogue of delivered functionality", CELL)],
    [Paragraph("<b>Document date</b>", CELL), Paragraph(datetime.now().strftime("%d %B %Y"), CELL)],
    [Paragraph("<b>Scope</b>", CELL), Paragraph("Every module and feature built across the platform "
     "(public site, store POS, dashboards, reports, campaigns, AI, loyalty engine, ops, support, admin)", CELL)],
    [Paragraph("<b>Basis</b>", CELL), Paragraph("Enumerated from 58 backend route packages and 80+ frontend "
     "pages/components of the running application", CELL)],
], colWidths=[38 * mm, 122 * mm])
meta.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                          ("BACKGROUND", (0, 0), (0, -1), LIGHT), ("TOPPADDING", (0, 0), (-1, -1), 5),
                          ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (-1, -1), 6)]))
story.append(meta)
story.append(Spacer(1, 16))
p("This catalogue lists the functional capabilities implemented in the platform, grouped by module. "
  "It is written from a direct review of the source code and running services. Where a capability "
  "depends on an external credential or a production redeploy, that is stated plainly.", SMALL)
story.append(PageBreak())

# ───────────────────────── 0. AT A GLANCE ─────────────────────────
sec("At a Glance")
p("FundleBrain is a single-tenant, enterprise loyalty and customer-intelligence platform for a retail "
  "brand. It spans the full lifecycle: a public loyalty website, an in-store POS loyalty integration, "
  "a CRM &amp; analytics back-office, campaign automation, an action-enabled AI assistant, reporting/exports, "
  "support tooling and operational monitoring.")
table(["Area", "What it delivers"],
      [["Public loyalty site", "Brand website: how-it-works, earn/redeem, rewards, referral, store locator, FAQs, CMS-managed"],
       ["Store portal / POS", "eWards POS loyalty: enrol, earn, redeem, coupon lookup, OTP — live at the till"],
       ["Dashboards", "15+ real-time analytics dashboards with drill-down and on-demand AI narratives"],
       ["Customer intelligence", "Customer 360, RFM &amp; churn, cohorts, affinity, NPS history"],
       ["Reports &amp; exports", "Store/Weekly/CRM/Shopper KPI reports + streamed CSV/XLSX exports at scale"],
       ["Marketing", "Campaign manager + wizard, segments, marketing DB, coupons, ROI attribution"],
       ["Communications", "DLT-compliant SMS/WhatsApp via Karix, templates, bulk jobs, delivery receipts"],
       ["AI tools", "Fundle Brain analyst + Master Brain executor (tool-use, preview→confirm→execute)"],
       ["Loyalty engine", "Fully config-driven rules, tiers, multipliers, points integrity tooling"],
       ["Operations", "Historical ingest, daily reconciliation, item &amp; store masters, API monitor"],
       ["Support", "Ticketing / support desk + NPS inbox"],
       ["Administration", "10-role RBAC, user management, audit trail"]],
      [40 * mm, 120 * mm])
story.append(PageBreak())

# ───────────────────────── 1. ACCESS & ROLES ─────────────────────────
sec("1. Access, Portals &amp; Roles")
bullets([
    "<b>Three separate login portals:</b> the CRM/admin portal, the enterprise login, and the in-store "
    "Store portal — login is portal-gated so store credentials cannot reach the admin back-office and vice versa.",
    "<b>10-role RBAC:</b> super admin, brand admin, CRM manager, marketing manager, regional manager, "
    "store manager, store staff, support agent, analytics viewer and read-only executive. Every endpoint "
    "and every navigation item is gated by role.",
    "<b>JWT + bcrypt auth</b> (12-hour tokens, Bearer or HttpOnly cookie); passwords are bcrypt-hashed and "
    "never logged.",
    "<b>Read-only demo mode:</b> public demo accounts are enforced read-only at the auth layer (all writes "
    "rejected except a tiny explicit allow-list).",
    "<b>Audit trail:</b> logins, logouts and all data-mutating actions are written to an immutable audit log "
    "with actor, action, entity, IP and timestamp.",
])

# ───────────────────────── 2. PUBLIC SITE ─────────────────────────
sec("2. Public Loyalty Website")
p("A full customer-facing marketing/loyalty website, fully content-managed from the admin CMS.")
table(["Page", "Function"],
      [["Home / Landing", "Brand hero, programme highlights, calls-to-action (CMS-managed)"],
       ["How It Works", "Explains enrol → earn → redeem journey"],
       ["Earn Points / Redeem Points", "Programme mechanics: how points accrue and how to spend them"],
       ["Loyalty Benefits &amp; Rewards", "Tier benefits and the rewards catalogue"],
       ["Referral Programme", "Refer-a-friend messaging"],
       ["Store Locator", "Find-a-store listing"],
       ["About the Programme / FAQs", "Programme details and frequently-asked questions"],
       ["Contact", "Contact form / brand contact details"],
       ["Privacy &amp; Terms", "Legal / policy pages"],
       ["Public CMS", "Admins edit all of the above copy, imagery and links without code (cms_routes)"]],
      [46 * mm, 114 * mm])

# ───────────────────────── 3. STORE POS ─────────────────────────
sec("3. Store Portal &amp; POS Loyalty (eWards)")
p("The in-store experience and the live integration with the eWards point-of-sale, running against a "
  "dedicated database connection pool so till operations are never starved by back-office analytics.")
bullets([
    "<b>Store Operations console</b> for store staff/managers (mobile-friendly).",
    "<b>Customer check &amp; enrolment</b> at billing (posCustomerCheck) — instant member lookup by mobile.",
    "<b>Points earn</b> on each bill (posAddPoint) — crash-safe and idempotent (retries never double-credit); "
    "real-time tier evaluation and last-visit update on every bill.",
    "<b>Points redemption</b> with OTP verification.",
    "<b>Coupon redemption at POS</b> — validates public coupons and per-mobile unique coupons "
    "(single-use, mobile-bound).",
    "<b>Store logins</b> managed centrally (store_logins) and locked down per store.",
    "<b>Resilience:</b> reads use primaryPreferred so the till keeps working through transient database "
    "primary-loss windows; writes self-heal on the till's idempotent retry.",
])

# ───────────────────────── 4. DASHBOARDS ─────────────────────────
sec("4. Analytics Dashboards")
p("All dashboards run on live MongoDB aggregations (no stored snapshots) with full drill-down. AI "
  "narratives are click-to-generate (never auto-run) to keep pages instant and control AI spend.")
table(["Dashboard", "What it shows"],
      [["Command Center / Executive Cockpit", "Top-line KPIs: sales, bills, customers, points liability, trends"],
       ["Sales MTD", "Month-to-date sales performance"],
       ["Customer Analytics", "New vs repeat, acquisition and behaviour breakdowns"],
       ["Loyalty", "Points earned/redeemed, liability, tier movement"],
       ["Campaign Performance", "Campaign reach and outcome metrics"],
       ["Store", "Per-store performance and comparison"],
       ["RFM &amp; Churn", "Recency-Frequency-Monetary segmentation and churn risk"],
       ["Cohorts", "Acquisition cohorts and retention curves"],
       ["Points Economics", "Points issued vs burned, burn ratio, liability economics"],
       ["Campaign ROI", "Attributed revenue and ROI per campaign"],
       ["Executive Summary", "Consolidated executive view with AI narrative"],
       ["NPS", "Net Promoter Score trend and distribution"],
       ["KPI Trends", "Sales / bills / customers / discount over day/week/month"],
       ["New vs Repeat (Day-wise)", "Daily new-vs-repeat customer split"],
       ["Customer Count by Store", "Customer base sized per store"]],
      [56 * mm, 104 * mm])
p("Each dashboard supports date/zone/city/store filters, a drill-down modal to the underlying bills, and "
  "an on-demand &ldquo;Generate AI insight&rdquo; panel (headline, summary, drivers, recommendations).", SMALL)
story.append(PageBreak())

# ───────────────────────── 5. CUSTOMER INTELLIGENCE ─────────────────────────
sec("5. Customer Intelligence")
bullets([
    "<b>Customer 360:</b> a single profile view — identity, tier, points balance/ledger, lifetime spend &amp; "
    "visits, recency, monthly-spend chart, category &amp; store affinity, NPS history, and an AI "
    "&ldquo;Customer Intelligence Report&rdquo;.",
    "<b>Fast at scale:</b> the profile loads core data instantly and lazy-loads heavy analytics; RFM "
    "breakpoints are precomputed off the request path (startup + every 30 min) so drill-downs are sub-second "
    "even against ~1M customers.",
    "<b>Customer search &amp; list</b> with filters, plus a customer drawer for quick inspection from any table.",
    "<b>RFM segment labels</b> (Champions, Loyal, At-Risk, etc.) derived live from whole-base quintile breakpoints.",
])

# ───────────────────────── 6. REPORTS & EXPORTS ─────────────────────────
sec("6. Reports &amp; Exports")
p("A suite of finance-grade reports modelled on the client's reference formats, each reconciled to exact "
  "accounting identities and exportable at any scale via end-to-end streaming (no memory-timeout crashes).")
table(["Report", "Function"],
      [["Store KPI Report", "Per-store sales, discount, fresh/return bills, new/repeat/mapped/unmapped, "
        "ATV, customer counts, with Year-over-Year compare and live reconciliation banner"],
       ["Store-wise KPI (matrix)", "Store-wise KPI matrix with the same reconciled identities"],
       ["Weekly KPI", "Weekly performance rollup"],
       ["CRM Customer Report", "Customer master: points, billing, visits, recency, DOB/DOA, home store, "
        "with filters, sort, column-select and streamed export"],
       ["Shopper Bill Report", "Bill-level report with derived customer type (New/New-Repeat/Existing) and "
        "per-bill recency (status before each bill)"],
       ["Raw Reports", "Transaction / Customer / Repeat / By-Visit raw extracts"],
       ["Custom Report Builder", "Configurable report builder with export"],
       ["BOPS Reports", "Business-operations reporting set"],
       ["Reconciliation", "Reconcile platform figures against the raw source file"],
       ["Formula Catalog", "Transparent catalogue of every KPI definition/formula used"],
       ["Downloads Center", "Central place to retrieve generated exports"]],
      [46 * mm, 114 * mm])
bullets([
    "<b>Real-time recency:</b> &ldquo;Days Since Last Visit&rdquo; is computed live from each customer's "
    "last-visit timestamp (updated by POS on every bill) — no nightly backfill needed.",
    "<b>Canonical money:</b> one revenue definition (&ldquo;Total Paid&rdquo; = post-discount, incl. GST) is "
    "used across every report, export and dashboard, with locked Gross/Net/Point-Base/Total-Paid identities.",
    "<b>Streamed exports:</b> CSV/XLSX exports stream row-by-row on a deadline-free path so million-row "
    "downloads never crash the browser or the server.",
])
story.append(PageBreak())

# ───────────────────────── 7. MARKETING & CAMPAIGNS ─────────────────────────
sec("7. Marketing &amp; Campaign Automation")
bullets([
    "<b>Campaign Manager + 4-step guided wizard</b> (Objective → Audience → Message → Review &amp; Launch) "
    "with per-step validation and a live audience preview.",
    "<b>Campaign objectives:</b> generic, store, coupon or SKU — each with its own ROI window and cost input.",
    "<b>Real ROI attribution engine:</b> the targeted audience is frozen at launch (t0); a real transaction "
    "join computes converters, conversion %, attributed net revenue, revenue/recipient and ROI% — with "
    "Universal, Store-wise, Coupon and Target-SKU breakdowns over selectable windows (72h…30d).",
    "<b>Segment Builder:</b> build audiences from any combination of tier/city/points/visits/spend/recency/"
    "cohort filters, including a one-click &ldquo;Points ≥ N&rdquo; preset; preview then launch.",
    "<b>Marketing Database:</b> upload or paste an external number list (CSV/Excel), see how many are members "
    "vs non-members, and run a campaign to the full list (members personalised, non-members minimally).",
    "<b>Coupons:</b> a coupon engine plus per-mobile <b>unique coupon batches</b> (single-use, mobile-bound, "
    "validated at POS) with CSV export of allocated codes.",
    "<b>Automated campaigns:</b> rule-based auto-campaigns run on a daily schedule; scheduled campaigns "
    "auto-fire at their set time.",
    "<b>Auto-blacklist:</b> a number is auto-suppressed after 3 consecutive delivery failures and excluded "
    "from every future send; manual add/remove supported.",
])

# ───────────────────────── 8. COMMUNICATIONS ─────────────────────────
sec("8. Communications (SMS / WhatsApp)")
bullets([
    "<b>DLT-compliant messaging via Karix (Tanla):</b> separate transactional and bulk-marketing pipes, "
    "registered sender ID and DLT entity/template binding.",
    "<b>Message templates</b> with variable merge — bodies render {{name}} {{tier}} {{city}} {{points}} "
    "{{points_balance}} {{expiry}} {{coupon_code}} {{link}} per recipient.",
    "<b>Bulk send jobs</b> with progress, per-message logging tagged to the originating campaign, and "
    "write-back of final status.",
    "<b>Delivery receipts (DLR):</b> a webhook ingests Karix DLRs (delivered/failed/reasons) and reconciles "
    "them to sent messages, including fallback matching by destination number.",
    "<b>OTP delivery</b> for redemption/verification flows.",
    "<b>Provider Settings UI</b> to configure transactional and bulk credentials (keys masked); a "
    "connectivity diagnostic reports the deployment egress IP for provider IP-whitelisting.",
])

# ───────────────────────── 9. AI TOOLS ─────────────────────────
sec("9. AI Tools — Fundle Brain &amp; Master Brain")
p("A conversational, action-enabled analytics assistant backed by frontier LLMs through an "
  "OpenAI-compatible gateway — no provider secrets in the codebase; models are swappable.")
bullets([
    "<b>Fundle Brain (analyst):</b> ask questions in natural language; it runs read-only aggregations and "
    "returns answers, tables and charts, and can narrate uploaded CSV/report files.",
    "<b>Master Brain (executor):</b> deep-reasoning assistant with function-calling that can perform "
    "data-changing actions through a safe <b>preview → confirm → audited-execute</b> pattern; multi-mobile "
    "reads are batched into one aggregation and a wall-clock budget guarantees every streamed turn completes.",
    "<b>Bulk Bonus tool:</b> award bonus points to an uploaded mobile list with a preview and a downloadable "
    "&ldquo;not-found mobiles&rdquo; CSV.",
    "<b>Data Health (Quick Wins):</b> six read-only integrity audits (negative balances, uncredited earns, "
    "double redemptions, missing-redemption ledger, duplicate adjustments, historic derived points) run "
    "off-path daily, with a summary panel and deep-links to fix.",
    "<b>Multi-model &amp; selectable:</b> Anthropic Claude (default), OpenAI GPT and Google Gemini can be "
    "selected; all calls carry an app identifier for cost attribution.",
])
story.append(PageBreak())

# ───────────────────────── 10. LOYALTY ENGINE ─────────────────────────
sec("10. Loyalty Engine &amp; Configuration")
bullets([
    "<b>Fully config-driven Loyalty Rules editor:</b> earn rates, tier thresholds &amp; benefits, category/"
    "SKU multipliers, bonus rules, points expiry and card validity — all editable in the UI with nothing "
    "hardcoded (enables zero-code launch of new rules).",
    "<b>Tiering &amp; points ledger:</b> every earn/redeem/adjustment is recorded in an auditable points "
    "ledger; balances and tiers are derived from it.",
    "<b>Points Integrity Center:</b> detect and repair negative balances, uncredited/partial-commit earn "
    "bills, double redemptions and duplicate adjustments.",
    "<b>Redemption Repair:</b> targeted tooling to fix redemption/ledger mismatches.",
    "<b>Coupon engine:</b> public and unique coupon definitions with validity, min-bill and max-discount "
    "controls, enforced at POS.",
])

# ───────────────────────── 11. DATA OPS ─────────────────────────
sec("11. Data Operations")
bullets([
    "<b>Historical data upload:</b> ingest large historical transaction files with a customer post-pass "
    "(links each customer to a home store, derives visits, points, tiers).",
    "<b>Daily Reco:</b> add only the missing bills from the daily reconciliation file (idempotent, keyed on "
    "bill number); manual upload plus an optional email auto-pull (Microsoft 365 IMAP / OAuth2, "
    "credential-gated) and a daily scheduled job.",
    "<b>Item Master:</b> maintain the product/SKU catalogue with category facets used across reports and "
    "campaigns.",
    "<b>Stores master:</b> manage stores (code, name, class, zone/region, city) that dimension every report.",
    "<b>Verify Load &amp; POS Credentials:</b> validate ingested loads and manage POS integration credentials.",
    "<b>Chunked/streamed processing</b> and disk-safe aggregations so large loads never spill or lock the "
    "database.",
])

# ───────────────────────── 12. SUPPORT ─────────────────────────
sec("12. Support")
bullets([
    "<b>Tickets / Support Desk:</b> create, assign, track and resolve customer/support tickets with a detail "
    "view and status workflow.",
    "<b>NPS Inbox:</b> capture and triage NPS responses and feedback, feeding the NPS dashboard.",
])

# ───────────────────────── 13. ADMIN & MONITORING ─────────────────────────
sec("13. Administration &amp; Monitoring")
bullets([
    "<b>User Management:</b> create/manage users and roles; store roles require a store assignment (dropdown "
    "from the stores master).",
    "<b>API Monitor:</b> every API request is logged (method, path, status, latency) via pure-ASGI "
    "middleware (so streaming exports are never truncated) and surfaced in a monitoring console.",
    "<b>Executive Digests:</b> scheduled weekly executive digest generation.",
    "<b>Health &amp; scheduler:</b> health endpoints plus an async scheduler running weekly digests, report "
    "ingest, auto-campaigns, RFM refresh, data-health scans and the daily reco pull, each with its own logging.",
])

# ───────────────────────── 14. MARKETING MEDIA ─────────────────────────
sec("14. Marketing Media")
bullets([
    "<b>Product film (/watch):</b> a narrated cinematic walkthrough of the platform, downloadable as a 1080p "
    "MP4 with real text-to-speech voiceover and synced captions.",
    "<b>Fundle Reels (/reel):</b> three vertical (9:16) marketing films positioning Fundle Brain &amp; Master "
    "Brain as AI loyalty agents, rendered and downloadable.",
])

# ───────────────────────── 15. PLATFORM CAPABILITIES ─────────────────────────
sec("15. Platform &amp; Delivery Capabilities")
bullets([
    "<b>Single-config rebranding:</b> a single brand configuration file drives all branding across the "
    "frontend and backend, enabling zero-code deployment of a new brand instance.",
    "<b>Real-time everything:</b> dashboards and recency metrics are computed live from source data — no "
    "stale snapshots or nightly backfills required.",
    "<b>Production resilience:</b> dedicated POS connection pool, primaryPreferred reads with fast fail-over, "
    "capped analytics query times, non-blocking startup/seeding, and disk-safe aggregations.",
    "<b>Scale-tested:</b> operates against ~1M+ customers and a high-volume transaction/points ledger with "
    "~43 managed indexes.",
])

# ───────────────────────── 16. INTEGRATIONS ─────────────────────────
sec("16. Integrations")
table(["Integration", "Purpose"],
      [["Karix / Tanla", "DLT-compliant transactional &amp; bulk SMS, WhatsApp send, OTP, delivery receipts"],
       ["LLM providers (Anthropic / OpenAI / Google)", "AI assistant, narratives, TTS — via an OpenAI-compatible gateway"],
       ["eWards POS", "In-store loyalty: customer check, earn, redeem, coupon validation"],
       ["Microsoft 365 mailbox (IMAP/OAuth2)", "Optional daily auto-pull of the reconciliation file (credential-gated)"]],
      [58 * mm, 102 * mm])

# ───────────────────────── 17. ROADMAP ─────────────────────────
sec("17. Roadmap (planned — not yet built)")
p("Listed separately so nothing above is mistaken for current capability:")
bullets([
    "Meta / WhatsApp Cloud API and Meta Ads custom-audience integration (pending Meta credentials).",
    "Location-wise DLT SMS configuration, reward brands / gift-voucher rewards, and expanded OTP audit search.",
    "Variable (parameterised) DLT SMS templates for fully personalised marketing copy.",
    "Scheduled backups to object storage and a drag-and-drop report builder.",
    "Security hardening: MFA and automated login brute-force lockout.",
])
story.append(Spacer(1, 12))
story.append(HRFlowable(width="100%", thickness=0.8, color=LINE, spaceAfter=6))
p("Prepared from a direct review of the application source code and running services on the document date.", SMALL)

doc = SimpleDocTemplate(OUT, pagesize=A4, topMargin=26 * mm, bottomMargin=16 * mm,
                        leftMargin=18 * mm, rightMargin=18 * mm,
                        title="FundleBrain - Functionality Catalogue", author="FundleBrain")


def _footer(canvas, doc_):
    canvas.saveState()
    lw = 38 * mm
    lh = lw * 100 / 382.0
    ltop = A4[1] - 11 * mm - lh
    canvas.drawImage(ImageReader(LOGO), 18 * mm, ltop, width=lw, height=lh,
                     mask="auto", preserveAspectRatio=True)
    canvas.setStrokeColor(BURG)
    canvas.setLineWidth(1.2)
    canvas.line(18 * mm, ltop - 3 * mm, A4[0] - 18 * mm, ltop - 3 * mm)
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, 12 * mm, A4[0] - 18 * mm, 12 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GREY)
    canvas.drawString(18 * mm, 7 * mm, "FundleBrain \u2014 Functionality Catalogue \u2014 Confidential")
    canvas.drawRightString(A4[0] - 18 * mm, 7 * mm, "Page %d" % doc_.page)
    canvas.restoreState()


doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
print("WROTE", OUT)
