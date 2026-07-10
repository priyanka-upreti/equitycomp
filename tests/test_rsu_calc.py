"""Unit tests for RSU Vest + Sell-to-Cover calculations."""

from datetime import date

import pytest

from lib.rsu_calc import (
    RSUVestInputs,
    calculate_rsu_vest,
    SOCIAL_SECURITY_WAGE_BASE_2026,
)


def _default_inputs(**overrides) -> RSUVestInputs:
    """Helper: baseline inputs with overrides."""
    defaults = dict(
        shares_vested=1_000,
        fmv_at_vest_per_share=100.0,
        vest_date=date(2026, 6, 15),
        state_supplemental_rate=0.10,
        social_security_rate=0.062,
        medicare_rate=0.0145,
        additional_medicare_rate=0.009,
        ytd_supplemental_wages=0.0,
        ytd_social_security_wages=0.0,
        ytd_total_wages=0.0,
        social_security_wage_base=SOCIAL_SECURITY_WAGE_BASE_2026,
        filing_status="single",
        is_private_double_trigger=False,
        marginal_ordinary_rate=0.32,
        sale_date=None,
        sale_price_per_share=None,
    )
    defaults.update(overrides)
    return RSUVestInputs(**defaults)


# ---------------------------------------------------------------------------
# Withholding basics
# ---------------------------------------------------------------------------


def test_basic_vest_flat_22pct_federal():
    """1000 shares × $100 = $100K income. YTD $0, so all federal @ 22%."""
    result = calculate_rsu_vest(_default_inputs())

    assert result.ordinary_income == pytest.approx(100_000.0)
    # Federal supplemental 22% × $100K = $22,000
    assert result.federal_supplemental_wh == pytest.approx(22_000.0)
    assert result.federal_effective_rate == pytest.approx(0.22)
    assert not result.federal_crossed_1m_threshold
    # State 10% × $100K = $10,000
    assert result.state_wh == pytest.approx(10_000.0)
    # SS 6.2% × $100K = $6,200 (below wage base)
    assert result.social_security_wh == pytest.approx(6_200.0)
    assert not result.ss_wage_base_capped
    # Medicare 1.45% × $100K = $1,450
    assert result.medicare_wh == pytest.approx(1_450.0)
    # Additional Medicare: $100K < $200K single threshold → $0
    assert result.additional_medicare_wh == pytest.approx(0.0)
    # Total = $22K + $10K + $6.2K + $1.45K = $39,650
    assert result.total_withholding == pytest.approx(39_650.0)
    assert result.effective_wh_rate == pytest.approx(0.3965)


def test_federal_crosses_1m_threshold_mid_vest():
    """YTD supplemental $600K + vest $500K = $1.1M. Split: $400K@22%, $100K@37%."""
    result = calculate_rsu_vest(_default_inputs(
        shares_vested=5_000,
        fmv_at_vest_per_share=100.0,  # $500K income
        ytd_supplemental_wages=600_000.0,
        ytd_social_security_wages=SOCIAL_SECURITY_WAGE_BASE_2026,  # cap already hit
        ytd_total_wages=600_000.0,
    ))

    # $400K at 22% ($88K) + $100K at 37% ($37K) = $125K
    assert result.federal_supplemental_wh == pytest.approx(125_000.0)
    # Effective rate: $125K / $500K = 25%
    assert result.federal_effective_rate == pytest.approx(0.25)
    assert result.federal_crossed_1m_threshold


def test_federal_all_37pct_when_ytd_already_past_1m():
    """YTD supplemental already $1.2M → entire vest at 37%."""
    result = calculate_rsu_vest(_default_inputs(
        shares_vested=1_000,
        fmv_at_vest_per_share=100.0,  # $100K vest
        ytd_supplemental_wages=1_200_000.0,
        ytd_social_security_wages=SOCIAL_SECURITY_WAGE_BASE_2026,
        ytd_total_wages=1_200_000.0,
    ))

    # $100K × 37% = $37,000
    assert result.federal_supplemental_wh == pytest.approx(37_000.0)
    assert result.federal_effective_rate == pytest.approx(0.37)
    assert result.federal_crossed_1m_threshold


# ---------------------------------------------------------------------------
# Social Security wage base cap
# ---------------------------------------------------------------------------


def test_ss_wage_base_fully_capped_no_ss_wh():
    """YTD SS wages already $180K (over cap $176,100) → no SS on this vest."""
    result = calculate_rsu_vest(_default_inputs(
        ytd_social_security_wages=180_000.0,
    ))

    assert result.social_security_taxable_wages == pytest.approx(0.0)
    assert result.social_security_wh == pytest.approx(0.0)
    assert result.ss_wage_base_capped


def test_ss_wage_base_partial_cap_mid_vest():
    """YTD SS $150K, vest $100K → only $26,100 of vest subject to SS."""
    result = calculate_rsu_vest(_default_inputs(
        ytd_social_security_wages=150_000.0,
    ))

    remaining_room = SOCIAL_SECURITY_WAGE_BASE_2026 - 150_000.0  # 26,100
    assert result.social_security_taxable_wages == pytest.approx(remaining_room)
    assert result.social_security_wh == pytest.approx(remaining_room * 0.062)
    assert result.ss_wage_base_capped


# ---------------------------------------------------------------------------
# Additional Medicare threshold
# ---------------------------------------------------------------------------


def test_additional_medicare_crossed_single_threshold():
    """YTD $180K + vest $50K = $230K > $200K single threshold. Extra $30K at 0.9%."""
    result = calculate_rsu_vest(_default_inputs(
        shares_vested=500,
        fmv_at_vest_per_share=100.0,  # $50K vest
        ytd_total_wages=180_000.0,
        filing_status="single",
    ))

    assert result.additional_medicare_taxable_wages == pytest.approx(30_000.0)
    assert result.additional_medicare_wh == pytest.approx(30_000.0 * 0.009)
    assert result.additional_medicare_threshold_used == pytest.approx(200_000.0)


def test_additional_medicare_mfj_threshold_250k():
    """MFJ threshold is $250K, not $200K."""
    result = calculate_rsu_vest(_default_inputs(
        shares_vested=1_000,
        fmv_at_vest_per_share=100.0,  # $100K vest
        ytd_total_wages=200_000.0,  # under MFJ threshold
        filing_status="mfj",
    ))

    # $300K total > $250K → $50K over threshold
    assert result.additional_medicare_taxable_wages == pytest.approx(50_000.0)
    assert result.additional_medicare_threshold_used == pytest.approx(250_000.0)


# ---------------------------------------------------------------------------
# Sell-to-cover mechanics
# ---------------------------------------------------------------------------


def test_sell_to_cover_ceils_shares():
    """Shares sold = ceil(total_wh / FMV). Basic vest total $39,650 / $100 → 397."""
    result = calculate_rsu_vest(_default_inputs())

    # Total wh $39,650 / $100 = 396.5 → ceil to 397
    assert result.shares_sold_to_cover == 397
    assert result.net_shares_retained == 603
    # Cash overage = 397 × $100 − $39,650 = $50
    assert result.cash_overage == pytest.approx(50.0)


def test_cost_basis_equals_fmv_at_vest():
    """Retained shares get cost basis = FMV at vest."""
    result = calculate_rsu_vest(_default_inputs())

    assert result.cost_basis_per_share == pytest.approx(100.0)
    assert result.total_cost_basis_of_retained_shares == pytest.approx(603 * 100.0)


# ---------------------------------------------------------------------------
# Under-withholding warning
# ---------------------------------------------------------------------------


def test_underwithheld_when_marginal_above_22pct():
    """User at 32% marginal rate vs 22% supplemental → under-withheld by 10% of income."""
    result = calculate_rsu_vest(_default_inputs(
        marginal_ordinary_rate=0.32,
    ))

    # Expected marginal tax: 32% × $100K = $32,000
    # Federal wh actual: 22% × $100K = $22,000
    # Under-withheld: $10,000
    assert result.underwithheld_amount == pytest.approx(10_000.0)
    assert result.is_underwithheld


def test_not_underwithheld_at_22pct_marginal():
    """If marginal rate matches supplemental rate, not under-withheld."""
    result = calculate_rsu_vest(_default_inputs(
        marginal_ordinary_rate=0.22,
    ))

    assert result.underwithheld_amount == pytest.approx(0.0)
    assert not result.is_underwithheld


# ---------------------------------------------------------------------------
# Optional sale outcome
# ---------------------------------------------------------------------------


def test_sale_over_one_year_from_vest_is_ltcg():
    """Vest 2026-06-15, sale 2027-07-01 → 381 days → LTCG."""
    result = calculate_rsu_vest(_default_inputs(
        sale_date=date(2027, 7, 1),
        sale_price_per_share=150.0,
    ))

    assert result.days_from_vest_to_sale == 381
    assert result.is_ltcg_at_sale
    # 603 net shares × ($150 − $100) = $30,150 gain
    assert result.capital_gain_or_loss == pytest.approx(30_150.0)


def test_sale_within_one_year_is_stcg():
    """Sale within 365 days of vest → STCG."""
    result = calculate_rsu_vest(_default_inputs(
        sale_date=date(2027, 1, 1),  # 200 days after vest
        sale_price_per_share=120.0,
    ))

    assert result.days_from_vest_to_sale == 200
    assert not result.is_ltcg_at_sale


def test_sale_at_loss_gives_negative_gain():
    """Sale price below FMV at vest → capital loss (negative gain)."""
    result = calculate_rsu_vest(_default_inputs(
        sale_date=date(2027, 7, 1),
        sale_price_per_share=80.0,  # dropped
    ))

    # 603 shares × ($80 − $100) = −$12,060
    assert result.capital_gain_or_loss == pytest.approx(-12_060.0)


def test_no_sale_data_leaves_sale_outputs_none():
    """Sale outputs are None when sale_date/price not provided."""
    result = calculate_rsu_vest(_default_inputs())

    assert result.days_from_vest_to_sale is None
    assert result.is_ltcg_at_sale is None
    assert result.capital_gain_or_loss is None
