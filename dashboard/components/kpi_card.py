"""Reusable KPI card: label, R:R, %, money, optional win-rate ring."""
import streamlit as st

from dashboard.components.header import fmt_currency_signed


def render_kpi_card(
    label: str,
    pct: float,
    rupee: float,
    rr: float,
    win_rate: float | None = None,
    accent: str = "emerald",
):
    sign_class = "positive" if pct >= 0 else "negative"
    accent_color = {"emerald": "#00F5A0", "gold": "#F0C040"}.get(accent, "#00F5A0")
    money_text = fmt_currency_signed(rupee, decimals=0)

    ring_html = ""
    if win_rate is not None:
        ring_html = f"""
        <div style="position:relative;width:38px;height:38px;border-radius:50%;
                    background:conic-gradient({accent_color} 0% {win_rate}%, rgba(255,255,255,0.1) {win_rate}% 100%);
                    display:flex;align-items:center;justify-content:center;flex-shrink:0;">
            <div style="width:28px;height:28px;border-radius:50%;background:#0c0c14;
                        display:flex;align-items:center;justify-content:center;font-size:9px;color:#fff;">
                {win_rate:.0f}%
            </div>
        </div>
        """

    st.markdown(
        f"""
        <div class="glass-card" style="display:flex;justify-content:space-between;align-items:center;">
            <div>
                <div class="kpi-label">{label}</div>
                <div class="kpi-value {sign_class}">{pct:+.1f}%</div>
                <div class="kpi-sub">R:R {rr:+.2f} &middot; {money_text}</div>
            </div>
            {ring_html}
        </div>
        """,
        unsafe_allow_html=True,
    )
