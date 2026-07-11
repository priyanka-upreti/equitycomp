"""Unit tests for §16 Form 4 compliance tracker."""

from datetime import date

import pytest

from lib.section16_tracker import (
    Section16Inputs,
    Transaction,
    add_business_days,
    analyze_section16,
    count_business_days_between,
    is_within_short_swing_window,
)


# ---------------------------------------------------------------------------
# Business day helpers
# ---------------------------------------------------------------------------


def test_add_business_days_from_monday():
    """Mon Jan 5 2026 + 2 business days = Wed Jan 7."""
    assert add_business_days(date(2026, 1, 5), 2) == date(2026, 1, 7)


def test_add_business_days_from_friday_skips_weekend():
    """Fri Jan 2 2026 + 2 business days = Tue Jan 6 (skips Sat + Sun)."""
    assert add_business_days(date(2026, 1, 2), 2) == date(2026, 1, 6)


def test_add_business_days_from_thursday_partial_skip():
    """Thu Jan 1 2026 + 2 business days = Mon Jan 5 (Fri = 1, skip weekend, Mon = 2)."""
    assert add_business_days(date(2026, 1, 1), 2) == date(2026, 1, 5)


def test_count_business_days_between_same_week():
    """Mon → Fri = 4 business days."""
    assert count_business_days_between(date(2026, 1, 5), date(2026, 1, 9)) == 4


def test_count_business_days_between_across_weekend():
    """Fri → next Tue = 2 business days (weekend skipped)."""
    assert count_business_days_between(date(2026, 1, 2), date(2026, 1, 6)) == 2


# ---------------------------------------------------------------------------
# Short-swing window (less-than-6-months rule)
# ---------------------------------------------------------------------------


def test_short_swing_window_within_6_months():
    """Jan 1 → June 30 is within 6 months."""
    assert is_within_short_swing_window(date(2026, 1, 1), date(2026, 6, 30))


def test_short_swing_window_exactly_6_months_not_within():
    """Jan 1 → July 1 is exactly 6 months — NOT within (strict inequality)."""
    assert not is_within_short_swing_window(date(2026, 1, 1), date(2026, 7, 1))


def test_short_swing_window_more_than_6_months_not_within():
    """Jan 1 → July 15 is > 6 months — not within."""
    assert not is_within_short_swing_window(date(2026, 1, 1), date(2026, 7, 15))


def test_short_swing_window_month_end_edge_case():
    """Aug 31 + 6 months = Feb 28 (or 29). Aug 31 → Feb 28 is exactly 6 months."""
    # Aug 31, 2025 + 6 months = Feb 28, 2026 (2026 is not a leap year in this system... check: 2026 % 4 = 2, not leap)
    # So Feb 28 is the correct rollover. Feb 28 is NOT within (exactly 6 months).
    assert not is_within_short_swing_window(date(2025, 8, 31), date(2026, 2, 28))
    # Feb 27 IS within
    assert is_within_short_swing_window(date(2025, 8, 31), date(2026, 2, 27))


# ---------------------------------------------------------------------------
# Form 3 + Form 4 deadlines
# ---------------------------------------------------------------------------


def test_form3_deadline_10_calendar_days():
    """Insider start Jan 15 → Form 3 due Jan 25."""
    inputs = Section16Inputs(
        insider_role="officer",
        insider_start_date=date(2026, 1, 15),
        company_ticker="ACME",
        transactions=[],
        as_of_date=date(2026, 1, 20),
    )
    result = analyze_section16(inputs)

    assert result.form3_deadline == date(2026, 1, 25)
    assert result.form3_days_remaining == 5
    assert not result.form3_is_overdue


def test_form3_overdue_after_deadline():
    """As-of date past deadline → overdue."""
    inputs = Section16Inputs(
        insider_role="director",
        insider_start_date=date(2026, 1, 1),
        company_ticker="ACME",
        transactions=[],
        as_of_date=date(2026, 2, 1),
    )
    result = analyze_section16(inputs)
    assert result.form3_is_overdue
    assert result.form3_days_remaining < 0


def test_form4_deadline_two_business_days():
    """Transaction on Mon → Form 4 due Wed (2 business days)."""
    txn = Transaction(
        date=date(2026, 3, 2),  # Monday
        transaction_type="buy",
        shares=1_000,
        price_per_share=50.0,
        is_16b3_exempt=False,
    )
    inputs = Section16Inputs(
        insider_role="officer",
        insider_start_date=date(2026, 1, 1),
        company_ticker="ACME",
        transactions=[txn],
        as_of_date=date(2026, 3, 3),  # Tuesday, before Wed deadline
    )
    result = analyze_section16(inputs)

    assert result.form4_filings[0].deadline == date(2026, 3, 4)  # Wed
    assert not result.form4_filings[0].is_overdue


def test_form4_overdue_when_deadline_passed():
    """As-of well past deadline → overdue."""
    txn = Transaction(
        date=date(2026, 3, 2),
        transaction_type="sell",
        shares=500,
        price_per_share=100.0,
        is_16b3_exempt=False,
    )
    inputs = Section16Inputs(
        insider_role="officer",
        insider_start_date=date(2026, 1, 1),
        company_ticker="ACME",
        transactions=[txn],
        as_of_date=date(2026, 3, 10),  # week past deadline
    )
    result = analyze_section16(inputs)

    assert result.form4_filings[0].is_overdue
    assert result.overdue_form4_count == 1


# ---------------------------------------------------------------------------
# §16(b) short-swing matching
# ---------------------------------------------------------------------------


def test_short_swing_basic_pair_recovers_profit():
    """Buy $50, sell $80 within 3 months → recoverable profit."""
    inputs = Section16Inputs(
        insider_role="officer",
        insider_start_date=date(2026, 1, 1),
        company_ticker="ACME",
        transactions=[
            Transaction(date(2026, 3, 1), "buy", 1_000, 50.0, False),
            Transaction(date(2026, 5, 1), "sell", 1_000, 80.0, False),
        ],
        as_of_date=date(2026, 5, 10),
    )
    result = analyze_section16(inputs)

    assert len(result.short_swing_pairs) == 1
    assert result.short_swing_pairs[0].matched_shares == 1_000
    assert result.short_swing_pairs[0].profit_per_share == pytest.approx(30.0)
    assert result.total_recoverable_profit == pytest.approx(30_000.0)


def test_short_swing_outside_window_no_recovery():
    """Buy and sell > 6 months apart → no §16(b) match."""
    inputs = Section16Inputs(
        insider_role="officer",
        insider_start_date=date(2026, 1, 1),
        company_ticker="ACME",
        transactions=[
            Transaction(date(2026, 1, 1), "buy", 1_000, 50.0, False),
            Transaction(date(2026, 9, 1), "sell", 1_000, 80.0, False),  # 8 months later
        ],
        as_of_date=date(2026, 10, 1),
    )
    result = analyze_section16(inputs)

    assert len(result.short_swing_pairs) == 0
    assert result.total_recoverable_profit == pytest.approx(0.0)


def test_short_swing_16b3_exempt_grant_not_matched():
    """Grant flagged as Rule 16b-3 exempt → no match even if a sale follows."""
    inputs = Section16Inputs(
        insider_role="officer",
        insider_start_date=date(2026, 1, 1),
        company_ticker="ACME",
        transactions=[
            Transaction(date(2026, 3, 1), "grant", 1_000, 0.0, True),  # exempt grant
            Transaction(date(2026, 5, 1), "sell", 1_000, 80.0, False),
        ],
        as_of_date=date(2026, 5, 10),
    )
    result = analyze_section16(inputs)

    # No pair — the exempt grant doesn't get matched
    assert len(result.short_swing_pairs) == 0


def test_short_swing_sale_below_purchase_no_profit():
    """Sale price below purchase price → no profit → no match."""
    inputs = Section16Inputs(
        insider_role="officer",
        insider_start_date=date(2026, 1, 1),
        company_ticker="ACME",
        transactions=[
            Transaction(date(2026, 3, 1), "buy", 1_000, 100.0, False),
            Transaction(date(2026, 5, 1), "sell", 1_000, 80.0, False),  # loss
        ],
        as_of_date=date(2026, 5, 10),
    )
    result = analyze_section16(inputs)

    assert len(result.short_swing_pairs) == 0
    assert result.total_recoverable_profit == pytest.approx(0.0)


def test_short_swing_maximizes_profit_multiple_purchases():
    """Multiple purchases → cheapest purchase paired with sale (max profit).

    Buy 500 @ $50 + buy 500 @ $80, then sell 500 @ $100 within 3 months.
    Should match: $50 buy → $100 sell = $25K profit (not $80 → $100 = $10K).
    """
    inputs = Section16Inputs(
        insider_role="officer",
        insider_start_date=date(2026, 1, 1),
        company_ticker="ACME",
        transactions=[
            Transaction(date(2026, 2, 1), "buy", 500, 50.0, False),
            Transaction(date(2026, 3, 1), "buy", 500, 80.0, False),
            Transaction(date(2026, 4, 1), "sell", 500, 100.0, False),
        ],
        as_of_date=date(2026, 5, 1),
    )
    result = analyze_section16(inputs)

    # Should match cheapest buy ($50) with sale ($100)
    assert len(result.short_swing_pairs) == 1
    matched = result.short_swing_pairs[0]
    assert matched.purchase.price_per_share == pytest.approx(50.0)
    assert matched.matched_shares == 500
    assert matched.recoverable_profit == pytest.approx(25_000.0)  # 500 × $50


def test_short_swing_sale_before_purchase_still_matches():
    """Sale-then-purchase within 6 months also triggers §16(b) matching."""
    inputs = Section16Inputs(
        insider_role="officer",
        insider_start_date=date(2026, 1, 1),
        company_ticker="ACME",
        transactions=[
            Transaction(date(2026, 3, 1), "sell", 500, 100.0, False),
            Transaction(date(2026, 5, 1), "buy", 500, 60.0, False),  # buy later, lower
        ],
        as_of_date=date(2026, 6, 1),
    )
    result = analyze_section16(inputs)

    # Sale @ $100 vs later purchase @ $60 → profit is (100 − 60) × 500 = $20K
    assert len(result.short_swing_pairs) == 1
    assert result.total_recoverable_profit == pytest.approx(20_000.0)


def test_no_transactions_no_form4_no_short_swing():
    """No transactions → no Form 4 filings, no short-swing pairs."""
    inputs = Section16Inputs(
        insider_role="director",
        insider_start_date=date(2026, 1, 1),
        company_ticker="ACME",
        transactions=[],
        as_of_date=date(2026, 3, 1),
    )
    result = analyze_section16(inputs)

    assert result.form4_filings == []
    assert result.overdue_form4_count == 0
    assert result.short_swing_pairs == []
    assert result.total_recoverable_profit == pytest.approx(0.0)
