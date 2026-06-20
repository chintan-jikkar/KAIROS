"""Timezone-aware market-hours status for NSE (India) and US equities."""
from datetime import datetime, time

import pytz
import streamlit as st

IST = pytz.timezone("Asia/Kolkata")
EASTERN = pytz.timezone("America/New_York")

NSE_OPEN, NSE_CLOSE = time(9, 15), time(15, 30)
US_OPEN, US_CLOSE = time(9, 30), time(16, 0)
CLOSING_SOON_MINUTES = 30


def _status_for(now_local: datetime, open_t: time, close_t: time) -> tuple[str, str]:
    """Returns (status, label). status: open | closing_soon | closed | weekend."""
    if now_local.weekday() >= 5:
        return "weekend", "Closed (weekend)"

    now_t = now_local.time()
    if now_t < open_t or now_t > close_t:
        return "closed", "Closed"

    minutes_to_close = (close_t.hour * 60 + close_t.minute) - (now_t.hour * 60 + now_t.minute)
    if minutes_to_close <= CLOSING_SOON_MINUTES:
        return "closing_soon", f"Closing in {minutes_to_close} min"
    return "open", "Open"


def get_market_status(market: str) -> dict:
    if market == "INDIA":
        now_local = datetime.now(IST)
        status, label = _status_for(now_local, NSE_OPEN, NSE_CLOSE)
        hours = "09:15–15:30 IST"
    else:
        now_local = datetime.now(EASTERN)
        status, label = _status_for(now_local, US_OPEN, US_CLOSE)
        hours = "09:30–16:00 ET"
    return {"status": status, "label": label, "hours": hours, "local_time": now_local.strftime("%H:%M")}


def _market_status_html(market: str) -> str:
    info = get_market_status(market)
    colors = {
        "open": ("var(--accent-emerald)", "rgba(0,245,160,0.08)", "rgba(0,245,160,0.3)"),
        "closing_soon": ("var(--accent-amber)", "rgba(255,179,71,0.1)", "rgba(255,179,71,0.4)"),
        "closed": ("var(--text-muted)", "rgba(255,255,255,0.04)", "var(--border-glass)"),
        "weekend": ("var(--text-muted)", "rgba(255,255,255,0.04)", "var(--border-glass)"),
    }
    color, bg, border = colors[info["status"]]
    dot = "●" if info["status"] in ("open", "closing_soon") else "○"
    return (
        f'<span style="display:inline-flex;align-items:center;gap:6px;font-size:11px;'
        f'padding:4px 10px;border-radius:6px;background:{bg};border:0.5px solid {border};color:{color};">'
        f'{dot} {market} {info["label"]} &middot; {info["hours"]}</span>'
    )


def render_market_status_badge(market: str):
    st.markdown(_market_status_html(market), unsafe_allow_html=True)


def render_market_status_row(markets: list[str]):
    """Multiple badges in one tight, left-aligned flex row instead of separate
    equal-width columns (which stretches narrow badges across wide gaps)."""
    badges = "".join(_market_status_html(m) for m in markets)
    st.markdown(f'<div style="display:flex;gap:10px;">{badges}</div>', unsafe_allow_html=True)
