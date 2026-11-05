# paper-strategies

Pat Donohue's paper-only research strategies, run on GitHub Actions so they do not depend on a laptop being awake.
No real money: every Alpaca script refuses anything but the paper endpoint, and the Kalshi, Hyperliquid and Binance
jobs only read public data.

| Workflow | Schedule (ET) | What it does |
|---|---|---|
| funds-close | weekdays ~15:15, retry ~15:32 | Bond calendar fund, portable-alpha fund (separate paper account) and the BILI exit, all as market-on-close orders |
| bili-entry | weekdays ~08:40, retry ~09:02 | C90 BILI pre-open parity rule, market-on-open order |
| kalshi-maker | every 10 min | C66 weekend paper maker (paper orders, fills read from trade history) |
| hl-logger | hourly | Hyperliquid wallet-position logger |
| perp-forward-test | daily ~10:37 | FWD-C10 Binance perp breakdown short forward test |

Each job keeps its data on its own `state-*` branch (funds, kalshi, hl, fwd). Logs: open that branch on GitHub.
Secrets used: `APCA_KEY_ID`, `APCA_SECRET` (bond fund + BILI account), `APCA2_KEY_ID`, `APCA2_SECRET` (portable alpha).
Jobs do nothing until `ci/ENABLED` exists on main. Pre-registrations live in the Investing Thesis project.
