# Paper strategies health report 2026-11-27 (Fri 16:30 ET)

**3 problem(s), see section 4**

## 1. Jobs today

| Workflow | Runs | First | Last | Failed | Slots on time / due | Late or missed slots |
|---|---|---|---|---|---|---|
| kalshi-maker | 101 | 00:00 | 16:30 | 0 | 99/99 |  |
| hl-logger | 19 | 00:07 | 16:07 | 0 | 17/17 |  |
| doge-fv | 17 | 00:03 | 16:03 | 0 | 17/17 |  |
| perp-forward-test | 1 | 10:37 | 10:37 | 0 | 1/1 |  |
| bili-entry | 2 | 08:40 | 09:02 | 0 | 2/2 |  |
| vix-score | 1 | 08:50 | 08:50 | 0 | 1/1 |  |
| funds | 2 | 15:15 | 15:32 | 0 | 2/2 |  |
| opt-fwd | 1 | 15:40 | 15:40 | 0 | 1/1 |  |
| ftmo-fwd | 1 | 16:20 | 16:20 | 0 | 0/0 |  |
| health | 1 | 16:30 | 16:30 | 0 | 0/0 |  |
| futures-shadow | 0 | | | | 0/0 |  |
| c237-listings | 17 | 00:05 | 16:05 | 0 | 17/17 |  |
| c238-noon | 1 | 10:55 | 10:55 | 0 | 1/1 |  |
| c239-hourly | 16 | 00:56 | 15:56 | 0 | 16/16 |  |
| c251-gold | 1 | 12:55 | 12:55 | 0 | 1/1 |  |
| c253-ticks | 1 | 13:25 | 13:25 | 0 | 1/1 |  |
| c269f-hlcarry | 17 | 00:02 | 16:02 | 0 | 17/17 |  |
| c267-niche | 0 | | | | 0/0 |  |
| c275f-power | 17 | 00:30 | 16:30 | 0 | 16/16 |  |
| c281f-closure | 1 | 10:00 | 10:00 | 0 | 1/1 |  |
| c296f-nav | 0 | | | | 0/0 |  |
| c348f-book | 1 | 09:40 | 09:40 | 0 | 1/1 |  |
| c349f-book | 1 | 09:40 | 09:40 | 0 | 1/1 |  |
| c390f-book | 1 | 09:40 | 09:40 | 0 | 1/1 |  |
| c391f-book | 1 | 09:40 | 09:40 | 0 | 1/1 |  |
| scheduler | 5 | 00:10 | 11:56 | 0 | 0/0 |  |

## 2. Bond fund + BILI (APACKEYID)

Status ACTIVE, equity $993,016 (prior close $993,221, day -205), cash $843,181, buying power $3,182,285

Orders today:

| Submitted | Symbol | Side | Qty | Filled | Avg price | Type/TIF | Status | Filled at |
|---|---|---|---|---|---|---|---|---|
| 08:40:30 | BILI | buy | 8748 | 8748 | 12.31 | market/day | filled | 09:32:45 |
| 15:15:19 | BILI | sell | 8748 | 0 | | market/day | accepted | |

Positions:

| Symbol | Qty | Market value | % equity | Today's target $ | Unrealized P&L |
|---|---|---|---|---|---|
| BILI | 8748 | $107,163 | 10.8% |  | $-525 |
| IEF | -2774 | $-254,157 | -25.6% |  | $397 |
| VCIT | 3737 | $296,830 | 29.9% |  | $-1,594 |

## 2. Portable alpha (APACKEYID2)

Status ACTIVE, equity $966,659 (prior close $952,641, day +14,018), cash $-690,068, buying power $1,878,564

Orders today:

none

Positions:

| Symbol | Qty | Market value | % equity | Today's target $ | Unrealized P&L |
|---|---|---|---|---|---|
| IEF | 5167 | $473,407 | 49.0% |  | $-97 |
| SPY | 1330 | $972,070 | 100.6% |  | $-32,168 |
| TLT | 2600 | $211,250 | 21.9% |  | $-1,040 |

## 3. Strategy logs (today's live rows and each job's own summary)

- BILI entry: 08:40:30 signal 1, gap 0.0659, order da00b376-8889-416a-aa78-dafb198508ae, long 8748
- BILI exit: 15:15:19 held 8748.0, order 4250f2c3-d0e8-45cc-925a-0b48f832b83a
- Kalshi maker: C66 paper maker summary 2026-11-27 16:20 ET (interim, decides nothing) / weekend  above/below  orders   38 filled   11 mean filled P&L -36.00c t -1.25 | if all filled +25.47c / weekend  range modal  orders   17 filled   15 mean filled P&L -14.93c t -1.04 | if all filled -4.82c / weekday  above/below  orders  148 filled   38 mean filled P&L -19.50c t -1.27 | if all filled +27.95c
- perp forward test: Forward test, perp breakdown short (frozen rule, paper only). Updated 2026-11-27 10:38. Data through 2026-11-26 UTC. / Signals since 2026-10-01: 362 (memes 46, alts 316); open 304; top-trader ratio still pending 0 /  / CLOSED trades (returns before funding):
- futures shadow: Futures shadow log (C91 rule), updated 2026-11-26 23:15 / TY: 1 closed months, total $+495, mean $+495/contract-month / US: 1 closed months, total $+89, mean $+89/contract-month / 2026-10 TYZ26: closed; entry corrected 106.046875 -> 106.109375 (v1.1 date fix) entry 106.109375 exit 106.640625 pnl 495.0
- VIX scoring: C100 VIX forecast forward scoring, 2026-11-27 08:50: 12 scored days, mean QLIKE improvement +0.8526 (positive = VIX helps), VIX better on 83% of days; decision at 250 days
- Hyperliquid logger: last line `2026-11-27 16:08:21 logged 2026-11-27 21:00: 235 coins, 2000 wallets queried in 53s, 4404 positions`

## 4. Errors and warnings

- Bond fund + BILI (APACKEYID): order BILI sell 8748 still accepted after the close
- bond fund: no LIVE-PAPER row today (funds-close did not trade)
- portable alpha: no LIVE-PAPER row today (funds-close did not trade)

