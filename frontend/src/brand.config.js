/**
 * BRAND CONFIGURATION — Single Source of Truth
 * ============================================
 *
 * Every display string, asset URL and brand identifier visible on the
 * public site, login screens and admin sidebar lives in this file.
 *
 * 📦 To rebrand this project for a new brand (e.g. Red Chief):
 *   1. Edit the values below.
 *   2. Edit colour values at the top of `frontend/src/index.css`
 *      (the `--kazo-*` CSS variables — keep the variable NAMES, just
 *      swap the hex values to match the new brand palette).
 *   3. Edit `<title>` + `<meta>` tags in `frontend/public/index.html`
 *      (these are static / build-time and cannot read this file).
 *   4. Edit `BRAND_NAME` + super-admin / brand-admin emails in
 *      `backend/.env`.
 *   5. Replace hero / boutique / editorial Unsplash image URLs below
 *      with brand-appropriate imagery (or upload your own via the
 *      Public Site CMS once logged in).
 *
 * 🔒 Do NOT rename CSS class names (`kazo-text-burgundy`, etc.) —
 *    those are stable selectors used across 50+ components. Only the
 *    underlying CSS variable VALUES need to change per brand.
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
