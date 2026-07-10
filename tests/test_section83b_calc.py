"""Unit tests for §83(b) decision calculations."""

from datetime import date

import pytest

from lib.section83b_calc import (
    Section83bInputs,
    calculate_section83b_scenarios,
)


# ---------------------------------------------------------------------------
# Classic scenarios
# ---------------------------------------------------------------------------


def test_founder_grant_massive_appreciation():
    """Classic founder RSA: $0.0001 FMV at grant, huge growth, low forfeit → §83(b) obviously wins."""
    inputs = Section83bInputs(
        grant_type="RSA",
        grant_date=date(2022, 1, 1),
        shares=1_000_000,
        price_paid_per_share=0.0001,
        fmv_at_grant_per_share=0.0001,  # essentially $0
        vesting_years=4.0,
        projected_fmv_at_vest_per_share=10.00,  # $10M valuation vest
        projected_sale_price_per_share=50.00,  # $50M exit
        sale_date=date(2027, 6, 1),  # ~5.5 years post-grant
        forfeiture_probability=0.05,  # low — founder likely stays
        marginal_ordinary_rate=0.37,  # top bracket
        ltcg_rate=0.20,  # top LTCG
    )
    result = calculate_section83b_scenarios(inputs)

    # §83(b) income at grant is basically $0 (spread = 0)
    assert result.a_income_at_grant == pytest.approx(0.0)
    assert result.a_tax_at_grant == pytest.approx(0.0)

    # §83(b) at sale: all $50M is LTCG (held > 1 yr from grant)
    assert result.a_is_ltcg
    assert result.a_capital_gain_at_sale == pytest.approx(50_000_000.0, rel=1e-5)
    assert result.a_tax_at_sale == pytest.approx(10_000_000.0, rel=1e-5)  # 20% × $50M

    # No §83(b): ordinary income of $10M at vest, then LTCG on remaining $40M
    assert result.b_income_at_vest == pytest.approx(10_000_000.0, rel=1e-5)
    assert result.b_tax_at_vest == pytest.approx(3_700_000.0, rel=1e-5)  # 37% × $10M
    assert result.b_is_ltcg
    assert result.b_capital_gain_at_sale == pytest.approx(40_000_000.0, rel=1e-5)
    assert result.b_tax_at_sale == pytest.approx(8_000_000.0, rel=1e-5)  # 20% × $40M

    # §83(b) saves ~$1.7M in expected value (accounting for 5% forfeit risk)
    assert result.expected_savings_from_83b > 1_500_000
    assert result.is_83b_favorable_at_zero_forfeit


def test_forfeit_probability_100pct():
    """100% forfeit probability: §83(b) is worst (all tax paid, no benefit)."""
    inputs = Section83bInputs(
        grant_type="RSA",
        grant_date=date(2024, 1, 1),
        shares=10_000,
        price_paid_per_share=0.0,
        fmv_at_grant_per_share=1.00,
        vesting_years=4.0,
        projected_fmv_at_vest_per_share=10.00,
        projected_sale_price_per_share=15.00,
        sale_date=date(2028, 6, 1),
        forfeiture_probability=1.0,  # 100% certain to forfeit
        marginal_ordinary_rate=0.37,
        ltcg_rate=0.20,
    )
    result = calculate_section83b_scenarios(inputs)

    # §83(b) expected tax = tax at grant (all paid, no refund)
    assert result.a_expected_tax == pytest.approx(result.a_tax_at_grant)
    # No §83(b) expected tax = $0 (nothing recognized)
    assert result.b_expected_tax == pytest.approx(0.0)
    # §83(b) is a losing move by exactly the grant-tax amount
    assert result.expected_savings_from_83b == pytest.approx(-result.a_tax_at_grant)


def test_forfeit_probability_zero_and_appreciation():
    """0% forfeit + big appreciation → §83(b) saves ordinary-rate on the delta."""
    inputs = Section83bInputs(
        grant_type="RSA",
        grant_date=date(2022, 1, 1),
        shares=10_000,
        price_paid_per_share=0.0,
        fmv_at_grant_per_share=1.00,
        vesting_years=4.0,
        projected_fmv_at_vest_per_share=10.00,  # $10 at vest
        projected_sale_price_per_share=20.00,  # $20 at sale
        sale_date=date(2027, 6, 1),
        forfeiture_probability=0.0,  # certain to vest
        marginal_ordinary_rate=0.37,
        ltcg_rate=0.20,
    )
    result = calculate_section83b_scenarios(inputs)

    # §83(b): $10K ordinary income at grant + LTCG on ($20-$1) × 10K = $190K
    assert result.a_income_at_grant == pytest.approx(10_000.0)
    assert result.a_tax_at_grant == pytest.approx(3_700.0)  # 37% × $10K
    assert result.a_is_ltcg
    assert result.a_capital_gain_at_sale == pytest.approx(190_000.0)
    assert result.a_tax_at_sale == pytest.approx(38_000.0)  # 20% × $190K

    # No §83(b): $100K ordinary income at vest + LTCG on ($20-$10) × 10K = $100K
    assert result.b_income_at_vest == pytest.approx(100_000.0)
    assert result.b_tax_at_vest == pytest.approx(37_000.0)  # 37% × $100K
    assert result.b_capital_gain_at_sale == pytest.approx(100_000.0)
    assert result.b_tax_at_sale == pytest.approx(20_000.0)  # 20% × $100K

    # §83(b) saves ($37K + $20K) − ($3.7K + $38K) = $57K − $41.7K = $15.3K
    assert result.expected_savings_from_83b == pytest.approx(15_300.0)
    assert result.is_83b_favorable_at_zero_forfeit


def test_sold_within_one_year_of_grant_forces_stcg_on_83b():
    """§83(b) with sale <365 days from grant → capital gain is STCG (ordinary rate), no LTCG benefit."""
    inputs = Section83bInputs(
        grant_type="RSA",
        grant_date=date(2024, 1, 1),
        shares=1_000,
        price_paid_per_share=0.0,
        fmv_at_grant_per_share=1.00,
        vesting_years=1.0,  # short vest
        projected_fmv_at_vest_per_share=5.00,
        projected_sale_price_per_share=8.00,
        sale_date=date(2024, 10, 1),  # 274 days post-grant (< 365)
        forfeiture_probability=0.0,
        marginal_ordinary_rate=0.37,
        ltcg_rate=0.20,
    )
    result = calculate_section83b_scenarios(inputs)

    assert result.days_grant_to_sale == 274
    assert not result.a_is_ltcg  # < 1 yr from grant → STCG
    # Cap gain rate = ordinary rate (37%) for STCG
    assert result.a_tax_at_sale == pytest.approx(
        result.a_capital_gain_at_sale * 0.37
    )


def test_sale_below_fmv_at_grant_no_capital_gain():
    """Sale below FMV at grant → cap gain = 0 (no negative gain)."""
    inputs = Section83bInputs(
        grant_type="RSA",
        grant_date=date(2022, 1, 1),
        shares=1_000,
        price_paid_per_share=0.0,
        fmv_at_grant_per_share=10.00,  # taxed on $10K at grant
        vesting_years=4.0,
        projected_fmv_at_vest_per_share=8.00,
        projected_sale_price_per_share=5.00,  # sold at loss
        sale_date=date(2027, 6, 1),
        forfeiture_probability=0.0,
        marginal_ordinary_rate=0.37,
        ltcg_rate=0.20,
    )
    result = calculate_section83b_scenarios(inputs)

    # §83(b): $10K ordinary income at grant. Sold below → cap gain floor at 0.
    assert result.a_capital_gain_at_sale == pytest.approx(0.0)
    assert result.a_tax_at_sale == pytest.approx(0.0)
    # V1 simplification: doesn't model capital loss (Phase 2)


def test_breakeven_forfeit_probability():
    """Breakeven is the forfeit rate that makes E[§83(b)] = E[§83(a)]."""
    inputs = Section83bInputs(
        grant_type="RSA",
        grant_date=date(2022, 1, 1),
        shares=10_000,
        price_paid_per_share=0.0,
        fmv_at_grant_per_share=1.00,
        vesting_years=4.0,
        projected_fmv_at_vest_per_share=10.00,
        projected_sale_price_per_share=20.00,
        sale_date=date(2027, 6, 1),
        forfeiture_probability=0.5,  # doesn't affect breakeven calc
        marginal_ordinary_rate=0.37,
        ltcg_rate=0.20,
    )
    result = calculate_section83b_scenarios(inputs)

    # Verify breakeven by plugging p back in
    p = result.breakeven_forfeit_probability
    assert p is not None
    assert 0.0 <= p <= 1.0
    # At breakeven, expected tax should be equal
    ea = (1 - p) * result.a_total_tax_if_vested + p * result.a_total_tax_if_forfeited
    eb = (1 - p) * result.b_total_tax_if_vested + p * result.b_total_tax_if_forfeited
    assert ea == pytest.approx(eb, rel=1e-6)


def test_vest_date_computed_from_years():
    """4.0 vesting years → vest_date = grant + 1460 days."""
    inputs = Section83bInputs(
        grant_type="RSA",
        grant_date=date(2024, 1, 1),
        shares=1_000,
        price_paid_per_share=0.0,
        fmv_at_grant_per_share=1.00,
        vesting_years=4.0,
        projected_fmv_at_vest_per_share=5.00,
        projected_sale_price_per_share=10.00,
        sale_date=date(2029, 1, 1),
        forfeiture_probability=0.1,
        marginal_ordinary_rate=0.37,
        ltcg_rate=0.20,
    )
    result = calculate_section83b_scenarios(inputs)
    # int(4.0 * 365) = 1460
    assert result.vest_date == date(2027, 12, 31)


def test_election_deadline_is_30_days_after_grant():
    """30-day election deadline runs from grant date."""
    inputs = Section83bInputs(
        grant_type="RSA",
        grant_date=date(2024, 6, 1),
        shares=100,
        price_paid_per_share=0.0,
        fmv_at_grant_per_share=1.0,
        vesting_years=4.0,
        projected_fmv_at_vest_per_share=5.0,
        projected_sale_price_per_share=10.0,
        sale_date=date(2029, 1, 1),
        forfeiture_probability=0.0,
        marginal_ordinary_rate=0.32,
        ltcg_rate=0.15,
    )
    result = calculate_section83b_scenarios(inputs)
    assert result.election_deadline == date(2024, 7, 1)  # +30 days


def test_no_appreciation_no_savings():
    """If FMV_grant == FMV_vest and no forfeit, §83(b) saves nothing meaningful."""
    inputs = Section83bInputs(
        grant_type="RSA",
        grant_date=date(2022, 1, 1),
        shares=1_000,
        price_paid_per_share=0.0,
        fmv_at_grant_per_share=10.0,
        vesting_years=4.0,
        projected_fmv_at_vest_per_share=10.0,  # no appreciation during vest
        projected_sale_price_per_share=15.0,
        sale_date=date(2027, 6, 1),
        forfeiture_probability=0.0,
        marginal_ordinary_rate=0.37,
        ltcg_rate=0.20,
    )
    result = calculate_section83b_scenarios(inputs)

    # Both scenarios: $10K ordinary income (at grant or at vest), then $5K LTCG
    # Same tax bill → savings ~0
    assert result.expected_savings_from_83b == pytest.approx(0.0, abs=1e-6)
