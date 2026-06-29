"""ESPP (§423) Calculations.

Implements purchase + tax math for qualified §423 Employee Stock Purchase Plans.

Key concepts:
- §423-qualified ESPP allows employees to purchase company stock at a discount
  (up to 15% per §423(b)(6)) with no tax at purchase (§421 nonrecognition)
- Look-back: purchase price calculated using the LOWER of offering-date FMV or
  purchase-date FMV (a powerful benefit during stock appreciation)
- $25,000 annual limit (§423(b)(8)): measured by offering-date FMV (not purchase)
- Qualifying Disposition (QD): hold > 2 yrs from offering AND > 1 yr from purchase
  → ordinary income = lesser of (offering FMV − purchase price) or (sale price − purchase price)
    per IRC §423(c)
  → capital gain on remainder = LTCG (always, since 1-yr-from-purchase requirement is met)
- Disqualifying Disposition (DD): violates either holding period
  → ordinary income = full bargain at purchase (purchase FMV − purchase price)
  → capital gain/loss on remainder; LT or ST depending on holding from purchase

All amounts are in USD. Dates use datetime.date.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal


# ---------------------------------------------------------------------------
# Input + output containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ESPPInputs:
    """Inputs for a single §423 ESPP offering + purchase + sale scenario."""

    offering_start_fmv: float  # per-share FMV at start of offering period
    purchase_fmv: float  # per-share FMV on purchase date
    discount_pct: float  # discount percentage (0.0 to 0.15 typical, max 0.15 per §423(b)(6))
    has_lookback: bool  # True if plan uses look-back to offering-date FMV
    offering_start_date: date  # start of offering period (for 2-year QD rule)
    purchase_date: date  # date shares delivered (for 1-year QD rule)
    sale_date: date  # planned or actual sale date
    sale_price: float  # per-share sale price
    contributions: float  # total $ contributed during offering period


@dataclass(frozen=True)
class ESPPOutputs:
    """Purchase mechanics + tax outcomes for the ESPP scenario."""

    # Purchase mechanics
    reference_fmv: float  # FMV used to set the discount (offering or purchase FMV)
    purchase_price_per_share: float  # actual per-share price employee pays
    shares_requested: float  # uncapped — what contributions would buy at purchase price
    shares_purchased: float  # actually purchased — capped at §423(b)(8) limit
    bargain_element_per_share: float  # purchase_fmv − purchase_price (W-2 if DD)
    total_bargain_element: float

    # §423(b)(8) $25K annual limit
    max_shares_under_25k_limit: float  # 25000 / offering_start_fmv
    is_within_25k_limit: bool  # True if shares_requested <= max (no cap triggered)
    shares_over_limit: float  # = shares_requested − shares_purchased (the excess prevented)
    excess_contributions_refunded: float  # dollars NOT used to buy shares (refunded to employee)

    # Holding period analysis
    days_from_offering_start_to_sale: int
    days_from_purchase_to_sale: int
    holds_two_years_from_offering: bool  # > 2 years
    holds_one_year_from_purchase: bool  # > 1 year
    disposition: Literal["QD", "DD"]
    qd_reason_failed: list[str]  # empty if QD; explanation if DD

    # At sale — QD outcome (§423(c) lesser-of formula)
    qd_ordinary_income: float  # per §423(c)(1) and §423(c)(2)
    qd_capital_gain: float  # always LTCG when QD (1-yr-from-purchase satisfied)
    qd_capital_loss: float  # if sale < purchase_price

    # At sale — DD outcome
    dd_ordinary_income: float  # full bargain at purchase: (purchase_fmv − purchase_price) × shares
    dd_capital_gain: float  # (sale_price − purchase_fmv) × shares, if positive
    dd_capital_loss: float  # if sale_price < purchase_fmv: capital loss
    dd_capital_gain_is_long_term: bool  # held > 1 yr from purchase


# ---------------------------------------------------------------------------
# Core calculations
# ---------------------------------------------------------------------------


def calculate_espp_purchase(inputs: ESPPInputs) -> ESPPOutputs:
    """Calculate ESPP purchase + sale outcomes under §423."""

    # --- Purchase price ---
    # With look-back: discount applies to LOWER of offering FMV or purchase FMV
    # Without look-back: discount applies to purchase FMV only
    if inputs.has_lookback:
        reference_fmv = min(inputs.offering_start_fmv, inputs.purchase_fmv)
    else:
        reference_fmv = inputs.purchase_fmv

    purchase_price = reference_fmv * (1.0 - inputs.discount_pct)

    # --- Shares requested (uncapped) ---
    shares_requested = inputs.contributions / purchase_price if purchase_price > 0 else 0.0

    # --- §423(b)(8) $25K annual limit ---
    # Limit uses OFFERING-DATE FMV (not purchase FMV, not actual purchase price).
    # Most plans CAP purchases at the limit and refund excess contributions —
    # rather than letting excess shares lose §423-qualified status.
    if inputs.offering_start_fmv > 0:
        max_shares_25k = 25_000.0 / inputs.offering_start_fmv
    else:
        max_shares_25k = 0.0

    if shares_requested > max_shares_25k:
        shares = max_shares_25k
        is_within_25k = False
        shares_over_limit = shares_requested - max_shares_25k
        excess_contributions_refunded = shares_over_limit * purchase_price
    else:
        shares = shares_requested
        is_within_25k = True
        shares_over_limit = 0.0
        excess_contributions_refunded = 0.0

    # --- Bargain element at purchase (becomes W-2 ordinary income if DD) ---
    # Uses CAPPED shares — only shares actually owned generate a bargain element.
    bargain_per_share = max(0.0, inputs.purchase_fmv - purchase_price)
    total_bargain = bargain_per_share * shares

    # --- Holding period analysis ---
    days_offering_to_sale = (inputs.sale_date - inputs.offering_start_date).days
    days_purchase_to_sale = (inputs.sale_date - inputs.purchase_date).days
    # §423(a)(1): no disposition within 2 years after grant of option (= offering start)
    # or 1 year after transfer (= purchase). QD = "more than" each window.
    holds_two_years = days_offering_to_sale > 730
    holds_one_year = days_purchase_to_sale > 365

    if holds_two_years and holds_one_year:
        disposition: Literal["QD", "DD"] = "QD"
        reasons_failed: list[str] = []
    else:
        disposition = "DD"
        reasons_failed = []
        if not holds_two_years:
            reasons_failed.append(
                f"Sold {days_offering_to_sale} days after offering start (need > 730)."
            )
        if not holds_one_year:
            reasons_failed.append(
                f"Sold {days_purchase_to_sale} days after purchase (need > 365)."
            )

    # --- QD outcome — IRC §423(c) lesser-of formula ---
    # Per §423(c):
    #   (1) offering_start_fmv − purchase_price       (the "phantom" bargain at offering)
    #   (2) sale_price − purchase_price                (the actual realized gain)
    # Ordinary income = max(0, lesser of the two)
    # NOTE: When stock APPRECIATED during the offering and look-back applies,
    #   (1) simplifies to offering_fmv × discount_pct.
    # When stock DEPRECIATED during the offering, (1) is LARGER than that —
    #   this is a common edge case the user-facing tool must handle correctly.
    qd_oi_offering_side = inputs.offering_start_fmv - purchase_price  # §423(c)(1)
    qd_oi_sale_side = inputs.sale_price - purchase_price  # §423(c)(2)

    if inputs.sale_price <= purchase_price:
        # Sold at or below purchase price — no economic gain, no ordinary income at QD
        qd_ordinary = 0.0
    else:
        qd_ordinary_per_share = max(0.0, min(qd_oi_offering_side, qd_oi_sale_side))
        qd_ordinary = qd_ordinary_per_share * shares

    # Total capital gain/loss after ordinary income absorption
    # Basis for cap gain calc = purchase_price × shares + ordinary income recognized
    qd_total_proceeds = inputs.sale_price * shares
    qd_adjusted_basis = (purchase_price * shares) + qd_ordinary
    qd_gain_or_loss = qd_total_proceeds - qd_adjusted_basis

    if qd_gain_or_loss >= 0:
        qd_cap_gain = qd_gain_or_loss
        qd_cap_loss = 0.0
    else:
        qd_cap_gain = 0.0
        qd_cap_loss = -qd_gain_or_loss

    # --- DD outcome ---
    # Ordinary income = full bargain at purchase, regardless of sale price
    dd_ordinary = total_bargain
    # Capital gain/loss = sale_price - purchase_fmv (basis stepped up via DD ordinary income)
    # Uses CAPPED shares (only shares actually owned generate gain/loss)
    dd_gain_per_share = inputs.sale_price - inputs.purchase_fmv
    dd_total_gain = dd_gain_per_share * shares

    if dd_total_gain > 0:
        dd_cap_gain = dd_total_gain
        dd_cap_loss = 0.0
    elif dd_total_gain < 0:
        dd_cap_gain = 0.0
        dd_cap_loss = -dd_total_gain
    else:
        dd_cap_gain = 0.0
        dd_cap_loss = 0.0

    dd_long_term = holds_one_year  # capital gain is LTCG if held > 1 yr from purchase

    return ESPPOutputs(
        reference_fmv=reference_fmv,
        purchase_price_per_share=purchase_price,
        shares_requested=shares_requested,
        shares_purchased=shares,
        bargain_element_per_share=bargain_per_share,
        total_bargain_element=total_bargain,
        max_shares_under_25k_limit=max_shares_25k,
        is_within_25k_limit=is_within_25k,
        shares_over_limit=shares_over_limit,
        excess_contributions_refunded=excess_contributions_refunded,
        days_from_offering_start_to_sale=days_offering_to_sale,
        days_from_purchase_to_sale=days_purchase_to_sale,
        holds_two_years_from_offering=holds_two_years,
        holds_one_year_from_purchase=holds_one_year,
        disposition=disposition,
        qd_reason_failed=reasons_failed,
        qd_ordinary_income=qd_ordinary,
        qd_capital_gain=qd_cap_gain,
        qd_capital_loss=qd_cap_loss,
        dd_ordinary_income=dd_ordinary,
        dd_capital_gain=dd_cap_gain,
        dd_capital_loss=dd_cap_loss,
        dd_capital_gain_is_long_term=dd_long_term,
    )


# ---------------------------------------------------------------------------
# Optional: marginal federal tax estimator (for planning UX)
# ---------------------------------------------------------------------------


def estimate_marginal_federal_tax(
    ordinary_income: float,
    other_taxable_income: float = 0.0,
    filing_status: Literal["single", "mfj"] = "single",
) -> dict:
    """Rough federal income tax estimate for additional ordinary income.

    Uses 2025 federal marginal brackets. SIMPLIFIED — excludes:
    - State + local income tax
    - FICA (ESPP ordinary income IS subject to FICA, unlike ISO §3121(a)(22))
    - NIIT (3.8%) on investment income above thresholds
    - AMT considerations (ESPP doesn't trigger AMT preference items)

    For PLANNING purposes only. Consult a tax professional before decisions.

    Returns dict with: incremental_federal_tax, marginal_rate, total_taxable_income
    """
    # 2025 federal marginal brackets
    if filing_status == "single":
        brackets = [
            (11_925, 0.10),
            (48_475, 0.12),
            (103_350, 0.22),
            (197_300, 0.24),
            (250_525, 0.32),
            (626_350, 0.35),
            (float("inf"), 0.37),
        ]
    else:  # mfj
        brackets = [
            (23_850, 0.10),
            (96_950, 0.12),
            (206_700, 0.22),
            (394_600, 0.24),
            (501_050, 0.32),
            (751_600, 0.35),
            (float("inf"), 0.37),
        ]

    total_income = other_taxable_income + ordinary_income
    tax_total = _compute_progressive_tax(total_income, brackets)
    tax_base = _compute_progressive_tax(other_taxable_income, brackets)
    incremental_tax = tax_total - tax_base

    # Marginal rate at top of total_income
    marginal_rate = brackets[-1][1]
    for threshold, rate in brackets:
        if total_income <= threshold:
            marginal_rate = rate
            break

    return {
        "incremental_federal_tax": incremental_tax,
        "marginal_rate": marginal_rate,
        "total_taxable_income": total_income,
    }


def _compute_progressive_tax(income: float, brackets) -> float:
    """Apply progressive marginal tax brackets to a positive income amount."""
    if income <= 0:
        return 0.0
    tax = 0.0
    prev_threshold = 0.0
    for threshold, rate in brackets:
        if income <= threshold:
            tax += (income - prev_threshold) * rate
            return tax
        tax += (threshold - prev_threshold) * rate
        prev_threshold = threshold
    return tax


# ---------------------------------------------------------------------------
# Multi-purchase ESPP with cascading reset (NVIDIA / Apple style)
# ---------------------------------------------------------------------------
#
# Real-world tech-company ESPP plans (e.g., NVIDIA, Apple) typically:
# - Have a 2-year (24-month) offering period with 4 × 6-month purchase periods
# - Apply a look-back to the offering-anchor FMV
# - Auto-RESET the anchor if FMV at any purchase date drops below the current anchor
# - Track the §423(b)(8) $25K limit PER CALENDAR YEAR cumulatively (multiple
#   purchases in same year share the $25K bucket)
#
# Each purchase lot has its OWN effective offering anchor (post any resets),
# its OWN holding-period clocks, and its OWN per-lot QD/DD determination at sale.


@dataclass(frozen=True)
class PurchaseInput:
    """Inputs for a single purchase event within a multi-purchase offering."""

    purchase_date: date
    fmv_at_purchase: float  # per-share FMV on the purchase date
    contributions: float  # contributions accumulated for this purchase period


@dataclass(frozen=True)
class PurchaseEvent:
    """Outputs for a single purchase event."""

    purchase_index: int  # 1-based index in the purchases list
    purchase_date: date
    fmv_at_purchase: float

    # Effective offering anchor (may have moved due to a reset)
    effective_anchor_date: date
    effective_anchor_fmv: float
    reset_occurred: bool  # True if THIS purchase triggered the anchor to move

    # Purchase mechanics
    reference_fmv: float  # min of (anchor, purchase FMV) when look-back; else purchase FMV
    purchase_price: float
    contributions: float

    # Shares (with §423(b)(8) per-calendar-year cap applied)
    shares_requested: float  # uncapped
    shares_purchased: float  # post-cap
    excess_contributions_refunded: float

    # §423(b)(8) calendar-year accounting
    calendar_year: int
    ytd_fmv_used_before: float  # FMV value used in this year BEFORE this purchase
    ytd_fmv_used_after: float  # FMV value used in this year AFTER this purchase

    # Bargain element (becomes ordinary income if DD)
    bargain_per_share: float
    total_bargain: float


@dataclass(frozen=True)
class LotDisposition:
    """Per-lot QD/DD analysis at sale."""

    purchase_index: int
    purchase_date: date
    effective_anchor_date: date
    shares_held: float

    # Holding periods (measured from THIS lot's anchor + purchase dates)
    days_anchor_to_sale: int
    days_purchase_to_sale: int
    holds_two_years_from_anchor: bool
    holds_one_year_from_purchase: bool
    disposition: Literal["QD", "DD"]

    # Tax outcome for this lot (based on actual disposition)
    ordinary_income: float
    capital_gain: float
    capital_loss: float


@dataclass(frozen=True)
class ESPPMultiInputs:
    """Inputs for a multi-purchase §423 ESPP scenario with optional reset."""

    offering_start_date: date
    offering_start_fmv: float
    discount_pct: float
    has_lookback: bool
    has_reset: bool  # cascading reset: anchor moves to any purchase-date FMV below current anchor
    purchases: list[PurchaseInput]  # processed in chronological order as given
    sale_date: date
    sale_price: float


@dataclass(frozen=True)
class ESPPMultiOutputs:
    """Aggregated outputs for a multi-purchase ESPP scenario."""

    purchase_events: list[PurchaseEvent]
    lot_dispositions: list[LotDisposition]

    # Aggregated purchase totals
    total_shares_purchased: float
    total_contributions_applied: float  # contributions − refunds
    total_refunded: float
    total_bargain_at_purchase: float

    # "What if" totals — what would tax look like if every lot were QD vs DD?
    # (useful for comparison; the per-lot actual disposition is what counts)
    qd_total_ordinary_income: float
    qd_total_capital_gain: float
    qd_total_capital_loss: float
    dd_total_ordinary_income: float
    dd_total_capital_gain: float
    dd_total_capital_loss: float

    # Actual aggregated tax (each lot uses its own disposition)
    total_ordinary_income: float
    total_capital_gain: float
    total_capital_loss: float

    # §423(b)(8) calendar-year usage summary
    ytd_fmv_usage: dict[int, float]  # year → cumulative FMV value used

    # Reset events for UI highlighting
    reset_dates: list[date]


def calculate_multi_purchase_espp(inputs: ESPPMultiInputs) -> ESPPMultiOutputs:
    """Multi-purchase §423 ESPP with cascading reset + per-calendar-year limit.

    Processes purchases in the order given. At each purchase:
    1. If look-back + reset are enabled AND FMV_at_purchase < current anchor FMV:
       reset the anchor (date + FMV) to this purchase event.
    2. Compute reference FMV (min of anchor, purchase FMV) if look-back enabled.
    3. Compute purchase price = reference FMV × (1 − discount).
    4. Compute uncapped shares = contributions / purchase price.
    5. Apply §423(b)(8) per-calendar-year cap: $25,000 of anchor-FMV value per year
       per employee. Cumulative across purchases in same calendar year.
       Excess shares are not purchased; the corresponding contributions are refunded.
    6. Compute bargain element on the (capped) shares actually purchased.

    At sale, each lot uses its own anchor + purchase dates for QD/DD holding clocks.
    """

    purchase_events: list[PurchaseEvent] = []
    ytd_fmv_used: dict[int, float] = {}
    reset_dates: list[date] = []

    current_anchor_date = inputs.offering_start_date
    current_anchor_fmv = inputs.offering_start_fmv

    for idx, p in enumerate(inputs.purchases):
        # --- Step 1: Reset check ---
        if (
            inputs.has_lookback
            and inputs.has_reset
            and p.fmv_at_purchase < current_anchor_fmv
        ):
            reset_occurred = True
            current_anchor_date = p.purchase_date
            current_anchor_fmv = p.fmv_at_purchase
            reset_dates.append(p.purchase_date)
        else:
            reset_occurred = False

        # --- Step 2: Reference FMV ---
        if inputs.has_lookback:
            reference_fmv = min(current_anchor_fmv, p.fmv_at_purchase)
        else:
            reference_fmv = p.fmv_at_purchase

        # --- Step 3: Purchase price ---
        purchase_price = reference_fmv * (1.0 - inputs.discount_pct)

        # --- Step 4: Uncapped shares ---
        shares_requested = (
            p.contributions / purchase_price if purchase_price > 0 else 0.0
        )

        # --- Step 5: §423(b)(8) per-calendar-year cap ---
        year = p.purchase_date.year
        ytd_before = ytd_fmv_used.get(year, 0.0)
        available_this_year = max(0.0, 25_000.0 - ytd_before)

        if current_anchor_fmv > 0 and available_this_year > 0:
            max_shares_this_year = available_this_year / current_anchor_fmv
        else:
            max_shares_this_year = 0.0

        if shares_requested > max_shares_this_year:
            shares_actual = max_shares_this_year
            excess_shares = shares_requested - max_shares_this_year
            excess_refund = excess_shares * purchase_price
        else:
            shares_actual = shares_requested
            excess_refund = 0.0

        ytd_after = ytd_before + (shares_actual * current_anchor_fmv)
        ytd_fmv_used[year] = ytd_after

        # --- Step 6: Bargain element on actual (capped) shares ---
        bargain_per_share = max(0.0, p.fmv_at_purchase - purchase_price)
        total_bargain = bargain_per_share * shares_actual

        purchase_events.append(
            PurchaseEvent(
                purchase_index=idx + 1,
                purchase_date=p.purchase_date,
                fmv_at_purchase=p.fmv_at_purchase,
                effective_anchor_date=current_anchor_date,
                effective_anchor_fmv=current_anchor_fmv,
                reset_occurred=reset_occurred,
                reference_fmv=reference_fmv,
                purchase_price=purchase_price,
                contributions=p.contributions,
                shares_requested=shares_requested,
                shares_purchased=shares_actual,
                excess_contributions_refunded=excess_refund,
                calendar_year=year,
                ytd_fmv_used_before=ytd_before,
                ytd_fmv_used_after=ytd_after,
                bargain_per_share=bargain_per_share,
                total_bargain=total_bargain,
            )
        )

    # --- Per-lot disposition analysis at sale ---
    lot_dispositions: list[LotDisposition] = []
    qd_oi_total = 0.0
    qd_cg_total = 0.0
    qd_cl_total = 0.0
    dd_oi_total = 0.0
    dd_cg_total = 0.0
    dd_cl_total = 0.0
    total_oi = 0.0
    total_cg = 0.0
    total_cl = 0.0

    for pe in purchase_events:
        if pe.shares_purchased <= 0:
            continue  # skip empty lots

        days_anchor_to_sale = (inputs.sale_date - pe.effective_anchor_date).days
        days_purchase_to_sale = (inputs.sale_date - pe.purchase_date).days
        holds_2yr = days_anchor_to_sale > 730
        holds_1yr = days_purchase_to_sale > 365
        is_qd = holds_2yr and holds_1yr

        # QD math (always compute for "what if" comparison)
        qd_oi_offering = pe.effective_anchor_fmv - pe.purchase_price
        qd_oi_sale = inputs.sale_price - pe.purchase_price
        if inputs.sale_price <= pe.purchase_price:
            lot_qd_ordinary = 0.0
        else:
            lot_qd_ordinary = (
                max(0.0, min(qd_oi_offering, qd_oi_sale)) * pe.shares_purchased
            )
        qd_proceeds = inputs.sale_price * pe.shares_purchased
        qd_basis = (pe.purchase_price * pe.shares_purchased) + lot_qd_ordinary
        qd_diff = qd_proceeds - qd_basis
        lot_qd_cg = qd_diff if qd_diff >= 0 else 0.0
        lot_qd_cl = -qd_diff if qd_diff < 0 else 0.0

        # DD math (always compute for "what if" comparison)
        lot_dd_ordinary = pe.total_bargain
        dd_diff = (inputs.sale_price - pe.fmv_at_purchase) * pe.shares_purchased
        lot_dd_cg = dd_diff if dd_diff > 0 else 0.0
        lot_dd_cl = -dd_diff if dd_diff < 0 else 0.0

        qd_oi_total += lot_qd_ordinary
        qd_cg_total += lot_qd_cg
        qd_cl_total += lot_qd_cl
        dd_oi_total += lot_dd_ordinary
        dd_cg_total += lot_dd_cg
        dd_cl_total += lot_dd_cl

        # Actual disposition
        if is_qd:
            disposition: Literal["QD", "DD"] = "QD"
            lot_oi = lot_qd_ordinary
            lot_cg = lot_qd_cg
            lot_cl = lot_qd_cl
        else:
            disposition = "DD"
            lot_oi = lot_dd_ordinary
            lot_cg = lot_dd_cg
            lot_cl = lot_dd_cl

        total_oi += lot_oi
        total_cg += lot_cg
        total_cl += lot_cl

        lot_dispositions.append(
            LotDisposition(
                purchase_index=pe.purchase_index,
                purchase_date=pe.purchase_date,
                effective_anchor_date=pe.effective_anchor_date,
                shares_held=pe.shares_purchased,
                days_anchor_to_sale=days_anchor_to_sale,
                days_purchase_to_sale=days_purchase_to_sale,
                holds_two_years_from_anchor=holds_2yr,
                holds_one_year_from_purchase=holds_1yr,
                disposition=disposition,
                ordinary_income=lot_oi,
                capital_gain=lot_cg,
                capital_loss=lot_cl,
            )
        )

    total_shares = sum(pe.shares_purchased for pe in purchase_events)
    total_contrib_applied = sum(
        pe.contributions - pe.excess_contributions_refunded for pe in purchase_events
    )
    total_refunded = sum(pe.excess_contributions_refunded for pe in purchase_events)
    total_bargain = sum(pe.total_bargain for pe in purchase_events)

    return ESPPMultiOutputs(
        purchase_events=purchase_events,
        lot_dispositions=lot_dispositions,
        total_shares_purchased=total_shares,
        total_contributions_applied=total_contrib_applied,
        total_refunded=total_refunded,
        total_bargain_at_purchase=total_bargain,
        qd_total_ordinary_income=qd_oi_total,
        qd_total_capital_gain=qd_cg_total,
        qd_total_capital_loss=qd_cl_total,
        dd_total_ordinary_income=dd_oi_total,
        dd_total_capital_gain=dd_cg_total,
        dd_total_capital_loss=dd_cl_total,
        total_ordinary_income=total_oi,
        total_capital_gain=total_cg,
        total_capital_loss=total_cl,
        ytd_fmv_usage=ytd_fmv_used,
        reset_dates=reset_dates,
    )


def generate_purchase_dates(
    offering_start: date,
    num_purchases: int,
    months_between_purchases: int = 6,
) -> list[date]:
    """Generate purchase dates spaced N months apart from the offering start.

    Default 6-month spacing matches NVIDIA's typical 4 × 6-month structure.
    """
    from dateutil.relativedelta import relativedelta

    return [
        offering_start + relativedelta(months=i * months_between_purchases)
        for i in range(1, num_purchases + 1)
    ]
