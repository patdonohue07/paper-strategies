"""C334F forward paper log of the C333 book under FTMO 2-Step 100K rules. Log only: no orders, no account.

Frozen rules (research_lab C320, C311, C327, C330, C332, C333; reports/c333/README.md):
- US leg (US500/US100/US2000/US30 = ^GSPC ^NDX ^RUT ^DJI): at each daily close score 8 votes (+1 above MA200, +1 above MA50, +1 20-day
  return up, +1 VIX > 1.2 x its MA20 (-1 if < 0.85 x), +1 VIX in its top 20% of 250 days (-1 bottom 20%), +1 turn of month (first 3 or
  last trading day), -1 x sign(RUT 5-day minus SPX 5-day return), -1 x sign(5-day return)). |score| >= 5 -> enter at that close in the
  score's direction (one position per index). Stop: close beyond 1.5 x ATR14% from entry; target 2R on closes; exit after 7 sessions.
  Risk $875 (0.875%) per trade at full size: notional = 875 / (1.5 x ATR14%). Costs 1 bp per side, longs 2.5 bp per calendar night.
- Crypto leg (BTCUSD, ETHUSD): equal-weight ensemble of 8 trend variants = horizons {7/14/28/56, 14/28/56/112} x vol lookback {20, 60}
  x rebalance band {0, 0.25}; each variant per coin: signal = mean sign of the L-day returns at the prior close, target = signal x 0.5 /
  sd(lookback) of daily returns, position kept unless |target - position| > band x |target|. Daily P&L = pos x return - 0.10% x |change|
  - 0.082% x |pos| (FTMO crypto commission+spread, -30%/yr swap), scaled by $500 (0.5% of the account in daily vol).
- FTMO 2-Step 100K: +10% then +5%, daily loss 5% of the day-start equity, static $90,000 floor, >= 4 trading days per phase, fee $603
  refunded with the first payout, funded: every 14 days withdraw 80% of profit above $100,000; full size in all stages. A breach starts a
  new attempt the next day. Daily data only: the intraday low is approximated as the day-start equity + 1.5 x the day's loss (as research).
- Data: Yahoo daily bars. Run once a day after 00:00 UTC (20:30 ET); processes every completed day not yet in the ledger.
- Decision (prereg in research_lab claude/c334f-preregistration.md): after 12 months, report FTMO attempts, payouts and daily P&L t-stat.
Usage: python3 book_logger.py [STATE_DIR] | python3 book_logger.py --backtest START END OUT.csv  (verification against research)
"""
import csv, json, math, os, sys, urllib.request
from datetime import date, datetime, timedelta, timezone

UA = {"User-Agent": "research-client/1.0"}
US = ["^GSPC", "^NDX", "^RUT", "^DJI"]; CRY = ["BTC-USD", "ETH-USD"]
RISK, CVOL, ACCT, FEE = 875.0, 500.0, 100000.0, 603.0
START = date.fromisoformat(os.environ.get("C334F_START", "2026-11-23"))
HOLIDAYS = {date(2026, 11, 26), date(2026, 12, 25), date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 3, 26),
            date(2027, 5, 31), date(2027, 6, 18), date(2027, 7, 5), date(2027, 9, 6), date(2027, 11, 25), date(2027, 12, 24)}   # NYSE, 2026-27
VARIANTS = [(hz, lb, band) for hz in ((7, 14, 28, 56), (14, 28, 56, 112)) for lb in (20, 60) for band in (0.0, 0.25)]


def yahoo(sym, rng="10y"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(sym)}?range={rng}&interval=1d"
    for i in range(4):
        try:
            d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()); break
        except Exception:
            if i == 3:
                raise
    r = d["chart"]["result"][0]; q = r["indicators"]["quote"][0]; out = {}
    for i, t in enumerate(r.get("timestamp", [])):
        h, l, c = q["high"][i], q["low"][i], q["close"][i]
        if None in (h, l, c):
            continue
        out[datetime.fromtimestamp(t, timezone.utc).date() if sym in CRY else datetime.fromtimestamp(t, timezone(timedelta(hours=-5))).date()] = (h, l, c)
    return dict(sorted(out.items()))


def sgn(x):
    return 0.0 if x is None or x == 0 or x != x else (1.0 if x > 0 else -1.0)


def mean(a):
    return sum(a) / len(a)


def sd(a):
    m = mean(a); return math.sqrt(sum((x - m) ** 2 for x in a) / (len(a) - 1))


def rank_pct(win):
    x = win[-1]; less = sum(1 for v in win if v < x); eq = sum(1 for v in win if v == x)
    return (less + (eq + 1) / 2) / len(win)


def next_session(d):
    n = d + timedelta(days=1)
    while n.weekday() >= 5 or n in HOLIDAYS:
        n += timedelta(days=1)
    return n


def us_votes(px, vix, spx, rut, days):
    """score per date for one index (votes use data up to and including that close)."""
    C = [px[d][2] for d in days]; H = [px[d][0] for d in days]; L = [px[d][1] for d in days]
    vx, sx, rx = [], [], []; lv = ls = lr = None
    for d in days:
        lv = vix.get(d, lv); ls = spx.get(d, ls); lr = rut.get(d, lr); vx.append(lv); sx.append(ls); rx.append(lr)
    sc, atr = {}, {}
    for i, d in enumerate(days):
        if i >= 13:
            tr = [max(H[j] - L[j], abs(H[j] - C[j - 1]), abs(L[j] - C[j - 1])) for j in range(i - 13, i + 1)]; atr[d] = mean(tr) / C[i]
        if i < 250:
            continue
        s = sgn(C[i] - mean(C[i - 199:i + 1])) + sgn(C[i] - mean(C[i - 49:i + 1])) + sgn(C[i] / C[i - 20] - 1)
        m20 = mean(vx[i - 19:i + 1]); s += 1 if vx[i] > 1.2 * m20 else (-1 if vx[i] < 0.85 * m20 else 0)
        p = rank_pct(vx[i - 249:i + 1]); s += 1 if p > 0.8 else (-1 if p < 0.2 else 0)
        k = sum(1 for e in days[:i + 1] if (e.year, e.month) == (d.year, d.month))
        last = (days[i + 1].month != d.month) if i + 1 < len(days) else (next_session(d).month != d.month)
        s += 1 if (k <= 3 or last) else 0
        s -= sgn((rx[i] / rx[i - 5] - 1) - (sx[i] / sx[i - 5] - 1)); s -= sgn(C[i] / C[i - 5] - 1)
        sc[d] = s
    return sc, atr, C


def us_pnl(data, first, last):
    """daily $ P&L of the US leg for dates first..last (positions may open before first)."""
    vix = {d: v[2] for d, v in data["^VIX"].items()}; spx = {d: v[2] for d, v in data["^GSPC"].items()}; rut = {d: v[2] for d, v in data["^RUT"].items()}
    out = {}; events = []
    for s in US:
        px = data[s]; days = list(px); sc, atr, C = us_votes(px, vix, spx, rut, days); pos = None
        for i, d in enumerate(days):
            if pos is not None:
                rt = pos["sg"] * (C[i] / pos["e"] - 1); fin = pos["n"] * 0.00025 * (d - days[i - 1]).days if pos["sg"] > 0 else 0.0
                out[d] = out.get(d, 0.0) + pos["sg"] * (C[i] / C[i - 1] - 1) * pos["n"] - fin
                if rt <= -pos["u"] or rt >= 2 * pos["u"] or i - pos["i0"] >= 7:
                    out[d] -= pos["n"] * 1e-4; events.append((d, s, "exit", pos["sg"], round(rt / pos["u"], 2))); pos = None
                continue
            if d in sc and abs(sc[d]) >= 5 and d in atr:
                u = 1.5 * atr[d]; pos = dict(sg=sgn(sc[d]), e=C[i], u=u, n=RISK / u, i0=i); out[d] = out.get(d, 0.0) - pos["n"] * 1e-4
                events.append((d, s, "entry", pos["sg"], sc[d]))
    return {d: v for d, v in out.items() if first <= d <= last}, [e for e in events if first <= e[0] <= last]


def crypto_pnl(data, first, last):
    out = {}
    for s in CRY:
        px = data[s]; days = list(px); x = [px[d][2] for d in days]; n = len(x); ret = [float("nan")] + [x[i] / x[i - 1] - 1 for i in range(1, n)]
        for hz, lb, band in VARIANTS:
            pos = 0.0
            for i in range(1, n):
                sig = sum(sgn(x[i - 1] / x[i - 1 - L] - 1) if i - 1 - L >= 0 else 0.0 for L in hz) / len(hz)
                w = ret[max(1, i - lb):i]
                v = sd(w) if len(w) == lb and i - lb >= 1 else float("nan")
                tgt = sig * 0.5 / v if v == v and v > 0 else 0.0
                new = tgt if abs(tgt - pos) > band * abs(tgt) else pos
                p = (new * ret[i] - 0.0010 * abs(new - pos) - 0.00082 * abs(new)) * CVOL / len(VARIANTS); pos = new
                if first <= days[i] <= last:
                    out[days[i]] = out.get(days[i], 0.0) + p
    return out


def fetch():
    return {s: yahoo(s) for s in US + ["^VIX"] + CRY}


def backtest(a, b, path):
    data = fetch(); a, b = date.fromisoformat(a), date.fromisoformat(b); u, _ = us_pnl(data, a, b); c = crypto_pnl(data, a, b)
    with open(path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["date", "us", "crypto"])
        d = a
        while d <= b:
            w.writerow([d.isoformat(), round(u.get(d, 0.0), 4), round(c.get(d, 0.0), 4)]); d += timedelta(days=1)


def ftmo_step(acc, d, pnl):
    """advance the simulated FTMO account by one calendar day."""
    if acc["dead"]:
        acc.update(new_acc(acc["attempt"] + 1, d)); acc["log"].append(f"{d} attempt {acc['attempt']} starts (fee ${FEE:.0f})")
    st = acc["eq"]; low = st + min(pnl, 0) * 1.5; acc["eq"] = st + pnl; acc["days"] += 1
    if low < st - 0.05 * ACCT or low < 0.90 * ACCT:
        acc["dead"] = True; acc["log"].append(f"{d} BREACH ({'daily' if low < st - 0.05 * ACCT else 'max'} loss) stage {acc['stage']}"); return
    if acc["stage"] < 2 and acc["eq"] >= (1.10 if acc["stage"] == 0 else 1.05) * ACCT and acc["days"] >= 4:
        acc["log"].append(f"{d} passed phase {acc['stage'] + 1} in {acc['days']} days"); acc["stage"] += 1; acc["eq"] = ACCT; acc["days"] = 0; acc["since"] = 0; return
    if acc["stage"] == 2:
        acc["since"] += 1
        if acc["since"] >= 14 and acc["eq"] > ACCT:
            pay = 0.8 * (acc["eq"] - ACCT) + (0.0 if acc["refunded"] else FEE); acc["paid"] += pay; acc["refunded"] = True
            acc["log"].append(f"{d} payout ${pay:,.0f}"); acc["eq"] = ACCT; acc["since"] = 0


def new_acc(n, d):
    return dict(attempt=n, start=str(d), stage=0, eq=ACCT, days=0, since=0, dead=False, refunded=False, paid=0.0, fees=FEE * n, log=[])


def main(stdir):
    os.makedirs(stdir, exist_ok=True); sp = os.path.join(stdir, "state.json"); lp = os.path.join(stdir, "ledger.csv")
    S = json.load(open(sp)) if os.path.exists(sp) else dict(last=str(START - timedelta(days=1)), acc=new_acc(1, START), total_paid=0.0, attempts=[])
    today_utc = datetime.now(timezone.utc).date(); last_done = date.fromisoformat(S["last"]); upto = today_utc - timedelta(days=1)
    if upto <= last_done:
        print("nothing new"); return
    data = fetch()
    for s in CRY:                                          # drop the still-forming bar of the current UTC day
        data[s] = {d: v for d, v in data[s].items() if d < today_utc}
    first = last_done + timedelta(days=1); d = first
    while d <= upto:                                       # stop at the first day whose bars are not published yet
        session = d.weekday() < 5 and d not in HOLIDAYS and not any(e > d for e in data["^GSPC"])   # a later US bar => d was a closure
        session = session or (d.weekday() < 5 and d in data["^GSPC"])
        if any(d not in data[s] for s in CRY) or (session and any(d not in data[s] for s in US + ["^VIX"])):
            break
        d += timedelta(days=1)
    upto = d - timedelta(days=1)
    if upto < first:
        print("waiting for data"); return
    u, ev = us_pnl(data, first, upto); c = crypto_pnl(data, first, upto); new = not os.path.exists(lp)
    with open(lp, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "us_pnl", "crypto_pnl", "total", "attempt", "stage", "equity_after", "events"])
        d = first
        while d <= upto:
            tot = u.get(d, 0.0) + c.get(d, 0.0); acc = S["acc"]; nlog = len(acc["log"])
            if acc["dead"]:
                S["attempts"].append({k: acc[k] for k in ("attempt", "start", "stage", "paid")}); S["total_paid"] += acc["paid"]
            ftmo_step(acc, d, tot)
            evs = [f"{e[1]} {e[2]} {'long' if e[3] > 0 else 'short'} ({e[4]})" for e in ev if e[0] == d] + acc["log"][nlog:]
            w.writerow([d.isoformat(), round(u.get(d, 0.0), 2), round(c.get(d, 0.0), 2), round(tot, 2), acc["attempt"], acc["stage"], round(acc["eq"], 2), "; ".join(evs)])
            print(d, round(tot, 2), acc["stage"], round(acc["eq"], 2), "; ".join(evs)); d += timedelta(days=1)
    S["last"] = upto.isoformat(); json.dump(S, open(sp, "w"), indent=1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--backtest":
        backtest(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "state"))
