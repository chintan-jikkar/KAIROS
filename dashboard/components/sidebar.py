"""Custom icon sidebar — replaces Streamlit's default page list, matches KAIROS visual design."""
import streamlit as st
import streamlit.components.v1 as components

NAV_ITEMS = [
    ("Dashboard", "ti-layout-dashboard", "/Overview"),
    ("Live trades", "ti-activity", "/Live_Trades"),
    ("Logbook", "ti-notebook", "/Trade_Log"),
    ("Strategies", "ti-target", "/Strategies"),
    ("Markets", "ti-world", "/Markets"),
    ("Analysis", "ti-chart-line", "/Analysis"),
    ("Backtests", "ti-history", "/Backtest_Results"),
    ("Settings", "ti-settings", "/Settings"),
]

def _inject_tooltip_script():
    """Custom tooltip for nav icons. Two reasons this can't be simpler:
    native title= doesn't reliably render for dynamically-routed SPA anchors,
    and a pure-CSS ::after gets silently clipped because stSidebarContent has
    overflow:auto — anything that escapes the 52px-wide sidebar via absolute
    positioning is cut off before it's ever visible. A single tooltip div
    appended to body and positioned via JS escapes that clipping entirely."""
    components.html(
        """
        <script>
        (function() {
            const doc = window.parent.document;
            if (doc.__kairosTooltipBound) return;
            doc.__kairosTooltipBound = true;

            const tip = doc.createElement('div');
            tip.id = 'kairos-sidebar-tooltip';
            tip.style.cssText = 'position:fixed;z-index:99999;background:#16161f;' +
                'border:1px solid rgba(255,255,255,0.15);color:#fff;font-size:12px;' +
                'font-weight:500;padding:5px 10px;border-radius:6px;white-space:nowrap;' +
                'pointer-events:none;opacity:0;transition:opacity 0.15s ease;' +
                'box-shadow:0 4px 12px rgba(0,0,0,0.4);font-family:Inter,sans-serif;';
            doc.body.appendChild(tip);

            doc.addEventListener('mouseover', function(e) {
                const item = e.target.closest('.kairos-nav-item');
                if (!item) return;
                const label = item.getAttribute('data-tooltip');
                if (!label) return;
                const rect = item.getBoundingClientRect();
                tip.textContent = label;
                tip.style.left = (rect.right + 8) + 'px';
                tip.style.top = (rect.top + rect.height / 2) + 'px';
                tip.style.transform = 'translateY(-50%)';
                tip.style.opacity = '1';
            });
            doc.addEventListener('mouseout', function(e) {
                const item = e.target.closest('.kairos-nav-item');
                if (item) tip.style.opacity = '0';
            });
        })();
        </script>
        """,
        height=0,
    )


def render_sidebar(active: str):
    with st.sidebar:
        _inject_tooltip_script()
        st.markdown(
            '<div style="padding:4px 0 12px;text-align:center;">'
            '<i class="ti ti-bolt" style="font-size:20px;color:#F0C040;'
            'filter:drop-shadow(0 0 6px rgba(240,192,64,0.5));"></i></div>',
            unsafe_allow_html=True,
        )

        items_html = ""
        for label, icon, href in NAV_ITEMS:
            cls = "kairos-nav-item active" if label == active else "kairos-nav-item"
            items_html += (
                f'<a class="{cls} collapsed" href="{href}" target="_self" data-tooltip="{label}">'
                f'<i class="ti {icon}"></i></a>'
            )
        st.markdown(items_html, unsafe_allow_html=True)
