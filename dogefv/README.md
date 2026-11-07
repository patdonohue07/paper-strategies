# C120-FWD: Kalshi DOGE vs GBM fair value (forward paper score)
Log only: no orders, no keys. Hourly at :03 ET via the scheduler (cron backup 15:03-22:03 UTC).
Frozen rule and backtest: research_lab claude/c120-preregistration.md (C112-B1, C114, C120).
State on branch `state-dogefv`: summary.md (running score), signals.csv, trades.csv, log.txt, state.json.
Decision: 150 settled paper trades; pass if mean net > 0 with day-clustered t >= 2.
Note: spot is Coinbase DOGE-USD (Binance blocks US runners); the backtest used the Binance perp (basis small).
