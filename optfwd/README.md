# optfwd: C125 options forward paper test (log only)

Scores the two strongest C125 survivors (research_lab `claude/c125-options-batch-summary.md`) on real Alpaca indicative option
quotes. No orders are sent. Rules are frozen in the `opt_fwd.py` docstring.

- A (F20_02442): SPY 10-delta put, first expiry >= 60 days, entered every 5th trading day only if SPY > 200-day mean and nothing open;
  buy back at the ask once 50% of the credit is captured, else hold to expiry. Decision at 40 settled trades.
- B (F07_02095): weekly, short 25-delta strangles (first expiry >= 45 days) on the 3 names whose 30d ATM IV is richest vs sector
  peers relative to their own trailing history; no trade across an earnings date. Decision at 100 settled trades.

- S (C157 amendment, 2026-11-10; A and B unchanged): the same weekly ranking as B but with peer_dm history seeded from
  `iv_seed.csv` (peer ratio per name for the 252 trading days to 2026-09-29, computed from the Bloomberg 30d ATM IV export with
  the same formula), so it ranks from the first candidate day. Each pick logs two structures on one expiry: S1 the short
  25-delta strangle and S2 an iron condor (S1 plus long 10-delta wings bought at the ask). Own open list; same earnings skip.
  Decision at 100 settled picks per structure. Backtest (modeled): strangle +421bp, condor +217bp per trade in the C125 holdout
  (research_lab `reports/c157/README.md`).

Fills: sell at the bid, buy back at the ask (primary); mid shown for reference. P&L in bp of the underlying at entry.

Differences from the backtest (disclosed):
- SPY options stand in for SPX (Alpaca has no index options); SPY options are American and physically settled; settlement uses intrinsic.
- 30d IV is interpolated from Alpaca's chain, not Bloomberg's constant-maturity series. B's peer_dm needs 60 stored days of Alpaca
  history before it ranks (backtest used 200 of 252), so B starts trading about 3 months after install.
- Earnings: dates in `earnings_dates.csv` (recent actual dates per name), projected forward by 91 days, with a 7-day buffer.

- S mixes two IV sources in its trailing mean (Bloomberg seed, then Alpaca) until the seed ages out (about a year); the seed has a
  gap from 2026-09-30 to the first Alpaca day. B (Alpaca history only) starts about 3 months after install and is the clean comparison.
- `iv_seed.csv` is derived from Bloomberg data (log ratio of each name's IV to its sector median; no IV levels). Check the data
  licence before making this repository public.

State: `state-optfwd` branch: state.json, a_trades.csv, b_trades.csv, s_trades.csv, iv_hist.csv, summary.md, log.txt.
Local logic test without network or keys: `python3 opt_fwd.py --mock`.
