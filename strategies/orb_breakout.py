"""
Opening Range Breakout (ORB_BRK)
---------------------------------
Opening range:  09:15–09:45 IST (India) | 09:30–10:00 EST (US)
Entry trigger:  15-min candle CLOSES above ORH on ≥1.5× volume AND market is green
Stop:           Price falls back below ORH (signal invalidated)
Target:         entry + Range × 2  (2:1 R:R minimum)
EOD exit:       14:45 IST if still open (avoid illiquid last 15 min)
"""
import pandas as pd
from loguru import logger

from strategies.base import BaseStrategy

DEFAULT_PARAMS = {
    "orb_window_minutes": 30,
    "confirmation_candle_tf": "15min",
    "volume_multiplier": 1.5,
    "market_filter": True,       # NIFTY50/SPY must be green (handled by signals.py)
    "stop_loss_type": "below_orh",
    "min_rr_ratio": 2.0,
    "exit_timing": "eod",
    "max_hold_days": 1,
}


class ORBBreakoutStrategy(BaseStrategy):
    strategy_id = "ORB_BRK"
    name = "Opening Range Breakout"

    def __init__(self, params: dict | None = None, market: str = "INDIA"):
        merged = {**DEFAULT_PARAMS, **(params or {})}
        super().__init__(merged, market)

    def generate_signal(self, symbol: str, df: pd.DataFrame) -> dict | None:
        """
        df must be 15-min intraday bars for today.
        Caller (signals.py) is responsible for passing today-only intraday data.
        """
        if df is None or df.empty:
            return None

        # Identify opening range bars (first 2 × 15-min = 30 min)
        orb_bars = df.iloc[:2]
        if len(orb_bars) < 2:
            return None

        orh = float(orb_bars["high"].max())
        orl = float(orb_bars["low"].min())
        orb_range = orh - orl

        if orb_range <= 0:
            return None

        # Volume baseline: 20-day avg passed via column vol_sma_20 on first bar
        vol_sma = self._get(df.iloc[0], "vol_sma_20")

        # Scan candles after ORB window for breakout
        post_orb = df.iloc[2:]
        for i, (idx, row) in enumerate(post_orb.iterrows()):
            candle_close = self._get(row, "close")
            candle_vol = self._get(row, "volume")

            if candle_close is None or candle_vol is None:
                continue

            # Must close ABOVE ORH
            if candle_close <= orh:
                continue

            # Volume confirmation
            if vol_sma is not None and candle_vol < self.params["volume_multiplier"] * vol_sma:
                continue

            # R:R check — entry ≈ candle_close, stop = ORH, target = entry + range*2
            entry_price = float(candle_close)
            stop_price = round(orh, 4)           # break back below ORH = invalidated
            target_price = round(entry_price + orb_range * self.params["min_rr_ratio"], 4)
            rr = (target_price - entry_price) / max(entry_price - stop_price, 0.01)

            if rr < self.params["min_rr_ratio"]:
                continue

            vol_ratio = round(candle_vol / vol_sma, 2) if vol_sma else None
            reason = (
                f"ORB breakout: close={entry_price:.2f} > ORH={orh:.2f}, "
                f"range={orb_range:.2f}, vol_ratio={vol_ratio}x, R:R={rr:.2f}"
            )
            logger.info(f"[ORB_BRK] BUY signal: {symbol} | {reason}")

            return {
                "action": "BUY",
                "symbol": symbol,
                "strategy_id": self.strategy_id,
                "strategy_name": self.name,
                "entry_price": entry_price,
                "stop_price": stop_price,
                "target_price": target_price,
                "planned_rr_ratio": round(rr, 2),
                "signal_reason": reason,
                "indicators": {
                    "orh": round(orh, 2),
                    "orl": round(orl, 2),
                    "orb_range": round(orb_range, 2),
                    "vol_ratio": vol_ratio,
                },
            }

        return None

    def should_exit(self, trade: dict, current_bar: dict) -> tuple[bool, str]:
        entry_price = trade["entry_price"]
        stop_price = trade["stop_price"]
        target_price = trade["target_price"]
        current_price = current_bar.get("close", entry_price)
        orh = trade.get("opening_range_high", stop_price)

        # 1. Target hit
        if current_price >= target_price:
            return True, "TARGET"

        # 2. Price falls back below ORH (signal invalidated)
        if current_price < orh:
            return True, "STOP"

        # 3. EOD exit
        if current_bar.get("is_eod", False):
            return True, "EOD"

        # 4. Hard stop (shouldn't trigger before ORH break, but safety net)
        if self._pnl_pct(entry_price, current_price) <= -0.04:
            return True, "STOP"

        return False, ""
