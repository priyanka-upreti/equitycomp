"""ISO Exercise Calculations.

Implements tax math for Incentive Stock Option (ISO) exercises under IRC §422
and AMT preference under IRC §56(b)(3).

Key concepts:
- ISO exercise generates NO regular tax (§421(a)) but full spread is an AMT preference (§56(b)(3))
- Dual basis: regular tax basis = strike; AMT basis = strike + spread
- Qualifying Disposition (QD): hold > 1 yr post-exercise AND > 2 yrs post-grant
  → spread + appreciation = LTCG
- Disqualifying Disposition (DD): violates either holding period
  → spread at exercise = ordinary income (on W-2; NO FICA per §3121(a)(22))
  → appreciation past FMV at exercise = capital gain (ST or LT depending on holding)

All amounts are in USD. Dates use datetime.date.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal


# ---------------------------------------------------------------------------
# Input + output containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ISOExerciseInputs:
    """Inputs for a single ISO exercise + planned sale scenario."""

    shares: int  # number of shares exercised
    strike: float  # per-share strike price
    fmv_at_exercise: float  # per-share FMV at exercise
    grant_date: date  # original ISO grant date (for 2-year rule)
    exercise_date: date  # date of exercise (for 1-year rule)
    sale_date: date  # planned or actual sale date
    sale_price: float  # per-share sale price


@dataclass(frozen=True)
class ISOExerciseOutputs:
    """Tax + classification outputs for the exercise + sale scenario."""

    # At exercise
    spread_per_share: float
    total_spread: float  # AMT preference amount
    regular_tax_basis_per_share: float  # = strike (no regular income recognized)
    amt_basis_per_share: float  # = strike + spread

    # Holding period analysis
    days_from_exercise_to_sale: int
    days_from_grant_to_sale: int
    holds_one_year_post_exercise: bool  # > 1 year requirement
    holds_two_years_post_grant: bool  # > 2 years requirement
    disposition: Literal["QD", "DD"]
    qd_reason_failed: list[str]  # empty if QD; explanation if DD

    # At sale — QD outcome
    qd_total_gain: float  # (sale_price - strike) × shares
    qd_long_term_capital_gain: float  # = qd_total_gain (all LTCG for QD)

    # At sale — DD outcome (if DD)
    dd_ordinary_income: float  # min(spread, gain) per share × shares
    dd_capital_gain: float  # sale_price - fmv_at_exercise, if positive
    dd_capital_loss: float  # if sale_price < strike: capital loss
    dd_capital_gain_is_long_term: bool  # held > 1 yr from exercise


# ---------------------------------------------------------------------------
# Core calculations
# ---------------------------------------------------------------------------


def calculate_iso_exercise(inputs: ISOExerciseInputs) -> ISOExerciseOutputs:
    """Calculate ISO exercise outcomes including QD vs DD analysis."""

    # --- At exercise ---
    spread_per_share = max(0.0, inputs.fmv_at_exercise - inputs.strike)
    total_spread = spread_per_share * inputs.shares
    regular_basis = inputs.strike
    amt_basis = inputs.strike + spread_per_share

    # --- Holding period analysis ---
    days_to_sale_from_exercise = (inputs.sale_date - inputs.exercise_date).days
    days_to_sale_from_grant = (inputs.sale_date - inputs.grant_date).days
    # IRC §422(a)(1): "no disposition of such share within 2 years after grant nor 1 year after transfer"
    # Per Treas. Reg. §1.422-1(a): "more than 1 year" + "more than 2 years"
    holds_one_year = days_to_sale_from_exercise > 365
    holds_two_years = days_to_sale_from_grant > 730

    if holds_one_year and holds_two_years:
        disposition: Literal["QD", "DD"] = "QD"
        reasons_failed: list[str] = []
    else:
        disposition = "DD"
        reasons_failed = []
        if not holds_one_year:
            reasons_failed.append(
                f"Sold {days_to_sale_from_exercise} days post-exercise (need > 365)."
            )
        if not holds_two_years:
            reasons_failed.append(
                f"Sold {days_to_sale_from_grant} days post-grant (need > 730)."
            )

    # --- QD outcome (all LTCG on total appreciation) ---
    qd_total_gain = (inputs.sale_price - inputs.strike) * inputs.shares
    qd_long_term_capital_gain = qd_total_gain  # entire gain is LTCG at QD

    # --- DD outcome ---
    # Per §422(c)(2): ordinary income at DD = lesser of (FMV at exercise - strike)
    # or (sale price - strike). If sale < strike: ordinary income is $0.
    if inputs.sale_price <= inputs.strike:
        dd_ordinary_per_share = 0.0
    else:
        dd_ordinary_per_share = min(
            inputs.fmv_at_exercise - inputs.strike,
            inputs.sale_price - inputs.strike,
        )
    dd_ordinary_income = max(0.0, dd_ordinary_per_share * inputs.shares)

    # Capital gain/loss on appreciation past FMV at exercise
    dd_remaining_gain_per_share = (
        inputs.sale_price - inputs.fmv_at_exercise - 0  # any gain above FMV at exercise
    )
    if dd_remaining_gain_per_share > 0:
        dd_capital_gain = dd_remaining_gain_per_share * inputs.shares
        dd_capital_loss = 0.0
    elif inputs.sale_price < inputs.strike:
        # Sold for less than strike: capital loss on the difference
        dd_capital_gain = 0.0
        dd_capital_loss = (inputs.strike - inputs.sale_price) * inputs.shares
    else:
        # Sold between strike + FMV at exercise: no separate capital gain/loss
        # (ordinary income absorbs the gain above strike)
        dd_capital_gain = 0.0
        dd_capital_loss = 0.0

    dd_long_term = holds_one_year  # if held > 1 yr from exercise, capital gain is LTCG

    return ISOExerciseOutputs(
        spread_per_share=spread_per_share,
        total_spread=total_spread,
        regular_tax_basis_per_share=regular_basis,
        amt_basis_per_share=amt_basis,
        days_from_exercise_to_sale=days_to_sale_from_exercise,
        days_from_grant_to_sale=days_to_sale_from_grant,
        holds_one_year_post_exercise=holds_one_year,
        holds_two_years_post_grant=holds_two_years,
        disposition=disposition,
        qd_reason_failed=reasons_failed,
        qd_total_gain=qd_total_gain,
        qd_long_term_capital_gain=qd_long_term_capital_gain,
        dd_ordinary_income=dd_ordinary_income,
        dd_capital_gain=dd_capital_gain,
        dd_capital_loss=dd_capital_loss,
        dd_capital_gain_is_long_term=dd_long_term,
    )


def estimate_amt_due(
    total_spread: float,
    other_taxable_income: float = 0.0,
    filing_status: Literal["single", "mfj"] = "single",
    regular_tax_estimate: float = 0.0,
) -> dict:
    """Rough estimate of AMT due from an ISO exercise.

    SIMPLIFIED: real AMT requires Form 6251 with many adjustments + preference items.
    This function shows the magnitude using 2026 thresholds under the One Big
    Beautiful Bill Act (OB3), Pub. L. No. 119-21 § 70107 (enacted July 4, 2025).

    OB3 materially changed AMT for 2026 tax year:
      - Exemption Single: $90,100 (was $88,100 in 2025)
      - Exemption MFJ: $140,800 (was $137,000 in 2025)*
      - Phaseout begins Single: $500,000 (was $626,350 — LOWERED)
      - Phaseout begins MFJ: $1,000,000 (was $1,252,700 — LOWERED)
      - Phaseout RATE: 50% (was 25% — DOUBLED). Every $1 of AMTI over threshold
        eliminates $0.50 of exemption instead of $0.25.
      - Real effective AMT rate on income between phaseout endpoints: ~42%.

    *MFJ exemption source disagreement: Consider Your Options 11th ed says $140,800;
    Selected Issues 22nd ed says $140,200. Using $140,800; verify against IRS Form
    6251 (2026) instructions before high-stakes decisions.

    AMT rates:
      - 26% on first $244,500 of AMTI above exemption (2026, unchanged breakpoint)
      - 28% above

    Returns dict with: amti, exemption, taxable_amti, tentative_amt, regular_tax, amt_due
    """
    # 2026 figures under OB3 (Pub. L. No. 119-21 § 70107)
    if filing_status == "single":
        exemption_base = 90_100
        phaseout_start = 500_000
        # phaseout_end = 500,000 + (90,100 / 0.50) = 680,200
        phaseout_end = 680_200
    else:  # mfj
        exemption_base = 140_800
        phaseout_start = 1_000_000
        # phaseout_end = 1,000,000 + (140,800 / 0.50) = 1,281,600
        phaseout_end = 1_281_600

    amt_bracket_break = 244_500  # 2026

    # AMTI = ordinary income + ISO spread preference (simplified)
    amti = other_taxable_income + total_spread

    # Exemption phaseout: $0.50 lost per $1 over phaseout_start (OB3 doubled from 25% → 50%)
    if amti <= phaseout_start:
        exemption = exemption_base
    elif amti >= phaseout_end:
        exemption = 0.0
    else:
        reduction = (amti - phaseout_start) * 0.50
        exemption = max(0.0, exemption_base - reduction)

    taxable_amti = max(0.0, amti - exemption)

    # Tentative AMT: 26% on first bracket, 28% on remainder
    if taxable_amti <= amt_bracket_break:
        tentative_amt = taxable_amti * 0.26
    else:
        tentative_amt = (
            amt_bracket_break * 0.26 + (taxable_amti - amt_bracket_break) * 0.28
        )

    # AMT due = tentative AMT - regular tax (if positive)
    amt_due = max(0.0, tentative_amt - regular_tax_estimate)

    return {
        "amti": amti,
        "exemption": exemption,
        "taxable_amti": taxable_amti,
        "tentative_amt": tentative_amt,
        "regular_tax": regular_tax_estimate,
        "amt_due": amt_due,
    }
