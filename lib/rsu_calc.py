"""RSU Vest + Sell-to-Cover Calculations.

Models a single RSU vest event with:
- Full withholding breakdown: federal supplemental, state, Social Security
  (with wage-base cap), Medicare, Additional Medicare (over threshold)
- Sell-to-cover mechanics: shares to sell = ceil(total_withholding / FMV)
- Cost basis tracking on retained shares (= FMV_at_vest)
- Optional capital gain/loss analysis at future sale (LTCG vs STCG)
- Under-withholding warning when supplemental rate < marginal rate

Public-company RSUs (single-trigger) are fully modeled here. Private-company
double-trigger RSUs are flagged with a warning that the vest event ≠ tax event
until the liquidity trigger fires.

Key IRS mechanics (2026 tax year):
- Federal supplemental wage rate: 22% up to $1M YTD supplemental, 37% above
  (§3402(g), Treas. Reg. §31.3402(g)-1)
- Social Security wage base 2026: $176,100 (SSA published)
- Medicare: 1.45% (all wages)
- Additional Medicare: 0.9% over $200K single / $250K MFJ

All amounts in USD. Dates use datetime.date.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Literal, Optional


# 2026 IRS constants (verify against IRS Publication 15 before high-stakes use)
SOCIAL_SECURITY_WAGE_BASE_2026 = 176_100.0
FEDERAL_SUPPLEMENTAL_TIER1_RATE = 0.22
FEDERAL_SUPPLEMENTAL_TIER2_RATE = 0.37
FEDERAL_SUPPLEMENTAL_THRESHOLD = 1_000_000.0
ADDITIONAL_MEDICARE_THRESHOLD_SINGLE = 200_000.0
ADDITIONAL_MEDICARE_THRESHOLD_MFJ = 250_000.0


# ---------------------------------------------------------------------------
# Input + output containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RSUVestInputs:
    """Inputs for a single RSU vest event with sell-to-cover."""

    shares_vested: int
    fmv_at_vest_per_share: float
    vest_date: date

    # Withholding rate overrides / defaults
    state_supplemental_rate: float  # e.g., 0.10 for 10% (default varies by state)
    social_security_rate: float  # 0.062 (employee share)
    medicare_rate: float  # 0.0145
    additional_medicare_rate: float  # 0.009

    # YTD tracking for cap + threshold logic
    ytd_supplemental_wages: float  # for federal $1M threshold split
    ytd_social_security_wages: float  # for SS wage base cap
    ytd_total_wages: float  # for Additional Medicare threshold check
    social_security_wage_base: float  # 2026: $176,100
    filing_status: Literal["single", "mfj"]

    # Plan structure
    is_private_double_trigger: bool  # informational — triggers warning

    # For under-withholding analysis
    marginal_ordinary_rate: float  # user's actual bracket (e.g., 0.32)

    # Optional future sale
    sale_date: Optional[date]
    sale_price_per_share: Optional[float]


@dataclass(frozen=True)
class RSUVestOutputs:
    """Comprehensive outputs for RSU vest + sell-to-cover analysis."""

    # At vest
    ordinary_income: float

    # Federal supplemental withholding (auto-computed based on YTD)
    federal_supplemental_wh: float
    federal_effective_rate: float  # blended if crossed $1M threshold
    federal_crossed_1m_threshold: bool

    # State withholding
    state_wh: float

    # Social Security
    social_security_taxable_wages: float  # capped at remaining wage base room
    social_security_wh: float
    ss_wage_base_capped: bool  # this vest hit the cap

    # Medicare (no cap)
    medicare_wh: float

    # Additional Medicare
    additional_medicare_taxable_wages: float
    additional_medicare_wh: float
    additional_medicare_threshold_used: float  # $200K or $250K

    # Totals
    total_withholding: float
    effective_wh_rate: float  # total_wh / ordinary_income

    # Under-withholding warning
    underwithheld_amount: float  # positive → under-withheld (owes at year-end)
    is_underwithheld: bool  # True if marginal rate > effective wh rate

    # Sell-to-cover
    shares_sold_to_cover: int  # ceil(total_wh / FMV)
    net_shares_retained: int
    cash_from_stc: float  # shares_sold × FMV
    cash_overage: float  # cash_from_stc − total_wh (typically small, refunded)

    # Cost basis
    cost_basis_per_share: float  # = FMV_at_vest
    total_cost_basis_of_retained_shares: float

    # Optional sale outcome
    days_from_vest_to_sale: Optional[int]
    is_ltcg_at_sale: Optional[bool]
    capital_gain_or_loss: Optional[float]


# ---------------------------------------------------------------------------
# Core calculation
# ---------------------------------------------------------------------------


def calculate_rsu_vest(inputs: RSUVestInputs) -> RSUVestOutputs:
    """Calculate RSU vest event with full withholding + sell-to-cover mechanics."""

    ordinary_income = inputs.shares_vested * inputs.fmv_at_vest_per_share

    # --- Federal supplemental withholding (§3402(g)) ---
    # Rate: 22% up to $1M YTD supplemental, 37% above
    ytd_before = inputs.ytd_supplemental_wages
    ytd_after = ytd_before + ordinary_income
    threshold = FEDERAL_SUPPLEMENTAL_THRESHOLD

    if ytd_after <= threshold:
        federal_wh = ordinary_income * FEDERAL_SUPPLEMENTAL_TIER1_RATE
        federal_effective_rate = FEDERAL_SUPPLEMENTAL_TIER1_RATE
        federal_crossed_1m = False
    elif ytd_before >= threshold:
        federal_wh = ordinary_income * FEDERAL_SUPPLEMENTAL_TIER2_RATE
        federal_effective_rate = FEDERAL_SUPPLEMENTAL_TIER2_RATE
        federal_crossed_1m = True
    else:
        # Split: portion up to $1M at 22%, portion above at 37%
        under_1m = threshold - ytd_before
        over_1m = ordinary_income - under_1m
        federal_wh = (
            under_1m * FEDERAL_SUPPLEMENTAL_TIER1_RATE
            + over_1m * FEDERAL_SUPPLEMENTAL_TIER2_RATE
        )
        federal_effective_rate = federal_wh / ordinary_income if ordinary_income > 0 else 0.0
        federal_crossed_1m = True

    # --- State withholding (flat rate) ---
    state_wh = ordinary_income * inputs.state_supplemental_rate

    # --- Social Security (capped at wage base) ---
    remaining_ss_room = max(
        0.0, inputs.social_security_wage_base - inputs.ytd_social_security_wages
    )
    ss_taxable = min(ordinary_income, remaining_ss_room)
    social_security_wh = ss_taxable * inputs.social_security_rate
    ss_capped = ss_taxable < ordinary_income

    # --- Medicare (no cap) ---
    medicare_wh = ordinary_income * inputs.medicare_rate

    # --- Additional Medicare (over threshold based on filing status) ---
    add_med_threshold = (
        ADDITIONAL_MEDICARE_THRESHOLD_SINGLE
        if inputs.filing_status == "single"
        else ADDITIONAL_MEDICARE_THRESHOLD_MFJ
    )
    ytd_total_before = inputs.ytd_total_wages
    ytd_total_after = ytd_total_before + ordinary_income

    if ytd_total_after <= add_med_threshold:
        additional_medicare_taxable = 0.0
    elif ytd_total_before >= add_med_threshold:
        additional_medicare_taxable = ordinary_income
    else:
        additional_medicare_taxable = ytd_total_after - add_med_threshold

    additional_medicare_wh = additional_medicare_taxable * inputs.additional_medicare_rate

    # --- Totals ---
    total_wh = (
        federal_wh + state_wh + social_security_wh + medicare_wh + additional_medicare_wh
    )
    effective_wh_rate = total_wh / ordinary_income if ordinary_income > 0 else 0.0

    # --- Under-withholding analysis ---
    # Compare user's marginal ordinary rate to the effective federal rate applied
    # (state + FICA are separate from marginal rate comparison)
    marginal_estimated_tax = ordinary_income * inputs.marginal_ordinary_rate
    federal_actual_wh = federal_wh
    underwithheld = marginal_estimated_tax - federal_actual_wh
    is_underwithheld = underwithheld > 0

    # --- Sell-to-cover ---
    if inputs.fmv_at_vest_per_share > 0:
        shares_sold = math.ceil(total_wh / inputs.fmv_at_vest_per_share)
    else:
        shares_sold = 0
    shares_sold = min(shares_sold, inputs.shares_vested)  # can't sell more than vested
    net_shares = inputs.shares_vested - shares_sold
    cash_from_stc = shares_sold * inputs.fmv_at_vest_per_share
    cash_overage = max(0.0, cash_from_stc - total_wh)

    # --- Cost basis ---
    cost_basis_per_share = inputs.fmv_at_vest_per_share
    total_basis = net_shares * cost_basis_per_share

    # --- Optional future sale ---
    days_to_sale: Optional[int] = None
    is_ltcg: Optional[bool] = None
    cap_gain_loss: Optional[float] = None

    if inputs.sale_date is not None and inputs.sale_price_per_share is not None:
        days_to_sale = (inputs.sale_date - inputs.vest_date).days
        is_ltcg = days_to_sale > 365
        cap_gain_loss = (
            inputs.sale_price_per_share - inputs.fmv_at_vest_per_share
        ) * net_shares

    return RSUVestOutputs(
        ordinary_income=ordinary_income,
        federal_supplemental_wh=federal_wh,
        federal_effective_rate=federal_effective_rate,
        federal_crossed_1m_threshold=federal_crossed_1m,
        state_wh=state_wh,
        social_security_taxable_wages=ss_taxable,
        social_security_wh=social_security_wh,
        ss_wage_base_capped=ss_capped,
        medicare_wh=medicare_wh,
        additional_medicare_taxable_wages=additional_medicare_taxable,
        additional_medicare_wh=additional_medicare_wh,
        additional_medicare_threshold_used=add_med_threshold,
        total_withholding=total_wh,
        effective_wh_rate=effective_wh_rate,
        underwithheld_amount=underwithheld,
        is_underwithheld=is_underwithheld,
        shares_sold_to_cover=shares_sold,
        net_shares_retained=net_shares,
        cash_from_stc=cash_from_stc,
        cash_overage=cash_overage,
        cost_basis_per_share=cost_basis_per_share,
        total_cost_basis_of_retained_shares=total_basis,
        days_from_vest_to_sale=days_to_sale,
        is_ltcg_at_sale=is_ltcg,
        capital_gain_or_loss=cap_gain_loss,
    )
