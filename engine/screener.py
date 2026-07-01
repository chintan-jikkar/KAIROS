"""
Weekly stock universe screener — runs every Sunday 20:00 IST.
Filters INDIA_MASTER_POOL against INDIA_SCREEN_CRITERIA and returns top 5-6 stocks
ranked by combined ATR% + volume-ratio score. Auto-assigns best-fit strategy.
"""
import pandas as pd
from loguru import logger

from data.market_data import fetch_india_daily
from data.indicators import add_all_strategy_indicators, add_atr_pct, add_volume_ratio
from data.universe import (
    get_india_all_symbols,
    INDIA_SCREEN_CRITERIA,
    STRATEGY_ASSIGNMENT_RULES,
)
from engine.signals import STRATEGY_REGISTRY


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
    symbols = get_india_all_symbols()
    results = []

    for symbol in symbols:
        try:
            record = _evaluate_symbol(symbol)
            if record:
                results.append(record)
        except Exception as exc:
            logger.warning(f"Screener skipped {symbol}: {exc}")

    if not results:
        logger.warning("Screener returned 0 qualifying stocks")
        return []

    # Rank by composite score: atr_pct (60%) + vol_ratio (40%), both normalised
    df = pd.DataFrame(results)
    df["atr_norm"] = df["atr_pct"] / df["atr_pct"].max()
    df["vol_norm"] = df["vol_ratio"] / df["vol_ratio"].max()
    df["score"] = (df["atr_norm"] * 60 + df["vol_norm"] * 40).round(1)
    df = df.sort_values("score", ascending=False)
    if top_n is not None:
        df = df.head(top_n)

    ranked = df.to_dict(orient="records")
    logger.info(f"Screener selected {len(ranked)} stocks: {[r['symbol'] for r in ranked]}")
    return ranked


def _evaluate_symbol(symbol: str) -> dict | None:
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

    # RSI14 filter
    rsi14 = float(last.get("rsi_14", 50))
    rsi_lo, rsi_hi = c["rsi14_range"]
    if not (rsi_lo <= rsi14 <= rsi_hi):
        return None

    vol_ratio = float(last.get("vol_ratio_20", 1.0))
    adx = float(last.get("adx_14")) if last.get("adx_14") is not None else None

    # Beta is not available via yfinance easily — approximate from 90-day correlation with NIFTY
    # For now default to 1.0; will be populated when live Kite data is available
    beta = 1.0

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


def _assign_strategy(atr_pct: float, beta: float, vol_ratio: float, adx: float | None = None) -> str:
    rules = STRATEGY_ASSIGNMENT_RULES

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
