# Rebranding Checklist — Fundle Loyalty Platform Template

This document explains exactly what to change when spinning up this
codebase as a **new brand's** loyalty platform (e.g. Red Chief, ABFRL,
any client).

Each new brand should be deployed as its own **independent Emergent
project** with its own MongoDB and its own preview / production URL.

> Workflow:
> 1. Push this codebase to GitHub once (the "master template").
> 2. For each new brand, start a new Emergent task and have the agent
>    pull from the GitHub template.
> 3. Run through the checklist below.
> 4. Deploy.

---

## ⏱  10-minute rebrand checklist

### 1. Display strings — `frontend/src/brand.config.js`
Single source of truth for **every** brand-visible string on the public
site, login screens and admin sidebar.

Edit the `BRAND` object:
- `name`, `legalName`, `domain`
- `loyaltyProgramName`, `welcomeToast`, `ctaJoinFree`
- `social.instagram` / `social.facebook` / `social.youtube`
- `meta.title` / `meta.description`
- `homeCopy.*`, `footerTagline`, `loginCopy.*`
- `welcomePointsValue` (default 100 — adjust per brand's promo strategy)

### 2. Brand colours — `frontend/src/index.css`
At the top of the file you'll see CSS variables like:

```css
:root {
  --kazo-black: #0A0A0A;
  --kazo-cream: #F9F8F6;
  --kazo-burgundy: #571326;
  --kazo-burgundy-deep: #3B0D1B;
  --kazo-champagne: #C7A76D;
  --kazo-champagne-light: #E0CFA3;
}
```

**Change only the HEX VALUES, not the variable names.** The variable
names (`--kazo-burgundy`, etc.) are used as stable identifiers across
50+ components — keep them and just swap colours. For Red Chief you
might use:

```css
--kazo-burgundy: #B91C1C;       /* Red Chief brand red */
--kazo-champagne: #1F2937;      /* Charcoal accent */
```

### 3. HTML head — `frontend/public/index.html`
This file is static / build-time and cannot read `brand.config.js`.
Update manually:
- `<title>`
- `<meta name="description">`
- `<meta name="keywords">`
- `<meta property="og:title">`
- `<meta property="og:description">`

### 4. Backend env — `backend/.env`
- `BRAND_NAME` — display brand name
- `BRAND_ADMIN_EMAIL` — primary admin email
- `BRAND_ADMIN_PASSWORD` — initial password (force-rotate after first login)
- `SUPER_ADMIN_EMAIL` — Fundle super admin (usually unchanged)
- `JWT_SECRET` — **regenerate** a new random string per brand

### 5. Frontend env — `frontend/.env`
- `REACT_APP_BACKEND_URL` — Emergent auto-sets this per preview pod.
  Don't touch.

### 6. Hero & marketing imagery
The `Home.jsx` and `LoginShell.jsx` use Unsplash placeholders. Replace
either:
- Directly in `brand.config.js` (we'd need to add image URLs there), or
- Via the **Public Site CMS** once logged in as super admin:
  - Login → Configuration → Public Site CMS
  - Upload brand hero / boutique / editorial imagery via the CMS form.
  - CMS overrides take precedence at runtime, so no code changes needed.

### 7. POS API credentials
The platform auto-bootstraps a default credential on first boot via
`bootstrap_pos_defaults()` in `routes/pos_ewards_routes.py`. After
deploying for a new brand:
- Login → Operations → POS Credentials
- View the auto-generated `api_key`, `merchant_id`, `customer_key`.
- Share with the brand's POS integration team.

### 8. Karix SMS / WhatsApp credentials
- Login → Communications → Provider Settings
- Enter the brand's own Karix or alternative provider credentials.
- Save → test send.

### 9. Custom domain (optional)
After deploying via Emergent, configure the custom domain (e.g.
`redchiefloyalty.fundlebrain.ai`) via the Emergent deployment settings.

---

## What does NOT need to change per brand

The following are **intentionally brand-neutral** and should be left
alone:

- **CSS class names** like `kazo-text-burgundy`, `kazo-bg-black` —
  these are just stable selectors; only the variable values need
  to change.
- **MongoDB collection names** — `customers`, `transactions`,
  `points_ledger`, etc.
- **API route prefixes** — `/api/pos`, `/api/dashboard`, etc.
- **The Fundle Brain AI tools schema** — domain-agnostic.
- **All 14 POS endpoints** (eWards-compatible contract) — brand-neutral.

---

## Keeping multiple brands in sync

When you ship a new improvement to the master template:

1. Make the change in the master template's Emergent project.
2. Push to GitHub.
3. For each downstream brand project, ask its Emergent agent:
   > *"Pull the latest changes from `fundle-loyalty-template` and merge
   > them into this codebase, preserving Red Chief's branding
   > overrides in `brand.config.js`, `index.css` and `index.html`."*

The agent will do a 3-way merge, keeping brand-specific overrides while
pulling in new features.

---

## File reference — what's already abstracted

| File | What it controls |
| --- | --- |
| `frontend/src/brand.config.js` | All display strings, social URLs, CTAs |
| `frontend/src/index.css` (top) | All brand colours (CSS variables) |
| `frontend/public/index.html` | SEO meta + page title (build-time) |
| `backend/.env` | Brand name, admin emails, JWT secret |

Everything else (1500+ files of React, FastAPI, MongoDB plumbing) is
**fully brand-neutral**. ✅
