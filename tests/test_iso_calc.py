"""Tests for ISO exercise calculations.

Validation source: Tax PPT 04 (`04_IRC_Section_422_ISOs.pptx`) worked examples
from Level-1-Attempt-2 study guide.
"""

from datetime import date

import pytest

from lib.iso_calc import (
    ISOExerciseInputs,
    calculate_iso_exercise,
    estimate_amt_due,
)


# ---------------------------------------------------------------------------
# Test 1: Classic QD scenario
# Grant Jan 2022, exercise Jan 2024, sell Feb 2025
# Strike $10, FMV at exercise $40, sale at $60, 100 shares
# Expected: QD (>1 yr post-exercise + >2 yr post-grant)
# Spread = $3,000 (AMT preference)
# QD gain = ($60 - $10) × 100 = $5,000 LTCG
# ---------------------------------------------------------------------------


def test_qd_scenario_classic():
    inputs = ISOExerciseInputs(
        shares=100,
        strike=10.00,
        fmv_at_exercise=40.00,
        grant_date=date(2022, 1, 1),
        exercise_date=date(2024, 1, 1),
        sale_date=date(2025, 2, 1),
        sale_price=60.00,
    )
    out = calculate_iso_exercise(inputs)

    assert out.disposition == "QD"
    assert out.spread_per_share == 30.00
    assert out.total_spread == 3_000.00
    assert out.regular_tax_basis_per_share == 10.00
    assert out.amt_basis_per_share == 40.00
    assert out.qd_total_gain == 5_000.00
    assert out.qd_long_term_capital_gain == 5_000.00
    assert out.holds_one_year_post_exercise is True
    assert out.holds_two_years_post_grant is True


# ---------------------------------------------------------------------------
# Test 2: Cashless exercise + same-day sale = DD
# Spread becomes ordinary income; minimal capital gain
# ---------------------------------------------------------------------------


def test_dd_same_day_sale():
    inputs = ISOExerciseInputs(
        shares=100,
        strike=10.00,
        fmv_at_exercise=40.00,
        grant_date=date(2024, 6, 1),
        exercise_date=date(2024, 6, 1),
        sale_date=date(2024, 6, 1),  # same-day sale
        sale_price=40.00,  # at FMV
    )
    out = calculate_iso_exercise(inputs)

    assert out.disposition == "DD"
    assert out.dd_ordinary_income == 3_000.00  # full spread at exercise
    assert out.dd_capital_gain == 0.00  # no appreciation post-exercise


# ---------------------------------------------------------------------------
# Test 3: DD with appreciation past FMV at exercise
# Spread = ordinary income; further appreciation = capital gain
# Held < 1 year → short-term
# ---------------------------------------------------------------------------


def test_dd_with_appreciation_short_term():
    inputs = ISOExerciseInputs(
        shares=100,
        strike=10.00,
        fmv_at_exercise=40.00,
        grant_date=date(2024, 1, 1),
        exercise_date=date(2024, 6, 1),
        sale_date=date(2024, 12, 1),  # 183 days post-exercise → DD
        sale_price=55.00,
    )
    out = calculate_iso_exercise(inputs)

    assert out.disposition == "DD"
    assert out.dd_ordinary_income == 3_000.00  # spread at exercise: (40-10) × 100
    assert out.dd_capital_gain == 1_500.00  # (55-40) × 100
    assert out.dd_capital_gain_is_long_term is False  # held < 1 year


# ---------------------------------------------------------------------------
# Test 4: DD held > 1 year (but < 2 years from grant)
# Fails 2-year-post-grant test → still DD
# Capital gain is LTCG (>1 year from exercise)
# ---------------------------------------------------------------------------


def test_dd_failed_two_year_grant_rule():
    inputs = ISOExerciseInputs(
        shares=100,
        strike=10.00,
        fmv_at_exercise=40.00,
        grant_date=date(2023, 6, 1),
        exercise_date=date(2023, 12, 1),
        sale_date=date(2025, 1, 15),  # ~13 months post-exercise; ~19 months post-grant
        sale_price=50.00,
    )
    out = calculate_iso_exercise(inputs)

    assert out.disposition == "DD"
    assert "post-grant" in " ".join(out.qd_reason_failed)
    assert out.holds_one_year_post_exercise is True
    assert out.holds_two_years_post_grant is False
    assert out.dd_ordinary_income == 3_000.00
    assert out.dd_capital_gain == 1_000.00  # (50-40) × 100
    assert out.dd_capital_gain_is_long_term is True


# ---------------------------------------------------------------------------
# Test 5: Sale below strike → capital loss + $0 ordinary income at DD
# Per §422(c)(2): ordinary income at DD = lesser of spread or (sale - strike)
# If sale < strike, "sale - strike" is negative → ordinary income = $0
# ---------------------------------------------------------------------------


def test_dd_underwater_sale():
    inputs = ISOExerciseInputs(
        shares=100,
        strike=20.00,
        fmv_at_exercise=50.00,
        grant_date=date(2024, 1, 1),
        exercise_date=date(2024, 6, 1),
        sale_date=date(2024, 9, 1),  # 92 days → DD
        sale_price=15.00,  # below strike
    )
    out = calculate_iso_exercise(inputs)

    assert out.disposition == "DD"
    assert out.dd_ordinary_income == 0.00  # sale below strike
    assert out.dd_capital_loss == 500.00  # (20-15) × 100


# ---------------------------------------------------------------------------
# Test 6: 100% spread → at-the-money exercise
# No AMT preference, no income at exercise, simple LTCG at QD sale
# ---------------------------------------------------------------------------


def test_atm_exercise_no_spread():
    inputs = ISOExerciseInputs(
        shares=50,
        strike=25.00,
        fmv_at_exercise=25.00,  # ATM exercise (rare; FMV = strike)
        grant_date=date(2022, 1, 1),
        exercise_date=date(2024, 1, 1),
        sale_date=date(2025, 6, 1),
        sale_price=40.00,
    )
    out = calculate_iso_exercise(inputs)

    assert out.spread_per_share == 0.00
    assert out.total_spread == 0.00  # no AMT preference
    assert out.disposition == "QD"
    assert out.qd_total_gain == 750.00  # (40-25) × 50


# ---------------------------------------------------------------------------
# Test 7: AMT estimation — example from Tax PPT 04 cheat sheet
# Single filer; $200K ordinary income; ISO spread $200K → AMTI ~$400K
# Should owe meaningful AMT (six figures)
# ---------------------------------------------------------------------------


def test_amt_estimation_large_spread():
    result = estimate_amt_due(
        total_spread=200_000,
        other_taxable_income=200_000,
        filing_status="single",
        regular_tax_estimate=50_000,
    )

    assert result["amti"] == 400_000
    # Exemption phaseout starts at $626,350 → full exemption ($88,100) applies
    assert result["exemption"] == 88_100
    assert result["taxable_amti"] == pytest.approx(311_900)
    # 26% × $232,600 + 28% × ($311,900 - $232,600)
    expected_tentative = 232_600 * 0.26 + (311_900 - 232_600) * 0.28
    assert result["tentative_amt"] == pytest.approx(expected_tentative, abs=1)
    assert result["amt_due"] == pytest.approx(expected_tentative - 50_000, abs=1)


def test_amt_estimation_small_spread_no_amt():
    """Small ISO exercise + modest ordinary income → AMT should not exceed regular tax."""
    result = estimate_amt_due(
        total_spread=5_000,
        other_taxable_income=80_000,
        filing_status="single",
        regular_tax_estimate=15_000,
    )

    # AMTI = $85,000; exemption $88,100; taxable AMTI = $0
    assert result["taxable_amti"] == 0
    assert result["tentative_amt"] == 0
    assert result["amt_due"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
