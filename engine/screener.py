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

    # Beta is not available via yfinance easily — approximate from 90-day correlation with NIFTY
    # For now default to 1.0; will be populated when live Kite data is available
    beta = 1.0

    strategy = _assign_strategy(atr_pct=atr_pct, beta=beta, vol_ratio=vol_ratio)

    return {
        "symbol": symbol,
        "price": round(price, 2),
        "atr_pct": round(atr_pct, 2),
        "vol_ratio": round(vol_ratio, 2),
        "avg_volume": int(avg_vol),
        "rsi14": round(rsi14, 1),
        "beta": beta,
        "assigned_strategy": strategy,
        "score": 0.0,  # filled by caller after normalisation
    }


def _assign_strategy(atr_pct: float, beta: float, vol_ratio: float) -> str:
    rules = STRATEGY_ASSIGNMENT_RULES

    # Priority: highest ATR gets MOM_CONT, then ORB_BRK, else RSI2_OVN
    if (atr_pct >= rules["MOM_CONT"]["atr_min"]
            and vol_ratio >= rules["MOM_CONT"]["volume_ratio_min"]):
        return "MOM_CONT"

    if (atr_pct >= rules["ORB_BRK"]["atr_min"]
            and beta >= rules["ORB_BRK"]["beta_min"]):
        return "ORB_BRK"

    return "RSI2_OVN"
