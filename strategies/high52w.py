"""
52-Week High Momentum (HIGH_52W)
---------------------------------
Systematic version of the classic breakout play: buy when a stock closes
at a new 52-week high on above-average volume, with ADX confirming the
underlying trend is real and RSI14 not yet overbought.

The academic basis is strong — Jegadeesh & Titman (1993) momentum, and
George & Hwang (2004) specifically show 52-week-high proximity predicts
future returns because investors use it as an anchor; when the stock
finally breaks through, anchoring-pinned sellers are exhausted and the
stock re-rates quickly.

Entry:  close > donchian_upper_252 (new 52-week closing high, shifted
        so today's own high isn't part of the channel — fresh break only)
        + volume ≥ 1.5× 20-day average (confirms institutional participation)
        + RSI14 < 70 (not already overbought at the break)
        + ADX ≥ 20 (genuine trend, not a sideways chopfest).
Stop:   2× ATR below entry.
Target: 5× ATR — breakouts can run, but stop is closer than DONCHIAN_BRK
        so the 5× target still delivers >2:1 R:R.
Exit:   stop, target, 30-bar Donchian low trail (structure), or 40-day cap.
"""
import pandas as pd
from loguru import logger

from strategies.base import BaseStrategy

DEFAULT_PARAMS = {
    "lookback_bars": 252,       # trading days in a year
    "volume_ratio_min": 1.5,
    "rsi14_max": 70,
    "adx_min": 20,
    "adx_period": 14,
    "atr_period": 14,
    "atr_stop_multiplier": 2.0,
    "atr_target_multiplier": 5.0,
    "trailing_lookback": 20,    # bar low used as trailing stop after entry
    "max_hold_days": 40,
}


class High52WStrategy(BaseStrategy):
    strategy_id = "HIGH_52W"
    name = "52-week high momentum"

    def __init__(self, params: dict | None = None, market: str = "INDIA"):
        merged = {**DEFAULT_PARAMS, **(params or {})}
        super().__init__(merged, market)
        self.strategy_id = "HIGH_52W"
        self.name = "52-week high momentum"

    def generate_signal(self, symbol: str, df: pd.DataFrame) -> dict | None:
        lookback = self.params["lookback_bars"]
        if df is None or len(df) < lookback + 2:
            return None

        last = df.iloc[-1]
        close = self._get(last, "close")
        high_252 = self._get(last, f"donchian_upper_{lookback}")
        vol_ratio = self._get(last, "vol_ratio_20")
        rsi14 = self._get(last, "rsi_14")
        atr = self._get(last, f"atr_{self.params['atr_period']}")
        adx = self._get(last, f"adx_{self.params['adx_period']}")

        if any(v is None for v in [close, high_252, atr]):
            return None

        # New 52-week closing high
        if close <= high_252:
            return None

        # Volume confirmation
        if vol_ratio is not None and vol_ratio < self.params["volume_ratio_min"]:
            logger.debug(f"{symbol}: 52W break but vol_ratio={vol_ratio:.2f} < min — skipping")
            return None

        # RSI gate — don't chase already-overbought breakouts
        if rsi14 is not None and rsi14 >= self.params["rsi14_max"]:
            logger.debug(f"{symbol}: 52W break but RSI14={rsi14:.1f} overbought — skipping")
            return None

        # ADX filter
        if adx is not None and adx < self.params["adx_min"]:
            logger.debug(f"{symbol}: 52W break but ADX={adx:.1f} too weak — skipping")
            return None

        entry_price = float(close)
        risk = self.params["atr_stop_multiplier"] * float(atr)
        stop_price = round(entry_price - risk, 4)
        target_price = round(entry_price + self.params["atr_target_multiplier"] * float(atr), 4)
        planned_rr = round((target_price - entry_price) / risk, 2) if risk > 0 else None

        vol_str = f"{vol_ratio:.2f}" if vol_ratio is not None else "n/a"
        rsi_str = f"{rsi14:.1f}" if rsi14 is not None else "n/a"
        adx_str = f"{adx:.1f}" if adx is not None else "n/a"
        reason = (
            f"New 52W high: close={entry_price:.2f} > prev_high={high_252:.2f}, "
            f"vol_ratio={vol_str}, RSI14={rsi_str}, ADX={adx_str}"
        )
        logger.info(f"[HIGH_52W] BUY signal: {symbol} | {reason}")

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
                "high_252": round(float(high_252), 2),
                "vol_ratio": round(float(vol_ratio), 2) if vol_ratio is not None else None,
                "rsi14": round(float(rsi14), 1) if rsi14 is not None else None,
                "adx": round(float(adx), 1) if adx is not None else None,
                "atr": round(float(atr), 2),
                "close": round(entry_price, 2),
            },
        }

    def should_exit(self, trade: dict, current_bar: dict) -> tuple[bool, str]:
        current_price = float(current_bar.get("close", trade["entry_price"]))

        stop_price = trade.get("stop_loss_price")
        if stop_price and current_price <= float(stop_price):
            return True, "STOP"

        target_price = trade.get("target_price")
        if target_price and current_price >= float(target_price):
            return True, "TARGET"

        # Trailing structure stop: 20-bar low (signals trend exhaustion / pullback)
        donchian_low = current_bar.get(f"donchian_lower_{self.params['trailing_lookback']}")
        if donchian_low is not None and current_price <= float(donchian_low):
            return True, "TRAIL_STOP"

        hold_days = trade.get("hold_days", 0)
        if self.params["max_hold_days"] and hold_days >= self.params["max_hold_days"]:
            return True, "TIME_STOP"

        return False, ""
