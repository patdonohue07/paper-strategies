# C349F: forward paper log of the C348F book plus the C349 stablecoin stream (no orders, no account)

A second book beside C348F, on the same simulated accounts, with the research_lab C358 capped C349-only setups. The exact rules are in
the docstring of `book_logger.py`, which loads `c348f/book_logger.py` unchanged for the US leg, the BTC/ETH trend ensemble, the data
feeds and the account engine. Setups:

| Account | C348F (frozen C347) | C349F (C358 capped, C349 only) |
|---|---|---|
| FundedNext Stellar 200K | US 1.5, crypto 1.25, -4% stop | US 1.5, crypto 1.0 + C349 0.5, -4% stop (funded stage: US 0.75, crypto off, as C348F) |
| FTMO 200K | US 1.5, crypto 1.25, -4% stop | US 1.25, crypto 0.75 + C349 0.75, -4% stop |
| CFT 2-Phase 200K | $1,500/unit, x1.25, -3% stop | $1,000/unit + C349 $750, x1.5, -4% stop |
| CFT 1-Step 100K | $1,500/unit, x1.25, -2% stop | $1,000/unit + C349 $750, x1.0, -1.5% stop |
| HyroTrader 200K | $1,500/unit, x1.25, -3% stop | $1,000/unit + C349 $750, x1.0, -3% stop |
| Bitfunded 100K | $1,500/unit, x1.25, -3% stop | $1,000/unit + C349 $750, x1.5, -3% stop |

Amounts are per $100K (200K accounts double them); "x" is the size multiplier in the challenge.

**C349 stream.** It is built from DefiLlama's total USD stablecoin supply:
- 24 variants: the z-score of the L-day change in log supply (L = 3, 7, 14, 28) against its 180-day history, using the value dated two
  days before the trading day, with long-only or long/short thresholds.
- Each month trades the variant with the best Sharpe over the previous 3 calendar months.
- Positions are on BTC and ETH, sized at 0.5 / 20-day volatility, with perp or CFD costs.

**No look-ahead from data revisions.** DefiLlama can revise past values, so the log never reads a value after the day it is used for:
- Every run fetches a fresh snapshot and freezes the signals for the next 4 UTC days. A later run before the day starts overwrites them,
  and every freeze is recorded in `freezes.csv`.
- Each month's pick uses the last snapshot fetched before that month started.
- A day with no frozen signal carries the previous one ("stale signal"). A month with no pre-month snapshot trades C349 flat.

Data, all free and public (user agent `research-client/1.0`):
- Yahoo and data.binance.vision, exactly as C348F.
- data.binance.vision monthly 1h klines and monthly funding-rate files, for the monthly pick.
- `stablecoins.llama.fi/stablecoincharts/all` (about 1.4 MB per run; that host has no robots.txt).

Runs daily at 09:40 and 21:30 ET via `ci/scheduler.py` (workflow `c349f-book.yml`). The 09:40 run is always before the next UTC day
starts. Runs before 2026-12-01 only freeze signals and the December pre-month snapshot; the first logged day is 2026-12-01.

State is on branch `state-c349f`:
- `streams.csv`: per day, each stream's P&L and intraday low per $100K. Also the ensemble and C349 positions, the C349 pick and sign,
  the C349 and ensemble components per $1,000 unit, the funding estimate and events.
- `accounts.csv`: as C348F.
- `freezes.csv`: every signal freeze, with the snapshot date, the supply value used and the four z-scores.
- `state.json`: frozen signals, pre-month snapshots, monthly picks and accounts.

Review after 12 months (2027-12-01). The decision rules are in research_lab `claude/c349f-preregistration.md`.

Verification (2026-11-23, before the window):
- `python3 c349f/book_logger.py --backtest 2026-08-01 2026-10-30 out.csv <research DefiLlama file>`, checked against research
  (c349_lib route, c358 X paths and per-account streams):
  - C349 picks for Aug, Sep and Oct 2026 are identical (L3_A_th1.0, L14_B_th0.0, L14_A_th0.0). Positions are identical on all 91 days.
  - The C349 CFD component is exact ($0.00). The C349 perp component is within $1.16 per $1,000 unit on every day (funding estimate vs
    actual): the Aug-Oct sum is $1,322.5 vs research $1,323.7.
  - Per-account streams over 2026-09-25..10-30 (the span of Yahoo's 5-minute bars):
    - CFD daily P&L is exact, and lows are within $7.
    - Perp streams are within $1.10.
    - The exceptions are 2026-10-28/29, where research filled the ensemble's Binance gap from Yahoo (as in C348F).
- The account engine on this table reproduces research `sim_year` replays exactly on 30 account-years (6 accounts x 5 windows,
  2021-26): $0.00 difference.
- End-to-end run of the live path over 2026-11-20..22 in a scratch state, with signals seeded from the research file:
  - Freezes, the pre-month snapshot, the November pick (L14_B_th0.0, the same as research), streams and accounts were all written.
  - 11-23 correctly waited for Binance.
  - These days are not part of the window.

Disclosed differences from the research method:
- The day's funding is the premium-index estimate, as in C348F. The monthly pick uses Binance's actual monthly funding files, or the
  estimate when a month's file is not out yet.
- Signals are frozen before each day. Research used one snapshot for all history.
- On 2026-12-01 the C349 position opens from flat and pays the entry cost. Research's route was continuous.
