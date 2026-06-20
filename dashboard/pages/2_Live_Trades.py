"""Page 2 — Live Trades: strategy control panel + open positions + intraday P&L."""
from datetime import date
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
from sqlalchemy import func

from dashboard.db import get_session
from dashboard.components.sidebar import render_sidebar
from dashboard.components.header import render_header, fmt_currency_signed, currency_symbol, selected_market
from dashboard.components.ticker_ribbon import render_ticker_ribbon
from dashboard.components.notifications import check_and_notify
from database.models import Trade, Signal
from database.trade_log import get_open_trades

st.set_page_config(page_title="KAIROS · Live Trades", page_icon="⚡", layout="wide")
st.markdown(f"<style>{(Path(__file__).parent.parent / 'style.css').read_text()}</style>", unsafe_allow_html=True)

render_sidebar("Live trades")
db = get_session()
check_and_notify(db)
render_header()
render_ticker_ribbon()
st.markdown('<h2 class="kairos-heading">Live trades</h2>', unsafe_allow_html=True)

market = selected_market()
sym = currency_symbol()

STRATEGY_NAMES = {
    "RSI2_OVN": "RSI-2 overnight mean reversion",
    "ORB_BRK": "Opening range breakout",
    "MOM_CONT": "Momentum continuation",
    "TREND_EMA": "Trend following (50/200 EMA cross)",
    "BB_MEANREV": "Intraday Bollinger mean reversion",
    "DONCHIAN_BRK": "Donchian/Turtle channel breakout",
    "SUPERTREND": "Supertrend",
}

left_col, right_col = st.columns([1, 1.6])

with left_col:
    st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:8px;">Strategy control</p>', unsafe_allow_html=True)

    for strategy_id, name in STRATEGY_NAMES.items():
        closed = db.query(Trade).filter(
            Trade.market == market, Trade.strategy_id == strategy_id, Trade.net_pnl.isnot(None)
        ).all()
        open_count = db.query(Trade).filter(
            Trade.market == market, Trade.strategy_id == strategy_id, Trade.timestamp_exit.is_(None)
        ).count()
        today_trades = [t for t in closed if t.timestamp_exit and t.timestamp_exit.date() == date.today()]

        net_pnl = sum(t.net_pnl for t in closed) if closed else 0.0
        today_pnl = sum(t.net_pnl for t in today_trades) if today_trades else 0.0
        max_loss = min((t.net_pnl for t in closed), default=0.0)
        is_active = open_count > 0 or len(today_trades) > 0

        status_class = "status-running" if is_active else "status-waiting"
        status_text = "Running" if is_active else "Waiting — no signal today"
        pnl_class = "positive" if net_pnl >= 0 else "negative"
        today_class = "positive" if today_pnl >= 0 else "negative"

        st.markdown(
            f"""
            <div class="glass-card" style="margin-bottom:12px;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                    <span style="font-weight:600;font-size:13px;"><span class="status-dot {status_class}"></span>{name}</span>
                </div>
                <p style="font-size:11px;color:var(--text-muted);margin:0 0 8px;">{status_text}</p>
                <div style="display:flex;gap:24px;">
                    <div>
                        <p class="kpi-label" style="margin-bottom:2px;">Today P&amp;L</p>
                        <p class="kairos-mono {today_class}" style="font-size:13px;">{fmt_currency_signed(today_pnl)}</p>
                    </div>
                    <div>
                        <p class="kpi-label" style="margin-bottom:2px;">Overall P&amp;L</p>
                        <p class="kairos-mono {pnl_class}" style="font-size:13px;">{fmt_currency_signed(net_pnl)}</p>
                    </div>
                    <div>
                        <p class="kpi-label" style="margin-bottom:2px;">Max loss</p>
                        <p class="kairos-mono negative" style="font-size:13px;">{sym}{max_loss:,.0f}</p>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

with right_col:
    open_trades = get_open_trades(db, market=market)
    today_closed = db.query(Trade).filter(
        Trade.market == market, func.date(Trade.timestamp_exit) == date.today(), Trade.net_pnl.isnot(None)
    ).all()
    realized_today = sum(t.net_pnl for t in today_closed) if today_closed else 0.0

    st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:8px;">Account</p>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div style="display:flex;gap:12px;margin-bottom:16px;">
            <div class="glass-card" style="flex:1;text-align:center;">
                <p class="kpi-label">Today's P&amp;L</p>
                <p class="kairos-mono {"positive" if realized_today >= 0 else "negative"}" style="font-size:18px;">{fmt_currency_signed(realized_today)}</p>
            </div>
            <div class="glass-card" style="flex:1;text-align:center;">
                <p class="kpi-label">Open positions</p>
                <p class="kairos-mono" style="font-size:18px;">{len(open_trades)}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:8px;">Open positions</p>', unsafe_allow_html=True)
    if not open_trades:
        st.info("No open positions right now.")
    else:
        rows = []
        for t in open_trades:
            rows.append({
                "Symbol": t.symbol,
                "Dir": t.direction,
                "Strategy": t.strategy_id,
                "Entry": f"{sym}{t.entry_price:.2f}",
                "Stop": f"{sym}{t.stop_loss_price:.2f}" if t.stop_loss_price else "–",
                "Target": f"{sym}{t.target_price:.2f}" if t.target_price else "–",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:8px;">Recent signals</p>', unsafe_allow_html=True)
    recent_signals = db.query(Signal).filter(Signal.market == market).order_by(Signal.generated_at.desc()).limit(8).all()
    if not recent_signals:
        st.caption("No signals logged yet.")
    else:
        sig_rows = [{
            "Time": s.generated_at.strftime("%H:%M:%S"),
            "Symbol": s.symbol,
            "Strategy": s.strategy_id,
            "Action": s.action,
            "Executed": "Yes" if s.was_executed else "No",
            "Reason": s.signal_reason,
        } for s in recent_signals]
        st.dataframe(pd.DataFrame(sig_rows), use_container_width=True, hide_index=True)
