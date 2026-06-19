"""Reward:Risk bar chart — green/red bars with rolling average overlay."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.components.equity_curve import KAIROS_CHART_LAYOUT


def render_rr_chart(df: pd.DataFrame, window: int = 5, height: int = 280):
    """
    df columns: trade_id (or date), actual_rr_achieved
    """
    if df.empty:
        st.info("No closed trades yet.")
        return

    colors = ["#00F5A0" if v >= 0 else "#FF3B3B" for v in df["actual_rr_achieved"]]
    rolling_avg = df["actual_rr_achieved"].rolling(window=window, min_periods=1).mean()

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=list(range(len(df))),
            y=df["actual_rr_achieved"],
            marker_color=colors,
            hovertemplate="R:R %{y:.2f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=list(range(len(df))),
            y=rolling_avg,
            mode="lines",
            line=dict(color="#00D4FF", width=1.5, dash="dot"),
            hovertemplate="Avg %{y:.2f}<extra></extra>",
        )
    )
    fig.update_layout(**KAIROS_CHART_LAYOUT, height=height)
    fig.update_xaxes(visible=False)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
