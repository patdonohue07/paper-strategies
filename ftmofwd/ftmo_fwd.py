"""C210-FWD: forward paper test of rebalancing (RB) + RTY morning trend (EMA) under FTMO 2-Step 100K rules. Log only, no orders.

Frozen rules (research_lab C149, C175/C176, C204-C209; preregistration claude/c210-preregistration.md):
- RB: rebalancing composite z (mean of 10/21/63-day ES-minus-ZN log-return z-scores vs prior 252 days, plus the month-to-date term in
  the last 5 sessions of the month), known at the prior close. |z| >= 0.5: NQ against the imbalance (z > 0 -> short), 09:31 open ->
  15:55 open, stop 1.0 x mean prior-20 RTH range, 1 adverse tick per side. Per MNQ micro: points x $2 - $1.22 - 2 ticks.
- EMA: RTY 5-minute closes (RTH), EMA20/EMA50 cross, follow; entry at the next 1-min open if that minute is 30..150 (10:00-12:00),
  stop 1 x A, target 2 x A, A = 0.25 x mean prior-20 RTH range; one position at a time; exit 15:55 open. Per M2K micro: points x $5 - $2.22.
- FTMO 2-Step 100K (rules confirmed 2026-11-11): static $90,000 floor, 5% daily loss vs the day's worst, phase 1 +10%, phase 2 +5% (new
  account), >= 4 trading days per phase; funded: every 10 trading days withdraw 80% of profit above $100,000. Fee EUR 540 = $603,
  refunded with the first payout. Size: 1% of the account ($1,000) in expected daily $ sd per strategy, re-estimated every day as
  K x prior-20 RTH range x point value (K: RB 0.6521, EMA 0.34, calibrated on 2021-24); CFD lots are fractional. A failed attempt starts a new one the next session.
- Data: Yahoo 1-minute bars (NQ=F, RTY=F), 5-minute bars for ranges, daily closes (ES=F, ZN=F) for the composite. Continuous front
  contracts: roll jumps are not removed (research used roll-free returns) - disclosed difference.
- Decision: after 250 sessions, pass if the combined daily P&L mean > 0 with t >= 1.5; FTMO attempts and payouts reported throughout.
Standard library only. Catches up on any of the last ~6 sessions not yet processed.
"""
import csv, json, math, os, sys, urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
HERE = os.path.dirname(os.path.abspath(__file__)); ST = os.path.join(HERE, "state")
K_SD = {"RB": 0.6521, "EMA": 0.34}   # per-micro daily $ sd = K x prior-20 RTH range x point value (calibrated 2021-24)
TARGET_SD = 1000.0                   # 1% of the account per strategy
ACCT, FEE = 100000.0, 603.0
START = date.fromisoformat(os.environ.get("FTMO_START", "2026-11-12"))   # first forward session (override only for local tests)
TICK = {"NQ": 0.25, "RTY": 0.10}; PV = {"NQ": 2.0, "RTY": 5.0}; COST = {"NQ": 1.22 + 2 * 0.25 * 2.0, "RTY": 1.22 + 2 * 0.10 * 5.0}


# ---------------- data ----------------
def yahoo(sym, rng, interval):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval={interval}"
    d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "student-research-script/1.0"}), timeout=30).read())
    r = d["chart"]["result"][0]; q = r["indicators"]["quote"][0]; out = []
    for i, t in enumerate(r.get("timestamp", [])):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            continue
        out.append((datetime.fromtimestamp(t, ET), o, h, l, c))
    return out


def rth_days(bars):
    """date -> list of 390 (o,h,l,c) for 09:30..15:59 ET minutes (gaps filled with the previous close as a flat bar)."""
    by = {}
    for t, o, h, l, c in bars:
        k = (t.hour - 9) * 60 + t.minute - 30
        if 0 <= k < 390:
            by.setdefault(t.date(), {})[k] = (o, h, l, c)
    out = {}
    for d, m in by.items():
        if len(m) < 300:
            continue
        seq, last = [], None
        for k in range(390):
            if k in m:
                last = m[k][3]; seq.append(m[k])
            else:
                seq.append((last, last, last, last) if last is not None else None)
        if seq[0] is None:
            first = next(x for x in seq if x is not None); seq = [x if x is not None else first for x in seq]
        out[d] = seq
    return out


def daily_ranges(bars5):
    hi, lo = {}, {}
    for t, o, h, l, c in bars5:
        k = (t.hour - 9) * 60 + t.minute - 30
        if 0 <= k < 390:
            d = t.date(); hi[d] = max(hi.get(d, h), h); lo[d] = min(lo.get(d, l), l)
    return {d: hi[d] - lo[d] for d in hi}


def range20(ranges, d):
    prev = sorted(x for x in ranges if x < d)[-20:]
    return sum(ranges[x] for x in prev) / len(prev) if len(prev) == 20 else None


# ---------------- RB composite ----------------
HOLIDAYS = {date(2026, 11, 26), date(2026, 12, 25), date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 3, 26), date(2027, 5, 31),
            date(2027, 6, 18), date(2027, 7, 5), date(2027, 9, 6), date(2027, 11, 25), date(2027, 12, 24)}


def future_days(last):
    out, d = [], last + timedelta(days=1)
    while d <= last + timedelta(days=40):
        if d.weekday() < 5 and d not in HOLIDAYS:
            out.append(d)
        d += timedelta(days=1)
    return out


def composite(es, zn):
    """es, zn: lists of (date, close). Returns date -> composite value applying to that session (uses closes through the prior day)."""
    ce = dict(es); cz = dict(zn); days = sorted(set(ce) & set(cz))
    s = [math.log(ce[d]) for d in days]; b = [math.log(cz[d]) for d in days]; n = len(days)
    def zser(L):
        x = [None] * n
        for i in range(L, n):
            x[i] = (s[i] - s[i - L]) - (b[i] - b[i - L])
        z = [None] * n
        for i in range(n):
            hist = [v for v in x[max(0, i - 252):i] if v is not None]
            if x[i] is None or len(hist) < 120:
                continue
            mu = sum(hist) / len(hist); sd = math.sqrt(sum((v - mu) ** 2 for v in hist) / (len(hist) - 1))
            z[i] = (x[i] - mu) / sd if sd > 0 else None
        return z
    thr = {L: zser(L) for L in (10, 21, 63)}
    # month-to-date term
    month = [(d.year, d.month) for d in days]
    fut = [(d.year, d.month) for d in future_days(days[-1])] if days else []
    allm = month + fut
    pos_from_end = [0] * n
    for i in range(n):
        j = i
        while j + 1 < len(allm) and allm[j + 1] == month[i]:
            j += 1
        pos_from_end[i] = j - i + 1
    mtd = [None] * n
    for i in range(n):
        k = i
        while k - 1 >= 0 and month[k - 1] == month[i]:
            k -= 1
        if k - 1 >= 0:
            mtd[i] = (s[i] - s[k - 1]) - (b[i] - b[k - 1])
    cal_raw = [None] * n
    for i in range(1, n):
        if pos_from_end[i] <= 5 and month[i] == month[i - 1]:
            cal_raw[i] = mtd[i - 1]
    cal = [None] * n; hist = []
    for i in range(n):
        if cal_raw[i] is None:
            continue
        if len(hist) >= 30:
            h = hist[-250:]; mu = sum(h) / len(h); sd = math.sqrt(sum((v - mu) ** 2 for v in h) / (len(h) - 1))
            cal[i] = cal_raw[i] / sd if sd > 0 else None
        hist.append(cal_raw[i])
    out = {}
    for i in range(1, n):
        t = [thr[L][i - 1] for L in (10, 21, 63)]
        if any(v is None for v in t):
            continue
        vals = t + ([cal[i]] if cal[i] is not None else [])
        out[days[i]] = sum(vals) / len(vals)
    # value for the next (unseen) session: uses closes through the last day
    return out, days


# ---------------- trades ----------------
def rb_trade(bars, side, rng20):
    """NQ 09:31 open -> 15:55 open with stop 1.0 x range20. Returns per-micro (net, worst) or None."""
    tk = TICK["NQ"]; e = bars[1][0] + side * tk; stop = e - side * rng20; worst = 0.0
    for k in range(1, 385):
        o, h, l, c = bars[k]
        adv = (l - e) if side > 0 else (e - h)
        worst = min(worst, adv)
        if (side > 0 and l <= stop) or (side < 0 and h >= stop):
            px = (min(o, stop) if side > 0 else max(o, stop)) - side * tk
            net = side * (px - e) * PV["NQ"] - 1.22
            return net, min(net, worst * PV["NQ"] - 1.22)
    px = bars[385][0] - side * tk
    net = side * (px - e) * PV["NQ"] - 1.22
    return net, min(net, worst * PV["NQ"] - 1.22)


def ema(vals, n, prev=None):
    a = 2 / (n + 1); out = []; e = prev
    for v in vals:
        e = v if e is None else a * v + (1 - a) * e; out.append(e)
    return out


def ema_signals(days_bars):
    """days_bars: ordered list of (date, bars). Returns {date: [(k_entry, side)]} using a continuous 5-min close series."""
    xs, idx = [], []
    for d, bars in days_bars:
        for k in range(4, 390, 5):
            xs.append(bars[k][3]); idx.append((d, k))
    e20, e50 = ema(xs, 20), ema(xs, 50); out = {}
    for i in range(1, len(xs)):
        up = e20[i] > e50[i] and e20[i - 1] <= e50[i - 1]; dn = e20[i] < e50[i] and e20[i - 1] >= e50[i - 1]
        if not (up or dn):
            continue
        d, k = idx[i]
        if 29 <= k <= 359 and 30 <= k + 1 <= 150:
            out.setdefault(d, []).append((k + 1, 1 if up else -1))
    return out


def ema_trades(bars, sigs, A):
    tk = TICK["RTY"]; res = []; free = -1
    for k0, s in sorted(sigs):
        if k0 <= free:
            continue
        e = bars[k0][0] + s * tk; stop = e - s * A; tgt = e + s * 2 * A; worst = 0.0; px = None; xb = 385
        for kk in range(k0, 386):
            o, h, l, c = bars[kk]
            if kk >= 385:
                px = o - s * tk; xb = 385; break
            worst = min(worst, (l - e) if s > 0 else (e - h))
            if (s > 0 and l <= stop) or (s < 0 and h >= stop):
                px = (min(o, stop) if s > 0 else max(o, stop)) - s * tk; xb = kk; break
            if (s > 0 and h >= tgt + tk) or (s < 0 and l <= tgt - tk):
                px = max(o, tgt) if s > 0 else min(o, tgt); xb = kk; break
        net = s * (px - e) * PV["RTY"] - COST["RTY"]
        res.append((k0, s, net, min(net, worst * PV["RTY"] - COST["RTY"]))); free = xb
    return res


# ---------------- FTMO account ----------------
def step_account(acc, day_pnl, day_worst, traded):
    ev = ""
    if acc["dead"]:
        acc.update(attempt=acc["attempt"] + 1, stage=0, bal=0.0, days=0, age=0, dead=False, refunded=False); acc["fees"] += FEE; ev = "new attempt; "
    acc["age"] += 1
    if acc["bal"] + day_worst <= -0.10 * ACCT or day_worst <= -0.05 * ACCT:
        acc["dead"] = True; return ev + f"BREACH stage {acc['stage']} (worst {day_worst:+.0f})"
    acc["bal"] += day_pnl; acc["days"] += 1 if traded else 0
    if acc["stage"] < 2:
        tgt = 0.10 if acc["stage"] == 0 else 0.05
        if acc["bal"] >= tgt * ACCT and acc["days"] >= 4:
            acc["stage"] += 1; acc.update(bal=0.0, days=0, age=0); ev += f"PASSED to stage {acc['stage']}"
    elif acc["age"] % 10 == 0 and acc["bal"] > 0:
        pay = 0.8 * acc["bal"]; acc["payouts"] += pay; acc["npay"] += 1
        if not acc["refunded"]:
            acc["fees"] -= FEE; acc["refunded"] = True; ev += "fee refunded; "
        ev += f"PAYOUT ${pay:,.0f}"; acc["bal"] = 0.0
    return ev


def main():
    os.makedirs(ST, exist_ok=True)
    tf = os.path.join(ST, "trades.csv"); af = os.path.join(ST, "account.csv"); sf = os.path.join(ST, "state.json")
    state = json.load(open(sf)) if os.path.exists(sf) else {"done": [], "acc": {"attempt": 1, "stage": 0, "bal": 0.0, "days": 0, "age": 0, "dead": False,
                                                                                 "fees": FEE, "refunded": False, "payouts": 0.0, "npay": 0}}
    nq = rth_days(yahoo("NQ=F", "7d", "1m")); rty = rth_days(yahoo("RTY=F", "7d", "1m"))
    rng_nq = daily_ranges(yahoo("NQ=F", "60d", "5m")); rng_rty = daily_ranges(yahoo("RTY=F", "60d", "5m"))
    es = [(t.date(), c) for t, o, h, l, c in yahoo("ES=F", "2y", "1d")]; zn = [(t.date(), c) for t, o, h, l, c in yahoo("ZN=F", "2y", "1d")]
    comp, _ = composite(es, zn)
    today = datetime.now(ET).date()
    ordered = sorted((d, b) for d, b in rty.items())
    sig = ema_signals(ordered)
    trows, arows = [], []
    for d in sorted(set(nq) & set(rty)):
        if str(d) in state["done"] or d < START or (d == today and datetime.now(ET).hour < 16):
            continue
        rbn = rbw = emn = emw = 0.0; traded = False
        z = comp.get(d); r20 = range20(rng_nq, d)
        if z is not None and abs(z) >= 0.5 and r20:
            side = -1 if z > 0 else 1; net, w = rb_trade(nq[d], side, r20)
            rbn, rbw, traded = net, w, True
            trows.append(dict(date=d, stream="RB", side=side, z=round(z, 3), k_entry=1, net_micro=round(net, 2), worst_micro=round(w, 2)))
        a20 = range20(rng_rty, d)
        if a20 and d in sig:
            for k0, s, net, w in ema_trades(rty[d], sig[d], 0.25 * a20):
                emn += net; emw += w; traded = True
                trows.append(dict(date=d, stream="EMA", side=s, z="", k_entry=k0, net_micro=round(net, 2), worst_micro=round(w, 2)))
        u_rb = TARGET_SD / (K_SD["RB"] * r20 * PV["NQ"]) if r20 else 0.0
        u_em = TARGET_SD / (K_SD["EMA"] * a20 * PV["RTY"]) if a20 else 0.0
        pnl = u_rb * rbn + u_em * emn; worst = min(pnl, u_rb * rbw + u_em * emw)
        acc = state["acc"]; ev = step_account(acc, pnl, worst, traded)
        arows.append(dict(date=d, attempt=acc["attempt"], stage=acc["stage"], units_rb=round(u_rb, 3), units_ema=round(u_em, 3),
                          day_pnl=round(pnl, 2), day_worst=round(worst, 2),
                          balance=round(acc["bal"], 2), event=ev, payouts=round(acc["payouts"], 2), net_fees=round(acc["fees"], 2)))
        state["done"].append(str(d))
    for f, rows in ((tf, trows), (af, arows)):
        if rows:
            new = not os.path.exists(f)
            with open(f, "a", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader() if new else None; w.writerows(rows)
    json.dump(state, open(sf, "w"), indent=1, default=str)
    summary(state, af, tf)


def summary(state, af, tf):
    acc = state["acc"]; rows = list(csv.DictReader(open(af))) if os.path.exists(af) else []
    x = [float(r["day_pnl"]) for r in rows]; n = len(x)
    mu = sum(x) / n if n else 0.0; sd = math.sqrt(sum((v - mu) ** 2 for v in x) / (n - 1)) if n > 2 else 0.0
    t = mu / (sd / math.sqrt(n)) if sd > 0 else float("nan")
    tr = list(csv.DictReader(open(tf))) if os.path.exists(tf) else []
    by = {s: [float(r["net_micro"]) for r in tr if r["stream"] == s] for s in ("RB", "EMA")}
    lines = [f"# C210-FWD: RB + RTY trend on FTMO 2-Step 100K (log only, no orders)", f"Updated {datetime.now(ET):%Y-%m-%d %H:%M} ET.", "",
             f"- Sessions processed: {n}; combined daily P&L mean ${mu:+,.0f} (t {t:.2f}); decision at 250 sessions (pass: mean > 0, t >= 1.5).",
             f"- RB trades: {len(by['RB'])}, mean ${sum(by['RB'])/len(by['RB']):+.2f}/micro" if by["RB"] else "- RB trades: 0",
             f"- EMA trades: {len(by['EMA'])}, mean ${sum(by['EMA'])/len(by['EMA']):+.2f}/micro" if by["EMA"] else "- EMA trades: 0",
             f"- FTMO: attempt {acc['attempt']}, stage {acc['stage']} (0 = phase 1, 1 = phase 2, 2 = funded), balance ${acc['bal']:+,.0f}, "
             f"payouts ${acc['payouts']:,.0f} ({acc['npay']}), net fees ${acc['fees']:,.0f}, net cash ${acc['payouts'] - acc['fees']:+,.0f}.", ""]
    lines += ["Last 10 sessions:"] + [f"  {r['date']} attempt {r['attempt']} stage {r['stage']} day {float(r['day_pnl']):+,.0f} bal {float(r['balance']):+,.0f} {r['event']}" for r in rows[-10:]]
    open(os.path.join(ST, "summary.md"), "w").write("\n".join(lines) + "\n"); print("\n".join(lines))


if __name__ == "__main__":
    main()
