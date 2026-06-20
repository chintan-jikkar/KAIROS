"""Page 4 — Strategies: status cards for the 7 active strategies + a creator form stub."""
import json
from datetime import date
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from dashboard.db import get_session
from dashboard.components.sidebar import render_sidebar
from dashboard.components.header import render_header
from dashboard.components.ticker_ribbon import render_ticker_ribbon
from dashboard.components.notifications import check_and_notify
from dashboard.components.strategy_card import render_strategy_card
from dashboard.components.manual_trade import render_manual_paper_trade_button
from dashboard.components.market_quotes import fetch_quote
from database.models import Trade

st.set_page_config(page_title="KAIROS · Strategies", page_icon="⚡", layout="wide")
st.markdown(f"<style>{(Path(__file__).parent.parent / 'style.css').read_text()}</style>", unsafe_allow_html=True)

render_sidebar("Strategies")
db = get_session()
check_and_notify(db)
render_header()
render_ticker_ribbon()
st.markdown('<h2 class="kairos-heading">Strategies</h2>', unsafe_allow_html=True)

STRATEGY_LIBRARY = {
    "RSI2_OVN": "RSI-2 overnight mean reversion",
    "ORB_BRK": "Opening range breakout",
    "MOM_CONT": "Momentum continuation",
    "TREND_EMA": "Trend following (50/200 EMA cross)",
    "BB_MEANREV": "Intraday Bollinger mean reversion",
    "DONCHIAN_BRK": "Donchian/Turtle channel breakout",
    "SUPERTREND": "Supertrend",
}
INACTIVE_LIBRARY = [
    "Dual EMA crossover", "VWAP reclaim", "Gap and go",
]

params_path = Path(__file__).parent.parent.parent / "config" / "strategy_params.json"
all_params = json.loads(params_path.read_text()) if params_path.exists() else {}

universe_cache_path = Path(__file__).parent.parent.parent / "config" / "universe_cache.json"
_universe = json.loads(universe_cache_path.read_text()) if universe_cache_path.exists() else []


def _universe_symbols_for(strategy_id: str) -> list[str]:
    return [s["symbol"] for s in _universe if s.get("assigned_strategy") == strategy_id]

left_col, right_col = st.columns([1.3, 1])

with left_col:
    st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:8px;">Active strategies</p>', unsafe_allow_html=True)

    for strategy_id, name in STRATEGY_LIBRARY.items():
        closed = db.query(Trade).filter(Trade.strategy_id == strategy_id, Trade.net_pnl.isnot(None)).all()
        open_count = db.query(Trade).filter(Trade.strategy_id == strategy_id, Trade.timestamp_exit.is_(None)).count()

        wins = [t for t in closed if t.outcome == "WIN"]
        win_rate = (len(wins) / len(closed) * 100) if closed else 0.0
        avg_rr = (sum(t.actual_rr_achieved or 0 for t in closed) / len(closed)) if closed else 0.0
        net_pnl = sum(t.net_pnl for t in closed) if closed else 0.0
        symbols = sorted({t.symbol for t in closed} | {t.symbol for t in db.query(Trade).filter(Trade.strategy_id == strategy_id, Trade.timestamp_exit.is_(None)).all()})
        traded_today = any(t.timestamp_exit and t.timestamp_exit.date() == date.today() for t in closed)

        render_strategy_card(
            strategy_id=strategy_id,
            name=name,
            is_running=open_count > 0 or traded_today,
            trade_count=len(closed),
            win_rate=win_rate,
            avg_rr=avg_rr,
            net_pnl=net_pnl,
            symbols=symbols,
        )

        with st.expander(f"Edit parameters — {strategy_id}"):
            params = all_params.get(strategy_id, {})
            st.json(params)
            st.caption("Parameter editing writes to config/strategy_params.json — wire-up pending.")

        with st.expander(f"Try {strategy_id} on paper before deploying"):
            candidate_symbols = symbols or _universe_symbols_for(strategy_id)
            if not candidate_symbols:
                st.caption("No candidate symbols yet — run the screener first.")
            else:
                pick = st.selectbox("Symbol", candidate_symbols, key=f"try_pick_{strategy_id}")
                quote = fetch_quote(f"{pick}.NS")
                render_manual_paper_trade_button(
                    pick, market="INDIA",
                    current_price=quote["price"] if quote else None,
                    recommended_strategy=strategy_id,
                    key_context=strategy_id,
                )

    st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin:20px 0 8px;">Strategy library — inactive</p>', unsafe_allow_html=True)
    for name in INACTIVE_LIBRARY:
        st.markdown(
            f'<div class="glass-card" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;padding:12px 16px;">'
            f'<span style="font-size:13px;color:var(--text-secondary);">{name}</span>'
            f'<span class="badge" style="background:rgba(255,255,255,0.06);color:var(--text-muted);">Inactive</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

with right_col:
    st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:8px;">Create new strategy</p>', unsafe_allow_html=True)
    with st.form("new_strategy_form"):
        st.text_input("Name")
        st.text_input("ID")
        st.selectbox("Type", ["Trend", "Mean reversion", "Momentum", "Breakout"])
        st.markdown("**Entry conditions**")
        st.text_input("Condition 1", placeholder="e.g. RSI(2) < 10")
        st.text_input("Condition 2", placeholder="e.g. Price > SMA(200)")
        st.markdown("**Exit conditions**")
        st.text_input("Exit condition 1", placeholder="e.g. RSI(2) > 65")
        st.number_input("Risk per trade (%)", min_value=0.5, max_value=10.0, value=2.0, step=0.5)
        st.number_input("Stop loss (%)", min_value=0.5, max_value=20.0, value=4.0, step=0.5)
        st.multiselect("Apply to symbols", [])
        submitted = st.form_submit_button("Save strategy")
        if submitted:
            st.info("Strategy creation backend not wired yet — this form is a UI placeholder.")
