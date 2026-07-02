"""
RSI-2 Overnight Mean Reversion (RSI2_OVN)
------------------------------------------
Entry:  RSI(2) < 10  AND  close > SMA(200)  AND  not Friday
Timing: Signal generated at 15:00 IST; order placed at market close (~15:25 IST)
Exit:   Next-day open by default. Also exits on RSI(2)>65, 4% stop, or 2-day time stop.
"""
import pandas as pd
from loguru import logger

from strategies.base import BaseStrategy

DEFAULT_PARAMS = {
    "rsi_period": 2,
    "rsi_entry_threshold": 10,
    "rsi_exit_threshold": 65,
    "sma_filter_period": 200,
    "stop_loss_pct": 0.04,
    "max_hold_candles": 2,
    "entry_timing": "close",
    "exit_timing": "next_open",
    "avoid_friday_entry": True,
}


class RSI2OvernightStrategy(BaseStrategy):
    strategy_id = "RSI2_OVN"
    name = "RSI-2 Overnight Mean Reversion"

    def __init__(self, params: dict | None = None, market: str = "INDIA"):
        merged = {**DEFAULT_PARAMS, **(params or {})}
        super().__init__(merged, market)

    def generate_signal(self, symbol: str, df: pd.DataFrame) -> dict | None:
        if df is None or len(df) < self.params["sma_filter_period"]:
            return None

        last = df.iloc[-1]
        rsi_col = f"rsi_{self.params['rsi_period']}"
        sma_col = f"sma_{self.params['sma_filter_period']}"

        rsi2 = self._get(last, rsi_col)
        sma200 = self._get(last, sma_col)
        close = self._get(last, "close")

        if any(v is None for v in [rsi2, sma200, close]):
            logger.debug(f"{symbol}: missing indicators — rsi2={rsi2}, sma200={sma200}")
            return None

        # Friday filter
        if self.params["avoid_friday_entry"]:
            idx = last.name if hasattr(last, "name") else df.index[-1]
            if pd.Timestamp(idx).dayofweek == 4:  # 4 = Friday
                logger.debug(f"{symbol}: skipping Friday entry")
                return None

        # Entry conditions
        if rsi2 >= self.params["rsi_entry_threshold"]:
            return None
        if close <= sma200:
            return None

        entry_price = float(close)
        stop_price = round(entry_price * (1 - self.params["stop_loss_pct"]), 4)
        # Nominal 2:1 target for R:R logging; actual exit is RSI-based
        target_price = round(entry_price + 2 * (entry_price - stop_price), 4)
        planned_rr = round((target_price - entry_price) / (entry_price - stop_price), 2)

        reason = (
            f"RSI({self.params['rsi_period']})={rsi2:.2f} < {self.params['rsi_entry_threshold']}, "
            f"close={close:.2f} > SMA{self.params['sma_filter_period']}={sma200:.2f}, "
            f"entry at close"
        )
        logger.info(f"[RSI2_OVN] BUY signal: {symbol} | {reason}")

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
                "rsi2": round(float(rsi2), 2),
                "sma200": round(float(sma200), 2),
                "close": round(entry_price, 2),
            },
        }

    def should_exit(self, trade: dict, current_bar: dict) -> tuple[bool, str]:
        entry_price = trade["entry_price"]
        current_price = current_bar.get("close", entry_price)
        rsi2 = current_bar.get(f"rsi_{self.params['rsi_period']}")
        hold_days = trade.get("hold_days", 0)

        # 1. RSI exit (target)
        if rsi2 is not None and rsi2 > self.params["rsi_exit_threshold"]:
            return True, "RSI_EXIT"

        # 2. Hard stop
        loss_pct = self._pnl_pct(entry_price, current_price)
        if loss_pct <= -self.params["stop_loss_pct"]:
            return True, "STOP"

        # 3. Default: always exit at next open (hold_days >= 1 means we've passed open)
        if trade.get("exit_timing") == "next_open" and hold_days >= 1:
            return True, "EOD"

        return False, ""
