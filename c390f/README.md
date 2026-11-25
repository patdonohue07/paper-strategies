# C390F: forward paper log of the C387 v3.2 prop books (no orders, no account)

Logs the books from research_lab C387 "FINAL BOOKS v3.2" (prereg Amendment 7) on simulated prop accounts, one path per account. The
frozen setups are in `book.json` (written by research_lab `code/c390_freeze.py`). The exact rules are in the docstring of
`book_logger.py`, which loads `c348f/book_logger.py` unchanged for the data feeds, the US CFD leg, the BTC/ETH trend ensemble and the
crypto CFD and perp paths.

| Book | Accounts | Entries | What it is |
|---|---|---|---|
| AUTO (primary) | 29 | 18 | Fully automated, risk-capped (one account per firm, then copies while p10 >= -$12K and P(loss) <= 15%) |
| AUTO_MAX | 54 | 16 | Fully automated, every copy each firm allows |
| FULL | 41 | 25 | Capped, also using accounts that must be traded by hand in the US |

There are 31 distinct entries. Copies of one entry are identical paths, so each entry is simulated once and multiplied by its count.

**Streams**
- **Futures accounts** (Topstep, FundedNext Futures, FTMO Futures, LucidFlex, MFFU, ETF, DayTraders, BrightCore, BluSky; FULL adds
  Alpha Futures and Aqua Futures):
  - The US index swing rule (C320 8-vote score, |score| >= 5 or >= 4) in whole CME micros (MES, MNQ, M2K, MYM). Sized to the entry's
    risk at the 1.5 x ATR stop.
  - $0.70 per micro per side plus one tick. Session-chained setups pay a round trip on every held day.
  - Intraday lows come from Yahoo 5-minute ES=F / NQ=F / RTY=F bars.
- **CFD accounts:** FTMO 200K (gap rule). FULL adds CTI and FundedNext.
- **Mix accounts** (US leg + crypto at perp costs): MyFundedPerps, Velotrade.
- **Perp accounts:** HyroTrader. FULL adds CFT 2-Phase and Bitfunded.

**Engine:** research c341 `sim_year` (fixed version: an account out of attempts stops) on one path. A breach starts a new attempt (new
fee) the next day, at most 3 attempts. Monthly fees, evaluation expiry and every payout rule follow the plan in `book.json`.

**Data**, all free and public (user agent `research-client/1.0`):
- Yahoo daily bars for ^GSPC ^NDX ^RUT ^DJI ^VIX BTC-USD ETH-USD.
- Yahoo 5-minute RTH bars of ES=F NQ=F RTY=F.
- data.binance.vision daily 1h klines and 1m premium-index files.

**Schedule:** runs daily at 09:40 and 21:30 ET via `ci/scheduler.py` (workflow `c390f-book.yml`). Each run logs every completed UTC day
whose data are complete. Window 2026-12-01 .. 2027-11-30 (365 days); every account starts its first attempt on 2026-12-01. Review
2027-12-01. The decision rules are in research_lab `claude/c390f-preregistration.md`.

**State** is on branch `state-c390f`:
- `streams.csv`: per day, each entry's stream P&L and intraday low (FundedNext's funded stream too), the futures K5 / K4 lows per
  $1,000 risk, crypto positions, the funding estimate and events.
- `accounts.csv`: per day per entry: attempt, stage, day P&L, balance, cash to date, events.
- `books.csv`: per day, net cash to date of AUTO, AUTO_MAX and FULL (copies counted).
- `state.json`.

**Verification** (2026-11-25, before the window; research_lab `reports/c390/verify_*.log`):
- **Account engine** (`c390_verify_engine.py`): exact against research `sim_year`. $0.00 difference on all 31 entries x 2,005
  account-years each (400 bootstrap paths x 5 windows + 5 actual replays). `book.json` rules, sizes and stops equal the research
  setups.
- **Streams** (`c390_verify_streams.py`, live Yahoo + Binance data):
  - US vote scores are identical on all 5,020 index-days of 2021-11..2026-10.
  - Integer-micro futures P&L and active days are identical ($0.00) for all 15 futures specs over 2021-11-01..2026-10-30.
  - Futures intraday lows over 2026-09-18..10-30 are within $4.64 per $1,000 risk. The exception is 2026-10-13 at K = 4, where the
    research 1-minute panel is missing the 2026-10-12 session and measured NQ from the 10-09 close. The log's -$584 is right; research
    had -$990.
  - CFD, mix and perp streams are within $1.71 a day, except 2026-10-28/29. Research filled a Binance gap there from Yahoo (as in
    C348F).
- **Dry runs** of the live path in scratch state:
  - 2026-11-18..24: all files written. The FTMO 200K and HyroTrader streams equal C348F's logged 11-23 and 11-24 values.
  - 2026-10-01..11-24: futures personal stops, phase passes, activation fees, a funded breach and a new attempt all fired.
  - Python 3.9 and 3.12. These days are not part of the window.

**Disclosed differences from research:**
- **Futures prices:** cash index closes stand in for futures prices, as in research. Basis, rolls and settlement-vs-close timing are
  not modelled. The review compares against Yahoo futures closes.
- **Data sources:** 5-minute bars instead of research's 1-minute panel for the futures lows. Funding is estimated from the premium
  index, and assumed at 0.03%/day when files stay missing for more than 3 days (as C348F).
- **Not modelled:** Topstep's call-up to a Live account (which closes all funded accounts), Lucid's live transition, and firm
  discretion.
