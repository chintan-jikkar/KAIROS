"""Custom icon sidebar — replaces Streamlit's default page list, matches KAIROS visual design."""
import streamlit as st

NAV_ITEMS = [
    ("Dashboard", "ti-layout-dashboard", "/Overview"),
    ("Live trades", "ti-activity", "/Live_Trades"),
    ("Logbook", "ti-notebook", "/Trade_Log"),
    ("Strategies", "ti-target", "/Strategies"),
    ("Markets", "ti-world", "/Markets"),
    ("Analysis", "ti-chart-line", "/Analysis"),
    ("Settings", "ti-settings", "/Settings"),
]


def render_sidebar(active: str):
    if "sidebar_expanded" not in st.session_state:
        st.session_state.sidebar_expanded = True

    expanded = st.session_state.sidebar_expanded
    width_px = 132 if expanded else 60

    st.markdown(
        f"""<style>
        [data-testid="stSidebar"], [data-testid="stSidebar"] > div:first-child {{
            width: {width_px}px !important;
            min-width: {width_px}px !important;
        }}
        </style>""",
        unsafe_allow_html=True,
    )

    with st.sidebar:
        logo_col, toggle_col = st.columns([2, 1])
        with logo_col:
            st.markdown(
                '<div style="padding:4px 0 12px;">'
                '<i class="ti ti-bolt" style="font-size:20px;color:#F0C040;'
                'filter:drop-shadow(0 0 6px rgba(240,192,64,0.5));"></i></div>',
                unsafe_allow_html=True,
            )
        with toggle_col:
            if st.button("‹" if expanded else "›", key="sidebar_toggle_btn",
                        help="Collapse sidebar" if expanded else "Expand sidebar"):
                st.session_state.sidebar_expanded = not expanded
                st.rerun()

        items_html = ""
        for label, icon, href in NAV_ITEMS:
            cls = "kairos-nav-item active" if label == active else "kairos-nav-item"
            if not expanded:
                cls += " collapsed"
            label_html = f"<span>{label}</span>" if expanded else ""
            items_html += (
                f'<a class="{cls}" href="{href}" target="_self" title="{label}">'
                f'<i class="ti {icon}"></i>{label_html}</a>'
            )
        st.markdown(items_html, unsafe_allow_html=True)
