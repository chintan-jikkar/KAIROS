"""Page 5 — Screener: run the weekly screener on demand, show ranked results."""
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from dashboard.components.sidebar import render_sidebar
from dashboard.components.header import render_header

st.set_page_config(page_title="KAIROS · Screener", page_icon="⚡", layout="wide")
st.markdown(f"<style>{(Path(__file__).parent.parent / 'style.css').read_text()}</style>", unsafe_allow_html=True)

render_sidebar("Screener")
render_header()
st.markdown('<h2 class="kairos-heading">Screener</h2>', unsafe_allow_html=True)

cache_path = Path(__file__).parent.parent.parent / "config" / "universe_cache.json"

top_col, btn_col = st.columns([4, 1])
with btn_col:
    run_clicked = st.button("Run screener now", use_container_width=True)

if run_clicked:
    with st.spinner("Screening India universe…"):
        from engine.screener import run_india_screener
        results = run_india_screener(top_n=6)
        cache_path.write_text(json.dumps(results, indent=2))
        st.success(f"Screener complete — {len(results)} stocks selected.")

if cache_path.exists():
    universe = json.loads(cache_path.read_text())
    last_modified = pd.Timestamp(cache_path.stat().st_mtime, unit="s")
    st.caption(f"Last run: {last_modified.strftime('%A %H:%M IST')}")
else:
    universe = []
    st.info("Screener hasn't run yet. Click 'Run screener now' or wait for the Sunday 20:00 IST scheduled job.")

if universe:
    st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin:16px 0 8px;">Active universe</p>', unsafe_allow_html=True)
    df = pd.DataFrame(universe)
    display_df = df.rename(columns={
        "symbol": "Symbol", "price": "Price", "atr_pct": "ATR%", "vol_ratio": "Vol ratio",
        "rsi14": "RSI14", "beta": "Beta", "assigned_strategy": "Strategy", "score": "Score",
    })
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:8px;">Score breakdown</p>', unsafe_allow_html=True)
    cols = st.columns(min(len(universe), 6))
    for col, stock in zip(cols, universe):
        with col:
            st.markdown(
                f"""
                <div class="glass-card" style="text-align:center;padding:14px;">
                    <p style="font-weight:600;font-size:13px;margin:0 0 4px;">{stock['symbol']}</p>
                    <p class="kairos-mono" style="font-size:18px;color:var(--accent-gold);margin:0 0 4px;">{stock['score']:.0f}</p>
                    <span class="badge badge-long">{stock['assigned_strategy']}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
