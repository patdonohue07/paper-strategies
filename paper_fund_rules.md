# Paper fund rules (frozen 2026-11-04 01:55 ET; paper only)
- Sleeve A, bond calendar: short 10% TLT + 10% IEF of equity from the close 6 trading days before each 10/20/30-year nominal auction to the close the day before it (C34); long 10% TLT + 10% IEF over the last 4 trading days of each month (C43). Flat otherwise. Auction windows take precedence over month-end windows.
- Sleeve B, hedged IG credit: long VCIT at 30% of equity; short IEF at beta x 30% of equity, with beta from trailing 120 daily dividend-adjusted returns. The hedge is multiplied by 1.25 inside auction windows and 0.75 inside month-end windows (C79-3).
- Orders: market-on-close (Alpaca time_in_force "cls"), sent around 15:40 ET, before the 15:50 cutoff. Integer shares.
- Benchmarks logged: each sleeve's daily P&L; fills vs the day's VWAP (execution check); expected backtest numbers: Sleeve A about 0.1-0.4% of notional per window; Sleeve B about +2.5%/yr at 4% vol (C79-3, 2016-2026).
- Review after 3 months (about 10 month-end and 30 auction windows). Paper only: no live account, no real money.

## Expectation update (02:10 ET, from C83)
In TLT/IEF the bond calendar captured about half of the yield-based edge in 2016-2026 (t 1.85 vs 2.98 in yields). The auction leg is weakest in ETFs (t 1.13); the month-end leg holds better (t 1.97). The paper fund keeps the frozen rules, since tracking that shortfall live is the point of the forward test; expected Sleeve A contribution is about +1%/yr at 20% sizing, not the yield-based figure.

## Proposal, not adopted (02:20 ET, from C85)
The month-end leg is cleaner in intermediate and aggregate funds (IEF t 2.84, BND t 2.88, GOVT t 2.43) than in TLT (t 1.66). Proposed variant for Pat to approve: month-end sleeve 20% IEF (instead of 10% TLT + 10% IEF). The frozen rules stay as written until he decides.

## 2026-11-04 11:15 ET: first dry runs, and C84
- Dry run works: state "auction" today (10y auction Nov 10, 30y Nov 12); dry orders short 1,228 TLT and 4,659 IEF, long 3,772 VCIT on $1M paper equity; VCIT/IEF beta 0.869.
- Fixed: TreasuryDirect lists upcoming auction dates under competitiveAuctionCloseDate (auctionDate is empty until results).
- Known gap: 20y auctions are announced about 4 trading days ahead, so the 6-day window starts late for them until the Treasury tentative auction schedule is added.
- C84: the auction concession is weak since 2022 in every form (yields t 0.88), so Sleeve A's auction part is the least supported piece. Decision for Pat: keep it at the frozen size, halve it, or track it paper-only while trading the month-end part.
- Install: install_paper_fund_daily.command (Pat runs it once) adds a LaunchAgent for weekdays at 3:40 pm with --live (paper endpoint only).

## v2 rules (2026-11-04 11:20 ET, Pat's decisions)
- Auction leg: TRACK ONLY. In auction windows the would-be frozen trade (short 10% TLT + 10% IEF, and the x1.25 hedge boost) is logged in fund_log.csv (auction_tracked_only) with prices, so its P&L can be scored, but no auction orders are sent. The credit sleeve's hedge stays at 1.0x in auction windows.
- Month-end sleeve: long 20% IEF over the last 4 trading days (was 10% TLT + 10% IEF). The credit sleeve's hedge stays at 0.75x in month-end windows.
- Sleeve B unchanged otherwise: long 30% VCIT, short beta x 30% IEF.
- The frozen v1 script is kept as paper_fund_v1_frozen.py.

## v2.1 (2026-11-04, approved by Pat): half-day fix
- On early-close days (1 pm close, e.g. Nov 27, Dec 24) the 3:40 pm run sends no orders, since the market is already closed.
- If a window's entry day is a half day, enter one session earlier (Dec 2026 month-end: enter at the Dec 23 close instead of Dec 24). Same shift for the tracked auction window.
- Previous version saved as paper_fund_v2_prefix_20261104.py.
