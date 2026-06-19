"""Portfolio value area chart — gold fill on dark background."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

KAIROS_CHART_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="IBM Plex Mono", color="#FFFFFF", size=11),
    margin=dict(l=0, r=0, t=10, b=0),
    xaxis=dict(gridcolor="rgba(255,255,255,0.06)", showgrid=False),
    yaxis=dict(gridcolor="rgba(255,255,255,0.06)"),
    showlegend=False,
)


def render_equity_curve(df: pd.DataFrame, height: int = 280, symbol: str = "₹", divisor: float = 1.0):
    """
    df columns: date, portfolio_value
    symbol/divisor let callers display the same series in a different currency (e.g. USD toggle).
    """
    if df.empty:
        st.info("No portfolio history yet — snapshots populate after the first trading day.")
        return

    values = df["portfolio_value"] / divisor

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=values,
            mode="lines",
            line=dict(color="#F0C040", width=2),
            fill="tozeroy",
            fillcolor="rgba(240,192,64,0.12)",
            hovertemplate=f"{symbol}%{{y:,.2f}}<extra></extra>",
        )
    )
    fig.update_layout(**KAIROS_CHART_LAYOUT, height=height, hovermode="x unified")
    fig.update_yaxes(tickprefix=symbol)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
