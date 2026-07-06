<div align="center">

# KAIROS

**An autonomous, signal-driven algorithmic trading system.**

11 rule-based strategies, a daily 4-factor composite screener, and a real backtesting engine, running across India, US, and FX. Paper-first, always.

`Streamlit` · `SQLAlchemy` · `pandas / pandas-ta` · `APScheduler` · `yfinance` · `pytest`

**[Landing page](docs/index.html)** · **[Architecture](docs/ARCHITECTURE.md)** · **[Strategy research](docs/strategy-library.md)**

</div>

---

## What it is

KAIROS generates trading signals with the same discipline an investment
bank's systematic desk would use: no sentiment, no news, no discretion.
A dashboard makes every step watchable: which strategy fired, why, what it
did about it, and how the resulting portfolio is actually performing.

> **All trading today is simulated (paper).** No live order has ever been
> placed. See [Known limitations](#known-limitations) and
> [Disclaimers](#disclaimers).

Every strategy implements one interface (`generate_signal(symbol, df) ->
signal | None` and `should_exit(trade, current_bar) -> (bool, reason)`).
This lets the screener assign any qualifying stock to whichever strategy
fits its current volatility/trend regime, and lets the backtester replay
the *exact* code live trading uses, not an approximation of it.

---

## The dashboard (8 pages)

| # | Page | What it answers |
|---|---|---|
| 01 | **Overview** | "How is the portfolio doing right now?": hero KPIs, equity curve, monthly returns grid |
| 02 | **Live Trades** | "What's open, and which strategy opened it?": per-strategy control cards, open positions |
| 03 | **Logbook** | "What actually happened on trade N?": full trade journal, editable conviction/lessons |
| 04 | **Strategies** | "Which of the 11 strategies is active, and can I try one manually?" |
| 05 | **Markets** | "Which names rank best right now?": India/US/FX screener tabs, candlestick deep-dive |
| 06 | **Analysis** | "How much am I risking?": portfolio-level VaR/CVaR (95%/99%, 1-day + 10-day) |
| 07 | **Backtests** | "Would this strategy have worked historically?": filterable run history + full metrics |
| 08 | **Settings** | Risk parameter overrides, broker key storage (unused until live trading), market toggle |

---

## The strategy roster (11 strategies)

| ID | Type | Rule (one line) | Market fit |
|---|---|---|---|
| `RSI2_OVN` | Mean reversion | RSI(2)<15 above SMA200, buy close, sell next open | Cross-market |
| `ORB_BRK` | Breakout | 30-min opening-range breakout, 1.5× volume, 2:1 R:R | India/US |
| `MOM_CONT` | Momentum | +3% on 2× volume → next-day entry if gap-up <2% | India/US |
| `TREND_EMA` | Trend | 50/200 EMA golden/death cross, ADX-filtered | Cross-market |
| `BB_MEANREV` | Mean reversion | Intraday 15-min Bollinger fade below lower band | Cross-market |
| `DONCHIAN_BRK` | Trend | 20-bar high entry / 10-bar low trailing exit (Turtles, 1983) | Cross-market |
| `MACD_CROSS` | Momentum | 12/26/9 EMA crossover with SMA50 trend filter | Cross-market |
| `SUPERTREND` | Trend | ATR-band trend flip | Cross-market |
| `DUAL_EMA` | Trend | 9/20 EMA cross, fires 4–6 weeks before `TREND_EMA` | Cross-market |
| `HIGH_52W` | Momentum | New 52-week closing high on ≥1.5× volume, ADX≥20 | Cross-market |
| `GAP_GO` | Breakout | 2–5% gap-up, bullish first 15-min candle, 2× volume | India/US |

"Cross-market" strategies run on India, US, and FX identically, see
[docs/strategy-library.md](docs/strategy-library.md) for the full research
behind each one, including what's deliberately *not* built yet and why
(pairs trading, cross-sectional momentum, PEAD).

---

## Architecture

```
strategies/    Pluggable BaseStrategy subclasses, 11 today, zero UI imports
engine/        signals · screener · scheduler · executor · risk · backtest
data/          yfinance fetch layer + pandas_ta indicator wrappers
brokers/       paper.py (only broker implemented, no live client yet)
database/      SQLAlchemy models: Trade, Signal, PortfolioSnapshot, ...
dashboard/     Streamlit app (8 pages), reads the DB, never writes to it
```

**Core design rule:** `strategies/` and `engine/` import zero dashboard/UI
code, so each is independently readable and unit-tested. The dashboard runs
on a separate, `pandas-ta`-free Python interpreter from the engine. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full two-interpreter
split, the scheduler's per-market job table, and the data models.

```
KAIROS/
├── engine/                 signals.py, screener.py, scheduler.py,
│                           executor.py, risk.py, costs.py, backtest.py,
│                           backtest_metrics.py
├── strategies/              base.py + 11 BaseStrategy subclasses
├── data/                    market_data.py, indicators.py, universe.py
├── brokers/                 paper.py
├── database/                models.py + query helpers
├── dashboard/
│   ├── app.py                entry point
│   ├── pages/                 1_Overview.py … 9_Backtest_Results.py
│   ├── components/            header, sidebar, candlestick chart, engine_bridge
│   └── style.css              theme
├── config/                  settings.py, universes, risk overrides
├── tests/                    86 pytest functions
└── docs/                     index.html (landing page), ARCHITECTURE.md,
                              strategy-library.md
```

---

## Quick start

```bash
git clone https://github.com/chintan-jikkar/KAIROS.git
cd KAIROS
pip install -r requirements.txt

streamlit run dashboard/app.py --server.port 8501
# open http://localhost:8501
```

On macOS you can also double-click **`start_kairos.command`** to launch and
**`stop_kairos.command`** to stop.

**No API keys required for paper trading.** Market data comes from
yfinance (India via `.NS` suffix, US, and FX via `=X` pairs). No key, no
rate-limit tier. Broker keys (Zerodha/Alpaca/OANDA) are only needed once
live trading is built.

Two Python interpreters are involved. See
[docs/ARCHITECTURE.md §1](docs/ARCHITECTURE.md#1-the-big-picture) if you're
extending the engine (`kairos_env/`, Python 3.12, has `pandas-ta`) rather
than just running the dashboard (any Python ≥3.11 without `pandas-ta` is
fine).

### Markets

| Market | Universe | Automated daily screener |
|---|---|---|
| India (NSE) | Liquid large/mid-caps, `.NS` suffix | 08:45 IST |
| US | S&P-listed large-caps | 09:15 ET |
| FX | 8 major pairs, `=X` suffix | On-demand only (Markets page) |

---

## Tests

```bash
./kairos_env/bin/python3 -m pytest -q
```

86 tests cover strategy signal/exit logic, the factor-composite screener
and assignment cascade, backtest P&L accounting and tearsheet metrics
(Sharpe, Sortino, max drawdown, VaR/CVaR), and cost/risk calculations.

---

## Extending it

- **Add a strategy**: subclass `strategies/base.py::BaseStrategy`,
  implement `generate_signal`/`should_exit`, register it in
  `engine/signals.py::STRATEGY_REGISTRY` and the assignment cascade in
  `engine/screener.py::_assign_strategy`. The Strategies page and
  backtester pick it up automatically.
- **Add a market**: add a fetch function to `data/market_data.py`, a
  universe to `data/universe.py`, and a `run_<market>_screener` to
  `engine/screener.py`. Wire it into `dashboard/components/engine_bridge.py`'s
  `_SCREENER_MAP` for dashboard access.

---

## Known limitations

This reflects the current, honest state of the project, not hidden gaps:

- **No live broker integration exists yet.** Only `brokers/paper.py` is
  implemented. Zerodha/Alpaca/OANDA keys in `.env` are staged for a future
  phase, unused today.
- **Single-symbol backtests only**: no portfolio-level simulation across
  multiple concurrent positions with shared capital.
- **The factor screener covers momentum and low-volatility only**: no
  value/quality factors, since those need fundamentals data (P/E, ROE)
  KAIROS doesn't pull today.
- **FX isn't on the automated daily schedule**: the screener exists and
  runs on demand from the dashboard, but no scheduler job calls it yet.
- **All strategies are long-only.**

See [docs/ARCHITECTURE.md §6](docs/ARCHITECTURE.md#6-known-blindspots--roadmap)
for the full list.

---

## Disclaimers

KAIROS is a rule-based, purely technical trading system: no sentiment or
news inputs of any kind. Every signal is a model output, **not financial
advice**. **All trading today is simulated**: no live capital is at risk,
and no strategy moves to live trading until it clears the standing bar of
≥30 days and 50+ paper trades showing positive expectancy. **Backtested
performance is not indicative of future results.** Market data is sourced
from Yahoo Finance on a best-effort basis and may be delayed, incomplete, or
revised.
