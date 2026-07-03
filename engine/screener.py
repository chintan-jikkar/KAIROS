"""
Daily pre-market screener — runs every trading day before the session opens.
Filters the master pool against screener criteria, assigns strategies via the
ADX/ATR/beta cascade, and ranks survivors using a 4-factor alpha composite:

  Composite = 0.35×MOM_6M + 0.20×MOM_1M + 0.25×LOW_VOL + 0.20×VOL_TREND

All factors are cross-sectionally Z-scored (clipped ±2σ) before weighting, so
no factor dominates by scale. The composite is then re-scaled 0–100 for display.

Fetch period upgraded to 1Y (was 3mo): needed for the 6M momentum factor and for
EMA200/SMA200 indicators to be meaningful.
"""
import datetime
import math

import pandas as pd
import yfinance as yf
from loguru import logger

from data.market_data import fetch_india_daily, fetch_us_daily
from data.indicators import add_all_strategy_indicators, add_atr_pct, add_volume_ratio
from data.universe import (
    get_india_all_symbols,
    get_us_all_symbols,
    get_fx_all_symbols,
    INDIA_SCREEN_CRITERIA,
    US_SCREEN_CRITERIA,
    FX_SCREEN_CRITERIA,
    STRATEGY_ASSIGNMENT_RULES,
    US_STRATEGY_ASSIGNMENT_RULES,
    FX_STRATEGY_ASSIGNMENT_RULES,
    FX_DISPLAY_NAMES,
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
    nifty_df = fetch_us_daily("^NSEI", period="1y")
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

    results = _apply_factor_composite(results)
    df = pd.DataFrame(results)
    df = df.sort_values("composite_score", ascending=False)
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
    spy_df = fetch_us_daily("SPY", period="1y")
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

    results = _apply_factor_composite(results)
    df = pd.DataFrame(results)
    df = df.sort_values("composite_score", ascending=False)
    if top_n is not None:
        df = df.head(top_n)

    ranked = df.to_dict(orient="records")
    logger.info(f"US screener selected {len(ranked)} stocks: {[r['symbol'] for r in ranked]}")
    return ranked


def run_fx_screener(top_n: int | None = None) -> list[dict]:
    """Rank FX pairs by 4-factor alpha composite.
    top_n defaults to None (return all qualifying pairs) — the FX universe is small
    (8 pairs) so there is no reason to cut it down for display purposes.
    Beta is computed vs DXY (US Dollar Index), representing the dollar's directional pull.
    """
    dxy_df = fetch_us_daily("DX-Y.NYB", period="1y")
    if not dxy_df.empty and len(dxy_df) >= 2:
        dxy_closes = dxy_df["close"].tolist()
        dxy_returns = [
            (dxy_closes[i] - dxy_closes[i - 1]) / dxy_closes[i - 1]
            for i in range(1, len(dxy_closes))
        ]
    else:
        logger.warning("Could not fetch DXY data — FX beta will default to 1.0")
        dxy_returns = []

    symbols = get_fx_all_symbols()
    results = []

    for symbol in symbols:
        try:
            record = _evaluate_symbol_fx(symbol, dxy_returns)
            if record:
                results.append(record)
        except Exception as exc:
            logger.warning(f"FX screener skipped {symbol}: {exc}")

    if not results:
        logger.warning("FX screener returned 0 qualifying pairs")
        return []

    results = _apply_factor_composite(results)
    df = pd.DataFrame(results)
    df = df.sort_values("composite_score", ascending=False)
    if top_n is not None:
        df = df.head(top_n)

    ranked = df.to_dict(orient="records")
    logger.info(f"FX screener ranked {len(ranked)} pairs: {[r['symbol'] for r in ranked]}")
    return ranked


def _evaluate_symbol_fx(symbol: str, dxy_returns: list[float]) -> dict | None:
    c = FX_SCREEN_CRITERIA

    df = fetch_us_daily(symbol, period="1y")   # yfinance accepts FX tickers directly (EURUSD=X)
    if df.empty or len(df) < 60:
        return None

    df = add_all_strategy_indicators(df)
    last = df.iloc[-1]

    price = float(last["close"])

    atr_pct = float(last.get("atr_pct_14", 0))
    if atr_pct < c["min_atr_pct_14d"]:
        return None

    rsi14 = float(last.get("rsi_14", 50))
    rsi_lo, rsi_hi = c["rsi14_range"]
    if not (rsi_lo <= rsi14 <= rsi_hi):
        return None

    adx = float(last.get("adx_14")) if last.get("adx_14") is not None else None
    vol_ratio = float(last.get("vol_ratio_20", 1.0))
    avg_vol = float(df["volume"].tail(20).mean())

    closes = df["close"].tolist()
    symbol_returns = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
    beta = _compute_beta_vs_spy(symbol_returns, dxy_returns) if dxy_returns else 1.0

    strategy_id = _assign_strategy(
        atr_pct=atr_pct, beta=beta, vol_ratio=vol_ratio, adx=adx,
        rules=FX_STRATEGY_ASSIGNMENT_RULES,
    )
    signal = STRATEGY_REGISTRY[strategy_id]().generate_signal(symbol, df)

    factor_inputs = _compute_factor_inputs(closes)

    return {
        "symbol": symbol,
        "display_name": FX_DISPLAY_NAMES.get(symbol, symbol),
        "price": round(price, 5),
        "atr_pct": round(atr_pct, 3),
        "vol_ratio": round(vol_ratio, 2),
        "avg_volume": int(avg_vol),
        "rsi14": round(rsi14, 1),
        "beta": round(beta, 2),
        "adx": round(adx, 1) if adx is not None else None,
        "assigned_strategy": strategy_id,
        "has_live_signal": signal is not None,
        "target_price": round(signal["target_price"], 5) if signal else None,
        "score": 0.0,
        "composite_score": 0.0,
        **factor_inputs,
    }


def _evaluate_symbol(symbol: str, nifty_returns: list[float] | None = None) -> dict | None:
    c = INDIA_SCREEN_CRITERIA

    df = fetch_india_daily(symbol, period="1y")
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
    signal = STRATEGY_REGISTRY[strategy_id]().generate_signal(symbol, df)

    factor_inputs = _compute_factor_inputs(closes)

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
        "score": 0.0,         # back-filled by _apply_factor_composite
        "composite_score": 0.0,
        **factor_inputs,
    }


def _evaluate_symbol_us(symbol: str, spy_returns: list[float]) -> dict | None:
    c = US_SCREEN_CRITERIA

    df = fetch_us_daily(symbol, period="1y")
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

    factor_inputs = _compute_factor_inputs(closes)

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
        "composite_score": 0.0,
        **factor_inputs,
    }


def _compute_factor_inputs(closes: list[float]) -> dict:
    """Compute raw factor values for a single stock from its close price series.
    All values are raw — cross-sectional Z-scoring happens in _apply_factor_composite.
    """
    n = len(closes)

    # MOM_6M: 6-month return excluding the most recent month (skip-month momentum).
    # 6M = ~127 bars back, +21 bars skip = compare close[-1] to close[-148] if available.
    if n >= 148:
        mom_6m = closes[-1] / closes[-148] - 1
    elif n >= 63:
        mom_6m = closes[-1] / closes[-63] - 1  # 3M fallback
    else:
        mom_6m = closes[-1] / closes[0] - 1

    # MOM_1M: 21-trading-day return.
    mom_1m = closes[-1] / closes[-21] - 1 if n >= 21 else closes[-1] / closes[0] - 1

    # LOW_VOL: Realized annualized volatility from the last 20 log-returns.
    # Will be inverted (negated) during Z-scoring — lower vol → higher alpha score.
    if n >= 21:
        log_rets = [math.log(closes[i] / closes[i - 1]) for i in range(n - 20, n)]
        mean_r = sum(log_rets) / len(log_rets)
        var_r = sum((r - mean_r) ** 2 for r in log_rets) / (len(log_rets) - 1)
        realized_vol_20 = round(math.sqrt(var_r) * math.sqrt(252), 6)
    else:
        realized_vol_20 = 0.25  # neutral fallback (≈25% annualized vol)

    return {
        "mom_6m": round(mom_6m, 6),
        "mom_1m": round(mom_1m, 6),
        "realized_vol_20": realized_vol_20,
    }


# Factor weights — IB quant composite (Jegadeesh-Titman momentum core + vol + flow).
_FACTOR_WEIGHTS = {
    "mom_6m":       0.35,   # medium-term momentum — highest conviction factor
    "mom_1m":       0.20,   # short-term momentum — fast confirmation
    "low_vol":      0.25,   # low-volatility anomaly — risk-adjusted return enhancer
    "vol_trend":    0.20,   # volume trend / institutional flow proxy
}


def _apply_factor_composite(records: list[dict]) -> list[dict]:
    """Cross-sectional factor scoring across all qualifying stocks.

    Each raw factor is converted to a Z-score across the pool, winsorized at ±2σ,
    then weighted and summed. The composite is re-scaled to 0–100 for display.
    The 'score' field is also set to composite_score for backwards compatibility
    with dashboard code that reads 'score'.
    """
    if not records:
        return records

    if len(records) == 1:
        records[0]["composite_score"] = 50.0
        records[0]["score"] = 50.0
        for key in ("factor_mom_6m", "factor_mom_1m", "factor_low_vol", "factor_vol_trend"):
            records[0][key] = 0.0
        return records

    def _zscore_col(values: list[float]) -> list[float]:
        n = len(values)
        mu = sum(values) / n
        var = sum((v - mu) ** 2 for v in values) / max(n - 1, 1)
        sigma = math.sqrt(var) if var > 0 else 1.0
        return [max(-2.0, min(2.0, (v - mu) / sigma)) for v in values]

    mom_6m_z   = _zscore_col([r["mom_6m"] for r in records])
    mom_1m_z   = _zscore_col([r["mom_1m"] for r in records])
    # LOW_VOL: invert so lower volatility = higher Z-score
    low_vol_z  = _zscore_col([-r["realized_vol_20"] for r in records])
    vol_trend_z = _zscore_col([r["vol_ratio"] for r in records])

    w = _FACTOR_WEIGHTS
    composites = [
        w["mom_6m"] * mom_6m_z[i]
        + w["mom_1m"] * mom_1m_z[i]
        + w["low_vol"] * low_vol_z[i]
        + w["vol_trend"] * vol_trend_z[i]
        for i in range(len(records))
    ]

    c_min, c_max = min(composites), max(composites)
    c_range = c_max - c_min if c_max > c_min else 1.0

    for i, rec in enumerate(records):
        rec["factor_mom_6m"]    = round(mom_6m_z[i], 3)
        rec["factor_mom_1m"]    = round(mom_1m_z[i], 3)
        rec["factor_low_vol"]   = round(low_vol_z[i], 3)
        rec["factor_vol_trend"] = round(vol_trend_z[i], 3)
        scaled = round((composites[i] - c_min) / c_range * 100, 1)
        rec["composite_score"] = scaled
        rec["score"] = scaled   # backwards-compat alias

    return records


def _assign_strategy(
    atr_pct: float,
    beta: float,
    vol_ratio: float,
    adx: float | None = None,
    rules: dict = STRATEGY_ASSIGNMENT_RULES,
) -> str:
    # Priority cascade: most specific/extreme conditions first, RSI2_OVN is the catch-all.
    # MOM_CONT, GAP_GO, and ORB_BRK are guarded because FX rules omit these keys
    # (all three require a single exchange-open event that FX doesn't have).
    if ("MOM_CONT" in rules
            and atr_pct >= rules["MOM_CONT"]["atr_min"]
            and vol_ratio >= rules["MOM_CONT"]["volume_ratio_min"]):
        return "MOM_CONT"

    if ("GAP_GO" in rules
            and atr_pct >= rules["GAP_GO"]["atr_min"]
            and beta >= rules["GAP_GO"]["beta_min"]):
        return "GAP_GO"

    if ("ORB_BRK" in rules
            and atr_pct >= rules["ORB_BRK"]["atr_min"]
            and beta >= rules["ORB_BRK"]["beta_min"]):
        return "ORB_BRK"

    if (adx is not None and adx >= rules["SUPERTREND"]["adx_min"]
            and atr_pct >= rules["SUPERTREND"]["atr_min"]):
        return "SUPERTREND"

    if (adx is not None and adx >= rules["TREND_EMA"]["adx_min"]
            and atr_pct <= rules["TREND_EMA"]["atr_max"]):
        return "TREND_EMA"

    if (adx is not None and "DUAL_EMA" in rules
            and rules["DUAL_EMA"]["adx_min"] <= adx < rules["DUAL_EMA"]["adx_max"]):
        return "DUAL_EMA"

    if (adx is not None and rules["DONCHIAN_BRK"]["adx_min"] <= adx < rules["DONCHIAN_BRK"]["adx_max"]):
        return "DONCHIAN_BRK"

    if (adx is not None and "HIGH_52W" in rules
            and rules["HIGH_52W"]["adx_min"] <= adx < rules["HIGH_52W"]["adx_max"]
            and vol_ratio >= rules["HIGH_52W"].get("volume_ratio_min", 0)):
        return "HIGH_52W"

    if (adx is not None and "MACD_CROSS" in rules
            and rules["MACD_CROSS"]["adx_min"] <= adx < rules["MACD_CROSS"]["adx_max"]):
        return "MACD_CROSS"

    if (adx is not None and adx <= rules["BB_MEANREV"]["adx_max"]
            and atr_pct >= rules["BB_MEANREV"]["atr_min"]):
        return "BB_MEANREV"

    return "RSI2_OVN"
