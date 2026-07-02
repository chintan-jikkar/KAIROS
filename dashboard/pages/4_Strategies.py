"""Page 4 — Strategies: status cards for active strategies + dynamic strategy creator."""
import json
from datetime import date
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import streamlit as st

from dashboard.db import get_session
from dashboard.components.sidebar import render_sidebar
from dashboard.components.header import render_header, selected_market
from dashboard.components.ticker_ribbon import render_ticker_ribbon
from dashboard.components.notifications import check_and_notify
from dashboard.components.strategy_card import render_strategy_card
from dashboard.components.manual_trade import render_manual_paper_trade_button
from dashboard.components.market_quotes import fetch_quote
from database.models import Trade

st.set_page_config(page_title="KAIROS · Strategies", page_icon="⚡", layout="wide")
st.markdown(f"<style>{(Path(__file__).parent.parent / 'style.css').read_text()}</style>", unsafe_allow_html=True)

render_sidebar("Strategies")
db = get_session()
check_and_notify(db)
render_header()
render_ticker_ribbon()
st.markdown('<h2 class="kairos-heading">Strategies</h2>', unsafe_allow_html=True)

STRATEGY_LIBRARY = {
    "RSI2_OVN":     "RSI-2 overnight mean reversion",
    "ORB_BRK":      "Opening range breakout",
    "MOM_CONT":     "Momentum continuation",
    "TREND_EMA":    "Trend following (50/200 EMA cross)",
    "BB_MEANREV":   "Intraday Bollinger mean reversion",
    "DONCHIAN_BRK": "Donchian/Turtle channel breakout",
    "SUPERTREND":   "Supertrend",
    "MACD_CROSS":   "MACD momentum crossover",
}
INACTIVE_LIBRARY = [
    "Dual EMA crossover", "VWAP reclaim", "Gap and go",
]

params_path = Path(__file__).parent.parent.parent / "config" / "strategy_params.json"
all_params = json.loads(params_path.read_text()) if params_path.exists() else {}

universe_cache_path = Path(__file__).parent.parent.parent / "config" / "universe_cache.json"
_universe = json.loads(universe_cache_path.read_text()) if universe_cache_path.exists() else []


def _universe_symbols_for(strategy_id: str) -> list[str]:
    return [s["symbol"] for s in _universe if s.get("assigned_strategy") == strategy_id]

market = selected_market()

left_col, right_col = st.columns([1.3, 1])

with left_col:
    st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:8px;">Active strategies</p>', unsafe_allow_html=True)

    for strategy_id, name in STRATEGY_LIBRARY.items():
        closed = db.query(Trade).filter(Trade.strategy_id == strategy_id, Trade.market == market, Trade.net_pnl.isnot(None)).all()
        open_count = db.query(Trade).filter(Trade.strategy_id == strategy_id, Trade.market == market, Trade.timestamp_exit.is_(None)).count()

        wins = [t for t in closed if t.outcome == "WIN"]
        win_rate = (len(wins) / len(closed) * 100) if closed else 0.0
        avg_rr = (sum(t.actual_rr_achieved or 0 for t in closed) / len(closed)) if closed else 0.0
        net_pnl = sum(t.net_pnl for t in closed) if closed else 0.0
        symbols = sorted({t.symbol for t in closed} | {t.symbol for t in db.query(Trade).filter(Trade.strategy_id == strategy_id, Trade.market == market, Trade.timestamp_exit.is_(None)).all()})
        traded_today = any(t.timestamp_exit and t.timestamp_exit.date() == date.today() for t in closed)

        render_strategy_card(
            strategy_id=strategy_id,
            name=name,
            is_running=open_count > 0 or traded_today,
            trade_count=len(closed),
            win_rate=win_rate,
            avg_rr=avg_rr,
            net_pnl=net_pnl,
            symbols=symbols,
        )

        with st.expander(f"Edit parameters — {strategy_id}"):
            params = all_params.get(strategy_id, {})
            st.json(params)
            st.caption("Parameter editing writes to config/strategy_params.json — wire-up pending.")

        with st.expander(f"Try {strategy_id} on paper before deploying"):
            candidate_symbols = symbols or _universe_symbols_for(strategy_id)
            if not candidate_symbols:
                st.caption("No candidate symbols yet — run the screener first.")
            else:
                pick = st.selectbox("Symbol", candidate_symbols, key=f"try_pick_{strategy_id}")
                ticker = f"{pick}.NS" if market == "INDIA" else pick
                quote = fetch_quote(ticker)
                render_manual_paper_trade_button(
                    pick, market=market,
                    current_price=quote["price"] if quote else None,
                    recommended_strategy=strategy_id,
                    key_context=strategy_id,
                )

    st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin:20px 0 8px;">Strategy library — inactive</p>', unsafe_allow_html=True)
    for name in INACTIVE_LIBRARY:
        st.markdown(
            f'<div class="glass-card" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;padding:12px 16px;">'
            f'<span style="font-size:13px;color:var(--text-secondary);">{name}</span>'
            f'<span class="badge" style="background:rgba(255,255,255,0.06);color:var(--text-muted);">Inactive</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

with right_col:
    st.markdown('<p style="color:var(--text-secondary);font-size:13px;margin-bottom:8px;">Create new strategy</p>', unsafe_allow_html=True)

    # ── Session-state initialisation ─────────────────────────────────────────
    for _k, _v in [("ns_entry_count", 1), ("ns_exit_count", 1), ("ns_saved_ok", False)]:
        if _k not in st.session_state:
            st.session_state[_k] = _v

    def _collect_conditions(prefix: str, count: int) -> list[str]:
        return [
            st.session_state.get(f"{prefix}_{i}", "").strip()
            for i in range(count)
            if st.session_state.get(f"{prefix}_{i}", "").strip()
        ]

    def _shift_down(prefix: str, remove_idx: int, count: int) -> None:
        for j in range(remove_idx, count - 1):
            st.session_state[f"{prefix}_{j}"] = st.session_state.get(f"{prefix}_{j+1}", "")

    # ── Name / ID / Type ────────────────────────────────────────────────────
    with st.container(border=True):
        ns_name = st.text_input("Strategy name", key="ns_name", placeholder="e.g. VWAP Reversion")
        ns_id   = st.text_input("Strategy ID (alphanumeric, underscores)", key="ns_id",
                                placeholder="e.g. VWAP_REV")
        ns_type = st.selectbox("Type", ["Trend", "Mean reversion", "Momentum", "Breakout", "Other"],
                               key="ns_type")

    # ── Entry conditions ─────────────────────────────────────────────────────
    st.markdown('<p style="color:var(--text-secondary);font-size:12px;margin:12px 0 6px;">Entry conditions</p>', unsafe_allow_html=True)
    for i in range(st.session_state["ns_entry_count"]):
        ec1, ec2 = st.columns([5, 1])
        with ec1:
            st.text_input(
                f"Entry {i + 1}", key=f"ns_entry_{i}",
                placeholder="e.g. RSI(2) < 10", label_visibility="collapsed",
            )
        with ec2:
            if st.session_state["ns_entry_count"] > 1:
                if st.button("✕", key=f"rm_entry_{i}", help="Remove this condition"):
                    _shift_down("ns_entry", i, st.session_state["ns_entry_count"])
                    st.session_state["ns_entry_count"] -= 1
                    st.rerun()
    if st.button("＋ Add entry condition", key="add_entry_cond", use_container_width=True):
        st.session_state["ns_entry_count"] += 1
        st.rerun()

    # ── Exit conditions ──────────────────────────────────────────────────────
    st.markdown('<p style="color:var(--text-secondary);font-size:12px;margin:12px 0 6px;">Exit conditions</p>', unsafe_allow_html=True)
    for i in range(st.session_state["ns_exit_count"]):
        xc1, xc2 = st.columns([5, 1])
        with xc1:
            st.text_input(
                f"Exit {i + 1}", key=f"ns_exit_{i}",
                placeholder="e.g. RSI(2) > 65 or time-stop 5 days", label_visibility="collapsed",
            )
        with xc2:
            if st.session_state["ns_exit_count"] > 1:
                if st.button("✕", key=f"rm_exit_{i}", help="Remove this condition"):
                    _shift_down("ns_exit", i, st.session_state["ns_exit_count"])
                    st.session_state["ns_exit_count"] -= 1
                    st.rerun()
    if st.button("＋ Add exit condition", key="add_exit_cond", use_container_width=True):
        st.session_state["ns_exit_count"] += 1
        st.rerun()

    # ── Risk params ──────────────────────────────────────────────────────────
    st.markdown('<p style="color:var(--text-secondary);font-size:12px;margin:12px 0 6px;">Risk parameters</p>', unsafe_allow_html=True)
    rp1, rp2 = st.columns(2)
    with rp1:
        ns_risk = st.number_input("Risk per trade (%)", min_value=0.5, max_value=10.0,
                                   value=2.0, step=0.5, key="ns_risk")
    with rp2:
        ns_stop = st.number_input("Stop loss (%)", min_value=0.5, max_value=20.0,
                                   value=4.0, step=0.5, key="ns_stop")

    # ── Save ─────────────────────────────────────────────────────────────────
    if st.button("Save strategy spec", type="primary", use_container_width=True, key="save_strategy"):
        s_id   = st.session_state.get("ns_id", "").strip().upper().replace(" ", "_")
        s_name = st.session_state.get("ns_name", "").strip()
        entry_conds = _collect_conditions("ns_entry", st.session_state["ns_entry_count"])
        exit_conds  = _collect_conditions("ns_exit",  st.session_state["ns_exit_count"])

        errors = []
        if not s_name:
            errors.append("Strategy name is required.")
        if not s_id:
            errors.append("Strategy ID is required.")
        if s_id in STRATEGY_LIBRARY:
            errors.append(f"ID '{s_id}' is already used by an active strategy.")
        if not entry_conds:
            errors.append("At least one entry condition is required.")
        if not exit_conds:
            errors.append("At least one exit condition is required.")

        if errors:
            for e in errors:
                st.error(e)
        else:
            existing = json.loads(params_path.read_text()) if params_path.exists() else {}
            existing[s_id] = {
                "name": s_name,
                "type": st.session_state.get("ns_type", ""),
                "entry_conditions": entry_conds,
                "exit_conditions": exit_conds,
                "risk_pct": round(st.session_state.get("ns_risk", 2.0) / 100, 4),
                "stop_loss_pct": round(st.session_state.get("ns_stop", 4.0) / 100, 4),
                "created_at": str(date.today()),
                "status": "spec",
            }
            params_path.parent.mkdir(exist_ok=True)
            params_path.write_text(json.dumps(existing, indent=2))
            # Reset form
            for _k in ["ns_name", "ns_id", "ns_type", "ns_risk", "ns_stop"]:
                st.session_state.pop(_k, None)
            for _i in range(st.session_state["ns_entry_count"]):
                st.session_state.pop(f"ns_entry_{_i}", None)
            for _i in range(st.session_state["ns_exit_count"]):
                st.session_state.pop(f"ns_exit_{_i}", None)
            st.session_state["ns_entry_count"] = 1
            st.session_state["ns_exit_count"]  = 1
            st.session_state["ns_saved_ok"] = True
            st.rerun()

    if st.session_state.get("ns_saved_ok"):
        st.success("Strategy spec saved to config/strategy_params.json. Implement the Python class in strategies/ to deploy it.")
        st.session_state["ns_saved_ok"] = False

    # ── Saved specs ──────────────────────────────────────────────────────────
    all_params_now = json.loads(params_path.read_text()) if params_path.exists() else {}
    saved_specs = {k: v for k, v in all_params_now.items() if isinstance(v, dict) and v.get("status") == "spec"}
    if saved_specs:
        st.markdown('<p style="color:var(--text-secondary);font-size:12px;margin:16px 0 6px;">Saved specs (not yet deployed)</p>', unsafe_allow_html=True)
        for spec_id, spec in saved_specs.items():
            with st.expander(f"{spec.get('name', spec_id)} ({spec_id})"):
                entry_list = "".join(f"<li>{c}</li>" for c in spec.get("entry_conditions", []))
                exit_list  = "".join(f"<li>{c}</li>" for c in spec.get("exit_conditions", []))
                st.markdown(
                    f'<p style="font-size:12px;color:var(--text-muted);">Type: {spec.get("type","–")} · '
                    f'Risk: {spec.get("risk_pct",0)*100:.1f}% · Stop: {spec.get("stop_loss_pct",0)*100:.1f}% · '
                    f'Created: {spec.get("created_at","–")}</p>'
                    f'<p style="font-size:12px;color:var(--text-secondary);margin-top:8px;">Entry conditions</p>'
                    f'<ul style="font-size:12px;color:var(--text-muted);margin:4px 0 8px;">{entry_list}</ul>'
                    f'<p style="font-size:12px;color:var(--text-secondary);">Exit conditions</p>'
                    f'<ul style="font-size:12px;color:var(--text-muted);margin:4px 0 8px;">{exit_list}</ul>',
                    unsafe_allow_html=True,
                )
                st.caption("To deploy: implement a Python class in strategies/ following the BaseStrategy interface, add to engine/signals.py STRATEGY_REGISTRY, and wire into engine/screener.py.")
