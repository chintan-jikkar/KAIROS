"""
Paper trading simulator — logs all orders to kairos.db without touching real money.
Mimics the interface of live broker wrappers so executor.py can swap them transparently.
"""
from datetime import datetime
from loguru import logger


class PaperBroker:
    def __init__(self, db_session, starting_capital: float):
        self.session = db_session
        self.cash = starting_capital
        self.positions: dict = {}   # symbol → {qty, entry_price, entry_time}
        logger.info(f"PaperBroker initialized with capital={starting_capital}")

    def buy(self, symbol: str, quantity: float, price: float) -> dict:
        cost = quantity * price
        if cost > self.cash:
            logger.warning(f"Insufficient cash for {symbol}: need {cost:.2f}, have {self.cash:.2f}")
            return {"status": "REJECTED", "reason": "insufficient_cash"}

        self.cash -= cost
        self.positions[symbol] = {
            "qty": quantity,
            "entry_price": price,
            "entry_time": datetime.utcnow(),
        }
        order_id = f"PAPER-BUY-{symbol}-{datetime.now().strftime('%H%M%S')}"
        logger.info(f"[PAPER] BUY {quantity} {symbol} @ {price:.2f} | cash remaining: {self.cash:.2f}")
        return {"status": "FILLED", "order_id": order_id, "fill_price": price}

    def sell(self, symbol: str, quantity: float, price: float) -> dict:
        if symbol not in self.positions:
            logger.warning(f"No open position to sell for {symbol}")
            return {"status": "REJECTED", "reason": "no_position"}

        proceeds = quantity * price
        self.cash += proceeds
        del self.positions[symbol]
        order_id = f"PAPER-SELL-{symbol}-{datetime.now().strftime('%H%M%S')}"
        logger.info(f"[PAPER] SELL {quantity} {symbol} @ {price:.2f} | cash: {self.cash:.2f}")
        return {"status": "FILLED", "order_id": order_id, "fill_price": price}

    def get_portfolio_value(self, current_prices: dict) -> float:
        invested = sum(
            pos["qty"] * current_prices.get(sym, pos["entry_price"])
            for sym, pos in self.positions.items()
        )
        return self.cash + invested

    def get_open_positions(self) -> dict:
        return self.positions.copy()
