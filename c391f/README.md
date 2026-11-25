# C391F: rolling-cohort forward paper log of the C391 short-horizon prop book (no orders, no account)

The C391 book (research_lab reports/c391/README.md) aims at the fastest first payout. A single simulated account gives one yes/no
answer per attempt. So this log starts a **new one-attempt simulated account (a cohort) every UTC day** for each entry, follows it for
60 days, and records whether and when it reached a first payout.

| Id | Plan | Fee | Modelled P30 (twin) |
|---|---|---|---|
| S01 | MyFundedPerps Elite 3% DLL $10K (primary) | $71 | 23% (10%) |
| S02 | MFFU Pro 50K | $265 | 4% (2%) |
| S03 | Velotrade CLASSIC 2-Step $5K | $54 | 5% (1%) |
| S04 | CFT 2-Phase $5K (manual in the US) | $58 | 9% (6%) |
| S05 / S06 | S01 with leverage capped at 5x / 10x gross notional (C391 Amendment 1) | $71 | 21% / 25% (9% / 10%) |

P30 = the chance of a first payout within 30 days on one attempt. The twin is the same setup with no edge.

**Books:** AUTO_150 = 2 x S01; AUTO_150_L5 / _L10 = 2 x S05 / S06; AUTO_500 = S02 + 2 x S01 + S03; AUTO_1500 = 5 x S02 + 2 x S01; ALL_500 = S02 + 2 x S01 + S04.

**Streams:** `book_logger.py` loads `c390f/book_logger.py` and, through it, `c348f/book_logger.py`, both unchanged. It adds the T1
turn-of-month leg: long each index over the last 4 and first 2 sessions of every month. The leg comes in a CFD version and a
whole-micro futures version, and the hourly lows behind the combined futures stop are kept. The exact rules are in the docstring.

**Engine:** c390f `step` (research c341 `sim_year`, fixed engine) with one attempt and a 60-day horizon.

**Schedule and state:**
- Runs daily at 09:40 and 21:30 ET via `ci/scheduler.py` (workflow `c391f-book.yml`).
- Cohorts start each day from 2026-12-01 to 2027-09-30; the last ends 2027-11-29.
- State on branch `state-c391f`: `streams.csv`, `cohorts.csv` (one row per finished cohort) and `state.json` (active cohorts).

**Verification** (2026-11-25; research_lab `code/c391f_verify.py`, `reports/c391/c391f_verify.log`):
- **Streams** vs research over 2026-09-18..10-30:
  - S01 within $0.78 every day.
  - S03 within $0.68 and S04 within $0.11, except 2026-10-28/29 (Binance gap, as C348F).
  - S02 P&L exact; lows within $48 (5-minute vs 1-minute bars).
- **Engine:** cohorts equal research `sim_year(max_attempts=1, horizon=60)` to $0.00 on 1,500 paths per entry.
- **Dry run** (2026-09-20..11-24, scratch): files written and 28 cohorts completed (all failed in October 2026). Not part of the
  window.

Prereg and decision rules: research_lab `claude/c391f-preregistration.md`, plus addenda 1-2. MyFundedPerps' leverage cap for Elite $10K is not verified: S05 is the reference below 10x, S06 at 10x or more. Day-14 plumbing check about 2026-12-15; review 2027-12-01.
