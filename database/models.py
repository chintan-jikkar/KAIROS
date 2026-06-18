from datetime import datetime
import uuid

from sqlalchemy import (
    Column, String, Float, DateTime, Date,
    Text, Boolean, Integer
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Trade(Base):
    __tablename__ = "trades"

    # Identity
    trade_id = Column(
        String, primary_key=True,
        default=lambda: f"KRS-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:6].upper()}"
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    # Timing
    timestamp_entry = Column(DateTime, nullable=False)
    timestamp_exit = Column(DateTime, nullable=True)
    holding_period_hours = Column(Float)

    # Market context
    market = Column(String)          # INDIA | US | FX
    exchange = Column(String)        # NSE | NASDAQ | NYSE | FOREX
    segment = Column(String)         # equity_delivery | equity_intraday | fno_options | fno_futures | fx
    execution_mode = Column(String)  # PAPER | LIVE

    # Instrument
    symbol = Column(String, nullable=False)
    instrument_type = Column(String)  # STOCK | OPTION | FUTURE | FX

    # Options-specific (null for stocks)
    option_type = Column(String, nullable=True)    # CE | PE | CALL | PUT
    strike_price = Column(Float, nullable=True)
    expiry_date = Column(Date, nullable=True)
    lot_size = Column(Integer, nullable=True)

    # Strategy
    strategy_id = Column(String)     # RSI2_OVN | ORB_BRK | MOM_CONT | CUSTOM
    strategy_name = Column(String)
    direction = Column(String)       # LONG | SHORT
    signal_reason = Column(Text)

    # Execution
    entry_price = Column(Float)
    exit_price = Column(Float, nullable=True)
    quantity = Column(Float)
    entry_order_id = Column(String, nullable=True)
    exit_order_id = Column(String, nullable=True)

    # Signal snapshot at entry
    rsi2_at_entry = Column(Float, nullable=True)
    rsi14_at_entry = Column(Float, nullable=True)
    atr14_at_entry = Column(Float, nullable=True)
    sma20_at_entry = Column(Float, nullable=True)
    sma50_at_entry = Column(Float, nullable=True)
    sma200_at_entry = Column(Float, nullable=True)
    vwap_at_entry = Column(Float, nullable=True)
    volume_at_entry = Column(Float, nullable=True)
    volume_ratio_at_entry = Column(Float, nullable=True)
    macd_at_entry = Column(Float, nullable=True)
    bbands_upper_at_entry = Column(Float, nullable=True)
    bbands_lower_at_entry = Column(Float, nullable=True)
    india_vix_at_entry = Column(Float, nullable=True)
    nifty50_return_at_entry = Column(Float, nullable=True)
    opening_range_high = Column(Float, nullable=True)
    opening_range_low = Column(Float, nullable=True)

    # Risk levels
    stop_loss_price = Column(Float)
    target_price = Column(Float)
    planned_rr_ratio = Column(Float)

    # P&L (gross)
    gross_pnl = Column(Float, nullable=True)
    gross_pnl_pct = Column(Float, nullable=True)

    # Cost breakdown — India
    brokerage = Column(Float, default=0.0)
    stt = Column(Float, default=0.0)
    stamp_duty = Column(Float, default=0.0)
    exchange_charges = Column(Float, default=0.0)
    sebi_charges = Column(Float, default=0.0)
    gst = Column(Float, default=0.0)

    # Cost breakdown — US
    sec_fee = Column(Float, default=0.0)
    finra_taf = Column(Float, default=0.0)

    # Net P&L
    total_costs = Column(Float, default=0.0)
    net_pnl = Column(Float, nullable=True)
    net_pnl_pct = Column(Float, nullable=True)

    # Trade analytics
    max_adverse_excursion_pct = Column(Float, nullable=True)
    max_favorable_excursion_pct = Column(Float, nullable=True)
    actual_rr_achieved = Column(Float, nullable=True)

    # Outcome
    outcome = Column(String, nullable=True)      # WIN | LOSS | BREAKEVEN
    exit_reason = Column(String, nullable=True)  # TARGET | STOP | RSI_EXIT | EOD | TIME_STOP | MANUAL

    # Notes
    auto_notes = Column(Text, nullable=True)
    manual_notes = Column(Text, nullable=True)


class PortfolioSnapshot(Base):
    """Daily end-of-day portfolio snapshot for equity curve."""
    __tablename__ = "portfolio_snapshots"

    snapshot_id = Column(String, primary_key=True,
                         default=lambda: str(uuid.uuid4()))
    date = Column(Date, nullable=False)
    market = Column(String)
    portfolio_value = Column(Float)
    cash_balance = Column(Float)
    invested_value = Column(Float)
    open_positions_count = Column(Integer)
    realized_pnl_today = Column(Float)
    realized_pnl_cumulative = Column(Float)
    unrealized_pnl = Column(Float)
    total_costs_today = Column(Float)
    total_costs_cumulative = Column(Float)
    peak_value = Column(Float)
    drawdown_from_peak_pct = Column(Float)


class Signal(Base):
    """Log every signal generated, executed or not."""
    __tablename__ = "signals"

    signal_id = Column(String, primary_key=True,
                       default=lambda: str(uuid.uuid4()))
    generated_at = Column(DateTime, default=datetime.utcnow)
    market = Column(String)
    symbol = Column(String)
    strategy_id = Column(String)
    signal_type = Column(String)     # ENTRY | EXIT
    action = Column(String)          # BUY | SELL | HOLD
    signal_reason = Column(Text)
    was_executed = Column(Boolean, default=False)
    execution_skipped_reason = Column(String, nullable=True)
    trade_id = Column(String, nullable=True)
