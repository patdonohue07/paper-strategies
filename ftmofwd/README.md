# ftmofwd: C210 forward paper test on FTMO 2-Step rules (log only)

Rebalancing (NQ, research C148/C149) and the RTY morning EMA20/50 trend (C175/C176), traded on paper every weekday after the close
from Yahoo 1-minute bars, and run through a simulated FTMO 2-Step 100K account (static $90K floor, 5% daily loss, +10% / +5% phases,
80% payouts every 10 trading days, EUR 540 fee refunded at the first payout). Rules are frozen in the `ftmo_fwd.py` docstring.
No orders, no broker or FTMO account. First session 2026-11-12; decision at 250 sessions.

Variant B (added 2026-11-11): same strategies, but rebalancing skips FOMC statement days (research C211). It runs its own simulated
FTMO account (`account_b.csv`); account A is unchanged.

Differences from the research (disclosed): Yahoo continuous front-month bars (roll jumps not removed; the rebalancing signal agrees
with the research version on 93% of Nov 2025-Oct 2026 days); daily volatility-scaled size (1% of the account per strategy);
futures micro costs stand in for FTMO CFD costs.

State: `state-ftmofwd` branch: trades.csv, account.csv (A), account_b.csv (B), state.json, summary.md. Local test: `FTMO_START=2026-11-04 python3 ftmo_fwd.py`
in a scratch copy (it writes ./state).
