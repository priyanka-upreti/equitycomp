"""§83(b) Election Decision Tool.

Compares expected tax outcomes with vs without filing an IRC §83(b) election
on restricted stock (or early-exercised options subject to substantial risk of
forfeiture), weighted by the employee's own estimate of forfeiture probability.

Key mechanics:
- §83(a) default: no tax at grant (forfeitable); at vest, ordinary income =
  (FMV_at_vest − price_paid) × shares; capital gain clock starts at VEST.
- §83(b) election (filed within 30 days of transfer via IRS Form 15620):
  pay ordinary tax NOW on (FMV_at_grant − price_paid) × shares even though
  forfeitable; capital gain clock starts at GRANT.
- If forfeited under §83(b): tax paid at grant is a permanent loss (no refund).

Only applies to actual PROPERTY transfers per Treas. Reg. §1.83-3(e):
- ✅ Restricted Stock Awards (RSAs)
- ✅ Early-exercised ISO or NSO (share issued subject to vesting)
- ❌ Restricted Stock Units (RSUs) — unfunded promise, NOT property under §83

All amounts in USD. Dates use datetime.date.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal, Optional


# ---------------------------------------------------------------------------
# Input + output containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Section83bInputs:
    """Inputs for the §83(b) decision comparison."""

    # Grant details
    grant_type: Literal["RSA", "ISO_EARLY_EX", "NSO_EARLY_EX"]
    grant_date: date
    shares: int
    price_paid_per_share: float  # 0 for typical founder RSAs
    fmv_at_grant_per_share: float

    # Vesting (V1 simplification: all shares vest together at end of period)
    vesting_years: float  # e.g., 4.0

    # Projected values
    projected_fmv_at_vest_per_share: float
    projected_sale_price_per_share: float
    sale_date: date

    # Employee's forfeiture estimate + tax rates
    forfeiture_probability: float  # 0.0 to 1.0
    marginal_ordinary_rate: float  # e.g., 0.32 for 32%
    ltcg_rate: float  # e.g., 0.15 for 15%


@dataclass(frozen=True)
class Section83bOutputs:
    """Comparison outputs for §83(b) vs no-election scenarios."""

    # Vest computation
    vest_date: date
    election_deadline: date  # 30 days after grant date
    days_grant_to_sale: int
    days_vest_to_sale: int

    # Scenario A: File §83(b)
    a_income_at_grant: float
    a_tax_at_grant: float
    a_capital_gain_at_sale: float
    a_is_ltcg: bool  # held > 1 yr from grant?
    a_tax_at_sale: float
    a_total_tax_if_vested: float
    a_total_tax_if_forfeited: float  # tax_at_grant — lost, no refund
    a_expected_tax: float  # probability-weighted

    # Scenario B: No §83(b) (default §83(a))
    b_income_at_vest: float
    b_tax_at_vest: float
    b_capital_gain_at_sale: float
    b_is_ltcg: bool  # held > 1 yr from vest?
    b_tax_at_sale: float
    b_total_tax_if_vested: float
    b_total_tax_if_forfeited: float  # 0
    b_expected_tax: float

    # Comparison
    expected_savings_from_83b: float  # positive → §83(b) saves money
    is_83b_favorable_at_zero_forfeit: bool
    breakeven_forfeit_probability: Optional[float]  # None if §83(b) is always/never favorable


# ---------------------------------------------------------------------------
# Core calculation
# ---------------------------------------------------------------------------


def calculate_section83b_scenarios(inputs: Section83bInputs) -> Section83bOutputs:
    """Compare filing §83(b) vs default §83(a) treatment on restricted stock."""

    vest_date = inputs.grant_date + timedelta(days=int(inputs.vesting_years * 365))
    election_deadline = inputs.grant_date + timedelta(days=30)

    days_grant_to_sale = (inputs.sale_date - inputs.grant_date).days
    days_vest_to_sale = (inputs.sale_date - vest_date).days

    # --- Scenario A: File §83(b) ---
    # At grant/transfer: ordinary income on the spread
    a_income_at_grant = max(
        0.0,
        (inputs.fmv_at_grant_per_share - inputs.price_paid_per_share) * inputs.shares,
    )
    a_tax_at_grant = a_income_at_grant * inputs.marginal_ordinary_rate

    # At sale (if not forfeited): capital gain from FMV at grant
    a_capital_gain_at_sale = max(
        0.0,
        (inputs.projected_sale_price_per_share - inputs.fmv_at_grant_per_share)
        * inputs.shares,
    )
    # LTCG clock started at grant per §83(b) — must hold > 1 year from grant
    a_is_ltcg = days_grant_to_sale > 365
    a_cap_gain_rate = inputs.ltcg_rate if a_is_ltcg else inputs.marginal_ordinary_rate
    a_tax_at_sale = a_capital_gain_at_sale * a_cap_gain_rate

    a_total_tax_if_vested = a_tax_at_grant + a_tax_at_sale
    a_total_tax_if_forfeited = a_tax_at_grant  # paid but no benefit

    # Expected tax under §83(b) = weighted average
    p_forfeit = inputs.forfeiture_probability
    p_not_forfeit = 1.0 - p_forfeit
    a_expected_tax = (
        p_not_forfeit * a_total_tax_if_vested + p_forfeit * a_total_tax_if_forfeited
    )

    # --- Scenario B: No §83(b) (default §83(a)) ---
    # At grant: no tax
    # At vest (if not forfeited): ordinary income on the spread at vest
    b_income_at_vest = max(
        0.0,
        (inputs.projected_fmv_at_vest_per_share - inputs.price_paid_per_share)
        * inputs.shares,
    )
    b_tax_at_vest = b_income_at_vest * inputs.marginal_ordinary_rate

    # At sale: capital gain from FMV at vest
    b_capital_gain_at_sale = max(
        0.0,
        (inputs.projected_sale_price_per_share - inputs.projected_fmv_at_vest_per_share)
        * inputs.shares,
    )
    # LTCG clock starts at vest — must hold > 1 year from vest
    b_is_ltcg = days_vest_to_sale > 365
    b_cap_gain_rate = inputs.ltcg_rate if b_is_ltcg else inputs.marginal_ordinary_rate
    b_tax_at_sale = b_capital_gain_at_sale * b_cap_gain_rate

    b_total_tax_if_vested = b_tax_at_vest + b_tax_at_sale
    b_total_tax_if_forfeited = 0.0  # nothing recognized

    b_expected_tax = (
        p_not_forfeit * b_total_tax_if_vested + p_forfeit * b_total_tax_if_forfeited
    )

    # --- Comparison ---
    expected_savings_from_83b = b_expected_tax - a_expected_tax  # + = §83(b) wins

    is_83b_favorable_at_zero_forfeit = a_total_tax_if_vested < b_total_tax_if_vested

    breakeven = _compute_breakeven_forfeit_probability(
        a_success=a_total_tax_if_vested,
        a_forfeit=a_total_tax_if_forfeited,
        b_success=b_total_tax_if_vested,
        b_forfeit=b_total_tax_if_forfeited,
    )

    return Section83bOutputs(
        vest_date=vest_date,
        election_deadline=election_deadline,
        days_grant_to_sale=days_grant_to_sale,
        days_vest_to_sale=days_vest_to_sale,
        a_income_at_grant=a_income_at_grant,
        a_tax_at_grant=a_tax_at_grant,
        a_capital_gain_at_sale=a_capital_gain_at_sale,
        a_is_ltcg=a_is_ltcg,
        a_tax_at_sale=a_tax_at_sale,
        a_total_tax_if_vested=a_total_tax_if_vested,
        a_total_tax_if_forfeited=a_total_tax_if_forfeited,
        a_expected_tax=a_expected_tax,
        b_income_at_vest=b_income_at_vest,
        b_tax_at_vest=b_tax_at_vest,
        b_capital_gain_at_sale=b_capital_gain_at_sale,
        b_is_ltcg=b_is_ltcg,
        b_tax_at_sale=b_tax_at_sale,
        b_total_tax_if_vested=b_total_tax_if_vested,
        b_total_tax_if_forfeited=b_total_tax_if_forfeited,
        b_expected_tax=b_expected_tax,
        expected_savings_from_83b=expected_savings_from_83b,
        is_83b_favorable_at_zero_forfeit=is_83b_favorable_at_zero_forfeit,
        breakeven_forfeit_probability=breakeven,
    )


def _compute_breakeven_forfeit_probability(
    a_success: float,
    a_forfeit: float,
    b_success: float,
    b_forfeit: float,
) -> Optional[float]:
    """Solve for the forfeit probability p ∈ [0, 1] where E[A] == E[B].

    E[A] = (1−p) × a_success + p × a_forfeit
    E[B] = (1−p) × b_success + p × b_forfeit

    Setting E[A] = E[B]:
    (1−p)(a_success − b_success) + p(a_forfeit − b_forfeit) = 0

    Solving for p:
    p = (b_success − a_success) / (a_forfeit − b_forfeit + b_success − a_success)

    Returns None if:
    - Denominator is 0 (§83(b) and no-election yield identical outcomes)
    - Breakeven falls outside [0, 1] (§83(b) is always/never favorable across
      the whole forfeit range)
    """
    denominator = (a_forfeit - b_forfeit) + (b_success - a_success)
    if abs(denominator) < 1e-9:
        return None

    p = (b_success - a_success) / denominator
    if 0.0 <= p <= 1.0:
        return p
    return None
