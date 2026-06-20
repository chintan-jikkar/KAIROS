"""
KAIROS dashboard entry point. Run: streamlit run dashboard/app.py
Read-only from kairos.db — never writes.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

st.set_page_config(
    page_title="KAIROS",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.switch_page("pages/1_Overview.py")
