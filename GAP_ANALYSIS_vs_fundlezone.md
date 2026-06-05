# Gap Analysis — KAZO Fundle (new) vs newu.fundlezone.com (legacy)

**Audit date**: Feb 2026
**Auditor login**: Vineet @ newu.fundlezone.com (Head Office, NewU brand)
**Production scale on legacy**: 3,531,862 customers · 171 locations · ₹14.6 Cr earn value · ₹18 L redeem value

---

## A. LEGACY SYSTEM (newu.fundlezone.com) — Full Inventory

### A1. REWARDS DESK (in-browser POS / desk operator UI)
| # | Module | URL | Purpose |
|---|---|---|---|
| 1 | **Customer Search** | `/CustomerSearch/` | Mobile-number lookup of any registered customer |
| 2 | **Registration** | `/CustRegistration/` | Create new loyalty customer at the desk |
| 3 | **Enter Bill** | `/EnterBill/` | Manual bill entry → earn points |
| 4 | **Redeem Points** | `/RedeemPoints/` | OTP-validated point redemption against a bill |
| 5 | **Redeem Coupon** | `/RedeemCoupon/` | OTP-validated coupon redemption |
| 6 | **Redeem Points GV** | `/giftvouhcersearch/` | Gift Voucher lookup + redemption |
| 7 | **Customer Profile Edit** | `/CustomerProfileEdit/` | Edit name, email, anniversary, etc. |

### A2. ANALYTICS / SUMMARY
| # | Report | URL | What it shows |
|---|---|---|---|
| 1 | **Customers Summary** | `/analytics/customer-summary/` | Bar chart + table of customer counts by Location/City/State/Zone/Month/Tier (toggle radios) |
| 2 | **Transaction Summary** | `/analytics/TransactionReportSummary/` | Multi-metric overlay: Total Points / Total Purchase / Total Bills / Unique Customers by location group |
| 3 | **Repeat Purchase Summary** | `/analytics/RepeatTransbyLocSummary/` | Repeat-purchase counts and amounts by group |
| 4 | **Earn Burn Summary** | `/analytics/EarnBurnSummaryReport/` | Table: Earn / Redeem / Bonus / Expired / Liability per location |
| 5 | **Customers by Visits** | `/analytics/CustomerByVisit/` | Frequency distribution (how many customers have N visits) |

### A3. ANALYTICS / DETAILED (raw-level reports)
| # | Report | URL |
|---|---|---|
| 1 | **Live Monitor** | `/analytics/live-monitor/` | 8 KPI cards (Total Purchase, Loyalty Sale, Total Bills, Loyalty Bills, Burn Points, Total Live Locations, Data Received, Repeat Bills) + bill-by-bill stream |
| 2 | **Customer Data** | `/analytics/CustomerDataReportView/` | Raw customer list (export) |
| 3 | **Transaction Data** | `/analytics/TransactionDataView/` | Raw transactions list |
| 4 | **Repeat Customers** | `/analytics/repeat-customers-report-data/` | List of customers with ≥2 visits |
| 5 | **Top Customers** | `/analytics/top-customers/` | Top N by Visits or Purchase, with bar chart |
| 6 | **Fraud Report** | `/analytics/fraudReport/` | Flag suspicious activity |
| 7 | **Pending Bills** | `/analytics/PendingBillsReport/` | Bills awaiting processing |
| 8 | **Feedback Data** | `/analytics/feedbackcustomerdata/` | Customer feedback responses |
| 9 | **Missed Call Requests** | `/analytics/missedrequestcustomer/` | IVR / missed-call campaign captures |
| 10 | **Location Wise Customer** | `/analytics/LocationWiseCustomerReport/` | Customer distribution by home store |
| 11 | **Expiry Points Report** | `/analytics/ExpiryPointsReport/` | Points expiring soon, by customer |
| 12 | **Active Coupon Report** | `/analytics/ActiveCouponReport/` | All currently-active issued coupons |

### A4. ANALYTICS / CAMPAIGN ROI
| # | Report | URL |
|---|---|---|
| 1 | **M'ktg Campaign ROI** | `/analytics/MarketingCampaignROISummary/` |
| 2 | **M'ktg Campaign Data** | `/analytics/marketingcampaigndata/` |
| 3 | **Coupon Campaign ROI** | `/analytics/CouponCampaignROISummary/` |
| 4 | **Coupon Redemption** | `/analytics/coupon-redemption-report/` |
| 5 | **Coupon Campaign** | `/analytics/CouponCampaignView/` |
| 6 | **WhatsApp Campaign ROI** | `/analytics/WhatsAppCampaignROISummary/` |
| 7 | **RCS Campaign ROI** | `/analytics/RCSCampaignROISummary/` |

### A5. SETTINGS
| # | Module | URL | Purpose |
|---|---|---|---|
| 1 | **Program Setup** | `/settings/programsetup/` | Program Name, Mall Name, SMS Sender ID, Program URL, Logo, Earn Logic, Redeem Logic |
| 2 | **Logic Configuration** | `/settings/logicconfig/` | Tier Management (Percent Points OR Points Per Spend), tier min/max amounts |
| 3 | **Location Master** | `/settings/locations/` | Store catalog |
| 4 | **SKU Master** | `/settings/skumst/` | Item / SKU catalog |
| 5 | **Reward Category** | `/settings/rwrdcategories/` | Reward category taxonomy |
| 6 | **Reward Brands** | `/settings/rwrdbrands/` | Partner brands available for redemption |
| 7 | **Reward Gift Vouchers** | `/settings/rwrdgvs/` | GV catalog (denomination, validity) |
| 8 | **SMS Configuration** | `/settings/smsconfig/` | DLT template ID, sender ID setup |
| 9 | **Reports Criteria** | `/settings/customercriteria/` | Saved filter presets for reports |

### A6. SUPPORT DESK (L1 customer service)
| # | Module | URL |
|---|---|---|
| 1 | **User Logins** | `/supportdesk/mstusers/` |
| 2 | **Search Redeem Points OTP** | `/supportdesk/searchrdmptsdtl` |
| 3 | **Search Redeem Coupon OTP** | `/supportdesk/searchrdmcpsdtl` |
| 4 | **Reactivate Coupon** | `/supportdesk/redeemedcouponsearch` |
| 5 | **Reactivate Redeem Points** | `/supportdesk/redeempointsearch` |
| 6 | **Customer Deactivate** | `/supportdesk/customerdeactivatedetails` |
| 7 | **Customer Reactivate** | `/supportdesk/customerreactivatedetails/` |
| 8 | **Unsubscribe Customer** | `/settings/UnSubscribeCustomersList/` |

---

## B. OUR NEW SYSTEM (KAZO Fundle) — What We Already Have

✅ DASHBOARDS: Command Center · Sales · Customer Analytics · Loyalty · Campaign Performance · Store · **RFM & Churn (11 segments + 5×5 heatmap)** · **Cohorts & Segments** · Points Economics · Campaign ROI · Executive Summary · **NPS**

✅ CUSTOMERS: Customer 360 (drawer + timeline + lifetime spend/visit/earn/burn)

✅ MARKETING: Campaigns · Coupons · **Auto Campaigns (Birthday / Anniversary / Win-back automation)**

✅ COMMUNICATIONS: Karix-integrated Templates · Bulk Send Jobs · Provider Settings

✅ AI TOOLS: **Fundle Brain (LLM chat over live data)** · floating FAB on every page · post-ingest AI narrative

✅ DATA: Historical Upload (CSV/XLSX with integrity check + skipped-row recovery) · **5 Raw Data Reports with drill-down**

✅ OPERATIONS: Stores · Item Master · **Live API Monitor (every internal call logged)**

✅ SUPPORT: Tickets · NPS Inbox

✅ REPORTS: Reports & Exports · Exec Digests · Formula Catalog

✅ CONFIGURATION: Loyalty Rules · Public Site CMS

✅ ADMIN: User Management

---

## C. GAP MATRIX — What's MISSING in Our System

### 🔴 P0 — Critical / Launch-Blockers

| Gap | Where it lives in legacy | Effort | Notes |
|---|---|---|---|
| **Rewards Desk module (7 pages)** | A1 (all 7) | High | We have backend POS APIs but NO desk-operator UI. Desk staff currently can't operate without legacy. |
| → Customer Search by mobile | `/CustomerSearch/` | S | Backend exists |
| → New Customer Registration | `/CustRegistration/` | S | Backend exists |
| → Manual Bill Entry | `/EnterBill/` | M | Critical for franchisee desks without POS integration |
| → Redeem Points (OTP) | `/RedeemPoints/` | M | Backend `/api/pos/posRedeemPoint*` exists |
| → Redeem Coupon (OTP) | `/RedeemCoupon/` | M | We have coupon engine but no live-redeem flow |
| → Redeem Points → Gift Voucher | `/giftvouhcersearch/` | M | NEW — no GV concept in our system yet |
| → Customer Profile Edit | `/CustomerProfileEdit/` | S | Currently only via admin Customer 360 |
| **Logic Configuration page (tier rules editor)** | A5 #2 | M | We have Loyalty Rules but legacy has a richer Tier-Management interface with "Percent Points" vs "Points Per Spend" modes |
| **Support Desk reactivate / deactivate flows** | A6 #4–7 | M | No way to reverse a coupon/point redemption or restore a deactivated customer |
| **Unsubscribe Customer list** | A6 #8 | S | Compliance-critical (DND / DLT regulations) |

### 🟡 P1 — Important Reports / Operational Tools

| Gap | Where it lives | Effort | Notes |
|---|---|---|---|
| **Fraud Report** | A3 #6 | M | Suspicious-pattern flags (multi-bill in short window, large redemptions, etc.) |
| **Pending Bills Report** | A3 #7 | S | Bills ingested but not yet processed/awarded |
| **Expiry Points Report (by customer)** | A3 #11 | S | We show liability total; legacy shows per-customer expiry list (action-able) |
| **Active Coupon Report** | A3 #12 | S | All currently issued + unused coupons |
| **Top Customers (dedicated)** | A3 #5 | S | We have it via Customer 360 sort, no dashboard yet |
| **Repeat Customers (raw list)** | A3 #4 | S | We have repeat *purchases* analytics, not a raw repeat-customer drilldown |
| **Location Wise Customer Report** | A3 #10 | S | Per-store customer counts (different from store performance) |
| **WhatsApp Campaign ROI / RCS Campaign ROI** | A4 #6–7 | M | Channel-specific breakdowns (we have generic Campaign ROI) |
| **Audit search by OTP** | A6 #2–3 | S | Compliance / dispute resolution tool |
| **Reward Brands master** | A5 #6 | M | Partner-brand catalog for redemption marketplaces |
| **Reward Gift Vouchers master** | A5 #7 | M | GV catalog with denominations & validity |
| **Reward Category** | A5 #5 | S | Taxonomy for reward shop |
| **DLT SMS Configuration UI** | A5 #8 | M | DLT template ID / sender ID registration (regulatory) |

### 🟢 P2 — Nice-to-Have / Niche

| Gap | Where | Notes |
|---|---|---|
| **Feedback Data report** | A3 #8 | Generic feedback inbox (distinct from NPS) |
| **Missed Call Requests** | A3 #9 | IVR / missed-call campaign captures |
| **Saved Reports Criteria** | A5 #9 | User-saved filter presets across reports |
| **M'ktg Campaign Data (raw)** | A4 #2 | Raw send-level data |

---

## D. WHERE WE'RE AHEAD OF LEGACY ⭐

| Feature | Why it matters |
|---|---|
| **Fundle Brain (LLM chat)** | Ask ANY question in natural language; brain has 8+ tools (overall KPIs, RFM, top stores, liability, top cities). Legacy has none. |
| **RFM & Churn — 11 segments + 5×5 heatmap** | Legacy only shows raw counts. We do Champions / At-Risk / Lost / Hibernating / Promising / etc. |
| **Cohorts & Retention Triangle** | Legacy has none |
| **NPS module (Promoter/Passive/Detractor)** | Legacy has only generic Feedback |
| **Auto Campaigns** | Birthday + Anniversary + Win-back daily automation. Legacy needs manual campaigns. |
| **Live API Monitor** | Every internal API logged with body+status+actor+IP. Critical for compliance + debugging. |
| **AI Post-Ingest Narrative** | Every upload → GPT-5 explains what changed |
| **Multi-Brand Abstraction (brand.config.js)** | Clone for new brand in ~10 min. Legacy is hardcoded NewU. |
| **Date Range Picker with custom range** | Legacy has only start_date/end_date inputs |
| **CSV/XLSX/PDF exports across the board** | Legacy has CSV only |
| **Editorial UI design (Inter, tabular nums, tight typography)** | Legacy is a generic Bootstrap admin template (purple gradient header) |
| **CSV/XLSX historic upload with integrity check + skipped-row recovery** | Legacy has no batch upload tool |
| **Karix bulk-send Campaign Manager (WhatsApp/SMS/RCS in one place)** | Legacy has ROI but no bulk-send-from-UI |

---

## E. RECOMMENDATIONS

### Phase 1 — Launch Parity (must-have to fully replace legacy)
1. **Build Rewards Desk** (7 pages, ~10 days). All backends already exist; this is a UI sprint.
2. **Add Logic Configuration page** with Tier Management UI (Percent Points / Points Per Spend modes).
3. **Add Support Desk** reactivate/deactivate/unsubscribe flows.
4. **Build Expiry Points Report** + **Active Coupon Report** + **Top Customers** + **Repeat Customers list** (~3 days as a "P1 reports sprint").
5. **Add WhatsApp / RCS Campaign ROI breakdowns** to the existing Campaign ROI dashboard.

### Phase 2 — Operational Completeness
- Fraud Report
- Pending Bills Report
- Location Wise Customer
- DLT SMS Configuration UI
- Audit search by OTP / dispute-resolution tools

### Phase 3 — Reward Marketplace (if NewU plans to expand redemption beyond points)
- Reward Categories
- Reward Brands
- Reward Gift Vouchers catalog with denominations + validity

---

## F. SUMMARY VERDICT

**Our system is functionally ahead in analytics, AI, and automation** — Fundle Brain alone is a category-leading differentiator. But **we are missing the operational "Rewards Desk"** that desk staff use day-to-day in stores, and several specialised reports (Fraud, Expiry, Active Coupons, Pending Bills).

To fully replace newu.fundlezone.com in production, we need **~3 weeks of focused build** on the items in Phase 1 above. Phase 2 is another ~2 weeks. After that, we exceed legacy in every dimension.
