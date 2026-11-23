# C334F: forward paper log of the C333 FTMO book (no orders, no account)

**Retired 2026-11-23 before its first logged day; replaced by [C348F](../c348f/README.md)** (the C347 rule-compliant multi-account book).
The workflow file stays for history but is no longer scheduled.

Frozen book from research_lab C320/C311/C327/C330/C332/C333 (rules in the docstring of `book_logger.py`):
- US index swing rule on US500/US100/US2000/US30 (8-vote score >= 5, stop 1.5 x ATR14, target 2R, max 7 sessions), $875 risk per trade.
- BTC/ETH trend: equal-weight ensemble of 8 variants, 0.5% of the account in daily volatility, FTMO crypto costs.
- Simulated FTMO 2-Step $100K account, full size in every stage; a breach starts a new attempt (and a new $603 fee) the next day.

Runs daily at 21:30 ET via `ci/scheduler.py` (workflow `c334f-book.yml`), Yahoo daily bars, processes every completed day not yet logged
(waits when a bar is not published; a later US bar marks a market closure). State on branch `state-c334f`:
`ledger.csv` (date, US P&L, crypto P&L, total, attempt, stage, equity, events) and `state.json`.
First logged day 2026-11-23. Review after 12 months (2027-11-22): attempts, payouts, fees, daily P&L mean and t.
Verification: `python3 c334f/book_logger.py --backtest 2024-11-22 2026-11-21 out.csv` reproduces the research streams exactly
(daily correlation 1.0, totals equal, 0 days off by more than $1).
