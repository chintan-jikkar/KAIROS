"""Toast notifications for trade entry/exit events. Streamlit has no real
server push — this only fires on your next interaction/rerun, not the
instant something happens in the background scheduler. First call each
session seeds the baseline to "now" so you don't get toasted for your
entire trade history the moment you open the app — only for things that
happen from here on.
"""
from datetime import datetime

import streamlit as st

from database.models import Trade


def check_and_notify(db):
    if not st.session_state.get("_notif_seeded"):
        st.session_state["_notif_seeded"] = True
        st.session_state["_notif_last_entry_ts"] = datetime.utcnow()
        st.session_state["_notif_last_exit_ts"] = datetime.utcnow()
        return

    last_entry_ts = st.session_state["_notif_last_entry_ts"]
    new_entries = db.query(Trade).filter(Trade.created_at > last_entry_ts).all()
    for t in new_entries:
        st.toast(f"Entered {t.symbol} ({t.strategy_id}) — {t.direction} at ₹{t.entry_price:,.2f}", icon="🟢")
    if new_entries:
        st.session_state["_notif_last_entry_ts"] = max(t.created_at for t in new_entries)

    last_exit_ts = st.session_state["_notif_last_exit_ts"]
    new_exits = db.query(Trade).filter(
        Trade.timestamp_exit.isnot(None), Trade.timestamp_exit > last_exit_ts
    ).all()
    for t in new_exits:
        pnl = t.net_pnl or 0.0
        if t.exit_reason == "TARGET":
            st.toast(f"{t.symbol} hit target — +₹{pnl:,.0f}", icon="🎯")
        elif t.exit_reason == "STOP":
            st.toast(f"{t.symbol} stopped out — ₹{pnl:,.0f}", icon="🛑")
        else:
            st.toast(f"Exited {t.symbol} ({t.exit_reason}) — {'+' if pnl >= 0 else ''}₹{pnl:,.0f}", icon="🔵")
    if new_exits:
        st.session_state["_notif_last_exit_ts"] = max(t.timestamp_exit for t in new_exits)
