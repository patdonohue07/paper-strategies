# Paper strategies health report 2026-11-13 (Fri 16:30 ET)

**1 problem(s), see section 4**

## 1. Jobs today

| Workflow | Runs | First | Last | Failed | Slots on time / due | Late or missed slots |
|---|---|---|---|---|---|---|
| kalshi-maker | 102 | 00:00 | 16:30 | 0 | 99/99 |  |
| hl-logger | 19 | 00:07 | 16:07 | 0 | 17/17 |  |
| doge-fv | 18 | 00:03 | 16:16 | 0 | 17/17 |  |
| perp-forward-test | 1 | 10:37 | 10:37 | 0 | 1/1 |  |
| bili-entry | 4 | 08:40 | 15:22 | 0 | 2/2 |  |
| vix-score | 2 | 08:50 | 15:05 | 0 | 1/1 |  |
| funds | 2 | 15:15 | 15:32 | 0 | 2/2 |  |
| opt-fwd | 1 | 15:40 | 15:40 | 0 | 1/1 |  |
| ftmo-fwd | 1 | 16:20 | 16:20 | 0 | 0/0 |  |
| health | 1 | 16:30 | 16:30 | 0 | 0/0 |  |
| futures-shadow | 0 | | | | 0/0 |  |
| c237-listings | 0 | | | | 0/17 | 00:05 missed, 01:05 missed, 02:05 missed, 03:05 missed, 04:05 missed, 05:05 missed (+11 more) |
| scheduler | 5 | 02:29 | 14:00 | 0 | 0/0 |  |

## 2. Bond fund + BILI (APACKEYID)

Status ACTIVE, equity $998,302 (prior close $998,546, day -244), cash $950,928, buying power $3,331,252

Orders today:

| Submitted | Symbol | Side | Qty | Filled | Avg price | Type/TIF | Status | Filled at |
|---|---|---|---|---|---|---|---|---|
| 08:40:19 | BILI | sell | 7407 | 7407 | 13.265688 | market/day | filled | 09:33:10 |
| 15:15:20 | IEF | buy | 17 | 17 | 90.06 | market/day | filled | 15:15:22 |
| 15:15:20 | VCIT | buy | 8 | 8 | 78.64 | market/day | filled | 15:15:22 |
| 15:15:23 | BILI | buy | 7407 | 7407 | 13.27 | market/day | filled | 15:15:24 |

Positions:

| Symbol | Qty | Market value | % equity | Today's target $ | Unrealized P&L |
|---|---|---|---|---|---|
| IEF | -2798 | $-252,128 | -25.3% | $-251,995 | $4,671 |
| VCIT | 3809 | $299,502 | 30.0% | $299,554 | $-4,678 |

## 2. Portable alpha (APACKEYID2)

Status ACTIVE, equity $994,073 (prior close $1,002,451, day -8,377), cash $27, buying power $2,783,437

Orders today:

| Submitted | Symbol | Side | Qty | Filled | Avg price | Type/TIF | Status | Filled at |
|---|---|---|---|---|---|---|---|---|
| 15:15:22 | SPY | buy | 1 | 1 | 753.64 | market/day | filled | 15:15:23 |

Positions:

| Symbol | Qty | Market value | % equity | Today's target $ | Unrealized P&L |
|---|---|---|---|---|---|
| SPY | 1324 | $994,046 | 100.0% | $997,741 | $-5,929 |

## 3. Strategy logs (today's live rows and each job's own summary)

- bond fund: 15:15:20 state auction, orders [["IEF", 17, "3d95f57a-7bb3-4b0d-a93e-0557a879ef89"], ["VCIT", 8, "ea77637b-4ee4-47ec-ad0c-9e0638f38141"]]
- portable alpha: 15:15:22 state core_only, orders [["SPY", 1, "7153d205-bdc8-4501-b525-4bc1209cf748"]]
- BILI entry: 08:40:19 signal -1, gap -0.01497, order 4c775773-9a5b-49c1-b81f-66ba4e919c94, short 7407
- BILI exit: 15:15:23 held -7407.0, order 64047228-59da-49d2-8efd-1faf564bf7be
- Kalshi maker: C66 paper maker summary 2026-11-13 16:20 ET (interim, decides nothing) / weekend  above/below  orders   17 filled    3 mean filled P&L -18.67c t nan | if all filled +41.00c / weekend  range modal  orders    6 filled    5 mean filled P&L -34.60c t nan | if all filled -18.33c / weekday  above/below  orders   62 filled   11 mean filled P&L -30.91c t -1.37 | if all filled +36.65c
- perp forward test: Forward test, perp breakdown short (frozen rule, paper only). Updated 2026-11-13 10:38. Data through 2026-11-12 UTC. / Signals since 2026-10-01: 229 (memes 22, alts 207); open 199; top-trader ratio still pending 0 /  / CLOSED trades (returns before funding):
- futures shadow: Futures shadow log (C91 rule), updated 2026-11-12 21:37 / TY: 1 closed months, total $+495, mean $+495/contract-month / US: 1 closed months, total $+89, mean $+89/contract-month / 2026-10 TYZ26: closed; entry corrected 106.046875 -> 106.109375 (v1.1 date fix) entry 106.109375 exit 106.640625 pnl 495.0
- VIX scoring: C100 VIX forecast forward scoring, 2026-11-13 08:50: 3 scored days, mean QLIKE improvement +0.7140 (positive = VIX helps), VIX better on 100% of days; decision at 250 days
- Hyperliquid logger: last line `2026-11-13 16:08:12 logged 2026-11-13 21:00: 235 coins, 2000 wallets queried in 49s, 4848 positions`

## 4. Errors and warnings

- c237-listings.yml: 00:05 missed, 01:05 missed, 02:05 missed, 03:05 missed, 04:05 missed, 05:05 missed, 06:05 missed, 07:05 missed, 08:05 missed, 09:05 missed, 10:05 missed, 11:05 missed, 12:05 missed, 13:05 missed, 14:05 missed, 15:05 missed, 16:05 missed

