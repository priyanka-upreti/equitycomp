"""EquityComp Calculator — Home Page.

Multi-module Streamlit app for equity-comp tax + decision calculations.
Each module lives in pages/ and appears in the sidebar automatically.
"""

import streamlit as st

st.set_page_config(
    page_title="EquityComp Calculator",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📊 EquityComp Calculator")
st.subheader("Open-source equity compensation tax + decision tools")

st.markdown(
    """
Welcome! This is a free, open-source calculator for **employee equity compensation**.
Each tool walks you through the math — citing the relevant **IRC sections** + **ASC topics** — so
you understand what's happening to your grant at every stage.

**Pick a tool from the sidebar** to get started.
"""
)

st.divider()

col_a, col_b, col_c = st.columns(3)

with col_a:
    st.markdown("### 🎯 ISO Exercise Modeler")
    st.markdown(
        """
Model an **Incentive Stock Option** (ISO) exercise.
See AMT preference, dual basis, and Qualifying vs Disqualifying Disposition outcomes side-by-side.

**Try it →** sidebar: *ISO Exercise Modeler*
"""
    )

with col_b:
    st.markdown("### 🛒 ESPP Calculator")
    st.markdown(
        """
Model an **Employee Stock Purchase Plan** (§423) purchase.
Includes look-back, $25K limit, and Qualifying vs Disqualifying Disposition math.

**Coming soon**
"""
    )

with col_c:
    st.markdown("### ✍️ §83(b) Decision Tool")
    st.markdown(
        """
Should you file a **§83(b) election** on your restricted stock?
See net tax savings vs forfeiture risk, plus a sample election letter.

**Coming soon**
"""
    )

st.write("")  # vertical spacer between rows

col_d, col_e, col_f = st.columns(3)

with col_d:
    st.markdown("### 📅 RSU Vest + Sell-to-Cover")
    st.markdown(
        """
Model an **RSU vest event** with sell-to-cover. Calculates net shares retained,
withholding (federal supplemental + state + FICA), and cost basis tracking for sale.

**Coming soon**
"""
    )

with col_e:
    st.markdown("### 🛡️ §16 Form 4 Tracker")
    st.markdown(
        """
Track **insider transactions** under SEC §16. Calculates the 2-business-day
filing deadline + 6-month short-swing exposure window per §16(b).

**Coming soon**
"""
    )

with col_f:
    st.markdown("### 💡 Suggest a Tool")
    st.markdown(
        """
What equity-comp calculation do you wish existed?

[Open an issue on GitHub →](https://github.com/priyanka-upreti/equitycomp/issues)
or DM on [LinkedIn](https://www.linkedin.com/in/priyankaupreti1998).
"""
    )

st.divider()

st.markdown(
    """
### About

**Built by:** Priyanka Upreti — CEPI Equity Compensation Associate (ECA) Candidate ([GitHub](https://github.com/priyanka-upreti/equitycomp))

**Validated against:** Stock Options Book (NCEO, 24th ed.), Consider Your Options (Kaye Thomas, 2019),
Selected Issues in Equity Compensation (NCEO, 20th ed.), Equity Alternatives (NCEO, 21st ed.).

**Disclaimer:** This tool is for **educational + planning purposes only**. It does not constitute tax,
legal, or investment advice. Tax outcomes depend on individual facts + circumstances. Always consult
a qualified tax professional before making decisions about equity compensation.

---

### 📰 Stay in the loop

Subscribe to **Equity Comp Gotchas** — a LinkedIn newsletter on the counter-intuitive corners of equity compensation.

[Subscribe on LinkedIn →](https://www.linkedin.com/build-relation/newsletter-follow?entityUrn=7476698423992270848)
"""
)
