"""
Portfolio snapshot tracker — one record per trading day, per market.
Used to build the equity curve in the dashboard.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models import PortfolioSnapshot, Trade


def take_snapshot(
    db: Session,
    portfolio_value: float,
    cash_balance: float,
    market: str = "INDIA",
    snapshot_date: date | None = None,
) -> PortfolioSnapshot:
    """
    Called at EOD (15:30 IST). Records full portfolio state for the equity curve.
    """
    today = snapshot_date or date.today()

    open_trades = db.query(Trade).filter(Trade.timestamp_exit.is_(None)).all()
    invested_value = sum(
        (t.entry_price or 0) * (t.quantity or 0) for t in open_trades
    )

    # Today's realized P&L
    today_trades = db.query(Trade).filter(
        func.date(Trade.timestamp_exit) == today,
        Trade.net_pnl.isnot(None),
    ).all()
    realized_today = sum(t.net_pnl for t in today_trades)
    costs_today = sum(t.total_costs for t in today_trades)

    # Cumulative realized P&L
    all_closed = db.query(Trade).filter(Trade.net_pnl.isnot(None)).all()
    realized_cumulative = sum(t.net_pnl for t in all_closed)
    costs_cumulative = sum(t.total_costs for t in all_closed)

    # Unrealized P&L (entry-price based — live price updates come from dashboard)
    unrealized = portfolio_value - cash_balance - invested_value

    # Peak value for drawdown calculation
    peak = _get_peak_value(db, market, portfolio_value)
    drawdown_pct = (portfolio_value - peak) / peak if peak else 0.0

    snap = PortfolioSnapshot(
        snapshot_id=str(uuid.uuid4()),
        date=today,
        market=market,
        portfolio_value=round(portfolio_value, 4),
        cash_balance=round(cash_balance, 4),
        invested_value=round(invested_value, 4),
        open_positions_count=len(open_trades),
        realized_pnl_today=round(realized_today, 4),
        realized_pnl_cumulative=round(realized_cumulative, 4),
        unrealized_pnl=round(unrealized, 4),
        total_costs_today=round(costs_today, 4),
        total_costs_cumulative=round(costs_cumulative, 4),
        peak_value=round(peak, 4),
        drawdown_from_peak_pct=round(drawdown_pct, 6),
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    logger.info(
        f"Portfolio snapshot: {today} | value=₹{portfolio_value:.2f} | "
        f"drawdown={drawdown_pct:.2%}"
    )
    return snap


def get_latest_snapshot(db: Session, market: str = "INDIA") -> PortfolioSnapshot | None:
    return (
        db.query(PortfolioSnapshot)
        .filter(PortfolioSnapshot.market == market)
        .order_by(PortfolioSnapshot.date.desc())
        .first()
    )


def _get_peak_value(db: Session, market: str, current_value: float) -> float:
    row = (
        db.query(func.max(PortfolioSnapshot.portfolio_value))
        .filter(PortfolioSnapshot.market == market)
        .scalar()
    )
    return max(row or current_value, current_value)
