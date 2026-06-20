"""Page 3 — Logbook: full trade journal, filters, export, editable journal fields."""
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from dashboard.db import get_session
from dashboard.components.sidebar import render_sidebar
from dashboard.components.header import render_header
from dashboard.components.trade_table import (
    trades_to_dataframe, render_trade_table, render_summary_bar, render_journal_detail,
)
from database.models import Trade

st.set_page_config(page_title="KAIROS · Logbook", page_icon="⚡", layout="wide")
st.markdown(f"<style>{(Path(__file__).parent.parent / 'style.css').read_text()}</style>", unsafe_allow_html=True)

render_sidebar("Logbook")
db = get_session()
render_header()
st.markdown('<h2 class="kairos-heading">Logbook</h2>', unsafe_allow_html=True)
st.markdown(
    '<p style="font-size:12px;color:var(--text-secondary);margin:-6px 0 14px;">'
    'Amounts shown in each trade\'s own market currency — independent of the INR/USD display toggle above.</p>',
    unsafe_allow_html=True,
)

all_trades = db.query(Trade).filter(Trade.timestamp_exit.isnot(None)).order_by(Trade.timestamp_exit.desc()).all()
df = trades_to_dataframe(all_trades)
if not df.empty:
    df["direction"] = [t.direction for t in all_trades]
else:
    st.info("No closed trades yet — the logbook populates once trades start closing.")
    st.stop()

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
st.caption("Click a row to open its journal entry below.")
selected_trade_id = render_trade_table(filtered)

if not filtered.empty:
    csv = filtered.drop(columns=[c for c in filtered.columns if c.endswith("_raw")]).to_csv(index=False).encode("utf-8")
    st.download_button("Export CSV", data=csv, file_name="kairos_trade_log.csv", mime="text/csv")

if selected_trade_id:
    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    selected_row = filtered[filtered["trade_id"] == selected_trade_id].iloc[0]
    render_journal_detail(db, selected_row)
