"""Unit tests for Rule 701 sizing calculations."""

from datetime import date

from lib.rule701_calc import (
    CAP_FLOOR,
    DISCLOSURE_THRESHOLD,
    Issuance,
    Rule701Inputs,
    calculate_rule701_capacity,
    max_additional_option_grant,
    value_issuance,
)


def _issuer(**overrides):
    """Small seed-stage issuer: $4M assets, 10M shares outstanding."""
    base = dict(
        is_reporting_company=False,
        total_assets=4_000_000.0,
        outstanding_shares_of_class=10_000_000,
        balance_sheet_date=date(2025, 12, 31),
        issuances=(),
        measurement_date=date(2026, 6, 30),
    )
    base.update(overrides)
    return Rule701Inputs(**base)


def _option(d: date, shares: int, strike: float, fmv: float = 1.00) -> Issuance:
    return Issuance(
        issuance_date=d,
        issuance_type="OPTION",
        shares=shares,
        price_per_share=strike,
        fmv_per_share=fmv,
    )


# ---------------------------------------------------------------------------
# Capacity sizing — Rule 701(d)(2)
# ---------------------------------------------------------------------------


def test_dollar_floor_governs_when_assets_are_small():
    """15% of $4M = $600K, which is below the $1M floor, so the floor governs."""
    result = calculate_rule701_capacity(_issuer())
    assert result.cap_15pct_assets == 600_000.0
    assert result.dollar_capacity == CAP_FLOOR
    assert result.governing_dollar_test == "$1,000,000 floor"


def test_asset_test_governs_when_assets_are_large():
    """15% of $40M = $6M, which beats the $1M floor."""
    result = calculate_rule701_capacity(_issuer(total_assets=40_000_000.0))
    assert result.cap_15pct_assets == 6_000_000.0
    assert result.dollar_capacity == 6_000_000.0
    assert result.governing_dollar_test == "15% of total assets"


def test_share_capacity_is_15pct_of_outstanding():
    result = calculate_rule701_capacity(_issuer())
    assert result.share_capacity == 1_500_000


# ---------------------------------------------------------------------------
# Valuation — Rule 701(d)(3)
# ---------------------------------------------------------------------------


def test_option_valued_at_exercise_price_not_fmv():
    """Rule 701(d)(3)(ii): options count at grant on the EXERCISE price."""
    v = value_issuance(_option(date(2026, 1, 15), shares=100_000, strike=0.50, fmv=5.00))
    assert v.sales_price == 50_000.0  # not 500_000 at FMV


def test_rsu_valued_at_grant_fmv():
    """RSUs have no exercise price, so grant-date FMV is the measure."""
    v = value_issuance(
        Issuance(
            issuance_date=date(2026, 1, 15),
            issuance_type="RSU",
            shares=10_000,
            price_per_share=0.0,
            fmv_per_share=3.00,
        )
    )
    assert v.sales_price == 30_000.0


def test_founder_rsa_consumes_shares_but_almost_no_dollars():
    """A $0.0001 founder RSA barely touches the dollar cap but eats share capacity."""
    inputs = _issuer(
        issuances=(
            Issuance(
                issuance_date=date(2026, 2, 1),
                issuance_type="RSA",
                shares=1_000_000,
                price_per_share=0.0001,
                fmv_per_share=0.0001,
            ),
        )
    )
    result = calculate_rule701_capacity(inputs)
    assert result.aggregate_sales_price == 100.0
    assert result.aggregate_shares == 1_000_000
    assert result.is_compliant


# ---------------------------------------------------------------------------
# The cap is "dollar OR share" — either test can carry the window
# ---------------------------------------------------------------------------


def test_share_test_rescues_a_window_that_blows_the_dollar_cap():
    """$1.2M of options exceeds the $1M dollar cap, but 400K shares is under 15%."""
    inputs = _issuer(
        issuances=(_option(date(2026, 3, 1), shares=400_000, strike=3.00),),
    )
    result = calculate_rule701_capacity(inputs)
    assert result.aggregate_sales_price == 1_200_000.0
    assert result.aggregate_sales_price > result.dollar_capacity  # dollar test fails
    assert result.aggregate_shares == 400_000
    assert result.aggregate_shares <= result.share_capacity  # share test passes
    assert result.is_compliant
    assert result.compliant_via == "the share test (15% of outstanding)"


def test_breach_requires_failing_both_tests():
    """2M shares at $3.00 blows the $1M dollar cap AND the 1.5M share cap."""
    inputs = _issuer(
        issuances=(_option(date(2026, 3, 1), shares=2_000_000, strike=3.00),),
    )
    result = calculate_rule701_capacity(inputs)
    assert result.aggregate_sales_price == 6_000_000.0
    assert result.aggregate_shares == 2_000_000
    assert not result.is_compliant
    assert result.compliant_via is None


# ---------------------------------------------------------------------------
# Rolling 12-month windows, not calendar years
# ---------------------------------------------------------------------------


def test_rolling_window_catches_breach_that_calendar_year_would_miss():
    """Two grants 8 months apart straddle a year boundary.

    Calendar 2025 sees only the Sep grant and calendar 2026 only the May grant,
    so a naive per-calendar-year test passes. The consecutive 12-month window
    ending May 2026 contains both and breaches.
    """
    inputs = _issuer(
        total_assets=4_000_000.0,          # $1M dollar cap
        outstanding_shares_of_class=1_000_000,  # 150K share cap
        issuances=(
            _option(date(2025, 9, 1), shares=100_000, strike=8.00),  # $800K
            _option(date(2026, 5, 1), shares=100_000, strike=8.00),  # $800K
        ),
        measurement_date=date(2026, 5, 1),
    )
    result = calculate_rule701_capacity(inputs)

    # Both land in the window ending 2026-05-01
    assert result.aggregate_sales_price == 1_600_000.0
    assert result.aggregate_shares == 200_000
    assert not result.is_compliant  # over $1M and over 150K shares

    # And the breach is surfaced as the worst window
    assert result.worst_window is not None
    assert not result.worst_window.is_compliant


def test_old_issuance_drops_out_of_the_window():
    """An issuance more than 12 months before the measurement date is excluded."""
    inputs = _issuer(
        issuances=(
            _option(date(2024, 1, 1), shares=500_000, strike=2.00),  # long past
            _option(date(2026, 6, 1), shares=10_000, strike=2.00),
        ),
        measurement_date=date(2026, 6, 30),
    )
    result = calculate_rule701_capacity(inputs)
    assert result.aggregate_sales_price == 20_000.0
    assert result.aggregate_shares == 10_000


# ---------------------------------------------------------------------------
# Disclosure trigger — Rule 701(e)
# ---------------------------------------------------------------------------


def test_disclosure_not_triggered_below_10m():
    inputs = _issuer(
        total_assets=200_000_000.0,  # $30M dollar cap, so no cap breach
        outstanding_shares_of_class=100_000_000,
        issuances=(_option(date(2026, 4, 1), shares=1_000_000, strike=9.00),),  # $9M
    )
    result = calculate_rule701_capacity(inputs)
    assert result.aggregate_sales_price == 9_000_000.0
    assert not result.disclosure_triggered
    assert result.amount_over_disclosure_threshold == 0.0


def test_disclosure_triggered_above_10m():
    inputs = _issuer(
        total_assets=200_000_000.0,
        outstanding_shares_of_class=100_000_000,
        issuances=(_option(date(2026, 4, 1), shares=1_000_000, strike=12.00),),  # $12M
    )
    result = calculate_rule701_capacity(inputs)
    assert result.aggregate_sales_price == 12_000_000.0
    assert result.disclosure_triggered
    assert result.disclosure_trigger_date == date(2026, 4, 1)
    assert result.amount_over_disclosure_threshold == 2_000_000.0
    assert result.is_compliant  # still inside the cap — disclosure is a separate test


def test_exactly_10m_does_not_trigger():
    """Rule 701(e) says 'exceeds' $10 million."""
    inputs = _issuer(
        total_assets=200_000_000.0,
        outstanding_shares_of_class=100_000_000,
        issuances=(_option(date(2026, 4, 1), shares=1_000_000, strike=10.00),),
    )
    result = calculate_rule701_capacity(inputs)
    assert result.aggregate_sales_price == DISCLOSURE_THRESHOLD
    assert not result.disclosure_triggered


# ---------------------------------------------------------------------------
# Availability — Rule 701(b)
# ---------------------------------------------------------------------------


def test_reporting_company_cannot_use_rule_701():
    result = calculate_rule701_capacity(_issuer(is_reporting_company=True))
    assert not result.exemption_available
    assert result.unavailable_reason is not None
    assert "Form S-8" in result.unavailable_reason


def test_private_company_can_use_rule_701():
    result = calculate_rule701_capacity(_issuer())
    assert result.exemption_available
    assert result.unavailable_reason is None


# ---------------------------------------------------------------------------
# Warnings + headroom helper
# ---------------------------------------------------------------------------


def test_blue_sky_warning_always_present():
    result = calculate_rule701_capacity(_issuer())
    assert any("Blue Sky" in w for w in result.warnings)


def test_stale_balance_sheet_flagged():
    inputs = _issuer(
        balance_sheet_date=date(2024, 12, 31),
        measurement_date=date(2026, 6, 30),
    )
    result = calculate_rule701_capacity(inputs)
    assert result.balance_sheet_is_stale
    assert any("Balance sheet date" in w for w in result.warnings)


def test_max_additional_option_grant_uses_more_permissive_test():
    """$1M dollar cap at a $1.00 strike = 1M shares; share cap allows 1.5M."""
    inputs = _issuer()
    assert max_additional_option_grant(inputs, exercise_price=1.00) == 1_500_000


def test_max_additional_option_grant_zero_when_already_over():
    inputs = _issuer(
        issuances=(_option(date(2026, 3, 1), shares=2_000_000, strike=3.00),),
    )
    assert max_additional_option_grant(inputs, exercise_price=1.00) == 0
