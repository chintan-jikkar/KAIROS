"""
Dual EMA Crossover (DUAL_EMA)
------------------------------
Faster trend-entry cousin of TREND_EMA's 50/200 golden cross.
Uses the 9/20 EMA pair to catch trends 4-6 weeks earlier, in the
ADX 20-27 regime where the 50/200 cross hasn't fired yet but a
shorter-term trend is already established.

TREND_EMA fires 1-2× per year per stock; DUAL_EMA fires 6-8× — it
fills the calendar gaps where there's a valid setup but no golden cross.
Complementary: if TREND_EMA is assigned (ADX≥25, ATR≤2.5), DUAL_EMA
takes the stocks with similar ADX but faster-moving EMA dynamics.

Entry:  EMA(9) crosses above EMA(20) + close > EMA(50) (trend filter)
        + ADX ≥ 18 (need some directional conviction, not just noise).
Stop:   2× ATR below entry (tighter than TREND_EMA's 3×; faster
        strategy means less room for adverse excursions).
Target: 4× ATR — 2:1 R:R.
Exit:   EMA(9) crosses below EMA(20), stop hit, or 35-day time stop.
"""
import pandas as pd
from loguru import logger

from strategies.base import BaseStrategy

DEFAULT_PARAMS = {
    "fast_ema_period": 9,
    "slow_ema_period": 20,
    "trend_ema_period": 50,
    "adx_period": 14,
    "min_adx_for_entry": 18,
    "atr_period": 14,
    "atr_stop_multiplier": 2.0,
    "atr_target_multiplier": 4.0,
    "max_hold_days": 35,
}


class DualEMAStrategy(BaseStrategy):
    strategy_id = "DUAL_EMA"
    name = "Dual EMA crossover (9/20)"

    def __init__(self, params: dict | None = None, market: str = "INDIA"):
        merged = {**DEFAULT_PARAMS, **(params or {})}
        super().__init__(merged, market)
        self.strategy_id = "DUAL_EMA"
        self.name = "Dual EMA crossover (9/20)"

    def generate_signal(self, symbol: str, df: pd.DataFrame) -> dict | None:
        fast_col = f"ema_{self.params['fast_ema_period']}"
        slow_col = f"ema_{self.params['slow_ema_period']}"
        trend_col = f"ema_{self.params['trend_ema_period']}"
        adx_col = f"adx_{self.params['adx_period']}"
        atr_col = f"atr_{self.params['atr_period']}"

        if df is None or len(df) < self.params["slow_ema_period"] + 2:
            return None

        last, prev = df.iloc[-1], df.iloc[-2]
        fast_now = self._get(last, fast_col)
        slow_now = self._get(last, slow_col)
        fast_prev = self._get(prev, fast_col)
        slow_prev = self._get(prev, slow_col)
        trend_ema = self._get(last, trend_col)
        adx = self._get(last, adx_col)
        atr = self._get(last, atr_col)
        close = self._get(last, "close")

        if any(v is None for v in [fast_now, slow_now, fast_prev, slow_prev, close, atr]):
            return None

        # Fresh bullish cross only
        if not (fast_prev <= slow_prev and fast_now > slow_now):
            return None

        # Price must be above intermediate trend (EMA50) — no contra-trend entries
        if trend_ema is not None and close < trend_ema:
            return None

        if adx is not None and adx < self.params["min_adx_for_entry"]:
            logger.debug(f"{symbol}: EMA9/20 cross but ADX={adx:.1f} too weak — skipping")
            return None

        entry_price = float(close)
        risk = self.params["atr_stop_multiplier"] * float(atr)
        stop_price = round(entry_price - risk, 4)
        target_price = round(entry_price + self.params["atr_target_multiplier"] * float(atr), 4)
        planned_rr = round((target_price - entry_price) / risk, 2) if risk > 0 else None

        adx_text = f"{adx:.1f}" if adx is not None else "n/a"
        reason = (
            f"EMA{self.params['fast_ema_period']}={fast_now:.2f} crossed above "
            f"EMA{self.params['slow_ema_period']}={slow_now:.2f}, "
            f"ADX={adx_text}, close={entry_price:.2f} > EMA50"
        )
        logger.info(f"[DUAL_EMA] BUY signal: {symbol} | {reason}")

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
        current_price = float(current_bar.get("close", trade["entry_price"]))
        fast = current_bar.get(f"ema_{self.params['fast_ema_period']}")
        slow = current_bar.get(f"ema_{self.params['slow_ema_period']}")

        # EMA9 crosses back below EMA20 — trend reversal
        if fast is not None and slow is not None and fast < slow:
            return True, "TREND_REVERSAL"

        stop_price = trade.get("stop_loss_price")
        if stop_price and current_price <= float(stop_price):
            return True, "STOP"

        target_price = trade.get("target_price")
        if target_price and current_price >= float(target_price):
            return True, "TARGET"

        hold_days = trade.get("hold_days", 0)
        if self.params["max_hold_days"] and hold_days >= self.params["max_hold_days"]:
            return True, "TIME_STOP"

        return False, ""
