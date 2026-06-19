"""Custom icon sidebar — replaces Streamlit's default page list, matches KAIROS visual design."""
import streamlit as st

NAV_ITEMS = [
    ("Dashboard", "ti-layout-dashboard", "/Overview"),
    ("Live trades", "ti-activity", "/Live_Trades"),
    ("Logbook", "ti-notebook", "/Trade_Log"),
    ("Strategies", "ti-target", "/Strategies"),
    ("Screener", "ti-filter", "/Screener"),
    ("Markets", "ti-world", "/Markets"),
    ("Analysis", "ti-chart-line", "/Analysis"),
    ("Settings", "ti-settings", "/Settings"),
]


def render_sidebar(active: str):
    with st.sidebar:
        st.markdown(
            '<div style="display:flex;justify-content:center;padding:6px 0 18px;">'
            '<i class="ti ti-bolt" style="font-size:24px;color:#F0C040;'
            'filter:drop-shadow(0 0 7px rgba(240,192,64,0.5));"></i></div>',
            unsafe_allow_html=True,
        )
        items_html = ""
        for label, icon, href in NAV_ITEMS:
            cls = "kairos-nav-item active" if label == active else "kairos-nav-item"
            items_html += (
                f'<a class="{cls}" href="{href}" target="_self">'
                f'<i class="ti {icon}"></i><span>{label}</span></a>'
            )
        st.markdown(items_html, unsafe_allow_html=True)
