"""
Watchlist CRUD — persisted pinned symbols shown at-a-glance in the Markets page.
Independent of the screener's auto-selected universe; this is purely user curation.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from database.models import WatchlistItem


def add_to_watchlist(db: Session, symbol: str, market: str = "INDIA", note: str | None = None) -> WatchlistItem:
    existing = db.query(WatchlistItem).filter(
        WatchlistItem.symbol == symbol, WatchlistItem.market == market
    ).first()
    if existing:
        return existing

    max_order = db.query(WatchlistItem).count()
    item = WatchlistItem(
        item_id=str(uuid.uuid4()),
        symbol=symbol,
        market=market,
        note=note,
        added_at=datetime.utcnow(),
        sort_order=max_order,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def remove_from_watchlist(db: Session, item_id: str) -> None:
    db.query(WatchlistItem).filter(WatchlistItem.item_id == item_id).delete()
    db.commit()


def get_watchlist(db: Session, market: str | None = None) -> list[WatchlistItem]:
    q = db.query(WatchlistItem)
    if market:
        q = q.filter(WatchlistItem.market == market)
    return q.order_by(WatchlistItem.sort_order).all()


def is_watchlisted(db: Session, symbol: str, market: str = "INDIA") -> bool:
    return db.query(WatchlistItem).filter(
        WatchlistItem.symbol == symbol, WatchlistItem.market == market
    ).first() is not None
