"""Page 7 — Analysis: drawdown, strategy attribution, time-of-day, symbol performance, MAE/MFE, costs."""
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.db import get_session
from dashboard.components.sidebar import render_sidebar
from dashboard.components.header import render_header, selected_market
from dashboard.components.ticker_ribbon import render_ticker_ribbon
from dashboard.components.notifications import check_and_notify
from dashboard.components.equity_curve import KAIROS_CHART_LAYOUT
from database.models import Trade, PortfolioSnapshot
from engine.backtest_metrics import historical_var, conditional_var

st.set_page_config(page_title="KAIROS · Analysis", page_icon="⚡", layout="wide")
st.markdown(f"<style>{(Path(__file__).parent.parent / 'style.css').read_text()}</style>", unsafe_allow_html=True)

render_sidebar("Analysis")
db = get_session()
check_and_notify(db)
render_header()
render_ticker_ribbon()
st.markdown('<h2 class="kairos-heading">Analysis</h2>', unsafe_allow_html=True)

st.markdown('<div class="glass-card no-glow">', unsafe_allow_html=True)
st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:8px;">Value at Risk</p>', unsafe_allow_html=True)

var_snapshots = db.query(PortfolioSnapshot).filter(
    PortfolioSnapshot.market == selected_market()
).order_by(PortfolioSnapshot.date).all()
var_equity_curve = [s.portfolio_value for s in var_snapshots if s.portfolio_value is not None]

var_95 = historical_var(var_equity_curve, confidence=0.95)
var_99 = historical_var(var_equity_curve, confidence=0.99)
cvar_95 = conditional_var(var_equity_curve, confidence=0.95)
cvar_99 = conditional_var(var_equity_curve, confidence=0.99)

if var_95 is None:
    st.info(
        f"Not enough portfolio history yet for VaR (have {len(var_equity_curve)} daily "
        f"snapshots). This fills in automatically as paper/live trading accumulates more days."
    )
else:
    var_cols = st.columns(4)
    for col, label, value in [
        (var_cols[0], "VaR 95%", var_95), (var_cols[1], "VaR 99%", var_99),
        (var_cols[2], "CVaR 95%", cvar_95), (var_cols[3], "CVaR 99%", cvar_99),
    ]:
        with col:
            one_day = f"{value:.2%}"
            ten_day = f"{value * math.sqrt(10):.2%}"
            st.markdown(
                f"""
                <div class="glass-card" style="padding:11px 13px;">
                    <p class="kpi-label" style="margin:0 0 4px;">{label}</p>
                    <p class="kpi-value" style="font-size:18px;margin:0 0 2px;">{one_day}</p>
                    <p style="font-size:11px;color:var(--text-secondary);margin:0;">10-day: {ten_day}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
st.markdown('</div>', unsafe_allow_html=True)
st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

closed_trades = db.query(Trade).filter(Trade.net_pnl.isnot(None)).all()

if not closed_trades:
    st.info("No closed trades yet — analysis populates once trades start closing.")
else:
    df = pd.DataFrame([{
        "symbol": t.symbol, "strategy_id": t.strategy_id, "net_pnl": t.net_pnl,
        "net_pnl_pct": (t.net_pnl_pct or 0) * 100, "gross_pnl": t.gross_pnl,
        "total_costs": t.total_costs, "timestamp_exit": t.timestamp_exit,
        "timestamp_entry": t.timestamp_entry,
        "max_adverse_excursion_pct": t.max_adverse_excursion_pct or 0,
        "max_favorable_excursion_pct": t.max_favorable_excursion_pct or 0,
        "outcome": t.outcome,
    } for t in closed_trades])

    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="glass-card no-glow">', unsafe_allow_html=True)
        st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:8px;">Drawdown from peak</p>', unsafe_allow_html=True)
        snapshots = db.query(PortfolioSnapshot).order_by(PortfolioSnapshot.date).all()
        if snapshots:
            dd_df = pd.DataFrame([{"date": s.date, "drawdown": (s.drawdown_from_peak_pct or 0) * 100} for s in snapshots])
            fig = go.Figure(go.Scatter(
                x=dd_df["date"], y=dd_df["drawdown"], mode="lines", fill="tozeroy",
                line=dict(color="#FF3B3B", width=1.5), fillcolor="rgba(255,59,59,0.1)",
            ))
            fig.update_layout(**KAIROS_CHART_LAYOUT, height=240)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.caption("No snapshot history yet.")
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="glass-card no-glow">', unsafe_allow_html=True)
        st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:8px;">Strategy attribution</p>', unsafe_allow_html=True)
        attr = df.groupby("strategy_id")["net_pnl"].sum().reset_index()
        fig = go.Figure(go.Pie(
            labels=attr["strategy_id"], values=attr["net_pnl"].abs(), hole=0.55,
            marker=dict(colors=["#F0C040", "#00D4FF", "#A855F7"]),
            textinfo="label+percent",
        ))
        fig.update_layout(**KAIROS_CHART_LAYOUT, height=240)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    col3, col4 = st.columns(2)

    with col3:
        st.markdown('<div class="glass-card no-glow">', unsafe_allow_html=True)
        st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:8px;">Net P&L by symbol</p>', unsafe_allow_html=True)
        by_symbol = df.groupby("symbol")["net_pnl"].sum().sort_values()
        colors = ["#00F5A0" if v >= 0 else "#FF3B3B" for v in by_symbol]
        fig = go.Figure(go.Bar(x=by_symbol.values, y=by_symbol.index, orientation="h", marker_color=colors))
        fig.update_layout(**KAIROS_CHART_LAYOUT, height=max(240, len(by_symbol) * 30))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    with col4:
        st.markdown('<div class="glass-card no-glow">', unsafe_allow_html=True)
        st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:8px;">MAE vs MFE</p>', unsafe_allow_html=True)
        colors = ["#00F5A0" if o == "WIN" else "#FF3B3B" for o in df["outcome"]]
        fig = go.Figure(go.Scatter(
            x=df["max_adverse_excursion_pct"], y=df["max_favorable_excursion_pct"],
            mode="markers", marker=dict(color=colors, size=8),
        ))
        fig.update_layout(**KAIROS_CHART_LAYOUT, height=240)
        fig.update_xaxes(title="Max adverse excursion %")
        fig.update_yaxes(title="Max favorable excursion %")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    st.markdown('<div class="glass-card no-glow">', unsafe_allow_html=True)
    st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:8px;">Gross P&L vs costs vs net P&L</p>', unsafe_allow_html=True)
    df["month"] = pd.to_datetime(df["timestamp_exit"]).dt.to_period("M").astype(str)
    monthly = df.groupby("month").agg(gross=("gross_pnl", "sum"), costs=("total_costs", "sum"), net=("net_pnl", "sum")).reset_index()
    fig = go.Figure()
    fig.add_trace(go.Bar(x=monthly["month"], y=monthly["gross"], name="Gross", marker_color="#00D4FF"))
    fig.add_trace(go.Bar(x=monthly["month"], y=-monthly["costs"], name="Costs", marker_color="#FF3B3B"))
    fig.add_trace(go.Scatter(x=monthly["month"], y=monthly["net"], mode="lines+markers", name="Net", line=dict(color="#F0C040", width=2)))
    fig.update_layout(**{**KAIROS_CHART_LAYOUT, "showlegend": True}, height=280, barmode="relative")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)
