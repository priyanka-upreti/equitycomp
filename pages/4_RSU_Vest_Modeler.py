"""RSU Vest + Sell-to-Cover Modeler — Streamlit page.

Interactive tool for modeling a single RSU vest event:
- Full withholding breakdown (federal supplemental, state, SS, Medicare, Additional Medicare)
- Sell-to-cover mechanics (shares sold to cover taxes)
- Cost basis tracking on retained shares
- Optional capital gain/loss at future sale (LTCG vs STCG)
- Under-withholding warning when marginal rate exceeds supplemental rate
"""

from datetime import date

import pandas as pd
import streamlit as st

# Make lib/ importable regardless of how streamlit launches
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.rsu_calc import (  # noqa: E402
    RSUVestInputs,
    SafeHarborInputs,
    calculate_rsu_vest,
    check_underpayment_safe_harbor,
    SOCIAL_SECURITY_WAGE_BASE_2026,
)


st.set_page_config(
    page_title="RSU Vest Modeler",
    page_icon="📅",
    layout="wide",
)

st.title("📅 RSU Vest + Sell-to-Cover Modeler")
st.markdown(
    "Model a single RSU vest event with full withholding breakdown "
    "(federal supplemental, state, FICA, Medicare) and **sell-to-cover** "
    "share mechanics. See net shares retained + cost basis."
)

st.divider()

# ---------------------------------------------------------------------------
# Inputs in sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("📥 Vest Event")
    shares_vested = st.number_input(
        "Shares vesting (this event)",
        min_value=1,
        max_value=1_000_000,
        value=1_000,
        step=100,
    )
    fmv_at_vest = st.number_input(
        "FMV at vest (per share, USD)",
        min_value=0.01,
        value=100.00,
        step=0.01,
        format="%.2f",
    )
    vest_date = st.date_input(
        "Vest date",
        value=date(2026, 6, 15),
    )
    is_private_double_trigger = st.checkbox(
        "Private-company RSU with double-trigger?",
        value=False,
        help="If checked, this vest is only a tax event when a liquidity event "
        "(IPO/M&A) also occurs. Until then, this is a 'service trigger' only.",
    )

    st.divider()
    st.header("💰 Withholding Rates")
    state_rate_int = st.slider(
        "State supplemental rate (%)",
        min_value=0,
        max_value=15,
        value=10,
        step=1,
        format="%d%%",
        help="Varies by state. Common: CA 10.23%, NY 11.7%, TX/FL/WA 0%.",
    )
    state_supplemental_rate = state_rate_int / 100.0

    # SS + Medicare rates (fixed, but visible)
    st.caption(
        f"**FICA:** Social Security 6.2% (capped at ${SOCIAL_SECURITY_WAGE_BASE_2026:,.0f} "
        f"wage base 2026) · Medicare 1.45% · Additional Medicare 0.9% over threshold"
    )

    st.divider()
    st.header("📊 YTD Wage Tracker")
    st.caption("For threshold + cap checks. Leave at 0 if this is the first income of the year.")
    ytd_supplemental = st.number_input(
        "YTD supplemental wages ($)",
        min_value=0,
        value=0,
        step=10_000,
        help="For federal $1M threshold. Above $1M YTD, further supplemental "
        "wages are withheld at 37% (not 22%).",
    )
    ytd_ss_wages = st.number_input(
        "YTD Social Security wages ($)",
        min_value=0,
        value=0,
        step=10_000,
        help=f"For SS wage base cap. 2026: ${SOCIAL_SECURITY_WAGE_BASE_2026:,.0f}",
    )
    ytd_total_wages = st.number_input(
        "YTD total wages ($)",
        min_value=0,
        value=0,
        step=10_000,
        help="For Additional Medicare threshold ($200K single / $250K MFJ).",
    )
    filing_status = st.radio(
        "Filing status",
        options=["single", "mfj"],
        format_func=lambda x: "Single" if x == "single" else "Married Filing Jointly",
        horizontal=True,
    )

    st.divider()
    st.header("🎯 Under-Withholding Check")
    marginal_int = st.slider(
        "Your marginal ordinary rate (%)",
        min_value=10,
        max_value=45,
        value=32,
        step=1,
        format="%d%%",
        help="Combined federal + state at the top of your ordinary bracket. "
        "If higher than the 22% federal supplemental rate, the vest will be "
        "under-withheld and you'll owe more at year-end.",
    )
    marginal_ordinary_rate = marginal_int / 100.0

    st.divider()
    st.header("📤 Optional: Future Sale")
    include_sale = st.checkbox("Model a future sale?", value=True)
    if include_sale:
        sale_date_val = st.date_input(
            "Sale date",
            value=date(2027, 7, 1),
            min_value=vest_date,
        )
        sale_price = st.number_input(
            "Sale price (per share, USD)",
            min_value=0.01,
            value=150.00,
            step=0.01,
            format="%.2f",
        )
    else:
        sale_date_val = None
        sale_price = None

# ---------------------------------------------------------------------------
# Run calculation
# ---------------------------------------------------------------------------

inputs = RSUVestInputs(
    shares_vested=int(shares_vested),
    fmv_at_vest_per_share=float(fmv_at_vest),
    vest_date=vest_date,
    state_supplemental_rate=state_supplemental_rate,
    social_security_rate=0.062,
    medicare_rate=0.0145,
    additional_medicare_rate=0.009,
    ytd_supplemental_wages=float(ytd_supplemental),
    ytd_social_security_wages=float(ytd_ss_wages),
    ytd_total_wages=float(ytd_total_wages),
    social_security_wage_base=SOCIAL_SECURITY_WAGE_BASE_2026,
    filing_status=filing_status,
    is_private_double_trigger=bool(is_private_double_trigger),
    marginal_ordinary_rate=marginal_ordinary_rate,
    sale_date=sale_date_val,
    sale_price_per_share=float(sale_price) if sale_price else None,
)
result = calculate_rsu_vest(inputs)

# ---------------------------------------------------------------------------
# Double-trigger warning
# ---------------------------------------------------------------------------

if is_private_double_trigger:
    st.warning(
        "⚠️ **Double-trigger RSU (private company):** The tax event isn't THIS vest date — "
        "it's the DATE OF LIQUIDITY EVENT (IPO / M&A / tender offer) after both triggers "
        "are met. Until the second trigger fires, no ordinary income is recognized and no "
        "withholding happens. When the liquidity event occurs, ALL previously-time-vested "
        "tranches settle at once — creating a large single-year tax event."
    )

# ---------------------------------------------------------------------------
# At Vest section
# ---------------------------------------------------------------------------

st.header("📊 At Vest")

top_col1, top_col2, top_col3, top_col4 = st.columns(4)
with top_col1:
    st.metric("Shares vested", f"{shares_vested:,}")
with top_col2:
    st.metric("FMV at vest", f"${fmv_at_vest:,.2f}")
with top_col3:
    st.metric("Ordinary income (W-2)", f"${result.ordinary_income:,.2f}")
with top_col4:
    st.metric("Total withholding", f"${result.total_withholding:,.2f}")

# ---------------------------------------------------------------------------
# Withholding breakdown
# ---------------------------------------------------------------------------

st.divider()
st.header("💸 Withholding Breakdown")

withholding_rows = [
    {
        "Category": "Federal supplemental",
        "Rate applied": f"{result.federal_effective_rate * 100:.2f}%",
        "Taxable base": f"${result.ordinary_income:,.2f}",
        "Withheld": f"${result.federal_supplemental_wh:,.2f}",
    },
    {
        "Category": "State supplemental",
        "Rate applied": f"{state_supplemental_rate * 100:.0f}%",
        "Taxable base": f"${result.ordinary_income:,.2f}",
        "Withheld": f"${result.state_wh:,.2f}",
    },
    {
        "Category": "Social Security (6.2%)",
        "Rate applied": "6.2%",
        "Taxable base": f"${result.social_security_taxable_wages:,.2f}",
        "Withheld": f"${result.social_security_wh:,.2f}",
    },
    {
        "Category": "Medicare (1.45%)",
        "Rate applied": "1.45%",
        "Taxable base": f"${result.ordinary_income:,.2f}",
        "Withheld": f"${result.medicare_wh:,.2f}",
    },
    {
        "Category": "Additional Medicare (0.9%)",
        "Rate applied": "0.9%",
        "Taxable base": f"${result.additional_medicare_taxable_wages:,.2f}",
        "Withheld": f"${result.additional_medicare_wh:,.2f}",
    },
    {
        "Category": "TOTAL",
        "Rate applied": f"{result.effective_wh_rate * 100:.2f}%",
        "Taxable base": "",
        "Withheld": f"${result.total_withholding:,.2f}",
    },
]
st.dataframe(pd.DataFrame(withholding_rows), use_container_width=True, hide_index=True)

# Flag threshold crossings
threshold_notes = []
if result.federal_crossed_1m_threshold:
    threshold_notes.append(
        f"🚨 **\\$1M federal threshold crossed** — YTD supplemental wages "
        f"(\\${ytd_supplemental:,} + this vest \\${result.ordinary_income:,.0f}) "
        f"exceed \\$1M. Portion above \\$1M withheld at 37%. Effective federal rate: "
        f"{result.federal_effective_rate * 100:.2f}%."
    )
if result.ss_wage_base_capped:
    threshold_notes.append(
        f"ℹ️ **Social Security wage base reached** — only "
        f"\\${result.social_security_taxable_wages:,.2f} of this vest subject to SS."
    )
if result.additional_medicare_taxable_wages > 0:
    threshold_notes.append(
        f"ℹ️ **Additional Medicare threshold crossed** — "
        f"\\${result.additional_medicare_taxable_wages:,.2f} subject to 0.9% surcharge "
        f"(over \\${result.additional_medicare_threshold_used:,.0f} for {filing_status.upper()})."
    )

for note in threshold_notes:
    st.info(note)

# ---------------------------------------------------------------------------
# Under-withholding warning
# ---------------------------------------------------------------------------

if result.is_underwithheld:
    st.warning(
        f"💰 **Cash owed at filing: about \\${result.underwithheld_amount:,.0f}** — Your marginal "
        f"rate ({marginal_ordinary_rate * 100:.0f}%) exceeds the federal supplemental "
        f"rate applied ({result.federal_effective_rate * 100:.2f}%), so this vest is "
        f"under-withheld. You'll write a check for the difference at filing. "
        f"**Whether you also owe a penalty** depends on §6654 safe harbor — check below."
    )

# ---------------------------------------------------------------------------
# §6654 Safe Harbor Analysis (optional)
# ---------------------------------------------------------------------------

st.divider()
st.header("🛡️ IRC §6654 Safe Harbor — Underpayment Penalty Check")

st.markdown(
    "**Two different things:**\n"
    "1. **Cash owed at filing** (above) — you'll always write a check if under-withheld\n"
    "2. **Underpayment penalty** (this section) — an IRS penalty ON TOP of the cash owed, "
    "only if you fail the safe harbor test\n\n"
    "**Safe harbor:** Total federal withholding this year must equal or exceed the "
    "**LESSER of** (a) 90% of THIS year's tax, or (b) **100% of LAST year's tax** — "
    "bumped to **110%** if last year's AGI exceeded \\$150,000."
)

sh_col1, sh_col2 = st.columns(2)
with sh_col1:
    prior_year_tax = st.number_input(
        "Prior year federal tax liability ($)",
        min_value=0,
        value=0,
        step=1_000,
        help="Total federal tax from last year's Form 1040 line 24. Enter 0 to skip analysis.",
    )
    prior_year_high_income = st.checkbox(
        "Prior year AGI over \\$150,000 (or \\$75K if MFS)?",
        value=False,
        help="If yes, safe harbor threshold is 110% of prior year tax instead of 100%.",
    )
with sh_col2:
    projected_ytd_federal_wh = st.number_input(
        "Projected TOTAL federal WH this year ($)",
        min_value=0,
        value=int(result.federal_supplemental_wh),
        step=1_000,
        help="All federal income tax withheld this year across ALL sources "
        "(paycheck W-2, RSU vests, estimated payments) — including this vest.",
    )
    projected_current_year_tax = st.number_input(
        "Projected current year federal tax ($, optional)",
        min_value=0,
        value=0,
        step=1_000,
        help="If known: enables the 90% prong of the safe harbor test. Leave at 0 to skip.",
    )

if prior_year_tax > 0:
    sh_result = check_underpayment_safe_harbor(
        SafeHarborInputs(
            prior_year_federal_tax=float(prior_year_tax),
            prior_year_agi_over_threshold=prior_year_high_income,
            projected_total_federal_wh_this_year=float(projected_ytd_federal_wh),
            projected_current_year_tax=(
                float(projected_current_year_tax) if projected_current_year_tax > 0 else None
            ),
        )
    )

    st.markdown("---")
    sh_metric_col1, sh_metric_col2, sh_metric_col3 = st.columns(3)
    with sh_metric_col1:
        st.metric(
            f"Prior year threshold ({sh_result.applicable_prior_year_rate * 100:.0f}%)",
            f"${sh_result.prior_year_threshold:,.0f}",
        )
    with sh_metric_col2:
        if sh_result.current_year_90pct_threshold is not None:
            st.metric(
                "Current year threshold (90%)",
                f"${sh_result.current_year_90pct_threshold:,.0f}",
            )
        else:
            st.metric("Current year threshold (90%)", "N/A")
    with sh_metric_col3:
        st.metric(
            "Applicable threshold (lesser)",
            f"${sh_result.applicable_threshold:,.0f}",
        )

    if sh_result.is_safe_harbor_met:
        if sh_result.is_de_minimis_exception:
            st.success(
                f"✅ **Safe harbor MET** — via de minimis exception (tax owed at filing "
                f"< \\$1,000). No underpayment penalty regardless of withholding."
            )
        else:
            st.success(
                f"✅ **Safe harbor MET** — projected withholding "
                f"(\\${projected_ytd_federal_wh:,.0f}) equals or exceeds the applicable "
                f"threshold (\\${sh_result.applicable_threshold:,.0f}). **No underpayment "
                f"penalty**, even though you'll owe cash at filing."
            )
    else:
        st.error(
            f"🚨 **Safe harbor NOT met** — projected withholding "
            f"(\\${projected_ytd_federal_wh:,.0f}) is **\\${sh_result.shortfall:,.0f} short** "
            f"of the applicable threshold (\\${sh_result.applicable_threshold:,.0f}). "
            f"You may owe an underpayment penalty on top of the cash due at filing. "
            f"Consider making an estimated payment via **Form 1040-ES** or increasing "
            f"W-4 withholding for the remainder of the year."
        )
else:
    st.caption(
        "💡 Enter your prior year federal tax liability above to run the safe harbor check."
    )

# ---------------------------------------------------------------------------
# Sell-to-cover mechanics
# ---------------------------------------------------------------------------

st.divider()
st.header("🎯 Sell-to-Cover Mechanics")

stc_col1, stc_col2, stc_col3, stc_col4 = st.columns(4)
with stc_col1:
    st.metric("Shares sold to cover", f"{result.shares_sold_to_cover:,}")
with stc_col2:
    st.metric("Net shares retained", f"{result.net_shares_retained:,}")
with stc_col3:
    st.metric("Cash from STC", f"${result.cash_from_stc:,.2f}")
with stc_col4:
    st.metric(
        "Cash overage",
        f"${result.cash_overage:,.2f}",
        help="Difference between STC proceeds and withholding. Typically refunded to employee.",
    )

st.caption(
    f"**Formula:** shares sold = ceil(total withholding ÷ FMV at vest) = "
    f"ceil(\\${result.total_withholding:,.2f} ÷ \\${fmv_at_vest:,.2f}) = "
    f"{result.shares_sold_to_cover:,} shares"
)

# ---------------------------------------------------------------------------
# Cost basis
# ---------------------------------------------------------------------------

st.divider()
st.header("📚 Cost Basis (Retained Shares)")

basis_col1, basis_col2, basis_col3 = st.columns(3)
with basis_col1:
    st.metric("Cost basis per share", f"${result.cost_basis_per_share:,.2f}")
with basis_col2:
    st.metric("Total cost basis", f"${result.total_cost_basis_of_retained_shares:,.2f}")
with basis_col3:
    st.metric("Net shares retained", f"{result.net_shares_retained:,}")

st.caption(
    "Cost basis of retained shares = FMV at vest. This becomes the reference point for "
    "capital gain/loss at future sale. **Broker 1099-B may report \\$0 basis** — you must "
    "adjust to prevent double-taxation."
)

# ---------------------------------------------------------------------------
# Optional sale outcome
# ---------------------------------------------------------------------------

if result.days_from_vest_to_sale is not None:
    st.divider()
    st.header("💵 At Sale (Projected)")

    sale_col1, sale_col2, sale_col3, sale_col4 = st.columns(4)
    with sale_col1:
        st.metric("Days held from vest", f"{result.days_from_vest_to_sale:,}")
    with sale_col2:
        if result.is_ltcg_at_sale:
            st.success("✅ LTCG (> 1 yr from vest)")
        else:
            st.error("❌ STCG (≤ 1 yr from vest)")
    with sale_col3:
        gain_label = "Capital gain" if (result.capital_gain_or_loss or 0) >= 0 else "Capital loss"
        st.metric(gain_label, f"${abs(result.capital_gain_or_loss or 0):,.2f}")
    with sale_col4:
        st.metric("Sale proceeds", f"${(sale_price or 0) * result.net_shares_retained:,.2f}")

    st.caption(
        f"**Formula:** (sale price − cost basis) × net shares retained = "
        f"(\\${sale_price:.2f} − \\${result.cost_basis_per_share:.2f}) × "
        f"{result.net_shares_retained:,} = \\${result.capital_gain_or_loss:,.2f}"
    )

# ---------------------------------------------------------------------------
# References
# ---------------------------------------------------------------------------

st.divider()
with st.expander("📚 Statutory + regulatory references"):
    st.markdown(
        f"""
- **IRC §61(a)** — Gross income includes compensation for services (RSU vest is compensation income)
- **IRC §83(a)** — Property transferred as compensation is taxed when substantial risk of forfeiture lapses (= vest)
- **IRC §83(b)** — **DOES NOT APPLY TO RSUs.** Only to actual property transfers (see §83(b) tool for details)
- **IRC §3402(g)** — Federal supplemental wage withholding rules
- **Treas. Reg. §31.3402(g)-1** — 22% rate up to $1M YTD supplemental; 37% above
- **IRC §3101** — FICA taxes (Social Security + Medicare)
- **IRC §3121(a)** — Social Security wage base (2026: ${SOCIAL_SECURITY_WAGE_BASE_2026:,.0f})
- **IRC §3101(b)(2)** — Additional Medicare tax (0.9% over $200K single / $250K MFJ)
- **§409A** — Deferred compensation rules (RSUs settling later than 2.5 months after year-of-vest can trigger)
- **IRC §6654** — Underpayment penalty for individuals + SAFE HARBOR rules
  - §6654(d)(1)(B)(i) — 90% of current year tax
  - §6654(d)(1)(B)(ii) — 100% of prior year tax (110% if prior year AGI > \\$150K per §6654(d)(1)(C))
  - §6654(e) — De minimis rule: no penalty if tax owed < \\$1,000
- **IRS Publication 15 (Circular E) 2026** — Employer's withholding tax guide
- **IRS Form 2210** — Underpayment of estimated tax by individuals
- **Form W-2** — Reports RSU ordinary income in Box 1 + withholding in Box 2

### V1 model simplifications (documented for transparency)
- Single vest event only (V2: multi-tranche schedule)
- Double-trigger cumulative tax stacking at IPO (V2: full multi-year unwind)
- Simplified state withholding as flat rate (V2: per-state lookup with local + supplemental variations)
- Assumes vest income doesn't push you into a higher marginal bracket (V2: bracket-jump analysis)
- §409A short-term deferral compliance assumed
- 2026 tax year figures (SS wage base $176,100, thresholds unchanged)
"""
    )
