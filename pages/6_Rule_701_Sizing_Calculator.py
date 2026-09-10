"""Rule 701 Sizing Calculator — Streamlit page.

Sizes a private company's Rule 701 capacity for compensatory equity issuances:
the 12-month cap under Rule 701(d)(2), the $10M enhanced-disclosure trigger under
Rule 701(e), and rolling-window testing across any consecutive 12-month period.
"""

from datetime import date

import pandas as pd
import streamlit as st

# Make lib/ importable regardless of how streamlit launches
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.rule701_calc import (  # noqa: E402
    DISCLOSURE_THRESHOLD,
    Issuance,
    Rule701Inputs,
    calculate_rule701_capacity,
    max_additional_option_grant,
)


st.set_page_config(
    page_title="Rule 701 Sizing Calculator",
    page_icon="📐",
    layout="wide",
)

st.title("📐 Rule 701 Sizing Calculator")
st.markdown(
    "Size a private company's **Rule 701** capacity for compensatory equity. "
    "Models the **12-month cap** (Rule 701(d)(2)), the **$10M enhanced-disclosure "
    "trigger** (Rule 701(e)), and — critically — tests **every consecutive 12-month "
    "window**, not just the calendar year."
)

st.divider()

# ---------------------------------------------------------------------------
# Sidebar — issuer profile
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("🏢 Issuer Profile")

    is_reporting = st.checkbox(
        "Issuer is an Exchange Act reporting company",
        value=False,
        help="Rule 701 is available only to companies NOT subject to §13 or §15(d) "
        "reporting. Public companies register plan shares on Form S-8 instead.",
    )

    total_assets = st.number_input(
        "Total assets ($)",
        min_value=0.0,
        value=4_000_000.00,
        step=100_000.0,
        format="%.2f",
        help="Measured at the most recent annual balance sheet date. Drives the "
        "15%-of-assets test.",
    )

    outstanding_shares = st.number_input(
        "Outstanding shares of the class",
        min_value=1,
        value=10_000_000,
        step=100_000,
        help="Measured at the most recent annual balance sheet date. Drives the "
        "15%-of-outstanding test.",
    )

    balance_sheet_date = st.date_input(
        "Most recent annual balance sheet date",
        value=date(2025, 12, 31),
    )

    st.divider()
    st.header("📅 Measurement")

    measurement_date = st.date_input(
        "Measure the 12-month window ending",
        value=date(2026, 6, 30),
        help="The rule tests ANY consecutive 12-month period. This sets the primary "
        "window to report on; every issuance date is also tested as a window end.",
    )

    st.divider()
    st.header("🧮 Headroom Check")
    planned_strike = st.number_input(
        "Planned option exercise price ($)",
        min_value=0.01,
        value=1.00,
        step=0.01,
        format="%.2f",
        help="Used to compute how many additional option shares could be granted "
        "today without breaching the cap.",
    )

# ---------------------------------------------------------------------------
# Main — issuance schedule
# ---------------------------------------------------------------------------

st.header("📝 Issuances Made in Reliance on Rule 701")
st.caption(
    "Enter every compensatory issuance. **Options count at grant on the exercise "
    "price** — not at exercise, and not at FMV (Rule 701(d)(3)(ii)). RSUs have no "
    "exercise price and are valued at grant-date FMV. RSAs and direct sales count "
    "the consideration actually received."
)

default_issuances = pd.DataFrame(
    {
        "Date": ["2025-09-01", "2026-02-15", "2026-05-01"],
        "Type": ["OPTION", "RSA", "OPTION"],
        "Shares": [250_000, 500_000, 300_000],
        "Price / share ($)": [1.20, 0.0001, 2.40],
        "FMV / share ($)": [1.20, 0.0001, 2.40],
        "Recipient": ["2025 new hires", "Founder top-up", "2026 refresh grants"],
    }
)

edited = st.data_editor(
    default_issuances,
    use_container_width=True,
    hide_index=True,
    num_rows="dynamic",
    column_config={
        "Date": st.column_config.TextColumn(
            "Date", help="ISO format: YYYY-MM-DD"
        ),
        "Type": st.column_config.SelectboxColumn(
            "Type",
            options=["OPTION", "RSA", "RSU", "DIRECT_SALE"],
            required=True,
        ),
        "Shares": st.column_config.NumberColumn(
            "Shares", min_value=0, step=1_000, format="%d"
        ),
        "Price / share ($)": st.column_config.NumberColumn(
            "Price / share ($)",
            min_value=0.0,
            step=0.01,
            format="$%.4f",
            help="Exercise price for options; purchase price for RSA / direct sale; "
            "ignored for RSUs.",
        ),
        "FMV / share ($)": st.column_config.NumberColumn(
            "FMV / share ($)",
            min_value=0.0,
            step=0.01,
            format="$%.4f",
            help="Used to value RSUs. Informational for other types.",
        ),
    },
    key="rule701_issuances",
)

# --- Parse the editor into Issuance objects, tolerating bad rows ---
issuances = []
parse_errors = []
for idx, row in edited.iterrows():
    raw_date = str(row["Date"]).strip()
    if not raw_date or raw_date.lower() in ("nan", "none"):
        continue
    try:
        d = date.fromisoformat(raw_date)
    except ValueError:
        parse_errors.append(f"Row {idx + 1}: '{raw_date}' is not a valid YYYY-MM-DD date.")
        continue
    try:
        shares = int(row["Shares"] or 0)
    except (TypeError, ValueError):
        parse_errors.append(f"Row {idx + 1}: shares must be a whole number.")
        continue
    if shares <= 0:
        continue
    issuances.append(
        Issuance(
            issuance_date=d,
            issuance_type=str(row["Type"]),
            shares=shares,
            price_per_share=float(row["Price / share ($)"] or 0.0),
            fmv_per_share=float(row["FMV / share ($)"] or 0.0),
            recipient_label=str(row.get("Recipient") or ""),
        )
    )

for err in parse_errors:
    st.error(f"⚠️ {err}")

inputs = Rule701Inputs(
    is_reporting_company=bool(is_reporting),
    total_assets=float(total_assets),
    outstanding_shares_of_class=int(outstanding_shares),
    balance_sheet_date=balance_sheet_date,
    issuances=tuple(issuances),
    measurement_date=measurement_date,
)
result = calculate_rule701_capacity(inputs)

# ---------------------------------------------------------------------------
# Availability gate
# ---------------------------------------------------------------------------

if not result.exemption_available:
    st.error(f"🚫 **Rule 701 is not available.** {result.unavailable_reason}")
    st.stop()

st.divider()

# ---------------------------------------------------------------------------
# Capacity
# ---------------------------------------------------------------------------

st.header("📊 Capacity — Rule 701(d)(2)")
st.caption(
    "The cap is the **greatest of** three tests. Two are dollar-denominated and one "
    "is share-denominated, and the rule reads *aggregate sales price* **or** *amount "
    "of securities* — so either test can carry the window."
)

cap1, cap2, cap3, cap4 = st.columns(4)
with cap1:
    st.metric("$1,000,000 floor", f"${result.cap_floor:,.0f}")
with cap2:
    st.metric("15% of total assets", f"${result.cap_15pct_assets:,.0f}")
with cap3:
    st.metric(
        "Dollar capacity",
        f"${result.dollar_capacity:,.0f}",
        help=f"Governed by: {result.governing_dollar_test}",
    )
with cap4:
    st.metric("Share capacity (15%)", f"{result.share_capacity:,}")

st.caption(f"Dollar capacity is governed by **{result.governing_dollar_test}**.")

# ---------------------------------------------------------------------------
# Current window
# ---------------------------------------------------------------------------

st.divider()
st.header("🎯 Measurement Window")
st.caption(
    f"Consecutive 12-month period: **{result.window_start.isoformat()}** (exclusive) "
    f"→ **{result.window_end.isoformat()}** (inclusive)."
)

if result.is_compliant:
    st.success(
        f"✅ **Within the Rule 701 cap** — carried by {result.compliant_via}."
    )
else:
    st.error(
        "❌ **Over the Rule 701 cap.** This window exceeds both the dollar test and "
        "the share test. Issuances beyond the cap are not exempt under Rule 701 and "
        "need a different exemption."
    )

w1, w2, w3, w4 = st.columns(4)
with w1:
    st.metric("Aggregate sales price", f"${result.aggregate_sales_price:,.0f}")
with w2:
    st.metric(
        "Dollar headroom",
        f"${result.dollar_headroom:,.0f}",
        delta=None if result.dollar_headroom >= 0 else "over cap",
        delta_color="inverse",
    )
with w3:
    st.metric("Aggregate shares", f"{result.aggregate_shares:,}")
with w4:
    st.metric(
        "Share headroom",
        f"{result.share_headroom:,}",
        delta=None if result.share_headroom >= 0 else "over cap",
        delta_color="inverse",
    )

headroom = max_additional_option_grant(inputs, exercise_price=float(planned_strike))
if headroom is not None:
    st.info(
        f"💡 At a **${planned_strike:,.2f}** exercise price, roughly "
        f"**{headroom:,} additional option shares** could be granted today before the "
        f"more permissive of the two tests is exhausted."
    )

# ---------------------------------------------------------------------------
# Disclosure trigger
# ---------------------------------------------------------------------------

st.divider()
st.header("📄 Enhanced Disclosure — Rule 701(e)")

if result.disclosure_triggered:
    st.warning(
        f"📋 **Triggered.** Aggregate sales price of "
        f"${result.aggregate_sales_price:,.0f} exceeds the "
        f"${DISCLOSURE_THRESHOLD:,.0f} threshold by "
        f"**${result.amount_over_disclosure_threshold:,.0f}** "
        f"(first crossed in the window ending "
        f"{result.disclosure_trigger_date.isoformat() if result.disclosure_trigger_date else 'n/a'}).\n\n"
        "The issuer must deliver, a reasonable period **before** sale: a copy of the "
        "plan, risk factors, and financial statements (balance sheet dated no more "
        "than 180 days before sale, plus income statements for the two prior fiscal years)."
    )
else:
    remaining = DISCLOSURE_THRESHOLD - result.aggregate_sales_price
    st.success(
        f"✅ **Not triggered.** ${remaining:,.0f} of room remains before the "
        f"${DISCLOSURE_THRESHOLD:,.0f} enhanced-disclosure threshold."
    )

# ---------------------------------------------------------------------------
# Rolling windows
# ---------------------------------------------------------------------------

if result.window_checks:
    st.divider()
    st.header("🔁 Every Consecutive 12-Month Window")
    st.caption(
        "Rule 701 tests **any** consecutive 12-month period. A plan can pass a "
        "calendar-year test and still breach a rolling window — this table checks "
        "a window ending at each issuance date plus your measurement date."
    )

    rows = []
    for w in result.window_checks:
        rows.append(
            {
                "Window end": w.window_end.isoformat(),
                "Window start": w.window_start.isoformat(),
                "Sales price": f"${w.aggregate_sales_price:,.0f}",
                "Shares": f"{w.aggregate_shares:,}",
                "Dollar test": "✅" if w.within_dollar_cap else "❌",
                "Share test": "✅" if w.within_share_cap else "❌",
                "Status": "✅ Within cap" if w.is_compliant else "❌ Over cap",
                "$10M disclosure": "📋 Required" if w.disclosure_triggered else "",
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    breaches = [w for w in result.window_checks if not w.is_compliant]
    if breaches:
        st.error(
            f"❌ **{len(breaches)} window(s) breach the cap.** Worst: the period ending "
            f"{result.worst_window.window_end.isoformat()} with "
            f"${result.worst_window.aggregate_sales_price:,.0f} across "
            f"{result.worst_window.aggregate_shares:,} shares."
        )

# ---------------------------------------------------------------------------
# Per-issuance valuation
# ---------------------------------------------------------------------------

if result.valued_issuances:
    st.divider()
    st.header("🔍 How Each Issuance Was Counted")

    rows = []
    for v in result.valued_issuances:
        i = v.issuance
        in_window = result.window_start < i.issuance_date <= result.window_end
        rows.append(
            {
                "Date": i.issuance_date.isoformat(),
                "Type": i.issuance_type,
                "Recipient": i.recipient_label,
                "Shares": f"{i.shares:,}",
                "Counted as": f"${v.sales_price:,.2f}",
                "In window?": "✅" if in_window else "—",
                "Basis": v.valuation_basis,
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# Warnings
# ---------------------------------------------------------------------------

if result.warnings:
    st.divider()
    st.header("⚠️ Compliance Notes")
    for w in result.warnings:
        st.warning(w)

# ---------------------------------------------------------------------------
# References
# ---------------------------------------------------------------------------

st.divider()
with st.expander("📚 Statutory + regulatory references"):
    st.markdown(
        """
- **Securities Act of 1933 §3(b)** — statutory authority for Rule 701
- **Rule 701(b)** — available only to issuers NOT subject to Exchange Act §13 or §15(d) reporting
- **Rule 701(c)** — eligible recipients: employees, directors, general partners, trustees,
  officers, and consultants/advisors who are natural persons providing bona fide services
- **Rule 701(d)(2)** — 12-month cap: greatest of $1,000,000; 15% of total assets;
  or 15% of the outstanding amount of the class
- **Rule 701(d)(3)(ii)** — **options are counted at the time of grant, using the exercise
  price** (not at exercise, not at FMV)
- **Rule 701(e)** — enhanced disclosure once aggregate sales price in any consecutive
  12-month period exceeds **$10,000,000** (raised from $5M by the Economic Growth,
  Regulatory Relief and Consumer Protection Act of 2018)
- **Rule 701(g)** — securities issued are **restricted securities**; resale under Rule 144
- **Form S-8** — the registration path a reporting company uses instead

**What this tool does not model:**

- **State Blue Sky compliance.** Rule 701 is a *federal* exemption only. NSMIA does not
  preempt state law for private-company issuances, so a separate state exemption is needed
  in every state where a recipient resides.
- **Rule 144 resale mechanics** for the restricted shares that result.
- Consultant/advisor eligibility conditions beyond the natural-person test.
- The valuation convention for RSUs is grant-date FMV; the rule text addresses options and
  deferred-compensation elections expressly but not RSUs, and practitioners differ. Confirm
  with counsel before relying on it.

⚠️ **Planning tool, not legal advice.** Rule 701 compliance failures can create rescission
rights for recipients. Confirm sizing with securities counsel before granting.
"""
    )
