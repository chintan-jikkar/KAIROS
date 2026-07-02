"""
Weekly stock universe screener — runs every Sunday 20:00 IST.
Filters INDIA_MASTER_POOL against INDIA_SCREEN_CRITERIA and returns top 5-6 stocks
ranked by combined ATR% + volume-ratio score. Auto-assigns best-fit strategy.
"""
import datetime

import pandas as pd
import yfinance as yf
from loguru import logger

from data.market_data import fetch_india_daily, fetch_us_daily
from data.indicators import add_all_strategy_indicators, add_atr_pct, add_volume_ratio
from data.universe import (
    get_india_all_symbols,
    get_us_all_symbols,
    INDIA_SCREEN_CRITERIA,
    US_SCREEN_CRITERIA,
    STRATEGY_ASSIGNMENT_RULES,
    US_STRATEGY_ASSIGNMENT_RULES,
)
from engine.signals import STRATEGY_REGISTRY


def _has_earnings_soon(ticker_str: str, days: int) -> bool:
    """Return True if yfinance reports an earnings date within `days` calendar days
    from today. Fails open — returns False on any API failure or missing data so
    that stocks without calendar coverage (common for NSE) are not wrongly excluded."""
    try:
        cal = yf.Ticker(ticker_str).calendar
        if not cal:
            return False
        dates = cal.get("Earnings Date") or []
        if not isinstance(dates, list):
            dates = [dates]
        today = datetime.date.today()
        cutoff = today + datetime.timedelta(days=days)
        return any(d is not None and today <= d <= cutoff for d in dates)
    except Exception:
        return False


def _compute_beta_vs_spy(symbol_returns: list[float], spy_returns: list[float]) -> float:
    """beta = cov(symbol, spy) / var(spy). Pure Python, no numpy dependency."""
    n = min(len(symbol_returns), len(spy_returns))
    if n < 2:
        return 1.0
    s = symbol_returns[-n:]
    m = spy_returns[-n:]
    mean_s = sum(s) / n
    mean_m = sum(m) / n
    cov = sum((s[i] - mean_s) * (m[i] - mean_m) for i in range(n)) / (n - 1)
    var_m = sum((m[i] - mean_m) ** 2 for i in range(n)) / (n - 1)
    if var_m == 0:  # exact equality safe: inputs are literal zeros, not computed floats
        return 1.0
    return round(cov / var_m, 4)


def run_india_screener(top_n: int | None = 6) -> list[dict]:
    """
    Returns a ranked list of dicts, each with:
        symbol, atr_pct, vol_ratio, rsi14, beta, assigned_strategy, score
    top_n caps the result (used to pick the active trading universe);
    pass None to return every qualifying stock (used for browsing in the Markets page).
    """
    # Fetch NIFTY50 once for beta computation across all symbols.
    # ^NSEI is yfinance's ticker for the index; fetch_us_daily passes it unchanged (no .NS suffix).
    nifty_df = fetch_us_daily("^NSEI", period="3mo")
    if not nifty_df.empty and len(nifty_df) >= 2:
        nifty_closes = nifty_df["close"].tolist()
        nifty_returns = [
            (nifty_closes[i] - nifty_closes[i - 1]) / nifty_closes[i - 1]
            for i in range(1, len(nifty_closes))
        ]
    else:
        logger.warning("Could not fetch ^NSEI data — India beta will default to 1.0")
        nifty_returns = []

    symbols = get_india_all_symbols()
    results = []

    for symbol in symbols:
        try:
            record = _evaluate_symbol(symbol, nifty_returns)
            if record:
                results.append(record)
        except Exception as exc:
            logger.warning(f"Screener skipped {symbol}: {exc}")

    if not results:
        logger.warning("Screener returned 0 qualifying stocks")
        return []

    # Rank by composite score against fixed absolute baselines (not relative to
    # this week's best) so scores are comparable across different screener runs.
    # India baselines: ATR 3.0% and vol_ratio 2.0x represent a genuinely active
    # trending name; anything at or above baseline scores the full 60 or 40 points.
    ATR_BASELINE = 3.0
    VOL_BASELINE = 2.0
    df = pd.DataFrame(results)
    df["atr_norm"] = (df["atr_pct"] / ATR_BASELINE).clip(upper=1.0)
    df["vol_norm"] = (df["vol_ratio"] / VOL_BASELINE).clip(upper=1.0)
    df["score"] = (df["atr_norm"] * 60 + df["vol_norm"] * 40).round(1)
    df = df.sort_values("score", ascending=False)
    if top_n is not None:
        df = df.head(top_n)

    ranked = df.to_dict(orient="records")
    logger.info(f"Screener selected {len(ranked)} stocks: {[r['symbol'] for r in ranked]}")
    return ranked


def run_us_screener(top_n: int | None = 6) -> list[dict]:
    """
    Returns a ranked list of dicts with the same shape as run_india_screener.
    SPY daily data is fetched once here and passed to each symbol evaluation
    to avoid one API call per symbol for beta computation.
    """
    spy_df = fetch_us_daily("SPY", period="3mo")
    if spy_df.empty or len(spy_df) < 2:
        logger.warning("Could not fetch SPY data for beta computation — aborting US screener")
        return []
    spy_closes = spy_df["close"].tolist()
    spy_returns = [
        (spy_closes[i] - spy_closes[i - 1]) / spy_closes[i - 1]
        for i in range(1, len(spy_closes))
    ]

    symbols = get_us_all_symbols()
    results = []

    for symbol in symbols:
        try:
            record = _evaluate_symbol_us(symbol, spy_returns)
            if record:
                results.append(record)
        except Exception as exc:
            logger.warning(f"US screener skipped {symbol}: {exc}")

    if not results:
        logger.warning("US screener returned 0 qualifying stocks")
        return []

    # Absolute baselines — US large-caps are more volatile than NSE names.
    ATR_BASELINE = 3.5
    VOL_BASELINE = 2.0
    df = pd.DataFrame(results)
    df["atr_norm"] = (df["atr_pct"] / ATR_BASELINE).clip(upper=1.0)
    df["vol_norm"] = (df["vol_ratio"] / VOL_BASELINE).clip(upper=1.0)
    df["score"] = (df["atr_norm"] * 60 + df["vol_norm"] * 40).round(1)
    df = df.sort_values("score", ascending=False)
    if top_n is not None:
        df = df.head(top_n)

    ranked = df.to_dict(orient="records")
    logger.info(f"US screener selected {len(ranked)} stocks: {[r['symbol'] for r in ranked]}")
    return ranked


def _evaluate_symbol(symbol: str, nifty_returns: list[float] | None = None) -> dict | None:
    c = INDIA_SCREEN_CRITERIA

    df = fetch_india_daily(symbol, period="3mo")
    if df.empty or len(df) < 60:
        return None

    df = add_all_strategy_indicators(df)
    last = df.iloc[-1]

    # Price filter
    price = float(last["close"])
    if not (c["min_price_inr"] <= price <= c["max_price_inr"]):
        return None

    # Volume filter
    avg_vol = float(df["volume"].tail(20).mean())
    if avg_vol < c["min_avg_daily_volume"]:
        return None

    # ATR% filter
    atr_pct = float(last.get("atr_pct_14", 0))
    if atr_pct < c["min_atr_pct_14d"]:
        return None

    # RSI14 filter — skipped for MOM_CONT candidates because a stock posting the
    # required +3% move with 2x volume always has RSI14 > 70 by construction.
    vol_ratio = float(last.get("vol_ratio_20", 1.0))
    mom_cont_rules = STRATEGY_ASSIGNMENT_RULES["MOM_CONT"]
    is_mom_cont_candidate = (
        atr_pct >= mom_cont_rules["atr_min"]
        and vol_ratio >= mom_cont_rules["volume_ratio_min"]
    )
    if not is_mom_cont_candidate:
        rsi14 = float(last.get("rsi_14", 50))
        rsi_lo, rsi_hi = c["rsi14_range"]
        if not (rsi_lo <= rsi14 <= rsi_hi):
            return None
    else:
        rsi14 = float(last.get("rsi_14", 50))

    # Earnings blackout filter — skip if earnings within the configured window
    no_earnings_days = c.get("no_earnings_within_days")
    if no_earnings_days and _has_earnings_soon(f"{symbol}.NS", no_earnings_days):
        logger.debug(f"Screener skipped {symbol}: earnings within {no_earnings_days} days")
        return None

    adx = float(last.get("adx_14")) if last.get("adx_14") is not None else None

    closes = df["close"].tolist()
    symbol_returns = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
    beta = _compute_beta_vs_spy(symbol_returns, nifty_returns or [])

    strategy_id = _assign_strategy(atr_pct=atr_pct, beta=beta, vol_ratio=vol_ratio, adx=adx)

    # Reuses the df already fetched/indicator-computed above — assignment is about which
    # strategy's regime fits the stock, not that its entry conditions are met today, so most
    # rows won't have a live signal. Real target/stop only show up when one actually fires.
    signal = STRATEGY_REGISTRY[strategy_id]().generate_signal(symbol, df)

    return {
        "symbol": symbol,
        "price": round(price, 2),
        "atr_pct": round(atr_pct, 2),
        "vol_ratio": round(vol_ratio, 2),
        "avg_volume": int(avg_vol),
        "rsi14": round(rsi14, 1),
        "beta": beta,
        "adx": round(adx, 1) if adx is not None else None,
        "assigned_strategy": strategy_id,
        "has_live_signal": signal is not None,
        "target_price": round(signal["target_price"], 2) if signal else None,
        "score": 0.0,  # filled by caller after normalisation
    }


def _evaluate_symbol_us(symbol: str, spy_returns: list[float]) -> dict | None:
    c = US_SCREEN_CRITERIA

    df = fetch_us_daily(symbol, period="3mo")
    if df.empty or len(df) < 60:
        return None

    df = add_all_strategy_indicators(df)
    last = df.iloc[-1]

    price = float(last["close"])
    lo, hi = c["price_range_usd"]
    if not (lo <= price <= hi):
        return None

    avg_vol = float(df["volume"].tail(20).mean())
    if avg_vol < c["min_avg_daily_volume"]:
        return None

    atr_pct = float(last.get("atr_pct_14", 0))
    if atr_pct < c["min_atr_pct_14d"]:
        return None

    # RSI14 filter — skipped for MOM_CONT candidates (same reason as India screener).
    vol_ratio = float(last.get("vol_ratio_20", 1.0))
    us_mom_cont_rules = US_STRATEGY_ASSIGNMENT_RULES["MOM_CONT"]
    is_mom_cont_candidate = (
        atr_pct >= us_mom_cont_rules["atr_min"]
        and vol_ratio >= us_mom_cont_rules["volume_ratio_min"]
    )
    if not is_mom_cont_candidate:
        rsi14 = float(last.get("rsi_14", 50))
        rsi_lo, rsi_hi = c["rsi14_range"]
        if not (rsi_lo <= rsi14 <= rsi_hi):
            return None
    else:
        rsi14 = float(last.get("rsi_14", 50))

    # Earnings blackout filter — skip if earnings within the configured window
    no_earnings_days = c.get("no_earnings_within_days")
    if no_earnings_days and _has_earnings_soon(symbol, no_earnings_days):
        logger.debug(f"US screener skipped {symbol}: earnings within {no_earnings_days} days")
        return None
    adx = float(last.get("adx_14")) if last.get("adx_14") is not None else None

    closes = df["close"].tolist()
    symbol_returns = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
    beta = _compute_beta_vs_spy(symbol_returns, spy_returns)

    strategy_id = _assign_strategy(
        atr_pct=atr_pct, beta=beta, vol_ratio=vol_ratio, adx=adx,
        rules=US_STRATEGY_ASSIGNMENT_RULES,
    )

    signal = STRATEGY_REGISTRY[strategy_id]().generate_signal(symbol, df)

    return {
        "symbol": symbol,
        "price": round(price, 2),
        "atr_pct": round(atr_pct, 2),
        "vol_ratio": round(vol_ratio, 2),
        "avg_volume": int(avg_vol),
        "rsi14": round(rsi14, 1),
        "beta": round(beta, 2),
        "adx": round(adx, 1) if adx is not None else None,
        "assigned_strategy": strategy_id,
        "has_live_signal": signal is not None,
        "target_price": round(signal["target_price"], 2) if signal else None,
        "score": 0.0,
    }


def _assign_strategy(
    atr_pct: float,
    beta: float,
    vol_ratio: float,
    adx: float | None = None,
    rules: dict = STRATEGY_ASSIGNMENT_RULES,
) -> str:
    # Priority cascade: most specific/extreme conditions first, RSI2_OVN is the catch-all.
    if (atr_pct >= rules["MOM_CONT"]["atr_min"]
            and vol_ratio >= rules["MOM_CONT"]["volume_ratio_min"]):
        return "MOM_CONT"

    if (atr_pct >= rules["ORB_BRK"]["atr_min"]
            and beta >= rules["ORB_BRK"]["beta_min"]):
        return "ORB_BRK"

    if (adx is not None and adx >= rules["SUPERTREND"]["adx_min"]
            and atr_pct >= rules["SUPERTREND"]["atr_min"]):
        return "SUPERTREND"

    if (adx is not None and adx >= rules["TREND_EMA"]["adx_min"]
            and atr_pct <= rules["TREND_EMA"]["atr_max"]):
        return "TREND_EMA"

    if (adx is not None and rules["DONCHIAN_BRK"]["adx_min"] <= adx < rules["DONCHIAN_BRK"]["adx_max"]):
        return "DONCHIAN_BRK"

    if (adx is not None and adx <= rules["BB_MEANREV"]["adx_max"]
            and atr_pct >= rules["BB_MEANREV"]["atr_min"]):
        return "BB_MEANREV"

    return "RSI2_OVN"
