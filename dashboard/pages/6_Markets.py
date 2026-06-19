"""Page 6 — Markets: India / US / FX overview tabs."""
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="KAIROS · Markets", page_icon="⚡", layout="wide")
st.markdown(f"<style>{(Path(__file__).parent.parent / 'style.css').read_text()}</style>", unsafe_allow_html=True)

st.markdown('<h2 class="kairos-heading">Markets</h2>', unsafe_allow_html=True)


@st.cache_data(ttl=60)
def fetch_quote(ticker: str) -> dict | None:
    import yfinance as yf
    try:
        df = yf.download(ticker, period="2d", interval="1d", auto_adjust=True, progress=False)
        if len(df) < 2:
            return None
        last, prev = float(df["Close"].iloc[-1]), float(df["Close"].iloc[-2])
        return {"price": last, "change": last - prev, "change_pct": (last - prev) / prev * 100}
    except Exception:
        return None


def render_quote_card(label: str, ticker: str, prefix: str = ""):
    q = fetch_quote(ticker)
    if q is None:
        st.markdown(
            f'<div class="glass-card"><p class="kpi-label">{label}</p><p class="kairos-mono">–</p></div>',
            unsafe_allow_html=True,
        )
        return
    sign_class = "positive" if q["change"] >= 0 else "negative"
    arrow = "▲" if q["change"] >= 0 else "▼"
    st.markdown(
        f"""
        <div class="glass-card">
            <p class="kpi-label">{label}</p>
            <p class="kairos-mono" style="font-size:20px;margin:0 0 4px;">{prefix}{q['price']:,.2f}</p>
            <p class="kairos-mono {sign_class}" style="font-size:12px;">{arrow} {q['change']:+,.2f} ({q['change_pct']:+.2f}%)</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


tab_india, tab_us, tab_fx = st.tabs(["India", "US", "FX"])

with tab_india:
    cols = st.columns(4)
    with cols[0]:
        render_quote_card("Nifty 50", "^NSEI")
    with cols[1]:
        render_quote_card("Bank Nifty", "^NSEBANK")
    with cols[2]:
        render_quote_card("India VIX", "^INDIAVIX")
    with cols[3]:
        render_quote_card("USD/INR", "INR=X")

with tab_us:
    cols = st.columns(4)
    with cols[0]:
        render_quote_card("S&P 500", "^GSPC")
    with cols[1]:
        render_quote_card("Nasdaq", "^IXIC")
    with cols[2]:
        render_quote_card("VIX", "^VIX")
    with cols[3]:
        render_quote_card("Dow Jones", "^DJI")

with tab_fx:
    cols = st.columns(4)
    with cols[0]:
        render_quote_card("USD/INR", "INR=X")
    with cols[1]:
        render_quote_card("EUR/USD", "EURUSD=X")
    with cols[2]:
        render_quote_card("GBP/USD", "GBPUSD=X")
    with cols[3]:
        render_quote_card("USD/JPY", "JPY=X")
    st.caption("FX trading routed via NSE Currency Derivatives (India) or OANDA (US) — Phase 7.")
