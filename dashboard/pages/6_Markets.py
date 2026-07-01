"""Page 6 — Markets: India / US / FX overview, merged screener browser, watchlist, deep-dive, news."""
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from dashboard.components.sidebar import render_sidebar
from dashboard.components.header import render_header
from dashboard.components.ticker_ribbon import render_ticker_ribbon
from dashboard.components.notifications import check_and_notify
from dashboard.components.market_quotes import fetch_quote, logo_url
from dashboard.components.market_hours import render_market_status_row
from dashboard.components.manual_trade import render_manual_paper_trade_button
from dashboard.components.news_feed import render_news_list
from dashboard.components.candlestick_chart import render_candlestick_chart
from dashboard.db import get_session
from database.watchlist import add_to_watchlist, remove_from_watchlist, get_watchlist
from database.trade_log import market_currency_symbol

st.set_page_config(page_title="KAIROS · Markets", page_icon="⚡", layout="wide")
st.markdown(f"<style>{(Path(__file__).parent.parent / 'style.css').read_text()}</style>", unsafe_allow_html=True)


@st.dialog("Chart")
def _render_fullscreen_chart_dialog(symbol: str, db, market: str = "INDIA"):
    render_candlestick_chart(symbol, db, market=market, key_prefix="full", height=560)
    if st.button("Close"):
        st.session_state["_fullscreen_chart_symbol"] = None
        st.rerun()


render_sidebar("Markets")
db = get_session()
check_and_notify(db)
render_header()
render_ticker_ribbon()

st.markdown('<h2 class="kairos-heading">Markets</h2>', unsafe_allow_html=True)
render_market_status_row(["INDIA", "US"])

# --------------------------------------------------------------------------- #
# Watchlist — pinned items reserved at a glance, persisted in the DB           #
# --------------------------------------------------------------------------- #

st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin:14px 0 10px;">On your radar</p>', unsafe_allow_html=True)

watchlist = get_watchlist(db, market="INDIA")
if watchlist:
    WATCHLIST_ROW_SIZE = 5
    for row_start in range(0, len(watchlist), WATCHLIST_ROW_SIZE):
        row_items = watchlist[row_start:row_start + WATCHLIST_ROW_SIZE]
        wl_cols = st.columns(WATCHLIST_ROW_SIZE)
        for col, item in zip(wl_cols, row_items):
            with col:
                q = fetch_quote(f"{item.symbol}.NS")
                price_text = f"₹{q['price']:,.2f}" if q else "–"
                chg_class = "positive" if (q and q["change_pct"] >= 0) else "negative" if q else "neutral"
                chg_text = f"{q['change_pct']:+.2f}%" if q else ""
                st.markdown(
                    f"""
                    <div class="glass-card" style="padding:11px 13px;">
                        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
                            <img src="{logo_url(item.symbol + '.NS')}" loading="lazy"
                                style="width:18px;height:18px;border-radius:4px;background:#fff;object-fit:contain;flex-shrink:0;"
                                onerror="this.style.display='none'"/>
                            <p style="font-size:12px;font-weight:600;margin:0;">{item.symbol}</p>
                        </div>
                        <p class="kairos-mono" style="font-size:15px;margin:0 0 2px;">{price_text}</p>
                        <p class="kairos-mono {chg_class}" style="font-size:11px;margin:0;">{chg_text}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button("Remove", key=f"rm_wl_{item.item_id}", use_container_width=True):
                    remove_from_watchlist(db, item.item_id)
                    st.rerun()
        # Fill any remaining slots in a short last row so cards don't stretch full-width
        for empty_col in wl_cols[len(row_items):]:
            with empty_col:
                st.empty()
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


STRATEGY_DIRECTION = {
    "RSI2_OVN": "LONG", "ORB_BRK": "LONG", "MOM_CONT": "LONG",
    "TREND_EMA": "LONG", "BB_MEANREV": "LONG",
    "DONCHIAN_BRK": "LONG", "SUPERTREND": "LONG",
}

SCREENER_COLUMNS = [
    ("", "28px"), ("Symbol", "1fr"), ("Price", "0.9fr"), ("Target", "0.9fr"), ("ATR%", "0.7fr"),
    ("Vol ratio", "0.8fr"), ("RSI14", "0.7fr"), ("Beta", "0.6fr"),
    ("Strategy", "1.1fr"), ("Score", "0.7fr"),
]
SCREENER_GRID_TEMPLATE = " ".join(w for _, w in SCREENER_COLUMNS)


def _target_text(row, currency_sym: str = "₹") -> str:
    """Target only shows for rows with an actual live signal firing today —
    'assigned strategy' means the regime fits, not that entry conditions are
    met right now, so most rows legitimately won't have one."""
    if not row.get("has_live_signal") or row.get("target_price") is None:
        return "–"
    return f"{currency_sym}{row['target_price']:,.2f}"


def _target_color_class(row) -> str:
    if not row.get("has_live_signal"):
        return "neutral"
    direction = STRATEGY_DIRECTION.get(row["assigned_strategy"], "LONG")
    return "positive" if direction == "LONG" else "negative"


def render_screener_table(
    df: pd.DataFrame,
    active_symbols: set[str],
    market: str = "INDIA",
    session_key: str = "_screener_selected_symbol",
) -> str | None:
    """Themed, click-anywhere-on-row replacement for st.dataframe. The canvas-
    rendered grid looked like a spreadsheet (no control over its styling) and
    row-selection only registered on a specific internal hotspot, not anywhere
    in the row. Each row is a real st.container so the invisible full-size
    button genuinely overlays the visual HTML (unlike stacking separate
    st.markdown calls, which render as siblings, not nested)."""
    currency_sym = market_currency_symbol(market)
    logo_ticker = lambda sym: sym + ".NS" if market == "INDIA" else sym
    sorted_df = df.sort_values("score", ascending=False).reset_index(drop=True)
    selected = st.session_state.get(session_key)

    with st.container(border=True, key=f"screener_table_outer_{market}"):
        header_html = "".join(f"<div>{label}</div>" for label, _ in SCREENER_COLUMNS)
        st.markdown(
            f'<div class="screener-row screener-header" '
            f'style="grid-template-columns:{SCREENER_GRID_TEMPLATE};">{header_html}</div>',
            unsafe_allow_html=True,
        )

        for _, row in sorted_df.iterrows():
            symbol = row["symbol"]
            is_active = symbol in active_symbols
            is_selected = symbol == selected
            row_html = (
                f'<div class="screener-row {"selected" if is_selected else ""}" '
                f'style="grid-template-columns:{SCREENER_GRID_TEMPLATE};">'
                f'<div>{"●" if is_active else ""}</div>'
                f'<div style="display:flex;align-items:center;gap:8px;">'
                f'<img src="{logo_url(logo_ticker(symbol))}" loading="lazy" '
                f'style="width:20px;height:20px;border-radius:4px;background:#fff;object-fit:contain;flex-shrink:0;" '
                f'onerror="this.style.display=\'none\'"/>'
                f'<span class="kairos-mono" style="font-weight:600;">{symbol}</span></div>'
                f'<div class="kairos-mono">{currency_sym}{row["price"]:,.2f}</div>'
                f'<div class="kairos-mono {_target_color_class(row)}">{_target_text(row, currency_sym)}</div>'
                f'<div class="kairos-mono">{row["atr_pct"]:.2f}%</div>'
                f'<div class="kairos-mono">{row["vol_ratio"]:.2f}x</div>'
                f'<div class="kairos-mono">{row["rsi14"]:.1f}</div>'
                f'<div class="kairos-mono">{row["beta"]:.2f}</div>'
                f'<div><span class="badge {"badge-direction-short" if STRATEGY_DIRECTION.get(row["assigned_strategy"]) == "SHORT" else "badge-direction-long"}">'
                f'{row["assigned_strategy"]}</span></div>'
                f'<div class="kairos-mono" style="font-weight:600;">{row["score"]:.0f}</div>'
                f'</div>'
            )
            with st.container(key=f"screener_row_{market}_{symbol}"):
                st.markdown(row_html, unsafe_allow_html=True)
                if st.button("", key=f"screener_select_{market}_{symbol}", use_container_width=True):
                    st.session_state[session_key] = symbol
                    st.rerun()

    return selected


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
    from datetime import datetime as _dt
    cache_path = Path(__file__).parent.parent.parent / "config" / "universe_cache.json"
    full_cache_path = Path(__file__).parent.parent.parent / "config" / "screener_full_cache.json"

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
                full_cache_path.write_text(json.dumps(
                    {"generated_at": _dt.now().strftime("%Y-%m-%d %H:%M:%S"), "results": full_results}, indent=2
                ))
                st.session_state["_screener_full_results"] = full_results
                st.session_state["_screener_cached_at"] = "just now"
                if full_results:
                    st.success(f"Screener ran — {len(full_results)} of ~25 pool stocks currently qualify, top 6 set as the active trading universe.")
                else:
                    st.warning("Screener ran but 0 stocks currently meet the live filter criteria (ATR%, volume, RSI range). This can happen briefly intraday or outside market hours — try again later.")

    # Fall back to the on-disk cache so the table is populated by default each session —
    # 'Re-run screener' stays the only way to trigger a fresh (slow) engine run.
    if st.session_state.get("_screener_full_results") is None and full_cache_path.exists():
        cached = json.loads(full_cache_path.read_text())
        st.session_state["_screener_full_results"] = cached["results"]
        st.session_state["_screener_cached_at"] = cached["generated_at"]

    full_results = st.session_state.get("_screener_full_results", None)
    active_universe_symbols = {s["symbol"] for s in json.loads(cache_path.read_text())} if cache_path.exists() else set()

    if full_results:
        cached_at = st.session_state.get("_screener_cached_at")
        if cached_at and cached_at != "just now":
            st.caption(f"Showing cached results from {cached_at}. Click 'Re-run screener' to refresh.")
        df = pd.DataFrame(full_results)
        selected_symbol = render_screener_table(df, active_universe_symbols, market="INDIA", session_key="_screener_selected_symbol")
        st.caption("● marks stocks in the currently deployed top-6 universe. Click any row to open its deep dive below.")
    else:
        st.info("No screener data yet. Click 'Re-run screener' to evaluate the full India universe — results are cached after that.")
        selected_symbol = None
        df = pd.DataFrame()

    if selected_symbol and not df.empty:
        sel = df[df["symbol"] == selected_symbol].iloc[0]
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

            render_manual_paper_trade_button(
                sel["symbol"], market="INDIA", current_price=sel["price"],
                recommended_strategy=sel["assigned_strategy"],
            )

        with dd2:
            chart_title_col, chart_fs_col = st.columns([6, 1])
            with chart_title_col:
                st.markdown('<p class="kpi-label" style="margin:4px 0;">Chart</p>', unsafe_allow_html=True)
            with chart_fs_col:
                if st.button("⛶", key=f"chart_fs_{sel['symbol']}", help="Open fullscreen chart"):
                    st.session_state["_fullscreen_chart_symbol"] = sel["symbol"]
            render_candlestick_chart(sel["symbol"], db, market="INDIA", key_prefix="dd", height=260)

            st.markdown('<p style="font-size:12px;color:var(--text-secondary);margin:4px 0 8px;">Recent headlines</p>', unsafe_allow_html=True)
            render_news_list(f"{sel['symbol']}.NS", limit=4)

        if st.session_state.get("_fullscreen_chart_symbol") == sel["symbol"]:
            _render_fullscreen_chart_dialog(sel["symbol"], db)

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
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:8px;">Screener universe</p>', unsafe_allow_html=True)

    us_rc1, us_rc2 = st.columns([4, 1])
    with us_rc2:
        us_run_clicked = st.button("Re-run screener", key="us_run_screener_btn", use_container_width=True)

    us_cache_path = Path(__file__).parent.parent.parent / "config" / "universe_cache_us.json"
    us_full_cache_path = Path(__file__).parent.parent.parent / "config" / "screener_full_cache_us.json"

    if us_run_clicked:
        with st.spinner("Screening US universe… (runs in the engine process, can take ~60s)"):
            from dashboard.components.engine_bridge import run_screener
            us_full_results, us_err = run_screener(market="US", top_n=None)
            if us_err:
                st.error(us_err)
            else:
                us_top6 = sorted(us_full_results, key=lambda r: r["score"], reverse=True)[:6]
                if us_top6:
                    us_cache_path.write_text(json.dumps(us_top6, indent=2))
                us_full_cache_path.write_text(json.dumps(
                    {"generated_at": _dt.now().strftime("%Y-%m-%d %H:%M:%S"), "results": us_full_results}, indent=2
                ))
                st.session_state["_us_screener_full_results"] = us_full_results
                st.session_state["_us_screener_cached_at"] = "just now"
                if us_full_results:
                    st.success(f"Screener ran — {len(us_full_results)} of ~14 US pool stocks currently qualify, top 6 set as the active US trading universe.")
                else:
                    st.warning("Screener ran but 0 US stocks currently meet the live filter criteria (ATR%, volume, RSI range). Try again during NYSE hours.")

    if st.session_state.get("_us_screener_full_results") is None and us_full_cache_path.exists():
        us_cached = json.loads(us_full_cache_path.read_text())
        st.session_state["_us_screener_full_results"] = us_cached["results"]
        st.session_state["_us_screener_cached_at"] = us_cached["generated_at"]

    us_full_results = st.session_state.get("_us_screener_full_results", None)
    us_active_symbols = {s["symbol"] for s in json.loads(us_cache_path.read_text())} if us_cache_path.exists() else set()

    if us_full_results:
        us_cached_at = st.session_state.get("_us_screener_cached_at")
        if us_cached_at and us_cached_at != "just now":
            st.caption(f"Showing cached results from {us_cached_at}. Click 'Re-run screener' to refresh.")
        us_df = pd.DataFrame(us_full_results)
        render_screener_table(us_df, us_active_symbols, market="US", session_key="_us_screener_selected_symbol")
        st.caption("● marks stocks in the currently deployed top-6 US universe. Click any row to open its deep dive below.")
    else:
        st.info("No US screener data yet. Click 'Re-run screener' to evaluate the US universe — results are cached after that.")
        us_df = pd.DataFrame()

    us_selected_symbol = st.session_state.get("_us_screener_selected_symbol")

    if us_selected_symbol and not us_df.empty and us_selected_symbol in us_df["symbol"].values:
        us_sel = us_df[us_df["symbol"] == us_selected_symbol].iloc[0]
        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)

        us_dd1, us_dd2 = st.columns([1, 1.4])
        with us_dd1:
            st.markdown(
                f"""
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                    <span style="font-size:16px;font-weight:600;">{us_sel['symbol']}</span>
                    <span class="badge badge-long">{us_sel['assigned_strategy']}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            us_metric_pairs = [
                ("Price", f"${us_sel['price']:,.2f}"), ("Score", f"{us_sel['score']:.0f}/100"),
                ("ATR %", f"{us_sel['atr_pct']:.2f}%"), ("Vol ratio", f"{us_sel['vol_ratio']:.2f}x"),
                ("RSI 14", f"{us_sel['rsi14']:.1f}"), ("Beta", f"{us_sel['beta']:.2f}"),
            ]
            us_mcols = st.columns(2)
            for i, (label, val) in enumerate(us_metric_pairs):
                with us_mcols[i % 2]:
                    st.markdown(
                        f'<p class="kpi-label" style="margin:8px 0 2px;">{label}</p>'
                        f'<p class="kairos-mono" style="font-size:14px;">{val}</p>',
                        unsafe_allow_html=True,
                    )

            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
            us_watchlist = get_watchlist(db, market="US")
            already_pinned_us = us_sel["symbol"] in {w.symbol for w in us_watchlist}
            if already_pinned_us:
                st.caption("Already on your watchlist.")
            elif st.button("Add to watchlist", key=f"us_pin_{us_sel['symbol']}", use_container_width=True):
                add_to_watchlist(db, us_sel["symbol"], market="US")
                st.rerun()

            render_manual_paper_trade_button(
                us_sel["symbol"], market="US", current_price=us_sel["price"],
                recommended_strategy=us_sel["assigned_strategy"],
            )

        with us_dd2:
            us_chart_title_col, us_chart_fs_col = st.columns([6, 1])
            with us_chart_title_col:
                st.markdown('<p class="kpi-label" style="margin:4px 0;">Chart</p>', unsafe_allow_html=True)
            with us_chart_fs_col:
                if st.button("⛶", key=f"us_chart_fs_{us_sel['symbol']}", help="Open fullscreen chart"):
                    st.session_state["_fullscreen_chart_symbol"] = us_sel["symbol"]
            render_candlestick_chart(us_sel["symbol"], db, market="US", key_prefix="us_dd", height=260)

            st.markdown('<p style="font-size:12px;color:var(--text-secondary);margin:4px 0 8px;">Recent headlines</p>', unsafe_allow_html=True)
            render_news_list(us_sel["symbol"], limit=4)

        if st.session_state.get("_fullscreen_chart_symbol") == us_sel["symbol"]:
            _render_fullscreen_chart_dialog(us_sel["symbol"], db, market="US")

        st.markdown('</div>', unsafe_allow_html=True)

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
