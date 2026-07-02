"""TradingView-style candlestick chart — OHLC candles, volume, selectable indicator
overlays, and live/paper trade entry/exit markers.

Indicators here are computed with plain pandas (rolling/ewm), not data/indicators.py —
that module imports pandas_ta at module level, which crashes the dashboard's bare
interpreter. See dashboard/components/engine_bridge.py for the two-interpreter split.
Supertrend is left out of the selectable set for the same reason (needs pandas_ta).

render_candlestick_chart is self-contained (owns its own timeframe + indicator widgets)
so the same function can be called twice on one page — once inline, once inside a
st.dialog for a fullscreen view — as long as each call gets a distinct key_prefix.
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import pandas as pd

from dashboard.components.equity_curve import KAIROS_CHART_LAYOUT
from data.market_data import fetch_india_daily, fetch_us_daily
from database.models import Trade, BacktestTrade

_PERIODS = {"1M": "1mo", "3M": "3mo", "6M": "6mo", "1Y": "1y", "2Y": "2y"}

_INDICATOR_CHOICES = ["EMA 50", "EMA 200", "SMA 200", "Bollinger Bands", "Donchian 20"]

_GREEN = "#3DDC97"
_RED = "#F0506E"


def _add_overlay_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["ema_200"] = df["close"].ewm(span=200, adjust=False).mean()
    df["sma_200"] = df["close"].rolling(200).mean()
    bb_mid = df["close"].rolling(20).mean()
    bb_std = df["close"].rolling(20).std()
    df["bb_upper"] = bb_mid + 2 * bb_std
    df["bb_lower"] = bb_mid - 2 * bb_std
    df["donchian_upper_20"] = df["high"].shift(1).rolling(20).max()
    df["donchian_lower_20"] = df["low"].shift(1).rolling(20).min()
    return df


_BT_ENTRY_COLOR = "#4FC3F7"   # light blue — distinct from live-trade gold (#F0C040)
_BT_WIN_COLOR   = "#3DDC97"   # same green as live wins, but different marker shape
_BT_LOSS_COLOR  = "#F0506E"


def render_candlestick_chart(
    symbol: str,
    db,
    market: str = "INDIA",
    key_prefix: str = "chart",
    height: int = 320,
    show_trades: bool = True,
    backtest_run_id: str | None = None,
    default_timeframe: str = "1Y",
):
    """Drop-in candlestick+volume chart for a symbol. Call from any page; pass a
    different key_prefix for each simultaneous call site on the same page (e.g.
    inline drill-down vs. fullscreen dialog) to avoid widget key collisions."""
    default_tf_index = list(_PERIODS.keys()).index(default_timeframe) if default_timeframe in _PERIODS else 3
    ctrl_tf, ctrl_ind = st.columns([1, 3])
    with ctrl_tf:
        timeframe = st.selectbox(
            "Timeframe", list(_PERIODS.keys()), index=default_tf_index,
            key=f"{key_prefix}_tf_{symbol}", label_visibility="collapsed",
        )
    with ctrl_ind:
        selected_indicators = st.multiselect(
            "Indicators", _INDICATOR_CHOICES, default=["EMA 50"],
            key=f"{key_prefix}_ind_{symbol}", label_visibility="collapsed",
            placeholder="Add indicator overlay...",
        )

    if market == "US":
        df = fetch_us_daily(symbol, period=_PERIODS[timeframe])
    elif market == "INDIA":
        df = fetch_india_daily(symbol, period=_PERIODS[timeframe])
    else:
        st.info("Candlestick chart currently supports India and US market symbols only.")
        return
    if df.empty:
        st.info("No price data available.")
        return
    df = _add_overlay_indicators(df)

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25],
        vertical_spacing=0.03,
    )
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        increasing_line_color=_GREEN, decreasing_line_color=_RED,
        increasing_fillcolor=_GREEN, decreasing_fillcolor=_RED,
        name=symbol, showlegend=False,
    ), row=1, col=1)

    overlay_specs = {
        "EMA 50": [("ema_50", "#F0C040")],
        "EMA 200": [("ema_200", "#8E7CFF")],
        "SMA 200": [("sma_200", "#4FC3F7")],
        "Bollinger Bands": [("bb_upper", "rgba(255,255,255,0.35)"), ("bb_lower", "rgba(255,255,255,0.35)")],
        "Donchian 20": [("donchian_upper_20", "rgba(240,192,64,0.5)"), ("donchian_lower_20", "rgba(240,192,64,0.5)")],
    }
    for label in selected_indicators:
        for col, color in overlay_specs.get(label, []):
            fig.add_trace(go.Scatter(
                x=df.index, y=df[col], mode="lines",
                line=dict(color=color, width=1), showlegend=False, hoverinfo="skip",
            ), row=1, col=1)

    vol_colors = [_GREEN if c >= o else _RED for o, c in zip(df["open"], df["close"])]
    fig.add_trace(go.Bar(
        x=df.index, y=df["volume"], marker_color=vol_colors, showlegend=False,
    ), row=2, col=1)

    currency_sym = "$" if market == "US" else "₹"

    if show_trades:
        trades = db.query(Trade).filter(Trade.symbol == symbol, Trade.market == market).all()
        entries_x, entries_y = [], []
        exits_x, exits_y, exit_colors = [], [], []
        for t in trades:
            if t.timestamp_entry is not None and t.entry_price is not None:
                entries_x.append(t.timestamp_entry)
                entries_y.append(t.entry_price)
            if t.timestamp_exit is not None and t.exit_price is not None:
                exits_x.append(t.timestamp_exit)
                exits_y.append(t.exit_price)
                exit_colors.append(_GREEN if t.outcome == "WIN" else _RED)
        if entries_x:
            fig.add_trace(go.Scatter(
                x=entries_x, y=entries_y, mode="markers", name="Entry",
                marker=dict(symbol="triangle-up", size=11, color="#F0C040",
                            line=dict(width=1, color="#0A0A0A")),
                showlegend=False, hovertemplate=f"Entry {currency_sym}%{{y:,.2f}}<extra></extra>",
            ), row=1, col=1)
        if exits_x:
            fig.add_trace(go.Scatter(
                x=exits_x, y=exits_y, mode="markers", name="Exit",
                marker=dict(symbol="triangle-down", size=11, color=exit_colors,
                            line=dict(width=1, color="#0A0A0A")),
                showlegend=False, hovertemplate=f"Exit {currency_sym}%{{y:,.2f}}<extra></extra>",
            ), row=1, col=1)

    if backtest_run_id is not None:
        bt_trades = (
            db.query(BacktestTrade)
            .filter(BacktestTrade.run_id == backtest_run_id)
            .all()
        )
        bt_entries_x, bt_entries_y, bt_entry_tips = [], [], []
        bt_exits_x, bt_exits_y, bt_exit_colors, bt_exit_tips = [], [], [], []
        for t in bt_trades:
            if t.entry_date and t.entry_price is not None:
                bt_entries_x.append(pd.to_datetime(t.entry_date))
                bt_entries_y.append(t.entry_price)
                bt_entry_tips.append(
                    f"BT Entry {currency_sym}{t.entry_price:,.2f}"
                    f"<br>{t.strategy_id} · {t.entry_date[:10]}"
                )
            if t.exit_date and t.exit_price is not None:
                bt_exits_x.append(pd.to_datetime(t.exit_date))
                bt_exits_y.append(t.exit_price)
                bt_exit_colors.append(_BT_WIN_COLOR if t.outcome == "WIN" else _BT_LOSS_COLOR)
                pnl_str = f"{currency_sym}{t.net_pnl:+,.2f}" if t.net_pnl is not None else "–"
                bt_exit_tips.append(
                    f"BT Exit {currency_sym}{t.exit_price:,.2f}"
                    f"<br>{t.exit_reason or '–'} · P&L {pnl_str}"
                )
        if bt_entries_x:
            fig.add_trace(go.Scatter(
                x=bt_entries_x, y=bt_entries_y, mode="markers",
                name="BT Entry",
                marker=dict(symbol="diamond", size=9, color=_BT_ENTRY_COLOR,
                            line=dict(width=1, color="#0A0A0A")),
                showlegend=False,
                customdata=bt_entry_tips,
                hovertemplate="%{customdata}<extra></extra>",
            ), row=1, col=1)
        if bt_exits_x:
            fig.add_trace(go.Scatter(
                x=bt_exits_x, y=bt_exits_y, mode="markers",
                name="BT Exit",
                marker=dict(symbol="x", size=9, color=bt_exit_colors,
                            line=dict(width=2, color=bt_exit_colors)),
                showlegend=False,
                customdata=bt_exit_tips,
                hovertemplate="%{customdata}<extra></extra>",
            ), row=1, col=1)

    fig.update_layout(
        paper_bgcolor=KAIROS_CHART_LAYOUT["paper_bgcolor"],
        plot_bgcolor=KAIROS_CHART_LAYOUT["plot_bgcolor"],
        font=KAIROS_CHART_LAYOUT["font"],
        margin=KAIROS_CHART_LAYOUT["margin"],
        showlegend=False,
        height=height,
        hovermode="x unified",
        bargap=0.15,
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.06)", showgrid=False, rangeslider_visible=False)
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.06)")
    fig.update_xaxes(showticklabels=False, row=1, col=1)
    fig.update_yaxes(showgrid=False, row=2, col=1)

    st.plotly_chart(
        fig, use_container_width=True, config={"displayModeBar": False},
        key=f"{key_prefix}_fig_{symbol}",
    )
