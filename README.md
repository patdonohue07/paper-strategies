# paper-strategies

Pat Donohue's paper-only research strategies, run on GitHub Actions so they do not depend on a laptop being awake.
No real money: every Alpaca script refuses anything but the paper endpoint, and the Kalshi, Hyperliquid and Binance
jobs only read public data.

| Workflow | Schedule (ET) | What it does |
|---|---|---|
| funds-close | weekdays 15:15, retry 15:32 | Bond calendar fund, portable-alpha fund (separate paper account) and the BILI exit, plain market orders (day) since 2026-11-06 |
| bili-entry | weekdays 08:40, retry 09:02 | C90 BILI pre-open parity rule, market order sent before the open |
| kalshi-maker | every 10 min | C66 weekend paper maker (paper orders, fills read from trade history) |
| hl-logger | hourly at :07 | Hyperliquid wallet-position logger |
| perp-forward-test | daily 10:37 | FWD-C10 Binance perp breakdown short forward test |
| futures-shadow | weekdays 18:20 | C91 month-end trade in actual TY and US futures: a log only, no orders |
| vix-score | weekdays 08:50 | C100 forward scoring of the VIX-augmented SPY variance forecast (no trading) |
| health | weekdays 16:30 | Daily health report: one file per day on `state-health` (`health/YYYY-MM-DD.md`, `health/latest.md`) |
| scheduler | always on | Starts every job above at its exact ET time (see below) |
| checks | manual only | `orders`: read-only check that Monday's market orders would be accepted; `yahoo`: raw bar timestamps |

## Scheduler
GitHub's own cron is throttled on this repo (about 2 runs per 14 hours), so `scheduler` (ci/scheduler.py) keeps one run
alive for about 5h45m, starts each job with `gh workflow run` at its slot (kalshi every 10 min, hl :07, perp 10:37,
bili-entry 08:40 and 09:02 dry=false, vix 08:50, funds-close 15:15 and 15:32 dry=false, health 16:30, futures-shadow 18:20
weekdays), then starts its successor and exits. Before each start it checks the Actions API so a slot is never started
twice; a missed slot is started late only within its grace window. A second scheduler exits at once if one is already
running; the hourly cron on scheduler.yml only matters when the chain breaks. The jobs keep their own cron lines as a
backup; they are time-gated and once-per-day guarded, so a stray cron run does nothing harmful.
Stop the chain: create `ci/SCHEDULER_OFF` on main (takes effect within 10 minutes) or disable the scheduler workflow.

Each job keeps its data on its own `state-*` branch (funds, kalshi, hl, fwd, fut, vix, health). Logs: open that branch on GitHub.
Secrets used: `APACKEYID`, `APCSECRET` (bond fund + BILI account), `APACKEYID2`, `APACSECRET2` (portable alpha).
Jobs do nothing until `ci/ENABLED` exists on main. Pre-registrations live in the Investing Thesis project.
