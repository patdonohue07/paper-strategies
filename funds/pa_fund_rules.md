# Portable-alpha paper fund (C88), rules frozen 2026-11-04

- Account: a SECOND Alpaca paper account (~/.alpaca_paper2). The script refuses to run live if those keys point to the bond paper fund's account.
- Core: SPY sized to 100% of account equity, held at all times.
- Overlay: IEF sized to 50% of equity, bought at the close 4 trading days before month-end (T-4), sold at the close of the last trading day (T). Uses margin (150% gross during the window).
- Early closes: if T-4 is a half day (e.g. Dec 24), enter at the close of T-5. No orders are sent on half days (the 3:42 pm run is after the 1 pm close).
- Orders: market-on-close (time_in_force cls), sent at 3:42 pm ET weekdays, before Alpaca's 3:50 pm cutoff.
- Financing: Alpaca paper does not charge margin interest, so the log carries an estimated drag (borrowed $ x 6.25%/252 per day). Judge results net of it.
- Benchmark: SPY alone, same start date.
- Expectation (C88 ETF version, 2016-2026): +0.8%/yr over SPY before the drag estimate, about the same volatility and drawdowns. One month is noise: overlay months win about 60% of the time.
- Review: after 3 months, the first look; a real verdict needs about 12 months of windows.
- Real-money version (not now): replace the IEF overlay with micro 10-year Treasury futures sized by DV01 at the time.
