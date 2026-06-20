"""Shared header: logo, last-updated clock, INR/USD switch, paper/running badges."""
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components

from config.settings import EXECUTION_MODE


def _inject_header_scripts():
    """Two delegated, idempotent behaviors that plain CSS can't do:
    1. Tracks the mouse over .glass-card elements so the hover glow follows the
       cursor instead of sitting at a fixed point.
    2. Ticks #kairos-live-clock every second — Streamlit only re-renders on
       interaction, so a server-rendered timestamp would otherwise sit stale
       between reruns."""
    components.html(
        """
        <script>
        (function() {
            const doc = window.parent.document;
            if (!doc.__kairosGlowBound) {
                doc.__kairosGlowBound = true;
                doc.addEventListener('mousemove', function(e) {
                    const card = e.target.closest('.glass-card');
                    if (!card) return;
                    const rect = card.getBoundingClientRect();
                    const x = ((e.clientX - rect.left) / rect.width) * 100;
                    const y = ((e.clientY - rect.top) / rect.height) * 100;
                    card.style.setProperty('--mx', x + '%');
                    card.style.setProperty('--my', y + '%');
                });
            }
            if (!doc.__kairosClockBound) {
                doc.__kairosClockBound = true;
                const pad = (n) => String(n).padStart(2, '0');
                setInterval(function() {
                    const el = doc.getElementById('kairos-live-clock');
                    if (!el) return;
                    const d = new Date();
                    el.textContent = pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
                }, 1000);
            }
        })();
        </script>
        """,
        height=0,
    )


def render_header():
    if "currency" not in st.session_state:
        st.session_state.currency = "INR"

    _inject_header_scripts()

    left, right = st.columns([1.3, 5.7])

    with left:
        st.markdown(
            '<div style="display:flex;align-items:center;gap:11px;">'
            '<i class="ti ti-bolt" style="font-size:32px;color:#F0C040;'
            'filter:drop-shadow(0 0 7px rgba(240,192,64,0.5));"></i>'
            '<span class="kairos-heading" style="font-size:34px;">KAIROS</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        selected = st.segmented_control(
            "Currency", ["INR", "USD"],
            default=st.session_state.currency,
            label_visibility="collapsed",
            key="currency_toggle",
        )
        st.session_state.currency = selected or st.session_state.currency

        now = datetime.now().strftime("%H:%M:%S")  # JS clock takes over after first paint
        st.markdown(
            f'<p style="font-size:11px;color:var(--text-secondary);margin:4px 0 0 2px;">Last updated '
            f'<span id="kairos-live-clock" class="kairos-mono" style="color:var(--accent-cyan);">{now}</span></p>',
            unsafe_allow_html=True,
        )

    with right:
        if EXECUTION_MODE == "PAPER":
            mode_html = (
                '<span class="badge-paper-prominent">'
                '<i class="ti ti-flask" style="font-size:14px;"></i>PAPER TRADING'
                '</span>'
            )
        else:
            mode_html = (
                '<span class="badge-live-prominent">'
                '<span class="pulse-dot"></span>LIVE'
                '</span>'
            )
        st.markdown(
            f'<div style="display:flex;gap:8px;justify-content:flex-end;align-items:center;padding-top:5px;">'
            f'{mode_html}'
            f'<span class="badge" style="background:rgba(0,245,160,0.08);color:var(--accent-emerald);">'
            f'<span class="status-dot status-running"></span>Running</span>'
            f'</div>',
            unsafe_allow_html=True,
        )


def fmt_currency(value: float, decimals: int = 2) -> str:
    """Format an amount with the symbol for the currently selected market.
    The INR/USD toggle selects which market's stats are shown (India vs US),
    not a currency conversion — value must already be in that market's native
    currency (the caller is responsible for querying market-filtered data)."""
    return f"{currency_symbol()}{value:,.{decimals}f}"


def fmt_currency_signed(value: float, decimals: int = 2) -> str:
    """Same as fmt_currency but always shows a +/- sign."""
    sign = "+" if value >= 0 else "-"
    return sign + fmt_currency(abs(value), decimals)


def currency_symbol() -> str:
    return "$" if st.session_state.get("currency", "INR") == "USD" else "₹"


def selected_market() -> str:
    """Which market's data should be queried, driven by the header's INR/USD toggle."""
    return "US" if st.session_state.get("currency", "INR") == "USD" else "INDIA"
