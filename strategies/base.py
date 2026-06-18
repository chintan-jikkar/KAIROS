from abc import ABC, abstractmethod
import pandas as pd


class BaseStrategy(ABC):
    def __init__(self, params: dict, market: str = "INDIA"):
        self.params = params
        self.market = market
        self.strategy_id: str = ""
        self.name: str = ""

    @abstractmethod
    def generate_signal(self, symbol: str, df: pd.DataFrame) -> dict | None:
        """
        Evaluate the latest bar in df and return a signal dict or None.

        Signal dict schema:
        {
            "action":        "BUY" | "SELL" | "HOLD",
            "symbol":        str,
            "strategy_id":   str,
            "entry_price":   float,
            "stop_price":    float,
            "target_price":  float,
            "signal_reason": str,   # human-readable, e.g. "RSI(2)=8.3 < 10, above SMA200=1456.2"
            "indicators":    dict,  # snapshot of all indicator values at signal time
        }
        """

    @abstractmethod
    def should_exit(self, trade: dict, current_bar: dict) -> tuple[bool, str]:
        """
        Returns (should_exit, exit_reason).
        exit_reason values: TARGET | STOP | RSI_EXIT | EOD | TIME_STOP | MANUAL
        """

    # ------------------------------------------------------------------ #
    # Shared helpers available to all subclasses                          #
    # ------------------------------------------------------------------ #

    def _get(self, row, col: str, default=None):
        """Safe column accessor — returns default if column missing or NaN."""
        val = row.get(col, default) if isinstance(row, dict) else getattr(row, col, default)
        if val is None:
            return default
        try:
            import math
            return default if math.isnan(float(val)) else val
        except (TypeError, ValueError):
            return val

    def _pnl_pct(self, entry: float, current: float, direction: str = "LONG") -> float:
        if direction == "LONG":
            return (current - entry) / entry
        return (entry - current) / entry
