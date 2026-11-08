# optfwd: C125 options forward paper test (log only)

Scores the two strongest C125 survivors (research_lab `claude/c125-options-batch-summary.md`) on real Alpaca indicative option
quotes. No orders are sent. Rules are frozen in the `opt_fwd.py` docstring.

- A (F20_02442): SPY 10-delta put, first expiry >= 60 days, entered every 5th trading day only if SPY > 200-day mean and nothing open;
  buy back at the ask once 50% of the credit is captured, else hold to expiry. Decision at 40 settled trades.
- B (F07_02095): weekly, short 25-delta strangles (first expiry >= 45 days) on the 3 names whose 30d ATM IV is richest vs sector
  peers relative to their own trailing history; no trade across an earnings date. Decision at 100 settled trades.

Fills: sell at the bid, buy back at the ask (primary); mid shown for reference. P&L in bp of the underlying at entry.

Differences from the backtest (disclosed):
- SPY options stand in for SPX (Alpaca has no index options); SPY options are American and physically settled; settlement uses intrinsic.
- 30d IV is interpolated from Alpaca's chain, not Bloomberg's constant-maturity series. B's peer_dm needs 60 stored days of Alpaca
  history before it ranks (backtest used 200 of 252), so B starts trading about 3 months after install.
- Earnings: dates in `earnings_dates.csv` (recent actual dates per name), projected forward by 91 days, with a 7-day buffer.

State: `state-optfwd` branch: state.json, a_trades.csv, b_trades.csv, iv_hist.csv, summary.md, log.txt.
Local logic test without network or keys: `python3 opt_fwd.py --mock`.
