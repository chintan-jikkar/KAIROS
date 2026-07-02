"""
MACD Crossover (MACD_CROSS)
---------------------------
Gerald Appel's MACD (1970s) — one of the oldest momentum indicators still in
universal use. Standard 12/26/9 EMA crossover; buy when the MACD line crosses
above the signal line with the histogram turning positive, and price is above
SMA50 as a trend filter.

Fits stocks in the 'momentum building' regime (ADX 15–20) — trend is
strengthening but hasn't reached the sustained strength that TREND_EMA or
SUPERTREND need (ADX≥25). MACD fires earlier in the trend than those two and
is complementary rather than redundant.

Entry: fresh MACD bullish crossover (was below signal prev bar, above now)
       + histogram > 0 + close > SMA50.
Stop:  1.5× ATR below entry.  Target: 3:1 R:R.
Exit:  stop, target, MACD histogram crossing negative (MACD_EXIT), or
       30-day time-stop.
"""
import pandas as pd
from loguru import logger

from strategies.base import BaseStrategy

DEFAULT_PARAMS = {
    "atr_period": 14,
    "atr_stop_multiplier": 1.5,
    "risk_reward": 3.0,
    "max_hold_days": 30,
    "trend_filter_sma": 50,
}


class MACDCrossoverStrategy(BaseStrategy):
    strategy_id = "MACD_CROSS"
    name = "MACD momentum crossover"

    def __init__(self, params: dict | None = None, market: str = "INDIA"):
        merged = {**DEFAULT_PARAMS, **(params or {})}
        super().__init__(merged, market)
        # BaseStrategy.__init__ sets self.strategy_id = "" which shadows the class
        # attribute; restore the correct values here.
        self.strategy_id = "MACD_CROSS"
        self.name = "MACD momentum crossover"

    def generate_signal(self, symbol: str, df: pd.DataFrame) -> dict | None:
        if df is None or len(df) < 2:
            return None

        last, prev = df.iloc[-1], df.iloc[-2]

        close = self._get(last, "close")
        atr = self._get(last, f"atr_{self.params['atr_period']}")
        sma_50 = self._get(last, f"sma_{self.params['trend_filter_sma']}")
        macd = self._get(last, "macd")
        macd_signal_val = self._get(last, "macd_signal")
        macd_hist = self._get(last, "macd_hist")
        prev_macd = self._get(prev, "macd")
        prev_macd_signal = self._get(prev, "macd_signal")

        if any(v is None for v in [close, atr, sma_50, macd, macd_signal_val,
                                    macd_hist, prev_macd, prev_macd_signal]):
            return None

        # Trend filter: price must be in an uptrend
        if close <= sma_50:
            return None

        # Fresh bullish crossover only — MACD was at or below signal on prev bar
        if not (prev_macd <= prev_macd_signal and macd > macd_signal_val):
            return None

        # Histogram confirms momentum is now positive
        if macd_hist <= 0:
            return None

        entry_price = float(close)
        risk = self.params["atr_stop_multiplier"] * float(atr)
        stop_price = round(entry_price - risk, 4)
        target_price = round(entry_price + risk * self.params["risk_reward"], 4)
        planned_rr = round((target_price - entry_price) / risk, 2) if risk > 0 else None

        reason = (
            f"MACD({float(macd):.4f}) crossed above signal({float(macd_signal_val):.4f}), "
            f"hist={float(macd_hist):.4f} > 0, close={entry_price:.2f} > SMA50={float(sma_50):.2f}"
        )
        logger.info(f"[MACD_CROSS] BUY signal: {symbol} | {reason}")

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
                "macd": round(float(macd), 4),
                "macd_signal": round(float(macd_signal_val), 4),
                "macd_hist": round(float(macd_hist), 4),
                "sma_50": round(float(sma_50), 2),
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

        # MACD momentum reversal — histogram crossed negative
        macd_hist = current_bar.get("macd_hist")
        try:
            if macd_hist is not None and float(macd_hist) < 0:
                return True, "MACD_EXIT"
        except (TypeError, ValueError):
            pass

        hold_days = trade.get("hold_days", 0)
        max_hold = self.params.get("max_hold_days")
        if max_hold and hold_days >= max_hold:
            return True, "TIME_STOP"

        return False, ""
