"""Cached live quote fetcher shared by the Overview and Markets pages."""
import math

import streamlit as st
import yfinance as yf


@st.cache_data(ttl=60)
def fetch_quote(ticker: str) -> dict | None:
    try:
        df = yf.download(ticker, period="5d", interval="1d", auto_adjust=True, progress=False)
        close = df["Close"].squeeze().dropna()
        if len(close) < 2:
            return None
        last, prev = float(close.iloc[-1]), float(close.iloc[-2])
        if math.isnan(last) or math.isnan(prev) or prev == 0:
            return None
        return {"price": last, "change": last - prev, "change_pct": (last - prev) / prev * 100}
    except Exception:
        return None
