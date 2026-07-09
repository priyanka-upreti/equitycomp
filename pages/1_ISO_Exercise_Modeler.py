"""ISO Exercise Modeler — Streamlit page.

Interactive tool for modeling Incentive Stock Option (ISO) exercises:
- AMT preference + dual basis at exercise
- Qualifying Disposition (QD) vs Disqualifying Disposition (DD) outcomes
- Side-by-side comparison of "Sell now (DD)" vs "Wait to QD"
"""

from datetime import date, timedelta

import streamlit as st

# Make lib/ importable regardless of how streamlit launches
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.iso_calc import (  # noqa: E402
    ISOExerciseInputs,
    calculate_iso_exercise,
    estimate_amt_due,
)


st.set_page_config(
    page_title="ISO Exercise Modeler",
    page_icon="🎯",
    layout="wide",
)

st.title("🎯 ISO Exercise Modeler")
st.markdown(
    "Model an **Incentive Stock Option** exercise — see AMT preference, dual basis, "
    "and the tax difference between **Qualifying** vs **Disqualifying** Disposition."
)

st.divider()

# ---------------------------------------------------------------------------
# Inputs in sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("📥 Grant + Exercise")
    shares = st.number_input(
        "Number of shares exercised",
        min_value=1,
        max_value=1_000_000,
        value=1_000,
        step=100,
    )
    strike = st.number_input(
        "Strike price (per share, USD)",
        min_value=0.01,
        value=10.00,
        step=0.01,
        format="%.2f",
    )
    fmv_at_exercise = st.number_input(
        "FMV at exercise (per share, USD)",
        min_value=0.01,
        value=50.00,
        step=0.01,
        format="%.2f",
    )
    grant_date = st.date_input(
        "ISO grant date",
        value=date(2022, 1, 1),
        max_value=date.today(),
    )
    exercise_date = st.date_input(
        "Exercise date",
        value=date(2024, 1, 1),
        min_value=grant_date,
    )

    st.divider()
    st.header("📤 Planned Sale")
    sale_date = st.date_input(
        "Sale date",
        value=date(2025, 2, 1),
        min_value=exercise_date,
    )
    sale_price = st.number_input(
        "Sale price (per share, USD)",
        min_value=0.01,
        value=80.00,
        step=0.01,
        format="%.2f",
    )

    st.divider()
    st.header("💰 AMT Estimate (optional)")
    other_income = st.number_input(
        "Other taxable income for the year (USD)",
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
    regular_tax_est = st.number_input(
        "Estimated regular federal tax (USD)",
        min_value=0,
        value=30_000,
        step=1_000,
        help="Your projected federal income tax before considering ISO/AMT. "
        "Used to estimate AMT additional liability.",
    )

# ---------------------------------------------------------------------------
# Run calculations
# ---------------------------------------------------------------------------

inputs = ISOExerciseInputs(
    shares=int(shares),
    strike=float(strike),
    fmv_at_exercise=float(fmv_at_exercise),
    grant_date=grant_date,
    exercise_date=exercise_date,
    sale_date=sale_date,
    sale_price=float(sale_price),
)
result = calculate_iso_exercise(inputs)

amt = estimate_amt_due(
    total_spread=result.total_spread,
    other_taxable_income=float(other_income),
    filing_status=filing_status,
    regular_tax_estimate=float(regular_tax_est),
)

# ---------------------------------------------------------------------------
# At-exercise summary
# ---------------------------------------------------------------------------

st.header("📊 At Exercise")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Spread per share", f"${result.spread_per_share:,.2f}")
with col2:
    st.metric("Total spread (AMT preference)", f"${result.total_spread:,.2f}")
with col3:
    st.metric("Regular tax basis / share", f"${result.regular_tax_basis_per_share:,.2f}")
with col4:
    st.metric("AMT basis / share", f"${result.amt_basis_per_share:,.2f}")

with st.expander("📖 Why are there two cost bases?"):
    st.markdown(
        """
**Dual basis** is one of the trickiest concepts in ISO taxation. At exercise:

- **Regular tax**: §421(a) defers all income — no regular tax is owed. Your regular-tax cost basis stays at the **strike price**.
- **AMT (per §56(b)(3))**: the spread (FMV at exercise − strike) is treated as an AMT preference item. For AMT purposes, your cost basis steps up to the **FMV at exercise** (strike + spread).

This matters at sale because AMT capital gain (sale − AMT basis) is **smaller** than regular tax capital gain (sale − regular basis). You may be able to claim an **AMT credit** (Form 8801) in later years to recover the AMT paid at exercise.
"""
    )

# ---------------------------------------------------------------------------
# AMT estimate
# ---------------------------------------------------------------------------

st.header("⚠️ Estimated AMT Impact (planning only)")

amt_cols = st.columns(4)
with amt_cols[0]:
    st.metric("AMTI", f"${amt['amti']:,.0f}")
with amt_cols[1]:
    st.metric("Exemption", f"${amt['exemption']:,.0f}")
with amt_cols[2]:
    st.metric("Tentative AMT", f"${amt['tentative_amt']:,.0f}")
with amt_cols[3]:
    delta_color = "inverse" if amt["amt_due"] > 0 else "off"
    st.metric(
        "Additional tax from AMT",
        f"${amt['amt_due']:,.0f}",
        delta=f"${amt['amt_due']:,.0f} above regular tax" if amt["amt_due"] > 0 else "no additional AMT",
        delta_color=delta_color,
    )

st.caption(
    "⚠️ **Simplified estimate.** Actual AMT requires Form 6251 with all preference items + adjustments. "
    "**2026 thresholds under OB3 (Pub. L. 119-21 § 70107, July 4, 2025)** — phaseout rate doubled to 50%, "
    "MFJ exemption $140,800 (verify against IRS Form 6251 2026 instructions). "
    "Consult a tax professional before exercising large ISO positions."
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
        st.caption("Both holding periods satisfied. Spread + appreciation = LTCG.")
    else:
        st.error(f"❌ **{result.disposition}** — Disqualifying Disposition")
        st.caption("Loses ISO QD benefit. Spread at exercise becomes ordinary income.")

with cls_col2:
    st.markdown(
        f"""
**Days post-exercise:** {result.days_from_exercise_to_sale} (need > 365 for §422 QD)
{"✅" if result.holds_one_year_post_exercise else "❌"} 1-year-post-exercise rule

**Days post-grant:** {result.days_from_grant_to_sale} (need > 730 for §422 QD)
{"✅" if result.holds_two_years_post_grant else "❌"} 2-year-post-grant rule
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
**Total gain:** `${result.qd_total_gain:,.2f}`

**Treatment:** Long-Term Capital Gain (LTCG)
**Tax rate:** 0% / 15% / 20% (vs ordinary rates)

`(Sale price − Strike) × Shares`
`= (${sale_price:.2f} − ${strike:.2f}) × {shares:,}`
`= ${result.qd_total_gain:,.2f}`
"""
    )

with scenario_col2:
    st.subheader("If DD")
    st.markdown(
        f"""
**Ordinary income:** `${result.dd_ordinary_income:,.2f}` (W-2; **no FICA** per §3121(a)(22))

**Capital gain:** `${result.dd_capital_gain:,.2f}` ({'LTCG' if result.dd_capital_gain_is_long_term else 'STCG'})

**Capital loss:** `${result.dd_capital_loss:,.2f}` (if sale below strike)

Ordinary income = lesser of spread at exercise or (sale − strike) × shares
Capital gain = (sale − FMV at exercise) × shares
"""
    )

# Total tax estimate comparison (informational)
if result.disposition == "QD":
    st.info(
        f"🎯 **Your current scenario is QD** — you keep the LTCG benefit on the full "
        f"${result.qd_total_gain:,.2f} gain. The DD column above shows what you'd lose "
        "if you sold any earlier (before satisfying both holding periods)."
    )
else:
    st.warning(
        f"⚠️ **Your current scenario is DD** — the spread at exercise becomes ordinary income. "
        f"To convert to QD, you'd need to hold until at least "
        f"**{max(inputs.exercise_date + timedelta(days=366), inputs.grant_date + timedelta(days=731)):%B %d, %Y}**."
    )

# ---------------------------------------------------------------------------
# References
# ---------------------------------------------------------------------------

st.divider()
with st.expander("📚 Statutory + accounting references"):
    st.markdown(
        """
- **IRC §421(a)** — General rule deferring tax at ISO exercise
- **IRC §422** — ISO requirements (10-year max, FMV strike, etc.)
- **IRC §422(a)(1)** — Holding period rules for Qualifying Disposition
- **IRC §422(c)(2)** — Disqualifying Disposition ordinary income (lesser-of formula)
- **IRC §56(b)(3)** — Spread is AMT preference at exercise
- **IRC §3121(a)(22)** — No FICA on ISO spread (even on DD)
- **Form 6251** — Alternative Minimum Tax computation
- **Form 8801** — AMT credit carryforward (claim in later years)
- **Treas. Reg. §1.421-1, §1.422-1** — Regulations under §421/§422
"""
    )
