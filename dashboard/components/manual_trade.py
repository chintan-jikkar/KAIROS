"""
Manual 'try this stock on paper before deploying a strategy' action.
Usable from the Markets and Strategies pages. Always routes through the same
Executor/PaperBroker path real signals use, so position sizing, risk checks,
and cost calculation are identical — it's a real (simulated) order, not a toy.
"""
import streamlit as st

from dashboard.db import get_session
from dashboard.components.strategy_meta import STRATEGY_NAMES
from brokers.paper import PaperBroker
from engine.executor import Executor
from database.portfolio import get_latest_snapshot
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
