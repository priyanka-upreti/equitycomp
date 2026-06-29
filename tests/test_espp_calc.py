"""Unit tests for ESPP §423 calculations."""

from datetime import date

import pytest

from lib.espp_calc import (
    ESPPInputs,
    calculate_espp_purchase,
    estimate_marginal_federal_tax,
)


# ---------------------------------------------------------------------------
# Classic scenarios
# ---------------------------------------------------------------------------


def test_qd_with_lookback_appreciation():
    """Classic QD: stock appreciated, look-back applies, held > 2y/1y."""
    inputs = ESPPInputs(
        offering_start_fmv=100.0,
        purchase_fmv=150.0,
        discount_pct=0.15,
        has_lookback=True,
        offering_start_date=date(2022, 1, 1),
        purchase_date=date(2022, 6, 30),
        sale_date=date(2025, 8, 1),  # ~3 years post-offering, ~3 years post-purchase
        sale_price=200.0,
        contributions=1700.0,
    )
    result = calculate_espp_purchase(inputs)

    # Purchase price = $100 × 0.85 = $85 (look-back picks lower offering FMV)
    assert result.purchase_price_per_share == pytest.approx(85.0)
    assert result.reference_fmv == pytest.approx(100.0)
    assert result.shares_purchased == pytest.approx(20.0)
    assert result.bargain_element_per_share == pytest.approx(65.0)  # $150 - $85
    assert result.total_bargain_element == pytest.approx(1300.0)

    # Disposition: QD
    assert result.disposition == "QD"
    assert result.qd_reason_failed == []

    # QD ordinary income = lesser of:
    #   (1) $100 - $85 = $15/share → $300 total
    #   (2) $200 - $85 = $115/share → $2300 total
    # → $300
    assert result.qd_ordinary_income == pytest.approx(300.0)

    # QD capital gain = $200 × 20 - $85 × 20 - $300 = $4000 - $1700 - $300 = $2000
    assert result.qd_capital_gain == pytest.approx(2000.0)
    assert result.qd_capital_loss == pytest.approx(0.0)


def test_dd_same_day_sale():
    """DD same-day flip: sold immediately at purchase."""
    inputs = ESPPInputs(
        offering_start_fmv=100.0,
        purchase_fmv=150.0,
        discount_pct=0.15,
        has_lookback=True,
        offering_start_date=date(2024, 1, 1),
        purchase_date=date(2024, 6, 30),
        sale_date=date(2024, 6, 30),  # same day
        sale_price=150.0,
        contributions=1700.0,
    )
    result = calculate_espp_purchase(inputs)

    assert result.disposition == "DD"
    # Held 0 days from purchase (need > 365) and 181 days from offering (need > 730)
    assert not result.holds_one_year_from_purchase
    assert not result.holds_two_years_from_offering

    # DD ordinary income = full bargain = $1300
    assert result.dd_ordinary_income == pytest.approx(1300.0)
    # DD capital gain = ($150 - $150) × 20 = $0
    assert result.dd_capital_gain == pytest.approx(0.0)
    assert result.dd_capital_loss == pytest.approx(0.0)


def test_25k_limit_caps_purchase_with_refund():
    """§423(b)(8) cap: 600 shares requested → 500 actually purchased + $4,250 refunded."""
    inputs = ESPPInputs(
        offering_start_fmv=50.0,
        purchase_fmv=50.0,
        discount_pct=0.15,
        has_lookback=True,
        offering_start_date=date(2024, 1, 1),
        purchase_date=date(2024, 6, 30),
        sale_date=date(2024, 6, 30),
        sale_price=50.0,
        contributions=25_500.0,  # would buy 600 at $42.50 — but capped at 500
    )
    result = calculate_espp_purchase(inputs)

    assert result.shares_requested == pytest.approx(600.0)  # uncapped (informational)
    assert result.shares_purchased == pytest.approx(500.0)  # actually bought (capped)
    assert result.max_shares_under_25k_limit == pytest.approx(500.0)
    assert not result.is_within_25k_limit
    assert result.shares_over_limit == pytest.approx(100.0)
    # 100 excess shares × $42.50 purchase price = $4,250 refunded to employee
    assert result.excess_contributions_refunded == pytest.approx(4_250.0)
    # Bargain element calculated on CAPPED shares only
    # purchase FMV $50 − purchase price $42.50 = $7.50/share × 500 = $3,750
    assert result.total_bargain_element == pytest.approx(3_750.0)


def test_within_25k_limit():
    """Stays within $25K annual limit."""
    inputs = ESPPInputs(
        offering_start_fmv=100.0,
        purchase_fmv=120.0,
        discount_pct=0.15,
        has_lookback=True,
        offering_start_date=date(2024, 1, 1),
        purchase_date=date(2024, 6, 30),
        sale_date=date(2027, 1, 1),
        sale_price=150.0,
        contributions=8_500.0,  # 100 shares at $85
    )
    result = calculate_espp_purchase(inputs)

    assert result.shares_requested == pytest.approx(100.0)
    assert result.shares_purchased == pytest.approx(100.0)
    assert result.max_shares_under_25k_limit == pytest.approx(250.0)
    assert result.is_within_25k_limit
    assert result.shares_over_limit == pytest.approx(0.0)
    assert result.excess_contributions_refunded == pytest.approx(0.0)


def test_no_lookback_offering_above_purchase():
    """No-look-back plan: discount applies to purchase FMV only.

    Corner case: offering FMV ($80) > purchase price ($90).
    The §423(c)(1) prong is NEGATIVE → ordinary income at QD is $0.
    QD becomes MORE favorable than expected (all gain is LTCG).
    """
    inputs = ESPPInputs(
        offering_start_fmv=80.0,
        purchase_fmv=100.0,
        discount_pct=0.10,
        has_lookback=False,
        offering_start_date=date(2022, 1, 1),
        purchase_date=date(2022, 6, 30),
        sale_date=date(2025, 8, 1),
        sale_price=150.0,
        contributions=900.0,  # 10 shares at $90
    )
    result = calculate_espp_purchase(inputs)

    # Purchase price = $100 × 0.90 = $90 (no look-back, uses purchase FMV)
    assert result.purchase_price_per_share == pytest.approx(90.0)
    assert result.shares_purchased == pytest.approx(10.0)

    # QD ordinary income: lesser of
    #   (1) $80 - $90 = -$10 → clamped to $0
    #   (2) $150 - $90 = $60 × 10 = $600
    # → $0 (the offering-side prong wins because it's <= 0)
    assert result.disposition == "QD"
    assert result.qd_ordinary_income == pytest.approx(0.0)
    # All $600 of gain is LTCG
    assert result.qd_capital_gain == pytest.approx(600.0)


def test_qd_sale_below_purchase_price():
    """QD sale at a loss: no ordinary income recognized, capital loss instead."""
    inputs = ESPPInputs(
        offering_start_fmv=100.0,
        purchase_fmv=150.0,
        discount_pct=0.15,
        has_lookback=True,
        offering_start_date=date(2022, 1, 1),
        purchase_date=date(2022, 6, 30),
        sale_date=date(2025, 8, 1),  # > 2 yrs offering, > 1 yr purchase
        sale_price=70.0,  # sale below purchase price ($85)
        contributions=850.0,  # 10 shares at $85
    )
    result = calculate_espp_purchase(inputs)

    assert result.disposition == "QD"
    # No ordinary income (sold at loss)
    assert result.qd_ordinary_income == pytest.approx(0.0)
    # Capital loss = $70 × 10 - $85 × 10 = -$150 → loss of $150
    assert result.qd_capital_gain == pytest.approx(0.0)
    assert result.qd_capital_loss == pytest.approx(150.0)


def test_lookback_with_depreciation_during_offering():
    """Stock dropped during offering — look-back picks the lower purchase FMV.

    Critical test: §423(c)(1) = offering_fmv - purchase_price ($49) is LARGER than
    the naive "offering FMV × discount" ($15). Confirms we use the correct formula.
    """
    inputs = ESPPInputs(
        offering_start_fmv=100.0,
        purchase_fmv=60.0,  # stock dropped during offering
        discount_pct=0.15,
        has_lookback=True,
        offering_start_date=date(2022, 1, 1),
        purchase_date=date(2022, 6, 30),
        sale_date=date(2025, 8, 1),
        sale_price=200.0,  # bounced back & beyond
        contributions=510.0,  # 10 shares at $51
    )
    result = calculate_espp_purchase(inputs)

    # Look-back uses lower of $100 or $60 = $60. Purchase price = $60 × 0.85 = $51.
    assert result.reference_fmv == pytest.approx(60.0)
    assert result.purchase_price_per_share == pytest.approx(51.0)
    assert result.shares_purchased == pytest.approx(10.0)

    # QD ordinary income: lesser of
    #   (1) $100 - $51 = $49/share → $490 total  ← NOT $15 × 10 = $150
    #   (2) $200 - $51 = $149/share → $1490 total
    # → $490
    assert result.disposition == "QD"
    assert result.qd_ordinary_income == pytest.approx(490.0)
    # Capital gain = $200 × 10 - $51 × 10 - $490 = $2000 - $510 - $490 = $1000
    assert result.qd_capital_gain == pytest.approx(1000.0)


def test_holding_period_exact_one_year_boundary():
    """Sold exactly 365 days after purchase fails the 1-year QD rule."""
    inputs = ESPPInputs(
        offering_start_fmv=100.0,
        purchase_fmv=100.0,
        discount_pct=0.15,
        has_lookback=False,
        offering_start_date=date(2020, 1, 1),
        purchase_date=date(2023, 1, 1),
        sale_date=date(2024, 1, 1),  # exactly 365 days post-purchase (need > 365)
        sale_price=120.0,
        contributions=850.0,
    )
    result = calculate_espp_purchase(inputs)

    # 365 days is NOT > 365 → fails 1-year-from-purchase rule → DD
    assert result.days_from_purchase_to_sale == 365
    assert not result.holds_one_year_from_purchase
    assert result.disposition == "DD"


def test_qd_at_day_366_and_731():
    """Day 366 post-purchase + day 731 post-offering: QD passes."""
    inputs = ESPPInputs(
        offering_start_fmv=100.0,
        purchase_fmv=100.0,
        discount_pct=0.15,
        has_lookback=False,
        offering_start_date=date(2022, 1, 1),
        purchase_date=date(2023, 1, 1),
        sale_date=date(2024, 1, 2),  # 731 days post-offering, 366 days post-purchase
        sale_price=120.0,
        contributions=850.0,
    )
    result = calculate_espp_purchase(inputs)

    assert result.days_from_offering_start_to_sale == 731
    assert result.days_from_purchase_to_sale == 366
    assert result.holds_two_years_from_offering
    assert result.holds_one_year_from_purchase
    assert result.disposition == "QD"


# ---------------------------------------------------------------------------
# Marginal tax estimator
# ---------------------------------------------------------------------------


def test_marginal_tax_typical_household():
    """Single filer at $150K base + $5K ESPP ordinary → 24% bracket marginal tax."""
    result = estimate_marginal_federal_tax(
        ordinary_income=5_000.0,
        other_taxable_income=150_000.0,
        filing_status="single",
    )

    # At $155K total, marginal rate is 24% (single bracket runs $103,350 → $197,300)
    assert result["marginal_rate"] == pytest.approx(0.24)
    assert result["total_taxable_income"] == pytest.approx(155_000.0)
    # Incremental tax: $5K at 24% = $1,200
    assert result["incremental_federal_tax"] == pytest.approx(1_200.0)


def test_marginal_tax_zero_other_income():
    """Lowest bracket: $5K ordinary with zero base → 10% rate."""
    result = estimate_marginal_federal_tax(
        ordinary_income=5_000.0,
        other_taxable_income=0.0,
        filing_status="single",
    )
    assert result["marginal_rate"] == pytest.approx(0.10)
    assert result["incremental_federal_tax"] == pytest.approx(500.0)
