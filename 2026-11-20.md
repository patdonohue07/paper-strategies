# Paper strategies health report 2026-11-20 (Fri 16:30 ET)

**ALL OK**

## 1. Jobs today

| Workflow | Runs | First | Last | Failed | Slots on time / due | Late or missed slots |
|---|---|---|---|---|---|---|
| kalshi-maker | 102 | 00:00 | 16:30 | 0 | 99/99 |  |
| hl-logger | 19 | 00:07 | 16:07 | 0 | 17/17 |  |
| doge-fv | 17 | 00:03 | 16:03 | 0 | 17/17 |  |
| perp-forward-test | 1 | 10:37 | 10:37 | 0 | 1/1 |  |
| bili-entry | 4 | 08:40 | 15:57 | 0 | 2/2 |  |
| vix-score | 2 | 08:50 | 15:45 | 0 | 1/1 |  |
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
| scheduler | 5 | 01:31 | 16:19 | 0 | 0/0 |  |

## 2. Bond fund + BILI (APACKEYID)

Status ACTIVE, equity $1,000,018 (prior close $1,000,249, day -231), cash $954,266, buying power $3,336,000

Orders today:

| Submitted | Symbol | Side | Qty | Filled | Avg price | Type/TIF | Status | Filled at |
|---|---|---|---|---|---|---|---|---|
| 15:15:31 | IEF | buy | 43 | 43 | 91.74 | market/day | filled | 15:15:32 |
| 15:15:31 | VCIT | sell | 27 | 27 | 79.38 | market/day | filled | 15:15:32 |

Positions:

| Symbol | Qty | Market value | % equity | Today's target $ | Unrealized P&L |
|---|---|---|---|---|---|
| IEF | -2774 | $-253,821 | -25.4% | $-254,489 | $734 |
| VCIT | 3777 | $299,573 | 30.0% | $299,899 | $-2,047 |

## 2. Portable alpha (APACKEYID2)

Status ACTIVE, equity $918,129 (prior close $947,839, day -29,710), cash $721, buying power $2,571,625

Orders today:

| Submitted | Symbol | Side | Qty | Filled | Avg price | Type/TIF | Status | Filled at |
|---|---|---|---|---|---|---|---|---|
| 15:15:33 | SPY | sell | 1 | 1 | 693.54 | market/day | filled | 15:15:34 |

Positions:

| Symbol | Qty | Market value | % equity | Today's target $ | Unrealized P&L |
|---|---|---|---|---|---|
| SPY | 1323 | $917,408 | 99.9% | $918,526 | $-81,812 |

## 3. Strategy logs (today's live rows and each job's own summary)

- bond fund: 15:15:31 state flat, orders [["IEF", 43, "89c404fc-0219-4a49-905b-17b994745d22"], ["VCIT", -27, "54e3d59d-c684-4642-ad3c-fbc860f814c2"]]
- portable alpha: 15:15:33 state core_only, orders [["SPY", -1, "383e5798-c77c-43ce-82de-c1ed7f3b7c85"]]
- BILI entry: 08:40:11 signal 0, gap -0.0074, order , 
- BILI exit: 15:15:33 held 0.0, order none
- Kalshi maker: C66 paper maker summary 2026-11-20 16:23 ET (interim, decides nothing) / weekend  above/below  orders   33 filled    6 mean filled P&L -23.00c t -0.76 | if all filled +37.15c / weekend  range modal  orders   12 filled   10 mean filled P&L -19.70c t -1.05 | if all filled -4.58c / weekday  above/below  orders  109 filled   24 mean filled P&L -31.00c t -1.37 | if all filled +31.94c
- perp forward test: Forward test, perp breakdown short (frozen rule, paper only). Updated 2026-11-20 10:39. Data through 2026-11-19 UTC. / Signals since 2026-10-01: 300 (memes 35, alts 265); open 258; top-trader ratio still pending 0 /  / CLOSED trades (returns before funding):
- futures shadow: Futures shadow log (C91 rule), updated 2026-11-19 22:15 / TY: 1 closed months, total $+495, mean $+495/contract-month / US: 1 closed months, total $+89, mean $+89/contract-month / 2026-10 TYZ26: closed; entry corrected 106.046875 -> 106.109375 (v1.1 date fix) entry 106.109375 exit 106.640625 pnl 495.0
- VIX scoring: C100 VIX forecast forward scoring, 2026-11-20 08:50: 8 scored days, mean QLIKE improvement +0.2319 (positive = VIX helps), VIX better on 75% of days; decision at 250 days
- Hyperliquid logger: last line `2026-11-20 16:08:30 logged 2026-11-20 21:00: 235 coins, 2000 wallets queried in 64s, 4493 positions`

## 4. Errors and warnings

- none

