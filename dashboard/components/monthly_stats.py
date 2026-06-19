"""Monthly performance grid — Year × Jan-Dec, each cell shows % return, colored."""
import pandas as pd
import streamlit as st


def render_monthly_grid(df: pd.DataFrame):
    """
    df columns: year, month (1-12), return_pct
    Renders a Year-by-month HTML table matching the KAIROS glass theme.
    """
    if df.empty:
        st.info("Not enough trade history for monthly breakdown yet.")
        return

    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    years = sorted(df["year"].unique(), reverse=True)

    rows_html = ""
    for year in years:
        year_data = df[df["year"] == year].set_index("month")["return_pct"]
        cells = ""
        total = 0.0
        has_any = False
        for m in range(1, 13):
            if m in year_data.index:
                val = year_data[m]
                total += val
                has_any = True
                color = "#00F5A0" if val >= 0 else "#FF3B3B"
                cells += f'<td style="padding:8px;text-align:center;color:{color};">{val:+.1f}%</td>'
            else:
                cells += '<td style="padding:8px;text-align:center;color:rgba(255,255,255,0.25);">–</td>'

        total_color = "#00F5A0" if total >= 0 else "#FF3B3B"
        total_cell = f'<td style="padding:8px;text-align:center;font-weight:600;color:{total_color};">{total:+.1f}%</td>' if has_any else '<td></td>'
        rows_html += f'<tr><td style="padding:8px;font-weight:600;">{year}</td>{cells}{total_cell}</tr>'

    header_cells = "".join(f'<th style="padding:8px;color:rgba(255,255,255,0.5);font-size:11px;">{m}</th>' for m in months)

    st.markdown(
        f"""
        <div class="glass-card">
            <table style="width:100%;border-collapse:collapse;font-family:'IBM Plex Mono',monospace;font-size:12px;">
                <tr>
                    <th style="padding:8px;color:rgba(255,255,255,0.5);font-size:11px;text-align:left;">Year</th>
                    {header_cells}
                    <th style="padding:8px;color:rgba(255,255,255,0.5);font-size:11px;">Total</th>
                </tr>
                {rows_html}
            </table>
        </div>
        """,
        unsafe_allow_html=True,
    )
