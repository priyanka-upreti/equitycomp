"""§16 Form 4 Compliance Tracker.

Models compliance with §16(a) reporting deadlines and §16(b) short-swing
profit exposure for insiders (officers, directors, 10% shareholders) of
publicly-traded companies.

Key mechanics:
- Form 3: Initial statement of ownership. Due 10 CALENDAR days after becoming insider.
- Form 4: Statement of changes. Due 2 BUSINESS days after each transaction.
- §16(b) short-swing rule: strict-liability disgorgement of profits from any
  purchase-sale (or sale-purchase) pair within LESS THAN 6 months. Rule 16b-3
  exempts grants/exercises/vests from an approved employee benefit plan.

For V1: business-day math skips weekends only (federal holidays deferred).
Short-swing pairing uses the profit-maximizing SEC method (lowest-cost purchases
matched to highest-price sales).

All amounts in USD. Dates use datetime.date.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal, Optional


# ---------------------------------------------------------------------------
# Input containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Transaction:
    """A single §16-relevant transaction."""

    date: date
    transaction_type: Literal["buy", "sell", "grant", "exercise", "vest", "gift"]
    shares: int
    price_per_share: float
    is_16b3_exempt: bool  # e.g., grants from approved comp plan (Rule 16b-3)
    description: str = ""


@dataclass(frozen=True)
class Section16Inputs:
    """Inputs for the §16 compliance analysis."""

    insider_role: Literal["officer", "director", "ten_percent_holder"]
    insider_start_date: date  # when became a §16 insider (for Form 3 deadline)
    company_ticker: str
    transactions: list[Transaction]
    as_of_date: date  # used to evaluate deadlines


# ---------------------------------------------------------------------------
# Output containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Form4Filing:
    """Form 4 deadline analysis for a single transaction.

    Pre-insider transactions (dated before insider_start_date) have no Form 4
    obligation — deadline + days_until are None and is_pre_insider is True.
    They still may appear in §16(b) short-swing matching for officers/directors.
    """

    transaction: Transaction
    deadline: Optional[date]  # None if pre-insider
    days_until_deadline: Optional[int]  # None if pre-insider
    is_overdue: bool  # always False if pre-insider
    is_pre_insider: bool  # True if transaction date < insider_start_date


@dataclass(frozen=True)
class ShortSwingPair:
    """A §16(b) matched pair — potential recoverable profit."""

    purchase: Transaction
    sale: Transaction
    days_between: int
    matched_shares: int
    profit_per_share: float
    recoverable_profit: float


@dataclass(frozen=True)
class Section16Outputs:
    """§16 compliance outputs."""

    # Form 3
    form3_deadline: date  # insider_start + 10 calendar days
    form3_days_remaining: int  # negative if overdue
    form3_is_overdue: bool

    # Form 4
    form4_filings: list[Form4Filing]
    overdue_form4_count: int
    upcoming_form4_count: int  # due within next 2 business days

    # §16(b) short-swing exposure
    short_swing_pairs: list[ShortSwingPair]
    total_recoverable_profit: float


# ---------------------------------------------------------------------------
# Business-day helpers
# ---------------------------------------------------------------------------


def add_business_days(start: date, business_days: int) -> date:
    """Add N business days to a start date, skipping weekends.

    Federal holidays are NOT excluded in V1 — that's a deferred feature.
    """
    current = start
    added = 0
    while added < business_days:
        current = current + timedelta(days=1)
        if current.weekday() < 5:  # Monday=0 … Friday=4
            added += 1
    return current


def count_business_days_between(start: date, end: date) -> int:
    """Count business days between two dates (positive if end > start).

    Includes end date, excludes start date. Returns negative if end < start.
    """
    if start == end:
        return 0
    sign = 1 if end > start else -1
    if end < start:
        start, end = end, start

    current = start
    count = 0
    while current < end:
        current = current + timedelta(days=1)
        if current.weekday() < 5:
            count += 1
    return sign * count


def is_within_short_swing_window(d1: date, d2: date) -> bool:
    """Return True if two transaction dates are within a §16(b) short-swing
    window (less than 6 calendar months).

    Per §16(b): "within any period of less than six months". Uses strict
    inequality — exactly 6 months is NOT within the window.
    """
    if d1 > d2:
        d1, d2 = d2, d1

    # Add 6 months to d1 using calendar-month arithmetic
    year = d1.year
    month = d1.month + 6
    while month > 12:
        month -= 12
        year += 1

    # Handle end-of-month edge cases (e.g., Aug 31 + 6 months = Feb 28/29)
    day = d1.day
    # Try same day; if invalid (e.g., Feb 30), roll back to last day of month
    while True:
        try:
            six_months_later = date(year, month, day)
            break
        except ValueError:
            day -= 1

    return d2 < six_months_later


# ---------------------------------------------------------------------------
# Core calculation
# ---------------------------------------------------------------------------


def analyze_section16(inputs: Section16Inputs) -> Section16Outputs:
    """Perform full §16 compliance analysis on the insider's transaction history."""

    # --- Form 3 deadline (10 calendar days from insider start) ---
    form3_deadline = inputs.insider_start_date + timedelta(days=10)
    form3_days_remaining = (form3_deadline - inputs.as_of_date).days
    form3_is_overdue = form3_days_remaining < 0

    # --- Form 4 filings (2 business days from each POST-INSIDER transaction) ---
    # Pre-insider transactions have no Form 4 obligation (§16(a)(2)(C)) — reporting
    # duty starts when insider status begins.
    form4_filings: list[Form4Filing] = []
    overdue_count = 0
    upcoming_count = 0

    for txn in inputs.transactions:
        if txn.date < inputs.insider_start_date:
            # Pre-insider — no Form 4 obligation
            form4_filings.append(
                Form4Filing(
                    transaction=txn,
                    deadline=None,
                    days_until_deadline=None,
                    is_overdue=False,
                    is_pre_insider=True,
                )
            )
            continue

        deadline = add_business_days(txn.date, 2)
        days_until = count_business_days_between(inputs.as_of_date, deadline)
        is_overdue = inputs.as_of_date > deadline

        form4_filings.append(
            Form4Filing(
                transaction=txn,
                deadline=deadline,
                days_until_deadline=days_until,
                is_overdue=is_overdue,
                is_pre_insider=False,
            )
        )
        if is_overdue:
            overdue_count += 1
        elif 0 <= days_until <= 2:
            upcoming_count += 1

    # --- §16(b) short-swing matching ---
    # Only non-exempt transactions are subject to §16(b) matching.
    # Standard SEC method: pair cheapest purchases with highest sales to maximize
    # the recoverable profit (this is a "worst case for insider" match).

    non_exempt_purchases: list[dict] = []
    non_exempt_sales: list[dict] = []

    for txn in inputs.transactions:
        if txn.is_16b3_exempt:
            continue
        if txn.transaction_type in ("buy", "exercise", "vest"):
            non_exempt_purchases.append(
                {"txn": txn, "shares_remaining": txn.shares}
            )
        elif txn.transaction_type == "sell":
            non_exempt_sales.append(
                {"txn": txn, "shares_remaining": txn.shares}
            )
        # "grant" and "gift" don't count as purchase or sale for §16(b)

    # Sort: cheapest purchases first (lowest cost basis → biggest profit spread)
    non_exempt_purchases.sort(key=lambda x: x["txn"].price_per_share)
    # Sort: highest sales first (biggest profit spread)
    non_exempt_sales.sort(key=lambda x: -x["txn"].price_per_share)

    short_swing_pairs: list[ShortSwingPair] = []
    total_profit = 0.0

    for p_entry in non_exempt_purchases:
        p_txn = p_entry["txn"]
        for s_entry in non_exempt_sales:
            if p_entry["shares_remaining"] <= 0:
                break
            if s_entry["shares_remaining"] <= 0:
                continue
            s_txn = s_entry["txn"]

            # Must be within 6-month window
            if not is_within_short_swing_window(p_txn.date, s_txn.date):
                continue
            # Must be profitable (sell > buy)
            if s_txn.price_per_share <= p_txn.price_per_share:
                continue

            match_shares = min(
                p_entry["shares_remaining"], s_entry["shares_remaining"]
            )
            profit_per_share = s_txn.price_per_share - p_txn.price_per_share
            profit = match_shares * profit_per_share
            days_between = abs((s_txn.date - p_txn.date).days)

            short_swing_pairs.append(
                ShortSwingPair(
                    purchase=p_txn,
                    sale=s_txn,
                    days_between=days_between,
                    matched_shares=match_shares,
                    profit_per_share=profit_per_share,
                    recoverable_profit=profit,
                )
            )
            total_profit += profit
            p_entry["shares_remaining"] -= match_shares
            s_entry["shares_remaining"] -= match_shares

    return Section16Outputs(
        form3_deadline=form3_deadline,
        form3_days_remaining=form3_days_remaining,
        form3_is_overdue=form3_is_overdue,
        form4_filings=form4_filings,
        overdue_form4_count=overdue_count,
        upcoming_form4_count=upcoming_count,
        short_swing_pairs=short_swing_pairs,
        total_recoverable_profit=total_profit,
    )
