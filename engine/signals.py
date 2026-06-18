"""
Signal orchestrator — called on each scheduler tick.
Fetches data, adds indicators, runs each active strategy on each symbol,
logs all signals to the DB (executed or not), and returns actionable signals.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pandas as pd
from loguru import logger
from sqlalchemy.orm import Session

from data.market_data import fetch_india_daily, fetch_india_intraday
from data.indicators import add_all_strategy_indicators, add_volume_sma
from database.models import Signal
from strategies.rsi2_overnight import RSI2OvernightStrategy
from strategies.orb_breakout import ORBBreakoutStrategy
from strategies.momentum_continuation import MomentumContinuationStrategy


# Active strategy registry — add / remove strategies here
STRATEGY_REGISTRY = {
    "RSI2_OVN": RSI2OvernightStrategy,
    "ORB_BRK": ORBBreakoutStrategy,
    "MOM_CONT": MomentumContinuationStrategy,
}


def run_eod_scan(
    universe: list[dict],
    db: Session,
    market: str = "INDIA",
    market_is_green: bool = True,
) -> list[dict]:
    """
    End-of-day scan (15:00–15:30 IST). Runs RSI2_OVN and MOM_CONT.
    universe: list of screener output dicts [{symbol, assigned_strategy, ...}]
    Returns list of actionable signal dicts (to be passed to executor).
    """
    actionable: list[dict] = []

    for stock in universe:
        symbol = stock["symbol"]
        assigned = stock.get("assigned_strategy", "RSI2_OVN")

        # Skip ORB in EOD scan — ORB runs intraday
        if assigned == "ORB_BRK":
            continue

        if assigned not in STRATEGY_REGISTRY:
            logger.warning(f"Unknown strategy {assigned} for {symbol}")
            continue

        strategy = STRATEGY_REGISTRY[assigned]()

        # Market filter for MOM_CONT
        if assigned == "MOM_CONT" and not market_is_green:
            _log_skipped(db, symbol, assigned, market, "MARKET_NOT_GREEN")
            continue

        try:
            df = fetch_india_daily(symbol, period="1y")
            if df.empty:
                continue
            df = add_all_strategy_indicators(df)

            signal = strategy.generate_signal(symbol, df)
        except Exception as exc:
            logger.error(f"Signal generation failed for {symbol}: {exc}")
            continue

        executed = signal is not None
        _persist_signal(db, symbol, assigned, market, signal, executed)

        if signal:
            actionable.append(signal)

    logger.info(f"EOD scan complete — {len(actionable)} actionable signal(s)")
    return actionable


def run_orb_scan(
    universe: list[dict],
    db: Session,
    market: str = "INDIA",
    market_is_green: bool = True,
) -> list[dict]:
    """
    Intraday scan for ORB signals (called every 15 min after 10:00 IST).
    Fetches today's 15-min bars and checks for ORB breakout.
    """
    actionable: list[dict] = []
    strategy = ORBBreakoutStrategy()

    if not market_is_green and strategy.params["market_filter"]:
        logger.info("ORB scan: market not green — skipping all")
        return []

    orb_symbols = [s["symbol"] for s in universe if s.get("assigned_strategy") == "ORB_BRK"]

    for symbol in orb_symbols:
        try:
            df_intra = fetch_india_intraday(symbol, interval="15m", period="1d")
            if df_intra.empty:
                continue

            # Add volume baseline (20-day) from daily data
            df_daily = fetch_india_daily(symbol, period="1mo")
            if not df_daily.empty:
                vol_sma_20 = df_daily["volume"].tail(20).mean()
                df_intra["vol_sma_20"] = vol_sma_20

            signal = strategy.generate_signal(symbol, df_intra)
        except Exception as exc:
            logger.error(f"ORB scan failed for {symbol}: {exc}")
            continue

        executed = signal is not None
        _persist_signal(db, symbol, "ORB_BRK", market, signal, executed)

        if signal:
            actionable.append(signal)

    return actionable


def confirm_momentum_entries(
    pending_signals: list[dict],
    db: Session,
    market: str = "INDIA",
) -> list[dict]:
    """
    Called at next-day open (09:30–09:45 IST) to confirm or cancel MOM_CONT signals.
    pending_signals: deferred signals from previous EOD scan.
    """
    strategy = MomentumContinuationStrategy()
    confirmed: list[dict] = []

    for signal in pending_signals:
        if signal.get("strategy_id") != "MOM_CONT":
            confirmed.append(signal)
            continue

        symbol = signal["symbol"]
        try:
            # Get current open price from intraday 1-min bar
            df_open = fetch_india_intraday(symbol, interval="1m", period="1d")
            if df_open.empty:
                continue
            open_price = float(df_open.iloc[0]["open"])
        except Exception as exc:
            logger.error(f"MOM_CONT gap check failed for {symbol}: {exc}")
            continue

        result = strategy.check_gap_and_confirm(signal, open_price)
        if result:
            _persist_signal(db, symbol, "MOM_CONT", market, result, executed=True)
            confirmed.append(result)
        else:
            _log_skipped(db, symbol, "MOM_CONT", market, "GAP_CHECK_FAILED")

    return confirmed


# --------------------------------------------------------------------------- #
# DB helpers                                                                    #
# --------------------------------------------------------------------------- #

def _persist_signal(
    db: Session,
    symbol: str,
    strategy_id: str,
    market: str,
    signal: dict | None,
    executed: bool,
) -> None:
    row = Signal(
        signal_id=str(uuid.uuid4()),
        generated_at=datetime.utcnow(),
        market=market,
        symbol=symbol,
        strategy_id=strategy_id,
        signal_type="ENTRY",
        action=signal["action"] if signal else "HOLD",
        signal_reason=signal["signal_reason"] if signal else "No signal",
        was_executed=executed,
        execution_skipped_reason=None if executed else "no_signal",
    )
    db.add(row)
    db.commit()


def _log_skipped(
    db: Session,
    symbol: str,
    strategy_id: str,
    market: str,
    reason: str,
) -> None:
    row = Signal(
        signal_id=str(uuid.uuid4()),
        generated_at=datetime.utcnow(),
        market=market,
        symbol=symbol,
        strategy_id=strategy_id,
        signal_type="ENTRY",
        action="HOLD",
        signal_reason=f"Skipped: {reason}",
        was_executed=False,
        execution_skipped_reason=reason,
    )
    db.add(row)
    db.commit()
