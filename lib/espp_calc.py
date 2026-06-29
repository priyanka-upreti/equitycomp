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
