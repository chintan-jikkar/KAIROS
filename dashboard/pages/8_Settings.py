"""Page 8 — Settings: market config, masked API keys, risk params, scheduler times, data tools."""
import os
from pathlib import Path

import streamlit as st

from config.settings import EXECUTION_MODE, ACTIVE_MARKET
from engine.risk import RISK_PARAMS

st.set_page_config(page_title="KAIROS · Settings", page_icon="⚡", layout="wide")
st.markdown(f"<style>{(Path(__file__).parent.parent / 'style.css').read_text()}</style>", unsafe_allow_html=True)

st.markdown('<h2 class="kairos-heading">Settings</h2>', unsafe_allow_html=True)

st.markdown('<div class="glass-card">', unsafe_allow_html=True)
st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:12px;">Market configuration</p>', unsafe_allow_html=True)
c1, c2 = st.columns(2)
with c1:
    st.selectbox("Active market", ["INDIA", "US", "BOTH"], index=["INDIA", "US", "BOTH"].index(ACTIVE_MARKET))
with c2:
    is_paper = EXECUTION_MODE == "PAPER"
    toggled = st.toggle("Paper mode", value=is_paper)
    if not toggled and is_paper:
        st.warning("Switching to LIVE requires editing EXECUTION_MODE in .env directly — not exposed here as a safety measure.")
st.markdown('</div>', unsafe_allow_html=True)

st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
st.markdown('<div class="glass-card">', unsafe_allow_html=True)
st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:12px;">API keys</p>', unsafe_allow_html=True)


def _mask(val: str) -> str:
    return "•" * 12 if val else "Not set"


keys = [
    ("Zerodha API key", os.getenv("ZERODHA_API_KEY", "")),
    ("Zerodha API secret", os.getenv("ZERODHA_API_SECRET", "")),
    ("Alpaca API key", os.getenv("ALPACA_API_KEY", "")),
    ("Alpaca secret key", os.getenv("ALPACA_SECRET_KEY", "")),
    ("OANDA API key", os.getenv("OANDA_API_KEY", "")),
]
for label, val in keys:
    kc1, kc2 = st.columns([3, 1])
    with kc1:
        st.text_input(label, value=_mask(val), disabled=True, label_visibility="visible")
st.caption("Keys are read from .env — never edited or revealed here.")
st.markdown('</div>', unsafe_allow_html=True)

st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
st.markdown('<div class="glass-card">', unsafe_allow_html=True)
st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:12px;">Risk parameters</p>', unsafe_allow_html=True)
r1, r2, r3 = st.columns(3)
with r1:
    st.number_input("Max risk per trade (%)", value=RISK_PARAMS["max_risk_per_trade_pct"] * 100, step=0.5)
    st.number_input("Max portfolio heat (%)", value=RISK_PARAMS["max_portfolio_heat_pct"] * 100, step=1.0)
with r2:
    st.number_input("Max positions", value=RISK_PARAMS["max_concurrent_positions"], step=1)
    st.number_input("Hard stop loss (%)", value=RISK_PARAMS["hard_stop_loss_pct"] * 100, step=0.5)
with r3:
    st.number_input("Daily loss limit (%)", value=RISK_PARAMS["daily_loss_limit_pct"] * 100, step=0.5)
    st.number_input("Max drawdown halt (%)", value=RISK_PARAMS["max_drawdown_halt_pct"] * 100, step=1.0)
st.caption("Edits here are visual only — persisting changes to engine/risk.py is not wired yet.")
st.markdown('</div>', unsafe_allow_html=True)

st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
col_sched, col_data = st.columns(2)

with col_sched:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:12px;">Scheduler times (IST)</p>', unsafe_allow_html=True)
    sched_rows = [
        ("Morning check", "09:00"), ("MOM_CONT gap confirm", "09:30"),
        ("ORB scan window", "10:00 – 11:30"), ("EOD entry scan", "15:00"),
        ("EOD force-exit", "15:20"), ("EOD snapshot", "15:30"),
        ("Universe refresh", "Sunday 20:00"),
    ]
    for label, time_val in sched_rows:
        st.markdown(
            f'<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border-glass);">'
            f'<span style="font-size:13px;color:var(--text-secondary);">{label}</span>'
            f'<span class="kairos-mono" style="font-size:13px;">{time_val}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    st.markdown('</div>', unsafe_allow_html=True)

with col_data:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:12px;">Data</p>', unsafe_allow_html=True)
    st.button("Export all data", use_container_width=True)
    st.button("Clear all paper trades", use_container_width=True)
    if st.button("Reset system", use_container_width=True, type="primary"):
        st.error("Destructive action — requires confirmation flow before this is wired up.")
    st.markdown('</div>', unsafe_allow_html=True)
