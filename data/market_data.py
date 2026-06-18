"""
OHLCV data fetching for India (yfinance NSE suffix) and US (yfinance).
Kite Connect intraday will be wired in Phase 6 when live Zerodha creds exist.
"""
import pandas as pd
import yfinance as yf
from loguru import logger


# --------------------------------------------------------------------------- #
# India — NSE via yfinance (.NS suffix)                                        #
# --------------------------------------------------------------------------- #

def fetch_india_daily(symbol: str, period: str = "1y") -> pd.DataFrame:
    """
    Fetch daily OHLCV for an NSE symbol.
    symbol: bare NSE ticker, e.g. "RELIANCE" (we append .NS automatically)
    period: yfinance period string — "1mo", "3mo", "6mo", "1y", "2y"
    """
    ticker = f"{symbol}.NS"
    df = yf.download(ticker, period=period, interval="1d",
                     auto_adjust=True, progress=False)
    if df.empty:
        logger.warning(f"No data returned for {ticker}")
        return pd.DataFrame()

    df = _normalise_columns(df)
    df["symbol"] = symbol
    logger.debug(f"Fetched {len(df)} daily bars for {symbol}")
    return df


def fetch_india_intraday(symbol: str, interval: str = "15m",
                         period: str = "5d") -> pd.DataFrame:
    """
    Fetch intraday OHLCV for an NSE symbol.
    interval: "1m", "5m", "15m", "30m", "60m"
    period: max 60 days for intraday via yfinance
    """
    ticker = f"{symbol}.NS"
    df = yf.download(ticker, period=period, interval=interval,
                     auto_adjust=True, progress=False)
    if df.empty:
        logger.warning(f"No intraday data for {ticker}")
        return pd.DataFrame()

    df = _normalise_columns(df)
    df["symbol"] = symbol
    return df


# --------------------------------------------------------------------------- #
# US — NYSE / NASDAQ via yfinance                                              #
# --------------------------------------------------------------------------- #

def fetch_us_daily(symbol: str, period: str = "1y") -> pd.DataFrame:
    df = yf.download(symbol, period=period, interval="1d",
                     auto_adjust=True, progress=False)
    if df.empty:
        logger.warning(f"No data returned for {symbol}")
        return pd.DataFrame()

    df = _normalise_columns(df)
    df["symbol"] = symbol
    logger.debug(f"Fetched {len(df)} daily bars for {symbol}")
    return df


def fetch_us_intraday(symbol: str, interval: str = "15m",
                      period: str = "5d") -> pd.DataFrame:
    df = yf.download(symbol, period=period, interval=interval,
                     auto_adjust=True, progress=False)
    if df.empty:
        logger.warning(f"No intraday data for {symbol}")
        return pd.DataFrame()

    df = _normalise_columns(df)
    df["symbol"] = symbol
    return df


# --------------------------------------------------------------------------- #
# Batch helpers                                                                 #
# --------------------------------------------------------------------------- #

def fetch_india_batch_daily(symbols: list[str],
                             period: str = "1y") -> dict[str, pd.DataFrame]:
    """Fetch daily data for a list of NSE symbols. Returns {symbol: df}."""
    result = {}
    for sym in symbols:
        df = fetch_india_daily(sym, period=period)
        if not df.empty:
            result[sym] = df
    return result


# --------------------------------------------------------------------------- #
# Internal helpers                                                              #
# --------------------------------------------------------------------------- #

def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase column names and drop timezone from index."""
    df.columns = [c.lower() if isinstance(c, str) else c[0].lower()
                  for c in df.columns]
    if hasattr(df.index, "tz") and df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    return df
