"""Sortable/filterable trade table for the Trade Log page."""
import pandas as pd
import streamlit as st

from database.models import Trade

DISPLAY_COLUMNS = [
    "trade_id", "symbol", "strategy_id", "direction", "entry_price", "exit_price",
    "quantity", "net_pnl", "net_pnl_pct", "outcome", "exit_reason",
    "timestamp_entry", "timestamp_exit", "total_costs",
]


def trades_to_dataframe(trades: list[Trade]) -> pd.DataFrame:
    rows = []
    for t in trades:
        rows.append({
            "trade_id": t.trade_id,
            "symbol": t.symbol,
            "strategy_id": t.strategy_id,
            "direction": t.direction,
            "entry_price": t.entry_price,
            "exit_price": t.exit_price,
            "quantity": t.quantity,
            "net_pnl": t.net_pnl,
            "net_pnl_pct": (t.net_pnl_pct or 0) * 100,
            "outcome": t.outcome,
            "exit_reason": t.exit_reason,
            "timestamp_entry": t.timestamp_entry,
            "timestamp_exit": t.timestamp_exit,
            "total_costs": t.total_costs,
            "signal_reason": t.signal_reason,
            "manual_notes": t.manual_notes,
        })
    return pd.DataFrame(rows)


def render_trade_table(df: pd.DataFrame):
    if df.empty:
        st.info("No trades match the current filters.")
        return

    def _row_style(row):
        if row["outcome"] == "WIN":
            return ["background-color: rgba(0,245,160,0.06)"] * len(row)
        if row["outcome"] == "LOSS":
            return ["background-color: rgba(255,59,59,0.06)"] * len(row)
        return [""] * len(row)

    display_df = df[DISPLAY_COLUMNS].copy()
    styled = display_df.style.apply(_row_style, axis=1).format({
        "entry_price": "₹{:.2f}",
        "exit_price": "₹{:.2f}",
        "net_pnl": "₹{:+.2f}",
        "net_pnl_pct": "{:+.2f}%",
        "total_costs": "₹{:.2f}",
    })
    st.dataframe(styled, use_container_width=True, height=480)


def render_summary_bar(df: pd.DataFrame):
    if df.empty:
        return
    total = len(df)
    wins = len(df[df["outcome"] == "WIN"])
    win_pct = (wins / total * 100) if total else 0
    avg_win = df[df["net_pnl"] > 0]["net_pnl_pct"].mean() if (df["net_pnl"] > 0).any() else 0
    avg_loss = df[df["net_pnl"] < 0]["net_pnl_pct"].mean() if (df["net_pnl"] < 0).any() else 0
    net_pnl = df["net_pnl"].sum()
    total_costs = df["total_costs"].sum()
    expectancy = df["net_pnl_pct"].mean()

    cols = st.columns(6)
    metrics = [
        ("Total trades", f"{total}"),
        ("Win rate", f"{win_pct:.1f}%"),
        ("Avg win", f"{avg_win:+.2f}%"),
        ("Avg loss", f"{avg_loss:+.2f}%"),
        ("Net P&L", f"₹{net_pnl:+,.0f}"),
        ("Total costs", f"₹{total_costs:,.0f}"),
    ]
    for col, (label, value) in zip(cols, metrics):
        with col:
            st.markdown(
                f'<div class="glass-card" style="padding:12px;text-align:center;">'
                f'<p class="kpi-label" style="margin-bottom:4px;">{label}</p>'
                f'<p class="kairos-mono" style="font-size:16px;font-weight:600;">{value}</p>'
                f'</div>',
                unsafe_allow_html=True,
            )
