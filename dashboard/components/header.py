"""Shared header: logo, last-updated clock, INR/USD switch, paper/running badges."""
from datetime import datetime

import streamlit as st

from config.settings import EXECUTION_MODE

USD_PER_INR_DIVISOR = 100  # matches spec's ₹10,000 vs $100 starting capital ratio


def render_header():
    if "currency" not in st.session_state:
        st.session_state.currency = "INR"

    left, right = st.columns([3, 4])

    with left:
        st.markdown(
            '<div style="display:flex;align-items:center;gap:9px;padding-top:4px;">'
            '<i class="ti ti-bolt" style="font-size:25px;color:#F0C040;'
            'filter:drop-shadow(0 0 7px rgba(240,192,64,0.5));"></i>'
            '<span class="kairos-heading" style="font-size:26px;">KAIROS</span>'
            '</div>',
            unsafe_allow_html=True,
        )

    with right:
        c1, c2, c3 = st.columns([2, 2, 2])
        with c1:
            now = datetime.now().strftime("%H:%M:%S")
            st.markdown(
                f'<p style="text-align:right;font-size:11px;color:var(--text-secondary);'
                f'padding-top:10px;">Last updated '
                f'<span class="kairos-mono" style="color:var(--accent-cyan);">{now}</span></p>',
                unsafe_allow_html=True,
            )
        with c2:
            selected = st.segmented_control(
                "Currency", ["INR", "USD"],
                default=st.session_state.currency,
                label_visibility="collapsed",
                key="currency_toggle",
            )
            st.session_state.currency = selected or st.session_state.currency
        with c3:
            if EXECUTION_MODE == "PAPER":
                mode_html = (
                    '<span class="badge-paper-prominent">'
                    '<i class="ti ti-flask" style="font-size:14px;"></i>PAPER TRADING'
                    '</span>'
                )
            else:
                mode_html = '<span class="badge badge-live">Live</span>'
            st.markdown(
                f'<div style="display:flex;gap:8px;justify-content:flex-end;align-items:center;padding-top:5px;">'
                f'{mode_html}'
                f'<span class="badge" style="background:rgba(0,245,160,0.08);color:var(--accent-emerald);">'
                f'<span class="status-dot status-running"></span>Running</span>'
                f'</div>',
                unsafe_allow_html=True,
            )


def fmt_currency(inr_value: float, decimals: int = 2) -> str:
    """Format a rupee amount according to the active INR/USD toggle."""
    if st.session_state.get("currency", "INR") == "USD":
        return f"${inr_value / USD_PER_INR_DIVISOR:,.{decimals}f}"
    return f"₹{inr_value:,.{decimals}f}"


def fmt_currency_signed(inr_value: float, decimals: int = 2) -> str:
    """Same as fmt_currency but always shows a +/- sign."""
    sign = "+" if inr_value >= 0 else "-"
    return sign + fmt_currency(abs(inr_value), decimals)


def currency_symbol() -> str:
    return "$" if st.session_state.get("currency", "INR") == "USD" else "₹"
