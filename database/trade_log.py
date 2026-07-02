"""
Trade CRUD operations — the only place that writes to the trades table.
All other modules (dashboard, signals) read only.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from loguru import logger
from sqlalchemy.orm import Session

import json

from database.models import Trade, PendingSignal


def market_currency_symbol(market: str) -> str:
    """The trade's own intrinsic currency — independent of any dashboard display toggle."""
    return "$" if market == "US" else "₹"


def breakeven_price(trade: Trade) -> float | None:
    """Price at which exiting would net exactly zero, given costs incurred so far."""
    if not trade.entry_price or not trade.quantity:
        return None
    costs_so_far = (trade.total_costs or 0) or (
        (trade.brokerage or 0) + (trade.stt or 0) + (trade.stamp_duty or 0)
        + (trade.exchange_charges or 0) + (trade.sebi_charges or 0) + (trade.gst or 0)
        + (trade.sec_fee or 0) + (trade.finra_taf or 0)
    )
    if trade.direction == "SHORT":
        return round(trade.entry_price - (costs_so_far / trade.quantity), 4)
    return round(trade.entry_price + (costs_so_far / trade.quantity), 4)


def create_trade(
    db: Session,
    signal: dict,
    order: dict,
    quantity: float,
    costs: dict,
    market: str = "INDIA",
    segment: str = "equity_intraday",
    execution_mode: str = "PAPER",
) -> Trade:
    """
    Called immediately after an order is filled.
    signal   — from signals.py
    order    — from broker: {order_id, fill_price}
    quantity — from risk.calculate_position_size
    costs    — from costs.calculate_costs (buy-side only; sell-side added on close)
    """
    entry_price = order["fill_price"]
    indicators = signal.get("indicators", {})

    trade = Trade(
        trade_id=f"KRS-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}",
        created_at=datetime.utcnow(),
        timestamp_entry=datetime.utcnow(),
        market=market,
        exchange="NSE" if market == "INDIA" else "NASDAQ",
        segment=segment,
        execution_mode=execution_mode,
        symbol=signal["symbol"],
        instrument_type="STOCK",
        strategy_id=signal["strategy_id"],
        strategy_name=signal.get("strategy_name", signal["strategy_id"]),
        direction="LONG",
        signal_reason=signal["signal_reason"],
        entry_price=entry_price,
        quantity=quantity,
        entry_order_id=order.get("order_id"),
        stop_loss_price=signal["stop_price"],
        target_price=signal["target_price"],
        planned_rr_ratio=signal.get("planned_rr_ratio"),
        # Indicator snapshot
        rsi2_at_entry=indicators.get("rsi2"),
        rsi14_at_entry=indicators.get("rsi14"),
        sma200_at_entry=indicators.get("sma200"),
        vwap_at_entry=indicators.get("vwap"),
        volume_at_entry=indicators.get("volume"),
        volume_ratio_at_entry=indicators.get("vol_ratio"),
        atr14_at_entry=indicators.get("atr14"),
        opening_range_high=indicators.get("orh"),
        opening_range_low=indicators.get("orl"),
        # Costs (buy-side)
        stamp_duty=costs.get("stamp_duty", 0.0),
        exchange_charges=costs.get("exchange_charges", 0.0) / 2,  # split buy/sell
        sebi_charges=costs.get("sebi_charges", 0.0) / 2,
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)
    logger.info(f"Trade created: {trade.trade_id} | {trade.symbol} @ {entry_price:.2f} × {quantity}")
    return trade


def close_trade(
    db: Session,
    trade: Trade,
    exit_price: float,
    exit_reason: str,
    sell_costs: dict,
    exit_order_id: str | None = None,
) -> Trade:
    """
    Called when a position is exited. Updates all P&L and cost fields.
    sell_costs — from costs.calculate_costs with actual sell price
    """
    now = datetime.utcnow()
    entry_price = trade.entry_price
    quantity = trade.quantity

    gross_pnl = (exit_price - entry_price) * quantity
    gross_pnl_pct = (exit_price - entry_price) / entry_price

    # Accumulate all costs (buy-side already partially recorded on entry)
    total_costs = (
        (trade.brokerage or 0)
        + sell_costs.get("brokerage", 0)
        + (trade.stt or 0)
        + sell_costs.get("stt", 0)
        + (trade.stamp_duty or 0)
        + (trade.exchange_charges or 0) + sell_costs.get("exchange_charges", 0) / 2
        + (trade.sebi_charges or 0) + sell_costs.get("sebi_charges", 0) / 2
        + sell_costs.get("gst", 0)
        + sell_costs.get("sec_fee", 0)
        + sell_costs.get("finra_taf", 0)
    )

    net_pnl = gross_pnl - total_costs
    net_pnl_pct = net_pnl / (entry_price * quantity)
    holding_hours = (now - trade.timestamp_entry).total_seconds() / 3600

    trade.timestamp_exit = now
    trade.exit_price = exit_price
    trade.exit_order_id = exit_order_id
    trade.exit_reason = exit_reason
    trade.holding_period_hours = round(holding_hours, 2)
    trade.gross_pnl = round(gross_pnl, 4)
    trade.gross_pnl_pct = round(gross_pnl_pct, 6)
    trade.total_costs = round(total_costs, 4)
    trade.net_pnl = round(net_pnl, 4)
    trade.net_pnl_pct = round(net_pnl_pct, 6)
    trade.stt = sell_costs.get("stt", 0)
    trade.brokerage = sell_costs.get("brokerage", 0)
    trade.gst = sell_costs.get("gst", 0)
    trade.sec_fee = sell_costs.get("sec_fee", 0)
    trade.finra_taf = sell_costs.get("finra_taf", 0)
    trade.outcome = (
        "WIN" if net_pnl > 0 else "LOSS" if net_pnl < 0 else "BREAKEVEN"
    )
    trade.actual_rr_achieved = round(
        net_pnl / abs((trade.stop_loss_price - entry_price) * quantity), 4
    ) if trade.stop_loss_price and trade.stop_loss_price != entry_price else None
    sym = market_currency_symbol(trade.market)
    trade.auto_notes = (
        f"Exit: {exit_reason} | Net P&L: {sym}{net_pnl:.2f} ({net_pnl_pct:.2%}) | "
        f"Costs: {sym}{total_costs:.2f} | Hold: {holding_hours:.1f}h"
    )

    db.commit()
    db.refresh(trade)
    logger.info(
        f"Trade closed: {trade.trade_id} | {trade.symbol} | {exit_reason} | "
        f"net P&L: ₹{net_pnl:.2f} ({net_pnl_pct:.2%})"
    )
    return trade


def update_journal(
    db: Session,
    trade_id: str,
    conviction: int | None = None,
    manual_notes: str | None = None,
    lesson_learned: str | None = None,
) -> Trade | None:
    """Lets the user fill in the journal fields after the fact, from the Logbook page."""
    trade = db.query(Trade).filter(Trade.trade_id == trade_id).first()
    if not trade:
        return None
    if conviction is not None:
        trade.conviction = conviction
    if manual_notes is not None:
        trade.manual_notes = manual_notes
    if lesson_learned is not None:
        trade.lesson_learned = lesson_learned
    db.commit()
    db.refresh(trade)
    return trade


def get_open_trades(db: Session, market: str | None = None) -> list[Trade]:
    query = db.query(Trade).filter(Trade.timestamp_exit.is_(None))
    if market is not None:
        query = query.filter(Trade.market == market)
    return query.all()


def get_open_trade(db: Session, symbol: str) -> Trade | None:
    return (
        db.query(Trade)
        .filter(Trade.symbol == symbol, Trade.timestamp_exit.is_(None))
        .first()
    )


# --------------------------------------------------------------------------- #
# Pending signal persistence (MOM_CONT crash-recovery)                         #
# --------------------------------------------------------------------------- #

def save_pending_signal(db: Session, market: str, signal: dict) -> None:
    """Persist a deferred MOM_CONT signal so it survives an overnight process restart."""
    row = PendingSignal(
        market=market,
        symbol=signal["symbol"],
        strategy_id=signal.get("strategy_id", "MOM_CONT"),
        signal_json=json.dumps(signal),
    )
    db.add(row)
    db.commit()


def load_pending_signals(db: Session, market: str) -> list[dict]:
    """Return unconsumed pending signals for the given market as plain dicts."""
    rows = (
        db.query(PendingSignal)
        .filter(PendingSignal.market == market, PendingSignal.is_consumed.is_(False))
        .all()
    )
    return [json.loads(r.signal_json) for r in rows]


def clear_pending_signals(db: Session, market: str) -> None:
    """Mark all pending signals for the given market as consumed after gap confirmation."""
    (
        db.query(PendingSignal)
        .filter(PendingSignal.market == market, PendingSignal.is_consumed.is_(False))
        .update({"is_consumed": True})
    )
    db.commit()
