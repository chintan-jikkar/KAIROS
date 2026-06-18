"""
Momentum Continuation (MOM_CONT)
----------------------------------
EOD scan (15:30 IST):  stock up >3% on >2× volume, RSI(14) 50–75, market green → FLAG
Next-day entry:        gap-up < 2%  → BUY within first 15 min
                       gap-up ≥ 2%  → SKIP (already priced in)
                       gap-down     → SKIP (momentum reversed)
Exit:                  intraday loss >2%, RSI(14) > 80, or EOD (15:20 IST always)
"""
import pandas as pd
from loguru import logger

from strategies.base import BaseStrategy

DEFAULT_PARAMS = {
    "min_daily_gain_pct": 3.0,
    "volume_multiplier": 2.0,
    "rsi14_range": (50, 75),
    "market_filter": True,
    "max_gap_up_pct": 2.0,
    "entry_window_minutes": 15,
    "entry_timing": "next_open",
    "stop_loss_pct": 0.02,
    "exit_timing": "eod",
    "rsi14_exit_threshold": 80,
}


class MomentumContinuationStrategy(BaseStrategy):
    strategy_id = "MOM_CONT"
    name = "Momentum Continuation"

    def __init__(self, params: dict | None = None, market: str = "INDIA"):
        merged = {**DEFAULT_PARAMS, **(params or {})}
        super().__init__(merged, market)

    def generate_signal(self, symbol: str, df: pd.DataFrame) -> dict | None:
        """
        Called on daily data at EOD scan (15:30 IST).
        df[-1] = today's completed bar.
        Returns a FLAGGED signal (entry deferred to next day's open check).
        The executor / scheduler will check gap at next open before executing.
        """
        if df is None or len(df) < 21:
            return None

        last = df.iloc[-1]
        prev = df.iloc[-2]

        close = self._get(last, "close")
        prev_close = self._get(prev, "close")
        volume = self._get(last, "volume")
        vol_sma = self._get(last, "vol_sma_20")
        rsi14 = self._get(last, "rsi_14")

        if any(v is None for v in [close, prev_close, volume, rsi14]):
            return None

        # Daily gain check
        day_return_pct = (close - prev_close) / prev_close * 100
        if day_return_pct < self.params["min_daily_gain_pct"]:
            return None

        # Volume check
        vol_ratio = (volume / vol_sma) if vol_sma else 0
        if vol_ratio < self.params["volume_multiplier"]:
            return None

        # RSI(14) momentum zone
        rsi_lo, rsi_hi = self.params["rsi14_range"]
        if not (rsi_lo <= rsi14 <= rsi_hi):
            return None

        # Market filter (NIFTY/SPY green) is checked by signals.py before calling this

        # Signal flagged — entry price determined next morning at open
        # stop based on signal-day close as proxy; updated by executor at next open
        entry_est = float(close)
        stop_price = round(entry_est * (1 - self.params["stop_loss_pct"]), 4)
        target_price = round(entry_est * (1 + self.params["stop_loss_pct"] * 2.5), 4)

        reason = (
            f"MOM_CONT flag: {symbol} +{day_return_pct:.1f}% on {vol_ratio:.1f}x volume, "
            f"RSI14={rsi14:.1f}, entry deferred to next open"
        )
        logger.info(f"[MOM_CONT] FLAGGED: {symbol} | {reason}")

        return {
            "action": "BUY",
            "symbol": symbol,
            "strategy_id": self.strategy_id,
            "strategy_name": self.name,
            "entry_price": entry_est,    # placeholder; executor replaces with actual open
            "stop_price": stop_price,
            "target_price": target_price,
            "planned_rr_ratio": 2.5,
            "signal_reason": reason,
            "deferred": True,            # tells executor to wait for next-day open gap check
            "indicators": {
                "day_return_pct": round(day_return_pct, 2),
                "vol_ratio": round(vol_ratio, 2),
                "rsi14": round(float(rsi14), 2),
                "signal_close": round(entry_est, 2),
            },
        }

    def check_gap_and_confirm(self, signal: dict, open_price: float) -> dict | None:
        """
        Called at next-day open (09:30–09:45 IST) to confirm or cancel the deferred signal.
        Returns the confirmed signal with updated entry_price, or None to cancel.
        """
        prev_close = signal["indicators"]["signal_close"]
        gap_pct = (open_price - prev_close) / prev_close * 100

        if gap_pct >= self.params["max_gap_up_pct"]:
            logger.info(f"[MOM_CONT] SKIP {signal['symbol']}: gap_up={gap_pct:.1f}% ≥ {self.params['max_gap_up_pct']}%")
            return None

        if gap_pct < 0:
            logger.info(f"[MOM_CONT] SKIP {signal['symbol']}: gap_down={gap_pct:.1f}% — momentum reversed")
            return None

        # Confirm: update entry price to actual open
        confirmed = {**signal}
        confirmed["entry_price"] = round(open_price, 4)
        confirmed["stop_price"] = round(open_price * (1 - self.params["stop_loss_pct"]), 4)
        confirmed["target_price"] = round(open_price * (1 + self.params["stop_loss_pct"] * 2.5), 4)
        confirmed["deferred"] = False
        confirmed["signal_reason"] += f" | gap_up={gap_pct:.1f}%, confirmed at open={open_price:.2f}"
        logger.info(f"[MOM_CONT] CONFIRMED: {signal['symbol']} @ open {open_price:.2f}, gap={gap_pct:.1f}%")
        return confirmed

    def should_exit(self, trade: dict, current_bar: dict) -> tuple[bool, str]:
        entry_price = trade["entry_price"]
        current_price = current_bar.get("close", entry_price)
        rsi14 = current_bar.get("rsi_14")

        # 1. RSI overbought exit
        if rsi14 is not None and rsi14 >= self.params["rsi14_exit_threshold"]:
            return True, "RSI_EXIT"

        # 2. Intraday stop
        if self._pnl_pct(entry_price, current_price) <= -self.params["stop_loss_pct"]:
            return True, "STOP"

        # 3. Always exit at EOD
        if current_bar.get("is_eod", False):
            return True, "EOD"

        return False, ""
