"""
Trend Following — 50/200 EMA Cross (TREND_EMA)
-------------------------------------------------
Classic golden-cross / death-cross trend following, adapted from a commodity
4-hour-candle approach to NSE daily bars (yfinance doesn't reliably provide
4h NSE candles; daily 50/200 EMA cross is the more proven equity-market form
of this same idea — same logic Richard Dennis-style trend systems use).

Entry:  EMA(50) crosses above EMA(200) (golden cross), with an ADX filter to
        skip the cross when there's no real trend behind it (raw EMA-cross
        systems are known to whipsaw badly in sideways markets).
Exit:   EMA(50) crosses below EMA(200) (death cross), or a fixed ATR-based
        stop set at entry. No EOD timer — this is a multi-day/multi-week
        hold by design, unlike KAIROS's other strategies.

Best suited to low-ATR, low-beta, cleanly-trending names — the opposite end
of the spectrum from MOM_CONT/ORB_BRK. Long-only, matching every other
KAIROS strategy (no short-side trading implemented anywhere yet).
"""
import pandas as pd
from loguru import logger

from strategies.base import BaseStrategy

DEFAULT_PARAMS = {
    "fast_ema_period": 50,
    "slow_ema_period": 200,
    "adx_period": 14,
    "min_adx_for_entry": 22,        # below this, treat the cross as noise
    "atr_period": 14,
    "atr_stop_multiplier": 3.0,     # fixed stop = entry - 3x ATR
    "atr_target_multiplier": 6.0,   # nominal 2:1 R:R for logging purposes
}


class TrendEMAStrategy(BaseStrategy):
    strategy_id = "TREND_EMA"
    name = "Trend Following (50/200 EMA Cross)"

    def __init__(self, params: dict | None = None, market: str = "INDIA"):
        merged = {**DEFAULT_PARAMS, **(params or {})}
        super().__init__(merged, market)

    def generate_signal(self, symbol: str, df: pd.DataFrame) -> dict | None:
        fast_col = f"ema_{self.params['fast_ema_period']}"
        slow_col = f"ema_{self.params['slow_ema_period']}"
        adx_col = f"adx_{self.params['adx_period']}"
        atr_col = f"atr_{self.params['atr_period']}"

        if df is None or len(df) < self.params["slow_ema_period"] + 2:
            return None

        last, prev = df.iloc[-1], df.iloc[-2]
        fast_now, slow_now = self._get(last, fast_col), self._get(last, slow_col)
        fast_prev, slow_prev = self._get(prev, fast_col), self._get(prev, slow_col)
        adx = self._get(last, adx_col)
        atr = self._get(last, atr_col)
        close = self._get(last, "close")

        if any(v is None for v in [fast_now, slow_now, fast_prev, slow_prev, close, atr]):
            return None

        golden_cross = fast_prev <= slow_prev and fast_now > slow_now
        if not golden_cross:
            return None

        if adx is not None and adx < self.params["min_adx_for_entry"]:
            logger.debug(f"{symbol}: golden cross but ADX={adx:.1f} too weak — skipping")
            return None

        entry_price = float(close)
        stop_price = round(entry_price - self.params["atr_stop_multiplier"] * atr, 4)
        target_price = round(entry_price + self.params["atr_target_multiplier"] * atr, 4)
        planned_rr = round((target_price - entry_price) / (entry_price - stop_price), 2)

        adx_text = f"{adx:.1f}" if adx is not None else "n/a"
        reason = (
            f"EMA{self.params['fast_ema_period']}={fast_now:.2f} crossed above "
            f"EMA{self.params['slow_ema_period']}={slow_now:.2f} (golden cross), "
            f"ADX={adx_text}, entry at close"
        )
        logger.info(f"[TREND_EMA] BUY signal: {symbol} | {reason}")

        return {
            "action": "BUY",
            "symbol": symbol,
            "strategy_id": self.strategy_id,
            "strategy_name": self.name,
            "entry_price": entry_price,
            "stop_price": stop_price,
            "target_price": target_price,
            "planned_rr_ratio": planned_rr,
            "signal_reason": reason,
            "indicators": {
                "ema_fast": round(float(fast_now), 2),
                "ema_slow": round(float(slow_now), 2),
                "adx": round(float(adx), 2) if adx is not None else None,
                "atr": round(float(atr), 2),
                "close": round(entry_price, 2),
            },
        }

    def should_exit(self, trade: dict, current_bar: dict) -> tuple[bool, str]:
        entry_price = trade["entry_price"]
        current_price = current_bar.get("close", entry_price)
        fast = current_bar.get(f"ema_{self.params['fast_ema_period']}")
        slow = current_bar.get(f"ema_{self.params['slow_ema_period']}")

        # 1. Death cross
        if fast is not None and slow is not None and fast < slow:
            return True, "TREND_REVERSAL"

        # 2. Fixed ATR stop set at entry
        stop_price = trade.get("stop_loss_price")
        if stop_price and current_price <= stop_price:
            return True, "STOP"

        return False, ""
