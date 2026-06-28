"""
Backtesting engine — replays history through the exact generate_signal/should_exit/
cost-calculation code paths live trading uses. See
docs/superpowers/specs/2026-06-20-backtesting-engine-design.md for the full design,
and the "Key design decisions" section at the top of
docs/superpowers/plans/2026-06-20-backtesting-engine.md for the entry/exit timing and
single-call-cost decisions baked into this loop.
"""
from __future__ import annotations

import itertools
import json
import uuid

import pandas as pd
from loguru import logger

from data.market_data import fetch_india_daily
from data.indicators import add_all_strategy_indicators
from engine.risk import calculate_position_size
from engine.costs import calculate_costs
from engine.signals import STRATEGY_REGISTRY
from engine.backtest_metrics import compute_all_metrics

HISTORY_BUFFER_DAYS = 365  # warms up SMA200/EMA200/ADX etc. before `start`

# Daily-bar strategies only — ORB_BRK and BB_MEANREV are intraday (need 15-min bars
# with concepts like an opening range that don't exist on a daily bar) and are
# explicitly out of scope per the spec, even though both are valid keys in
# engine.signals.STRATEGY_REGISTRY for live trading.
SUPPORTED_STRATEGIES = {"RSI2_OVN", "MOM_CONT", "TREND_EMA", "DONCHIAN_BRK", "SUPERTREND"}

# MOM_CONT's entry is confirmed on the bar AFTER the signal (gap-check at that bar's open) —
# every other in-scope strategy enters same-bar at that bar's close.
NEXT_OPEN_ENTRY_STRATEGIES = {"MOM_CONT"}

# (strategy_id, exit_reason) pairs that fill at the CURRENT bar's OPEN rather than close.
# See "Key design decisions" #1 in the plan doc — only RSI2_OVN's "EOD" (next_open) reason.
# NOTE for future strategies: this is a hand-maintained set, not derived from each
# strategy's own exit_timing param — if a new strategy declares exit_timing="next_open"
# (or any other non-"close" value) for some exit reason, it must be added here explicitly,
# or that exit will silently fill at close instead of open. No runtime check enforces this.
OPEN_FILL_EXIT_REASONS = {("RSI2_OVN", "EOD")}


def run_backtest(
    symbol: str,
    strategy_id: str,
    start: str,
    end: str,
    params: dict | None = None,
    starting_capital: float = 100_000.0,
    market: str = "INDIA",
    segment: str = "equity_intraday",
    db=None,
    sweep_label: str | None = None,
) -> dict:
    """
    Fetch real history and run one symbol/strategy backtest over [start, end].
    Default starting_capital is a hypothetical Rs 1,00,000, not the real Rs 10,000
    seed — position-sizing math against real NSE prices gets noisy with too little
    capital, and a backtest tests the *strategy*, not the literal current account size.
    """
    if strategy_id not in SUPPORTED_STRATEGIES:
        raise ValueError(
            f"strategy_id must be one of {sorted(SUPPORTED_STRATEGIES)} (got {strategy_id!r}) — "
            "ORB_BRK/BB_MEANREV are intraday and out of scope for this daily-bar backtester."
        )

    fetch_start = (pd.Timestamp(start) - pd.Timedelta(days=HISTORY_BUFFER_DAYS)).strftime("%Y-%m-%d")
    df = fetch_india_daily(symbol, start=fetch_start, end=end)
    if df.empty:
        raise ValueError(f"No data returned for {symbol} between {fetch_start} and {end}")
    df = add_all_strategy_indicators(df)

    result = _simulate_trades(
        df, symbol, strategy_id, start, end, params=params,
        starting_capital=starting_capital, market=market, segment=segment,
    )
    result["metrics"] = compute_all_metrics(result["trades"], result["equity_curve"])
    result["run_id"] = str(uuid.uuid4())
    result["sweep_label"] = sweep_label
    result["symbol"] = symbol
    result["strategy_id"] = strategy_id
    result["start"] = start
    result["end"] = end
    result["market"] = market

    if db is not None:
        _persist_run(db, result, params)

    logger.info(
        f"Backtest {symbol}/{strategy_id} [{start}..{end}]: "
        f"{result['metrics']['total_trades']} trades, "
        f"win_rate={result['metrics']['win_rate']:.1%}, "
        f"profit_factor={result['metrics']['profit_factor']:.2f}"
    )
    return result


def _simulate_trades(
    df: pd.DataFrame,
    symbol: str,
    strategy_id: str,
    start: str,
    end: str,
    params: dict | None = None,
    starting_capital: float = 100_000.0,
    market: str = "INDIA",
    segment: str = "equity_intraday",
) -> dict:
    """
    The actual walk-forward loop, separated from run_backtest() so tests can pass an
    already-fetched, already-indicator-enriched synthetic DataFrame directly — no
    monkeypatching yfinance, no network calls.

    Critical invariant: truncates to bars on/before `end` FIRST, before anything else,
    so there is no path by which a later step could see a future bar.
    """
    if strategy_id not in SUPPORTED_STRATEGIES:
        raise ValueError(
            f"strategy_id must be one of {sorted(SUPPORTED_STRATEGIES)} (got {strategy_id!r}) — "
            "ORB_BRK/BB_MEANREV are intraday and out of scope for this daily-bar backtester."
        )

    df = df[df.index <= pd.Timestamp(end)]
    strategy = STRATEGY_REGISTRY[strategy_id](params=params, market=market)

    sim_start_idx = df.index.searchsorted(pd.Timestamp(start))
    if sim_start_idx >= len(df):
        raise ValueError(f"No bars on/after {start} for {symbol}")

    cash = starting_capital
    open_trade: dict | None = None
    pending_mom_cont_signal: dict | None = None
    closed_trades: list[dict] = []
    equity_curve: list[float] = []

    for i in range(sim_start_idx, len(df)):
        bar = df.iloc[i]
        bar_date = df.index[i].to_pydatetime()
        current_bar = bar.to_dict()
        current_bar["close"] = float(bar["close"])

        # --- 1. Exit check for an existing position (never on its own entry bar) ---
        if open_trade is not None and i > open_trade["entry_bar_index"]:
            hold_days = i - open_trade["entry_bar_index"]
            trade_state = {
                "entry_price": open_trade["entry_price"],
                "stop_loss_price": open_trade["stop_loss_price"],
                "hold_days": hold_days,
                "exit_timing": strategy.params.get("exit_timing", "close"),
            }
            should_exit, exit_reason = strategy.should_exit(trade_state, current_bar)
            if should_exit:
                fill_price = (
                    float(bar["open"]) if (strategy_id, exit_reason) in OPEN_FILL_EXIT_REASONS
                    else float(bar["close"])
                )
                closed = _close_trade(open_trade, bar_date, fill_price, exit_reason, market, segment)
                cash += fill_price * open_trade["quantity"] - closed["total_costs"]
                closed_trades.append(closed)
                open_trade = None

        # --- 2. MOM_CONT: resolve yesterday's deferred signal at today's open ---
        if strategy_id in NEXT_OPEN_ENTRY_STRATEGIES and pending_mom_cont_signal is not None:
            confirmed = strategy.check_gap_and_confirm(pending_mom_cont_signal, open_price=float(bar["open"]))
            pending_mom_cont_signal = None
            if confirmed is not None and open_trade is None:
                quantity = calculate_position_size(cash, confirmed["entry_price"], confirmed["stop_price"])
                if quantity > 0:
                    cash -= confirmed["entry_price"] * quantity
                    open_trade = {
                        "entry_bar_index": i, "entry_date": bar_date, "symbol": symbol,
                        "strategy_id": strategy_id, "entry_price": confirmed["entry_price"],
                        "stop_loss_price": confirmed["stop_price"], "target_price": confirmed["target_price"],
                        "quantity": quantity, "signal_reason": confirmed["signal_reason"],
                    }
                    # MOM_CONT round-trips same-day on daily bars — no finer granularity
                    # exists to check intraday, so its "eod" exit_timing means *this* bar's close.
                    eod_bar = dict(current_bar)
                    eod_bar["is_eod"] = True
                    trade_state = {
                        "entry_price": open_trade["entry_price"],
                        "stop_loss_price": open_trade["stop_loss_price"],
                        "hold_days": 0, "exit_timing": "eod",
                    }
                    should_exit, exit_reason = strategy.should_exit(trade_state, eod_bar)
                    if should_exit:
                        fill_price = float(bar["close"])
                        closed = _close_trade(open_trade, bar_date, fill_price, exit_reason, market, segment)
                        cash += fill_price * open_trade["quantity"] - closed["total_costs"]
                        closed_trades.append(closed)
                        open_trade = None

        # --- 3. New entry check (generic path) — only if currently flat ---
        if open_trade is None and strategy_id not in NEXT_OPEN_ENTRY_STRATEGIES:
            signal = strategy.generate_signal(symbol, df.iloc[: i + 1])
            if signal is not None:
                quantity = calculate_position_size(cash, signal["entry_price"], signal["stop_price"])
                if quantity > 0:
                    cash -= signal["entry_price"] * quantity
                    open_trade = {
                        "entry_bar_index": i, "entry_date": bar_date, "symbol": symbol,
                        "strategy_id": strategy_id, "entry_price": signal["entry_price"],
                        "stop_loss_price": signal["stop_price"], "target_price": signal["target_price"],
                        "quantity": quantity, "signal_reason": signal["signal_reason"],
                    }
        elif open_trade is None and strategy_id in NEXT_OPEN_ENTRY_STRATEGIES:
            signal = strategy.generate_signal(symbol, df.iloc[: i + 1])
            if signal is not None:
                pending_mom_cont_signal = signal

        # --- 4. Mark-to-market equity for this bar ---
        if open_trade is not None:
            equity_curve.append(cash + open_trade["quantity"] * float(bar["close"]))
        else:
            equity_curve.append(cash)

    # --- End of range: force-close anything still open ---
    if open_trade is not None:
        last_bar = df.iloc[-1]
        last_date = df.index[-1].to_pydatetime()
        fill_price = float(last_bar["close"])
        closed = _close_trade(open_trade, last_date, fill_price, "BACKTEST_END", market, segment)
        cash += fill_price * open_trade["quantity"] - closed["total_costs"]
        closed_trades.append(closed)
        if equity_curve:
            equity_curve[-1] = cash

    return {
        "trades": closed_trades,
        "equity_curve": equity_curve,
        "starting_capital": starting_capital,
        "ending_capital": equity_curve[-1] if equity_curve else starting_capital,
    }


def _close_trade(open_trade: dict, exit_date, exit_price: float, exit_reason: str,
                 market: str, segment: str) -> dict:
    """Net P&L exactly as database/trade_log.py::close_trade computes it, but via one
    single calculate_costs() call covering both legs together — see "Key design
    decisions" #3 in the plan doc for why that's safe (and more direct) in a backtest,
    where both prices are already known when a trade closes."""
    entry_price = open_trade["entry_price"]
    quantity = open_trade["quantity"]
    costs = calculate_costs(market, buy_price=entry_price, sell_price=exit_price,
                            quantity=quantity, segment=segment)
    gross_pnl = (exit_price - entry_price) * quantity
    total_costs = costs["total_cost"]
    net_pnl = gross_pnl - total_costs
    net_pnl_pct = net_pnl / (entry_price * quantity) if entry_price and quantity else 0.0
    stop_loss_price = open_trade["stop_loss_price"]
    actual_rr_achieved = (
        round(net_pnl / abs((stop_loss_price - entry_price) * quantity), 4)
        if stop_loss_price and stop_loss_price != entry_price else None
    )
    return {
        **open_trade,
        "exit_date": exit_date,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "gross_pnl": round(gross_pnl, 4),
        "total_costs": round(total_costs, 4),
        "net_pnl": round(net_pnl, 4),
        "net_pnl_pct": round(net_pnl_pct, 6),
        "outcome": "WIN" if net_pnl > 0 else "LOSS" if net_pnl < 0 else "BREAKEVEN",
        "actual_rr_achieved": actual_rr_achieved,
    }


def _persist_run(db, result: dict, params: dict | None) -> None:
    from database.models import BacktestRun, BacktestTrade

    metrics = result["metrics"]
    run = BacktestRun(
        sweep_label=result.get("sweep_label"),
        symbol=result["symbol"],
        strategy_id=result["strategy_id"],
        market=result["market"],
        params_json=json.dumps(params or {}),
        start_date=result["start"],
        end_date=result["end"],
        starting_capital=result["starting_capital"],
        ending_capital=result["ending_capital"],
        total_trades=metrics["total_trades"],
        win_rate=metrics["win_rate"],
        profit_factor=metrics["profit_factor"],
        sharpe_ratio=metrics["sharpe_ratio"],
        max_drawdown_pct=metrics["max_drawdown_pct"],
        avg_rr_achieved=metrics["avg_rr_achieved"],
        total_net_pnl=metrics["total_net_pnl"],
        total_costs=metrics["total_costs"],
        var_95=metrics["var_95"],
        var_99=metrics["var_99"],
        cvar_95=metrics["cvar_95"],
        cvar_99=metrics["cvar_99"],
    )
    db.add(run)
    db.flush()
    for t in result["trades"]:
        db.add(BacktestTrade(
            run_id=run.run_id, symbol=t["symbol"], strategy_id=t["strategy_id"],
            entry_date=t["entry_date"].isoformat(), exit_date=t["exit_date"].isoformat(),
            entry_price=t["entry_price"], exit_price=t["exit_price"],
            stop_loss_price=t["stop_loss_price"], target_price=t.get("target_price"),
            quantity=t["quantity"], gross_pnl=t["gross_pnl"], total_costs=t["total_costs"],
            net_pnl=t["net_pnl"], net_pnl_pct=t["net_pnl_pct"],
            actual_rr_achieved=t["actual_rr_achieved"], outcome=t["outcome"],
            exit_reason=t["exit_reason"], signal_reason=t.get("signal_reason"),
        ))
    db.commit()


def run_sweep(
    symbol: str,
    strategy_id: str,
    start: str,
    end: str,
    param_grid: dict[str, list],
    market: str = "INDIA",
    segment: str = "equity_intraday",
    starting_capital: float = 100_000.0,
    db=None,
) -> list[dict]:
    """Cartesian product over param_grid, one run per combination, all tagged with a
    shared sweep_label so results are easy to group/rank later."""
    sweep_label = f"sweep-{symbol}-{strategy_id}-{uuid.uuid4().hex[:8]}"
    keys = list(param_grid.keys())
    results = []
    for combo in itertools.product(*param_grid.values()):
        params = dict(zip(keys, combo))
        result = run_backtest(
            symbol, strategy_id, start, end, params=params,
            starting_capital=starting_capital, market=market, segment=segment,
            db=db, sweep_label=sweep_label,
        )
        results.append(result)
    return results


def run_backtest_universe(
    symbols: list[str],
    strategy_id: str,
    start: str,
    end: str,
    market: str = "INDIA",
    segment: str = "equity_intraday",
    starting_capital: float = 100_000.0,
    db=None,
) -> list[dict]:
    """Loops one strategy across many symbols — no shared capital/position limits,
    that's the explicitly-deferred portfolio layer (see plan doc decision #2).
    Catches any exception per-symbol (not just data-fetch failures — a transient
    yfinance/network error is the realistic case, but this is deliberately broad)
    and logs + skips rather than aborting the whole run."""
    results = []
    for symbol in symbols:
        try:
            result = run_backtest(
                symbol, strategy_id, start, end, starting_capital=starting_capital,
                market=market, segment=segment, db=db,
            )
            results.append(result)
        except Exception as exc:
            logger.warning(f"Skipping {symbol}: {exc}")
            continue
    return results


def _cli() -> None:
    import argparse

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from config.settings import DB_PATH
    from database.models import Base

    parser = argparse.ArgumentParser(description="Run a KAIROS strategy backtest.")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--strategy", required=True, choices=sorted(SUPPORTED_STRATEGIES))
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--capital", type=float, default=100_000.0)
    parser.add_argument("--market", default="INDIA")
    parser.add_argument("--segment", default="equity_intraday")
    args = parser.parse_args()

    engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    try:
        result = run_backtest(
            args.symbol, args.strategy, args.start, args.end,
            starting_capital=args.capital, market=args.market, segment=args.segment, db=db,
        )
    except Exception as exc:
        print(f"Error: {exc}")
        raise SystemExit(1)

    print(f"\n{args.symbol} / {args.strategy}  [{args.start} .. {args.end}]")
    print(f"Starting capital: {result['starting_capital']:,.2f}")
    print(f"Ending capital:   {result['ending_capital']:,.2f}")
    for key, value in result["metrics"].items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    _cli()
