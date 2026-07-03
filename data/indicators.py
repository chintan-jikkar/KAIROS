"""
Technical indicators — thin pandas-ta wrappers with KAIROS naming conventions.
All functions accept a OHLCV DataFrame and return the same DataFrame with new columns appended.
Column naming: {INDICATOR}_{PERIOD}  e.g. rsi_2, sma_200, atr_14
"""
import pandas as pd
import pandas_ta as ta


# --------------------------------------------------------------------------- #
# Trend                                                                         #
# --------------------------------------------------------------------------- #

def add_sma(df: pd.DataFrame, periods: list[int] = [20, 50, 200]) -> pd.DataFrame:
    for p in periods:
        df[f"sma_{p}"] = ta.sma(df["close"], length=p)
    return df


def add_ema(df: pd.DataFrame, periods: list[int] = [9, 20, 50]) -> pd.DataFrame:
    for p in periods:
        df[f"ema_{p}"] = ta.ema(df["close"], length=p)
    return df


def add_vwap(df: pd.DataFrame) -> pd.DataFrame:
    # pandas-ta vwap requires high/low/close/volume and a datetime index
    df["vwap"] = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
    return df


def add_macd(df: pd.DataFrame,
             fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    macd = ta.macd(df["close"], fast=fast, slow=slow, signal=signal)
    if macd is not None:
        df["macd"] = macd[f"MACD_{fast}_{slow}_{signal}"]
        df["macd_signal"] = macd[f"MACDs_{fast}_{slow}_{signal}"]
        df["macd_hist"] = macd[f"MACDh_{fast}_{slow}_{signal}"]
    return df


def add_supertrend(df: pd.DataFrame,
                   period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    st = ta.supertrend(df["high"], df["low"], df["close"],
                       length=period, multiplier=multiplier)
    if st is not None:
        col = f"SUPERT_{period}_{multiplier}"
        dir_col = f"SUPERTd_{period}_{multiplier}"
        df["supertrend"] = st[col] if col in st.columns else st.iloc[:, 0]
        df["supertrend_direction"] = st[dir_col] if dir_col in st.columns else None
    return df


def add_adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    adx = ta.adx(df["high"], df["low"], df["close"], length=period)
    if adx is not None:
        df[f"adx_{period}"] = adx[f"ADX_{period}"]
    return df


# --------------------------------------------------------------------------- #
# Momentum                                                                      #
# --------------------------------------------------------------------------- #

def add_rsi(df: pd.DataFrame, periods: list[int] = [2, 14]) -> pd.DataFrame:
    for p in periods:
        df[f"rsi_{p}"] = ta.rsi(df["close"], length=p)
    return df


def add_stoch(df: pd.DataFrame, k: int = 14, d: int = 3) -> pd.DataFrame:
    stoch = ta.stoch(df["high"], df["low"], df["close"], k=k, d=d)
    if stoch is not None:
        df["stoch_k"] = stoch[f"STOCHk_{k}_{d}_{d}"]
        df["stoch_d"] = stoch[f"STOCHd_{k}_{d}_{d}"]
    return df


def add_cci(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    df[f"cci_{period}"] = ta.cci(df["high"], df["low"], df["close"], length=period)
    return df


def add_roc(df: pd.DataFrame, period: int = 10) -> pd.DataFrame:
    df[f"roc_{period}"] = ta.roc(df["close"], length=period)
    return df


def add_mfi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    df[f"mfi_{period}"] = ta.mfi(df["high"], df["low"], df["close"],
                                   df["volume"], length=period)
    return df


# --------------------------------------------------------------------------- #
# Volatility                                                                    #
# --------------------------------------------------------------------------- #

def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    df[f"atr_{period}"] = ta.atr(df["high"], df["low"], df["close"], length=period)
    return df


def add_atr_pct(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """ATR as percentage of close — used for screener criteria."""
    add_atr(df, period)
    df[f"atr_pct_{period}"] = (df[f"atr_{period}"] / df["close"]) * 100
    return df


def add_bbands(df: pd.DataFrame,
               period: int = 20, std: float = 2.0) -> pd.DataFrame:
    bb = ta.bbands(df["close"], length=period, lower_std=std, upper_std=std)
    if bb is not None:
        df["bb_upper"] = bb[f"BBU_{period}_{std}_{std}"]
        df["bb_mid"] = bb[f"BBM_{period}_{std}_{std}"]
        df["bb_lower"] = bb[f"BBL_{period}_{std}_{std}"]
        df["bb_width"] = bb[f"BBB_{period}_{std}_{std}"]
    return df


def add_donchian(df: pd.DataFrame, periods: list[int] = [10, 20]) -> pd.DataFrame:
    """Rolling channel high/low, shifted by 1 bar so today's own high/low isn't
    part of the channel it's compared against — needed for breakout detection
    (today broke yesterday's channel) and as a trailing-stop level."""
    for p in periods:
        df[f"donchian_upper_{p}"] = df["high"].shift(1).rolling(window=p).max()
        df[f"donchian_lower_{p}"] = df["low"].shift(1).rolling(window=p).min()
    return df


def add_keltner(df: pd.DataFrame,
                period: int = 20, multiplier: float = 2.0) -> pd.DataFrame:
    kc = ta.kc(df["high"], df["low"], df["close"],
                length=period, scalar=multiplier)
    if kc is not None:
        df["kc_upper"] = kc[f"KCUe_{period}_{multiplier}"]
        df["kc_lower"] = kc[f"KCLe_{period}_{multiplier}"]
    return df


# --------------------------------------------------------------------------- #
# Volume                                                                        #
# --------------------------------------------------------------------------- #

def add_obv(df: pd.DataFrame) -> pd.DataFrame:
    df["obv"] = ta.obv(df["close"], df["volume"])
    return df


def add_cmf(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    df[f"cmf_{period}"] = ta.cmf(df["high"], df["low"], df["close"],
                                   df["volume"], length=period)
    return df


def add_volume_sma(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    df[f"vol_sma_{period}"] = ta.sma(df["volume"], length=period)
    return df


def add_volume_ratio(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """Volume / MA(volume, period) — relative volume, used in multiple strategies."""
    add_volume_sma(df, period)
    df[f"vol_ratio_{period}"] = df["volume"] / df[f"vol_sma_{period}"]
    return df


# --------------------------------------------------------------------------- #
# Convenience — add all indicators needed by the strategies in one call        #
# --------------------------------------------------------------------------- #

def add_all_strategy_indicators(df: pd.DataFrame) -> pd.DataFrame:
    add_sma(df, [20, 50, 200])
    add_ema(df, [9, 20, 50, 200])
    add_rsi(df, [2, 14])
    add_atr(df, 14)
    add_atr_pct(df, 14)
    add_macd(df)
    add_bbands(df)
    add_volume_ratio(df, 20)
    add_obv(df)
    add_adx(df)
    add_donchian(df, [10, 20, 252])
    add_supertrend(df)
    return df
