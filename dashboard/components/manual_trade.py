"""
Manual paper trade actions — open and close.
Usable from the Markets, Strategies, and Live Trades pages. Always routes
through the same Executor/PaperBroker path real signals use, so position
sizing, risk checks, and cost calculation are identical.
"""
from datetime import datetime

import streamlit as st

from dashboard.db import get_session
from dashboard.components.strategy_meta import STRATEGY_NAMES
from brokers.paper import PaperBroker
from engine.executor import Executor
from engine.costs import calculate_costs
from database.portfolio import get_latest_snapshot
from database.models import Trade as TradeModel
from config.settings import STARTING_CAPITAL_INR


@st.dialog("Confirm paper trade")
def _confirm_and_place(symbol: str, market: str, direction: str, entry_price: float,
                       stop_price: float, target_price: float, strategy_id: str):
    sym = "₹" if market == "INDIA" else "$"
    strategy_name = STRATEGY_NAMES.get(strategy_id, "Manual paper trade")
    st.markdown(
        f"You're moving to **Paper Trading mode** for this order:\n\n"
        f"**{symbol}** — {direction} at {sym}{entry_price:,.2f}, "
        f"stop {sym}{stop_price:,.2f}, target {sym}{target_price:,.2f}.\n\n"
        f"Tagged as strategy: **{strategy_name}**"
    )
    st.caption("This is a simulated order in Paper mode — no real money moves. Continue?")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Yes, place paper order", type="primary", use_container_width=True):
            db = get_session()
            snap = get_latest_snapshot(db, market)
            capital = snap.portfolio_value if snap else STARTING_CAPITAL_INR
            broker = PaperBroker(db, capital)
            executor = Executor(db=db, broker=broker, market=market,
                                execution_mode="PAPER", segment="equity_intraday")

            risk_dist = abs(entry_price - stop_price)
            rr = round(abs(target_price - entry_price) / risk_dist, 2) if risk_dist else None
            signal = {
                "action": "BUY" if direction == "LONG" else "SELL",
                "symbol": symbol,
                "strategy_id": strategy_id,
                "strategy_name": strategy_name,
                "entry_price": entry_price,
                "stop_price": stop_price,
                "target_price": target_price,
                "planned_rr_ratio": rr,
                "signal_reason": f"Manually placed by user, tagged as {strategy_name} — trying this stock on paper",
                "indicators": {},
            }
            result = executor.execute_entry(signal)
            if result["status"] == "FILLED":
                st.success(f"Filled — trade {result['trade_id']} logged. See it in Live Trades.")
            else:
                st.error(f"Not placed: {result['reason']}")
            st.session_state.pop("manual_trade_open_for", None)
            st.rerun()
    with c2:
        if st.button("Cancel", use_container_width=True):
            st.session_state.pop("manual_trade_open_for", None)
            st.rerun()


def render_manual_paper_trade_button(
    symbol: str,
    market: str = "INDIA",
    current_price: float | None = None,
    recommended_strategy: str | None = None,
    key_context: str = "",
):
    """Drop-in button + form for a given symbol. Call from Markets or Strategies pages.
    recommended_strategy: the screener's assigned_strategy (Markets) or the strategy_id
    of the section this was opened from (Strategies) — pre-selects that strategy in the
    form's picker, but the user can still try the symbol against a different one.
    key_context: disambiguates the widget keys when the same symbol+market can render
    under more than one call site on the same page — e.g. Strategies renders this once
    per strategy section, and a symbol can legitimately appear under two different
    strategies at once (one's DB-tagged trade history, another's live screener
    assignment), which collided on a bare symbol+market key. Markets page only ever
    renders one card per symbol, so it doesn't need to pass this."""
    key_prefix = f"manual_{symbol}_{market}" + (f"_{key_context}" if key_context else "")

    if st.button("Try on paper", key=f"{key_prefix}_open", use_container_width=True):
        st.session_state[f"{key_prefix}_form_open"] = True

    if st.session_state.get(f"{key_prefix}_form_open"):
        strategy_ids = list(STRATEGY_NAMES.keys()) + ["MANUAL"]
        default_index = (
            strategy_ids.index(recommended_strategy)
            if recommended_strategy in STRATEGY_NAMES
            else 0
        )
        with st.form(key=f"{key_prefix}_form"):
            st.markdown(f"**Paper trade {symbol}**")
            strategy_id = st.selectbox(
                "Tag as strategy", strategy_ids,
                index=default_index,
                format_func=lambda sid: (
                    f"{STRATEGY_NAMES[sid]} (recommended)" if sid == recommended_strategy
                    else STRATEGY_NAMES.get(sid, "No strategy — manual only")
                ),
                key=f"{key_prefix}_strategy",
            )
            direction = st.radio("Direction", ["LONG", "SHORT"], horizontal=True, key=f"{key_prefix}_dir")
            default_entry = current_price or 0.0
            entry = st.number_input("Entry price", value=float(default_entry), min_value=0.0, key=f"{key_prefix}_entry")
            default_stop = entry * 0.96 if direction == "LONG" else entry * 1.04
            stop = st.number_input("Stop price", value=float(round(default_stop, 2)), min_value=0.0, key=f"{key_prefix}_stop")
            default_target = entry * 1.08 if direction == "LONG" else entry * 0.92
            target = st.number_input("Target price", value=float(round(default_target, 2)), min_value=0.0, key=f"{key_prefix}_target")
            submitted = st.form_submit_button("Review order", use_container_width=True)

        if submitted:
            if entry <= 0 or stop <= 0 or target <= 0:
                st.error("Entry, stop, and target must all be greater than zero.")
            else:
                _confirm_and_place(symbol, market, direction, entry, stop, target, strategy_id)


# ── Manual close ──────────────────────────────────────────────────────────────

@st.dialog("Close position")
def _close_position_dialog(trade_id: str):
    db = get_session()
    trade = (
        db.query(TradeModel)
        .filter(TradeModel.trade_id == trade_id, TradeModel.timestamp_exit.is_(None))
        .first()
    )
    if trade is None:
        st.error("Trade not found or already closed.")
        if st.button("OK"):
            st.session_state.pop("_close_trade_id", None)
            st.rerun()
        return

    sym = "$" if trade.market == "US" else "₹"
    days_held = max(0, (datetime.utcnow() - trade.timestamp_entry).days)

    st.markdown(
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">'
        f'<span style="font-size:16px;font-weight:600;">{trade.symbol}</span>'
        f'<span style="font-size:12px;color:var(--text-secondary);">{trade.direction} · {trade.strategy_id}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    mc1, mc2, mc3 = st.columns(3)
    with mc1:
        st.metric("Entry", f"{sym}{trade.entry_price:,.2f}")
    with mc2:
        st.metric("Qty", f"{trade.quantity:.0f}")
    with mc3:
        st.metric("Days held", days_held)

    exit_price = st.number_input(
        "Exit price",
        value=float(trade.entry_price),
        min_value=0.01,
        step=0.01,
        key="_close_exit_price",
        help="Enter the price you're exiting at. Costs are applied automatically.",
    )

    if exit_price > 0:
        costs = calculate_costs(
            trade.market, trade.entry_price, exit_price,
            trade.quantity, "equity_intraday",
        )
        gross = (exit_price - trade.entry_price) * float(trade.quantity)
        if trade.direction == "SHORT":
            gross = -gross
        net = gross - costs["total_cost"]
        pnl_class = "positive" if net >= 0 else "negative"
        st.markdown(
            f'<p style="font-size:12px;color:var(--text-muted);margin-top:8px;">Estimated P&amp;L</p>'
            f'<p class="kairos-mono {pnl_class}" style="font-size:18px;margin:2px 0;">{sym}{net:+,.2f}</p>'
            f'<p style="font-size:11px;color:var(--text-muted);">Costs: {sym}{costs["total_cost"]:,.2f} &nbsp;·&nbsp; '
            f'Gross: {sym}{gross:+,.2f}</p>',
            unsafe_allow_html=True,
        )

    st.caption("Exit reason will be recorded as MANUAL — no real money moves.")
    cc1, cc2 = st.columns(2)
    with cc1:
        if st.button("Confirm close", type="primary", use_container_width=True, key="_close_confirm"):
            snap = get_latest_snapshot(db, trade.market)
            capital = snap.portfolio_value if snap else STARTING_CAPITAL_INR
            broker = PaperBroker(db, capital)
            executor = Executor(
                db=db, broker=broker, market=trade.market,
                execution_mode="PAPER", segment="equity_intraday",
            )
            result = executor.execute_exit(trade.symbol, exit_price, "MANUAL")
            if result["status"] == "FILLED":
                st.success(f"Closed — trade {result['trade_id']} settled. Check Logbook for the record.")
            else:
                st.error(f"Failed: {result['reason']}")
            st.session_state.pop("_close_trade_id", None)
            st.rerun()
    with cc2:
        if st.button("Cancel", use_container_width=True, key="_close_cancel"):
            st.session_state.pop("_close_trade_id", None)
            st.rerun()


def render_close_position_button(trade, key_suffix: str = ""):
    """'Close manually' button for a single open trade. Call from the Live Trades page."""
    key = f"close_{trade.trade_id}" + (f"_{key_suffix}" if key_suffix else "")
    if st.button("Close manually", key=key, use_container_width=True):
        st.session_state["_close_trade_id"] = trade.trade_id
