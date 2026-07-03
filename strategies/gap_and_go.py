"""
Gap and Go (GAP_GO)
-------------------
Intraday strategy for high-beta names (TSLA, NVDA, COIN, TATAMOTORS etc.)
that gap up on news or earnings momentum and sustain the move intraday.

The setup is directional, not mean-reverting: a large gap up means buyers
are in control and shorts are squeezed — the 'go' phase follows the gap
as price continues higher into the session.

Entry:  today's open is 2-5% above prior close (the gap)
        + first 15-min candle is bullish (close > open of that candle)
        + volume on the first candle is ≥ 2× the 20-day average daily volume
          (institutional participation, not just retail FOMO).
Stop:   low of the first 15-min candle — if that level breaks, the gap
        failed and the intraday thesis is invalidated.
Target: entry + (entry − stop) × 2.5 (2.5:1 R:R).
Exit:   stop, target, or EOD — purely intraday.

Gap size range 2-5% filters out:
  < 2%: too small, normal overnight noise; no real gap-and-go dynamic.
  > 5%: often a binary event (earnings, news) — spread is wide, fill
        quality is poor, and mean-reversion risk is higher than momentum.
"""
import pandas as pd
from loguru import logger

from strategies.base import BaseStrategy

DEFAULT_PARAMS = {
    "gap_min_pct": 0.02,        # 2% minimum gap
    "gap_max_pct": 0.05,        # 5% maximum gap (larger = higher risk)
    "volume_ratio_min": 2.0,    # first-candle volume vs 20-day daily average
    "risk_reward": 2.5,
}


class GapAndGoStrategy(BaseStrategy):
    strategy_id = "GAP_GO"
    name = "Gap and go"

    def __init__(self, params: dict | None = None, market: str = "INDIA"):
        merged = {**DEFAULT_PARAMS, **(params or {})}
        super().__init__(merged, market)
        self.strategy_id = "GAP_GO"
        self.name = "Gap and go"

    def generate_signal(self, symbol: str, df: pd.DataFrame) -> dict | None:
        """df: intraday 15-min bars for today.
        Expected extra columns: vol_sma_20 (pre-computed from daily data).
        """
        if df is None or len(df) < 2:
            return None

        # Prior close is the last row of the previous session's data —
        # signals.py sets df_intra["prev_close"] from daily data before calling us.
        first = df.iloc[0]
        first_open = self._get(first, "open")
        first_close = self._get(first, "close")
        first_volume = self._get(first, "volume")
        prev_close = self._get(first, "prev_close")
        vol_sma_20 = self._get(first, "vol_sma_20")

        if any(v is None for v in [first_open, first_close, first_volume, prev_close]):
            return None

        # Gap calculation
        gap_pct = (float(first_open) - float(prev_close)) / float(prev_close)
        if not (self.params["gap_min_pct"] <= gap_pct <= self.params["gap_max_pct"]):
            logger.debug(f"{symbol}: gap={gap_pct:.2%} outside [{self.params['gap_min_pct']:.0%}-{self.params['gap_max_pct']:.0%}] window")
            return None

        # First candle must be bullish
        if float(first_close) <= float(first_open):
            logger.debug(f"{symbol}: gap present but first candle bearish — skipping")
            return None

        # Volume gate
        if vol_sma_20 is not None:
            candle_vol_ratio = float(first_volume) / float(vol_sma_20)
            if candle_vol_ratio < self.params["volume_ratio_min"]:
                logger.debug(f"{symbol}: gap+go but vol_ratio={candle_vol_ratio:.2f} insufficient — skipping")
                return None

        entry_price = float(first_close)
        stop_price = round(float(first.get("low", first_open)), 4)  # first candle low
        if stop_price >= entry_price:
            return None  # degenerate: stop ≥ entry (e.g. single-tick candle)

        risk = entry_price - stop_price
        target_price = round(entry_price + risk * self.params["risk_reward"], 4)
        planned_rr = round((target_price - entry_price) / risk, 2)

        reason = (
            f"Gap up {gap_pct:.1%} (open={first_open:.2f}, prev_close={prev_close:.2f}), "
            f"first candle bullish ({first_open:.2f}→{first_close:.2f})"
        )
        logger.info(f"[GAP_GO] BUY signal: {symbol} | {reason}")

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
                "gap_pct": round(gap_pct, 4),
                "first_candle_open": round(float(first_open), 2),
                "first_candle_close": round(float(first_close), 2),
                "prev_close": round(float(prev_close), 2),
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

        # Always flatten before close — intraday only
        if current_bar.get("is_eod", False):
            return True, "EOD"

        return False, ""
