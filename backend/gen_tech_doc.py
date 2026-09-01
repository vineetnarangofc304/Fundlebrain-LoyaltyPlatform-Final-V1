"""Generate the FundleBrain technical overview PDF (reportlab).
Every fact here was pulled directly from the codebase — no exaggeration."""
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                HRFlowable, ListFlowable, ListItem, PageBreak)

OUT = "/app/frontend/public/FundleBrain_Tech_Overview.pdf"
LOGO = "/app/backend/fundle_logo_black.png"
BURG = colors.HexColor("#6b1220")
BURG2 = colors.HexColor("#8a1a2b")
INK = colors.HexColor("#1a1a1a")
GREY = colors.HexColor("#555555")
LIGHT = colors.HexColor("#f3eaec")
LINE = colors.HexColor("#d9c3c8")

styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=styles["Heading1"], fontName="Helvetica-Bold",
                    fontSize=16, textColor=BURG, spaceBefore=14, spaceAfter=6, leading=20)
H2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName="Helvetica-Bold",
                    fontSize=11.5, textColor=BURG2, spaceBefore=10, spaceAfter=3, leading=15)
BODY = ParagraphStyle("BODY", parent=styles["BodyText"], fontName="Helvetica",
                      fontSize=9.3, textColor=INK, leading=13.5, spaceAfter=5, alignment=TA_LEFT)
SMALL = ParagraphStyle("SMALL", parent=BODY, fontSize=8, textColor=GREY, leading=11)
CELL = ParagraphStyle("CELL", parent=BODY, fontSize=8.6, leading=11.5, spaceAfter=0)
CELLB = ParagraphStyle("CELLB", parent=CELL, fontName="Helvetica-Bold")
TITLE = ParagraphStyle("TITLE", parent=styles["Title"], fontName="Helvetica-Bold",
                       fontSize=26, textColor=BURG, leading=30, alignment=TA_LEFT)
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


# ───────────────────────── COVER ─────────────────────────
story.append(Spacer(1, 40))
story.append(HRFlowable(width="100%", thickness=3, color=BURG, spaceAfter=18))
p("FundleBrain", TITLE)
p("Loyalty, CRM &amp; Customer-Intelligence Platform", SUB)
story.append(Spacer(1, 6))
p("Technical &amp; Architecture Overview", ParagraphStyle("t2", parent=SUB, textColor=BURG2, fontSize=13, fontName="Helvetica-Bold"))
story.append(Spacer(1, 24))
story.append(HRFlowable(width="100%", thickness=0.8, color=LINE, spaceAfter=10))
meta = Table([
    [Paragraph("<b>Prepared for</b>", CELL), Paragraph("Client technical / code review", CELL)],
    [Paragraph("<b>Document date</b>", CELL), Paragraph(datetime.now().strftime("%d %B %Y"), CELL)],
    [Paragraph("<b>Scope</b>", CELL), Paragraph("Technology stack, AI/LLM usage, integrations, security, code quality &amp; QA", CELL)],
    [Paragraph("<b>Classification</b>", CELL), Paragraph("Confidential — for the intended recipient only", CELL)],
], colWidths=[40 * mm, 120 * mm])
meta.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                          ("BACKGROUND", (0, 0), (0, -1), LIGHT), ("TOPPADDING", (0, 0), (-1, -1), 5),
                          ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (-1, -1), 6)]))
story.append(meta)
story.append(Spacer(1, 16))
p("This document describes the actual, implemented state of the platform as verified against the "
  "source code and running services. It intentionally avoids forward-looking claims except where a "
  "section is explicitly labelled &ldquo;Roadmap&rdquo;. Software/library version numbers are quoted "
  "from the project dependency manifests.", SMALL)
story.append(PageBreak())

# ───────────────────────── 1. EXEC SUMMARY ─────────────────────────
p("1. Executive Summary", H1)
rule()
p("The platform is a single-tenant, enterprise-grade loyalty and customer-intelligence system for the "
  "retail brand. It unifies point-of-sale loyalty processing, a CRM/customer 360, analytics and "
  "reporting, campaign automation (SMS), an AI analytics assistant, support tooling and API monitoring.")
bullets([
    "<b>Architecture:</b> a Python/FastAPI asynchronous REST backend, a React single-page frontend, "
    "and MongoDB (managed replica set) as the primary data store.",
    "<b>Scale:</b> the production data store holds a large customer base (~1M+ customer records) and "
    "a high-volume transaction / points ledger, served through indexed, read-preference-tuned queries.",
    "<b>AI:</b> a conversational, action-enabled analytics assistant backed by frontier LLMs "
    "(Anthropic Claude, OpenAI GPT, Google Gemini), accessed through a single managed key — no model "
    "provider keys are stored in the application.",
    "<b>Messaging:</b> DLT-compliant transactional and bulk marketing SMS via the Karix (Tanla) gateway, "
    "with delivery-receipt tracking.",
    "<b>Security:</b> JWT + bcrypt authentication, ten-role RBAC, portal gating, full audit logging, "
    "environment-only secrets and CORS allow-listing.",
])

# ───────────────────────── 2. ARCHITECTURE ─────────────────────────
p("2. System Architecture", H1)
rule()
p("A conventional, well-separated three-tier architecture. All backend routes are namespaced under "
  "<b>/api</b> and served by an ASGI stack; the frontend is a compiled SPA that talks to the backend "
  "exclusively over HTTPS using a configurable base URL. Long-running and scheduled work is handled by "
  "an in-process async scheduler and background tasks rather than blocking request threads.")
table(["Tier", "Responsibility", "Core technology"],
      [["Presentation", "Admin CRM dashboard, store portal, reports, campaign manager, AI console",
        "React 19 SPA (Tailwind CSS + Radix UI / shadcn pattern)"],
       ["Application / API", "REST endpoints, business logic, auth, AI orchestration, messaging",
        "FastAPI (ASGI) on Uvicorn, 58 modular route packages"],
       ["Data", "Customers, transactions, points ledger, campaigns, audit &amp; API logs",
        "MongoDB 7.0 replica set (via async Motor driver)"],
       ["Async / jobs", "Weekly digests, report ingestion, automated campaigns, daily reconciliation",
        "APScheduler (AsyncIO, Asia/Kolkata) + FastAPI background tasks"]],
      [26 * mm, 78 * mm, 56 * mm])
p("Cross-cutting middleware: a CORS policy (explicit allow-list plus a domain regex) and a pure-ASGI "
  "API-logging middleware that records every request&rsquo;s method, path, status and latency for the "
  "built-in API monitor (kept as raw ASGI specifically so streaming CSV/XLSX/PDF exports are never "
  "truncated).", SMALL)

story.append(PageBreak())

# ───────────────────────── 3. BACKEND STACK ─────────────────────────
p("3. Backend Technology Stack", H1)
rule()
table(["Component", "Technology", "Version"],
      [["Language / runtime", "Python", "3.11"],
       ["Web framework", "FastAPI", "0.110.1"],
       ["ASGI server", "Uvicorn", "0.25.0"],
       ["ASGI toolkit", "Starlette", "0.37.2"],
       ["Data validation / models", "Pydantic", "2.13.4"],
       ["MongoDB driver (async)", "Motor / PyMongo", "3.3.1 / 4.5.0"],
       ["Auth &mdash; JWT", "PyJWT", "2.12.1"],
       ["Auth &mdash; password hashing", "bcrypt", "4.1.3"],
       ["Scheduler", "APScheduler", "3.11.2"],
       ["Data processing", "pandas / numpy", "3.0.3 / 2.4.4"],
       ["Excel / PDF generation", "openpyxl / reportlab", "3.1.5 / 4.5.1"],
       ["LLM orchestration", "emergentintegrations + LiteLLM", "0.1.0 / 1.80.0"],
       ["HTTP client", "httpx / requests", "0.28.1 / 2.34.1"]],
      [46 * mm, 74 * mm, 40 * mm])

# ───────────────────────── 4. FRONTEND STACK ─────────────────────────
p("4. Frontend Technology Stack", H1)
rule()
table(["Component", "Technology", "Version"],
      [["UI library", "React", "19.0"],
       ["Routing", "React Router DOM", "7.5"],
       ["Build tooling", "Create React App + CRACO", "5.0.1 / 7.1"],
       ["Styling", "Tailwind CSS", "3.4"],
       ["Component primitives", "Radix UI (shadcn/ui pattern)", "1.x&ndash;2.x"],
       ["Charts / dataviz", "Recharts", "3.6"],
       ["Animation", "Framer Motion", "12.42"],
       ["HTTP client", "Axios", "1.8"],
       ["Forms &amp; validation", "React Hook Form + Zod", "7.56 / 3.24"],
       ["Notifications", "Sonner (toasts)", "2.0"],
       ["Icons", "lucide-react", "0.507"],
       ["Package manager", "Yarn", "1.22"]],
      [46 * mm, 74 * mm, 40 * mm])

story.append(PageBreak())

# ───────────────────────── 5. DATA LAYER ─────────────────────────
p("5. Data Layer &mdash; MongoDB", H1)
rule()
p("The primary datastore is MongoDB 7.0, running as a managed, multi-node replica set in production. "
  "Access is fully asynchronous via the Motor driver.")
table(["Aspect", "Detail"],
      [["Server version", "MongoDB 7.0 (managed replica set; dev/preview verified on 7.0.42)"],
       ["Connectivity", "Connection pooling (max pool 100), automatic retryable reads &amp; writes"],
       ["Write concern", "w = majority (durable, acknowledged by a majority of nodes)"],
       ["Read preference", "primaryPreferred &mdash; heavy analytics reads tolerate secondaries so "
        "primary stays responsive under load"],
       ["Schema approach", "Document models with a shared base that maps Mongo _id &rarr; string id; "
        "ObjectId is never returned raw to clients (JSON-safe boundaries)"],
       ["Indexing", "~43 managed indexes ensured at startup across the core collections"],
       ["Data volume (prod)", "~50 collections; ~1M+ customer records plus high-volume transaction, "
        "points-ledger and API-log collections"]],
      [40 * mm, 120 * mm])

# ───────────────────────── 6. AI / LLM ─────────────────────────
p("6. Artificial Intelligence &amp; LLMs", H1)
rule()
p("AI features are delivered through a single <b>managed universal LLM key</b> routed via an "
  "OpenAI-compatible integration proxy (using the <i>emergentintegrations</i> library and LiteLLM). "
  "Consequently <b>no OpenAI / Anthropic / Google API keys live in the application or repository</b> &mdash; "
  "the key is injected from the environment. The following models are configured in the code today:")
table(["Capability", "Provider", "Model (as configured)"],
      [["Analytics assistant &mdash; default (&ldquo;Fundle Brain&rdquo;)", "Anthropic", "Claude Sonnet 4.6"],
       ["Assistant &mdash; deep reasoning (&ldquo;Master Brain&rdquo;)", "Anthropic", "Claude Opus 4.7 (selectable)"],
       ["Assistant &mdash; alternate models (user-selectable)", "OpenAI / Google", "GPT-5.5 &nbsp;/&nbsp; Gemini 3.1 Pro"],
       ["Campaign copy &amp; report drill-down narratives", "OpenAI", "GPT-5.2"],
       ["Uploaded-report narrative summaries", "OpenAI", "GPT-5"],
       ["Text-to-speech (product walkthrough audio)", "OpenAI", "tts-1 / tts-1-hd"]],
      [70 * mm, 26 * mm, 64 * mm])
p("<b>Action-enabled assistant:</b> the assistant supports function-calling / tool-use. Data-mutating "
  "tools are role-gated, run through a preview &rarr; confirm &rarr; audited-execute pattern, and are "
  "reversible. All AI requests carry an application identifier for usage attribution and cost control.", SMALL)

story.append(PageBreak())

# ───────────────────────── 7. INTEGRATIONS ─────────────────────────
p("7. Third-Party Integrations", H1)
rule()
p("Only the integrations below are actually wired into the running system. (For transparency: some "
  "SDKs present in the dependency list &mdash; e.g. object-storage and payment SDKs &mdash; are not "
  "currently used by any code path, so they are deliberately excluded here.)")
table(["Integration", "Purpose", "Notes"],
      [["Karix / Tanla (messaging)", "DLT-compliant transactional &amp; bulk marketing SMS; WhatsApp send; "
        "OTP delivery", "Dedicated DLT-registered sender ID; delivery receipts (DLR) received by webhook; egress IP "
        "whitelisted with the provider; API keys held only in environment config"],
       ["Microsoft 365 mailbox (IMAP)", "Optional daily auto-pull of the sales reconciliation file",
        "Enabled only when IMAP credentials are supplied via environment; no secrets in code"],
       ["Emergent Universal LLM key", "Single managed gateway to Anthropic / OpenAI / Google models",
        "OpenAI-compatible proxy; usage attributed per application"]],
      [40 * mm, 55 * mm, 65 * mm])

# ───────────────────────── 8. SECURITY ─────────────────────────
p("8. Security &amp; Access Control", H1)
rule()
bullets([
    "<b>Authentication:</b> stateless JWT (HS256, 12-hour expiry) issued on login; accepted as a Bearer "
    "token or an HttpOnly cookie. Passwords are hashed with <b>bcrypt</b> (per-password salt); plaintext "
    "passwords are never stored or logged.",
    "<b>Authorisation (RBAC):</b> ten distinct roles (super admin, brand admin, CRM manager, marketing "
    "manager, regional manager, store manager, store staff, support agent, analytics viewer, read-only "
    "executive). Endpoints are guarded by explicit role requirements, and login is additionally "
    "<b>portal-gated</b> (store portal vs. CRM/admin portal).",
    "<b>Audit trail:</b> logins, logouts and all data-mutating actions are written to an immutable audit "
    "log with the actor, action, entity, metadata, IP and timestamp.",
    "<b>API monitoring:</b> every API call is logged (method, path, status, latency) for observability "
    "and abuse detection via the built-in API monitor.",
    "<b>Secrets management:</b> all credentials, connection strings, keys and JWT secret come from "
    "environment variables only &mdash; the codebase contains no hardcoded secrets; missing config "
    "fails fast rather than falling back to defaults.",
    "<b>Network:</b> HTTPS/TLS transport end-to-end; MongoDB Atlas provides encryption in transit and "
    "at rest plus an IP access-list; the messaging provider egress IP is whitelisted.",
    "<b>CORS:</b> requests are restricted to an explicit origin allow-list plus a controlled domain regex.",
    "<b>Least-privilege demo mode:</b> public demo accounts are enforced read-only at the auth layer &mdash; "
    "every write method is rejected except a tiny, explicit allow-list.",
])
p("<b>Not yet in place (candid disclosure):</b> multi-factor authentication, automated login "
  "brute-force lockout, and a formal third-party penetration test / SOC 2 attestation are not currently "
  "implemented &mdash; these are natural next steps and are noted on the roadmap.", SMALL)

story.append(PageBreak())

# ───────────────────────── 9. CODE QUALITY ─────────────────────────
p("9. Code Quality &amp; Engineering Practices", H1)
rule()
bullets([
    "<b>Modular structure:</b> the backend is split into 58 focused route modules by domain (loyalty, "
    "CRM, reports, campaigns, communications, AI, support, monitoring, etc.) rather than a monolith, "
    "with shared utilities for money/date normalisation, DB timeouts and serialisation.",
    "<b>Typed contracts:</b> Pydantic v2 models validate all request/response payloads at the API "
    "boundary; a shared document base guarantees JSON-safe serialisation from MongoDB.",
    "<b>Backend quality tooling:</b> configured with <b>black</b> (formatting), <b>isort</b> (imports), "
    "<b>flake8</b> (lint), and <b>mypy</b> (static type checking).",
    "<b>Frontend quality tooling:</b> <b>ESLint</b> with the React, React-Hooks, JSX-a11y and import "
    "plugins; consistent component conventions and a shared design system (Tailwind + Radix/shadcn).",
    "<b>Automated pre-deploy gate:</b> a static analysis pass blocks common production hazards "
    "(hardcoded secrets, unsafe DB serialisation, wrong ports/URLs, compile errors) before release.",
    "<b>Testability:</b> stable, descriptive test identifiers on interactive UI elements enable reliable "
    "end-to-end automation; the API is scriptable and self-documented via FastAPI&rsquo;s OpenAPI schema.",
])

# ───────────────────────── 10. TESTING / QA ─────────────────────────
p("10. Testing &amp; Quality Assurance", H1)
rule()
bullets([
    "<b>Backend tests:</b> pytest is set up with a dedicated test package for API/integration checks.",
    "<b>End-to-end QA:</b> features are validated through an iterative automated UI+API test process; "
    "each cycle produces a structured pass/fail report that is remediated before sign-off (100+ recorded "
    "iterations to date).",
    "<b>Verification discipline:</b> backend changes are verified with live API calls (real request / "
    "response assertions) and, where relevant, direct data checks; UI changes are verified against the "
    "running application.",
    "<b>Change safety:</b> the platform commits a checkpoint after each step, allowing instant rollback "
    "to any previous known-good state.",
])

# ───────────────────────── 11. DEPLOYMENT ─────────────────────────
p("11. Deployment &amp; Operations", H1)
rule()
bullets([
    "<b>Environments:</b> a clean separation between a preview/development environment and the live "
    "production deployment, each with its own database and configuration.",
    "<b>Process management:</b> backend and frontend run as supervised services; the API is stateless "
    "and horizontally scalable behind the ingress.",
    "<b>Configuration:</b> environment-driven (URLs, database, keys, feature flags) with no build-time "
    "secrets; the production database is a managed MongoDB Atlas cluster.",
    "<b>Observability:</b> built-in health endpoints, the request-level API monitor, application logs, "
    "and a background-job scheduler with per-job logging.",
])

# ───────────────────────── 12. ROADMAP ─────────────────────────
p("12. Roadmap (planned &mdash; not yet built)", H1)
rule()
p("Listed separately and explicitly so nothing above is mistaken for current capability:")
bullets([
    "Meta / WhatsApp Cloud API and Meta Ads custom-audience integration (pending provider credentials).",
    "Location-wise DLT SMS configuration, reward brands / gift-voucher rewards, and expanded OTP audit search.",
    "Variable (parameterised) DLT SMS templates for true per-customer personalised marketing copy.",
    "Security hardening: MFA, login brute-force lockout, and an external security assessment.",
    "Scheduled backups to object storage and a drag-and-drop report builder.",
])
story.append(Spacer(1, 12))
story.append(HRFlowable(width="100%", thickness=0.8, color=LINE, spaceAfter=6))
p("Prepared from a direct review of the application source code and running services. All version "
  "numbers reflect the project dependency manifests at the document date; model identifiers reflect "
  "the values configured in code and may be updated as newer managed models become available.", SMALL)

doc = SimpleDocTemplate(OUT, pagesize=A4, topMargin=26 * mm, bottomMargin=16 * mm,
                        leftMargin=18 * mm, rightMargin=18 * mm,
                        title="FundleBrain - Technical Overview", author="FundleBrain")


def _footer(canvas, doc_):
    canvas.saveState()
    # header: black Fundle logo + burgundy underline rule on every page
    lw = 38 * mm
    lh = lw * 100 / 382.0
    ltop = A4[1] - 11 * mm - lh
    canvas.drawImage(ImageReader(LOGO), 18 * mm, ltop, width=lw, height=lh,
                     mask="auto", preserveAspectRatio=True)
    canvas.setStrokeColor(BURG)
    canvas.setLineWidth(1.2)
    canvas.line(18 * mm, ltop - 3 * mm, A4[0] - 18 * mm, ltop - 3 * mm)
    # footer
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, 12 * mm, A4[0] - 18 * mm, 12 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(GREY)
    canvas.drawString(18 * mm, 7 * mm, "FundleBrain \u2014 Technical Overview \u2014 Confidential")
    canvas.drawRightString(A4[0] - 18 * mm, 7 * mm, "Page %d" % doc_.page)
    canvas.restoreState()


doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
print("WROTE", OUT)
