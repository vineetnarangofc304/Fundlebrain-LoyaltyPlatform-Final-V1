/**
 * BRAND CONFIGURATION — Single Source of Truth
 * ============================================
 *
 * Every brand-specific display string, contact detail, operational default,
 * asset URL and colour visible on the public site, login screens, store
 * portal and admin console is driven from THIS file (imported as `BRAND`).
 *
 * 📦 To rebrand this project for a new brand (e.g. Beverly Hills):
 *   1. Edit the values in this file (identity, loyalty copy, contact/legal,
 *      operational defaults, colours). Every field below has a KAZO default;
 *      change the values, not the field names.
 *   2. Edit `<title>` + `<meta>` tags in `frontend/public/index.html`
 *      (static / build-time — cannot read this file).
 *   3. Backend `backend/.env`: set `BRAND_NAME`, `BRAND_ADMIN_EMAIL`,
 *      `BRAND_ADMIN_PASSWORD`, and (optional) `BRAND_EMAIL_DOMAIN`,
 *      `DEMO_USER_PASSWORD` for the seeded logins; add the new site origin to
 *      `CORS_ORIGINS` (the CORS regex already allows *.fundlebrain.ai).
 *   4. Replace the DLT-approved SMS template seeded in `backend/server.py`
 *      with the new brand's Karix-registered sender/entity/template + body.
 *   5. Replace hero / boutique / editorial imagery below (or upload via the
 *      in-app Public Site CMS — CMS overrides take precedence at runtime).
 *   6. Add the brand logo asset(s) in /public.
 *
 * 🔒 Do NOT rename CSS class names (`kazo-text-burgundy`, etc.) or the
 *    `--kazo-*` CSS variables — they are stable selectors used across 50+
 *    components. Only the underlying colour VALUES (below) change per brand.
 */

export const BRAND = {
  // -- Identity --------------------------------------------------------
  name: "KAZO",                          // Short display name (uppercase logo)
  legalName: "KAZO",                     // Used in © footer
  domain: "kazo.com",                    // Public-facing website
  shortDescriptor: "premium Indian women's fashion brand",

  // -- Platform identity (Fundle = the loyalty engine running this app)
  platform: "Fundle",
  poweredBy: "Powered by Fundle",
  aiAssistant: "Fundle Brain",
  // Real Fundle wordmark (white/light — shows on dark surfaces). Lives in /public.
  platformLogoUrl: "/fundle-logo.png",

  // -- Loyalty programme branding -------------------------------------
  loyaltyProgramName: "KAZO Rewards",
  welcomePointsValue: 100,               // Bonus points credited on sign-up
  welcomeToast: "Welcome to KAZO Rewards! 100 bonus points credited.",
  ctaJoinFree: "Join KAZO Rewards Free",

  // -- Social --------------------------------------------------------
  social: {
    instagram: "https://instagram.com/kazo_brand",
    facebook: "https://facebook.com",
    youtube: "https://youtube.com",
  },

  // -- SEO / meta (also mirror in frontend/public/index.html) ---------
  meta: {
    title: "KAZO Rewards — Powered by Fundle",
    description:
      "Join the official KAZO loyalty programme. Earn points on every purchase, unlock exclusive tier privileges, birthday bonuses, and access VIP collections across India. Powered by Fundle.",
  },

  // -- Public home copy (CMS overrides take precedence at runtime) ----
  homeCopy: {
    heroEyebrow: "An Exclusive Programme · Powered by Fundle",
    heroSubtext:
      "The official KAZO loyalty programme. Every purchase reveals new privileges — from welcome bonuses and birthday gifts to private VIP previews.",
    heroImageAlt: "KAZO premium women's western fashion editorial",
    boutiqueImageAlt: "KAZO boutique interior",
    editorialImageAlt: "Model wearing KAZO collection",
  },

  // -- Footer copy ----------------------------------------------------
  footerTagline:
    "The official loyalty programme for KAZO — where every purchase becomes a privilege. Designed for the modern Indian woman.",

  // -- Login / portal copy --------------------------------------------
  loginCopy: {
    descriptor:
      "A unified suite for loyalty, CRM, analytics and campaigns — purpose-built for KAZO.",
    imageAlt: "KAZO",
  },

  // -- Public-site contact / legal (CMS overrides take precedence) ----
  audienceDescriptor: "the modern Indian woman",
  region: "India",
  storeCountLine: "25+ stores across India",
  legalEntity: "KAZO Fashion Pvt. Ltd.",
  headOffice: "New Delhi, India",
  supportPhone: "1800 123 456 · Mon–Sat, 10AM–8PM",
  supportPhoneTel: "+911800123456",
  // Public support emails are built as <box>@{domain} (rewards@, privacy@, agent@).

  // -- Operational defaults (admin console) ---------------------------
  couponPrefix: "KAZO",              // default coupon-code prefix
  posMerchantId: "KAZO_FUNDLE",      // default POS merchant_id
  sms: {
    senderId: "KAZOIN",             // transactional DLT sender header
    campaignSenderId: "KAZOFN",     // promotional / bulk DLT sender header
    campaignAccount: "fundle_campaign",
  },

  // -- Brand colour palette ------------------------------------------
  // These hex values are injected as CSS variables at runtime
  // (see App.js → useEffect). Variable NAMES stay `--kazo-*` because
  // 50+ class names like `.kazo-text-burgundy` reference them — only
  // the VALUES change per brand.
  //
  // For Red Chief you might use:
  //   black: "#0A0A0A", cream: "#F8F4EE",
  //   burgundy: "#B91C1C", burgundyDeep: "#7F1212",
  //   champagne: "#1F2937", champagneLight: "#374151",
  colors: {
    black: "#0A0A0A",          // --kazo-black           (header / footer)
    cream: "#F9F8F6",          // --kazo-cream           (page background)
    burgundy: "#571326",       // --kazo-burgundy        (primary brand accent)
    burgundyDeep: "#3B0D1B",   // --kazo-burgundy-deep   (hover state)
    champagne: "#C7A76D",      // --kazo-champagne       (secondary accent / luxury hint)
    champagneLight: "#E0CFA3", // --kazo-champagne-light (light backgrounds)
  },
};

export default BRAND;
