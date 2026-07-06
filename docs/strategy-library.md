# KAIROS Strategy Library: Research

A menu of additional proven strategies beyond the current 11, organized by
market. "Tried and tested" here means a real track record: either decades of
practitioner use or a well-documented academic anomaly, not a trendy
indicator combo with no history. Each entry sketches concrete rules (period,
threshold) at the level of detail KAIROS's existing strategies use, so this is
buildable, not just a list of names.

## Currently built (for context)

| ID | Type | Market fit |
|---|---|---|
| `RSI2_OVN` | Overnight mean reversion | Cross-market (India/US/FX) |
| `ORB_BRK` | Opening-range breakout | India/US (needs a single exchange open) |
| `MOM_CONT` | Next-day momentum continuation | India/US (needs a single exchange open) |
| `TREND_EMA` | 50/200 EMA golden/death cross | Cross-market (India/US/FX) |
| `BB_MEANREV` | Intraday Bollinger fade | Cross-market (India/US/FX) |
| `DONCHIAN_BRK` | 20/10-bar Turtle channel breakout | Cross-market (India/US/FX) |
| `SUPERTREND` | ATR-band trend flip | Cross-market (India/US/FX) |
| `MACD_CROSS` | 12/26/9 momentum crossover | Cross-market (India/US/FX) |
| `DUAL_EMA` | 9/20 EMA cross (faster `TREND_EMA`) | Cross-market (India/US/FX) |
| `HIGH_52W` | 52-week high breakout on volume | Cross-market (India/US/FX) |
| `GAP_GO` | Intraday gap-and-continue | India/US (needs a single exchange open) |

All 11 are architecture-agnostic. The assignment cascade in
`engine/screener.py::_assign_strategy` is the same function regardless of
market; FX just omits `MOM_CONT`/`GAP_GO`/`ORB_BRK` from its rule set since
all three require a single exchange-open event that FX (a 24-hour market)
doesn't have. Every strategy below is written the same way: works on any
single instrument with OHLCV history, fits the existing
`generate_signal`/`should_exit` interface.

---

## Cross-market candidates (India, US, and FX; same rules, just point them at a different universe)

Donchian/Turtle Breakout, Supertrend, and MACD Crossover, all three
originally listed here, have since shipped as `DONCHIAN_BRK`, `SUPERTREND`,
and `MACD_CROSS`. Remaining candidates:

### VWAP Reversion (the spec's still-unbuilt "VWAP Reclaim")
Intraday: when price deviates more than ~1.5 standard deviations below VWAP
on elevated volume, buy expecting reversion back toward VWAP; symmetric short
on the upside. This is standard institutional execution-desk logic adapted
into a signal: every major prop/market-making desk watches VWAP deviation.
Complements `BB_MEANREV` (different anchor: VWAP is volume-weighted,
Bollinger is price-only) rather than duplicating it.

### Bollinger Squeeze Breakout
The breakout counterpart to `BB_MEANREV`'s fade approach; John Bollinger
documented both uses himself. When band width (upper−lower)/middle compresses
to a multi-month low (a "squeeze"), volatility is coiling; trade the
direction of the eventual breakout candle with volume confirmation. Distinct
regime from `BB_MEANREV` (squeeze precedes a breakout; `BB_MEANREV` fades
moves that already happened), so the two don't compete for the same setups.

---

## India-specific additions

Gap and Go, Dual EMA Crossover, and 52-Week High Momentum, all three
originally listed here, have since shipped as `GAP_GO`, `DUAL_EMA`, and
`HIGH_52W` (and turned out to be cross-market, not India-only: see the table
above). No India-specific candidates are currently queued; revisit if a new
one surfaces.

---

## US-specific additions

### Post-Earnings Announcement Drift (PEAD)
Ball & Brown (1968): one of the oldest documented anomalies in finance, still
holds up. Stock beats earnings estimates by a meaningful margin → price drifts
in the same direction for the following 60–90 days, markets underreact to the
surprise. Needs an earnings-calendar/estimates data source KAIROS doesn't have
yet (yfinance's earnings data is thin). Flagging as a real strategy worth
building, but it has a data-sourcing dependency the others don't.

### Pre-Market Gap Fade (large-cap specific)
US large-caps that gap >3% on no fresh news by market open tend to partially
mean-revert in the first 30 minutes: the mirror image of Gap and Go, but
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
in FX literature as a real, persistent risk premium; it carries a genuinely
different risk profile from everything else in KAIROS (slow-moving carry P&L
punctuated by sharp crash risk), worth building deliberately, not by analogy
to an equity strategy.

---

## Explicitly excluded: don't fit KAIROS's architecture

Flagging these so they don't get silently revisited and rebuilt into
something that doesn't actually fit:

- **Pairs trading / statistical arbitrage**: needs a *pair* of correlated
  instruments and a cointegration/spread model, not a single-symbol
  `generate_signal(symbol, df)` call. Would need a genuinely different
  engine shape (two-symbol input, spread-based entry/exit), not a drop-in
  `BaseStrategy` subclass.
- **Cross-sectional / 12-1 month momentum**: ranks *all* stocks in a
  universe against each other and trades the top/bottom decile. KAIROS's
  screener already does something adjacent (scoring the universe), but this
  needs portfolio-level capital allocation across many simultaneous
  positions sized by rank, not a per-symbol signal. Same shape problem as
  pairs trading; fits naturally once the deferred portfolio-level
  simulation layer (see the backtesting engine design) exists, not before.

---

## Recommended build order

If picking up one or two next: **VWAP Reversion** and **Bollinger Squeeze
Breakout**, both cross-market (build once, use everywhere), both
complementary to the existing `BB_MEANREV` rather than redundant with it,
and neither needs a new data source (unlike PEAD, which is blocked on
earnings-calendar data KAIROS doesn't pull today).
