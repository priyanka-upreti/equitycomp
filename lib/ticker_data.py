"""Ticker symbol → historical price fetcher.

Uses yfinance (unofficial Yahoo Finance API) to pull daily closing prices for a
given ticker and date range. Falls back to nearest previous trading day if the
requested date is a weekend / holiday.

Cached per (ticker, start_date, end_date) tuple so multiple lookups within the
same offering period only hit Yahoo once per session.

The primary use is auto-populating ESPP FMV inputs (offering start, purchase
dates, sale date) based on the actual historical price of a publicly-traded
company's stock. If the ticker is invalid, private, or too new to have data on
the requested date, the caller falls back to manual entry.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import pandas as pd
import streamlit as st


class TickerFetchError(Exception):
    """Raised when we can't get price data for a ticker + date range."""


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_close_prices(ticker: str, start_date: date, end_date: date) -> pd.Series:
    """Return daily closing prices for the ticker over [start_date, end_date].

    Indexed by date (pandas DatetimeIndex, tz-naive). Values are USD closing
    prices. Weekends / holidays are absent from the index; the caller should
    use `get_price_on_or_before` to resolve non-trading days.

    Raises TickerFetchError with a human-readable message on any failure.
    """
    try:
        import yfinance as yf
    except ImportError as e:
        raise TickerFetchError("yfinance not installed on this deployment.") from e

    ticker = ticker.strip().upper()
    if not ticker:
        raise TickerFetchError("Empty ticker symbol.")

    # yfinance's `end` is exclusive; pad by 5 days to be safe
    end_padded = end_date + timedelta(days=5)

    try:
        yf_ticker = yf.Ticker(ticker)
        df = yf_ticker.history(
            start=start_date.isoformat(),
            end=end_padded.isoformat(),
            interval="1d",
            auto_adjust=False,
            actions=False,
        )
    except Exception as e:
        raise TickerFetchError(f"Yahoo Finance request failed: {type(e).__name__}") from e

    if df is None or df.empty:
        raise TickerFetchError(
            f"No price data returned for '{ticker}' between "
            f"{start_date.isoformat()} and {end_date.isoformat()}. "
            f"Check ticker spelling; only US-listed public tickers work here."
        )

    if "Close" not in df.columns:
        raise TickerFetchError(f"Unexpected data shape from Yahoo for '{ticker}'.")

    closes = df["Close"].copy()
    # tz-strip so we can compare with date objects cleanly
    try:
        closes.index = closes.index.tz_localize(None)
    except (TypeError, AttributeError):
        pass
    closes.index = pd.to_datetime(closes.index).date
    closes = pd.Series(closes.values, index=closes.index, name=ticker)
    return closes


def get_price_on_or_before(closes: pd.Series, target: date) -> Optional[float]:
    """Return the closing price on `target` or the most recent trading day
    before it. Returns None if there's no data on or before target.
    """
    if closes is None or len(closes) == 0:
        return None
    # Filter down to entries at or before target date
    eligible = closes[closes.index <= target]
    if len(eligible) == 0:
        return None
    return float(eligible.iloc[-1])


def get_ticker_info_safe(ticker: str) -> Optional[dict]:
    """Attempt to fetch basic ticker info (company name, currency). Returns
    None on any failure. Used only to enrich the UI — never affects math."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker.strip().upper())
        # Fast lookup that avoids the slow .info property when possible
        return {
            "name": t.info.get("shortName") or t.info.get("longName") or ticker.upper(),
            "currency": t.info.get("currency", "USD"),
        }
    except Exception:
        return None
