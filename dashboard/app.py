"""
KAIROS dashboard entry point. Run: streamlit run dashboard/app.py
Read-only from kairos.db — never writes.
"""
from pathlib import Path

import streamlit as st

from config.settings import EXECUTION_MODE, ACTIVE_MARKET

st.set_page_config(
    page_title="KAIROS",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)


def load_css():
    css_path = Path(__file__).parent / "style.css"
    st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)


load_css()

with st.sidebar:
    st.markdown(
        '<div style="display:flex;align-items:center;gap:8px;padding:8px 0 16px;">'
        '<span style="font-size:20px;">⚡</span>'
        '<span class="kairos-heading" style="font-size:22px;">KAIROS</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    mode_class = "badge-paper" if EXECUTION_MODE == "PAPER" else "badge-live"
    st.markdown(
        f'<span class="badge {mode_class}">{EXECUTION_MODE} MODE</span> '
        f'<span class="badge" style="background:rgba(255,255,255,0.06);color:rgba(255,255,255,0.7);">{ACTIVE_MARKET}</span>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

st.markdown(
    '<h2 class="kairos-heading">Welcome to KAIROS</h2>'
    '<p style="color:var(--text-secondary);">Select a page from the sidebar to begin.</p>',
    unsafe_allow_html=True,
)
