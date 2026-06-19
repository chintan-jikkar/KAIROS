"""Cached live quote fetcher shared by the Overview and Markets pages."""
import streamlit as st
import yfinance as yf


@st.cache_data(ttl=60)
def fetch_quote(ticker: str) -> dict | None:
    try:
        df = yf.download(ticker, period="2d", interval="1d", auto_adjust=True, progress=False)
        if len(df) < 2:
            return None
        close = df["Close"].squeeze()
        last, prev = float(close.iloc[-1]), float(close.iloc[-2])
        return {"price": last, "change": last - prev, "change_pct": (last - prev) / prev * 100}
    except Exception:
        return None
