"""
KAIROS dashboard entry point. Run: streamlit run dashboard/app.py
Read-only from kairos.db — never writes.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from dashboard.components.sidebar import render_sidebar
from dashboard.components.header import render_header

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
render_sidebar("Dashboard")
render_header()

st.markdown(
    '<p style="color:var(--text-secondary);margin-top:8px;">Open '
    '<a href="/Overview" target="_self">Overview</a> for the full dashboard.</p>',
    unsafe_allow_html=True,
)
