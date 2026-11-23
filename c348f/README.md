# C348F: forward paper log of the C347 rule-compliant multi-account book (no orders, no account)

Replaces C334F (the older C333 FTMO-only book, retired 2026-11-23 before it logged a day). Frozen setups from research_lab
C344/C344b/C347; the exact rules are in the docstring of `book_logger.py`. In short:
- **CFD book** (FundedNext, FTMO): the US index swing rule at 1.5% risk per trade, plus the BTC/ETH 8-variant trend ensemble at 1.25%
  daily volatility, with a gap-aware personal daily stop at -4%. FTMO skips US entries on the last session before a weekend or holiday
  (gap rule). FundedNext's funded stage runs the US rule at 0.75% with crypto off (3% open-risk rule).
- **Crypto-perp book** (CFT, HyroTrader, Bitfunded): the same ensemble at $1,500 per unit with perp fees and Binance funding, 1.25x size in
  the challenge, and a -3% personal daily stop (-2% on CFT 1-Step). Bitfunded closes and reopens every 10th day.
- **Simulated accounts**: FundedNext Stellar 2-Step 200K, FTMO 2-Step 200K, CFT 2-Phase 200K, CFT 1-Step Classic 100K, HyroTrader
  One-Step 200K (= book B), plus Bitfunded 2-Step 100K (book B+). Each runs the research `sim_year` engine on one path: a breach starts a
  new attempt (and fee) the next day, at most 3 attempts.

Data, all free and public (user agent `research-client/1.0`):
- Yahoo daily bars for ^GSPC ^NDX ^RUT ^DJI ^VIX BTC-USD ETH-USD.
- Yahoo 5-minute RTH bars of ES=F NQ=F RTY=F for the intraday US path.
- data.binance.vision daily files: USD-M 1h klines and the 1m premium index, which gives the funding estimate.

Runs daily at 09:40 and 21:30 ET via `ci/scheduler.py` (workflow `c348f-book.yml`). Each run logs every completed UTC day whose data are
complete and waits on the rest. Binance's daily files usually appear the next morning, so the log runs about a day behind.

State is on branch `state-c348f`:
- `streams.csv`: per day, P&L and intraday low of each stream per $100K, crypto positions, the funding estimate, and events.
- `accounts.csv`: per day per account: attempt, stage, day P&L, balance, cash to date, and events.
- `state.json`.

First logged day: 2026-11-23. Review after 12 months (2027-11-22); the decision rules are in research_lab `claude/c348f-preregistration.md`.

Verification (2026-11-23):
- `python3 c348f/book_logger.py --backtest 2026-09-22 2026-11-21 out.csv`, checked against research `reports/c347/paths_2021_26.pkl`
  over 2026-09-22..10-30 (39 days):
  - The US-only stream matches to $0.00 on daily P&L and within $3.5 on intraday lows.
  - The CFD and perp streams match within $7 on every day except 2026-10-28/29. Binance had not published 10-28 when the research data
    was built, so research filled it from Yahoo; the log uses the real bars.
  - The funding estimate is within 0.0027% per day of actual Binance funding.
- The account engine reproduces research `sim_year` exactly on all 60 account-years (6 accounts x 10 windows, 2016-26): $0.00 difference.

Disclosed changes from the research method:
- On a futures roll day, the proxy's prior close is re-based when the futures/cash ratio jumps by more than 0.2%. Research used the raw
  front-month close, which mixes two contracts on those days.
- When Binance premium files are missing for more than 3 days, funding is assumed at 0.03%/day, the same as the research pre-2020
  assumption.
