"""Rule 701 Sizing Calculator.

Rule 701 (Securities Act of 1933, adopted under §3(b)) is the federal exemption
private companies rely on to issue compensatory equity without registering. This
module sizes an issuer's remaining Rule 701 capacity and flags the two things
that actually bite in practice: the 12-month cap and the $10M disclosure trigger.

Key mechanics modeled
---------------------
1. **Availability (Rule 701(b))** — the exemption is only for issuers NOT subject
   to Exchange Act §13 or §15(d) reporting. A public company must use Form S-8.

2. **The 12-month cap (Rule 701(d)(2))** — aggregate sales price *or* amount of
   securities sold in reliance on Rule 701 during **any consecutive 12-month
   period** may not exceed the greatest of:
     (i)   $1,000,000;
     (ii)  15% of the issuer's total assets; or
     (iii) 15% of the outstanding amount of the class being offered.
   Tests (i) and (ii) are dollar-denominated; (iii) is share-denominated. Because
   the rule says "aggregate sales price **or** amount of securities," an issuer is
   within the cap if it satisfies *either* the dollar test or the share test. Both
   (ii) and (iii) are measured at the most recent annual balance sheet date.

3. **Rolling windows, not calendar years.** The rule says "any consecutive
   12-month period." A plan can pass a calendar-year test and still blow a
   rolling window. This module checks a window ending at every issuance date.

4. **Options are counted at GRANT, on the exercise price (Rule 701(d)(3)(ii)).**
   Not at exercise, and not at FMV. This is the mechanic most people get wrong:
   an option grant consumes capacity the day it is granted, forever, whether or
   not it is ever exercised.

5. **$10M disclosure trigger (Rule 701(e))** — if aggregate sales price in any
   consecutive 12-month period exceeds $10,000,000, the issuer must deliver plan
   documents, risk factors and financial statements to recipients a reasonable
   period before sale. (Raised from $5M by the Economic Growth, Regulatory Relief
   and Consumer Protection Act of 2018.)

Not modeled — deliberately
--------------------------
- **State Blue Sky compliance.** Rule 701 is a *federal* exemption only. NSMIA
  does not preempt state law for private-company issuances, so a separate
  exemption is needed in every state where a recipient resides.
- **Rule 144 resale mechanics.** Rule 701 shares are restricted securities.
- Consultant/advisor eligibility conditions beyond the natural-person test.

All amounts in USD. Dates use datetime.date.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, Optional

# Rule 701(d)(2)(i) — dollar floor
CAP_FLOOR = 1_000_000.0
# Rule 701(d)(2)(ii) / (iii) — percentage tests
CAP_PCT = 0.15
# Rule 701(e) — enhanced disclosure trigger
DISCLOSURE_THRESHOLD = 10_000_000.0

IssuanceType = Literal["OPTION", "RSA", "RSU", "DIRECT_SALE"]


# ---------------------------------------------------------------------------
# Input containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Issuance:
    """A single compensatory issuance made in reliance on Rule 701."""

    issuance_date: date
    issuance_type: IssuanceType
    shares: int
    # Exercise price for OPTION; purchase price for RSA / DIRECT_SALE; ignored for RSU
    price_per_share: float
    # Used to value RSUs (no exercise price); informational for other types
    fmv_per_share: float
    recipient_label: str = ""


@dataclass(frozen=True)
class Rule701Inputs:
    """Issuer profile plus the issuances to test."""

    is_reporting_company: bool
    total_assets: float
    outstanding_shares_of_class: int
    balance_sheet_date: date
    issuances: tuple[Issuance, ...]
    # Window endpoint to report on. Defaults to the latest issuance date.
    measurement_date: Optional[date] = None


# ---------------------------------------------------------------------------
# Output containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValuedIssuance:
    """An issuance with its Rule 701 'aggregate sales price' resolved."""

    issuance: Issuance
    sales_price: float
    valuation_basis: str  # human-readable explanation of how it was counted


@dataclass(frozen=True)
class WindowCheck:
    """Compliance state for one consecutive 12-month window."""

    window_start: date
    window_end: date
    aggregate_sales_price: float
    aggregate_shares: int
    within_dollar_cap: bool
    within_share_cap: bool
    is_compliant: bool
    disclosure_triggered: bool


@dataclass(frozen=True)
class Rule701Outputs:
    """Sizing results for the measurement window, plus every rolling window."""

    # Availability
    exemption_available: bool
    unavailable_reason: Optional[str]

    # Capacity (Rule 701(d)(2))
    cap_floor: float
    cap_15pct_assets: float
    dollar_capacity: float
    governing_dollar_test: str
    share_capacity: int

    # Measurement window
    window_start: date
    window_end: date
    aggregate_sales_price: float
    aggregate_shares: int
    dollar_headroom: float
    share_headroom: int
    is_compliant: bool
    compliant_via: Optional[str]

    # Disclosure (Rule 701(e))
    disclosure_threshold: float
    disclosure_triggered: bool
    disclosure_trigger_date: Optional[date]
    amount_over_disclosure_threshold: float

    # Detail
    valued_issuances: tuple[ValuedIssuance, ...]
    window_checks: tuple[WindowCheck, ...]
    worst_window: Optional[WindowCheck]
    balance_sheet_is_stale: bool
    warnings: tuple[str, ...]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _twelve_months_before(d: date) -> date:
    """The exclusive lower bound of a consecutive 12-month period ending at `d`."""
    from dateutil.relativedelta import relativedelta

    return d - relativedelta(months=12)


def value_issuance(issuance: Issuance) -> ValuedIssuance:
    """Resolve the Rule 701 'aggregate sales price' for a single issuance.

    Per Rule 701(d)(3)(ii), an option is counted at the time of GRANT using the
    EXERCISE price — not at exercise, and not at fair market value. RSUs carry no
    exercise price, so they are valued at grant-date FMV. Restricted stock awards
    and direct sales are counted at the consideration actually received, which is
    why a founder RSA priced at $0.0001 consumes almost no dollar capacity while
    still consuming full share capacity.
    """
    if issuance.issuance_type == "OPTION":
        price = issuance.shares * issuance.price_per_share
        basis = (
            f"Rule 701(d)(3)(ii): counted at grant on the ${issuance.price_per_share:,.4f} "
            f"exercise price, not at exercise"
        )
    elif issuance.issuance_type == "RSU":
        price = issuance.shares * issuance.fmv_per_share
        basis = (
            f"No exercise price — valued at grant-date FMV of "
            f"${issuance.fmv_per_share:,.4f}"
        )
    else:  # RSA, DIRECT_SALE
        price = issuance.shares * issuance.price_per_share
        basis = (
            f"Consideration received: ${issuance.price_per_share:,.4f} per share"
        )
    return ValuedIssuance(issuance=issuance, sales_price=price, valuation_basis=basis)


def _check_window(
    valued: tuple[ValuedIssuance, ...],
    window_end: date,
    dollar_capacity: float,
    share_capacity: int,
) -> WindowCheck:
    """Evaluate the consecutive 12-month period ending at `window_end`."""
    lower = _twelve_months_before(window_end)
    inside = [
        v for v in valued if lower < v.issuance.issuance_date <= window_end
    ]
    agg_price = sum(v.sales_price for v in inside)
    agg_shares = sum(v.issuance.shares for v in inside)

    within_dollar = agg_price <= dollar_capacity
    within_share = agg_shares <= share_capacity

    return WindowCheck(
        window_start=lower,
        window_end=window_end,
        aggregate_sales_price=agg_price,
        aggregate_shares=agg_shares,
        within_dollar_cap=within_dollar,
        within_share_cap=within_share,
        # "aggregate sales price OR amount of securities" — either test carries it
        is_compliant=within_dollar or within_share,
        disclosure_triggered=agg_price > DISCLOSURE_THRESHOLD,
    )


# ---------------------------------------------------------------------------
# Core calculation
# ---------------------------------------------------------------------------


def calculate_rule701_capacity(inputs: Rule701Inputs) -> Rule701Outputs:
    """Size Rule 701 capacity and test every consecutive 12-month window."""

    warnings: list[str] = []

    # --- Capacity, Rule 701(d)(2) ---
    cap_15pct_assets = inputs.total_assets * CAP_PCT
    dollar_capacity = max(CAP_FLOOR, cap_15pct_assets)
    governing_dollar_test = (
        "15% of total assets"
        if cap_15pct_assets > CAP_FLOOR
        else "$1,000,000 floor"
    )
    share_capacity = int(inputs.outstanding_shares_of_class * CAP_PCT)

    # --- Value every issuance ---
    valued = tuple(value_issuance(i) for i in inputs.issuances)

    # --- Determine the measurement window endpoint ---
    if inputs.measurement_date is not None:
        window_end = inputs.measurement_date
    elif valued:
        window_end = max(v.issuance.issuance_date for v in valued)
    else:
        window_end = inputs.balance_sheet_date

    # --- Test a window ending at every issuance date, plus the measurement date ---
    endpoints = sorted({v.issuance.issuance_date for v in valued} | {window_end})
    window_checks = tuple(
        _check_window(valued, e, dollar_capacity, share_capacity) for e in endpoints
    )

    current = _check_window(valued, window_end, dollar_capacity, share_capacity)

    # Worst window = any breach; otherwise the one closest to the dollar cap
    breaches = [w for w in window_checks if not w.is_compliant]
    if breaches:
        worst = max(breaches, key=lambda w: w.aggregate_sales_price)
    elif window_checks:
        worst = max(window_checks, key=lambda w: w.aggregate_sales_price)
    else:
        worst = None

    # --- Disclosure trigger, Rule 701(e) ---
    triggered_windows = [w for w in window_checks if w.disclosure_triggered]
    disclosure_triggered = bool(triggered_windows)
    disclosure_trigger_date = (
        min(w.window_end for w in triggered_windows) if triggered_windows else None
    )
    amount_over = max(0.0, current.aggregate_sales_price - DISCLOSURE_THRESHOLD)

    # --- Which test carries the current window ---
    if current.within_dollar_cap and current.within_share_cap:
        compliant_via = "both the dollar test and the share test"
    elif current.within_dollar_cap:
        compliant_via = f"the dollar test ({governing_dollar_test})"
    elif current.within_share_cap:
        compliant_via = "the share test (15% of outstanding)"
    else:
        compliant_via = None

    # --- Availability, Rule 701(b) ---
    exemption_available = not inputs.is_reporting_company
    unavailable_reason = (
        "Rule 701 is available only to issuers NOT subject to Exchange Act §13 or "
        "§15(d) reporting. A reporting company must register plan shares on Form S-8."
        if inputs.is_reporting_company
        else None
    )

    # --- Balance sheet staleness ---
    stale_cutoff = _twelve_months_before(window_end)
    balance_sheet_is_stale = inputs.balance_sheet_date < stale_cutoff
    if balance_sheet_is_stale:
        warnings.append(
            f"Balance sheet date ({inputs.balance_sheet_date.isoformat()}) is more than "
            f"12 months before the measurement date. Both percentage tests are measured "
            f"at the most recent annual balance sheet date — refresh before relying on them."
        )

    if not exemption_available:
        warnings.append(unavailable_reason or "")

    if disclosure_triggered:
        warnings.append(
            "Rule 701(e) enhanced disclosure is triggered: deliver the plan, risk factors "
            "and financial statements to recipients a reasonable period before sale."
        )

    if breaches:
        warnings.append(
            f"{len(breaches)} rolling 12-month window(s) exceed the cap. The rule tests "
            f"ANY consecutive 12-month period, not the calendar year."
        )

    warnings.append(
        "Rule 701 is a federal exemption only. State Blue Sky exemptions are still "
        "required in every state where a recipient resides — NSMIA does not preempt "
        "state law for private-company issuances."
    )

    return Rule701Outputs(
        exemption_available=exemption_available,
        unavailable_reason=unavailable_reason,
        cap_floor=CAP_FLOOR,
        cap_15pct_assets=cap_15pct_assets,
        dollar_capacity=dollar_capacity,
        governing_dollar_test=governing_dollar_test,
        share_capacity=share_capacity,
        window_start=current.window_start,
        window_end=current.window_end,
        aggregate_sales_price=current.aggregate_sales_price,
        aggregate_shares=current.aggregate_shares,
        dollar_headroom=dollar_capacity - current.aggregate_sales_price,
        share_headroom=share_capacity - current.aggregate_shares,
        is_compliant=current.is_compliant,
        compliant_via=compliant_via,
        disclosure_threshold=DISCLOSURE_THRESHOLD,
        disclosure_triggered=disclosure_triggered,
        disclosure_trigger_date=disclosure_trigger_date,
        amount_over_disclosure_threshold=amount_over,
        valued_issuances=valued,
        window_checks=window_checks,
        worst_window=worst,
        balance_sheet_is_stale=balance_sheet_is_stale,
        warnings=tuple(w for w in warnings if w),
    )


def max_additional_option_grant(
    inputs: Rule701Inputs, exercise_price: float
) -> Optional[int]:
    """How many more option shares can be granted today without breaching the cap.

    Returns None if the exercise price is non-positive (no dollar cost, so the
    share test alone governs) or if the issuer is already over the cap.
    """
    if exercise_price <= 0:
        return None

    result = calculate_rule701_capacity(inputs)
    if not result.is_compliant:
        return 0

    by_dollar = int(max(0.0, result.dollar_headroom) / exercise_price)
    by_share = max(0, result.share_headroom)
    # Either test can carry the window, so take the more permissive one.
    return max(by_dollar, by_share)
