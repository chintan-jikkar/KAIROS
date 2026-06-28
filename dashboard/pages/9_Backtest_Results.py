"""Page 9 — Backtests: browse persisted BacktestRun results (read-only; new backtests
are still triggered via `python -m engine.backtest`, not from the dashboard)."""
from pathlib import Path

import math
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from dashboard.components.sidebar import render_sidebar
from dashboard.components.header import render_header, selected_market
from dashboard.components.ticker_ribbon import render_ticker_ribbon
from dashboard.components.notifications import check_and_notify
from dashboard.components.strategy_meta import STRATEGY_NAMES
from dashboard.db import get_session
from database.models import BacktestRun

st.set_page_config(page_title="KAIROS · Backtests", page_icon="⚡", layout="wide")
st.markdown(f"<style>{(Path(__file__).parent.parent / 'style.css').read_text()}</style>", unsafe_allow_html=True)

# Backtesting only covers daily-bar strategies (engine/backtest.py::SUPPORTED_STRATEGIES).
# Hardcoded here rather than imported — engine.backtest transitively imports
# data.indicators, which imports pandas_ta at module level and would crash this
# dashboard's bare interpreter (same reason strategy_meta.py doesn't import
# engine.signals.STRATEGY_REGISTRY either).
BACKTESTABLE_STRATEGIES = ["RSI2_OVN", "MOM_CONT", "TREND_EMA", "DONCHIAN_BRK", "SUPERTREND"]

RUN_COLUMNS = [
    ("Symbol", "1fr"), ("Strategy", "1.4fr"), ("Date range", "1.6fr"),
    ("Trades", "0.7fr"), ("Win rate", "0.8fr"), ("Profit factor", "0.9fr"),
    ("VaR 95%", "0.9fr"),
]
RUN_GRID_TEMPLATE = " ".join(w for _, w in RUN_COLUMNS)


def _pct_or_dash(value: float | None) -> str:
    return f"{value:.2%}" if value is not None else "–"


def render_backtest_run_rows(runs: list[BacktestRun]) -> None:
    """Themed click-anywhere-on-row list — same container/button-overlay pattern as
    render_screener_table() in 6_Markets.py. st.dataframe's canvas grid isn't
    reliably automatable or stylable, so every clickable table in this dashboard
    uses real HTML rows + an invisible full-size button instead."""
    with st.container(border=True, key="backtest_runs_outer"):
        header_html = "".join(f"<div>{label}</div>" for label, _ in RUN_COLUMNS)
        st.markdown(
            f'<div class="backtest-row backtest-header" '
            f'style="grid-template-columns:{RUN_GRID_TEMPLATE};">{header_html}</div>',
            unsafe_allow_html=True,
        )
        selected_run_id = st.session_state.get("_selected_backtest_run_id")
        for run in runs:
            is_selected = run.run_id == selected_run_id
            date_range = f"{run.start_date} → {run.end_date}"
            win_rate_text = f"{run.win_rate:.1%}" if run.win_rate is not None else "–"
            pf_text = (
                "∞" if run.profit_factor == float("inf")
                else f"{run.profit_factor:.2f}" if run.profit_factor is not None else "–"
            )
            row_html = (
                f'<div class="backtest-row {"selected" if is_selected else ""}" '
                f'style="grid-template-columns:{RUN_GRID_TEMPLATE};">'
                f'<div class="kairos-mono" style="font-weight:600;">{run.symbol}</div>'
                f'<div>{STRATEGY_NAMES.get(run.strategy_id, run.strategy_id)}</div>'
                f'<div class="kairos-mono" style="font-size:12px;">{date_range}</div>'
                f'<div class="kairos-mono">{run.total_trades}</div>'
                f'<div class="kairos-mono">{win_rate_text}</div>'
                f'<div class="kairos-mono">{pf_text}</div>'
                f'<div class="kairos-mono">{_pct_or_dash(run.var_95)}</div>'
                f'</div>'
            )
            with st.container(key=f"backtest_row_{run.run_id}"):
                st.markdown(row_html, unsafe_allow_html=True)
                if st.button("", key=f"backtest_select_{run.run_id}", use_container_width=True):
                    st.session_state["_selected_backtest_run_id"] = run.run_id
                    st.rerun()


@st.dialog("Backtest run detail")
def _render_run_detail_dialog(run_id: str, db):
    run = db.query(BacktestRun).filter(BacktestRun.run_id == run_id).first()
    if run is None:
        st.error("Run not found (it may have been deleted).")
        if st.button("Close"):
            st.session_state["_selected_backtest_run_id"] = None
            st.rerun()
        return

    ending_text = f"{run.ending_capital:,.2f}" if run.ending_capital is not None else "–"
    st.markdown(f"**{run.symbol}** · {STRATEGY_NAMES.get(run.strategy_id, run.strategy_id)}")
    st.caption(
        f"{run.start_date} → {run.end_date}  ·  sweep: {run.sweep_label or '–'}  ·  "
        f"capital {run.starting_capital:,.2f} → {ending_text}"
    )

    def _metric_card(label: str, value: str):
        st.markdown(
            f"""
            <div class="glass-card" style="padding:11px 13px;">
                <p class="kpi-label" style="margin:0 0 4px;">{label}</p>
                <p class="kpi-value" style="font-size:17px;margin:0;">{value}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    pf_text = (
        "∞" if run.profit_factor == float("inf")
        else f"{run.profit_factor:.2f}" if run.profit_factor is not None else "–"
    )
    row1 = st.columns(4)
    with row1[0]:
        _metric_card("Total trades", str(run.total_trades))
    with row1[1]:
        _metric_card("Win rate", f"{run.win_rate:.1%}" if run.win_rate is not None else "–")
    with row1[2]:
        _metric_card("Profit factor", pf_text)
    with row1[3]:
        _metric_card("Sharpe ratio", f"{run.sharpe_ratio:.2f}" if run.sharpe_ratio is not None else "–")

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    row2 = st.columns(4)
    with row2[0]:
        _metric_card("Max drawdown", f"{run.max_drawdown_pct:.1%}" if run.max_drawdown_pct is not None else "–")
    with row2[1]:
        _metric_card("Avg R:R achieved", f"{run.avg_rr_achieved:.2f}" if run.avg_rr_achieved is not None else "–")
    with row2[2]:
        _metric_card("Total net P&L", f"{run.total_net_pnl:,.2f}" if run.total_net_pnl is not None else "–")
    with row2[3]:
        _metric_card("Total costs", f"{run.total_costs:,.2f}" if run.total_costs is not None else "–")

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:8px;">Value at Risk</p>', unsafe_allow_html=True)
    row3 = st.columns(4)
    for col, label, value in [
        (row3[0], "VaR 95%", run.var_95), (row3[1], "VaR 99%", run.var_99),
        (row3[2], "CVaR 95%", run.cvar_95), (row3[3], "CVaR 99%", run.cvar_99),
    ]:
        with col:
            one_day = f"{value:.2%}" if value is not None else "N/A"
            ten_day = f"{value * math.sqrt(10):.2%}" if value is not None else "N/A"
            st.markdown(
                f"""
                <div class="glass-card" style="padding:11px 13px;">
                    <p class="kpi-label" style="margin:0 0 4px;">{label}</p>
                    <p class="kpi-value" style="font-size:17px;margin:0 0 2px;">{one_day}</p>
                    <p style="font-size:11px;color:var(--text-secondary);margin:0;">10-day: {ten_day}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    if st.button("Close"):
        st.session_state["_selected_backtest_run_id"] = None
        st.rerun()


render_sidebar("Backtests")
db = get_session()
check_and_notify(db)
render_header()
render_ticker_ribbon()
st.markdown('<h2 class="kairos-heading">Backtests</h2>', unsafe_allow_html=True)
st.caption(
    "Read-only browsing of persisted backtest runs. Run a new one via the CLI: "
    "python -m engine.backtest --symbol SYM --strategy STRAT --start YYYY-MM-DD --end YYYY-MM-DD"
)

market = selected_market()
fc1, fc2 = st.columns([1, 2])
with fc1:
    strategy_filter = st.selectbox(
        "Strategy", ["All"] + BACKTESTABLE_STRATEGIES,
        format_func=lambda s: "All strategies" if s == "All" else STRATEGY_NAMES.get(s, s),
    )
with fc2:
    symbol_filter = st.text_input("Symbol search", placeholder="e.g. RELIANCE").strip().upper()

query = db.query(BacktestRun).filter(BacktestRun.market == market)
if strategy_filter != "All":
    query = query.filter(BacktestRun.strategy_id == strategy_filter)
if symbol_filter:
    query = query.filter(BacktestRun.symbol.contains(symbol_filter))
runs = query.order_by(BacktestRun.created_at.desc()).all()

if not runs:
    st.info(
        "No backtests recorded yet for this market/filter. Run one via the CLI, e.g.:\n\n"
        "`python -m engine.backtest --symbol RELIANCE --strategy DONCHIAN_BRK "
        "--start 2023-01-01 --end 2024-01-01`"
    )
else:
    render_backtest_run_rows(runs)

if st.session_state.get("_selected_backtest_run_id"):
    _render_run_detail_dialog(st.session_state["_selected_backtest_run_id"], db)
