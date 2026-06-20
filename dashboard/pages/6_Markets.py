"""Page 6 — Markets: India / US / FX overview, merged screener browser, watchlist, deep-dive, news."""
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.components.sidebar import render_sidebar
from dashboard.components.header import render_header
from dashboard.components.market_quotes import fetch_quote
from dashboard.components.market_hours import render_market_status_badge
from dashboard.components.manual_trade import render_manual_paper_trade_button
from dashboard.components.news_feed import render_news_list
from dashboard.components.equity_curve import KAIROS_CHART_LAYOUT
from dashboard.db import get_session
from database.watchlist import add_to_watchlist, remove_from_watchlist, get_watchlist
from data.market_data import fetch_india_daily

st.set_page_config(page_title="KAIROS · Markets", page_icon="⚡", layout="wide")
st.markdown(f"<style>{(Path(__file__).parent.parent / 'style.css').read_text()}</style>", unsafe_allow_html=True)

render_sidebar("Markets")
db = get_session()
render_header()

top_row = st.columns([3, 2])
with top_row[0]:
    st.markdown('<h2 class="kairos-heading">Markets</h2>', unsafe_allow_html=True)
with top_row[1]:
    hc1, hc2 = st.columns(2)
    with hc1:
        render_market_status_badge("INDIA")
    with hc2:
        render_market_status_badge("US")

# --------------------------------------------------------------------------- #
# Watchlist — pinned items reserved at a glance, persisted in the DB           #
# --------------------------------------------------------------------------- #

st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin:14px 0 10px;">On your radar</p>', unsafe_allow_html=True)

watchlist = get_watchlist(db, market="INDIA")
if watchlist:
    wl_cols = st.columns(min(len(watchlist), 6))
    for col, item in zip(wl_cols, watchlist):
        with col:
            q = fetch_quote(f"{item.symbol}.NS")
            price_text = f"₹{q['price']:,.2f}" if q else "–"
            chg_class = "positive" if (q and q["change_pct"] >= 0) else "negative" if q else "neutral"
            chg_text = f"{q['change_pct']:+.2f}%" if q else ""
            st.markdown(
                f"""
                <div class="glass-card" style="padding:11px 13px;">
                    <p style="font-size:12px;font-weight:600;margin:0 0 6px;">{item.symbol}</p>
                    <p class="kairos-mono" style="font-size:15px;margin:0 0 2px;">{price_text}</p>
                    <p class="kairos-mono {chg_class}" style="font-size:11px;margin:0;">{chg_text}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Remove", key=f"rm_wl_{item.item_id}", use_container_width=True):
                remove_from_watchlist(db, item.item_id)
                st.rerun()
else:
    st.caption("Nothing pinned yet — add symbols from the screener table below to keep them here always.")

with st.expander("Add to watchlist"):
    ac1, ac2 = st.columns([3, 1])
    with ac1:
        new_symbol = st.text_input("Symbol", placeholder="e.g. RELIANCE", label_visibility="collapsed", key="wl_add_input")
    with ac2:
        if st.button("Pin", use_container_width=True) and new_symbol:
            add_to_watchlist(db, new_symbol.strip().upper(), market="INDIA")
            st.rerun()

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
tab_india, tab_us, tab_fx = st.tabs(["India", "US", "FX"])


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


# --------------------------------------------------------------------------- #
# India — quotes + merged screener browser + deep-dive                         #
# --------------------------------------------------------------------------- #

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

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:8px;">Screener universe</p>', unsafe_allow_html=True)

    rc1, rc2 = st.columns([4, 1])
    with rc2:
        run_clicked = st.button("Re-run screener", use_container_width=True)

    import json
    cache_path = Path(__file__).parent.parent.parent / "config" / "universe_cache.json"

    if run_clicked:
        with st.spinner("Screening India universe… (runs in the engine process, can take ~30s)"):
            from dashboard.components.engine_bridge import run_screener
            full_results, err = run_screener(top_n=None)
            if err:
                st.error(err)
            else:
                top6 = sorted(full_results, key=lambda r: r["score"], reverse=True)[:6]
                if top6:
                    cache_path.write_text(json.dumps(top6, indent=2))
                st.session_state["_screener_full_results"] = full_results
                if full_results:
                    st.success(f"Screener ran — {len(full_results)} of ~25 pool stocks currently qualify, top 6 set as the active trading universe.")
                else:
                    st.warning("Screener ran but 0 stocks currently meet the live filter criteria (ATR%, volume, RSI range). This can happen briefly intraday or outside market hours — try again later.")

    full_results = st.session_state.get("_screener_full_results", None)
    active_universe_symbols = {s["symbol"] for s in json.loads(cache_path.read_text())} if cache_path.exists() else set()

    if full_results:
        df = pd.DataFrame(full_results)
        df["active"] = df["symbol"].apply(lambda s: "●" if s in active_universe_symbols else "")
        display_df = df.rename(columns={
            "active": "Active", "symbol": "Symbol", "price": "Price", "atr_pct": "ATR%", "vol_ratio": "Vol ratio",
            "rsi14": "RSI14", "beta": "Beta", "assigned_strategy": "Strategy", "score": "Score",
        })[["Active", "Symbol", "Price", "ATR%", "Vol ratio", "RSI14", "Beta", "Strategy", "Score"]]

        event = st.dataframe(
            display_df, use_container_width=True, height=380,
            on_select="rerun", selection_mode="single-row", key="markets_screener_table",
        )
        selected_rows = event.selection.get("rows", []) if hasattr(event, "selection") else []
        st.caption("● marks stocks in the currently deployed top-6 universe. Click any row to open its deep dive below.")
    else:
        st.info("No screener data loaded yet this session. Click 'Re-run screener' to evaluate the full India universe.")
        selected_rows = []
        df = pd.DataFrame()

    if selected_rows and not df.empty:
        sel = df.iloc[selected_rows[0]]
        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)

        dd1, dd2 = st.columns([1, 1.4])
        with dd1:
            st.markdown(
                f"""
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                    <span style="font-size:16px;font-weight:600;">{sel['symbol']}</span>
                    <span class="badge badge-long">{sel['assigned_strategy']}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            metric_pairs = [
                ("Price", f"₹{sel['price']:,.2f}"), ("Score", f"{sel['score']:.0f}/100"),
                ("ATR %", f"{sel['atr_pct']:.2f}%"), ("Vol ratio", f"{sel['vol_ratio']:.2f}x"),
                ("RSI 14", f"{sel['rsi14']:.1f}"), ("Beta", f"{sel['beta']:.2f}"),
            ]
            mcols = st.columns(2)
            for i, (label, val) in enumerate(metric_pairs):
                with mcols[i % 2]:
                    st.markdown(
                        f'<p class="kpi-label" style="margin:8px 0 2px;">{label}</p>'
                        f'<p class="kairos-mono" style="font-size:14px;">{val}</p>',
                        unsafe_allow_html=True,
                    )

            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            already_pinned = sel["symbol"] in {w.symbol for w in watchlist}
            if already_pinned:
                st.caption("Already on your watchlist.")
            elif st.button("Add to watchlist", key=f"pin_{sel['symbol']}", use_container_width=True):
                add_to_watchlist(db, sel["symbol"], market="INDIA")
                st.rerun()

            render_manual_paper_trade_button(sel["symbol"], market="INDIA", current_price=sel["price"])

        with dd2:
            price_df = fetch_india_daily(sel["symbol"], period="3mo")
            if not price_df.empty:
                fig = go.Figure(go.Scatter(
                    x=price_df.index, y=price_df["close"], mode="lines",
                    line=dict(color="#F0C040", width=2), fill="tozeroy",
                    fillcolor="rgba(240,192,64,0.1)",
                ))
                fig.update_layout(**KAIROS_CHART_LAYOUT, height=180)
                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

            st.markdown('<p style="font-size:12px;color:var(--text-secondary);margin:4px 0 8px;">Recent headlines</p>', unsafe_allow_html=True)
            render_news_list(f"{sel['symbol']}.NS", limit=4)

        st.markdown('</div>', unsafe_allow_html=True)

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
    st.caption("US screener universe lands in Phase 2 — manual paper trading and news are available per-symbol once that's wired up.")

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
