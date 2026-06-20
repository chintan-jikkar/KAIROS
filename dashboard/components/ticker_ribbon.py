"""Persistent scrolling ticker strip, fixed to the bottom of every page.
See docs/superpowers/specs/2026-06-20-ticker-ribbon-design.md for the design.
"""
import json
from pathlib import Path

import streamlit as st

from dashboard.components.market_quotes import fetch_quote

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

INDEX_TICKERS = [
    ("NIFTY 50", "^NSEI"), ("BANK NIFTY", "^NSEBANK"), ("INDIA VIX", "^INDIAVIX"),
    ("USD/INR", "INR=X"), ("S&P 500", "^GSPC"), ("NASDAQ", "^IXIC"),
    ("VIX", "^VIX"), ("DOW", "^DJI"), ("EUR/USD", "EURUSD=X"),
    ("GBP/USD", "GBPUSD=X"), ("USD/JPY", "JPY=X"),
]


def _active_universe_tickers() -> list[tuple[str, str]]:
    cache_path = PROJECT_ROOT / "config" / "universe_cache.json"
    if not cache_path.exists():
        return []
    try:
        universe = json.loads(cache_path.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    return [(item["symbol"], f"{item['symbol']}.NS") for item in universe if "symbol" in item]


def gather_ticker_items() -> list[dict]:
    """Pure data-gathering, separated from rendering so it's testable without
    a running Streamlit context. Skips any symbol fetch_quote can't resolve —
    a scrolling ribbon has no good way to show a partial/broken entry."""
    items = []
    for label, ticker in INDEX_TICKERS + _active_universe_tickers():
        q = fetch_quote(ticker)
        if q is None:
            continue
        items.append({"label": label, "price": q["price"], "change_pct": q["change_pct"]})
    return items


def render_ticker_ribbon():
    items = gather_ticker_items()
    if not items:
        return

    def _item_html(item: dict) -> str:
        cls = "positive" if item["change_pct"] >= 0 else "negative"
        arrow = "▲" if item["change_pct"] >= 0 else "▼"
        return (
            f'<span class="ticker-item">'
            f'<span style="color:var(--text-secondary);font-weight:600;">{item["label"]}</span> '
            f'<span class="kairos-mono">{item["price"]:,.2f}</span> '
            f'<span class="kairos-mono {cls}">{arrow} {item["change_pct"]:+.2f}%</span>'
            f'</span>'
        )

    track_items = "".join(_item_html(i) for i in items)
    st.markdown(
        f'<div class="ticker-ribbon"><div class="ticker-track">{track_items}{track_items}</div></div>',
        unsafe_allow_html=True,
    )
