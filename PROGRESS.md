# EquityCompCalculator — Progress Tracker

Detailed module-by-module tracker for Project 1 of the equity-comp portfolio.

**Master tracker:** [`../PROGRESS.md`](../PROGRESS.md)
**Strategic plan:** [`~/Documents/CEPI/PROJECT_PLAN_2026.md`](../../CEPI/PROJECT_PLAN_2026.md)
**Target MVP date:** **2026-07-21** (SCU CEPI Symposium)

---

## 📸 Current snapshot

| Metric | Value |
|---|---|
| **Modules complete** | 1 of 5 (ISO Exercise Modeler) |
| **Tests passing** | 8 of 8 |
| **Lines of code** | ~600 |
| **Deployment** | localhost only (not pushed/deployed) |
| **GitHub** | _repo not yet created_ |
| **Live URL** | _pending Streamlit Cloud deploy_ |

---

## 📦 Module status table

| # | Module | UI | Logic | Tests | Deployed | Spec source |
|---|---|---|---|---|---|---|
| 1 | **ISO Exercise Modeler** | ✅ | ✅ | ✅ 8/8 | localhost | Tax PPT 04 |
| 2 | **ESPP Calculator** | ⬜ | ⬜ | ⬜ | — | Tax PPT 06 + EPD&A PPT 05 |
| 3 | **§83(b) Decision Tool** | ⬜ | ⬜ | ⬜ | — | Tax PPT 02 + 05 |
| 4 | **RSU Vest + Sell-to-Cover Modeler** | ⬜ | ⬜ | ⬜ | — | Tax PPT 05; EPD&A PPT 02 |
| 5 | **§16 Form 4 Deadline Tracker** | ⬜ | ⬜ | ⬜ | — | Law PPT 02 + 07 |

**Legend:** ✅ done · 🟡 in progress · ⬜ not started

---

## Module 1: ISO Exercise Modeler ✅

**Spec source:** [Tax PPT 04 (IRC §422 ISOs)](../../CEPI/Study%20Guides/Level-1-Attempt-2/Taxation/04_IRC_Section_422_ISOs.pptx)

### Done
- [x] `lib/iso_calc.py` — `ISOExerciseInputs`, `ISOExerciseOutputs` dataclasses
- [x] `calculate_iso_exercise()` — spread, dual basis, QD vs DD classification
- [x] `estimate_amt_due()` — simplified 2025 AMT calc (exemption + phaseout + 26%/28% bracket)
- [x] `pages/1_ISO_Exercise_Modeler.py` — sidebar inputs + 3 output sections + statutory references expander
- [x] `tests/test_iso_calc.py` — 8 test cases:
  - [x] `test_qd_scenario_classic` — classic QD with held > 2 yrs/1 yr
  - [x] `test_dd_same_day_sale` — cashless exercise + same-day sale = DD
  - [x] `test_dd_with_appreciation_short_term` — DD held < 1 year
  - [x] `test_dd_failed_two_year_grant_rule` — DD due to grant rule violation
  - [x] `test_dd_underwater_sale` — sale below strike → $0 ordinary income + capital loss
  - [x] `test_atm_exercise_no_spread` — strike = FMV → no AMT preference
  - [x] `test_amt_estimation_large_spread` — meaningful AMT due
  - [x] `test_amt_estimation_small_spread_no_amt` — exemption absorbs small spread

### Pending (post-MVP nice-to-haves)
- [ ] Add visual chart of spread × time (line chart showing stock price + key thresholds)
- [ ] Add a "what date can I sell to convert DD → QD?" prompt with countdown
- [ ] AMT credit (Form 8801) carryforward calculator
- [ ] Multi-state tax overlay (CA + NY + state-of-residence)
- [ ] Print/export results as PDF for tax-prep records

### Known issues
- AMT calculation uses **2025 thresholds hardcoded** — will need annual update or year-selector
- §3121(a)(22) (no FICA on ISO DD) is referenced in UI text but not currently quantified
- No input validation for inverted dates (e.g., sale before exercise) — Streamlit `date_input` `min_value` largely prevents this, but worth double-checking

### Design notes
- Used `@dataclass(frozen=True)` for inputs/outputs — immutable, easy to test, no accidental mutation
- "QD" vs "DD" classification uses `Literal["QD", "DD"]` for type safety
- Holding period thresholds: per Treas. Reg. §1.422-1(a) — "more than 1 year" + "more than 2 years" (`>` not `>=`)
- AMT estimator deliberately simplified — disclaimer in UI directs users to Form 6251 + tax pro

---

## Module 2: ESPP Calculator ⬜

**Spec source:** [Tax PPT 06 (§423 ESPPs)](../../CEPI/Study%20Guides/Level-1-Attempt-2/Taxation/06_IRC_Section_423_ESPPs.pptx) + [EPD&A PPT 05 (ESPP Features)](../../CEPI/Study%20Guides/Level-1-Attempt-2/Equity-Plan-Design-Admin/05_ESPP_Features.pptx)

**Target build window:** Jul 1-7, 2026

### Planned scope
- Inputs: offering price (FMV at offering), purchase price (FMV at purchase), employee contribution rate, discount % (typically 5-15%), look-back yes/no, sale price, sale date, offering date, purchase date
- Outputs:
  - Effective purchase price (post-discount + look-back)
  - $25K limit check per §423(b)(8) (offering-date FMV)
  - QD vs DD classification (held > 1 yr post-purchase + > 2 yrs post-offering)
  - QD ordinary income = lesser of: (offering-date discount) or (sale gain over purchase)
  - QD capital gain = remainder
  - DD ordinary income = spread at purchase (FMV at purchase − purchase price)
  - DD capital gain = sale − FMV at purchase

### Test cases needed
- [ ] QD with look-back, sale price > offering FMV (basic QD path)
- [ ] QD with look-back, sale price < offering FMV (lesser-of formula tests the gain-side)
- [ ] DD ordinary income = full purchase-date spread
- [ ] $25K limit excess scenarios
- [ ] 15% maximum discount enforcement (warn if user inputs > 15%)
- [ ] No-look-back plan path

### Design questions
- [ ] How to handle multiple offering/purchase periods on one screen? Or one period at a time?
- [ ] Should the calculator support 27-month offering periods (max for look-back plans)?
- [ ] Default values for FMV — pick a recent stock example (NVDA? AAPL?) or just generic $50?

---

## Module 3: §83(b) Decision Tool ⬜

**Spec source:** [Tax PPT 02 (IRC §83)](../../CEPI/Study%20Guides/Level-1-Attempt-2/Taxation/02_IRC_Section_83.pptx) + [Tax PPT 05 (Restricted Stock)](../../CEPI/Study%20Guides/Level-1-Attempt-2/Taxation/05_Restricted_Stock_Tax.pptx)

**Target build window:** Jul 8-14, 2026

### Planned scope
- Inputs: shares, grant FMV, projected vest FMV, marginal ordinary tax bracket, projected LTCG rate, vesting schedule, forfeiture probability estimate
- Outputs:
  - With §83(b): ordinary income at grant + LTCG on appreciation (assuming hold > 1 yr post-grant)
  - Without §83(b): ordinary income at vest + STCG/LTCG on post-vest appreciation
  - Net tax savings = without − with
  - Risk-adjusted expected value = net savings × (1 − forfeiture probability)
  - Generate sample §83(b) election letter as downloadable PDF (per IRS sample)

### Test cases needed
- [ ] Low-FMV grant (early-stage startup): big savings if vests
- [ ] High-FMV grant: smaller savings, higher risk
- [ ] Forfeiture probability sweeps
- [ ] §83(b) letter PDF generation matches IRS template

### Design questions
- [ ] Embed PDF preview, or just download button?
- [ ] Election letter template should include: employee SSN field? (probably blank for privacy — let user fill in)

---

## Module 4: RSU Vest + Sell-to-Cover Modeler ⬜

**Spec source:** [Tax PPT 05 (Restricted Stock)](../../CEPI/Study%20Guides/Level-1-Attempt-2/Taxation/05_Restricted_Stock_Tax.pptx) + [EPD&A PPT 02 (Restricted Stock)](../../CEPI/Study%20Guides/Level-1-Attempt-2/Equity-Plan-Design-Admin/02_Restricted_Stock.pptx)

**Target build window:** August 2026 (post-symposium)

### Planned scope
- Inputs: shares vesting, FMV at vest, federal withholding rate (22% default or 37% if > $1M), state withholding rate, FICA rate, supplemental income status
- Outputs:
  - Gross income at vest (FMV × shares)
  - Total tax withheld (federal + FICA + state)
  - Shares sold to cover taxes (sell-to-cover)
  - Net shares retained
  - Cost basis going forward
  - Future sale capital gain/loss scenarios

### Design questions
- [ ] Show calendar of vesting events for a 4-year schedule (visualize the cliff + monthly accrual)?
- [ ] Compare share-settled vs net-share vs cashless settlement methods?

---

## Module 5: §16 Form 4 Deadline Tracker ⬜

**Spec source:** [Law PPT 02 (Securities Exchange Act of 1934)](../../CEPI/Study%20Guides/Level-1-Attempt-2/Corporate-Securities-Law/02_Securities_Exchange_Act_of_1934.pptx) + [Law PPT 07 (Sarbanes-Oxley)](../../CEPI/Study%20Guides/Level-1-Attempt-2/Corporate-Securities-Law/07_Sarbanes_Oxley.pptx)

**Target build window:** August 2026 (post-symposium)

### Planned scope
- Inputs: transaction date, transaction type (M/D/F/A/G), insider status (officer/director/10% holder)
- Outputs:
  - Form 4 deadline = transaction date + 2 business days (skip US federal holidays + weekends)
  - 6-month look-back + look-forward window for §16(b) short-swing matching
  - Short-swing exposure simulator: input N transactions → calculate disgorgeable profit
- Bonus: simple table of Form 3 / Form 4 / Form 5 deadlines + thresholds

### Design questions
- [ ] Use `python-dateutil` or write a small US-holiday calendar?
- [ ] Show calendar widget visualizing 6-month windows?

---

## 🚀 Deployment status

### Local development
- ✅ `python3.11 -m venv .venv` created
- ✅ Dependencies installed (see `requirements.txt`)
- ✅ `streamlit run streamlit_app.py` works (HTTP 200 on home + ISO pages)

### Git
- ⬜ `git init` not yet run
- ⬜ No commits
- ⬜ No remote configured

### GitHub
- ⬜ Repo not yet created at `github.com/priyanka-upreti/equitycomp`
- ⬜ Need: wife's Personal Access Token OR `gh` CLI auth setup

### Streamlit Cloud
- ⬜ Wife not yet signed up at share.streamlit.io
- ⬜ Repo not yet connected
- ⬜ App not yet deployed
- ⬜ Live URL not yet provisioned

### Pre-deploy checklist
- [ ] All modules MVP-complete (ISO ✅ + ESPP + §83(b))
- [ ] Tests passing (currently 8/8 for ISO; need ESPP + §83(b) tests)
- [ ] README has screenshots
- [ ] `requirements.txt` clean (no dev-only packages)
- [ ] Disclaimer text reviewed by wife
- [ ] Sample/default inputs reasonable (not zeros)
- [ ] Mobile responsiveness test
- [ ] Test deploy → real URL works

---

## 📋 Open UX / design questions for wife to decide

| # | Question | Default if no answer |
|---|---|---|
| 1 | Color scheme — Streamlit default (blue) or custom theme via `.streamlit/config.toml`? | Streamlit default |
| 2 | Logo / favicon? | None for MVP |
| 3 | Add "About" page with bio + LinkedIn link? | Skip for v1 |
| 4 | Add Google Analytics tracking? | Skip for v1 (privacy) |
| 5 | Add feedback form ("Found a bug? Email me")? | Just GitHub Issues link in README |
| 6 | Default scenario values — generic ($50 stock) or example-based (e.g., a 2024 tech IPO)? | Generic $50 stock |
| 7 | Show statutory references inline or in expanders? | Currently using expanders (collapsed by default) |
| 8 | Page width — wide (current) or centered narrower layout? | Wide currently |

---

## 🛠️ Quick reference

### Run locally
```bash
cd ~/Documents/EquityProjects/EquityCompCalculator
source .venv/bin/activate
streamlit run streamlit_app.py
# Open http://localhost:8501
```

### Run tests
```bash
cd ~/Documents/EquityProjects/EquityCompCalculator
.venv/bin/pytest tests/ -v
```

### Run specific test
```bash
.venv/bin/pytest tests/test_iso_calc.py::test_qd_scenario_classic -v
```

### Adding a new module (checklist)
1. Create `lib/<module>_calc.py` with dataclasses + pure functions
2. Write tests in `tests/test_<module>_calc.py` — validate against PPT worked examples
3. Run `pytest` — all tests must pass before UI work
4. Create `pages/N_<Display_Name>.py` — Streamlit UI
5. Update `streamlit_app.py` home page to advertise the new module
6. Update this `PROGRESS.md` — mark items done
7. Update parent `../PROGRESS.md` for cross-project visibility

---

## 📅 Session log (Project 1 only)

### Session 1 — 2026-06-24
**Outcome:** Working ISO Exercise Modeler running on localhost

- Created project skeleton (venv, requirements, .gitignore, README)
- Built home page (`streamlit_app.py`) with 3-tool cards
- Built ISO module (`lib/iso_calc.py` + `pages/1_ISO_Exercise_Modeler.py`)
- Wrote 8 tests; all passing
- Verified `localhost:8501` serving home + ISO page
- Created this PROGRESS.md

**Time spent:** ~2 hours
**Lines added:** ~600 (300 calc logic, 200 UI, 100 tests)
**Next session goals:** wife reviews ISO UX; then begin ESPP Calculator

---

## 📌 Notes / lessons learned

- **Python 3.9.6 system Python is too old for Streamlit Cloud** — must use 3.11+ (installed via Homebrew)
- **Streamlit's multi-page convention:** any `.py` in `pages/` gets auto-discovered + appears in sidebar. Leading number controls order.
- **Frozen dataclasses are great for tax math** — immutable, testable, no accidental mutation between calc + UI
- **AMT thresholds change annually** — hardcoding 2025 numbers means we'll need to update for 2026 tax year
- **§3121(a)(22) is one of the most-overlooked ISO benefits** — no FICA on DD spread (regular wages do have FICA). Worth calling out in UI text + at symposium conversations.
