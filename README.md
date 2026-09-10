# EquityComp Calculator

Open-source web app for equity compensation tax calculations.

**Live demo:** [equitycomp.streamlit.app](https://equitycomp.streamlit.app)<br>
**Author:** Priyanka Upreti — CEPI Equity Compensation Associate (ECA) Candidate<br>
**Source:** [github.com/priyanka-upreti/equitycomp](https://github.com/priyanka-upreti/equitycomp)<br>
**Subscribe:** [Equity Comp Gotchas newsletter on LinkedIn](https://www.linkedin.com/build-relation/newsletter-follow?entityUrn=7476698423992270848)

## What it does

A multi-module interactive web app that helps employees + practitioners understand the tax + decision implications of their equity grants. Each module accepts grant details and shows the math step-by-step, with the IRC sections + ASC topics cited inline.

## Modules

| Module | What it calculates | IRC / ASC reference |
|---|---|---|
| **ISO Exercise Modeler** | AMT preference, dual basis (regular vs AMT), QD vs DD outcomes at sale | IRC §422, §56(b)(3), §1.421-1 |
| **ESPP Calculator** | Look-back math, $25K limit, cascading anchor reset, QD lesser-of formula, DD treatment. Auto-fills FMVs from a ticker symbol. | IRC §423(b)(1)–(8), §423(c) |
| **§83(b) Decision Tool** | Net tax savings vs forfeiture risk, breakeven forfeit probability, Form 15620 filing procedure | IRC §83(b); Form 15620 |
| **RSU Vest + Sell-to-Cover** | Net shares retained, withholding rates, cost basis tracking | §409A short-term deferral; ASU 2016-09 |
| **§16 Form 4 Tracker** | 2-business-day deadline + short-swing exposure window | SEC §16(a), §16(b); SOX §403 |
| **Rule 701 Sizing Calculator** | 12-month cap (greatest of $1M / 15% assets / 15% outstanding), rolling-window testing, $10M enhanced-disclosure trigger | Securities Act §3(b); Rule 701(b)–(e) |

## Why this exists

Most equity comp calculations live in spreadsheets that are hard to share or verify. This is a public, free, open-source alternative that any employee can use to understand their own grants — and any practitioner can use as a quick reference. All math is validated against worked examples in the CEP reference textbooks (Stock Options Book, Selected Issues, Consider Your Options, Equity Alternatives).

## Disclaimer

This tool is for **educational + planning purposes only**. It does not constitute tax, legal, or investment advice. Tax outcomes depend on individual facts + circumstances. Always consult a qualified tax professional before making decisions about equity compensation.

## Tech stack

- Python 3.11
- Streamlit (UI framework)
- NumPy, SciPy (math)
- pandas (data tables)
- pytest (test suite)

## Local development

```bash
# Clone the repo
git clone https://github.com/priyanka-upreti/equitycomp.git
cd equitycomp

# Create + activate virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run streamlit_app.py
```

App opens at `http://localhost:8501`.

## License

MIT — free to use, modify, distribute.
