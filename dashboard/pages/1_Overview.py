"""Page 1 — Overview: KPI cards, equity curve, R:R chart, monthly grid, account sidebar."""
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import func

from dashboard.db import get_session
from dashboard.components.kpi_card import render_kpi_card
from dashboard.components.equity_curve import render_equity_curve
from dashboard.components.rr_chart import render_rr_chart
from dashboard.components.monthly_stats import render_monthly_grid
from database.models import Trade, PortfolioSnapshot
from database.trade_log import get_open_trades

st.set_page_config(page_title="KAIROS · Overview", page_icon="⚡", layout="wide")
st.markdown(f"<style>{(Path(__file__).parent.parent / 'style.css').read_text()}</style>", unsafe_allow_html=True)

db = get_session()


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

st.markdown('<h2 class="kairos-heading">Overview</h2>', unsafe_allow_html=True)

cols = st.columns(4)
with cols[0]:
    render_kpi_card("This week", week_stats["pct"], week_stats["rupee"], week_stats["rr"])
with cols[1]:
    render_kpi_card("This month", month_stats["pct"], month_stats["rupee"], month_stats["rr"], month_stats["win_rate"])
with cols[2]:
    render_kpi_card("This year", year_stats["pct"], year_stats["rupee"], year_stats["rr"], year_stats["win_rate"])
with cols[3]:
    render_kpi_card("All time", all_time_stats["pct"], all_time_stats["rupee"], all_time_stats["rr"], all_time_stats["win_rate"], accent="gold")

st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

main_col, side_col = st.columns([2.1, 1])

with main_col:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:8px;">Equity curve</p>', unsafe_allow_html=True)
    snapshots = db.query(PortfolioSnapshot).order_by(PortfolioSnapshot.date).all()
    snap_df = pd.DataFrame([{"date": s.date, "portfolio_value": s.portfolio_value} for s in snapshots])
    render_equity_curve(snap_df)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

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
    from config.settings import STARTING_CAPITAL_INR
    from engine.risk import RISK_PARAMS

    latest_snap = db.query(PortfolioSnapshot).order_by(PortfolioSnapshot.date.desc()).first()
    balance = latest_snap.portfolio_value if latest_snap else STARTING_CAPITAL_INR
    risk_value = balance * RISK_PARAMS["max_risk_per_trade_pct"]

    st.markdown(
        f"""
        <div class="glass-card">
            <p class="kpi-label">Account balance</p>
            <p class="kpi-value">₹{balance:,.2f}</p>
            <div style="display:flex;justify-content:space-between;font-size:12px;margin-top:12px;">
                <span style="color:var(--text-secondary);">Trade risk</span>
                <span class="kairos-mono">{RISK_PARAMS["max_risk_per_trade_pct"]*100:.0f}%</span>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:12px;margin-top:6px;">
                <span style="color:var(--text-secondary);">Risk value</span>
                <span class="kairos-mono">₹{risk_value:,.2f}</span>
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
            pnl_pct = 0.0
            st.markdown(
                f"""
                <div class="glass-card" style="margin-bottom:8px;padding:12px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                        <span style="font-weight:600;font-size:13px;">{t.symbol}</span>
                        <span class="badge badge-long">{t.direction}</span>
                    </div>
                    <p style="font-size:10px;color:var(--text-muted);margin:0 0 6px;">{t.strategy_id}</p>
                    <p class="kairos-mono" style="font-size:12px;">Entry ₹{t.entry_price:.2f}</p>
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
                <div class="glass-card" style="margin-bottom:8px;padding:12px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                        <span style="font-weight:600;font-size:13px;">{t.symbol}</span>
                        <span class="badge badge-long">{t.direction}</span>
                    </div>
                    <p style="font-size:10px;color:var(--text-muted);margin:0 0 6px;">{t.strategy_id} &middot; {t.exit_reason}</p>
                    <div style="display:flex;justify-content:space-between;">
                        <span class="kairos-mono {sign_class}" style="font-size:12px;">{(t.net_pnl_pct or 0)*100:+.2f}%</span>
                        <span class="kairos-mono {sign_class}" style="font-size:12px;">₹{(t.net_pnl or 0):+,.0f}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
