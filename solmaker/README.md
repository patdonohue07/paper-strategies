# sol-maker (C226)
Paper market-maker replay on Kalshi hourly crypto "above" ladders. **Gated series: KXSOLD**; KXBTCD and KXETHD are logged for comparison.
Public data only: 1-minute candles (quotes) and public trade prints (fills). No account, no keys, no orders.

Rules (preregistered in research_lab/claude/c226-preregistration.md):
- Minutes close-50 .. close-5; quote from the previous minute's candle when two-sided, mid 0.10-0.90, spread >= 2c.
  Spread >= 3c: improve both sides by 1c (alone at the top). Spread = 2c: join (fills only on trade-through).
- 10 contracts per side per minute, inventory cap +-50 per rung; fills from public trades in that minute; hold to settlement.
- Maker fee ceil(0.0175 p(1-p) n) per fill (conservative); P&L without fees also kept.
- Forward window: events closing 2026-11-13 .. 2026-12-11 ET. PASS (SOL): mean event P&L > 0 with day-clustered t >= 2 and per-contract P&L > 0.

State (branch `state-solmaker`): `events.csv` (one row per event), `fills.csv`, `summary.md`.
Each run replays every settled event since the start that is not yet logged, so missed runs catch up.
