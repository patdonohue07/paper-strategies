# C450F: forward paper log of the final C450 prop book

- **What it logs:** the final prop book from research_lab C449-C450: 48 accounts at 16 firms, $38,376 of listed fees.
- **Research expectation:** $109,495 mean over 12 months; $105,500 with book-level leave-one-year-out; median $33,291.
- **Frozen setups:** research_lab code/c451_freeze.py and c451_book.py wrote `book.json` from the exact plan dicts and settings the
  research engine used. **Do not edit book.json.**
- **Log only:** no orders, no account, nothing traded. Public Yahoo and data.binance.vision data.

## Protocol
- **Window:** every account starts one attempt on **2026-12-01** and is followed for 365 UTC days to 2027-11-30.
- **Breaches:** a breach ends the account, as in research (one attempt).
- **The test number:** book cash at **day 360** (fees paid, payouts received). It goes in `book.csv` as `book_cash_day360`, compared with
  the research mean, median and spread.
- **Schedule:** `.github/workflows/c450f-book.yml`, daily 09:40 and 21:30 ET via `ci/scheduler.py`. State on branch `state-c450f`:
  - `streams.csv`: each entry's daily P&L, intraday low and daily-loss offset;
  - `accounts.csv`: each entry's stage, balance and cash;
  - `book.csv`: book cash, funded and ended accounts, payouts;
  - `state.json`.

## The book (`book.json`, one entry per account type; copies follow the same path)
| Entry | Account | Count | Fee | Strategy | Research value each / yr |
|---|---|---|---|---|---|
| E01 | HyroTrader One-Step 200K | 1 | $1,299 | crypto trend (perp) | $9,411 |
| E02 | Propr Classic 1-Step 200K | 1 | $1,998 | crypto trend (perp) | $6,372 |
| E03 | CFT 2-Phase 200K, 90% add-on, 0.75x eval / 1.25x funded, $10K day and trade caps | 1 | $1,500 | crypto trend (perp) | $9,040 |
| E04 | City Traders Imperium 2-Step 100K | 1 | $549 | US index swing + crypto (CFD) | $2,919 |
| E05 | FTMO US 2-Step 200K Swing, indices without Russell + BTC | 2 | $1,249 | US swing + BTC, losers closed and reopened at the reset | $7,173 |
| E06 | FunderPro 2-Phase 200K Swing, 90% add-on | 1 | $1,565 | US swing + crypto, Swing caps, close-and-reopen | $7,957 |
| E07 | Instant Funding One-Phase Crypto 100K, 90% add-on | 10 | $1,079 | crypto trend (CFD), 1x cap | $2,106 |
| E08 | Velotrade Classic 100K, 1.25x phase 1 and funded | 1 | $769 | crypto trend (perp) | $3,756 |
| E09 | MyFundedPerps Signature 100K, 90/10 add-on | 1 | $1,007 | crypto trend (perp) | $983 |
| E10 | MyFundedPerps Elite 50K, 90/10 add-on, 0.75x eval / 1.25x funded | 2 | $594 | crypto trend (perp) | $1,310 |
| E11 | Ment Funding $1M, 90% add-on, 1.5x max-loss buffer | 1 | $11,180 | US index swing without Russell, close-and-reopen | $20,902 |
| E12-E17 | FundedNext Flex 100K, Lucid Flex 50K, MFFU Builder / Pro 50K, Topstep 50K, BrightFunded Core 50K | 5 / 5 / 1 / 4 / 5 / 5 | $49-$265 | micro futures after 3 down closes | $225-$769 |
| E18 | BluSky Orbit 50K | 1 | $199 | index-futures trend | $68 |

Values each are research C450 means over five test years.

## Checks before launch (research_lab code/c451_enginecheck.py, c451_streamcheck.py)
- **Engine:** this logger's `step` against the research c440 engine on the same research streams. All 18 entries match exactly on 300
  bootstrap paths each (max |difference| $0.00). That covers:
  - the daily-loss offsets, per-stage sizing and qualifying days;
  - payout buffers and gaps, max payouts, HyroTrader's cap forfeit;
  - floor locks and monthly / activation fees.
- **Streams:** `--backtest 2026-09-01 2026-10-30` against the research daily streams on the same dates. Daily P&L correlations by entry:

  | Entries | Correlation |
  |---|---|
  | HyroTrader, Propr, CFT, CTI, FunderPro, Instant Funding, Velotrade, MFP, Lucid, MFFU, BrightFunded | 1.000 |
  | Topstep | 0.995 |
  | FTMO US | 0.993 |
  | Ment | 0.991 |
  | FundedNext | 0.988 |
  | BluSky | 0.978 |

  Daily-loss offsets correlate 1.000.
- **Dry run:** a scratch run from 2026-11-20 logged seven days; state, CSVs and the no-new-data path all worked.

## Known differences from research (disclosed, not tuned)
- **Futures session P&L:** Yahoo 5-minute bars from 18:00 to 16:10 ET; research used 1-minute bars to 16:09.
- **News flattening not modelled.** Research flattens MFFU Pro (funded) and Topstep around tier-1 releases, about -$15 to -$33 per account a
  year. This is why Topstep correlates 0.995.
- **Reset timing:** daily closes stand in for each firm's reset (00:00 UTC crypto, 16:00 ET US). The firms reset at their own times:
  FTMO 00:00 CE(S)T, FunderPro and Ment 17:00 EST, CFT 12:05 UTC, Velotrade 00:30 UTC.
- **Data sources:** live Yahoo and Binance data replace the research panel, so means differ by a few dollars a day.
- **Not in the model:** CFT trades by hand (it bans bots). Written OKs for copies at FTMO, Instant Funding and MyFundedPerps are still
  to get.

Review: 2027-12-01. Research only, not advice.
