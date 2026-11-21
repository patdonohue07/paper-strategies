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
| doge-fv | hourly at :03 (signals 11:00-16:00) | C120-FWD Kalshi DOGE vs GBM fair-value forward paper score (log only, no orders; decides at 150 settled trades) |
| opt-fwd | weekdays 15:40 | C125-FWD options survivors on real Alpaca option quotes (log only, no orders): A SPY 10-delta put-write w/ MA200 + TP50 (decides at 40), B rich-IV short strangles (decides at 100) |
| perp-forward-test | daily 10:37 | FWD-C10 Binance perp breakdown short forward test |
| ftmo-fwd | weekdays 16:20 | C210-FWD rebalancing + RTY morning trend on FTMO 2-Step 100K rules: daily paper log from Yahoo bars (no orders, no account; decides at 250 sessions) |
| c237-listings | hourly :05 (5-min cycles) | C237 Kalshi new-listing snapshots 60-90 min after open, listings to 2026-12-13 (public data, no keys, no orders) |
| c238-noon | daily 10:55-12:00 ET | C238 Kalshi + Polymarket order-book tops for the noon-ET crypto contracts, settlement days to 2026-12-15 (public data, no keys, no orders) |
| c239-hourly | hourly :56-:00 ET | C239 Kalshi hourly crypto ladders + Coinbase spot in the last ~2.5 min before each close, closes to 2026-12-07 00:00 ET (public data, no keys, no orders) |
| c251-gold | weekdays 12:59-16:01 ET | C251 Kalshi daily gold/silver/copper ladders, top of book every minute, settlement days to 2026-12-31 (public data, no keys, no orders) |
| c253-ticks | weekdays 13:30-14:30 ET | C253 second-by-second order books of near-money Kalshi gold/silver/copper and BTC strikes, with Binance PAXG and Coinbase BTC, to 2026-12-04 (public data, no keys, no orders) |
| c269f-hlcarry | hourly :02 | C269F forward paper test of funding carry on Hyperliquid builder perps (niche dexes vs xyz control, random-side control), to 2027-02-18 (public data, no keys, no orders) |
| c267-niche | Mondays 11:00 ET | C267 weekly niche-market pipeline: new (<= 90-day) small-book Kalshi series priced (lognormal / barrier, Treasury par yields) and logged; flags on live order books; settled flags scored against the best-of-N random gate (public data, no keys, no orders) |
| c275f-power | hourly :30 | C275F forward paper test of the C275 weekly power pricer: live order books of Kalshi weekly ERCOT / PJM / MISO hub-price contracts, scored offline with the frozen pricer, to 2027-01-22 (public data, no keys, no orders) |
| c281f-closure | daily 10:00 and 20:00 | C281F forward paper test of the C281 closure snap-back (enter 20:00 ET the evening before a US market reopening, exit 10:00): live order books of 159 stock perps on Hyperliquid xyz / io / para and Lighter, scored offline with a pre-hashed scorer, to 2027-03-01 (public data, no keys, no orders) |
| c296f-nav | weekdays 21:00 | C296F forward paper test of the C296 stale-NAV rule: Vanguard international stock ETFs (VXUS, VEA, VWO, VGK, VPL, VSS) 15:45-16:00 SIP bars and NBBO (Alpaca market data, no orders) plus their Admiral funds' NAVs (Yahoo), scored offline with a pre-hashed scorer, to 2027-02-24 |
| futures-shadow | weekdays 18:20 | C91 month-end trade in actual TY and US futures: a log only, no orders |
| vix-score | weekdays 08:50 | C100 forward scoring of the VIX-augmented SPY variance forecast (no trading) |
| health | weekdays 16:30 | Daily health report: one file per day on the `state-health` branch (`YYYY-MM-DD.md`, plus `latest.md`) |
| scheduler | always on | Starts every job above at its exact ET time (see below) |
| checks | manual only | `orders`: read-only check that Monday's market orders would be accepted; `yahoo`: raw bar timestamps |

## Scheduler
GitHub's own cron is throttled on this repo (about 2 runs per 14 hours), so `scheduler` (ci/scheduler.py) keeps one run
alive for about 5h45m, starts each job with `gh workflow run` at its slot (kalshi every 10 min, hl :07, doge-fv :03, opt-fwd 15:40, ftmo-fwd 16:20, c237 :05, c238 10:55, c239 :56, c251 12:55, c253 13:25, perp 10:37,
bili-entry 08:40 and 09:02 dry=false, vix 08:50, funds-close 15:15 and 15:32 dry=false, health 16:30, futures-shadow 18:20
weekdays), then starts its successor and exits. Before each start it checks the Actions API so a slot is never started
twice; a missed slot is started late only within its grace window. A second scheduler exits at once if one is already
running; the hourly cron on scheduler.yml only matters when the chain breaks. The jobs keep their own cron lines as a
backup; they are time-gated and once-per-day guarded, so a stray cron run does nothing harmful.
Stop the chain: create `ci/SCHEDULER_OFF` on main (takes effect within 10 minutes) or disable the scheduler workflow.

Each job keeps its data on its own `state-*` branch (funds, kalshi, hl, fwd, fut, vix, health, dogefv, optfwd, ftmofwd, c237, c238, c239, c251, c253). Logs: open that branch on GitHub.
Secrets used: `APACKEYID`, `APCSECRET` (bond fund + BILI account), `APACKEYID2`, `APACSECRET2` (portable alpha).
Jobs do nothing until `ci/ENABLED` exists on main. Pre-registrations live in the Investing Thesis project.
