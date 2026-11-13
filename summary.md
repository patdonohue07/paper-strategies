# C125-FWD options forward paper score
Updated 2026-11-13 15:40 ET. Log only: no orders. Real Alpaca indicative quotes.

## A: SPY 10-delta put-write, 60 DTE, MA200 filter, TP 50% (F20_02442)
- No settled trades yet; open 1

## B: rich-IV short 25d strangles, 45 DTE (F07_02095)
- No settled trades yet; open 0

## S1: seeded-history short 25d strangles (C157)
- No settled trades yet; open 0

## S2: seeded-history iron condors, 10d wings (C157)
- No settled trades yet; open 0

Decision: pass if mean net > 0 and t >= 2 at the target count. Backtest (modeled) holdout: A +27bp/trade t 14.6; B +421bp/trade t 4.1.
