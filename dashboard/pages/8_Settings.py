"""Page 8 — Settings: market config, masked API keys, risk params, scheduler times, data tools."""
import io
import json
import os
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pandas as pd
import streamlit as st

from config.settings import EXECUTION_MODE, ACTIVE_MARKET, PROJECT_ROOT
from dashboard.components.sidebar import render_sidebar
from dashboard.components.header import render_header
from dashboard.components.ticker_ribbon import render_ticker_ribbon
from dashboard.db import get_session
from database.models import Trade, Signal, PortfolioSnapshot
from engine.risk import RISK_PARAMS

st.set_page_config(page_title="KAIROS · Settings", page_icon="⚡", layout="wide")
st.markdown(f"<style>{(Path(__file__).parent.parent / 'style.css').read_text()}</style>", unsafe_allow_html=True)

_OVERRIDES_PATH = PROJECT_ROOT / "config" / "risk_overrides.json"

render_sidebar("Settings")
render_header()
render_ticker_ribbon()
st.markdown('<h2 class="kairos-heading">Settings</h2>', unsafe_allow_html=True)

# ── Market configuration ─────────────────────────────────────────────────────
with st.container(border=True, key="settings_market_config"):
    st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:12px;">Market configuration</p>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.selectbox("Active market", ["INDIA", "US", "BOTH"],
                     index=["INDIA", "US", "BOTH"].index(ACTIVE_MARKET),
                     disabled=True, help="Change ACTIVE_MARKET in .env, then restart the scheduler.")
    with c2:
        is_paper = EXECUTION_MODE == "PAPER"
        st.toggle("Paper mode", value=is_paper, disabled=True,
                  help="LIVE mode is not exposed here as a safety measure. Edit EXECUTION_MODE in .env.")
    st.caption("Market and execution mode are read from .env — edit there and restart the scheduler to apply.")

st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

# ── API keys ─────────────────────────────────────────────────────────────────
with st.container(border=True, key="settings_api_keys"):
    st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:12px;">API keys</p>', unsafe_allow_html=True)

    def _mask(val: str) -> str:
        return "•" * 12 if val else "Not set"

    keys = [
        ("Zerodha API key", os.getenv("ZERODHA_API_KEY", "")),
        ("Zerodha API secret", os.getenv("ZERODHA_API_SECRET", "")),
        ("Alpaca API key", os.getenv("ALPACA_API_KEY", "")),
        ("Alpaca secret key", os.getenv("ALPACA_SECRET_KEY", "")),
        ("OANDA API key", os.getenv("OANDA_API_KEY", "")),
    ]
    for label, val in keys:
        kc1, _ = st.columns([3, 1])
        with kc1:
            st.text_input(label, value=_mask(val), disabled=True)
    st.caption("Keys are read from .env — never edited or revealed here.")

st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

# ── AI assistant keys ────────────────────────────────────────────────────────
with st.container(border=True, key="settings_ai_keys"):
    st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:4px;">AI assistant (optional)</p>', unsafe_allow_html=True)
    st.caption("Slots for a future in-dashboard AI help feature — not built yet. Keys are read from .env.")
    ai_keys = [
        ("Claude (Anthropic) API key", os.getenv("ANTHROPIC_API_KEY", "")),
        ("Gemini (Google) API key", os.getenv("GEMINI_API_KEY", "")),
        ("ChatGPT (OpenAI) API key", os.getenv("OPENAI_API_KEY", "")),
    ]
    for label, val in ai_keys:
        kc1, _ = st.columns([3, 1])
        with kc1:
            st.text_input(label, value=_mask(val), disabled=True)

st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

# ── Risk parameters ───────────────────────────────────────────────────────────
with st.container(border=True, key="settings_risk_params"):
    st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:12px;">Risk parameters</p>', unsafe_allow_html=True)
    r1, r2, r3 = st.columns(3)
    with r1:
        risk_pct = st.number_input("Max risk per trade (%)",
                                   value=float(RISK_PARAMS["max_risk_per_trade_pct"] * 100),
                                   min_value=0.1, max_value=10.0, step=0.5, key="rp_risk_pct")
        heat_pct = st.number_input("Max portfolio heat (%)",
                                   value=float(RISK_PARAMS["max_portfolio_heat_pct"] * 100),
                                   min_value=1.0, max_value=50.0, step=1.0, key="rp_heat")
    with r2:
        max_pos = st.number_input("Max positions",
                                  value=int(RISK_PARAMS["max_concurrent_positions"]),
                                  min_value=1, max_value=20, step=1, key="rp_max_pos")
        hard_stop = st.number_input("Hard stop loss (%)",
                                    value=float(RISK_PARAMS["hard_stop_loss_pct"] * 100),
                                    min_value=0.5, max_value=20.0, step=0.5, key="rp_hard_stop")
    with r3:
        daily_loss = st.number_input("Daily loss limit (%)",
                                     value=float(RISK_PARAMS["daily_loss_limit_pct"] * 100),
                                     min_value=0.5, max_value=20.0, step=0.5, key="rp_daily")
        max_dd = st.number_input("Max drawdown halt (%)",
                                  value=float(RISK_PARAMS["max_drawdown_halt_pct"] * 100),
                                  min_value=1.0, max_value=50.0, step=1.0, key="rp_max_dd")

    if st.button("Save risk parameters", type="primary", key="btn_save_risk"):
        overrides = {
            "max_risk_per_trade_pct": round(risk_pct / 100, 6),
            "max_portfolio_heat_pct": round(heat_pct / 100, 6),
            "max_concurrent_positions": int(max_pos),
            "hard_stop_loss_pct": round(hard_stop / 100, 6),
            "daily_loss_limit_pct": round(daily_loss / 100, 6),
            "max_drawdown_halt_pct": round(max_dd / 100, 6),
        }
        try:
            _OVERRIDES_PATH.write_text(json.dumps(overrides, indent=2))
            st.success("Saved to config/risk_overrides.json. Restart the scheduler to apply.")
        except Exception as exc:
            st.error(f"Failed to save: {exc}")

st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

# ── Charges & breakeven ───────────────────────────────────────────────────────
with st.container(border=True, key="settings_charges"):
    st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:4px;">Charges &amp; breakeven</p>', unsafe_allow_html=True)
    st.caption("Exact formulas used by engine/costs.py for every Net P&L and breakeven-price figure in the dashboard.")
    charge_cols = st.columns(2)
    with charge_cols[0]:
        st.markdown("**India (NSE)**")
        india_rows = [
            ("Equity delivery", "Free", "0.1% (sell)", "0.015% (buy)"),
            ("Equity intraday", "min(₹20, 0.03% turnover)", "0.025% (sell)", "0.003% (buy)"),
            ("F&O futures", "min(₹20, 0.03% turnover)", "0.01% (sell)", "0.002% (buy)"),
            ("F&O options", "₹20 flat/order", "0.05% (sell, on premium)", "0.003% (buy)"),
        ]
        india_df_rows = "".join(
            f'<tr><td style="padding:5px 8px;color:var(--text-secondary);">{seg}</td>'
            f'<td style="padding:5px 8px;" class="kairos-mono">{b}</td>'
            f'<td style="padding:5px 8px;" class="kairos-mono">{stt}</td>'
            f'<td style="padding:5px 8px;" class="kairos-mono">{sd}</td></tr>'
            for seg, b, stt, sd in india_rows
        )
        st.markdown(
            f'<table style="width:100%;font-size:11.5px;border-collapse:collapse;">'
            f'<tr style="color:var(--text-muted);"><td style="padding:5px 8px;">Segment</td>'
            f'<td style="padding:5px 8px;">Brokerage</td><td style="padding:5px 8px;">STT</td>'
            f'<td style="padding:5px 8px;">Stamp duty</td></tr>{india_df_rows}</table>'
            f'<p style="font-size:11px;color:var(--text-muted);margin-top:8px;">'
            f'Plus on every segment: exchange charges 0.00335% of turnover, SEBI charges 0.0001% of turnover, '
            f'GST 18% on (brokerage + exchange + SEBI).</p>',
            unsafe_allow_html=True,
        )
    with charge_cols[1]:
        st.markdown("**US (NASDAQ/NYSE)**")
        st.markdown(
            '<table style="width:100%;font-size:11.5px;border-collapse:collapse;">'
            '<tr style="color:var(--text-muted);"><td style="padding:5px 8px;">Fee</td>'
            '<td style="padding:5px 8px;">Rate</td></tr>'
            '<tr><td style="padding:5px 8px;color:var(--text-secondary);">SEC fee</td>'
            '<td style="padding:5px 8px;" class="kairos-mono">0.00278% of sell notional</td></tr>'
            '<tr><td style="padding:5px 8px;color:var(--text-secondary);">FINRA TAF</td>'
            '<td style="padding:5px 8px;" class="kairos-mono">$0.000119/share, max $5.95</td></tr>'
            '</table>'
            '<p style="font-size:11px;color:var(--text-muted);margin-top:8px;">'
            'Commission-free brokerage assumed (Alpaca). No stamp duty or STT equivalent in the US.</p>',
            unsafe_allow_html=True,
        )
    st.markdown(
        '<p style="font-size:11px;color:var(--text-muted);margin-top:12px;border-top:0.5px solid var(--border-glass);padding-top:10px;">'
        'Breakeven price (entry price adjusted for costs incurred so far) is calculated per-trade and shown '
        'when you open a trade\'s journal entry in the Logbook.</p>',
        unsafe_allow_html=True,
    )

st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

# ── Scheduler times + Data tools ─────────────────────────────────────────────
col_sched, col_data = st.columns(2)

with col_sched:
    with st.container(border=True, key="settings_scheduler"):
        if ACTIVE_MARKET == "US":
            tz_label = "ET"
            sched_rows = [
                ("Market open / morning check", "09:30"),
                ("MOM_CONT gap confirm", "09:45"),
                ("ORB scan window", "10:00 – 11:30"),
                ("EOD entry scan", "15:30"),
                ("EOD force-exit", "15:50"),
                ("EOD snapshot", "16:00"),
                ("Universe refresh", "Sunday 18:00"),
            ]
        else:
            tz_label = "IST"
            sched_rows = [
                ("Morning check", "09:00"),
                ("MOM_CONT gap confirm", "09:30"),
                ("ORB scan window", "10:00 – 11:30"),
                ("EOD entry scan", "15:00"),
                ("EOD force-exit", "15:20"),
                ("EOD snapshot", "15:30"),
                ("Universe refresh", "Sunday 20:00"),
            ]
        st.markdown(
            f'<p style="color:var(--text-secondary);font-size:13px;margin-bottom:12px;">'
            f'Scheduler times ({tz_label})</p>',
            unsafe_allow_html=True,
        )
        for label, time_val in sched_rows:
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;padding:6px 0;'
                f'border-bottom:1px solid var(--border-glass);">'
                f'<span style="font-size:13px;color:var(--text-secondary);">{label}</span>'
                f'<span class="kairos-mono" style="font-size:13px;">{time_val}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

with col_data:
    with st.container(border=True, key="settings_data_tools"):
        st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:12px;">Data</p>', unsafe_allow_html=True)
        db = get_session()

        # ── Export ───────────────────────────────────────────────────────────
        try:
            trades_df = pd.read_sql(db.query(Trade).statement, db.bind)
            signals_df = pd.read_sql(db.query(Signal).statement, db.bind)
            snapshots_df = pd.read_sql(db.query(PortfolioSnapshot).statement, db.bind)
        except Exception:
            trades_df = signals_df = snapshots_df = pd.DataFrame()

        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            trades_df.to_excel(writer, sheet_name="Trades", index=False)
            signals_df.to_excel(writer, sheet_name="Signals", index=False)
            snapshots_df.to_excel(writer, sheet_name="Snapshots", index=False)
        st.download_button(
            "Export all data (.xlsx)",
            data=buf.getvalue(),
            file_name="kairos_export.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        # ── Clear paper trades ────────────────────────────────────────────────
        confirm_clear = st.checkbox(
            "I understand this will permanently delete all paper trades and signals",
            key="chk_confirm_clear",
        )
        if st.button("Clear all paper trades", use_container_width=True,
                     disabled=not confirm_clear, key="btn_clear_trades"):
            try:
                db.query(Signal).delete()
                db.query(Trade).delete()
                db.commit()
                st.success("All paper trades and signals deleted.")
                st.rerun()
            except Exception as exc:
                db.rollback()
                st.error(f"Failed: {exc}")

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        # ── Reset system ──────────────────────────────────────────────────────
        with st.expander("Reset system (destructive)"):
            st.warning("This deletes **all** data — trades, signals, portfolio snapshots, and backtest runs. There is no undo.")
            reset_confirm = st.text_input(
                'Type RESET to confirm', key="txt_reset_confirm", placeholder="RESET"
            )
            if st.button("Reset system", type="primary", use_container_width=True,
                         key="btn_reset_system",
                         disabled=reset_confirm.strip() != "RESET"):
                try:
                    from database.models import BacktestRun, BacktestTrade
                    db.query(BacktestTrade).delete()
                    db.query(BacktestRun).delete()
                    db.query(Signal).delete()
                    db.query(Trade).delete()
                    db.query(PortfolioSnapshot).delete()
                    db.commit()
                    st.success("System reset complete. All data cleared.")
                    st.rerun()
                except Exception as exc:
                    db.rollback()
                    st.error(f"Reset failed: {exc}")
