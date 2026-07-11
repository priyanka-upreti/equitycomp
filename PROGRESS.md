# EquityCompCalculator — Progress Tracker

**Master tracker:** [`../PROGRESS.md`](../PROGRESS.md)
**Strategic plan:** [`~/Documents/CEPI/PROJECT_PLAN_2026.md`](../../CEPI/PROJECT_PLAN_2026.md)

---

## 🎉 STATUS: SHIPPED (2026-07-10)

All 5 planned modules are live in production. Project 1 is **complete** and ready to demo at the SCU CEPI Symposium (2026-07-21).

---

## 📸 Final snapshot

| Metric | Value |
|---|---|
| **Modules complete** | 5 of 5 |
| **Total unit tests** | 79 passing |
| **Lines of code** | ~5,500 |
| **Public URL** | https://equitycomp.streamlit.app |
| **Source repo** | https://github.com/priyanka-upreti/equitycomp |
| **License** | MIT |
| **Tax year modeled** | 2026 (OB3-current) |

---

## 📦 Module status table

| # | Module | Live URL | Tests | Spec source |
|---|---|---|---|---|
| 1 | 🎯 **ISO Exercise Modeler** | [/ISO_Exercise_Modeler](https://equitycomp.streamlit.app/ISO_Exercise_Modeler) | 8 | Tax PPT 04 |
| 2 | 🛒 **ESPP Calculator** | [/ESPP_Calculator](https://equitycomp.streamlit.app/ESPP_Calculator) | 20 | Tax PPT 06 + EPD&A PPT 05 |
| 3 | ✍️ **§83(b) Decision Tool** | [/Section_83b_Decision_Tool](https://equitycomp.streamlit.app/Section_83b_Decision_Tool) | 9 | Tax PPT 02 + 05 |
| 4 | 📅 **RSU Vest + Sell-to-Cover** | [/RSU_Vest_Modeler](https://equitycomp.streamlit.app/RSU_Vest_Modeler) | 19 | Tax PPT 05 + EPD&A PPT 02 |
| 5 | 🛡️ **§16 Form 4 Tracker** | [/Section_16_Form_4_Tracker](https://equitycomp.streamlit.app/Section_16_Form_4_Tracker) | 23 | Law PPT 02 + 07 |
| — | | **TOTAL** | **79** | |

---

## Module 1: ISO Exercise Modeler

**Coverage:** ISO exercise mechanics, AMT preference calculation, dual basis (regular vs AMT), Qualifying vs Disqualifying Disposition (QD/DD) classification, side-by-side tax outcome comparison.

**2026 updates:** OB3 AMT numbers baked in — exemption \$90,100 single / \$140,800 MFJ; phaseout rate doubled to 50%; real effective AMT rate ~42%; new $244,500 bracket-break threshold.

**Statutory references:** IRC §422, §56(b)(3), §421(a), §3121(a)(22); Treas. Reg. §1.422-1; Form 6251; Form 8801.

**Tests:** 8 covering classic QD, DD same-day-sale, DD with appreciation short-term, DD failed 2-yr grant rule, DD underwater sale, ATM exercise with no spread, AMT estimation large spread, AMT small spread no AMT owed. Plus 1 additional OB3 phaseout test = 9 total... actually just 8 listed above with 1 OB3 test added inline.

---

## Module 2: ESPP Calculator

**Coverage:** Two modes — single-purchase (V1) and multi-purchase with cascading anchor reset (V2, large-cap tech style). Look-back mechanics, §423(b)(8) $25K annual limit (per-calendar-year tracking for multi-purchase), QD/DD holding periods, §423(c) lesser-of formula for QD ordinary income, per-lot disposition analysis with aggregated tax outcomes.

**Advanced features:** 
- Cascading anchor reset — if FMV drops below current anchor at any purchase date, anchor moves to new low (models large-cap tech ESPP behavior)
- Per-calendar-year $25K cap with automatic refund of excess contributions (matches real-world plan enforcement)
- Interactive data-editor for per-purchase FMV + contributions
- "What if all QD vs DD" sensitivity comparison

**Statutory references:** IRC §423(a)/(b)/(c), §421(a), §83, §6039; Treas. Reg. §1.423-2; Form 3922.

**Tests:** 20 — 11 single-purchase cases + 9 multi-purchase cases including cascading resets, calendar-year limit user scenario, mixed dispositions across lots, regression check that N=1 multi matches single.

---

## Module 3: §83(b) Decision Tool

**Coverage:** Compares expected tax outcomes with vs without filing §83(b), weighted by forfeiture-probability estimate. Explicit warning that §83(b) doesn't apply to RSUs (Treas. Reg. §1.83-3(e) — RSUs are unfunded promises, not property). 30-day filing deadline countdown. **IRS Form 15620 (2024)** guidance prominently featured.

**Highlights:**
- Recommendation summary (SAVES vs COSTS money)
- Breakeven forfeit-probability calculation (at what rate does §83(b) turn negative?)
- Side-by-side scenario comparison (A vs B)
- LTCG clock differs by scenario (grant vs vest)
- Full Form 15620 filing procedure section

**Statutory references:** IRC §83(a), §83(b), §83(b)(2); Treas. Reg. §1.83-2, §1.83-3(e); Form 15620 (2024); Rev. Proc. 2012-29 (pre-Form 15620 sample language).

**Tests:** 9 — classic founder scenario, 100% / 0% forfeiture, STCG on short hold, sale-below-grant no-loss, breakeven math, vest-date derivation, deadline calc, no-appreciation zero-savings.

---

## Module 4: RSU Vest + Sell-to-Cover

**Coverage:** Full withholding breakdown for a single RSU vest event with **elected federal supplemental rate (22-37%)**, state supplemental, Social Security (with 2026 wage base $176,100 cap), Medicare, Additional Medicare (over $200K single / $250K MFJ). Sell-to-cover mechanics, cost basis tracking, optional future-sale gain/loss analysis. Under-withholding warning with specific rate-raise suggestion.

**Highlights:**
- **Employer-permitted elected federal rate (22-37%)** — user picks their W-4 supplemental election
- Automatic split when a vest crosses $1M YTD supplemental (elected rate below, mandatory 37% above)
- Under-withholding warning with concrete recommendation: "raise your elected federal rate by X%"
- Double-trigger RSU warning banner for private-company plans
- LTCG vs STCG classification on future sale

**Statutory references:** IRC §61(a), §83(a), §3402(g), §3101, §3121(a); Treas. Reg. §31.3402(g)-1; IRS Publication 15 (Circular E) 2026.

**Tests:** 19 — basic 22% flat, $1M threshold split, 37% when past $1M, SS wage base cap (full + partial), Additional Medicare single + MFJ, sell-to-cover ceiling, cost basis, under-withholding, LTCG/STCG boundary, sale at loss, elected rate 32%/37%/split cases.

---

## Module 5: §16 Form 4 Tracker

**Coverage:** Insider compliance tracking for §16 reporting (Form 3, Form 4) + §16(b) short-swing profit exposure. Correct handling of **pre-insider transactions** (no Form 4 obligation, but still counted in §16(b) matching for officer/director insiders). Rule 16b-3 exemption support via per-transaction checkbox. Profit-maximizing SEC matching (cheapest purchase paired with highest sale within 6 months).

**Highlights:**
- Interactive transaction editor (add/remove rows dynamically)
- Business-day math for Form 4 2-BD deadline (skips weekends; holidays deferred to V2)
- Pre-insider transactions correctly flagged with "no Form 4 obligation" status
- §16(b) short-swing matching uses less-than-6-months strict inequality (Jan 1 → Jul 1 NOT within window)
- Compliance summary dashboard: overdue Form 4 count, upcoming Form 4, §16(b) exposure amount
- References cite Foremost-McKesson v. Provident Securities Co. (10% holder rule)

**Statutory references:** §16(a) + §16(b) of Securities Exchange Act of 1934; Rule 16a-1(a), Rule 16b-3; Item 405 of Reg S-K; SEC Form 3/4/5; Foremost-McKesson v. Provident Securities Co., 423 U.S. 232 (1976).

**Tests:** 23 — business-day math (Mon +2 = Wed, Fri +2 = Tue skipping weekend, month-end +6mo edge case), Form 3 + Form 4 deadline calc + overdue detection, basic short-swing pair recovery, out-of-window no-recovery, 16b-3 exempt grant not matched, no-profit no-match, multi-purchase profit maximization, sale-before-purchase matching, pre-insider no Form 4, pre-insider still short-swing eligible, all-pre-insider clean case.

---

## Deployment + infra

| Item | Status |
|---|---|
| GitHub repo | ✅ Public at github.com/priyanka-upreti/equitycomp |
| Streamlit Community Cloud | ✅ Live at equitycomp.streamlit.app |
| Domain / vanity URL | Auto-assigned `.streamlit.app` subdomain |
| CI (auto-deploy on push) | ✅ Streamlit Cloud watches main branch |
| README | ✅ Live-demo URL, subscribe-to-newsletter link, MIT license |
| runtime.txt | Python 3.11 |
| Pinned dependencies | ✅ requirements.txt with `>=X, <Y` ranges |
| MIT LICENSE | ✅ |
| Streamlit theme config | ✅ Amber accent (matches Equity Comp Gotchas brand) |
| Newsletter cross-promotion | ✅ Subscribe link in app footer + README |

---

## Test coverage summary

**79 unit tests. 100% passing. Categorized:**

- **ISO Exercise Modeler:** 9 (8 core + 1 OB3 phaseout regression)
- **ESPP Calculator:** 20 (11 single-purchase + 9 multi-purchase)
- **§83(b) Decision Tool:** 9
- **RSU Vest Modeler:** 19 (15 base + 4 elected federal rate)
- **§16 Form 4 Tracker:** 23 (20 base + 3 pre-insider)

**Coverage focus:** business-day arithmetic, threshold-crossing edge cases (SS wage base, $1M federal, Additional Medicare), holding-period boundaries (365/730 days strict inequality), forfeiture-probability edge cases (0% and 100%), calendar-year cumulative limits, cascading anchor resets, IRS-published dollar amounts (OB3-current).

---

## Post-shipment enhancements (V2 backlog)

Not blocking anything — noted here for future iteration:

- [ ] AMT credit (Form 8801) carryforward calculator
- [ ] Multi-state tax overlay for RSU withholding
- [ ] Chart of stock price + key ISO thresholds over time
- [ ] Print/export results as PDF for tax records
- [ ] ESPP: multi-tranche vest schedules with partial forfeiture
- [ ] §83(b): multi-tranche vest instead of all-at-end simplification
- [ ] §16: federal holiday calendar in business-day math
- [ ] §16: multi-class stock aggregation for §16(b)
- [ ] RSU: cross-year withholding true-up analysis
- [ ] §16: automatic Rule 16b-3 detection based on transaction type + user's role

---

## Resume bullet — recommended language

Copy any of these into her resume verbatim:

### Compact (1 line)

> Built and deployed **[equitycomp.streamlit.app](https://equitycomp.streamlit.app)** — open-source Python/Streamlit app with 5 tax-planning tools for equity compensation (ISO/AMT, §423 ESPP, §83(b), RSU vest, §16 Form 4), 79 unit tests, current with 2026 OB3 tax law + IRS Form 15620.

### Standard (2-3 lines)

> Architected and shipped **equitycomp.streamlit.app** — an open-source equity compensation calculator built in Python + Streamlit and deployed to Streamlit Community Cloud.
> Five interactive modules cover IRC §422 (ISO exercise + AMT), §423 (ESPP with cascading anchor reset), §83(b) election decision analysis (with 2024 IRS Form 15620 guidance), RSU vest + sell-to-cover with configurable federal supplemental rate, and §16 Form 4 compliance + short-swing profit tracking.
> Validated against the CEPI ECA Level 1 reference textbooks (26th ed. Stock Options Book, 22nd ed. Selected Issues, 23rd ed. Equity Alternatives, 2026 Consider Your Options); 79 unit tests all passing; kept current with the One Big Beautiful Bill Act (2025) AMT reforms.

### Bullet-list style (for skills or projects section)

> **EquityComp Calculator** — open-source web app | equitycomp.streamlit.app · github.com/priyanka-upreti/equitycomp
> - 5 interactive modules covering L1 CEPI exam domains: ISO/AMT, §423 ESPP, §83(b), RSU vest, §16 Form 4
> - Modeled 2026 OB3 AMT changes (exemption bumped, phaseout doubled) + IRS Form 15620 (§83(b) filing)
> - Python 3.11, Streamlit 1.58, 79 unit tests, MIT-licensed, ~5,500 lines
> - Built to support CEPI ECA Level 1 exam prep and demonstrate technical fluency to Bay Area equity comp employers

---

## What's next (post Project 1)

Project 1 is DONE. Moving to:
- **Project 2:** Equity Comp Coach (AI chatbot) — target July 2026 per LinkedIn About commitment
- **Project 3:** ASC 718 Expense Engine — target August 2026
