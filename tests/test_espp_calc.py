"""Unit tests for ESPP §423 calculations."""

from datetime import date

import pytest

from lib.espp_calc import (
    ESPPInputs,
    ESPPMultiInputs,
    PurchaseInput,
    calculate_espp_purchase,
    calculate_multi_purchase_espp,
    estimate_marginal_federal_tax,
    generate_purchase_dates,
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


# ---------------------------------------------------------------------------
# Multi-purchase ESPP scenarios (NVIDIA / Apple style)
# ---------------------------------------------------------------------------


def test_generate_purchase_dates_default_6mo():
    """4 purchase dates spaced 6 months apart from offering start."""
    dates_out = generate_purchase_dates(date(2024, 3, 1), num_purchases=4)
    assert dates_out == [
        date(2024, 9, 1),
        date(2025, 3, 1),
        date(2025, 9, 1),
        date(2026, 3, 1),
    ]


def test_multi_purchase_no_reset_all_appreciation():
    """4 purchases, FMVs all above anchor → no reset, all use original anchor."""
    inputs = ESPPMultiInputs(
        offering_start_date=date(2024, 1, 1),
        offering_start_fmv=100.0,
        discount_pct=0.15,
        has_lookback=True,
        has_reset=True,
        purchases=[
            PurchaseInput(date(2024, 6, 30), 120.0, 3_000.0),
            PurchaseInput(date(2024, 12, 31), 140.0, 3_000.0),
            PurchaseInput(date(2025, 6, 30), 160.0, 3_000.0),
            PurchaseInput(date(2025, 12, 31), 200.0, 3_000.0),
        ],
        sale_date=date(2027, 6, 1),
        sale_price=250.0,
    )
    result = calculate_multi_purchase_espp(inputs)

    # No resets — all 4 purchases use the original anchor
    assert result.reset_dates == []
    for pe in result.purchase_events:
        assert pe.effective_anchor_date == date(2024, 1, 1)
        assert pe.effective_anchor_fmv == pytest.approx(100.0)
        assert not pe.reset_occurred
        # Look-back picks min(100, current FMV) = 100 (all higher)
        assert pe.reference_fmv == pytest.approx(100.0)
        # Purchase price = $100 × 0.85 = $85
        assert pe.purchase_price == pytest.approx(85.0)
        # 3000 / 85 ≈ 35.294 shares
        assert pe.shares_purchased == pytest.approx(3_000.0 / 85.0)


def test_multi_purchase_single_reset_on_dip():
    """Drop at purchase 2 triggers reset; purchases 3+ use new anchor."""
    inputs = ESPPMultiInputs(
        offering_start_date=date(2024, 1, 1),
        offering_start_fmv=100.0,
        discount_pct=0.15,
        has_lookback=True,
        has_reset=True,
        purchases=[
            PurchaseInput(date(2024, 6, 30), 120.0, 3_000.0),  # no reset, anchor $100
            PurchaseInput(date(2024, 12, 31), 80.0, 3_000.0),  # RESET — anchor → $80
            PurchaseInput(date(2025, 6, 30), 110.0, 3_000.0),  # uses new anchor $80
            PurchaseInput(date(2025, 12, 31), 130.0, 3_000.0),  # uses new anchor $80
        ],
        sale_date=date(2027, 6, 1),
        sale_price=200.0,
    )
    result = calculate_multi_purchase_espp(inputs)

    # Reset happened at purchase 2 (date 2024-12-31)
    assert result.reset_dates == [date(2024, 12, 31)]

    pe1, pe2, pe3, pe4 = result.purchase_events

    # Purchase 1: anchor stays at offering start $100, no reset
    assert pe1.effective_anchor_fmv == pytest.approx(100.0)
    assert not pe1.reset_occurred
    assert pe1.purchase_price == pytest.approx(85.0)  # $100 × 0.85

    # Purchase 2: RESET — anchor moves to ($80, 2024-12-31)
    assert pe2.reset_occurred
    assert pe2.effective_anchor_fmv == pytest.approx(80.0)
    assert pe2.effective_anchor_date == date(2024, 12, 31)
    # After reset, reference FMV = min($80, $80) = $80; purchase price = $80 × 0.85 = $68
    assert pe2.purchase_price == pytest.approx(68.0)

    # Purchase 3: anchor remains at $80 (no further drop)
    assert not pe3.reset_occurred
    assert pe3.effective_anchor_fmv == pytest.approx(80.0)
    # Reference FMV = min($80, $110) = $80; purchase price = $68
    assert pe3.purchase_price == pytest.approx(68.0)

    # Purchase 4: same anchor, same purchase price
    assert pe4.effective_anchor_fmv == pytest.approx(80.0)
    assert pe4.purchase_price == pytest.approx(68.0)


def test_multi_purchase_cascading_resets():
    """Multiple drops cascade — anchor moves at each new low."""
    inputs = ESPPMultiInputs(
        offering_start_date=date(2024, 1, 1),
        offering_start_fmv=100.0,
        discount_pct=0.15,
        has_lookback=True,
        has_reset=True,
        purchases=[
            PurchaseInput(date(2024, 6, 30), 80.0, 1_000.0),  # RESET to $80
            PurchaseInput(date(2024, 12, 31), 60.0, 1_000.0),  # RESET to $60
            PurchaseInput(date(2025, 6, 30), 50.0, 1_000.0),  # RESET to $50
            PurchaseInput(date(2025, 12, 31), 70.0, 1_000.0),  # no reset, anchor $50
        ],
        sale_date=date(2028, 6, 1),
        sale_price=200.0,
    )
    result = calculate_multi_purchase_espp(inputs)

    # 3 resets in a row, then purchase 4 holds at $50 anchor
    assert result.reset_dates == [
        date(2024, 6, 30),
        date(2024, 12, 31),
        date(2025, 6, 30),
    ]

    pe1, pe2, pe3, pe4 = result.purchase_events
    assert pe1.effective_anchor_fmv == pytest.approx(80.0)
    assert pe2.effective_anchor_fmv == pytest.approx(60.0)
    assert pe3.effective_anchor_fmv == pytest.approx(50.0)
    assert pe4.effective_anchor_fmv == pytest.approx(50.0)  # held at low


def test_user_calendar_year_25k_limit_scenario():
    """User's exact scenario: Feb 2026 + Aug 2026 share $25K limit for 2026.

    Aug 2025: $5,000 contributions → ~58.8 shares × $100 anchor = $5,882 in 2025
    Feb 2026: $15,000 contributions → ~176.5 shares × $100 anchor = $17,647 in 2026
    Aug 2026: would buy ~176.5 shares, but 2026 has only $7,353 of headroom
              → capped at 73.53 shares (× $100 = $7,353)
              → 102.94 shares refunded × $85 purchase price = $8,750 returned
    """
    inputs = ESPPMultiInputs(
        offering_start_date=date(2025, 3, 1),
        offering_start_fmv=100.0,
        discount_pct=0.15,
        has_lookback=True,
        has_reset=False,  # turn off reset to focus on calendar-year limit
        purchases=[
            PurchaseInput(date(2025, 8, 31), 100.0, 5_000.0),
            PurchaseInput(date(2026, 2, 28), 100.0, 15_000.0),
            PurchaseInput(date(2026, 8, 31), 100.0, 15_000.0),
        ],
        sale_date=date(2028, 6, 1),
        sale_price=150.0,
    )
    result = calculate_multi_purchase_espp(inputs)

    # Calendar-year usage
    assert result.ytd_fmv_usage[2025] == pytest.approx(5_000.0 / 85.0 * 100.0)
    assert result.ytd_fmv_usage[2026] == pytest.approx(25_000.0)  # capped at limit

    # Per-purchase verification
    pe1, pe2, pe3 = result.purchase_events
    assert pe1.shares_purchased == pytest.approx(5_000.0 / 85.0)  # ~58.82
    assert pe1.excess_contributions_refunded == pytest.approx(0.0)

    assert pe2.shares_purchased == pytest.approx(15_000.0 / 85.0)  # ~176.47
    assert pe2.excess_contributions_refunded == pytest.approx(0.0)

    # Purchase 3: capped
    available_for_3 = 25_000.0 - pe2.ytd_fmv_used_after
    expected_max_shares_3 = available_for_3 / 100.0
    assert pe3.shares_purchased == pytest.approx(expected_max_shares_3)
    requested_3 = 15_000.0 / 85.0
    assert pe3.shares_requested == pytest.approx(requested_3)
    assert pe3.excess_contributions_refunded == pytest.approx(
        (requested_3 - expected_max_shares_3) * 85.0
    )


def test_multi_purchase_no_reset_when_disabled():
    """If has_reset=False, anchor never moves even on price drops."""
    inputs = ESPPMultiInputs(
        offering_start_date=date(2024, 1, 1),
        offering_start_fmv=100.0,
        discount_pct=0.15,
        has_lookback=True,
        has_reset=False,
        purchases=[
            PurchaseInput(date(2024, 6, 30), 60.0, 1_000.0),  # drop, but no reset
            PurchaseInput(date(2024, 12, 31), 50.0, 1_000.0),  # drop, but no reset
        ],
        sale_date=date(2027, 6, 1),
        sale_price=200.0,
    )
    result = calculate_multi_purchase_espp(inputs)

    assert result.reset_dates == []
    for pe in result.purchase_events:
        assert pe.effective_anchor_fmv == pytest.approx(100.0)
        assert not pe.reset_occurred
    # But look-back STILL picks min(anchor, purchase) for the reference FMV
    pe1, pe2 = result.purchase_events
    assert pe1.reference_fmv == pytest.approx(60.0)  # = min(100, 60)
    assert pe1.purchase_price == pytest.approx(60.0 * 0.85)
    assert pe2.reference_fmv == pytest.approx(50.0)  # = min(100, 50)
    assert pe2.purchase_price == pytest.approx(50.0 * 0.85)


def test_multi_purchase_mixed_dispositions():
    """Lots with different anchor dates get different QD/DD outcomes at same sale.

    Pre-reset lots have anchor = Jan 2023 (long enough for QD by sale).
    Post-reset lots have anchor = Jan 2025 (too recent for 2-yr rule → DD).
    """
    inputs = ESPPMultiInputs(
        offering_start_date=date(2023, 1, 1),
        offering_start_fmv=100.0,
        discount_pct=0.15,
        has_lookback=True,
        has_reset=True,
        purchases=[
            PurchaseInput(date(2023, 7, 1), 120.0, 1_000.0),  # anchor stays Jan 2023
            PurchaseInput(date(2024, 1, 1), 150.0, 1_000.0),  # anchor stays Jan 2023
            PurchaseInput(date(2025, 1, 1), 50.0, 1_000.0),  # RESET to Jan 2025, $50
            PurchaseInput(date(2025, 7, 1), 80.0, 1_000.0),  # anchor stays Jan 2025
        ],
        sale_date=date(2026, 3, 1),
        sale_price=200.0,
    )
    result = calculate_multi_purchase_espp(inputs)

    # Reset happened at purchase 3
    assert result.reset_dates == [date(2025, 1, 1)]

    # Per-lot dispositions
    lots = result.lot_dispositions
    # Lot 1 (purchase Jul 2023, anchor Jan 2023): held > 2 yr from anchor, > 1 yr from purchase → QD
    assert lots[0].disposition == "QD"
    # Lot 2 (purchase Jan 2024, anchor Jan 2023): > 2 yr from anchor, > 1 yr from purchase → QD
    assert lots[1].disposition == "QD"
    # Lot 3 (purchase Jan 2025, anchor Jan 2025): only ~14 months from anchor, ~14 from purchase → DD
    assert lots[2].disposition == "DD"
    # Lot 4 (purchase Jul 2025, anchor Jan 2025): only ~8 months → DD
    assert lots[3].disposition == "DD"

    # Aggregated total should equal sum of per-lot
    sum_oi = sum(lot.ordinary_income for lot in lots)
    sum_cg = sum(lot.capital_gain for lot in lots)
    sum_cl = sum(lot.capital_loss for lot in lots)
    assert result.total_ordinary_income == pytest.approx(sum_oi)
    assert result.total_capital_gain == pytest.approx(sum_cg)
    assert result.total_capital_loss == pytest.approx(sum_cl)


def test_multi_purchase_n1_matches_single_purchase_qd():
    """N=1 multi-purchase should yield same outcome as single-purchase function.

    Regression check that the two functions agree on the simple single-purchase case.
    """
    common = dict(
        offering_start_fmv=100.0,
        purchase_fmv=150.0,
        discount_pct=0.15,
        has_lookback=True,
        offering_start_date=date(2022, 1, 1),
        purchase_date=date(2022, 6, 30),
        sale_date=date(2025, 8, 1),
        sale_price=200.0,
        contributions=1_700.0,
    )
    single_result = calculate_espp_purchase(ESPPInputs(**common))

    multi_result = calculate_multi_purchase_espp(
        ESPPMultiInputs(
            offering_start_date=common["offering_start_date"],
            offering_start_fmv=common["offering_start_fmv"],
            discount_pct=common["discount_pct"],
            has_lookback=common["has_lookback"],
            has_reset=False,
            purchases=[
                PurchaseInput(
                    common["purchase_date"],
                    common["purchase_fmv"],
                    common["contributions"],
                ),
            ],
            sale_date=common["sale_date"],
            sale_price=common["sale_price"],
        )
    )

    # Both should reach QD with same ordinary income + capital gain
    assert single_result.disposition == "QD"
    assert multi_result.lot_dispositions[0].disposition == "QD"
    assert multi_result.total_ordinary_income == pytest.approx(
        single_result.qd_ordinary_income
    )
    assert multi_result.total_capital_gain == pytest.approx(
        single_result.qd_capital_gain
    )
