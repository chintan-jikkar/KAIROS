"""Strategy status card with running stats and lifecycle controls."""
import streamlit as st


def render_strategy_card(
    strategy_id: str,
    name: str,
    is_running: bool,
    trade_count: int,
    win_rate: float,
    avg_rr: float,
    net_pnl: float,
    today_pnl: float = 0.0,
    max_drawdown: float = 0.0,
    symbols: list[str] | None = None,
):
    status_class = "status-running" if is_running else "status-waiting"
    status_text = "Running" if is_running else "Paused"
    pnl_class = "positive" if net_pnl >= 0 else "negative"
    today_class = "positive" if today_pnl >= 0 else "negative"
    symbols_text = ", ".join(symbols) if symbols else "No symbols assigned"

    st.markdown(
        f"""
        <div class="glass-card" style="margin-bottom:12px;">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;">
                <div>
                    <p style="font-weight:600;font-size:14px;margin:0;">{name}</p>
                    <p style="font-size:11px;color:var(--text-muted);margin:2px 0 0;">{strategy_id}</p>
                </div>
                <span style="font-size:11px;color:var(--text-secondary);">
                    <span class="status-dot {status_class}"></span>{status_text}
                </span>
            </div>
            <div style="display:flex;gap:20px;margin:12px 0;">
                <div>
                    <p class="kpi-label" style="margin-bottom:2px;">Trades</p>
                    <p class="kairos-mono" style="font-size:14px;">{trade_count}</p>
                </div>
                <div>
                    <p class="kpi-label" style="margin-bottom:2px;">Win rate</p>
                    <p class="kairos-mono" style="font-size:14px;">{win_rate:.1f}%</p>
                </div>
                <div>
                    <p class="kpi-label" style="margin-bottom:2px;">Avg R:R</p>
                    <p class="kairos-mono" style="font-size:14px;">{avg_rr:.2f}</p>
                </div>
                <div>
                    <p class="kpi-label" style="margin-bottom:2px;">Net P&amp;L</p>
                    <p class="kairos-mono {pnl_class}" style="font-size:14px;">₹{net_pnl:+,.0f}</p>
                </div>
            </div>
            <div style="display:flex;gap:20px;margin-bottom:10px;">
                <div>
                    <p class="kpi-label" style="margin-bottom:2px;">Today P&amp;L</p>
                    <p class="kairos-mono {today_class}" style="font-size:13px;">₹{today_pnl:+,.0f}</p>
                </div>
                <div>
                    <p class="kpi-label" style="margin-bottom:2px;">Max drawdown</p>
                    <p class="kairos-mono negative" style="font-size:13px;">₹{max_drawdown:,.0f}</p>
                </div>
            </div>
            <p style="font-size:11px;color:var(--text-muted);margin:0;">Applied to: {symbols_text}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
