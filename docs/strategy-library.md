# KAIROS Strategy Library — Research

A menu of additional proven strategies beyond the current 5, organized by
market. "Tried and tested" here means a real track record — either decades of
practitioner use or a well-documented academic anomaly — not a trendy
indicator combo with no history. Each entry sketches concrete rules (period,
threshold) at the level of detail KAIROS's existing strategies use, so this is
buildable, not just a list of names.

## Currently built (for context)

| ID | Type | Market fit |
|---|---|---|
| `RSI2_OVN` | Overnight mean reversion | India (any liquid equity) |
| `ORB_BRK` | Opening-range breakout | India (session-open markets) |
| `MOM_CONT` | Next-day momentum continuation | India (any liquid equity) |
| `TREND_EMA` | 50/200 EMA golden/death cross | India (any liquid equity) |
| `BB_MEANREV` | Intraday Bollinger fade | India (any liquid equity) |

All 5 are architecture-agnostic — none actually depend on India-specific
mechanics, they've just only been *applied* to NSE stocks so far. Every
strategy below is written the same way: works on any single instrument with
OHLCV history, fits the existing `generate_signal`/`should_exit` interface.

---

## Cross-market candidates (India, US, and FX — same rules, just point them at a different universe)

These are the highest-value additions: build once, deploy across all three
markets immediately.

### Donchian/Turtle Channel Breakout
The original Turtle Traders system (Richard Dennis, 1983) — decades of real
track record, the most battle-tested trend system that exists. Buy when price
closes above the highest high of the last N bars (default N=20), stop at the
lowest low of the last 10 bars, exit on a close below the 10-bar low (or a
trailing ATR stop). Works on trending instruments generally; weak in choppy
ranges, same failure mode as `TREND_EMA`. Genuinely complementary to
`TREND_EMA` rather than redundant — Donchian reacts faster to fresh breakouts,
EMA cross is slower/smoother.

### Supertrend
ATR-based trend-following band (`SuperTrend = HL2 ± multiplier × ATR`,
typically period=10, multiplier=3). Flip long/short when price crosses the
band. Less academically rigorous than Donchian but has an enormous pract
track record specifically among NSE/India intraday and swing traders — it's
the single most-used indicator in Indian retail algo trading. Good fit
alongside `TREND_EMA` for shorter-timeframe trend signals.

### VWAP Reversion (the spec's still-unbuilt "VWAP Reclaim")
Intraday: when price deviates more than ~1.5 standard deviations below VWAP
on elevated volume, buy expecting reversion back toward VWAP; symmetric short
on the upside. This is standard institutional execution-desk logic adapted
into a signal — every major prop/market-making desk watches VWAP deviation.
Complements `BB_MEANREV` (different anchor — VWAP is volume-weighted,
Bollinger is price-only) rather than duplicating it.

### MACD Crossover
Gerald Appel, 1970s — one of the oldest momentum indicators still in
universal use. Standard 12/26/9 EMA crossover; buy on MACD line crossing
above signal line with histogram turning positive. Simple, well-understood,
good as a *confirmation* filter for other strategies as much as a standalone
signal.

### Bollinger Squeeze Breakout
The breakout counterpart to `BB_MEANREV`'s fade approach — John Bollinger
documented both uses himself. When band width (upper−lower)/middle compresses
to a multi-month low (a "squeeze"), volatility is coiling; trade the
direction of the eventual breakout candle with volume confirmation. Distinct
regime from `BB_MEANREV` (squeeze precedes a breakout; `BB_MEANREV` fades
moves that already happened), so the two don't compete for the same setups.

---

## India-specific additions

### Gap and Go (the spec's still-unbuilt placeholder)
Stock gaps up >2% at open on above-average pre-market/early volume, holds
above the opening 5-minute range low — enter long on the hold, stop below
that low. Distinct from `MOM_CONT` (which trades the *next* day after a big
move) — this trades the *same-day* gap directly.

### Dual EMA Crossover (the spec's still-unbuilt placeholder — faster than TREND_EMA)
9/21 EMA cross instead of 50/200. Same mechanic as `TREND_EMA`, much shorter
holding period (days, not weeks/months) — fills the gap between `TREND_EMA`'s
slow trend signal and the intraday strategies.

### 52-Week High Momentum
Buy stocks making a new 52-week high on volume ≥1.5× average, with RSI(14)
in the 55–75 range (trending but not yet blown-off-top exhausted). One of the
most consistently replicated factors in momentum research (Jegadeesh &
Titman, 1993, and dozens of follow-ups) — distinct from `MOM_CONT`'s
next-day-after-a-spike logic since this is about proximity to a structural
price level, not a recent return threshold.

---

## US-specific additions

### Post-Earnings Announcement Drift (PEAD)
Ball & Brown, 1968 — one of the oldest documented anomalies in finance, still
holds up. Stock beats earnings estimates by a meaningful margin → price drifts
in the same direction for the following 60–90 days, markets underreact to the
surprise. Needs an earnings-calendar/estimates data source KAIROS doesn't have
yet (yfinance's earnings data is thin) — flagging as a real strategy worth
building, but it has a data-sourcing dependency the others don't.

### Pre-Market Gap Fade (large-cap specific)
US large-caps that gap >3% on no fresh news by market open tend to partially
mean-revert in the first 30 minutes — the mirror image of Gap and Go, but
fade rather than follow, and specifically tuned to large-cap US behavior
(this doesn't transfer well to India mid/small-caps, which gap-and-continue
far more often due to lower liquidity).

---

## FX-specific additions

### London Breakout
The direct FX analog to `ORB_BRK`. The Asian session (roughly 00:00–07:00
GMT) trades in a tight range; when London opens (07:00 GMT) and price breaks
that range with momentum, trade the breakout direction, stop at the opposite
side of the Asian range. One of the most-cited FX day-trading setups,
specifically because FX has genuine session-based liquidity/volatility
structure that equities don't (no single "exchange open").

### Carry Trade
Long the higher-yielding currency / short the lower-yielding one in a pair,
collecting the interest-rate differential, with a trend filter (only carry
when the pair is also trending in the carry direction, to avoid the classic
"picking up pennies in front of a steamroller" crash risk during
deleveraging events like 2008 or the 2015 CHF unpeg). Extensively documented
in FX literature as a real, persistent risk premium — but genuinely
different risk profile from everything else in KAIROS (slow-moving carry P&L
punctuated by sharp crash risk), worth building deliberately, not by analogy
to an equity strategy.

---

## Explicitly excluded — don't fit KAIROS's architecture

Flagging these so they don't get silently revisited and rebuilt into
something that doesn't actually fit:

- **Pairs trading / statistical arbitrage** — needs a *pair* of correlated
  instruments and a cointegration/spread model, not a single-symbol
  `generate_signal(symbol, df)` call. Would need a genuinely different
  engine shape (two-symbol input, spread-based entry/exit), not a drop-in
  `BaseStrategy` subclass.
- **Cross-sectional / 12-1 month momentum** — ranks *all* stocks in a
  universe against each other and trades the top/bottom decile. KAIROS's
  screener already does something adjacent (scoring the universe), but this
  needs portfolio-level capital allocation across many simultaneous
  positions sized by rank, not a per-symbol signal. Same shape problem as
  pairs trading — fits naturally once the deferred portfolio-level
  simulation layer (see the backtesting engine design) exists, not before.

---

## Recommended build order

If picking up one or two next: **Donchian Breakout** and **Supertrend** —
both cross-market (build once, use everywhere), both have the longest real
track records of anything on this list, and both are genuinely complementary
to what's already running rather than overlapping it.
