"""§83(b) Election Decision Tool — Streamlit page.

Compares expected tax outcomes with vs without filing an IRC §83(b) election,
weighted by the employee's own estimate of forfeiture probability. Handles the
30-day filing deadline and points to IRS Form 15620 (2024) for the filing.
"""

from datetime import date

import streamlit as st

# Make lib/ importable regardless of how streamlit launches
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.section83b_calc import (  # noqa: E402
    Section83bInputs,
    calculate_section83b_scenarios,
)


st.set_page_config(
    page_title="§83(b) Decision Tool",
    page_icon="✍️",
    layout="wide",
)

st.title("✍️ §83(b) Decision Tool")
st.markdown(
    "Should you file an **IRC §83(b) election** on your restricted stock? "
    "Compare expected tax outcomes with vs without the election, "
    "weighted by your forfeiture-risk estimate."
)

# ---------------------------------------------------------------------------
# Critical warning: §83(b) does NOT apply to RSUs
# ---------------------------------------------------------------------------

st.error(
    "🚨 **§83(b) does NOT apply to RSUs.** Per Treas. Reg. §1.83-3(e), an RSU is "
    "an unfunded, unsecured promise to pay — NOT property under §83. Filing an "
    "§83(b) on an RSU grant is **void from the moment of filing**. §83(b) only "
    "works for: (1) Restricted Stock Awards (RSAs), and (2) early-exercised "
    "ISOs / NSOs where the share is issued subject to vesting."
)

st.divider()

# ---------------------------------------------------------------------------
# Inputs in sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("📥 Grant Details")
    grant_type = st.radio(
        "Grant type",
        options=["RSA", "ISO_EARLY_EX", "NSO_EARLY_EX"],
        format_func=lambda x: {
            "RSA": "Restricted Stock Award (RSA)",
            "ISO_EARLY_EX": "Early-exercised ISO",
            "NSO_EARLY_EX": "Early-exercised NSO",
        }[x],
        help="§83(b) only applies to actual property transfers (not RSUs).",
    )
    grant_date = st.date_input(
        "Grant date (or early-exercise date)",
        value=date(2024, 1, 1),
        help="The 30-day §83(b) filing clock runs from this date.",
    )
    shares = st.number_input(
        "Shares granted",
        min_value=1,
        max_value=100_000_000,
        value=100_000,
        step=1_000,
    )
    price_paid = st.number_input(
        "Price paid per share ($)",
        min_value=0.00,
        value=0.0001,
        step=0.0001,
        format="%.4f",
        help="0 for typical founder RSAs; strike price for early-exercised options.",
    )
    fmv_at_grant = st.number_input(
        "FMV at grant per share ($)",
        min_value=0.00,
        value=0.0001,
        step=0.0001,
        format="%.4f",
    )

    st.divider()
    st.header("📅 Vesting")
    vesting_years = st.slider(
        "Vesting period (years)",
        min_value=0.25,
        max_value=6.0,
        value=4.0,
        step=0.25,
        help="V1 simplification: assumes all shares vest together at end of period.",
    )
    projected_fmv_at_vest = st.number_input(
        "Projected FMV at vest end ($/share)",
        min_value=0.01,
        value=10.00,
        step=0.01,
        format="%.2f",
    )

    st.divider()
    st.header("📤 Projected Sale")
    sale_date = st.date_input(
        "Sale date",
        value=date(2029, 6, 1),
        min_value=grant_date,
    )
    projected_sale_price = st.number_input(
        "Projected sale price ($/share)",
        min_value=0.01,
        value=50.00,
        step=0.01,
        format="%.2f",
    )

    st.divider()
    st.header("🎲 Forfeiture Risk")
    forfeit_pct_int = st.slider(
        "Forfeiture probability",
        min_value=0,
        max_value=100,
        value=10,
        step=5,
        format="%d%%",
        help="Your own estimate: probability you leave (or the deal fails) before vesting completes.",
    )
    forfeiture_probability = forfeit_pct_int / 100.0

    st.divider()
    st.header("💰 Tax Rates")
    marginal_ordinary_int = st.slider(
        "Marginal ordinary income rate",
        min_value=10,
        max_value=45,
        value=32,
        step=1,
        format="%d%%",
        help="Combined federal + state, at the top of your ordinary bracket.",
    )
    marginal_ordinary_rate = marginal_ordinary_int / 100.0

    ltcg_int = st.slider(
        "Long-term capital gains rate",
        min_value=0,
        max_value=35,
        value=20,
        step=1,
        format="%d%%",
        help="Combined federal + state LTCG rate. Federal LTCG is 0/15/20% by bracket.",
    )
    ltcg_rate = ltcg_int / 100.0

# ---------------------------------------------------------------------------
# Run calculations
# ---------------------------------------------------------------------------

inputs = Section83bInputs(
    grant_type=grant_type,
    grant_date=grant_date,
    shares=int(shares),
    price_paid_per_share=float(price_paid),
    fmv_at_grant_per_share=float(fmv_at_grant),
    vesting_years=float(vesting_years),
    projected_fmv_at_vest_per_share=float(projected_fmv_at_vest),
    projected_sale_price_per_share=float(projected_sale_price),
    sale_date=sale_date,
    forfeiture_probability=forfeiture_probability,
    marginal_ordinary_rate=marginal_ordinary_rate,
    ltcg_rate=ltcg_rate,
)
result = calculate_section83b_scenarios(inputs)

# ---------------------------------------------------------------------------
# 30-day deadline banner
# ---------------------------------------------------------------------------

today = date.today()
days_left_to_file = (result.election_deadline - today).days

if days_left_to_file < 0:
    st.warning(
        f"⏰ **Election deadline PASSED** on {result.election_deadline.isoformat()} "
        f"({-days_left_to_file} days ago). If you haven't filed within the 30-day window "
        f"from the grant/transfer date, the §83(b) election is no longer available for this grant."
    )
elif days_left_to_file <= 30:
    st.info(
        f"⏰ **{days_left_to_file} day(s) left to file §83(b)** — deadline: "
        f"**{result.election_deadline.isoformat()}**. File via **IRS Form 15620** "
        f"(paper or electronic): "
        f"[irs.gov/pub/irs-pdf/f15620.pdf](https://www.irs.gov/pub/irs-pdf/f15620.pdf)"
    )

st.divider()

# ---------------------------------------------------------------------------
# Recommendation summary
# ---------------------------------------------------------------------------

st.header("🎯 Recommendation")

rec_col1, rec_col2, rec_col3 = st.columns(3)
with rec_col1:
    if result.expected_savings_from_83b > 0:
        st.metric(
            "Expected savings from filing §83(b)",
            f"${result.expected_savings_from_83b:,.0f}",
            delta="Filing SAVES money",
            delta_color="normal",
        )
    else:
        st.metric(
            "Expected COST of filing §83(b)",
            f"${-result.expected_savings_from_83b:,.0f}",
            delta="Filing COSTS money",
            delta_color="inverse",
        )
with rec_col2:
    st.metric(
        "Your forfeit probability estimate",
        f"{forfeiture_probability * 100:.0f}%",
    )
with rec_col3:
    if result.breakeven_forfeit_probability is not None:
        st.metric(
            "Breakeven forfeit probability",
            f"{result.breakeven_forfeit_probability * 100:.1f}%",
            help="At this forfeit rate, filing §83(b) yields the same expected "
            "tax as not filing. Above this rate, don't file.",
        )
    else:
        if result.is_83b_favorable_at_zero_forfeit:
            st.success("§83(b) is favorable at any forfeit rate")
        else:
            st.error("§83(b) is unfavorable at any forfeit rate")

if result.expected_savings_from_83b > 0 and days_left_to_file >= 0:
    st.success(
        f"✅ **File §83(b)** — expected tax savings of "
        f"${result.expected_savings_from_83b:,.0f} outweighs the forfeiture risk. "
        f"Use IRS Form 15620."
    )
elif result.expected_savings_from_83b <= 0:
    st.warning(
        f"⚠️ **Don't file §83(b)** — expected cost of "
        f"${-result.expected_savings_from_83b:,.0f} exceeds the tax savings. "
        f"Either the appreciation isn't big enough, the forfeit risk is too high, "
        f"or the tax-rate spread is too small."
    )

# ---------------------------------------------------------------------------
# Side-by-side comparison
# ---------------------------------------------------------------------------

st.divider()
st.header("⚖️ Scenario Comparison")

scenario_col1, scenario_col2 = st.columns(2)

with scenario_col1:
    st.subheader("A) File §83(b)")
    st.markdown(
        f"""
**At grant ({grant_date.isoformat()}):**
- Ordinary income = `({fmv_at_grant:.4f} − {price_paid:.4f}) × {shares:,}`
- Ordinary income: **`${result.a_income_at_grant:,.2f}`**
- Tax at grant ({marginal_ordinary_rate * 100:.0f}%): **`${result.a_tax_at_grant:,.2f}`**

**At sale ({sale_date.isoformat()}):**
- Days from grant: `{result.days_grant_to_sale}` (need > 365 for LTCG)
- Treatment: **{'LTCG' if result.a_is_ltcg else 'STCG'}**
- Capital gain: **`${result.a_capital_gain_at_sale:,.2f}`**
- Tax at sale ({(ltcg_rate if result.a_is_ltcg else marginal_ordinary_rate) * 100:.0f}%): **`${result.a_tax_at_sale:,.2f}`**

**If vested + sold:** total tax = `${result.a_total_tax_if_vested:,.2f}`

**If FORFEITED:** total tax = `${result.a_total_tax_if_forfeited:,.2f}` (permanent loss — no refund)

**Expected tax:** `${result.a_expected_tax:,.2f}`
"""
    )

with scenario_col2:
    st.subheader("B) No §83(b) (default §83(a))")
    st.markdown(
        f"""
**At grant:** No tax (property still forfeitable)

**At vest ({result.vest_date.isoformat()}):**
- Ordinary income = `({projected_fmv_at_vest:.2f} − {price_paid:.4f}) × {shares:,}`
- Ordinary income: **`${result.b_income_at_vest:,.2f}`**
- Tax at vest ({marginal_ordinary_rate * 100:.0f}%): **`${result.b_tax_at_vest:,.2f}`**

**At sale ({sale_date.isoformat()}):**
- Days from vest: `{result.days_vest_to_sale}` (need > 365 for LTCG)
- Treatment: **{'LTCG' if result.b_is_ltcg else 'STCG'}**
- Capital gain: **`${result.b_capital_gain_at_sale:,.2f}`**
- Tax at sale ({(ltcg_rate if result.b_is_ltcg else marginal_ordinary_rate) * 100:.0f}%): **`${result.b_tax_at_sale:,.2f}`**

**If vested + sold:** total tax = `${result.b_total_tax_if_vested:,.2f}`

**If FORFEITED:** total tax = `${result.b_total_tax_if_forfeited:,.2f}` (no income recognized)

**Expected tax:** `${result.b_expected_tax:,.2f}`
"""
    )

# ---------------------------------------------------------------------------
# How to file (Form 15620)
# ---------------------------------------------------------------------------

st.divider()
st.header("📝 How to File — IRS Form 15620 (NEW 2024)")

st.markdown(
    """
**Before 2024:** No specific IRS form for §83(b). Taxpayer wrote own statement
using Rev. Proc. 2012-29 sample language.

**Since 2024:** File **IRS Form 15620** — a specific, official form for §83(b)
elections. Filing is easier and less error-prone.

**How to file:**
1. Complete Form 15620 within **30 days** of the property transfer (grant date for RSAs)
2. Either PAPER file (mail to IRS Service Center where you file your return) OR
   ELECTRONIC file (browser upload — no special software needed)
3. Attach a copy to your Form 1040 for the year of the grant
4. **Keep a copy forever** — the IRS does NOT acknowledge receipt of §83(b) elections
5. If married, also send a copy to your spouse

**Form 15620 fields:**
- Taxpayer's TIN
- Box 2: Property description (e.g., "1,000,000 shares of common stock of Acme Corp.")
- Box 5: Restrictions and conditions (e.g., "4-year vesting with 1-year cliff")
- Box 9: Company information

**Get the form:** [irs.gov/pub/irs-pdf/f15620.pdf](https://www.irs.gov/pub/irs-pdf/f15620.pdf)
"""
)

# ---------------------------------------------------------------------------
# References
# ---------------------------------------------------------------------------

st.divider()
with st.expander("📚 Statutory + regulatory references"):
    st.markdown(
        """
- **IRC §83(a)** — General rule: no tax until property is no longer subject to substantial risk of forfeiture (i.e., at vest)
- **IRC §83(b)** — Elective override: taxpayer may elect to be taxed at TRANSFER (grant), even though forfeitable
- **IRC §83(b)(2)** — Election must be filed within **30 days** of transfer (immutable — no extensions per Treas. Reg. §1.83-2(b))
- **Treas. Reg. §1.83-2** — Election procedure + required content
- **Treas. Reg. §1.83-3(e)** — Definition of "property" (excludes RSUs / unfunded promises)
- **Treas. Reg. §1.83-3(a)** — Definition of "transfer"
- **IRS Form 15620 (2024)** — Official §83(b) election form (replaces the "write your own statement" procedure)
- **Rev. Proc. 2012-29** — Pre-2024 sample §83(b) election language (superseded but still cited in older guidance)

### V1 model simplifications (documented for transparency)
- Assumes all shares vest together at end of vesting period (V2: tranche-by-tranche)
- Doesn't model capital loss if sale price < FMV at grant (V2: negative capital gain)
- Doesn't model AMT for early-exercised ISO + §83(b) — see ISO Modeler for AMT math
- Doesn't include state-specific tax nuances (New York, California, etc.)
- Uses single sale event (all shares sold on one date) — V2 can add partial sales
"""
    )
