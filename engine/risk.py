"""
Risk management engine — position sizing and circuit breakers.
The circuit breaker is sacred: HALT → no new entries, no exceptions.
"""
from __future__ import annotations

import json
from datetime import datetime, date, timedelta
from pathlib import Path

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

    # Correlation cap — skip entry if 60-day Pearson r with any open position exceeds this.
    # 0.70 blocks highly co-moving pairs (same sector, related ETFs) while allowing
    # genuinely diversified holdings.
    "max_correlation_threshold": 0.70,
}

# Merge any user-saved overrides from the dashboard Settings page.
# Fail open — a corrupt/missing file must never block the engine from starting.
_OVERRIDES_PATH = Path(__file__).resolve().parent.parent / "config" / "risk_overrides.json"
if _OVERRIDES_PATH.exists():
    try:
        RISK_PARAMS.update(json.loads(_OVERRIDES_PATH.read_text()))
    except Exception:
        pass


def calculate_position_size(
    portfolio_value: float,
    entry_price: float,
    stop_price: float,
    risk_pct: float = RISK_PARAMS["max_risk_per_trade_pct"],
    market: str = "INDIA",
) -> float:
    """
    Fixed-fractional position sizing: risk exactly risk_pct of portfolio on each trade.
    Capped at 25% of portfolio in a single position.
    NSE requires whole shares; US (Alpaca) supports fractional shares.
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

    # NSE requires whole shares; US (Alpaca) supports fractional
    if market == "INDIA":
        return float(int(units))
    return round(units, 4)


# Mean-reversion strategies thrive in high-volatility regimes — VIX spikes
# produce deeper oversold extremes and faster reversions, so halting them during
# high-VIX periods removes their best opportunities.
MEANREV_STRATEGIES = {"RSI2_OVN", "BB_MEANREV"}


def check_circuit_breakers(
    db: Session,
    portfolio_value: float,
    peak_portfolio_value: float,
    market: str = "INDIA",
    strategy_id: str = "",
) -> tuple[str, str]:
    """
    Returns (status, reason).
    status: 'NORMAL' | 'REDUCE_50PCT' | 'HALT'
    Mean-reversion strategies (RSI2_OVN, BB_MEANREV) skip the VIX filter.
    """
    # 1. Max drawdown from peak
    drawdown_pct = (portfolio_value - peak_portfolio_value) / peak_portfolio_value
    if drawdown_pct <= -RISK_PARAMS["max_drawdown_halt_pct"]:
        msg = f"Max drawdown {drawdown_pct:.1%} breached. System halted."
        logger.critical(msg)
        return "HALT", msg

    # 2. Daily loss limit
    today_pnl_pct = _get_today_pnl_pct(db, portfolio_value, market)
    if today_pnl_pct <= -RISK_PARAMS["daily_loss_limit_pct"]:
        msg = f"Daily loss limit hit: {today_pnl_pct:.1%}. Halting new entries today."
        logger.warning(msg)
        return "HALT", msg

    # 3. Weekly loss limit
    week_pnl_pct = _get_week_pnl_pct(db, portfolio_value, market)
    if week_pnl_pct <= -RISK_PARAMS["weekly_loss_limit_pct"]:
        msg = f"Weekly loss limit hit: {week_pnl_pct:.1%}. Halting new entries this week."
        logger.warning(msg)
        return "HALT", msg

    # 4. VIX regime filter — skipped for mean-reversion strategies
    if strategy_id not in MEANREV_STRATEGIES:
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


def check_position_limit(db: Session, market: str = "INDIA") -> bool:
    """Returns True if we can open a new position (under max concurrent positions)."""
    open_count = db.query(func.count(Trade.trade_id)).filter(
        Trade.timestamp_exit.is_(None),
        Trade.market == market,
    ).scalar() or 0
    return open_count < RISK_PARAMS["max_concurrent_positions"]


def check_portfolio_heat(db: Session, portfolio_value: float, market: str = "INDIA") -> bool:
    """Returns True if total risk across open positions is under max_portfolio_heat_pct."""
    open_trades = db.query(Trade).filter(
        Trade.timestamp_exit.is_(None),
        Trade.market == market,
    ).all()
    total_risk = sum(
        abs(t.entry_price - t.stop_loss_price) * t.quantity
        for t in open_trades
        if t.entry_price and t.stop_loss_price and t.quantity
    )
    heat_pct = total_risk / portfolio_value if portfolio_value else 0
    return heat_pct < RISK_PARAMS["max_portfolio_heat_pct"]


def _daily_returns(closes: list[float]) -> list[float]:
    return [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]


def _pearson_r(x: list[float], y: list[float]) -> float:
    """60-day Pearson correlation. Pure Python, no numpy. Returns 0.0 when undefined."""
    n = min(len(x), len(y))
    if n < 2:
        return 0.0
    x, y = x[-n:], y[-n:]
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    num = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    den_x = sum((xi - mean_x) ** 2 for xi in x) ** 0.5
    den_y = sum((yi - mean_y) ** 2 for yi in y) ** 0.5
    if den_x == 0 or den_y == 0:
        return 0.0
    return round(num / (den_x * den_y), 4)


def check_correlation_risk(
    db: Session,
    candidate: str,
    market: str = "INDIA",
    threshold: float | None = None,
) -> tuple[bool, str]:
    """
    Returns (True, "") if safe to enter, (False, reason) if the candidate's 60-day
    return series is too correlated with an existing open position.
    Fails open — any yfinance error is treated as uncorrelated so it never silently
    blocks entries due to a transient API outage.
    """
    from data.market_data import fetch_india_daily, fetch_us_daily

    if threshold is None:
        threshold = RISK_PARAMS["max_correlation_threshold"]

    open_trades = db.query(Trade).filter(
        Trade.timestamp_exit.is_(None),
        Trade.market == market,
    ).all()
    if not open_trades:
        return True, ""

    fetch_fn = fetch_india_daily if market == "INDIA" else fetch_us_daily

    try:
        cand_df = fetch_fn(candidate, period="3mo")
    except Exception:
        return True, ""  # fail open
    if cand_df.empty or len(cand_df) < 2:
        return True, ""

    cand_returns = _daily_returns(cand_df["close"].tolist())

    for trade in open_trades:
        if trade.symbol == candidate:
            continue
        try:
            pos_df = fetch_fn(trade.symbol, period="3mo")
        except Exception:
            continue  # treat as uncorrelated
        if pos_df.empty or len(pos_df) < 2:
            continue
        pos_returns = _daily_returns(pos_df["close"].tolist())
        r = _pearson_r(cand_returns, pos_returns)
        if abs(r) > threshold:
            msg = f"r({candidate}, {trade.symbol})={r:.2f} > {threshold} — skipping entry"
            logger.info(f"Correlation block: {msg}")
            return False, msg

    return True, ""


# --------------------------------------------------------------------------- #
# Internal helpers                                                              #
# --------------------------------------------------------------------------- #

def _get_today_pnl_pct(db: Session, portfolio_value: float, market: str = "INDIA") -> float:
    today = date.today()
    rows = db.query(Trade).filter(
        func.date(Trade.timestamp_exit) == today,
        Trade.net_pnl.isnot(None),
        Trade.market == market,
    ).all()
    total = sum(t.net_pnl for t in rows)
    return total / portfolio_value if portfolio_value else 0.0


def _get_week_pnl_pct(db: Session, portfolio_value: float, market: str = "INDIA") -> float:
    week_start = date.today() - timedelta(days=date.today().weekday())
    rows = db.query(Trade).filter(
        func.date(Trade.timestamp_exit) >= week_start,
        Trade.net_pnl.isnot(None),
        Trade.market == market,
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
