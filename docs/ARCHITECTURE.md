# KAIROS — Architecture & Internals

This is the engineering companion to the [README](../README.md). It explains
how a signal becomes a paper trade, the process/interpreter split, the
scheduler's job table, the data models, and an honest list of blindspots.

---

## 1. The big picture

KAIROS is **two independent processes that never import each other directly**:

1. **The engine** (`engine/`, `strategies/`, `data/`, `brokers/`) — pure
   Python, no UI imports. Generates signals, runs backtests, computes risk
   metrics. Runs continuously via `engine/scheduler.py` on market days, or
   on demand via CLI (`python -m engine.backtest ...`).
2. **The dashboard** (`dashboard/`) — a read-only Streamlit app. It queries
   `kairos.db` directly for anything already computed (trades, signals,
   snapshots), and only reaches into the engine for on-demand work (like
   "re-run the screener now") through a subprocess bridge, never an import.

Both share one SQLite database (`database/kairos.db`) as the only channel
between them — the dashboard never writes to it.

### Why two Python interpreters, not one

| | Dashboard | Engine |
|---|---|---|
| Interpreter | bare `pyenv 3.11.15` | `kairos_env/` venv, Python 3.12 |
| Has `pandas-ta`? | No | Yes |
| Runs | `streamlit run dashboard/app.py` | `engine/scheduler.py`, CLI tools |

`pandas-ta`'s only installable PyPI releases require Python ≥3.12, and it's a
heavy import (pulls in a large indicator library) the dashboard has no need
for — the dashboard reads already-computed values from the database, it
doesn't compute indicators itself except for the candlestick chart's
overlays, which are done with plain pandas (`.ewm()`, `.rolling()`) instead
of `pandas_ta`, specifically to avoid needing the split for that one
component.

Anything the dashboard needs from the engine that *does* require
`pandas_ta` — currently, only "re-run the screener" — goes through
**`dashboard/components/engine_bridge.py`**, which shells out to
`ENGINE_PYTHON` (the venv interpreter) as a subprocess, passes a one-line
`-c` script, and reads back JSON from stdout:

```
dashboard process (bare 3.11)          kairos_env subprocess (3.12 + pandas-ta)
┌─────────────────────────┐    subprocess.run()   ┌──────────────────────────┐
│ engine_bridge.run_       │ ─────────────────────▶│ python -c "from engine.  │
│   screener(market="US")  │                       │  screener import         │
│                          │ ◀───────────────────── │  run_us_screener; ..."   │
└─────────────────────────┘   JSON over stdout      └──────────────────────────┘
```

**Any future dashboard feature that needs `engine.screener`/`engine.signals`/
`data.indicators` must go through this bridge, not a direct import** — a
direct import would crash the dashboard's bare interpreter.

---

## 2. Layer boundaries

```
strategies/            Pluggable BaseStrategy subclasses — 11 today
├── base.py             generate_signal(symbol, df) -> signal dict | None
│                        should_exit(trade, current_bar) -> (bool, reason)
├── rsi2_overnight.py, orb_breakout.py, momentum_continuation.py,
│   trend_ema.py, bb_meanrev.py, donchian_breakout.py, supertrend.py,
│   macd_crossover.py, dual_ema.py, high52w.py, gap_and_go.py

engine/
├── signals.py          STRATEGY_REGISTRY, run_eod_scan() — evaluates every
│                        strategy against a symbol's latest bar
├── screener.py          4-factor composite scoring + strategy assignment
│                        cascade (run_india_screener / run_us_screener /
│                        run_fx_screener, all call the same _assign_strategy)
├── scheduler.py         APScheduler jobs — the only long-running process
├── executor.py          Places paper orders via brokers/paper.py
├── risk.py              RISK_PARAMS, position sizing, circuit breakers
├── costs.py             Slippage/brokerage cost model
├── backtest.py           Replays generate_signal/should_exit/costs against
│                        history — the *same* code live trading uses
└── backtest_metrics.py   Win rate, Sharpe, Sortino, max drawdown, VaR/CVaR

data/
├── market_data.py        yfinance fetch (India/US daily+intraday, FX, indices)
├── indicators.py         pandas_ta wrappers (EMA, RSI, ADX, ATR, Donchian, ...)
└── universe.py           Stock/pair universes per market

brokers/
└── paper.py              The only broker implemented — simulated fills.
                         Zerodha/Alpaca/OANDA keys are staged in .env but
                         no live broker client exists yet.

database/
├── models.py             Trade, Signal, PortfolioSnapshot, WatchlistItem,
│                        BacktestRun, BacktestTrade, PendingSignal
├── portfolio.py, trade_log.py, watchlist.py   Query helpers

dashboard/
├── app.py                Entry point — redirects to pages/1_Overview.py
├── pages/                8 Streamlit pages (see README)
├── components/           Shared widgets (header, sidebar, candlestick
│                        chart, engine_bridge, manual_trade, ...)
└── style.css              Theme: glass-morphism cards, gold/cyan/emerald
                         accent system, Bebas Neue + Inter + IBM Plex Mono
```

**Core design rule:** `strategies/` and `engine/` import zero dashboard/UI
code — a strategy takes an OHLCV DataFrame and returns a signal dict, full
stop. That's what makes each one independently unit-tested (86 tests today)
and what lets the backtester replay *exactly* the same code path live
trading uses, rather than a parallel approximation.

---

## 3. The scheduler — one long-running process per market

`engine/scheduler.py` is started once (`ACTIVE_MARKET` env var pins it to
`INDIA` or `US` for that run) and holds all of a market's jobs. Times are
IST for India, ET for US:

| Time (India / US) | Job | What it does |
|---|---|---|
| 08:45 IST / 09:15 ET | `job_daily_screener` | Runs the 4-factor composite screener, updates the in-memory universe + `config/*_cache.json` |
| 09:30 IST / 09:46 ET | GAP_GO scan | First 15-min candle closes — fires entries for symbols the screener assigned to `GAP_GO` |
| 09:20 & 15:15 IST (India only) | `job_check_exits` | Calls `should_exit()` on every open position — this is what actually closes trades, not just opens them |
| 14:45 IST / — | EOD force-flatten | `ORB_BRK`/`BB_MEANREV` intraday positions must close before illiquid last minutes |
| Sunday 20:00 IST / 18:00 ET | `job_weekly_screener` | Full universe reset — fallback if the daily screener is ever skipped |
| Market holiday | guard checked, screener skipped | Universe refresh doesn't run on non-trading days |

**FX is not on this schedule.** `engine/screener.py::run_fx_screener` exists
and is fully wired into the dashboard (Markets page → FX tab → "Re-run
screener", via `engine_bridge`), but no scheduler job calls it yet — it's
on-demand only. `MOM_CONT`/`GAP_GO`/`ORB_BRK` are excluded from FX's
strategy-assignment rules entirely (see `strategy-library.md`) since all
three need a single exchange-open event FX, a 24-hour market, doesn't have.

---

## 4. Data models (`database/models.py`)

| Model | Purpose |
|---|---|
| `Trade` | Every paper (and eventually live) position — entry/exit price, strategy_id, market, outcome |
| `Signal` | Every signal generated, whether or not it was acted on |
| `PortfolioSnapshot` | Daily equity snapshot per market — feeds the equity curve and VaR/CVaR |
| `WatchlistItem` | User-added symbols outside the active screener universe |
| `BacktestRun` / `BacktestTrade` | One row per backtest invocation + its individual trades — separate from live `Trade`, no FK, same "plain string ID" convention as the rest of this file |
| `PendingSignal` | `MOM_CONT` signals flagged end-of-day, persisted so a scheduler restart doesn't lose next-morning entries |

---

## 5. Backtesting — replays production code, not an approximation

`engine/backtest.py::run_backtest` calls the *exact* `generate_signal` /
`should_exit` / `calculate_costs` functions live trading uses, bar by bar,
over historical data. Two deliberate simplifications versus live trading:

- Only `RSI2_OVN`'s `"EOD"` exit fills at that bar's open rather than close
  (`OPEN_FILL_EXIT_REASONS`).
- Costs are calculated once per trade (both legs together) since a backtest
  already knows both prices when a trade closes — live trading calculates
  each leg separately as it happens.

`ORB_BRK` and `BB_MEANREV` are excluded from backtesting
(`SUPPORTED_STRATEGIES` in `engine/backtest.py`) — both are intraday, and
yfinance only retains ~60 days of 15-minute history, not enough for a
meaningful backtest window. They still run live/paper normally.

VaR/CVaR (`engine/backtest_metrics.py`) use historical simulation — 95%/99%
confidence, both a direct 1-day figure and a √10-scaled 10-day figure — and
return `None` below a 20-observation floor rather than a fabricated `0.0`,
since a zero would read as "no risk" instead of "not enough data yet."

---

## 6. Known blindspots & roadmap

Documented so they don't surprise anyone reading the code:

- **No live broker integration exists.** `brokers/paper.py` is the only
  broker; Zerodha/Alpaca/OANDA keys in `.env` are staged for Phase 6/7 but
  unused today. `EXECUTION_MODE` defaults to `PAPER` and nothing overrides it.
- **Single-symbol backtests only.** `run_backtest` takes one symbol/one
  strategy per run — there's no portfolio-level simulation (shared capital
  across multiple concurrent positions), which is also why pairs
  trading/statistical arbitrage and cross-sectional momentum are explicitly
  out of scope (see `strategy-library.md`'s exclusions).
- **Factor screener covers momentum and low-volatility only.** Value/quality
  factors (P/E, ROE) would need a fundamentals data source KAIROS doesn't
  pull today — yfinance's momentum/volume data is sufficient for the current
  4-factor composite, not for those two.
- **FX screener isn't on the automated schedule** (see §3) — on-demand only.
- **No AI assistant feature is built.** Settings has masked key slots for
  Anthropic/Gemini/OpenAI keys, stored for a possible future in-dashboard
  helper — nothing reads them yet.
- **All strategies are long-only.** No short-side logic exists anywhere in
  `strategies/`.
