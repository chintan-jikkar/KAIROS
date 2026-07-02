"""
APScheduler job definitions — dual-market (India NSE / US NYSE).
Run this as the main algo process: python engine/scheduler.py
Set ACTIVE_MARKET=US in env to switch to NYSE Eastern-Time schedule.

India (IST, Asia/Kolkata) schedule:
  09:00 IST Mon–Fri  — morning health check
  09:00–14:45 IST    — BB_MEANREV scan every 15 min
  09:20 IST Mon–Fri  — strategy-driven exit check (RSI2_OVN, TREND_EMA, etc.)
  09:30 IST Mon–Fri  — confirm MOM_CONT deferred signals from previous EOD
  10:00–11:30 IST    — ORB scan every 15 min
  15:00 IST Mon–Fri  — EOD entry scan (RSI2_OVN, MOM_CONT flags, TREND_EMA)
  15:15 IST Mon–Fri  — strategy-driven exit check (second pass)
  15:20 IST Mon–Fri  — force-exit all open MOM_CONT + ORB_BRK + BB_MEANREV positions
  15:30 IST Mon–Fri  — take portfolio snapshot
  Sunday 20:00 IST   — run weekly screener, refresh universe

US (ET, America/New_York) schedule:
  09:30 ET  Mon–Fri  — morning health check (NYSE open)
  09:35 ET  Mon–Fri  — strategy-driven exit check
  09:45 ET  Mon–Fri  — confirm MOM_CONT deferred signals from previous EOD
  10:00–11:30 ET     — ORB scan every 15 min
  09:30–15:45 ET     — BB_MEANREV scan every 15 min
  15:30 ET  Mon–Fri  — EOD entry scan (RSI2_OVN, MOM_CONT flags, TREND_EMA)
  15:45 ET  Mon–Fri  — strategy-driven exit check (second pass)
  15:50 ET  Mon–Fri  — force-exit all open MOM_CONT + ORB_BRK + BB_MEANREV positions
  16:00 ET  Mon–Fri  — take portfolio snapshot
  Sunday 18:00 ET    — run weekly screener, refresh universe
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytz
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from brokers.paper import PaperBroker
from config.settings import (
    DB_PATH, LOG_PATH, LOG_LEVEL,
    STARTING_CAPITAL_INR, ACTIVE_MARKET, EXECUTION_MODE,
)
from data.market_data import fetch_india_daily, fetch_us_daily
from database.models import Base
from database.portfolio import get_latest_snapshot
from database.trade_log import save_pending_signal, load_pending_signals, clear_pending_signals
from engine.executor import Executor
from engine.screener import run_india_screener, run_us_screener
from engine.signals import (
    run_eod_scan, run_orb_scan, run_meanrev_scan,
    confirm_momentum_entries, check_exits_for_open_trades,
)

IST = pytz.timezone("Asia/Kolkata")
ET = pytz.timezone("America/New_York")
TZ = ET if ACTIVE_MARKET == "US" else IST

# Global state (persists between ticks within a process run)
_pending_momentum_signals: list[dict] = []
_active_universe: list[dict] = []


def _make_session():
    engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _make_executor(db, broker):
    return Executor(
        db=db,
        broker=broker,
        market=ACTIVE_MARKET,
        execution_mode=EXECUTION_MODE,
        segment="equity_intraday",
    )


_market_open_cache: dict[str, bool] = {}  # key: "INDIA:2026-07-01"


def _is_market_open(market: str = "INDIA") -> bool:
    """Return False on exchange holidays — no intraday bars means no trading today.
    Result is cached per market per calendar day so every job in the same process day
    shares a single yfinance call. Fails open on any fetch error."""
    from data.market_data import fetch_india_intraday, fetch_us_intraday
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    cache_key = f"{market}:{today}"
    if cache_key in _market_open_cache:
        return _market_open_cache[cache_key]

    ticker = "^NSEI" if market == "INDIA" else "SPY"
    try:
        df = fetch_india_intraday(ticker, interval="1m", period="1d") if market == "INDIA" \
            else fetch_us_intraday(ticker, interval="1m", period="1d")
        result = not df.empty
        if not result:
            logger.info(f"Market holiday guard: no intraday bars for {ticker} — skipping today")
    except Exception as exc:
        logger.warning(f"Holiday check failed for {market}: {exc}")
        result = True  # fail open

    _market_open_cache[cache_key] = result
    return result


def _get_market_is_green() -> bool:
    """Quick proxy: NIFTY50 (India) or SPY (US) positive today vs yesterday."""
    try:
        if ACTIVE_MARKET == "US":
            df = fetch_us_daily("SPY", period="5d")
        else:
            from data.market_data import fetch_india_intraday
            df = fetch_india_intraday("^NSEI", interval="1d", period="2d")
        if len(df) >= 2:
            return float(df["close"].iloc[-1]) > float(df["close"].iloc[-2])
    except Exception as exc:
        logger.warning(f"Could not fetch benchmark for market filter: {exc}")
    return True  # default to green if fetch fails (conservative)


def _get_current_prices(universe: list[dict]) -> dict:
    from data.market_data import fetch_india_intraday, fetch_us_intraday
    fetch_intra = fetch_us_intraday if ACTIVE_MARKET == "US" else fetch_india_intraday
    prices = {}
    for stock in universe:
        sym = stock["symbol"]
        try:
            df = fetch_intra(sym, interval="1m", period="1d")
            if not df.empty:
                prices[sym] = float(df["close"].iloc[-1])
        except Exception:
            pass
    return prices


# --------------------------------------------------------------------------- #
# Job functions                                                                 #
# --------------------------------------------------------------------------- #

def job_morning_check():
    logger.info("=== KAIROS MORNING CHECK — system ready ===")
    logger.info(f"Mode: {EXECUTION_MODE} | Market: {ACTIVE_MARKET} | Universe: {len(_active_universe)} stocks")
    if not _active_universe:
        logger.warning("Universe is empty — run Sunday screener or restart after Sunday 20:00 IST")


def job_confirm_momentum():
    """09:30 IST — confirm or cancel deferred MOM_CONT signals from previous EOD."""
    global _pending_momentum_signals
    if not _is_market_open(ACTIVE_MARKET):
        return

    db = _make_session()

    # Crash-recovery: if in-memory list is empty (process restarted overnight), reload from DB.
    if not _pending_momentum_signals:
        _pending_momentum_signals = load_pending_signals(db, ACTIVE_MARKET)
    if not _pending_momentum_signals:
        db.close()
        return

    from config.settings import STARTING_CAPITAL_INR
    snap = get_latest_snapshot(db, ACTIVE_MARKET)
    capital = snap.portfolio_value if snap else STARTING_CAPITAL_INR
    broker = PaperBroker(db, capital, market=ACTIVE_MARKET)

    confirmed = confirm_momentum_entries(_pending_momentum_signals, db, ACTIVE_MARKET)
    executor = _make_executor(db, broker)
    for signal in confirmed:
        result = executor.execute_entry(signal)
        logger.info(f"MOM_CONT entry: {signal['symbol']} → {result['status']} ({result['reason']})")

    _pending_momentum_signals.clear()
    clear_pending_signals(db, ACTIVE_MARKET)
    db.close()


def job_orb_scan():
    """10:00–11:30 IST every 15 min — check for ORB breakout signals."""
    if not _is_market_open(ACTIVE_MARKET):
        return
    now = datetime.now(TZ)
    if now.hour == 11 and now.minute > 30:
        return  # ORB window closed

    db = _make_session()
    snap = get_latest_snapshot(db, ACTIVE_MARKET)
    capital = snap.portfolio_value if snap else STARTING_CAPITAL_INR
    broker = PaperBroker(db, capital, market=ACTIVE_MARKET)
    executor = _make_executor(db, broker)

    market_green = _get_market_is_green()
    signals = run_orb_scan(_active_universe, db, ACTIVE_MARKET, market_green)
    for signal in signals:
        result = executor.execute_entry(signal)
        logger.info(f"ORB entry: {signal['symbol']} → {result['status']} ({result['reason']})")

    db.close()


def job_meanrev_scan():
    """09:00–14:45 IST every 15 min — check for BB_MEANREV intraday signals."""
    if not _is_market_open(ACTIVE_MARKET):
        return

    db = _make_session()
    snap = get_latest_snapshot(db, ACTIVE_MARKET)
    capital = snap.portfolio_value if snap else STARTING_CAPITAL_INR
    broker = PaperBroker(db, capital, market=ACTIVE_MARKET)
    executor = _make_executor(db, broker)

    signals = run_meanrev_scan(_active_universe, db, ACTIVE_MARKET)
    for signal in signals:
        result = executor.execute_entry(signal)
        logger.info(f"BB_MEANREV entry: {signal['symbol']} → {result['status']} ({result['reason']})")

    db.close()


def job_check_exits():
    """
    09:20 and 15:15 IST — check open RSI2_OVN/TREND_EMA (and any other
    non-force-exited) positions against their own should_exit() logic.
    ORB_BRK/MOM_CONT/BB_MEANREV are also covered here for anything that
    should exit before the hard 15:20 EOD force-exit catches them.
    """
    if not _is_market_open(ACTIVE_MARKET):
        return

    db = _make_session()
    snap = get_latest_snapshot(db, ACTIVE_MARKET)
    capital = snap.portfolio_value if snap else STARTING_CAPITAL_INR
    broker = PaperBroker(db, capital, market=ACTIVE_MARKET)
    executor = _make_executor(db, broker)

    to_exit = check_exits_for_open_trades(db)
    for item in to_exit:
        result = executor.execute_exit(item["symbol"], item["exit_price"], item["exit_reason"])
        logger.info(f"Strategy-driven exit: {item['symbol']} ({item['exit_reason']}) → {result['status']}")

    db.close()


def job_eod_scan():
    """15:00 IST — RSI2_OVN entries + MOM_CONT flags for next day."""
    global _pending_momentum_signals
    if not _is_market_open(ACTIVE_MARKET):
        return

    db = _make_session()
    snap = get_latest_snapshot(db, ACTIVE_MARKET)
    capital = snap.portfolio_value if snap else STARTING_CAPITAL_INR
    broker = PaperBroker(db, capital, market=ACTIVE_MARKET)
    executor = _make_executor(db, broker)

    market_green = _get_market_is_green()
    signals = run_eod_scan(_active_universe, db, ACTIVE_MARKET, market_green)

    for signal in signals:
        if signal.get("deferred"):
            _pending_momentum_signals.append(signal)
            save_pending_signal(db, ACTIVE_MARKET, signal)
            logger.info(f"MOM_CONT deferred: {signal['symbol']} — checking gap at next open")
        else:
            result = executor.execute_entry(signal)
            logger.info(f"RSI2_OVN entry: {signal['symbol']} → {result['status']} ({result['reason']})")

    db.close()


def job_eod_exit():
    """15:20 IST — force-close all MOM_CONT and ORB positions (1-day hold only)."""
    if not _is_market_open(ACTIVE_MARKET):
        return

    db = _make_session()
    snap = get_latest_snapshot(db, ACTIVE_MARKET)
    capital = snap.portfolio_value if snap else STARTING_CAPITAL_INR
    broker = PaperBroker(db, capital, market=ACTIVE_MARKET)
    executor = _make_executor(db, broker)

    from database.trade_log import get_open_trades
    intraday_strategies = {"MOM_CONT", "ORB_BRK", "BB_MEANREV"}
    intraday_trades = [
        t for t in get_open_trades(db) if t.strategy_id in intraday_strategies
    ]

    if not intraday_trades:
        db.close()
        return

    symbols = [t.symbol for t in intraday_trades]
    prices = _get_current_prices([{"symbol": s} for s in symbols])

    for trade in intraday_trades:
        price = prices.get(trade.symbol, trade.entry_price)
        result = executor.execute_exit(trade.symbol, price, "EOD")
        logger.info(f"EOD exit: {trade.symbol} → {result['status']}")

    db.close()


def job_eod_snapshot():
    """15:30 IST — take EOD portfolio snapshot."""
    if not _is_market_open(ACTIVE_MARKET):
        return

    db = _make_session()
    snap = get_latest_snapshot(db, ACTIVE_MARKET)
    capital = snap.portfolio_value if snap else STARTING_CAPITAL_INR
    broker = PaperBroker(db, capital, market=ACTIVE_MARKET)
    executor = _make_executor(db, broker)

    prices = _get_current_prices(_active_universe)
    executor.take_eod_snapshot(prices)
    db.close()


def job_weekly_screener():
    """Sunday evening — refresh universe, re-assign strategies."""
    global _active_universe
    logger.info(f"=== KAIROS WEEKLY SCREENER RUNNING ({ACTIVE_MARKET}) ===")
    results = run_us_screener(top_n=6) if ACTIVE_MARKET == "US" else run_india_screener(top_n=6)
    _active_universe = results
    logger.info(f"Universe updated: {[s['symbol'] for s in _active_universe]}")

    cache_path = Path("config/universe_cache.json")
    cache_path.write_text(json.dumps(_active_universe, indent=2))


# --------------------------------------------------------------------------- #
# Bootstrap                                                                     #
# --------------------------------------------------------------------------- #

def _load_cached_universe():
    """Load last screener run on startup so we don't need to wait until Sunday."""
    global _active_universe
    cache_path = Path("config/universe_cache.json")
    if cache_path.exists():
        _active_universe = json.loads(cache_path.read_text())
        logger.info(f"Loaded cached universe: {[s['symbol'] for s in _active_universe]}")
    else:
        logger.warning("No cached universe found — running screener now")
        job_weekly_screener()


def _register_india_schedule(scheduler: BlockingScheduler) -> None:
    """Register all NSE/India jobs in IST timezone."""
    scheduler.add_job(job_morning_check, CronTrigger(
        hour=9, minute=0, day_of_week="mon-fri", timezone=IST))
    scheduler.add_job(job_check_exits, CronTrigger(
        hour=9, minute=20, day_of_week="mon-fri", timezone=IST))
    scheduler.add_job(job_confirm_momentum, CronTrigger(
        hour=9, minute=30, day_of_week="mon-fri", timezone=IST))
    scheduler.add_job(job_orb_scan, CronTrigger(
        hour="10,11", minute="0,15,30,45", day_of_week="mon-fri", timezone=IST))
    scheduler.add_job(job_meanrev_scan, CronTrigger(
        hour="9,10,11,12,13,14", minute="0,15,30,45", day_of_week="mon-fri", timezone=IST))
    scheduler.add_job(job_eod_scan, CronTrigger(
        hour=15, minute=0, day_of_week="mon-fri", timezone=IST))
    scheduler.add_job(job_check_exits, CronTrigger(
        hour=15, minute=15, day_of_week="mon-fri", timezone=IST))
    scheduler.add_job(job_eod_exit, CronTrigger(
        hour=15, minute=20, day_of_week="mon-fri", timezone=IST))
    scheduler.add_job(job_eod_snapshot, CronTrigger(
        hour=15, minute=30, day_of_week="mon-fri", timezone=IST))
    scheduler.add_job(job_weekly_screener, CronTrigger(
        hour=20, minute=0, day_of_week="sun", timezone=IST))
    logger.info("India (NSE/IST) schedule registered.")


def _register_us_schedule(scheduler: BlockingScheduler) -> None:
    """Register all NYSE/US jobs in ET timezone."""
    scheduler.add_job(job_morning_check, CronTrigger(
        hour=9, minute=30, day_of_week="mon-fri", timezone=ET))
    scheduler.add_job(job_check_exits, CronTrigger(
        hour=9, minute=35, day_of_week="mon-fri", timezone=ET))
    scheduler.add_job(job_confirm_momentum, CronTrigger(
        hour=9, minute=45, day_of_week="mon-fri", timezone=ET))
    # ORB window: 10:00–11:30 ET (first 2 hrs of session mirror India pattern)
    scheduler.add_job(job_orb_scan, CronTrigger(
        hour="10,11", minute="0,15,30,45", day_of_week="mon-fri", timezone=ET))
    # BB_MEANREV: 09:30–15:45 ET full session
    scheduler.add_job(job_meanrev_scan, CronTrigger(
        hour="9,10,11,12,13,14,15", minute="30,45,0,15", day_of_week="mon-fri", timezone=ET))
    scheduler.add_job(job_eod_scan, CronTrigger(
        hour=15, minute=30, day_of_week="mon-fri", timezone=ET))
    scheduler.add_job(job_check_exits, CronTrigger(
        hour=15, minute=45, day_of_week="mon-fri", timezone=ET))
    scheduler.add_job(job_eod_exit, CronTrigger(
        hour=15, minute=50, day_of_week="mon-fri", timezone=ET))
    scheduler.add_job(job_eod_snapshot, CronTrigger(
        hour=16, minute=0, day_of_week="mon-fri", timezone=ET))
    scheduler.add_job(job_weekly_screener, CronTrigger(
        hour=18, minute=0, day_of_week="sun", timezone=ET))
    logger.info("US (NYSE/ET) schedule registered.")


def main():
    from loguru import logger as _logger
    _logger.add(LOG_PATH, level=LOG_LEVEL, rotation="1 week")

    _load_cached_universe()

    scheduler = BlockingScheduler(timezone=TZ)

    if ACTIVE_MARKET == "US":
        _register_us_schedule(scheduler)
    else:
        _register_india_schedule(scheduler)

    logger.info(f"KAIROS scheduler started [{ACTIVE_MARKET}]. Press Ctrl+C to stop.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("KAIROS scheduler stopped.")


if __name__ == "__main__":
    main()
