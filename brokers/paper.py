"""
Paper trading simulator — logs all orders to kairos.db without touching real money.
Mimics the interface of live broker wrappers so executor.py can swap them transparently.
"""
from datetime import datetime
from loguru import logger

# Conservative one-way slippage estimates: India liquid NSE stocks ~10 bps,
# US large-caps ~5 bps. Applied as a fill-price penalty on both legs so that
# paper results reflect realistic execution rather than exact mid-price fills.
_SLIPPAGE_BPS: dict[str, float] = {"INDIA": 0.0010, "US": 0.0005}


class PaperBroker:
    def __init__(self, db_session, starting_capital: float, market: str = "INDIA"):
        self.session = db_session
        self.cash = starting_capital
        self.market = market
        self.positions: dict = {}   # symbol → {qty, entry_price, entry_time}
        self._slippage = _SLIPPAGE_BPS.get(market, 0.0010)
        logger.info(f"PaperBroker initialized with capital={starting_capital} market={market} slippage={self._slippage:.2%}")

    def buy(self, symbol: str, quantity: float, price: float) -> dict:
        fill_price = round(price * (1 + self._slippage), 4)
        cost = quantity * fill_price
        if cost > self.cash:
            logger.warning(f"Insufficient cash for {symbol}: need {cost:.2f}, have {self.cash:.2f}")
            return {"status": "REJECTED", "reason": "insufficient_cash"}

        self.cash -= cost
        self.positions[symbol] = {
            "qty": quantity,
            "entry_price": fill_price,
            "entry_time": datetime.utcnow(),
        }
        order_id = f"PAPER-BUY-{symbol}-{datetime.now().strftime('%H%M%S')}"
        logger.info(f"[PAPER] BUY {quantity} {symbol} @ {fill_price:.2f} (slip {self._slippage:.2%}) | cash: {self.cash:.2f}")
        return {"status": "FILLED", "order_id": order_id, "fill_price": fill_price}

    def sell(self, symbol: str, quantity: float, price: float) -> dict:
        if symbol not in self.positions:
            logger.warning(f"No open position to sell for {symbol}")
            return {"status": "REJECTED", "reason": "no_position"}

        fill_price = round(price * (1 - self._slippage), 4)
        proceeds = quantity * fill_price
        self.cash += proceeds
        del self.positions[symbol]
        order_id = f"PAPER-SELL-{symbol}-{datetime.now().strftime('%H%M%S')}"
        logger.info(f"[PAPER] SELL {quantity} {symbol} @ {fill_price:.2f} (slip {self._slippage:.2%}) | cash: {self.cash:.2f}")
        return {"status": "FILLED", "order_id": order_id, "fill_price": fill_price}

    def get_portfolio_value(self, current_prices: dict) -> float:
        invested = sum(
            pos["qty"] * current_prices.get(sym, pos["entry_price"])
            for sym, pos in self.positions.items()
        )
        return self.cash + invested

    def get_open_positions(self) -> dict:
        return self.positions.copy()
