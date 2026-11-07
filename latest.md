# Paper strategies health report 2026-11-06 (Fri 20:53 ET)

**12 problem(s), see section 4**

## 1. Jobs today

| Workflow | Runs | First | Last | Failed | Slots on time / due | Late or missed slots |
|---|---|---|---|---|---|---|
| kalshi-maker | 6 | 04:29 | 20:50 | 0 | 1/125 | 00:00 missed, 00:10 missed, 00:20 missed, 00:30 missed, 00:40 missed, 00:50 missed (+118 more) |
| hl-logger | 3 | 05:43 | 18:01 | 0 | 0/21 | 00:07 missed, 01:07 missed, 02:07 missed, 03:07 missed, 04:07 missed, 05:07 missed (+15 more) |
| perp-forward-test | 1 | 16:02 | 16:02 | 0 | 0/1 | 10:37 missed |
| bili-entry | 2 | 14:40 | 14:53 | 0 | 0/2 | 08:40 missed, 09:02 missed |
| vix-score | 1 | 14:43 | 14:43 | 0 | 0/1 | 08:50 missed |
| funds | 1 | 18:43 | 18:43 | 0 | 0/2 | 15:15 missed, 15:32 missed |
| health | 1 | 20:53 | 20:53 | 0 | 0/1 | 16:30 missed |
| futures-shadow | 1 | 20:53 | 20:53 | 0 | 0/1 | 18:20 missed |
| scheduler | 1 | 20:51 | 20:51 | 0 | 0/0 |  |

## 2. Bond fund + BILI (APACKEYID)

Status ACTIVE, equity $999,551 (prior close $999,995, day -444), cash $956,625, buying power $3,946,692

Orders today:

none

Positions:

| Symbol | Qty | Market value | % equity | Today's target $ | Unrealized P&L |
|---|---|---|---|---|---|
| VCIT | 543 | $42,926 | 4.3% |  | $-449 |

## 2. Portable alpha (APACKEYID2)

Status ACTIVE, equity $1,000,000 (prior close $1,000,000, day +0), cash $1,000,000, buying power $4,000,000

Orders today:

none

Positions:

| Symbol | Qty | Market value | % equity | Today's target $ | Unrealized P&L |
|---|---|---|---|---|---|
| (cash only) | | | | | |

## 3. Strategy logs (today's live rows and each job's own summary)

- Kalshi maker: C66 paper maker summary 2026-11-06 20:50 ET (interim, decides nothing) / weekend  above/below  orders    0 filled    0 mean filled P&L +nanc t nan | if all filled +nanc / weekend  range modal  orders    0 filled    0 mean filled P&L +nanc t nan | if all filled +nanc / weekday  above/below  orders   19 filled    3 mean filled P&L -56.00c t nan | if all filled +35.05c
- perp forward test: Forward test, perp breakdown short (frozen rule, paper only). Updated 2026-11-06 16:04. Data through 2026-11-05 UTC. / Signals since 2026-10-01: 187 (memes 18, alts 169); open 168; top-trader ratio still pending 0 /  / CLOSED trades (returns before funding):
- futures shadow: Futures shadow log (C91 rule), updated 2026-11-06 20:53 / TY: 1 closed months, total $+495, mean $+495/contract-month / US: 1 closed months, total $+89, mean $+89/contract-month / 2026-10 TYZ26: closed; entry corrected 106.046875 -> 106.109375 (v1.1 date fix) entry 106.109375 exit 106.640625 pnl 495.0
- VIX scoring: no summary yet
- Hyperliquid logger: last line `2026-11-06 18:02:30 logged 2026-11-06 23:00: 235 coins, 2000 wallets queried in 52s, 5120 positions`

## 4. Errors and warnings

- kalshi-maker: 124 of 125 slots late or missed
- hl-logger.yml: 00:07 missed, 01:07 missed, 02:07 missed, 03:07 missed, 04:07 missed, 05:07 missed, 06:07 missed, 07:07 missed, 08:07 missed, 09:07 missed, 10:07 missed, 11:07 missed, 12:07 missed, 13:07 missed, 14:07 missed, 15:07 missed, 16:07 missed, 17:07 missed, 18:07 missed, 19:07 missed, 20:07 missed
- perp-forward-test.yml: 10:37 missed
- bili-entry.yml: 08:40 missed, 09:02 missed
- vix-score.yml: 08:50 missed
- funds.yml: 15:15 missed, 15:32 missed
- health.yml: 16:30 missed
- futures-shadow.yml: 18:20 missed
- bond fund: no LIVE-PAPER row today (funds-close did not trade)
- portable alpha: no LIVE-PAPER row today (funds-close did not trade)
- BILI entry: no LIVE-PAPER row today
- BILI exit: no LIVE-PAPER row today

