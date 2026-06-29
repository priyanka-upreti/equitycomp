"""ESPP Calculator — Streamlit page.

Interactive tool for modeling a §423-qualified Employee Stock Purchase Plan:
- Purchase mechanics (look-back, discount, purchase price per share)
- §423(b)(8) $25,000 annual limit check
- Qualifying Disposition (QD) vs Disqualifying Disposition (DD) outcomes
- Side-by-side QD vs DD tax outcomes with the §423(c) lesser-of formula
- Simplified federal marginal tax estimate
"""

from datetime import date

import streamlit as st

# Make lib/ importable regardless of how streamlit launches
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.espp_calc import (  # noqa: E402
    ESPPInputs,
    calculate_espp_purchase,
    estimate_marginal_federal_tax,
)


st.set_page_config(
    page_title="ESPP Calculator",
    page_icon="🛒",
    layout="wide",
)

st.title("🛒 ESPP Calculator")
st.markdown(
    "Model a **§423-qualified Employee Stock Purchase Plan** purchase — see "
    "discount mechanics, the **$25K annual limit**, and the famous "
    "**§423(c) lesser-of formula** for QD ordinary income."
)

st.divider()

# ---------------------------------------------------------------------------
# Inputs in sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("📥 Plan + Offering")
    offering_fmv = st.number_input(
        "FMV at start of offering period (per share, USD)",
        min_value=0.01,
        value=100.00,
        step=0.01,
        format="%.2f",
    )
    purchase_fmv = st.number_input(
        "FMV at purchase date (per share, USD)",
        min_value=0.01,
        value=150.00,
        step=0.01,
        format="%.2f",
    )
    discount_pct = st.slider(
        "Discount % (max 15% per §423(b)(6))",
        min_value=0.0,
        max_value=0.15,
        value=0.15,
        step=0.01,
        format="%.0f%%",
    )
    has_lookback = st.checkbox(
        "Plan has look-back feature",
        value=True,
        help="If enabled, discount applies to the LOWER of offering FMV or "
        "purchase FMV — typically much more favorable to employees during "
        "stock appreciation.",
    )

    st.divider()
    st.header("📅 Dates + Contributions")
    offering_start_date = st.date_input(
        "Offering period start date",
        value=date(2024, 1, 1),
    )
    purchase_date = st.date_input(
        "Purchase date",
        value=date(2024, 6, 30),
        min_value=offering_start_date,
    )
    contributions = st.number_input(
        "Total contributions during offering ($)",
        min_value=0.0,
        value=8_500.00,
        step=100.00,
        format="%.2f",
    )

    st.divider()
    st.header("📤 Planned Sale")
    sale_date = st.date_input(
        "Sale date",
        value=date(2027, 1, 1),
        min_value=purchase_date,
    )
    sale_price = st.number_input(
        "Sale price (per share, USD)",
        min_value=0.01,
        value=200.00,
        step=0.01,
        format="%.2f",
    )

    st.divider()
    st.header("💰 Tax Estimate (optional)")
    other_income = st.number_input(
        "Other taxable income for the year ($)",
        min_value=0,
        value=150_000,
        step=1_000,
    )
    filing_status = st.radio(
        "Filing status",
        options=["single", "mfj"],
        format_func=lambda x: "Single" if x == "single" else "Married Filing Jointly",
        horizontal=True,
    )

# ---------------------------------------------------------------------------
# Run calculations
# ---------------------------------------------------------------------------

inputs = ESPPInputs(
    offering_start_fmv=float(offering_fmv),
    purchase_fmv=float(purchase_fmv),
    discount_pct=float(discount_pct),
    has_lookback=bool(has_lookback),
    offering_start_date=offering_start_date,
    purchase_date=purchase_date,
    sale_date=sale_date,
    sale_price=float(sale_price),
    contributions=float(contributions),
)
result = calculate_espp_purchase(inputs)

# ---------------------------------------------------------------------------
# At-purchase summary
# ---------------------------------------------------------------------------

st.header("📊 At Purchase")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Reference FMV", f"${result.reference_fmv:,.2f}")
with col2:
    st.metric("Purchase price / share", f"${result.purchase_price_per_share:,.2f}")
with col3:
    st.metric("Shares purchased", f"{result.shares_purchased:,.4f}")
with col4:
    st.metric("Bargain element / share", f"${result.bargain_element_per_share:,.2f}")

with st.expander("📖 How is the purchase price calculated?"):
    if has_lookback:
        st.markdown(
            f"""
**Look-back is enabled.** Purchase price uses the LOWER of:
- Offering-date FMV: `${offering_fmv:,.2f}`
- Purchase-date FMV: `${purchase_fmv:,.2f}`

Reference FMV = `${result.reference_fmv:,.2f}`
Discount applied: `{discount_pct * 100:.0f}%`
Purchase price = `${result.reference_fmv:,.2f} × (1 − {discount_pct:.2f})` = **`${result.purchase_price_per_share:,.2f}`**

The look-back is most valuable when stock appreciates during the offering — you lock in the discount against the lower starting price.
"""
        )
    else:
        st.markdown(
            f"""
**Look-back NOT enabled.** Discount applies only to purchase-date FMV:
- Purchase-date FMV: `${purchase_fmv:,.2f}`
- Discount: `{discount_pct * 100:.0f}%`
- Purchase price = `${purchase_fmv:,.2f} × (1 − {discount_pct:.2f})` = **`${result.purchase_price_per_share:,.2f}`**
"""
        )

# ---------------------------------------------------------------------------
# §423(b)(8) $25K Limit
# ---------------------------------------------------------------------------

st.header("📋 §423(b)(8) $25K Annual Limit")

limit_col1, limit_col2, limit_col3, limit_col4 = st.columns(4)
with limit_col1:
    st.metric(
        "Max shares allowed",
        f"{result.max_shares_under_25k_limit:,.2f}",
        help="$25,000 ÷ offering-date FMV (NOT purchase FMV, NOT actual price)",
    )
with limit_col2:
    st.metric(
        "Shares requested",
        f"{result.shares_requested:,.4f}",
        help="What your contributions would buy at the purchase price (uncapped).",
    )
with limit_col3:
    st.metric(
        "Shares actually purchased",
        f"{result.shares_purchased:,.4f}",
        help="Capped at the §423(b)(8) limit — most plans enforce this automatically.",
    )
with limit_col4:
    if result.is_within_25k_limit:
        st.success("✅ Within limit")
    else:
        st.error(f"❌ Capped — {result.shares_over_limit:,.2f} shares prevented")

if not result.is_within_25k_limit:
    st.warning(
        f"💵 **${result.excess_contributions_refunded:,.2f}** in excess contributions "
        f"will be refunded to you (most plans return un-applied payroll deferrals after "
        f"the cap is hit). Bargain element, taxes, and capital gains below are computed "
        f"on the **capped {result.shares_purchased:,.4f} shares** only."
    )

st.caption(
    "§423(b)(8) caps an employee's option-grant accrual at **$25,000 per calendar year** "
    "across all of the employer's §423 plans, measured at the **offering-date FMV**. "
    "Most plans enforce this at purchase by refunding excess payroll contributions; some "
    "plans allow excess purchases but those shares lose §423-qualified status (all "
    "discount becomes ordinary income at purchase)."
)

# ---------------------------------------------------------------------------
# Disposition classification
# ---------------------------------------------------------------------------

st.divider()
st.header("📅 Disposition Classification")

cls_col1, cls_col2 = st.columns([1, 2])

with cls_col1:
    if result.disposition == "QD":
        st.success(f"✅ **{result.disposition}** — Qualifying Disposition")
        st.caption("Both holding periods satisfied. Eligible for §423(c) lesser-of formula.")
    else:
        st.error(f"❌ **{result.disposition}** — Disqualifying Disposition")
        st.caption("Loses §423 QD benefit. Full bargain at purchase becomes ordinary income.")

with cls_col2:
    st.markdown(
        f"""
**Days post-offering-start:** {result.days_from_offering_start_to_sale} (need > 730 for QD)
{"✅" if result.holds_two_years_from_offering else "❌"} 2-year-from-offering rule

**Days post-purchase:** {result.days_from_purchase_to_sale} (need > 365 for QD)
{"✅" if result.holds_one_year_from_purchase else "❌"} 1-year-from-purchase rule
"""
    )

if result.qd_reason_failed:
    st.warning("**Why DD:**")
    for reason in result.qd_reason_failed:
        st.markdown(f"- {reason}")

# ---------------------------------------------------------------------------
# Side-by-side QD vs DD comparison
# ---------------------------------------------------------------------------

st.divider()
st.header("⚖️ Tax Outcome at Sale — Side-by-Side")

scenario_col1, scenario_col2 = st.columns(2)

with scenario_col1:
    st.subheader("If QD")
    st.markdown(
        f"""
**Ordinary income (W-2):** `${result.qd_ordinary_income:,.2f}`

**Capital gain (LTCG):** `${result.qd_capital_gain:,.2f}`

**Capital loss:** `${result.qd_capital_loss:,.2f}`

---

**§423(c) lesser-of formula:**

(1) `${offering_fmv:.2f} − ${result.purchase_price_per_share:.2f}` (offering FMV − purchase price) × {result.shares_purchased:,.4f} sh
(2) `${sale_price:.2f} − ${result.purchase_price_per_share:.2f}` (sale − purchase price) × {result.shares_purchased:,.4f} sh

→ ordinary income = max(0, lesser of (1), (2))
"""
    )

with scenario_col2:
    st.subheader("If DD")
    st.markdown(
        f"""
**Ordinary income (W-2, full bargain at purchase):** `${result.dd_ordinary_income:,.2f}`

**Capital gain ({'LTCG' if result.dd_capital_gain_is_long_term else 'STCG'}):** `${result.dd_capital_gain:,.2f}`

**Capital loss:** `${result.dd_capital_loss:,.2f}`

---

**DD math:**

Ordinary income = `(${purchase_fmv:.2f} − ${result.purchase_price_per_share:.2f}) × {result.shares_purchased:,.4f}` sh

Capital gain/loss = `(${sale_price:.2f} − ${purchase_fmv:.2f}) × {result.shares_purchased:,.4f}` sh

DD ordinary income IS subject to **FICA + Medicare** (unlike ISO).
"""
    )

if result.disposition == "QD":
    st.info(
        f"🎯 **Your current scenario is QD** — you keep the §423(c) lesser-of formula. "
        f"Ordinary income capped at ${result.qd_ordinary_income:,.2f}, with all remaining "
        f"gain (${result.qd_capital_gain:,.2f}) taxed at LTCG rates."
    )
else:
    st.warning(
        f"⚠️ **Your current scenario is DD** — full bargain at purchase "
        f"(${result.dd_ordinary_income:,.2f}) is ordinary income."
    )

# ---------------------------------------------------------------------------
# Federal tax estimate
# ---------------------------------------------------------------------------

st.divider()
st.header("💸 Federal Tax Estimate (planning only)")

# Pull the right ordinary income for the active disposition
active_ordinary = (
    result.qd_ordinary_income
    if result.disposition == "QD"
    else result.dd_ordinary_income
)
tax = estimate_marginal_federal_tax(
    ordinary_income=active_ordinary,
    other_taxable_income=float(other_income),
    filing_status=filing_status,
)

tax_col1, tax_col2, tax_col3 = st.columns(3)
with tax_col1:
    st.metric(
        "Incremental federal tax",
        f"${tax['incremental_federal_tax']:,.0f}",
        help="Federal income tax on the ordinary income above your other income.",
    )
with tax_col2:
    st.metric(
        "Marginal rate at top",
        f"{tax['marginal_rate'] * 100:.0f}%",
    )
with tax_col3:
    st.metric(
        "Total taxable income",
        f"${tax['total_taxable_income']:,.0f}",
    )

st.caption(
    "⚠️ **Simplified estimate.** Excludes state + local tax, FICA + Medicare (ESPP "
    "ordinary income IS subject to FICA unlike ISO), NIIT, and AMT considerations. "
    "Uses 2025 federal brackets. For planning only — consult a tax professional."
)

# ---------------------------------------------------------------------------
# References
# ---------------------------------------------------------------------------

st.divider()
with st.expander("📚 Statutory + regulatory references"):
    st.markdown(
        """
- **IRC §423(a)** — General rule deferring tax at qualified ESPP purchase
- **IRC §423(b)** — Requirements for a qualified §423 plan
- **IRC §423(b)(6)** — Discount limit (option price ≥ 85% of FMV; max 15% discount)
- **IRC §423(b)(8)** — $25,000 annual limit (measured at offering-date FMV)
- **IRC §423(c)** — QD ordinary income lesser-of formula
- **IRC §421(a)** — Nonrecognition of income at purchase
- **IRC §83(a)** — General compensation income recognition rule
- **IRC §6039** — Employer reporting (Form 3922)
- **Treas. Reg. §1.423-2** — §423 plan requirements + operation
- **Form 3922** — Information return for §423 ESPP purchases (Boxes 4, 5, 7, 8)
"""
    )
