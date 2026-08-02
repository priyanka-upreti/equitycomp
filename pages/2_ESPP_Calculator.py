"""ESPP Calculator — Streamlit page.

Two modes:
- Single purchase (V1): one offering period, one purchase, one sale
- Multi-purchase with auto-reset (large-cap tech style): multiple purchases over a
  2-year offering, cascading anchor reset when FMV drops, per-calendar-year
  §423(b)(8) $25K limit tracking, per-lot QD/DD at sale

Both modes support ticker auto-fill: type a US-listed ticker in the sidebar and
click "Fetch prices" to pull historical closes from Yahoo Finance and seed every
FMV field on the current dates.
"""

from datetime import date

import pandas as pd
import streamlit as st

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.espp_calc import (  # noqa: E402
    ESPPInputs,
    ESPPMultiInputs,
    PurchaseInput,
    calculate_espp_purchase,
    calculate_multi_purchase_espp,
    estimate_marginal_federal_tax,
    generate_purchase_dates,
)
from lib.ticker_data import (  # noqa: E402
    TickerFetchError,
    fetch_close_prices,
    get_price_on_or_before,
)


st.set_page_config(
    page_title="ESPP Calculator",
    page_icon="🛒",
    layout="wide",
)

st.title("🛒 ESPP Calculator")
st.markdown(
    "Model a **§423-qualified Employee Stock Purchase Plan**. Multi-purchase mode "
    "covers large-cap tech-style plans with 2-year look-back, 4 × 6-month purchases, "
    "and automatic anchor reset when stock drops."
)

mode_multi = st.toggle(
    "Multi-purchase plan with auto-reset (large-cap tech style)",
    value=True,
    help="Toggle OFF for a single-purchase plan.",
)

st.divider()


# ===========================================================================
# SHARED: Ticker auto-fill UI (top of sidebar, both modes)
# ===========================================================================

def _clear_ticker_state():
    """Wipe all ticker-related session state so widgets fully reset on next render."""
    for k in (
        "espp_ticker",
        "espp_ticker_prices",
        "espp_ticker_error",
        "espp_ticker_input",
        "_offering_fmv_source",
        "_purchase_fmv_source",
        "_sale_price_source",
    ):
        st.session_state.pop(k, None)


with st.sidebar:
    st.header("📈 Auto-fill from ticker (optional)")
    st.caption(
        "Enter a US-listed ticker to auto-populate every FMV field from historical "
        "closing prices. Any auto-filled value can still be edited manually."
    )
    ticker_input = st.text_input(
        "Ticker symbol",
        key="espp_ticker_input",
        placeholder="e.g., NVDA, AAPL",
        help="US-listed public companies only. Private / OTC / delisted tickers won't work.",
    ).strip().upper()

    fetch_col1, fetch_col2 = st.columns([2, 1])
    with fetch_col1:
        fetch_clicked = st.button(
            "🔍 Fetch prices",
            type="primary",
            use_container_width=True,
            disabled=not ticker_input,
        )
    with fetch_col2:
        st.button(
            "Clear",
            use_container_width=True,
            on_click=_clear_ticker_state,
        )

    if fetch_clicked and ticker_input:
        st.session_state["_espp_pending_fetch"] = ticker_input

    st.divider()


# Convenience for downstream force-syncing
prev_prices = st.session_state.get("espp_ticker_prices")
prev_ticker = st.session_state.get("espp_ticker")


def _seeded_price(target_date):
    """Fetched close on or before target_date, or None if no active ticker fetch."""
    if prev_prices is not None and prev_ticker == ticker_input and ticker_input:
        return get_price_on_or_before(prev_prices, target_date)
    return None


def _force_sync_widget(widget_key, source_key, source, seeded_val):
    """Push seeded_val into st.session_state[widget_key] when the (ticker, date)
    source changes. Streamlit's `value=` param is only honored on the widget's
    FIRST render; direct session_state writes are the documented override.

    Only rewrites when the source key differs, so manual user edits persist.
    """
    if seeded_val and st.session_state.get(source_key) != source:
        st.session_state[widget_key] = seeded_val
        st.session_state[source_key] = source


def _resolve_pending_fetch(start_date, end_date):
    """If a fetch was requested, run it now that we know the date range."""
    pending = st.session_state.pop("_espp_pending_fetch", None)
    if not pending:
        return
    with st.spinner(f"Fetching {pending} prices from Yahoo Finance..."):
        try:
            closes = fetch_close_prices(pending, start_date, end_date)
            st.session_state["espp_ticker"] = pending
            st.session_state["espp_ticker_prices"] = closes
            st.session_state.pop("espp_ticker_error", None)
            st.rerun()
        except TickerFetchError as e:
            st.session_state["espp_ticker_error"] = str(e)
            st.session_state.pop("espp_ticker_prices", None)


def _show_fetch_status():
    """Render success / error banner for the current fetch state."""
    if err := st.session_state.get("espp_ticker_error"):
        st.error(f"⚠️ {err}")
    elif prev_prices is not None and prev_ticker == ticker_input and ticker_input:
        st.success(
            f"✅ Loaded {len(prev_prices)} trading days for **{ticker_input}**. "
            "FMVs auto-filled from actual closing prices."
        )


# ===========================================================================
# MULTI-PURCHASE MODE
# ===========================================================================

if mode_multi:
    with st.sidebar:
        st.header("📥 Plan Setup")
        offering_start_date = st.date_input(
            "Offering start date",
            value=date(2024, 1, 1),
        )

        seeded_offering_fmv = _seeded_price(offering_start_date)
        _force_sync_widget(
            widget_key="offering_start_fmv_widget",
            source_key="_offering_fmv_source",
            source=f"{ticker_input}|{offering_start_date}",
            seeded_val=seeded_offering_fmv,
        )
        offering_start_fmv = st.number_input(
            "FMV at offering start (per share)",
            min_value=0.01,
            value=seeded_offering_fmv if seeded_offering_fmv else 100.00,
            step=0.01,
            format="%.2f",
            key="offering_start_fmv_widget",
            help=(
                f"Auto-filled from {ticker_input} close on or before {offering_start_date}. "
                "Edit to override."
                if seeded_offering_fmv else None
            ),
        )
        _discount_int = st.slider(
            "Discount % (max 15% per §423(b)(6))",
            min_value=0,
            max_value=15,
            value=15,
            step=1,
            format="%d%%",
        )
        discount_pct = _discount_int / 100.0
        has_lookback = st.checkbox(
            "Look-back feature",
            value=True,
            help="Discount applies to LOWER of offering FMV or purchase FMV.",
        )
        has_reset = st.checkbox(
            "Auto-reset feature",
            value=True,
            help="If FMV at any purchase date drops below the current anchor, "
            "the offering automatically restarts with the lower price as the "
            "new anchor (common in large-cap tech plans).",
        )

        st.divider()
        st.header("📅 Purchase Schedule")
        num_purchases = st.slider(
            "Number of purchase periods",
            min_value=1,
            max_value=8,
            value=4,
        )
        months_between = st.slider(
            "Months between purchases",
            min_value=3,
            max_value=12,
            value=6,
        )

        st.divider()
        st.header("📤 Planned Sale")
        sale_date = st.date_input(
            "Sale date",
            value=date(2027, 6, 1),
            min_value=offering_start_date,
        )

        seeded_sale_price = _seeded_price(sale_date)
        _force_sync_widget(
            widget_key="sale_price_widget",
            source_key="_sale_price_source",
            source=f"{ticker_input}|{sale_date}",
            seeded_val=seeded_sale_price,
        )
        sale_price = st.number_input(
            "Sale price (per share)",
            min_value=0.01,
            value=seeded_sale_price if seeded_sale_price else 200.00,
            step=0.01,
            format="%.2f",
            key="sale_price_widget",
            help=(
                f"Auto-filled from {ticker_input} close on or before {sale_date}. "
                "Edit to override for a hypothetical sale price."
                if seeded_sale_price else None
            ),
        )

        _resolve_pending_fetch(offering_start_date, sale_date)
        _show_fetch_status()

        st.divider()
        st.header("💰 Tax Estimate (optional)")
        other_income = st.number_input(
            "Other taxable income for the year ($)",
            min_value=0,
            value=150_000,
            step=1_000,
        )
        filing_status = st.radio(
            "Filing status",
            options=["single", "mfj"],
            format_func=lambda x: "Single" if x == "single" else "Married Filing Jointly",
            horizontal=True,
        )

    st.header("📝 Per-Purchase Inputs")
    st.caption(
        "Enter the FMV on each purchase date and contributions accumulated for "
        "that purchase period. Dates are auto-generated from your offering "
        "start + spacing in the sidebar — edit only the FMV + contribution columns."
    )

    purchase_dates = generate_purchase_dates(
        offering_start_date,
        num_purchases=num_purchases,
        months_between_purchases=months_between,
    )

    ticker_prices = st.session_state.get("espp_ticker_prices")
    ticker_active = ticker_input and st.session_state.get("espp_ticker") == ticker_input
    if ticker_active and ticker_prices is not None:
        default_fmvs = []
        for pd_ in purchase_dates:
            p = get_price_on_or_before(ticker_prices, pd_)
            default_fmvs.append(p if p else offering_start_fmv)
    else:
        default_fmvs = [offering_start_fmv * (1.0 + 0.05 * i) for i in range(1, num_purchases + 1)]
    default_contribs = [3_000.0 for _ in range(num_purchases)]

    default_df = pd.DataFrame({
        "Purchase #": list(range(1, num_purchases + 1)),
        "Date": [d.isoformat() for d in purchase_dates],
        "FMV at purchase ($)": default_fmvs,
        "Contributions ($)": default_contribs,
    })

    edited_df = st.data_editor(
        default_df,
        use_container_width=True,
        hide_index=True,
        disabled=["Purchase #", "Date"],
        column_config={
            "FMV at purchase ($)": st.column_config.NumberColumn(
                "FMV at purchase ($)", min_value=0.01, step=0.01, format="$%.2f"
            ),
            "Contributions ($)": st.column_config.NumberColumn(
                "Contributions ($)", min_value=0.0, step=100.0, format="$%.2f"
            ),
        },
        key="multi_purchase_inputs",
    )

    purchases = [
        PurchaseInput(
            purchase_date=date.fromisoformat(row["Date"]),
            fmv_at_purchase=float(row["FMV at purchase ($)"]),
            contributions=float(row["Contributions ($)"]),
        )
        for _, row in edited_df.iterrows()
    ]

    multi_inputs = ESPPMultiInputs(
        offering_start_date=offering_start_date,
        offering_start_fmv=float(offering_start_fmv),
        discount_pct=float(discount_pct),
        has_lookback=bool(has_lookback),
        has_reset=bool(has_reset),
        purchases=purchases,
        sale_date=sale_date,
        sale_price=float(sale_price),
    )
    result = calculate_multi_purchase_espp(multi_inputs)

    if ticker_active and ticker_prices is not None:
        st.divider()
        st.subheader(f"📈 Historical price — {ticker_input}")
        chart_df = pd.DataFrame({
            "Date": ticker_prices.index,
            "Close": ticker_prices.values,
        }).set_index("Date")
        st.line_chart(chart_df, use_container_width=True, height=200)
        st.caption(
            "Purchase dates are highlighted in the table above. "
            "Auto-populated FMVs are the closing price on each purchase date "
            "(or nearest prior trading day)."
        )

    if result.reset_dates:
        reset_dates_str = ", ".join(d.isoformat() for d in result.reset_dates)
        st.success(
            f"🔄 **Anchor reset(s) triggered on:** {reset_dates_str}. "
            f"Each reset moved the offering anchor to the lower FMV, "
            f"benefiting all subsequent purchases."
        )

    st.divider()
    st.header("📊 Per-Purchase Outputs")

    purchase_table_rows = []
    for pe in result.purchase_events:
        purchase_table_rows.append({
            "#": pe.purchase_index,
            "Date": pe.purchase_date.isoformat(),
            "FMV": f"${pe.fmv_at_purchase:,.2f}",
            "Anchor date": pe.effective_anchor_date.isoformat(),
            "Anchor FMV": f"${pe.effective_anchor_fmv:,.2f}",
            "Reset?": "🔄" if pe.reset_occurred else "",
            "Purchase price": f"${pe.purchase_price:,.2f}",
            "Shares req.": f"{pe.shares_requested:,.2f}",
            "Shares actual": f"{pe.shares_purchased:,.2f}",
            "Refund": f"${pe.excess_contributions_refunded:,.2f}",
            "Bargain element": f"${pe.total_bargain:,.2f}",
            "Year": pe.calendar_year,
            "$25K YTD after": f"${pe.ytd_fmv_used_after:,.0f}",
        })
    purchase_df = pd.DataFrame(purchase_table_rows)
    st.dataframe(purchase_df, use_container_width=True, hide_index=True)

    sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)
    with sum_col1:
        st.metric("Total shares purchased", f"{result.total_shares_purchased:,.2f}")
    with sum_col2:
        st.metric("Total contributions applied", f"${result.total_contributions_applied:,.2f}")
    with sum_col3:
        st.metric("Total refunded", f"${result.total_refunded:,.2f}")
    with sum_col4:
        st.metric("Total bargain at purchase", f"${result.total_bargain_at_purchase:,.2f}")

    st.divider()
    st.header("📋 §423(b)(8) $25K Annual Limit Usage")
    if result.ytd_fmv_usage:
        usage_rows = [
            {
                "Calendar year": year,
                "FMV value used (at anchor FMV)": f"${used:,.2f}",
                "Remaining (out of $25,000)": f"${max(0, 25_000 - used):,.2f}",
                "Status": "✅ Within limit" if used <= 25_000 else "❌ At limit",
            }
            for year, used in sorted(result.ytd_fmv_usage.items())
        ]
        st.dataframe(pd.DataFrame(usage_rows), use_container_width=True, hide_index=True)
    if result.total_refunded > 0:
        st.warning(
            f"💵 **${result.total_refunded:,.2f}** in excess contributions refunded "
            f"due to per-calendar-year $25K limit. All downstream tax math uses the "
            f"capped {result.total_shares_purchased:,.2f} shares only."
        )

    st.divider()
    st.header("📅 Per-Lot Disposition at Sale")

    lot_rows = []
    for lot in result.lot_dispositions:
        lot_rows.append({
            "#": lot.purchase_index,
            "Purchase date": lot.purchase_date.isoformat(),
            "Anchor date": lot.effective_anchor_date.isoformat(),
            "Shares": f"{lot.shares_held:,.2f}",
            "Days from anchor": lot.days_anchor_to_sale,
            "Days from purchase": lot.days_purchase_to_sale,
            "Disposition": "✅ QD" if lot.disposition == "QD" else "❌ DD",
            "Ordinary income": f"${lot.ordinary_income:,.2f}",
            "Cap gain": f"${lot.capital_gain:,.2f}",
            "Cap loss": f"${lot.capital_loss:,.2f}",
        })
    if lot_rows:
        st.dataframe(pd.DataFrame(lot_rows), use_container_width=True, hide_index=True)

    st.divider()
    st.header("⚖️ Aggregated Tax Outcome")

    qd_count = sum(1 for lot in result.lot_dispositions if lot.disposition == "QD")
    dd_count = sum(1 for lot in result.lot_dispositions if lot.disposition == "DD")
    st.caption(
        f"Based on per-lot dispositions: **{qd_count}** QD lot(s) + **{dd_count}** DD lot(s). "
        f"Each lot uses its own anchor + purchase dates for the holding clock."
    )

    tax_col1, tax_col2, tax_col3 = st.columns(3)
    with tax_col1:
        st.metric("Total ordinary income (W-2)", f"${result.total_ordinary_income:,.2f}")
    with tax_col2:
        st.metric("Total capital gain", f"${result.total_capital_gain:,.2f}")
    with tax_col3:
        st.metric("Total capital loss", f"${result.total_capital_loss:,.2f}")

    with st.expander("🔍 What if every lot were QD vs DD? (sensitivity comparison)"):
        what_col1, what_col2 = st.columns(2)
        with what_col1:
            st.markdown("**If ALL lots were QD:**")
            st.markdown(
                f"- Ordinary income: `${result.qd_total_ordinary_income:,.2f}`\n"
                f"- Capital gain (LTCG): `${result.qd_total_capital_gain:,.2f}`\n"
                f"- Capital loss: `${result.qd_total_capital_loss:,.2f}`"
            )
        with what_col2:
            st.markdown("**If ALL lots were DD:**")
            st.markdown(
                f"- Ordinary income: `${result.dd_total_ordinary_income:,.2f}`\n"
                f"- Capital gain: `${result.dd_total_capital_gain:,.2f}`\n"
                f"- Capital loss: `${result.dd_total_capital_loss:,.2f}`"
            )

    st.divider()
    st.header("💸 Federal Tax Estimate (planning only)")
    tax = estimate_marginal_federal_tax(
        ordinary_income=result.total_ordinary_income,
        other_taxable_income=float(other_income),
        filing_status=filing_status,
    )
    tcol1, tcol2, tcol3 = st.columns(3)
    with tcol1:
        st.metric("Incremental federal tax", f"${tax['incremental_federal_tax']:,.0f}")
    with tcol2:
        st.metric("Marginal rate at top", f"{tax['marginal_rate'] * 100:.0f}%")
    with tcol3:
        st.metric("Total taxable income", f"${tax['total_taxable_income']:,.0f}")
    st.caption(
        "⚠️ **Simplified estimate.** Excludes state + FICA + Medicare + NIIT. "
        "ESPP ordinary income IS subject to FICA (unlike ISO). For planning only."
    )

    st.divider()
    with st.expander("📚 Statutory + regulatory references"):
        st.markdown(
            """
- **IRC §423(a)** — General rule deferring tax at §423 ESPP purchase
- **IRC §423(b)** — Requirements for a qualified §423 plan
- **IRC §423(b)(6)** — Discount limit (max 15%)
- **IRC §423(b)(7)** — Offering period limits (27 months max with non-fixed price)
- **IRC §423(b)(8)** — **$25K per calendar year per employee per employer**, measured at offering-grant FMV
- **IRC §423(c)** — QD ordinary income lesser-of formula (per lot)
- **IRC §421(a)** — Nonrecognition of income at purchase
- **Treas. Reg. §1.423-2** — §423 plan requirements + operation
- **Form 3922** — Information return for §423 ESPP purchases

**Multi-purchase + reset mechanics modeled here:**
- Cascading anchor reset: if FMV at any purchase < current anchor, the anchor moves
  to that date + price. All subsequent purchases use the new (lower) anchor.
- Per-calendar-year $25K limit: cumulative across all purchases in same calendar year.
  Limit measured at the lot's effective offering-anchor FMV.
- Per-lot QD/DD: each lot uses its own anchor + purchase dates for the holding clock.
"""
        )

# ===========================================================================
# SINGLE-PURCHASE MODE (V1)
# ===========================================================================

else:
    with st.sidebar:
        st.header("📥 Plan + Offering")
        offering_start_date = st.date_input(
            "Offering period start date",
            value=date(2024, 1, 1),
        )
        purchase_date = st.date_input(
            "Purchase date",
            value=date(2024, 6, 30),
            min_value=offering_start_date,
        )

        seeded_offering_fmv = _seeded_price(offering_start_date)
        _force_sync_widget(
            widget_key="offering_start_fmv_widget",
            source_key="_offering_fmv_source",
            source=f"{ticker_input}|{offering_start_date}",
            seeded_val=seeded_offering_fmv,
        )
        offering_fmv = st.number_input(
            "FMV at start of offering period (per share, USD)",
            min_value=0.01,
            value=seeded_offering_fmv if seeded_offering_fmv else 100.00,
            step=0.01,
            format="%.2f",
            key="offering_start_fmv_widget",
            help=(
                f"Auto-filled from {ticker_input} close on or before {offering_start_date}. "
                "Edit to override."
                if seeded_offering_fmv else None
            ),
        )

        seeded_purchase_fmv = _seeded_price(purchase_date)
        _force_sync_widget(
            widget_key="single_purchase_fmv_widget",
            source_key="_purchase_fmv_source",
            source=f"{ticker_input}|{purchase_date}",
            seeded_val=seeded_purchase_fmv,
        )
        purchase_fmv = st.number_input(
            "FMV at purchase date (per share, USD)",
            min_value=0.01,
            value=seeded_purchase_fmv if seeded_purchase_fmv else 150.00,
            step=0.01,
            format="%.2f",
            key="single_purchase_fmv_widget",
            help=(
                f"Auto-filled from {ticker_input} close on or before {purchase_date}. "
                "Edit to override."
                if seeded_purchase_fmv else None
            ),
        )

        _discount_int = st.slider(
            "Discount % (max 15% per §423(b)(6))",
            min_value=0,
            max_value=15,
            value=15,
            step=1,
            format="%d%%",
        )
        discount_pct = _discount_int / 100.0
        has_lookback = st.checkbox(
            "Plan has look-back feature",
            value=True,
        )
        contributions = st.number_input(
            "Total contributions during offering ($)",
            min_value=0.0,
            value=8_500.00,
            step=100.00,
            format="%.2f",
        )

        st.divider()
        st.header("📤 Planned Sale")
        sale_date = st.date_input(
            "Sale date",
            value=date(2027, 1, 1),
            min_value=purchase_date,
        )

        seeded_sale_price = _seeded_price(sale_date)
        _force_sync_widget(
            widget_key="sale_price_widget",
            source_key="_sale_price_source",
            source=f"{ticker_input}|{sale_date}",
            seeded_val=seeded_sale_price,
        )
        sale_price = st.number_input(
            "Sale price (per share, USD)",
            min_value=0.01,
            value=seeded_sale_price if seeded_sale_price else 200.00,
            step=0.01,
            format="%.2f",
            key="sale_price_widget",
            help=(
                f"Auto-filled from {ticker_input} close on or before {sale_date}. "
                "Edit to override for a hypothetical sale price."
                if seeded_sale_price else None
            ),
        )

        _resolve_pending_fetch(offering_start_date, sale_date)
        _show_fetch_status()

        st.divider()
        st.header("💰 Tax Estimate (optional)")
        other_income = st.number_input(
            "Other taxable income for the year ($)",
            min_value=0,
            value=150_000,
            step=1_000,
        )
        filing_status = st.radio(
            "Filing status",
            options=["single", "mfj"],
            format_func=lambda x: "Single" if x == "single" else "Married Filing Jointly",
            horizontal=True,
        )

    inputs = ESPPInputs(
        offering_start_fmv=float(offering_fmv),
        purchase_fmv=float(purchase_fmv),
        discount_pct=float(discount_pct),
        has_lookback=bool(has_lookback),
        offering_start_date=offering_start_date,
        purchase_date=purchase_date,
        sale_date=sale_date,
        sale_price=float(sale_price),
        contributions=float(contributions),
    )
    result = calculate_espp_purchase(inputs)

    ticker_prices = st.session_state.get("espp_ticker_prices")
    ticker_active = ticker_input and st.session_state.get("espp_ticker") == ticker_input
    if ticker_active and ticker_prices is not None:
        st.subheader(f"📈 Historical price — {ticker_input}")
        chart_df = pd.DataFrame({
            "Date": ticker_prices.index,
            "Close": ticker_prices.values,
        }).set_index("Date")
        st.line_chart(chart_df, use_container_width=True, height=200)
        st.caption(
            "Offering start, purchase date, and sale date FMVs in the sidebar are "
            "pulled from these closing prices (or the nearest prior trading day)."
        )
        st.divider()

    st.header("📊 At Purchase")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Reference FMV", f"${result.reference_fmv:,.2f}")
    with col2:
        st.metric("Purchase price / share", f"${result.purchase_price_per_share:,.2f}")
    with col3:
        st.metric("Shares purchased", f"{result.shares_purchased:,.4f}")
    with col4:
        st.metric("Bargain element / share", f"${result.bargain_element_per_share:,.2f}")

    st.header("📋 §423(b)(8) $25K Annual Limit")
    limit_col1, limit_col2, limit_col3, limit_col4 = st.columns(4)
    with limit_col1:
        st.metric("Max shares allowed", f"{result.max_shares_under_25k_limit:,.2f}")
    with limit_col2:
        st.metric("Shares requested", f"{result.shares_requested:,.4f}")
    with limit_col3:
        st.metric("Shares actually purchased", f"{result.shares_purchased:,.4f}")
    with limit_col4:
        if result.is_within_25k_limit:
            st.success("✅ Within limit")
        else:
            st.error(f"❌ Capped — {result.shares_over_limit:,.2f} shares prevented")

    if not result.is_within_25k_limit:
        st.warning(
            f"💵 **${result.excess_contributions_refunded:,.2f}** in excess contributions "
            f"will be refunded to you."
        )

    st.divider()
    st.header("📅 Disposition Classification")
    cls_col1, cls_col2 = st.columns([1, 2])
    with cls_col1:
        if result.disposition == "QD":
            st.success(f"✅ **{result.disposition}** — Qualifying Disposition")
        else:
            st.error(f"❌ **{result.disposition}** — Disqualifying Disposition")
    with cls_col2:
        st.markdown(
            f"""
**Days post-offering-start:** {result.days_from_offering_start_to_sale} (need > 730 for QD)
{"✅" if result.holds_two_years_from_offering else "❌"} 2-year-from-offering rule

**Days post-purchase:** {result.days_from_purchase_to_sale} (need > 365 for QD)
{"✅" if result.holds_one_year_from_purchase else "❌"} 1-year-from-purchase rule
"""
        )

    st.divider()
    st.header("⚖️ Tax Outcome at Sale — Side-by-Side")
    scenario_col1, scenario_col2 = st.columns(2)
    with scenario_col1:
        st.subheader("If QD")
        st.markdown(
            f"""
**Ordinary income (W-2):** `${result.qd_ordinary_income:,.2f}`
**Capital gain (LTCG):** `${result.qd_capital_gain:,.2f}`
**Capital loss:** `${result.qd_capital_loss:,.2f}`
"""
        )
    with scenario_col2:
        st.subheader("If DD")
        st.markdown(
            f"""
**Ordinary income (W-2, full bargain at purchase):** `${result.dd_ordinary_income:,.2f}`
**Capital gain ({'LTCG' if result.dd_capital_gain_is_long_term else 'STCG'}):** `${result.dd_capital_gain:,.2f}`
**Capital loss:** `${result.dd_capital_loss:,.2f}`
"""
        )

    st.divider()
    st.header("💸 Federal Tax Estimate (planning only)")
    active_ordinary = (
        result.qd_ordinary_income
        if result.disposition == "QD"
        else result.dd_ordinary_income
    )
    tax = estimate_marginal_federal_tax(
        ordinary_income=active_ordinary,
        other_taxable_income=float(other_income),
        filing_status=filing_status,
    )
    tax_col1, tax_col2, tax_col3 = st.columns(3)
    with tax_col1:
        st.metric("Incremental federal tax", f"${tax['incremental_federal_tax']:,.0f}")
    with tax_col2:
        st.metric("Marginal rate at top", f"{tax['marginal_rate'] * 100:.0f}%")
    with tax_col3:
        st.metric("Total taxable income", f"${tax['total_taxable_income']:,.0f}")
    st.caption(
        "⚠️ Simplified estimate. Excludes state + FICA + Medicare + NIIT. For planning only."
    )

    st.divider()
    with st.expander("📚 Statutory + regulatory references"):
        st.markdown(
            """
- **IRC §423(a)** — General rule deferring tax at qualified ESPP purchase
- **IRC §423(b)** — Requirements for a qualified §423 plan
- **IRC §423(b)(6)** — Discount limit (max 15%)
- **IRC §423(b)(8)** — $25,000 annual limit (offering-date FMV)
- **IRC §423(c)** — QD ordinary income lesser-of formula
- **IRC §421(a)** — Nonrecognition of income at purchase
- **Treas. Reg. §1.423-2** — §423 plan requirements + operation
- **Form 3922** — Information return for §423 ESPP purchases
"""
        )
