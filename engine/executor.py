"""
Order router — sits between signals.py and the broker layer.
In PAPER mode: routes to brokers/paper.py.
In LIVE mode: routes to brokers/zerodha.py (Phase 6) or brokers/alpaca.py (Phase 7).

Flow:
  signal → check circuit breakers → check limits → size position
         → place order → write Trade → monitor for exit → close Trade
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy.orm import Session

from brokers.paper import PaperBroker
from database.trade_log import create_trade, close_trade, get_open_trades, get_open_trade
from database.portfolio import take_snapshot, get_latest_snapshot
from engine.costs import calculate_costs
from engine.risk import (
    RISK_PARAMS,
    calculate_position_size,
    check_circuit_breakers,
    check_position_limit,
    check_portfolio_heat,
)


class Executor:
    def __init__(
        self,
        db: Session,
        broker: PaperBroker,
        market: str = "INDIA",
        execution_mode: str = "PAPER",
        segment: str = "equity_intraday",
    ):
        self.db = db
        self.broker = broker
        self.market = market
        self.execution_mode = execution_mode
        self.segment = segment

    # ------------------------------------------------------------------ #
    # Entry                                                                #
    # ------------------------------------------------------------------ #

    def execute_entry(self, signal: dict) -> dict:
        """
        Validate, size, and place a buy order for a signal.
        Returns {"status": "FILLED"|"REJECTED", "reason": str, "trade_id": str|None}
        """
        symbol = signal["symbol"]

        # 1. Skip deferred signals (MOM_CONT waiting for next-day gap check)
        if signal.get("deferred"):
            return {"status": "DEFERRED", "reason": "Awaiting next-open gap check", "trade_id": None}

        # 2. No duplicate positions
        if get_open_trade(self.db, symbol):
            return {"status": "REJECTED", "reason": f"Already have open position in {symbol}", "trade_id": None}

        # 3. Circuit breakers
        snap = get_latest_snapshot(self.db, self.market)
        portfolio_value = self.broker.cash if snap is None else snap.portfolio_value
        peak_value = portfolio_value if snap is None else (snap.peak_value or portfolio_value)

        status, reason = check_circuit_breakers(
            self.db, portfolio_value, peak_value, self.market,
            strategy_id=signal.get("strategy_id", ""),
        )
        if status == "HALT":
            logger.warning(f"HALT — skipping {symbol}: {reason}")
            return {"status": "REJECTED", "reason": reason, "trade_id": None}

        # 4. Position count limit
        if not check_position_limit(self.db, self.market):
            return {"status": "REJECTED", "reason": "Max concurrent positions reached", "trade_id": None}

        # 5. Portfolio heat check
        if not check_portfolio_heat(self.db, portfolio_value, self.market):
            return {"status": "REJECTED", "reason": "Max portfolio heat reached", "trade_id": None}

        # 6. Position sizing (reduce 50% if VIX elevated)
        risk_pct = RISK_PARAMS["max_risk_per_trade_pct"]
        if status == "REDUCE_50PCT":
            risk_pct *= 0.5
            logger.info(f"VIX elevated: halving risk to {risk_pct:.1%} for {symbol}")

        quantity = calculate_position_size(
            portfolio_value=portfolio_value,
            entry_price=signal["entry_price"],
            stop_price=signal["stop_price"],
            risk_pct=risk_pct,
            market=self.market,
        )
        if quantity <= 0:
            return {"status": "REJECTED", "reason": "Calculated quantity = 0", "trade_id": None}

        # 7. Place order
        order = self.broker.buy(symbol, quantity, signal["entry_price"])
        if order["status"] != "FILLED":
            return {"status": "REJECTED", "reason": order.get("reason", "Broker rejected"), "trade_id": None}

        # 8. Cost estimate (buy-side; sell-side added on close)
        buy_costs = calculate_costs(
            self.market,
            buy_price=order["fill_price"],
            sell_price=order["fill_price"],  # placeholder — updated on exit
            quantity=quantity,
            segment=self.segment,
        )

        # 9. Log to DB
        trade = create_trade(
            db=self.db,
            signal=signal,
            order=order,
            quantity=quantity,
            costs=buy_costs,
            market=self.market,
            segment=self.segment,
            execution_mode=self.execution_mode,
        )

        return {"status": "FILLED", "reason": "OK", "trade_id": trade.trade_id}

    # ------------------------------------------------------------------ #
    # Exit                                                                 #
    # ------------------------------------------------------------------ #

    def execute_exit(
        self,
        symbol: str,
        exit_price: float,
        exit_reason: str,
    ) -> dict:
        """
        Close an open position and settle costs + P&L.
        """
        trade = get_open_trade(self.db, symbol)
        if not trade:
            return {"status": "REJECTED", "reason": f"No open trade for {symbol}"}

        order = self.broker.sell(symbol, trade.quantity, exit_price)
        if order["status"] != "FILLED":
            return {"status": "REJECTED", "reason": order.get("reason", "Broker rejected")}

        sell_costs = calculate_costs(
            self.market,
            buy_price=trade.entry_price,
            sell_price=order["fill_price"],
            quantity=trade.quantity,
            segment=self.segment,
        )

        close_trade(
            db=self.db,
            trade=trade,
            exit_price=order["fill_price"],
            exit_reason=exit_reason,
            sell_costs=sell_costs,
            exit_order_id=order.get("order_id"),
        )

        return {"status": "FILLED", "reason": "OK", "trade_id": trade.trade_id}

    # ------------------------------------------------------------------ #
    # EOD housekeeping                                                     #
    # ------------------------------------------------------------------ #

    def force_exit_all_eod(self, current_prices: dict) -> list[str]:
        """
        Force-close all open positions at EOD (15:20 IST).
        current_prices: {symbol: price}
        Returns list of trade_ids closed.
        """
        closed = []
        for trade in get_open_trades(self.db):
            symbol = trade.symbol
            price = current_prices.get(symbol, trade.entry_price)
            result = self.execute_exit(symbol, price, "EOD")
            if result["status"] == "FILLED":
                closed.append(result["trade_id"])
        logger.info(f"EOD force-exit: {len(closed)} position(s) closed")
        return closed

    def take_eod_snapshot(self, current_prices: dict) -> None:
        """Take portfolio snapshot after EOD exits."""
        portfolio_value = self.broker.get_portfolio_value(current_prices)
        take_snapshot(
            db=self.db,
            portfolio_value=portfolio_value,
            cash_balance=self.broker.cash,
            market=self.market,
        )
