"""§16 Form 4 Compliance Tracker — Streamlit page.

Tracks Form 3/4 filing deadlines and §16(b) short-swing profit exposure for
insiders (officers, directors, 10% shareholders) of publicly-traded companies.
"""

from datetime import date

import pandas as pd
import streamlit as st

# Make lib/ importable regardless of how streamlit launches
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.section16_tracker import (  # noqa: E402
    Section16Inputs,
    Transaction,
    analyze_section16,
)


st.set_page_config(
    page_title="§16 Form 4 Tracker",
    page_icon="🛡️",
    layout="wide",
)

st.title("🛡️ §16 Form 4 Compliance Tracker")
st.markdown(
    "Track **Form 3** (initial ownership statement) + **Form 4** (2-business-day "
    "transaction reports) + **§16(b) short-swing profit exposure** (less-than-6-month "
    "purchase-sale matching) for §16 insiders (officers, directors, 10% shareholders)."
)

st.divider()

# ---------------------------------------------------------------------------
# Sidebar inputs
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("👤 Insider Info")
    company_ticker = st.text_input("Company ticker", value="ACME")
    insider_role = st.radio(
        "Role",
        options=["officer", "director", "ten_percent_holder"],
        format_func=lambda x: {
            "officer": "Officer",
            "director": "Director",
            "ten_percent_holder": "10% Shareholder",
        }[x],
    )
    insider_start_date = st.date_input(
        "Date became insider",
        value=date(2026, 1, 15),
        help="Form 3 due 10 calendar days from this date.",
    )

    st.divider()
    st.header("📅 Evaluation Date")
    as_of_date = st.date_input(
        "Evaluate compliance as of",
        value=date.today(),
        help="Deadlines will be compared to this date.",
    )

# ---------------------------------------------------------------------------
# Transaction editor
# ---------------------------------------------------------------------------

st.header("📝 Transaction Log")
st.caption(
    "Enter each §16-reportable transaction. Mark grants/exercises/vests from an "
    "approved comp plan as **Rule 16b-3 exempt** (they won't be matched for §16(b))."
)

default_transactions = pd.DataFrame(
    [
        {
            "Date": date(2026, 2, 1),
            "Type": "buy",
            "Shares": 1000,
            "Price/share ($)": 50.00,
            "16b-3 Exempt": False,
            "Description": "Open-market purchase",
        },
        {
            "Date": date(2026, 3, 15),
            "Type": "grant",
            "Shares": 5000,
            "Price/share ($)": 0.00,
            "16b-3 Exempt": True,
            "Description": "RSA grant from approved plan",
        },
        {
            "Date": date(2026, 5, 15),
            "Type": "sell",
            "Shares": 1000,
            "Price/share ($)": 80.00,
            "16b-3 Exempt": False,
            "Description": "Open-market sale",
        },
    ]
)

edited_df = st.data_editor(
    default_transactions,
    num_rows="dynamic",
    use_container_width=True,
    hide_index=True,
    column_config={
        "Date": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
        "Type": st.column_config.SelectboxColumn(
            "Type",
            options=["buy", "sell", "grant", "exercise", "vest", "gift"],
        ),
        "Shares": st.column_config.NumberColumn(
            "Shares", min_value=1, step=100
        ),
        "Price/share ($)": st.column_config.NumberColumn(
            "Price/share ($)", min_value=0.0, step=0.01, format="$%.2f"
        ),
        "16b-3 Exempt": st.column_config.CheckboxColumn(
            "16b-3 Exempt",
            help="Grants/exercises/vests from an approved comp plan are exempt "
            "from §16(b) short-swing matching under Rule 16b-3.",
        ),
        "Description": st.column_config.TextColumn("Description"),
    },
    key="txn_editor",
)

# Convert dataframe to Transaction objects
transactions = []
for _, row in edited_df.iterrows():
    if pd.notna(row["Date"]) and row["Shares"] and row["Shares"] > 0:
        # Handle date type conversion
        d = row["Date"]
        if isinstance(d, str):
            d = date.fromisoformat(d)
        transactions.append(
            Transaction(
                date=d,
                transaction_type=row["Type"],
                shares=int(row["Shares"]),
                price_per_share=float(row["Price/share ($)"]),
                is_16b3_exempt=bool(row["16b-3 Exempt"]),
                description=str(row["Description"]) if pd.notna(row["Description"]) else "",
            )
        )

# ---------------------------------------------------------------------------
# Run analysis
# ---------------------------------------------------------------------------

inputs = Section16Inputs(
    insider_role=insider_role,
    insider_start_date=insider_start_date,
    company_ticker=company_ticker,
    transactions=transactions,
    as_of_date=as_of_date,
)
result = analyze_section16(inputs)

# ---------------------------------------------------------------------------
# Compliance summary metrics
# ---------------------------------------------------------------------------

st.divider()
st.header("📊 Compliance Summary")

sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)

with sum_col1:
    if result.form3_is_overdue:
        st.metric(
            "Form 3 status",
            "⚠️ Overdue",
            delta=f"{-result.form3_days_remaining} days late",
            delta_color="inverse",
        )
    else:
        st.metric(
            "Form 3 deadline",
            result.form3_deadline.isoformat(),
            delta=f"{result.form3_days_remaining} days remaining",
        )
with sum_col2:
    color = "inverse" if result.overdue_form4_count > 0 else "off"
    st.metric(
        "Overdue Form 4 filings",
        result.overdue_form4_count,
        delta="Action needed" if result.overdue_form4_count > 0 else "None",
        delta_color=color,
    )
with sum_col3:
    st.metric(
        "Upcoming Form 4 (≤2 days)",
        result.upcoming_form4_count,
    )
with sum_col4:
    st.metric(
        "§16(b) recoverable profit",
        f"${result.total_recoverable_profit:,.2f}",
        delta="Exposure" if result.total_recoverable_profit > 0 else "None",
        delta_color="inverse" if result.total_recoverable_profit > 0 else "off",
    )

# ---------------------------------------------------------------------------
# Form 3
# ---------------------------------------------------------------------------

st.divider()
st.header("📄 Form 3 — Initial Ownership Statement")

if result.form3_is_overdue:
    st.error(
        f"❌ **Form 3 OVERDUE** — deadline was **{result.form3_deadline.isoformat()}** "
        f"({-result.form3_days_remaining} days ago). Late filings trigger public disclosure "
        f"in the next proxy statement (Item 405 of Reg S-K) + potential SEC enforcement."
    )
else:
    st.success(
        f"✅ Form 3 due **{result.form3_deadline.isoformat()}** "
        f"({result.form3_days_remaining} days from evaluation date). "
        f"Required within **10 calendar days** of becoming a §16 insider."
    )

# ---------------------------------------------------------------------------
# Form 4
# ---------------------------------------------------------------------------

st.divider()
st.header("📄 Form 4 — Transaction Reports")
st.caption(
    "Each transaction (non-exempt or exempt) must be reported on Form 4 within "
    "**2 BUSINESS days** after the trade date. Late Form 4s are disclosed in Item 405 "
    "of the proxy statement + open the door to SEC enforcement (§32 penalties)."
)

if result.form4_filings:
    form4_rows = []
    pre_insider_count = 0
    for f in result.form4_filings:
        txn = f.transaction
        if f.is_pre_insider:
            status = "ℹ️ Pre-insider (no Form 4 required)"
            deadline_str = "—"
            days_str = "—"
            pre_insider_count += 1
        elif f.is_overdue:
            status = "❌ Overdue"
            deadline_str = f.deadline.isoformat()
            days_str = str(f.days_until_deadline)
        elif f.days_until_deadline is not None and 0 <= f.days_until_deadline <= 2:
            status = "⚠️ Due soon"
            deadline_str = f.deadline.isoformat()
            days_str = str(f.days_until_deadline)
        else:
            status = "✅ Not yet due"
            deadline_str = f.deadline.isoformat()
            days_str = str(f.days_until_deadline)
        form4_rows.append({
            "Txn date": txn.date.isoformat(),
            "Type": txn.transaction_type,
            "Shares": f"{txn.shares:,}",
            "Price": f"${txn.price_per_share:.2f}",
            "16b-3 Exempt": "✓" if txn.is_16b3_exempt else "",
            "Form 4 deadline": deadline_str,
            "Days until deadline": days_str,
            "Status": status,
        })
    st.dataframe(pd.DataFrame(form4_rows), use_container_width=True, hide_index=True)

    if pre_insider_count > 0:
        st.info(
            f"ℹ️ **{pre_insider_count} pre-insider transaction(s) shown.** These pre-date "
            f"your insider start ({insider_start_date.isoformat()}), so **no Form 4 filing "
            f"was required.** They ARE disclosed as part of your beneficial ownership on "
            f"**Form 3** (initial statement). Note: pre-insider purchases can still be "
            f"caught in the **§16(b) short-swing analysis below** if matched with post-insider "
            f"sales within 6 months (officer/director rule; stricter test for 10% holders per "
            f"*Foremost-McKesson v. Provident Securities Co.*, 423 U.S. 232 (1976))."
        )
else:
    st.info("No transactions logged yet.")

# ---------------------------------------------------------------------------
# §16(b) short-swing exposure
# ---------------------------------------------------------------------------

st.divider()
st.header("⚖️ §16(b) Short-Swing Profit Exposure")
st.caption(
    "Under §16(b), any purchase-sale (or sale-purchase) pair within **less than 6 months** "
    "creates a **strict-liability** disgorgement obligation — the company can recover the "
    "profit regardless of intent or actual insider info. Non-16b-3-exempt transactions only."
)

if result.short_swing_pairs:
    st.error(
        f"🚨 **${result.total_recoverable_profit:,.2f}** in potential §16(b) profit at risk "
        f"across {len(result.short_swing_pairs)} matched pair(s). Company (or shareholder "
        f"suing derivatively) may demand this profit be disgorged."
    )
    pair_rows = []
    for pair in result.short_swing_pairs:
        pair_rows.append({
            "Purchase date": pair.purchase.date.isoformat(),
            "Purchase $/sh": f"${pair.purchase.price_per_share:.2f}",
            "Sale date": pair.sale.date.isoformat(),
            "Sale $/sh": f"${pair.sale.price_per_share:.2f}",
            "Days between": pair.days_between,
            "Matched shares": f"{pair.matched_shares:,}",
            "Profit/share": f"${pair.profit_per_share:.2f}",
            "Recoverable": f"${pair.recoverable_profit:,.2f}",
        })
    st.dataframe(pd.DataFrame(pair_rows), use_container_width=True, hide_index=True)
else:
    st.success(
        "✅ No §16(b) exposure detected. Either no purchase-sale pairs exist within 6 months, "
        "all pairs are non-profitable, or all matching transactions are Rule 16b-3 exempt."
    )

# ---------------------------------------------------------------------------
# References
# ---------------------------------------------------------------------------

st.divider()
with st.expander("📚 Statutory + regulatory references"):
    st.markdown(
        """
### §16(a) — Reporting requirements
- **§16(a) of Securities Exchange Act of 1934** — Insider reporting mandate
- **Form 3** — Initial statement of beneficial ownership. Due **10 calendar days** after becoming insider (officer, director, or 10% shareholder).
- **Form 4** — Statement of changes. Due **2 business days** after transaction. Filed via SEC EDGAR.
- **Form 5** — Annual statement for transactions not required on Form 4 (e.g., certain small acquisitions, gifts). Due within 45 days after fiscal year-end.
- **Item 405 of Reg S-K** — Late filings must be disclosed in the proxy statement (public embarrassment)

### §16(b) — Short-swing profit rule
- **§16(b)** — Strict-liability disgorgement of profits from any purchase-sale (or sale-purchase) pair within **less than 6 months**
- No intent requirement — no insider info needed
- Recovery is by the COMPANY (or shareholder acting derivatively), not by SEC
- Two-year statute of limitations from the profit-taking transaction
- Applies to all "equity securities" including options, RSUs (once matured), preferred stock

### Pre-insider transactions + §16(b) — the tricky part
- **Form 4:** No obligation to file for transactions dated before becoming an insider (§16(a) reporting duty starts with insider status)
- **Form 3:** Discloses TOTAL beneficial ownership at insider start — includes shares from pre-insider transactions
- **§16(b) matching:**
  - **Officer/director:** SEC and courts have long swept pre-insider transactions into matching if within 6 months of a post-insider transaction. See discussion in *Foremost-McKesson v. Provident Securities Co.*, 423 U.S. 232 (1976).
  - **10% shareholder:** BOTH sides of the matched pair must occur while person is a 10% holder (per *Foremost-McKesson*). Pre-10%-holder purchases are safe.
  - This tool matches ALL non-exempt purchases and sales regardless of insider timing — conservative (may over-flag for 10% holders; under-inclusive vs. some edge cases). Apply legal judgment.

### Rule 16b-3 — Employee benefit plan exemption
- Grants of options, restricted stock, RSUs from an approved comp plan are exempt from §16(b) matching if:
  - Approved by the board (or comp committee) OR by shareholders
  - Held for 6 months (in the case of derivative securities being converted)
- **Critical exam concept:** Exempt grants don't count as §16(b) purchases; option exercises from an approved plan don't count either

### Rule 16a-1(a) — Beneficial ownership definition
- Pecuniary interest test — direct or indirect ability to profit
- Attribution rules for family members, trusts, partnerships

### Common §16 traps
- Broker-assisted cashless exercise on the SAME DAY = purchase (exercise) + sale = §16(b) match
- Section 83(b) election on early-exercised options → purchase for §16 purposes
- Gifts to family members can create attribution issues
- Termination of employment ≠ end of §16 status (still applies for 6 months post-termination if executive officer)

### V1 model simplifications (documented for transparency)
- Business day math skips weekends only (federal holidays not excluded — verify against SEC EDGAR calendar)
- Rule 16b-3 exemption is applied via user-marked checkbox — no automatic plan-lookup
- Doesn't model attribution to family members / trusts (V2)
- Doesn't handle multiple classes of equity (common vs preferred aggregation — V2)
- Doesn't detect broker-assisted same-day exercise-sale trap (V2)
- 6-month window is calendar-month math (Aug 31 + 6 months = Feb 28, not Feb 31)
"""
    )
