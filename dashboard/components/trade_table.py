"""Sortable/filterable trade table for the Logbook page, matching a standard trade-journal template."""
import pandas as pd
import streamlit as st

from database.models import Trade
from database.trade_log import market_currency_symbol, breakeven_price

DISPLAY_COLUMNS = [
    "trade_no", "entry_date", "symbol", "qty_signed", "entry_value", "exit_date",
    "exit_value", "net_pnl", "days", "stop_loss_price", "target_price",
    "planned_rr_ratio", "outcome",
]

COLUMN_LABELS = {
    "trade_no": "Trade #", "entry_date": "Entry date", "symbol": "Ticker",
    "qty_signed": "Quantity", "entry_value": "Entry $$", "exit_date": "Exit date",
    "exit_value": "Exit $$", "net_pnl": "Profit/loss", "days": "Days",
    "stop_loss_price": "Protective stop", "target_price": "Target",
    "planned_rr_ratio": "Reward:risk", "outcome": "Win/loss",
}


def trades_to_dataframe(trades: list[Trade]) -> pd.DataFrame:
    rows = []
    for i, t in enumerate(trades, start=1):
        sym = market_currency_symbol(t.market)
        qty_signed = t.quantity if t.direction == "LONG" else -(t.quantity or 0)
        entry_value = (t.entry_price or 0) * (t.quantity or 0)
        exit_value = (t.exit_price or 0) * (t.quantity or 0) if t.exit_price else None
        days = round((t.holding_period_hours or 0) / 24, 2)

        rows.append({
            "trade_no": i,
            "trade_id": t.trade_id,
            "entry_date": t.timestamp_entry.strftime("%Y-%m-%d") if t.timestamp_entry else "",
            "symbol": t.symbol,
            "market": t.market,
            "currency_symbol": sym,
            "qty_signed": qty_signed,
            "entry_value_raw": entry_value,
            "entry_value": f"{sym}{entry_value:,.2f}",
            "exit_date": t.timestamp_exit.strftime("%Y-%m-%d") if t.timestamp_exit else "—",
            "exit_value_raw": exit_value,
            "exit_value": f"{sym}{exit_value:,.2f}" if exit_value is not None else "—",
            "net_pnl_raw": t.net_pnl,
            "net_pnl": f"{sym}{t.net_pnl:+,.2f}" if t.net_pnl is not None else "—",
            "net_pnl_pct": (t.net_pnl_pct or 0) * 100,
            "days": days,
            "stop_loss_price": f"{sym}{t.stop_loss_price:,.2f}" if t.stop_loss_price else "—",
            "target_price": f"{sym}{t.target_price:,.2f}" if t.target_price else "—",
            "planned_rr_ratio": f"{t.planned_rr_ratio:.2f}" if t.planned_rr_ratio else "—",
            "actual_rr_achieved": t.actual_rr_achieved,
            "outcome": t.outcome or "OPEN",
            "exit_reason": t.exit_reason,
            "strategy_id": t.strategy_id,
            "strategy_name": t.strategy_name,
            "signal_reason": t.signal_reason,
            "conviction": t.conviction,
            "manual_notes": t.manual_notes,
            "lesson_learned": t.lesson_learned,
            "breakeven_price": breakeven_price(t),
            "total_costs_raw": t.total_costs,
            "total_costs": f"{sym}{t.total_costs:,.2f}" if t.total_costs is not None else "—",
        })
    return pd.DataFrame(rows)


def render_trade_table(df: pd.DataFrame) -> str | None:
    """Renders the journal table with row selection enabled. Returns the selected trade_id, if any."""
    if df.empty:
        st.info("No trades match the current filters.")
        return None

    def _row_style(row):
        if row["outcome"] == "WIN":
            return ["background-color: rgba(0,245,160,0.06)"] * len(row)
        if row["outcome"] == "LOSS":
            return ["background-color: rgba(255,59,59,0.06)"] * len(row)
        return [""] * len(row)

    display_df = df[DISPLAY_COLUMNS]
    styled = display_df.style.apply(_row_style, axis=1)

    event = st.dataframe(
        styled, use_container_width=True, height=420,
        on_select="rerun", selection_mode="single-row", key="trade_log_table",
        column_config={col: st.column_config.Column(label) for col, label in COLUMN_LABELS.items()},
    )
    selected_rows = event.selection.get("rows", []) if hasattr(event, "selection") else []
    if selected_rows:
        return df.iloc[selected_rows[0]]["trade_id"]
    return None


def render_summary_bar(df: pd.DataFrame):
    if df.empty:
        return
    total = len(df)
    wins = len(df[df["outcome"] == "WIN"])
    win_pct = (wins / total * 100) if total else 0
    avg_win = df[df["net_pnl_raw"] > 0]["net_pnl_pct"].mean() if (df["net_pnl_raw"] > 0).any() else 0
    avg_loss = df[df["net_pnl_raw"] < 0]["net_pnl_pct"].mean() if (df["net_pnl_raw"] < 0).any() else 0
    net_pnl = df["net_pnl_raw"].sum()
    total_costs = df["total_costs_raw"].sum()

    cols = st.columns(6)
    metrics = [
        ("Total trades", f"{total}"),
        ("Win rate", f"{win_pct:.1f}%"),
        ("Avg win", f"{avg_win:+.2f}%"),
        ("Avg loss", f"{avg_loss:+.2f}%"),
        ("Net P&L", f"{net_pnl:+,.0f}"),
        ("Total costs", f"{total_costs:,.0f}"),
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


def render_journal_detail(db, row: pd.Series):
    """Editable journal panel — strategy rationale, conviction, comment, lesson learned, BEP."""
    from database.trade_log import update_journal

    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    sym = row["currency_symbol"]
    st.markdown(
        f"""
        <div style="display:flex;justify-content:space-between;margin-bottom:12px;">
            <span style="font-weight:600;font-size:15px;">{row['symbol']} &middot; {row['trade_id']}</span>
            <span class="badge badge-long">{row['strategy_id']}</span>
        </div>
        <p style="font-size:12px;color:var(--text-secondary);margin:0 0 14px;">{row['signal_reason']}</p>
        """,
        unsafe_allow_html=True,
    )

    bep = row["breakeven_price"]
    st.markdown(
        f'<p style="font-size:12px;color:var(--text-secondary);">Breakeven price '
        f'<span class="kairos-mono" style="color:var(--text-primary);">{sym}{bep:,.2f}</span> '
        f'(covers all costs incurred)</p>' if bep else "",
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        conviction = st.select_slider(
            "Conviction at entry", options=[1, 2, 3, 4, 5],
            value=int(row["conviction"]) if row["conviction"] else 3,
            key=f"conv_{row['trade_id']}",
        )
    with c2:
        st.markdown(
            f'<p class="kpi-label">Actual vs planned R:R</p>'
            f'<p class="kairos-mono">{row["planned_rr_ratio"]} planned'
            + (f' &middot; {row["actual_rr_achieved"]:.2f} actual' if row["actual_rr_achieved"] else "")
            + '</p>',
            unsafe_allow_html=True,
        )

    comment = st.text_area("Comment", value=row["manual_notes"] or "", key=f"comment_{row['trade_id']}",
                           placeholder="Market conditions, what you did right, what you'd change...")
    lesson = st.text_area("Lesson learned", value=row["lesson_learned"] or "", key=f"lesson_{row['trade_id']}",
                          placeholder="What did this trade teach you?")

    if st.button("Save journal entry", key=f"save_{row['trade_id']}"):
        update_journal(db, row["trade_id"], conviction=conviction, manual_notes=comment, lesson_learned=lesson)
        st.success("Saved.")

    st.markdown('</div>', unsafe_allow_html=True)
