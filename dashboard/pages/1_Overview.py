"""Page 1 — Overview: hero KPIs, performance strip, equity curve, monthly grid, account sidebar, markets, strategies."""
from datetime import date, timedelta
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st
from sqlalchemy import func

from config.settings import STARTING_CAPITAL_INR
from dashboard.db import get_session
from dashboard.components.sidebar import render_sidebar
from dashboard.components.header import render_header, fmt_currency, fmt_currency_signed, currency_symbol
from dashboard.components.kpi_card import render_kpi_card
from dashboard.components.equity_curve import render_equity_curve
from dashboard.components.monthly_stats import render_monthly_grid
from dashboard.components.market_quotes import fetch_quote
from database.models import Trade, PortfolioSnapshot, Signal
from database.trade_log import get_open_trades
from engine.risk import RISK_PARAMS

st.set_page_config(page_title="KAIROS · Overview", page_icon="⚡", layout="wide")
st.markdown(f"<style>{(Path(__file__).parent.parent / 'style.css').read_text()}</style>", unsafe_allow_html=True)

render_sidebar("Dashboard")
db = get_session()
render_header()

USD_DIVISOR = 100
divisor = USD_DIVISOR if st.session_state.get("currency") == "USD" else 1
sym = currency_symbol()


def _period_stats(start_date: date) -> dict:
    rows = db.query(Trade).filter(
        Trade.net_pnl.isnot(None),
        func.date(Trade.timestamp_exit) >= start_date,
    ).all()
    if not rows:
        return {"pct": 0.0, "rupee": 0.0, "rr": 0.0, "win_rate": 0.0}

    total_pnl = sum(t.net_pnl for t in rows)
    total_invested = sum((t.entry_price or 0) * (t.quantity or 0) for t in rows) or 1
    wins = [t for t in rows if t.outcome == "WIN"]
    avg_rr = sum(t.actual_rr_achieved or 0 for t in rows) / len(rows)

    return {
        "pct": (total_pnl / total_invested) * 100,
        "rupee": total_pnl,
        "rr": avg_rr,
        "win_rate": (len(wins) / len(rows)) * 100,
    }


today = date.today()
week_stats = _period_stats(today - timedelta(days=7))
month_stats = _period_stats(today - timedelta(days=30))
year_stats = _period_stats(today - timedelta(days=365))
all_time_stats = _period_stats(date(2000, 1, 1))

latest_snap = db.query(PortfolioSnapshot).order_by(PortfolioSnapshot.date.desc()).first()
portfolio_value = latest_snap.portfolio_value if latest_snap else STARTING_CAPITAL_INR
peak_value = (latest_snap.peak_value if latest_snap else portfolio_value) or portfolio_value
drawdown_pct = (latest_snap.drawdown_from_peak_pct * 100) if latest_snap else 0.0

today_closed = db.query(Trade).filter(
    func.date(Trade.timestamp_exit) == today, Trade.net_pnl.isnot(None)
).all()
today_pnl = sum(t.net_pnl for t in today_closed) if today_closed else 0.0
today_pnl_pct = (today_pnl / portfolio_value * 100) if portfolio_value else 0.0

active_signals_today = db.query(func.count(Signal.signal_id)).filter(
    func.date(Signal.generated_at) == today
).scalar() or 0
strategies_live_today = db.query(func.count(Signal.strategy_id.distinct())).filter(
    func.date(Signal.generated_at) == today, Signal.was_executed.is_(True)
).scalar() or 0

st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

hero_cols = st.columns(4)
with hero_cols[0]:
    st.markdown(
        f"""
        <div class="glass-card" style="padding:14px 16px;">
            <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
                <span class="kpi-label" style="margin:0;">Portfolio value</span>
                <i class="ti ti-wallet" style="font-size:15px;color:rgba(255,255,255,0.3);"></i>
            </div>
            <p class="kpi-value" style="font-size:22px;margin:0 0 5px;">{fmt_currency(portfolio_value)}</p>
            <p style="font-size:12px;color:var(--accent-emerald);margin:0;">
                <i class="ti ti-arrow-up"></i> {month_stats['pct']:+.1f}% this month</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
with hero_cols[1]:
    pnl_class = "positive" if today_pnl >= 0 else "negative"
    st.markdown(
        f"""
        <div class="glass-card" style="padding:14px 16px;">
            <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
                <span class="kpi-label" style="margin:0;">Today's P&amp;L</span>
                <i class="ti ti-trending-up" style="font-size:15px;color:rgba(255,255,255,0.3);"></i>
            </div>
            <p class="kpi-value {pnl_class}" style="font-size:22px;margin:0 0 5px;">{fmt_currency_signed(today_pnl)}</p>
            <p class="{pnl_class}" style="font-size:12px;margin:0;">{today_pnl_pct:+.1f}%</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
with hero_cols[2]:
    st.markdown(
        f"""
        <div class="glass-card" style="padding:14px 16px;">
            <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
                <span class="kpi-label" style="margin:0;">Active signals</span>
                <i class="ti ti-radar-2" style="font-size:15px;color:rgba(255,255,255,0.3);"></i>
            </div>
            <p class="kpi-value" style="font-size:22px;margin:0 0 5px;">{active_signals_today}</p>
            <p class="kpi-sub" style="margin:0;">{strategies_live_today} strategies live</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
with hero_cols[3]:
    dd_class = "negative" if drawdown_pct < 0 else "neutral"
    within_limit = abs(drawdown_pct) < RISK_PARAMS["max_drawdown_halt_pct"] * 100
    limit_text = f"Within {RISK_PARAMS['max_drawdown_halt_pct']*100:.0f}% halt limit" if within_limit else "HALT THRESHOLD BREACHED"
    limit_class = "positive" if within_limit else "negative"
    st.markdown(
        f"""
        <div class="glass-card" style="padding:14px 16px;">
            <div style="display:flex;justify-content:space-between;margin-bottom:8px;">
                <span class="kpi-label" style="margin:0;">Max drawdown</span>
                <i class="ti ti-shield-check" style="font-size:15px;color:rgba(255,255,255,0.3);"></i>
            </div>
            <p class="kpi-value {dd_class}" style="font-size:22px;margin:0 0 5px;">{drawdown_pct:.1f}%</p>
            <p class="{limit_class}" style="font-size:12px;margin:0;">{limit_text}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

perf_cols = st.columns(4)
perf_data = [
    ("This week", week_stats, "emerald"),
    ("This month", month_stats, "emerald"),
    ("This year", year_stats, "emerald"),
    ("All time", all_time_stats, "gold"),
]
for col, (label, stats, accent) in zip(perf_cols, perf_data):
    with col:
        render_kpi_card(label, stats["pct"], stats["rupee"], stats["rr"], stats["win_rate"], accent=accent)

st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

main_col, side_col = st.columns([2.1, 1])

with main_col:
    st.markdown('<div class="glass-card no-glow">', unsafe_allow_html=True)
    st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:8px;">Equity curve</p>', unsafe_allow_html=True)
    snapshots = db.query(PortfolioSnapshot).order_by(PortfolioSnapshot.date).all()
    snap_df = pd.DataFrame([{"date": s.date, "portfolio_value": s.portfolio_value} for s in snapshots])
    render_equity_curve(snap_df, symbol=sym, divisor=divisor)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    trades_for_grid = db.query(Trade).filter(
        Trade.net_pnl.isnot(None), Trade.timestamp_exit.isnot(None)
    ).all()
    grid_df = pd.DataFrame([
        {"year": t.timestamp_exit.year, "month": t.timestamp_exit.month, "return_pct": t.net_pnl_pct * 100}
        for t in trades_for_grid
    ])
    if not grid_df.empty:
        grid_df = grid_df.groupby(["year", "month"], as_index=False)["return_pct"].sum()
    render_monthly_grid(grid_df)

with side_col:
    risk_value = portfolio_value * RISK_PARAMS["max_risk_per_trade_pct"]

    st.markdown(
        f"""
        <div class="glass-card">
            <p class="kpi-label">Account balance</p>
            <p class="kpi-value" style="font-size:17px;">{fmt_currency(portfolio_value)}</p>
            <div style="display:flex;justify-content:space-between;font-size:12px;margin-top:10px;">
                <span style="color:var(--text-secondary);">Trade risk</span>
                <span class="kairos-mono">{RISK_PARAMS["max_risk_per_trade_pct"]*100:.0f}%</span>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:12px;margin-top:6px;">
                <span style="color:var(--text-secondary);">Risk value</span>
                <span class="kairos-mono">{fmt_currency(risk_value)}</span>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:12px;margin-top:6px;">
                <span style="color:var(--text-secondary);">India VIX</span>
                <span class="kairos-mono positive">13.4 <i class="ti ti-arrow-down"></i></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    open_trades = get_open_trades(db)
    closed_trades = db.query(Trade).filter(Trade.timestamp_exit.isnot(None)).order_by(Trade.timestamp_exit.desc()).limit(10).all()

    tab_open, tab_closed = st.tabs(["Open", "Closed"])
    with tab_open:
        if not open_trades:
            st.caption("No open positions.")
        for t in open_trades:
            st.markdown(
                f"""
                <div class="glass-card" style="margin-bottom:8px;padding:11px 13px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                        <span style="font-weight:600;font-size:13px;">{t.symbol}</span>
                        <span class="badge badge-long">{t.direction}</span>
                    </div>
                    <p style="font-size:10px;color:var(--text-muted);margin:0 0 6px;">{t.strategy_id}</p>
                    <p class="kairos-mono" style="font-size:12px;">Entry {fmt_currency(t.entry_price)}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
    with tab_closed:
        if not closed_trades:
            st.caption("No closed trades yet.")
        for t in closed_trades:
            sign_class = "positive" if (t.net_pnl or 0) >= 0 else "negative"
            st.markdown(
                f"""
                <div class="glass-card" style="margin-bottom:8px;padding:11px 13px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                        <span style="font-weight:600;font-size:13px;">{t.symbol}</span>
                        <span class="badge badge-long">{t.direction}</span>
                    </div>
                    <p style="font-size:10px;color:var(--text-muted);margin:0 0 6px;">{t.strategy_id} &middot; {t.exit_reason}</p>
                    <div style="display:flex;justify-content:space-between;">
                        <span class="kairos-mono {sign_class}" style="font-size:12px;">{(t.net_pnl_pct or 0)*100:+.2f}%</span>
                        <span class="kairos-mono {sign_class}" style="font-size:12px;">{fmt_currency_signed(t.net_pnl or 0)}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:10px;">Markets overview</p>', unsafe_allow_html=True)

mkt_cols = st.columns(3)
mkt_data = [
    ("India markets", "Nifty 50", "^NSEI", "ti-currency-rupee", "var(--accent-gold)"),
    ("US markets", "S&P 500", "^GSPC", "ti-currency-dollar", "var(--accent-cyan)"),
    ("FX markets", "USD/INR", "INR=X", "ti-replace", "var(--accent-violet)"),
]
for col, (label, name, ticker, icon, border_color) in zip(mkt_cols, mkt_data):
    with col:
        q = fetch_quote(ticker)
        price_text = f"{q['price']:,.2f}" if q else "–"
        chg_text = f"{q['change_pct']:+.2f}%" if q else "–"
        chg_class = "positive" if (q and q["change_pct"] >= 0) else "negative" if q else "neutral"
        st.markdown(
            f"""
            <div class="glass-card" style="border-left:3px solid {border_color};border-radius:0 12px 12px 0;padding:14px 16px;">
                <div style="display:flex;justify-content:space-between;margin-bottom:9px;">
                    <span style="font-size:11px;color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.5px;">{label}</span>
                    <i class="ti {icon}" style="font-size:14px;color:rgba(255,255,255,0.3);"></i>
                </div>
                <div style="display:flex;justify-content:space-between;align-items:baseline;">
                    <div>
                        <p style="font-size:11px;color:var(--text-muted);margin:0 0 4px;">{name}</p>
                        <p class="kairos-mono" style="font-size:17px;font-weight:600;margin:0;">{price_text}</p>
                    </div>
                    <p class="kairos-mono {chg_class}" style="font-size:12px;margin:0;">{chg_text}</p>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:10px;">Strategy performance</p>', unsafe_allow_html=True)

STRATEGY_LABELS = {
    "RSI2_OVN": ("RSI-2 overnight", "Mean reversion"),
    "ORB_BRK": ("Opening range breakout", "Momentum"),
    "MOM_CONT": ("Momentum continuation", "Next-day intraday"),
    "TREND_EMA": ("Trend following", "50/200 EMA cross"),
    "BB_MEANREV": ("Bollinger mean reversion", "Intraday"),
}
strat_cols = st.columns(len(STRATEGY_LABELS))
for col, (strategy_id, (name, subtitle)) in zip(strat_cols, STRATEGY_LABELS.items()):
    with col:
        closed = db.query(Trade).filter(Trade.strategy_id == strategy_id, Trade.net_pnl.isnot(None)).all()
        wins = [t for t in closed if t.outcome == "WIN"]
        win_rate = (len(wins) / len(closed) * 100) if closed else 0.0
        today_strat_pnl = sum(t.net_pnl for t in closed if t.timestamp_exit and t.timestamp_exit.date() == today) if closed else 0.0
        wr_class = "positive" if win_rate >= 55 else "negative" if closed else "neutral"
        pnl_class = "positive" if today_strat_pnl >= 0 else "negative"
        st.markdown(
            f"""
            <div class="glass-card" style="padding:14px 16px;">
                <p style="font-size:13px;font-weight:600;margin:0 0 2px;">{name}</p>
                <p style="font-size:11px;color:var(--text-muted);margin:0 0 13px;">{subtitle}</p>
                <div style="display:flex;justify-content:space-between;">
                    <div>
                        <p class="kpi-label" style="margin:0 0 4px;">Win rate</p>
                        <p class="kairos-mono {wr_class}" style="font-size:14px;font-weight:600;margin:0;">{win_rate:.1f}%</p>
                    </div>
                    <div style="text-align:right;">
                        <p class="kpi-label" style="margin:0 0 4px;">Today P&amp;L</p>
                        <p class="kairos-mono {pnl_class}" style="font-size:14px;font-weight:600;margin:0;">{fmt_currency_signed(today_strat_pnl)}</p>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
