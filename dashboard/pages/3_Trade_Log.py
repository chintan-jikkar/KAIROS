"""Page 3 — Trade Log: full history, filters, export."""
from pathlib import Path

import streamlit as st

from dashboard.db import get_session
from dashboard.components.trade_table import trades_to_dataframe, render_trade_table, render_summary_bar
from database.models import Trade

st.set_page_config(page_title="KAIROS · Trade Log", page_icon="⚡", layout="wide")
st.markdown(f"<style>{(Path(__file__).parent.parent / 'style.css').read_text()}</style>", unsafe_allow_html=True)

db = get_session()
st.markdown('<h2 class="kairos-heading">Trade log</h2>', unsafe_allow_html=True)

all_trades = db.query(Trade).filter(Trade.timestamp_exit.isnot(None)).order_by(Trade.timestamp_exit.desc()).all()
df = trades_to_dataframe(all_trades)

with st.expander("Filters", expanded=False):
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        strategies = st.multiselect("Strategy", sorted(df["strategy_id"].unique()) if not df.empty else [])
    with f2:
        symbols = st.multiselect("Symbol", sorted(df["symbol"].unique()) if not df.empty else [])
    with f3:
        outcomes = st.multiselect("Outcome", ["WIN", "LOSS", "BREAKEVEN"])
    with f4:
        directions = st.multiselect("Direction", ["LONG", "SHORT"])

filtered = df.copy()
if not filtered.empty:
    if strategies:
        filtered = filtered[filtered["strategy_id"].isin(strategies)]
    if symbols:
        filtered = filtered[filtered["symbol"].isin(symbols)]
    if outcomes:
        filtered = filtered[filtered["outcome"].isin(outcomes)]
    if directions:
        filtered = filtered[filtered["direction"].isin(directions)]

render_summary_bar(filtered)
st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
render_trade_table(filtered)

if not filtered.empty:
    csv = filtered.to_csv(index=False).encode("utf-8")
    st.download_button("Export CSV", data=csv, file_name="kairos_trade_log.csv", mime="text/csv")
