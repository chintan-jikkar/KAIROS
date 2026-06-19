"""
Risk management engine — position sizing and circuit breakers.
The circuit breaker is sacred: HALT → no new entries, no exceptions.
"""
from __future__ import annotations

from datetime import datetime, date, timedelta

import yfinance as yf
from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models import Trade, PortfolioSnapshot

RISK_PARAMS = {
    # Per-trade sizing
    "max_risk_per_trade_pct": 0.02,         # Risk 2% of portfolio per trade
    "max_portfolio_heat_pct": 0.10,         # Max 10% total portfolio at risk simultaneously
    "max_concurrent_positions": 6,
    "max_single_position_pct": 0.25,        # Never more than 25% in one stock

    # Stop losses
    "hard_stop_loss_pct": 0.04,
    "atr_stop_multiplier": 2.0,

    # Portfolio-level circuit breakers
    "daily_loss_limit_pct": 0.05,
    "weekly_loss_limit_pct": 0.08,
    "max_drawdown_halt_pct": 0.20,

    # India VIX thresholds
    "india_vix_high_threshold": 20.0,
    "india_vix_extreme_threshold": 25.0,

    # US VIX thresholds
    "us_vix_high_threshold": 25.0,
    "us_vix_extreme_threshold": 30.0,
}


def calculate_position_size(
    portfolio_value: float,
    entry_price: float,
    stop_price: float,
    risk_pct: float = RISK_PARAMS["max_risk_per_trade_pct"],
) -> float:
    """
    Fixed-fractional position sizing: risk exactly risk_pct of portfolio on each trade.
    Capped at 25% of portfolio in a single position.
    Returns quantity (fractional shares supported).
    """
    risk_per_unit = abs(entry_price - stop_price)
    if risk_per_unit == 0:
        logger.warning("risk_per_unit=0 (entry == stop), returning 0 quantity")
        return 0.0

    risk_amount = portfolio_value * risk_pct
    units = risk_amount / risk_per_unit

    # Single-position cap
    max_units = (portfolio_value * RISK_PARAMS["max_single_position_pct"]) / entry_price
    if units > max_units:
        logger.debug(f"Position capped at 25% limit: {units:.2f} → {max_units:.2f} units")
        units = max_units

    return round(units, 4)


def check_circuit_breakers(
    db: Session,
    portfolio_value: float,
    peak_portfolio_value: float,
    market: str = "INDIA",
) -> tuple[str, str]:
    """
    Returns (status, reason).
    status: 'NORMAL' | 'REDUCE_50PCT' | 'HALT'
    """
    # 1. Max drawdown from peak
    drawdown_pct = (portfolio_value - peak_portfolio_value) / peak_portfolio_value
    if drawdown_pct <= -RISK_PARAMS["max_drawdown_halt_pct"]:
        msg = f"Max drawdown {drawdown_pct:.1%} breached. System halted."
        logger.critical(msg)
        return "HALT", msg

    # 2. Daily loss limit
    today_pnl_pct = _get_today_pnl_pct(db, portfolio_value)
    if today_pnl_pct <= -RISK_PARAMS["daily_loss_limit_pct"]:
        msg = f"Daily loss limit hit: {today_pnl_pct:.1%}. Halting new entries today."
        logger.warning(msg)
        return "HALT", msg

    # 3. Weekly loss limit
    week_pnl_pct = _get_week_pnl_pct(db, portfolio_value)
    if week_pnl_pct <= -RISK_PARAMS["weekly_loss_limit_pct"]:
        msg = f"Weekly loss limit hit: {week_pnl_pct:.1%}. Halting new entries this week."
        logger.warning(msg)
        return "HALT", msg

    # 4. VIX regime filter
    vix = _get_vix(market)
    if vix is not None:
        extreme = RISK_PARAMS[f"{market.lower()}_vix_extreme_threshold"]
        high = RISK_PARAMS[f"{market.lower()}_vix_high_threshold"]
        if vix > extreme:
            msg = f"VIX={vix:.1f} extreme. No new entries."
            logger.warning(msg)
            return "HALT", msg
        if vix > high:
            msg = f"VIX={vix:.1f} elevated. Reducing position size 50%."
            logger.info(msg)
            return "REDUCE_50PCT", msg

    return "NORMAL", "All systems operational."


def check_position_limit(db: Session) -> bool:
    """Returns True if we can open a new position (under max concurrent positions)."""
    open_count = db.query(func.count(Trade.trade_id)).filter(
        Trade.timestamp_exit.is_(None)
    ).scalar() or 0
    return open_count < RISK_PARAMS["max_concurrent_positions"]


def check_portfolio_heat(db: Session, portfolio_value: float) -> bool:
    """Returns True if total risk across open positions is under max_portfolio_heat_pct."""
    open_trades = db.query(Trade).filter(Trade.timestamp_exit.is_(None)).all()
    total_risk = sum(
        abs(t.entry_price - t.stop_loss_price) * t.quantity
        for t in open_trades
        if t.entry_price and t.stop_loss_price and t.quantity
    )
    heat_pct = total_risk / portfolio_value if portfolio_value else 0
    return heat_pct < RISK_PARAMS["max_portfolio_heat_pct"]


# --------------------------------------------------------------------------- #
# Internal helpers                                                              #
# --------------------------------------------------------------------------- #

def _get_today_pnl_pct(db: Session, portfolio_value: float) -> float:
    today = date.today()
    rows = db.query(Trade).filter(
        func.date(Trade.timestamp_exit) == today,
        Trade.net_pnl.isnot(None),
    ).all()
    total = sum(t.net_pnl for t in rows)
    return total / portfolio_value if portfolio_value else 0.0


def _get_week_pnl_pct(db: Session, portfolio_value: float) -> float:
    week_start = date.today() - timedelta(days=date.today().weekday())
    rows = db.query(Trade).filter(
        func.date(Trade.timestamp_exit) >= week_start,
        Trade.net_pnl.isnot(None),
    ).all()
    total = sum(t.net_pnl for t in rows)
    return total / portfolio_value if portfolio_value else 0.0


def _get_vix(market: str) -> float | None:
    ticker = "^INDIAVIX" if market == "INDIA" else "^VIX"
    try:
        df = yf.download(ticker, period="2d", interval="1d",
                         auto_adjust=True, progress=False)
        if not df.empty:
            return float(df["Close"].squeeze().iloc[-1])
    except Exception as exc:
        logger.warning(f"Could not fetch VIX for {market}: {exc}")
    return None
