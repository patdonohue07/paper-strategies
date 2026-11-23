"""C348F forward paper log of the C347 rule-compliant final multi-account book. Log only: no orders, no account, nothing traded.

Frozen setups (research_lab C344, C344b, C347; reports/c347/README.md; prereg claude/c348f-preregistration.md). Amounts per $100K:
- US leg (US500/US100/US2000/US30 = ^GSPC ^NDX ^RUT ^DJI, the C320 daily rule as in C334F): 8-vote score at each close, |score| >= 5 ->
  enter at that close in the score's direction (one position per index), stop 1.5 x ATR14% on closes, target 2R on closes, exit after 7
  sessions. Unit = $1,000 risked per trade; costs 1 bp per side, longs 2.5 bp per calendar night. Intraday path: Yahoo 5-minute RTH bars of
  ES=F / NQ=F / RTY=F (US30 uses ES=F) against the prior full session's last close, by UTC hour; hours after the cash close carry the
  cash-index day P&L; a day without a full proxy session books the day P&L at 20-23 UTC (low = 1.5 x the loss).
- Crypto: BTC/ETH equal-weight ensemble of 8 trend variants (positions from Yahoo daily closes, as C334F). P&L by UTC hour from Binance
  USD-M perpetual 1h bars, daily files from data.binance.vision (as research 2020+; Yahoo daily high/low when a day has no hourly bar
  after 2 days). CFD costs: 0.10% of the position change, 0.082% swap per day.
  Perp costs: 0.075% of the change plus Binance funding, estimated from Binance premium-index 1m bars (8-hour time-weighted premium P,
  rate = P + clamp(0.01% - P, -0.05%, +0.05%)); 0.03%/day when those files stay missing for more than 3 days.
- CFD stream (FundedNext, FTMO): US at 1.5 units + crypto at $1,250 x position, personal daily stop at -$4,000, gap-aware (when the loss
  first passes -$4,000 at the US-open hour, the day books the loss at that hour). FTMO: no US entry on the last session before a closure
  (FTMO gap rule). FundedNext funded stage: US at 0.75 units, crypto off (3% open-risk rule).
- Perp stream (CFT, HyroTrader, Bitfunded): crypto at $1,500 x position, challenge at 1.25x size, personal daily stop -$3,000 (CFT 1-Step
  -$2,000; its daily limit is 3%); Bitfunded closes and reopens every 10th day (days since 1970 divisible by 10).
- Accounts (C347 portfolio): FundedNext Stellar 2-Step 200K ($999.99), FTMO 2-Step 200K (EUR 1,080 = $1,185), CFT 2-Phase 200K ($1,250),
  CFT 1-Step Classic 100K ($949), HyroTrader One-Step 200K ($1,200 assumed), Bitfunded 2-Step 100K ($799). Rules as C347 `plans()`; the
  engine is research c341 `sim_year` on one path: a breach starts a new attempt (new fee) the next day, at most 3 attempts per account.
  Book B = the first five accounts; Book B+ adds Bitfunded.
Usage: python3 book_logger.py [STATE_DIR] | python3 book_logger.py --backtest START END OUT.csv  (streams, for checking against research)
"""
import csv, io, json, math, os, sys, time, urllib.error, urllib.request, zipfile
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

UA = {"User-Agent": "research-client/1.0"}; ET = ZoneInfo("America/New_York")
US = ["^GSPC", "^NDX", "^RUT", "^DJI"]; CRY = ["BTC-USD", "ETH-USD"]; BIN = {"BTC-USD": "BTCUSDT", "ETH-USD": "ETHUSDT"}
PROXY = {"^GSPC": "ES=F", "^NDX": "NQ=F", "^RUT": "RTY=F", "^DJI": "ES=F"}; FUT = ["ES=F", "NQ=F", "RTY=F"]
UNDER = {"ES=F": "^GSPC", "NQ=F": "^NDX", "RTY=F": "^RUT"}
START = date.fromisoformat(os.environ.get("C348F_START", "2026-11-23"))
HOLIDAYS = {date(2026, 11, 26), date(2026, 12, 25), date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 3, 26),
            date(2027, 5, 31), date(2027, 6, 18), date(2027, 7, 5), date(2027, 9, 6), date(2027, 11, 25), date(2027, 12, 24)}   # NYSE, 2026-27
VARIANTS = [(hz, lb, band) for hz in ((7, 14, 28, 56), (14, 28, 56, 112)) for lb in (20, 60) for band in (0.0, 0.25)]
RU, VC, GSTOP, RU_FN, VT, CM = 1.5, 1.25, 4000.0, 0.75, 1500.0, 1.25
CR_SIDE, CR_SWAP, PERP_SIDE, FUND_PRE, MAX_ATT = 0.0010, 0.00082, 0.00075, 0.0003, 3


def ph(target, mll, dll, min_days=0, cons=0.0):
    return dict(target=target, mll=mll, dll=dll, min_days=min_days, cons=cons)


ACCOUNTS = {   # per-$100K rules, s = size in $100K; ch / fu = stream in the challenge / funded stage
    "FN200": dict(name="FundedNext Stellar 2-Step 200K (3% risk compliant)", s=2, fee=999.99, ch="cfd", fu="cfd_fnf", cm=1.0, guard=None,
                  phases=[ph(8000, 10000, 5000, 5), ph(5000, 10000, 5000, 5)], funded=dict(mll=10000, dll=5000, first_wait=21, cycle=14), refund=True, refund_n=1),
    "FT200": dict(name="FTMO 2-Step 200K (gap-rule compliant)", s=2, fee=1185.0, ch="cfd_ft", fu="cfd_ft", cm=1.0, guard=None,
                  phases=[ph(10000, 10000, 5000, 4), ph(5000, 10000, 5000, 4)], funded=dict(mll=10000, dll=5000, first_wait=14, cycle=14), refund=True, refund_n=1),
    "C2P200": dict(name="CFT 2-Phase 200K", s=2, fee=1250.0, ch="perp", fu="perp", cm=CM, guard=3000.0,
                   phases=[ph(8000, 10000, 5000), ph(5000, 10000, 5000)], funded=dict(mll=10000, dll=5000, first_wait=15, cycle=15), refund=False, refund_n=1),
    "C1S100": dict(name="CFT 1-Step Classic 100K (2% stop)", s=1, fee=949.0, ch="perp", fu="perp", cm=CM, guard=2000.0,
                   phases=[ph(10000, 6000, 3000)], funded=dict(mll=6000, dll=3000, first_wait=7, cycle=7), refund=False, refund_n=1),
    "HY200": dict(name="HyroTrader One-Step 200K ($1,200 assumed)", s=2, fee=1200.0, ch="perp", fu="perp", cm=CM, guard=3000.0,
                  phases=[ph(10000, 8000, 4000, 3, 0.4)], funded=dict(mll=8000, dll=4000, first_wait=7, cycle=7, min_pay=31, cap=5000), refund=True, refund_n=1),
    "BF100": dict(name="Bitfunded 2-Step 100K", s=1, fee=799.0, ch="perp_bf", fu="perp_bf", cm=CM, guard=3000.0,
                  phases=[ph(8000, 10000, 5000), ph(5000, 10000, 5000)], funded=dict(mll=8000, dll=5000, first_wait=15, cycle=15), refund=True, refund_n=3),
}
BOOK_B = ["FN200", "FT200", "C2P200", "C1S100", "HY200"]


# ---------------------------------------------------------------- data
def get(url, binary=False, tries=4):
    for i in range(tries):
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()
            return r if binary else json.loads(r)
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return None
            if i == tries - 1:
                raise
        except Exception:
            if i == tries - 1:
                raise
        time.sleep(2 * (i + 1))


def yahoo(sym, rng="10y"):
    d = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(sym)}?range={rng}&interval=1d")
    r = d["chart"]["result"][0]; q = r["indicators"]["quote"][0]; out = {}
    for i, t in enumerate(r.get("timestamp", [])):
        h, l, c = q["high"][i], q["low"][i], q["close"][i]
        if None in (h, l, c):
            continue
        out[datetime.fromtimestamp(t, timezone.utc).date() if sym in CRY else datetime.fromtimestamp(t, timezone(timedelta(hours=-5))).date()] = (h, l, c)
    return dict(sorted(out.items()))


def yahoo_5m(sym, rng="60d"):
    """{ET date: [(minute of day, high, low, close), ...]} for RTH 09:30-16:00 ET bars."""
    d = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(sym)}?range={rng}&interval=5m")
    r = d["chart"]["result"][0]; q = r["indicators"]["quote"][0]; out = {}
    for i, t in enumerate(r.get("timestamp", [])):
        h, l, c = q["high"][i], q["low"][i], q["close"][i]
        if None in (h, l, c):
            continue
        lt = datetime.fromtimestamp(t, ET); m = lt.hour * 60 + lt.minute
        if 570 <= m < 960:
            out.setdefault(lt.date(), {})[m] = (h, l, c)
    return {k: [(m,) + v[m] for m in sorted(v)] for k, v in sorted(out.items())}


def epoch(d):
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


def daily_zip(kind, bsym, d):
    """{bar start (s): row} from data.binance.vision futures/um daily 1m/1h files, None if not published."""
    iv = "1m" if kind == "premiumIndexKlines" else "1h"
    raw = get(f"https://data.binance.vision/data/futures/um/daily/{kind}/{bsym}/{iv}/{bsym}-{iv}-{d}.zip", binary=True)
    if not raw:
        return None
    z = zipfile.ZipFile(io.BytesIO(raw)); out = {}
    for r in csv.reader(io.StringIO(z.read(z.namelist()[0]).decode())):
        if r and r[0][:1].isdigit():
            t = int(r[0]); t = t // 1000 if t > 1e14 else t; out[t // 1000] = r
    return out


KL = {}


def binance_hourly(bsym, a, b):
    """{hour start (s): (high, low, close)} of Binance USD-M perpetual 1h bars (as research 2020+) from a - 1 day through b."""
    out = {}; d = a - timedelta(days=1)
    while d <= b:
        if (bsym, d) not in KL:
            KL[(bsym, d)] = daily_zip("klines", bsym, d)
        for t, r in (KL[(bsym, d)] or {}).items():
            out[t] = (float(r[2]), float(r[3]), float(r[4]))
        d += timedelta(days=1)
    return out


PREM = {}


def premium_day(bsym, d):
    """{minute start (s): premium index close} for UTC day d from data.binance.vision, None if not published."""
    if (bsym, d) not in PREM:
        z = daily_zip("premiumIndexKlines", bsym, d); PREM[(bsym, d)] = None if z is None else {t: float(r[4]) for t, r in z.items()}
    return PREM[(bsym, d)]


def funding_day(bsym, d):
    """estimated sum of the three 8-hourly Binance funding rates stamped on UTC day d (00:00, 08:00, 16:00), None if data missing."""
    pa, pb = premium_day(bsym, d - timedelta(days=1)), premium_day(bsym, d)
    if pa is None or pb is None:
        return None
    pm = dict(pa); pm.update(pb); T0 = epoch(d); tot = 0.0
    for T in (T0, T0 + 28800, T0 + 57600):
        num = den = 0.0
        for i in range(480):
            v = pm.get(T - 28800 + 60 * i)
            if v is not None:
                num += (i + 1) * v; den += i + 1
        if den == 0:
            return None
        P = num / den; tot += max(min(P + min(max(0.0001 - P, -0.0005), 0.0005), 0.003), -0.003)
    return tot


# ---------------------------------------------------------------- signals
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


def utc_off(d):
    return int(-datetime(d.year, d.month, d.day, tzinfo=ET).utcoffset().total_seconds() // 3600)   # 4 (EDT) or 5 (EST)


def us_votes(px, vix, spx, rut, days):
    """score per date for one index (votes use data up to and including that close)."""
    C = [px[d][2] for d in days]; H = [px[d][0] for d in days]; L = [px[d][1] for d in days]
    vx, sx, rx = [], [], []; lv = ls = lr = None
    for d in days:
        lv = vix.get(d, lv); ls = spx.get(d, ls); lr = rut.get(d, lr); vx.append(lv); sx.append(ls); rx.append(lr)
    sc, atr = {}, {}; k = 0
    for i, d in enumerate(days):
        k = k + 1 if i > 0 and (days[i - 1].year, days[i - 1].month) == (d.year, d.month) else 1
        if i >= 13:
            tr = [max(H[j] - L[j], abs(H[j] - C[j - 1]), abs(L[j] - C[j - 1])) for j in range(i - 13, i + 1)]; atr[d] = mean(tr) / C[i]
        if i < 250:
            continue
        s = sgn(C[i] - mean(C[i - 199:i + 1])) + sgn(C[i] - mean(C[i - 49:i + 1])) + sgn(C[i] / C[i - 20] - 1)
        m20 = mean(vx[i - 19:i + 1]); s += 1 if vx[i] > 1.2 * m20 else (-1 if vx[i] < 0.85 * m20 else 0)
        p = rank_pct(vx[i - 249:i + 1]); s += 1 if p > 0.8 else (-1 if p < 0.2 else 0)
        last = (days[i + 1].month != d.month) if i + 1 < len(days) else (next_session(d).month != d.month)
        s += 1 if (k <= 3 or last) else 0
        s -= sgn((rx[i] / rx[i - 5] - 1) - (sx[i] / sx[i - 5] - 1)); s -= sgn(C[i] / C[i - 5] - 1)
        sc[d] = s
    return sc, atr, C


def us_paths(data, f5, V, first, last, no_pre_close):
    """{date: (CUM, LOW, FAV)} 24 UTC hours of the US leg at one unit ($1,000 risk per trade), plus events."""
    out, ev = {}, []

    def add(d, hrs, c, lo, fa):
        U = out.setdefault(d, ([0.0] * 24, [0.0] * 24, [0.0] * 24))
        for h in hrs:
            U[0][h] += c; U[1][h] += lo; U[2][h] += fa
    for s in US:
        px = data[s]; days = list(px); sc, atr, C = V[s]; pos = None
        f = f5[PROXY[s]]; full = [d for d in f if len(f[d]) >= 74]; fprev = {full[j]: full[j - 1] for j in range(1, len(full))}
        for i, d in enumerate(days):
            inr = first <= d <= last
            if pos is None:
                if d in sc and abs(sc[d]) >= 5 and d in atr:
                    nxt = days[i + 1] if i + 1 < len(days) else next_session(d)
                    if no_pre_close and (nxt - d).days > 1:
                        if inr:
                            ev.append((d, s, "entry skipped (closure next)", sgn(sc[d]), sc[d]))
                        continue
                    u = 1.5 * atr[d]; pos = dict(sg=sgn(sc[d]), e=C[i], u=u, n=1000.0 / u, i0=i)
                    if inr:
                        c = -pos["n"] * 1e-4; add(d, range(20, 24), c, c, c); ev.append((d, s, "entry", pos["sg"], sc[d]))
                continue
            n = pos["sg"] * pos["n"]; fin = pos["n"] * 0.00025 * (d - days[i - 1]).days if pos["sg"] > 0 else 0.0
            eod = n * (C[i] / C[i - 1] - 1) - fin; rt = pos["sg"] * (C[i] / pos["e"] - 1)
            ex = rt <= -pos["u"] or rt >= 2 * pos["u"] or i - pos["i0"] >= 7; fin_v = eod - (pos["n"] * 1e-4 if ex else 0.0)
            if inr:
                if d in fprev:
                    off = utc_off(d); pc = f[fprev[d]][-1][3]; bk = {}; cash = data[UNDER[PROXY[s]]]
                    if fprev[d] in cash and d in cash:                # contract roll: futures/cash ratio jumps -> re-base the prior close
                        jump = (f[d][-1][3] / cash[d][2]) / (pc / cash[fprev[d]][2])
                        if abs(jump - 1) > 0.002:
                            pc *= jump; ev.append((d, s, f"roll re-base {PROXY[s]} {jump - 1:+.2%}", 1, 0))
                    for m, hi, lo, cl in f[d]:
                        hh = m // 60 + off; cp = n * (cl / pc - 1)
                        lp = min(n * ((lo if n > 0 else hi) / pc - 1), cp); fp = max(n * ((hi if n > 0 else lo) / pc - 1), cp); b = bk.get(hh)
                        bk[hh] = (cp, lp, fp) if b is None else (cp, min(b[1], lp), max(b[2], fp))
                    prev = None
                    for hh in range(9 + off, 16 + off):          # a missing hour repeats the previous close (research panel ffill)
                        if hh not in bk and prev is not None:
                            bk[hh] = (prev, prev, prev)
                        if hh in bk:
                            prev = bk[hh][0]
                    lastc = n * (f[d][-1][3] / pc - 1)
                    for hh in range(24):
                        if hh in bk:
                            add(d, [hh], *bk[hh])
                        elif hh > 15 + off:
                            add(d, [hh], fin_v, min(fin_v, lastc), max(fin_v, lastc))
                else:
                    add(d, range(20, 24), fin_v, min(fin_v, 0.0) * 1.5, max(fin_v, 0.0))
            if ex:
                if inr:
                    ev.append((d, s, "exit", pos["sg"], round(rt / pos["u"], 2)))
                pos = None
    return out, ev


def ens_positions(px):
    """{UTC date: ensemble unit position held during that day} for one coin."""
    days = list(px); x = [px[d][2] for d in days]; n = len(x); ret = [float("nan")] + [x[i] / x[i - 1] - 1 for i in range(1, n)]; tot = [0.0] * n
    for hz, lb, band in VARIANTS:
        pos = 0.0
        for i in range(1, n):
            sig = sum(sgn(x[i - 1] / x[i - 1 - L] - 1) if i - 1 - L >= 0 else 0.0 for L in hz) / len(hz)
            w = ret[max(1, i - lb):i]; v = sd(w) if len(w) == lb and i - lb >= 1 else float("nan")
            tgt = sig * 0.5 / v if v == v and v > 0 else 0.0
            pos = tgt if abs(tgt - pos) > band * abs(tgt) else pos; tot[i] += pos / len(VARIANTS)
    return dict(zip(days, tot))


def coin_paths(d, p, pp, hourly, yd, side, swap=None, fund=None):
    """(CUM, LOW, FAV, used_hourly) by UTC hour of one coin on day d, unit position p (pp = previous day's)."""
    C, Lo, Fa = [0.0] * 24, [0.0] * 24, [0.0] * 24; T0 = epoch(d)
    if any(T0 + 3600 * h in hourly for h in range(24)):
        ts = sorted(t for t in hourly if t < T0 + 86400); cum = 0.0
        for h in range(24):
            t = T0 + 3600 * h; x = xl = xf = 0.0
            if t in hourly:
                j = ts.index(t); hi, lo, cl = hourly[t]; cp = hourly[ts[j - 1]][2] if j > 0 else cl
                cost = side * abs(p - pp) if h == 0 else 0.0
                carry = (p * fund / 3 if h in (7, 15, 23) else 0.0) if fund is not None else (abs(p) * swap if h == 23 else 0.0)
                r = cl / cp - 1; lr = (lo if p > 0 else hi) / cp - 1; fr = (hi if p > 0 else lo) / cp - 1
                x = p * r - cost - carry; xl = min(p * lr, p * r) - cost - carry; xf = max(p * fr, p * r) - cost - carry
            Lo[h] = cum + xl; Fa[h] = cum + xf; cum += x; C[h] = cum
        return C, Lo, Fa, True
    days = list(yd)
    if d in yd and days.index(d) > 0 and not (p == 0 and pp == 0):
        c0 = yd[days[days.index(d) - 1]][2]; hi, lo, cl = yd[d]; r = cl / c0 - 1
        lr = (lo if p > 0 else hi) / c0 - 1; fr = (hi if p > 0 else lo) / c0 - 1
        cost = side * abs(p - pp); carry = p * fund if fund is not None else abs(p) * swap
        x = p * r - cost - carry; xl = min(p * lr, p * r) - cost - carry; xf = max(p * fr, p * r) - cost - carry
        C[23] = x; Lo = [xl] * 24; Fa = [xf] * 24
    return C, Lo, Fa, False


# ---------------------------------------------------------------- streams
def cfd_stream(U, CR, ru, vc, g, oh):
    E = ru * U[0][23] + vc * 1000 * CR[0][23]; lh = [ru * U[1][h] + vc * 1000 * CR[1][h] for h in range(24)]
    Lo = min(min(lh), E, 0.0); A = E != 0
    pre = min(lh[:oh]); ato = lh[oh]
    if pre > -g and ato < -g:
        return ato, A, ato, "gap stop"
    if Lo < -g:
        return -g, A, -g, "stop"
    return E, A, Lo, ""


def perp_stream(PP, vt, ten):
    cum = [vt * c - ten for c in PP[0]]; low = [vt * c - ten for c in PP[1]]; E = cum[23]
    return E, E != 0, min(min(low), min(cum), 0.0), ""


def day_streams(d, Un, Unp, crc, crp, ten):
    """all five streams on day d, per $100K: (E, active, intraday low, note)."""
    z = ([0.0] * 24, [0.0] * 24, [0.0] * 24); oh = 9 + utc_off(d)
    return {"cfd": cfd_stream(Un.get(d, z), crc, RU, VC, GSTOP, oh), "cfd_ft": cfd_stream(Unp.get(d, z), crc, RU, VC, GSTOP, oh),
            "cfd_fnf": cfd_stream(Un.get(d, z), crc, RU_FN, 0.0, GSTOP, oh), "perp": perp_stream(crp, VT, 0.0), "perp_bf": perp_stream(crp, VT, VT * ten)}


# ---------------------------------------------------------------- account engine (research c341 sim_year, one path)
def new_account(key):
    P = ACCOUNTS[key]
    return dict(attempt=1, st=0, bal=0.0, td=0, best=0.0, since=0, wins=0, cyc=0.0, npay=0, refd=False, cash=-P["fee"], fees=P["fee"],
                payouts=0.0, dead=False, restart=False, start=None)


def step(a, key, S, d):
    """advance one account by one calendar day; S = day_streams(...). Returns (day P&L, events)."""
    P = ACCOUNTS[key]; s = P["s"]; nph = len(P["phases"]); F = P["funded"]; ev = []
    if a["start"] is None:
        a["start"] = str(d)
    if a["restart"]:
        a["restart"] = False
        if a["attempt"] >= MAX_ATT:
            a["dead"] = True; ev.append(f"stopped after {MAX_ATT} attempts")
        else:
            a.update(st=0, bal=0.0, td=0, best=0.0, since=0, wins=0, cyc=0.0, npay=0, refd=False); a["attempt"] += 1
            a["cash"] -= P["fee"]; a["fees"] += P["fee"]; ev.append(f"attempt {a['attempt']} starts (fee ${P['fee']:,.2f})")
    if a["dead"]:
        return 0.0, ev
    fu = a["st"] == nph; k = 1.0 if fu else P["cm"]
    E, A, Lo, note = S[P["fu"] if fu else P["ch"]]; pnl = E * s * k; low = min(Lo * s, 0.0) * k
    if note:
        ev.append(f"{note} (stream)")
    g = P["guard"] * s if P["guard"] else None
    if g is not None and low < -g:
        pnl = low = -g; ev.append(f"personal stop -${g:,.0f}")
    R = F if fu else P["phases"][a["st"]]
    if low < -R["dll"] * s or a["bal"] + low <= -R["mll"] * s:
        a["restart"] = True; ev.append(f"BREACH ({'daily' if low < -R['dll'] * s else 'max'} loss) in {'funded' if fu else 'phase ' + str(a['st'] + 1)}")
        return pnl, ev
    a["bal"] += pnl; a["td"] += bool(A); a["best"] = max(a["best"], pnl)
    if not fu:
        ph_ = P["phases"][a["st"]]; need = ph_["target"] * s
        if ph_["cons"]:
            need = max(need, a["best"] / ph_["cons"])
        if a["bal"] >= need and a["td"] >= ph_["min_days"]:
            ev.append(f"passed phase {a['st'] + 1}" + (" -> funded" if a["st"] + 1 == nph else "")); a.update(st=a["st"] + 1, bal=0.0, td=0, best=0.0)
        return pnl, ev
    a["since"] += 1; a["wins"] += pnl >= F.get("win_thr", 0.01); a["cyc"] += pnl
    wait = F["first_wait"] if a["npay"] == 0 else F["cycle"]; amt = min(F.get("cap", float("inf")) * s, a["bal"])
    if a["since"] >= wait and a["cyc"] >= 0.0 and amt >= max(F.get("min_pay", 0.0) * s, 1.0):
        a["cash"] += 0.8 * amt; a["payouts"] += 0.8 * amt; a["npay"] += 1; ev.append(f"payout ${0.8 * amt:,.2f}")
        if P["refund"] and not a["refd"] and a["npay"] >= P["refund_n"]:
            a["cash"] += P["fee"]; a["fees"] -= P["fee"]; ev.append(f"fee refund ${P['fee']:,.2f}")
        a["refd"] = a["refd"] or a["npay"] >= P["refund_n"]
        a["bal"] -= amt; a["since"] = 0; a["wins"] = 0; a["cyc"] = 0.0
    return pnl, ev


# ---------------------------------------------------------------- run
def fetch(rng="10y", rng5="60d"):
    data = {s: yahoo(s, rng) for s in US + ["^VIX"] + CRY}; f5 = {s: yahoo_5m(s, rng5) for s in FUT}
    return data, f5


def compute(data, f5, first, last, live_today=None, hourly=None, wait=False):
    """streams for every calendar day first..last. wait=True stops at the first day whose data are not complete yet."""
    vix = {d: v[2] for d, v in data["^VIX"].items()}; spx = {d: v[2] for d, v in data["^GSPC"].items()}; rut = {d: v[2] for d, v in data["^RUT"].items()}
    V = {s: us_votes(data[s], vix, spx, rut, list(data[s])) for s in US}
    Un, evn = us_paths(data, f5, V, first, last, False); Unp, evp = us_paths(data, f5, V, first, last, True)
    POS = {c: ens_positions(data[c]) for c in CRY}
    if hourly is None:
        hourly = {c: binance_hourly(BIN[c], first, last) for c in CRY}
    out = []; d = first
    while d <= last:
        age = (live_today - d).days if live_today else 99; notes = []
        if wait:
            session = d in data["^GSPC"] or (d.weekday() < 5 and d not in HOLIDAYS and not any(e > d for e in data["^GSPC"]))
            if any(d not in data[c] for c in CRY) or (session and any(d not in data[s] for s in US + ["^VIX"])):
                break                                         # daily bars not published yet
            if session and d in data["^GSPC"] and not any(d in f5[s] for s in FUT) and age <= 2:
                break                                         # 5-minute proxy bars not in yet
            if any(sum(1 for h in range(24) if epoch(d) + 3600 * h in hourly[c]) < 24 for c in CRY) and age <= 2:
                break                                         # Binance hourly bars incomplete
        crc = ([0.0] * 24, [0.0] * 24, [0.0] * 24); crp = ([0.0] * 24, [0.0] * 24, [0.0] * 24); absp = 0.0; fund = {}
        for c in CRY:
            days = list(POS[c]); p = POS[c].get(d, 0.0); j = days.index(d) if d in POS[c] else -1; pp = POS[c][days[j - 1]] if j > 0 else 0.0
            fr = funding_day(BIN[c], d)
            if fr is None:
                if wait and age <= 3:
                    return out, "waiting for premium-index files"
                fr = FUND_PRE; notes.append(f"{c} funding assumed 0.03%")
            fund[c] = fr; absp += abs(p)
            a = coin_paths(d, p, pp, hourly[c], data[c], CR_SIDE, swap=CR_SWAP); b = coin_paths(d, p, pp, hourly[c], data[c], PERP_SIDE, fund=fr)
            if not a[3]:
                notes.append(f"{c} no hourly bars, daily fallback")
            for X, Y in ((crc, a), (crp, b)):
                for i in range(3):
                    for h in range(24):
                        X[i][h] += Y[i][h]
        ten = 2 * PERP_SIDE * absp if (epoch(d) // 86400) % 10 == 0 else 0.0
        S = day_streams(d, Un, Unp, crc, crp, ten)
        evs = [f"{e[1]} {e[2]} {'long' if e[3] > 0 else 'short'} ({e[4]})" for e in evn if e[0] == d]
        evs += [f"FTMO book: {e[1]} {e[2]}" for e in evp if e[0] == d and e[2] != "exit" and e not in evn] + notes
        out.append(dict(date=d, S=S, events=evs, fund=fund, pos={c: POS[c].get(d, 0.0) for c in CRY}, us_open=sum(1 for e in evn if e[0] == d and e[2] == "entry")))
        d += timedelta(days=1)
    return out, ""


def backtest(a, b, path):
    a, b = date.fromisoformat(a), date.fromisoformat(b); data, f5 = fetch(); rows, _ = compute(data, f5, a, b)
    with open(path, "w", newline="") as f:
        w = csv.writer(f); keys = ["cfd", "cfd_ft", "cfd_fnf", "perp", "perp_bf"]
        w.writerow(["date"] + [f"{k}_{x}" for k in keys for x in ("E", "Lo")] + ["fund_btc", "fund_eth", "events"])
        for r in rows:
            w.writerow([r["date"].isoformat()] + [round(r["S"][k][i], 4) for k in keys for i in (0, 2)] + [round(r["fund"]["BTC-USD"], 8), round(r["fund"]["ETH-USD"], 8), "; ".join(r["events"])])


def main(stdir):
    os.makedirs(stdir, exist_ok=True); sp = os.path.join(stdir, "state.json")
    S = json.load(open(sp)) if os.path.exists(sp) else dict(last=str(START - timedelta(days=1)), acc={k: new_account(k) for k in ACCOUNTS})
    today = datetime.now(timezone.utc).date(); first = date.fromisoformat(S["last"]) + timedelta(days=1); upto = today - timedelta(days=1)
    if upto < first:
        print("nothing new"); return
    data, f5 = fetch()
    for c in CRY:                                            # drop the still-forming bar of the current UTC day
        data[c] = {d: v for d, v in data[c].items() if d < today}
    rows, why = compute(data, f5, first, upto, live_today=today, wait=True)
    if not rows:
        print(why or "waiting for data"); return
    keys = ["cfd", "cfd_ft", "cfd_fnf", "perp", "perp_bf"]; fs = os.path.join(stdir, "streams.csv"); fa = os.path.join(stdir, "accounts.csv")
    ns, na = not os.path.exists(fs), not os.path.exists(fa)
    with open(fs, "a", newline="") as f1, open(fa, "a", newline="") as f2:
        w1, w2 = csv.writer(f1), csv.writer(f2)
        if ns:
            w1.writerow(["date"] + [f"{k}_{x}" for k in keys for x in ("pnl", "low")] + ["btc_pos", "eth_pos", "fund_btc", "fund_eth", "events"])
        if na:
            w2.writerow(["date", "account", "attempt", "stage", "day_pnl", "balance", "cash_to_date", "events"])
        for r in rows:
            d = r["date"]
            w1.writerow([d.isoformat()] + [round(r["S"][k][i], 2) for k in keys for i in (0, 2)] + [round(r["pos"]["BTC-USD"], 4), round(r["pos"]["ETH-USD"], 4),
                        round(r["fund"]["BTC-USD"], 8), round(r["fund"]["ETH-USD"], 8), "; ".join(r["events"])])
            for k in ACCOUNTS:
                a = S["acc"][k]; pnl, ev = step(a, k, r["S"], d); nph = len(ACCOUNTS[k]["phases"])
                w2.writerow([d.isoformat(), k, a["attempt"], "dead" if a["dead"] else ("funded" if a["st"] == nph else f"phase {a['st'] + 1}"), round(pnl, 2),
                             round(a["bal"], 2), round(a["cash"], 2), "; ".join(ev)])
            book = sum(S["acc"][k]["cash"] for k in BOOK_B)
            print(d, " ".join(f"{k}={r['S'][k][0]:.0f}" for k in keys), f"book B cash {book:,.0f}", "; ".join(r["events"]))
    S["last"] = rows[-1]["date"].isoformat()
    S["book_B_cash"] = round(sum(S["acc"][k]["cash"] for k in BOOK_B), 2); S["book_Bplus_cash"] = round(S["book_B_cash"] + S["acc"]["BF100"]["cash"], 2)
    json.dump(S, open(sp, "w"), indent=1)
    if why:
        print(why)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--backtest":
        backtest(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "state"))
