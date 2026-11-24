"""C349F forward paper log of the C358 capped C349-only multi-account book. Log only: no orders, no account, nothing traded.

The C348F book (c348f/book_logger.py, loaded unchanged: US leg, BTC/ETH trend ensemble, data feeds, account engine) plus the C349
stablecoin-supply stream, at the C358 capped sizes (research_lab reports/c358/README.md; prereg claude/c349f-preregistration.md).
Amounts per $100K:
- C349 stream: 24 variants on DefiLlama total USD stablecoin supply S (stablecoins.llama.fi/stablecoincharts/all, peggedUSD, by UTC
  date). For L in (3, 7, 14, 28): g = log S - log S L days earlier, z = (g - 180-day mean of g) / 180-day sd (missing dates carried
  forward); day d uses z dated d-2. Mode A: long when z > th; mode B: also short when z < -th; th in (0, 0.5, 1.0). The same sign on
  BTC and ETH, size 0.5 / sd20 per coin (sd of the 20 daily returns ending d-1, Binance USD-M hour-23 closes). Each calendar month
  trades the variant with the best Sharpe over the 3 previous calendar months (perp costs, Binance funding; research S3 route).
- No look-ahead from DefiLlama revisions: every run freezes the signals of the next 4 UTC days from the snapshot it has just fetched
  (a later run before the day starts overwrites them; each freeze is logged in freezes.csv), and keeps the last snapshot fetched
  before each month starts for that month's pick. A day without a frozen signal carries the latest earlier one ("stale signal"); a
  month without a pre-month snapshot trades C349 flat.
- CFD book: FundedNext challenge: US 1.5 units + crypto $1,000 x (ensemble + 0.5 x C349); funded stage: US 0.75, crypto off.
  FTMO: US 1.25 units (no entry on the last session before a closure) + crypto $750 x (ensemble + 1.0 x C349). Gap-aware -4% stop.
  C349 at CFD costs: 0.10% of the position change, 0.082% swap per day on |position| (as c358 cfd_hourly).
- Perp book: $1,000 x (ensemble + 0.75 x C349) per unit. C349 at perp costs: 0.075% of the change at 00:00 UTC and funding q x rate at
  each 00/08/16 UTC settlement (rates estimated from the premium index as C348F; 0.03%/day when the files stay missing). Costs are
  charged on each component's own position, not netted (as research). CFT 2-Phase: challenge x1.5, -4% personal stop; CFT 1-Step:
  x1.0, -1.5%; HyroTrader: x1.0, -3%; Bitfunded: x1.5, -3%, closes and reopens both components every 10th day.
- Accounts, fees, rules and engine as C348F (research c341 sim_year on one path, at most 3 attempts). Book B = FundedNext 200K, FTMO
  200K, CFT 2-Phase 200K, CFT 1-Step 100K, HyroTrader 200K; B+ adds Bitfunded 100K.
Usage: python3 book_logger.py [STATE_DIR] | python3 book_logger.py --backtest START END OUT.csv [SNAPSHOT.json]  (for checking against research)
"""
import csv, importlib.util, io, json, math, os, sys, zipfile
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("c348f_logger", os.path.join(HERE, "..", "c348f", "book_logger.py"))
base = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(base)

START = date.fromisoformat(os.environ.get("C349F_START", "2026-12-01"))
STABLE_URL = "https://stablecoins.llama.fi/stablecoincharts/all"
CRY, BIN = base.CRY, base.BIN
LS = (3, 7, 14, 28); VARS = [(L, m, th) for L in LS for m in "AB" for th in (0.0, 0.5, 1.0)]; NAMES = [f"L{L}_{m}_th{th}" for L, m, th in VARS]
CFD_CFG = {"cfd_fn": (1.5, 1.0, 0.5), "cfd_ft": (1.25, 0.75, 1.0)}     # (US units, crypto $1,000s per unit, C349 weight)
GSTOP, RU_FN, VT, W349, AHEAD = 4000.0, 0.75, 1000.0, 0.75, 4
SIDE, CR_SIDE, CR_SWAP, FUND_PRE = 0.00075, base.CR_SIDE, base.CR_SWAP, base.FUND_PRE
KINDS = ["cfd_fn", "cfd_ft", "cfd_fnf", "perp", "perp_bf"]

ACCOUNTS = {k: dict(v) for k, v in base.ACCOUNTS.items()}
ACCOUNTS["FN200"].update(ch="cfd_fn")
ACCOUNTS["C2P200"].update(cm=1.5, guard=4000.0)
ACCOUNTS["C1S100"].update(name="CFT 1-Step Classic 100K (1.5% stop)", cm=1.0, guard=1500.0)
ACCOUNTS["HY200"].update(cm=1.0, guard=3000.0)
ACCOUNTS["BF100"].update(cm=1.5, guard=3000.0)
base.ACCOUNTS = ACCOUNTS            # the C348F engine (research sim_year, checked exact) runs on this book's account table
BOOK_B = base.BOOK_B
D1 = timedelta(days=1)


# ---------------------------------------------------------------- stablecoin signal
def stable_fetch():
    """{UTC date: total circulating USD-pegged supply} from DefiLlama, None on failure."""
    try:
        d = base.get(STABLE_URL)
    except Exception as e:
        print("DefiLlama fetch failed:", e); return None
    if not d:
        return None
    S = {}
    for r in d:
        v = (r.get("totalCirculatingUSD") or {}).get("peggedUSD")
        S[datetime.fromtimestamp(int(r["date"]), timezone.utc).date()] = float(v) if v is not None else float("nan")
    return dict(sorted(S.items()))


class Stable:
    """log supply on a daily calendar (missing dates and NaN carried forward, as research reindex + ffill); z(t) = [z3, z7, z14, z28]
    dated t, which uses only values dated <= t."""
    def __init__(self, S, upto):
        self.t0 = min(S); cur = float("nan"); self.ls = []
        for i in range((upto - self.t0).days + 1):
            v = S.get(self.t0 + timedelta(days=i))
            if v is not None and v == v and v > 0:
                cur = math.log(v)
            self.ls.append(cur)

    def z(self, t):
        i = (t - self.t0).days; out = []
        for L in LS:
            if i - 179 - L < 0 or i >= len(self.ls):
                out.append(float("nan")); continue
            g = [self.ls[j] - self.ls[j - L] for j in range(i - 179, i + 1)]
            if any(x != x for x in g):
                out.append(float("nan")); continue
            m = sum(g) / 180; s = math.sqrt(sum((x - m) ** 2 for x in g) / 179)
            out.append((g[-1] - m) / s if s > 0 else float("nan"))
        return out


def signs(z):
    """24 variant signals from [z3, z7, z14, z28] (NaN -> 0)."""
    if z is None:
        return [0] * len(VARS)
    out = []
    for L, m, th in VARS:
        x = z[LS.index(L)]
        out.append(0 if x != x else (1 if x > th else 0) - (1 if m == "B" and x < -th else 0))
    return out


# ---------------------------------------------------------------- Binance data
def _sec(x):
    t = int(x); t = t // 1000 if t > 1e14 else t; return t // 1000


def months_between(a, b):
    y, m = a.year, a.month
    while (y, m) <= (b.year, b.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def month_end(y, m):
    return (date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)) - D1


def add_months(d, k):
    n = d.year * 12 + d.month - 1 + k; return date(n // 12, n % 12 + 1, 1)


MZ = {}


def monthly_rows(kind, bsym, y, m):
    """rows of a data.binance.vision futures/um monthly file (1h klines or fundingRate), None if not published."""
    key = (kind, bsym, y, m)
    if key not in MZ:
        path = f"klines/{bsym}/1h/{bsym}-1h-{y}-{m:02d}" if kind == "klines" else f"fundingRate/{bsym}/{bsym}-fundingRate-{y}-{m:02d}"
        raw = base.get(f"https://data.binance.vision/data/futures/um/monthly/{path}.zip", binary=True); rows = None
        if raw:
            z = zipfile.ZipFile(io.BytesIO(raw)); rows = [r for r in csv.reader(io.StringIO(z.read(z.namelist()[0]).decode())) if r and r[0][:1].isdigit()]
        MZ[key] = rows
    return MZ[key]


def hourly_range(bsym, a, b, today):
    """{hour start (s): (high, low, close)} of Binance USD-M 1h bars for UTC days a-1..b: monthly files for months that ended before
    today's month, daily files otherwise (and when a monthly file is not out yet)."""
    out = {}; cur = today.replace(day=1)
    for y, m in months_between(a - D1, b):
        rows = monthly_rows("klines", bsym, y, m) if month_end(y, m) < cur else None
        if rows:
            for r in rows:
                out[_sec(r[0])] = (float(r[2]), float(r[3]), float(r[4]))
            continue
        d = max(a - D1, date(y, m, 1))
        while d <= min(b, month_end(y, m)):
            if (bsym, d) not in base.KL:
                base.KL[(bsym, d)] = base.daily_zip("klines", bsym, d)
            for t, r in (base.KL[(bsym, d)] or {}).items():
                out[t] = (float(r[2]), float(r[3]), float(r[4]))
            d += D1
    return out


def closes_ffill(hourly, a, b):
    """{hour start (s): close} for every hour of days a..b, the last available close carried forward (research ffill)."""
    t0, t1 = base.epoch(a), base.epoch(b) + 23 * 3600; prior = [t for t in hourly if t < t0]
    cur = hourly[max(prior)][2] if prior else None; out = {}; t = t0
    while t <= t1:
        if t in hourly:
            cur = hourly[t][2]
        out[t] = cur; t += 3600
    return out


def unit(CF, d):
    """0.5 / sd of the 20 daily returns ending d-1 (hour-23 closes), 0 when undefined (research nan_to_num(0.5 / sd20))."""
    c = [CF.get(base.epoch(d - timedelta(days=k)) + 23 * 3600) for k in range(21, 0, -1)]
    if any(x is None for x in c):
        return 0.0
    r = [c[i] / c[i - 1] - 1 for i in range(1, 21)]; s = base.sd(r)
    return 0.5 / s if s > 0 else 0.0


def day_ret(CF, d):
    """sum of the 24 hourly returns of day d (research daily_pnl_fast RS)."""
    t0 = base.epoch(d); return sum(CF[t0 + 3600 * h] / CF[t0 + 3600 * h - 3600] - 1 for h in range(24))


def funding_sums(bsym, days, today):
    """{day: sum of funding rates stamped that UTC day}: actual rates from Binance monthly files (as research), the premium-index
    estimate for months whose file is not out (0.03%/day if that is missing too). Also returns the sources used."""
    out, src = {d: 0.0 for d in days}, set(); cur = today.replace(day=1)
    for y, m in months_between(days[0], days[-1]):
        rows = monthly_rows("fundingRate", bsym, y, m) if month_end(y, m) < cur else None
        if rows:
            src.add("file")
            for r in rows:
                d = datetime.fromtimestamp(_sec(r[0]) // 3600 * 3600, timezone.utc).date()
                if d in out:
                    out[d] += float(r[-1])
            continue
        for d in days:
            if (d.year, d.month) == (y, m):
                f = base.funding_day(bsym, d); out[d] = FUND_PRE if f is None else f; src.add("estimate" if f is not None else "assumed")
    return out, src


def funding_rates(bsym, d):
    """the three estimated funding rates stamped 00:00, 08:00, 16:00 UTC on day d (c348f funding_day, kept per settlement)."""
    pa, pb = base.premium_day(bsym, d - D1), base.premium_day(bsym, d)
    if pa is None or pb is None:
        return None
    pm = dict(pa); pm.update(pb); T0 = base.epoch(d); out = []
    for T in (T0, T0 + 28800, T0 + 57600):
        num = den = 0.0
        for i in range(480):
            v = pm.get(T - 28800 + 60 * i)
            if v is not None:
                num += (i + 1) * v; den += i + 1
        if den == 0:
            return None
        P = num / den; out.append(max(min(P + min(max(0.0001 - P, -0.0005), 0.0005), 0.003), -0.003))
    return out


# ---------------------------------------------------------------- C349 route
def sharpe(x):
    m = sum(x) / len(x); s = math.sqrt(sum((v - m) ** 2 for v in x) / len(x))
    return m / s * math.sqrt(365) if s > 0 else float("-inf")


def pick_month(M1, snap, today):
    """research c349_lib.select for the month starting M1: the variant with the best Sharpe over the 3 previous calendar months."""
    W0, W1 = add_months(M1, -3), M1 - D1; days = [W0 + timedelta(days=i) for i in range((W1 - W0).days + 1)]
    st = Stable(snap, W1); sig = {d: signs(st.z(d - 2 * D1)) for d in [W0 - D1] + days}
    P = [[0.0] * len(days) for _ in VARS]; src = set()
    for c in CRY:
        lo = W0 - timedelta(days=23); CF = closes_ffill(hourly_range(BIN[c], lo, W1, today), lo, W1)
        FS, s = funding_sums(BIN[c], days, today); src |= s; U = {d: unit(CF, d) for d in [W0 - D1] + days}; R = {d: day_ret(CF, d) for d in days}
        for k in range(len(VARS)):
            qp = sig[W0 - D1][k] * U[W0 - D1]
            for i, d in enumerate(days):
                q = sig[d][k] * U[d]; P[k][i] += q * R[d] - SIDE * abs(q - qp) - q * FS[d]; qp = q
    sh = [sharpe(p) for p in P]; k = max(range(len(sh)), key=lambda i: (sh[i], -i))
    return dict(k=k, name=NAMES[k], sharpe=round(sh[k], 4), all=[round(x, 3) if x != float("-inf") else None for x in sh], funding=sorted(src),
                window=f"{W0}..{W1}")


def get_pick(S, d, today, snap=None):
    key = d.isoformat()[:7]
    if key not in S["pick"]:
        M1 = d.replace(day=1); ps = snap
        if ps is None and M1.isoformat() in S["presnap"]:
            p = S["presnap"][M1.isoformat()]; ps = {date.fromisoformat(a): v for a, v in p["S"].items()}
        if ps is None:
            S["pick"][key] = dict(k=None, why="no pre-month snapshot: C349 flat")
        else:
            S["pick"][key] = pick_month(M1, ps, today)
            if snap is None:
                S["pick"][key]["snapshot"] = S["presnap"][M1.isoformat()]["t"]
    p = S["pick"][key]; notes = []
    if d.day == 1 or d == START:
        notes.append(f"C349 pick {key}: {p['name']} (trailing Sharpe {p['sharpe']}, funding {'/'.join(p['funding'])})" if p["k"] is not None else f"C349 {p['why']}")
    return p["k"], notes


def get_sig(S, d, stable=None):
    if stable is not None:
        return signs(stable.z(d - 2 * D1)), []
    key = d.isoformat()
    if key in S["sig"]:
        return S["sig"][key]["s"], []
    older = [k for k in S["sig"] if k < key]
    if older:
        return S["sig"][max(older)]["s"], [f"C349 stale signal (frozen for {max(older)})"]
    return None, ["C349 no frozen signal: flat"]


def freeze(S, stdir, now):
    """freeze the next AHEAD days' signals and the next month's pre-month snapshot from a fresh DefiLlama snapshot."""
    snap = stable_fetch()
    if not snap:
        return "DefiLlama snapshot failed: nothing frozen this run"
    T = now.date(); last = max(snap); st = Stable(snap, T + timedelta(days=AHEAD)); rows = []
    for i in range(1, AHEAD + 1):
        D = T + timedelta(days=i)
        if D < START:
            continue
        z = st.z(D - 2 * D1); sg = signs(z)
        S["sig"][D.isoformat()] = dict(t=now.isoformat(timespec="seconds"), s=sg, z=[None if x != x else round(x, 4) for x in z], last=last.isoformat())
        rows.append([now.isoformat(timespec="seconds"), D.isoformat(), last.isoformat(), snap.get(D - 2 * D1, "")] + [None if x != x else round(x, 4) for x in z] + [" ".join(map(str, sg))])
    M1 = add_months(T.replace(day=1), 1)
    if M1 >= START:
        S["presnap"][M1.isoformat()] = dict(t=now.isoformat(timespec="seconds"), last=last.isoformat(),
                                            S={d.isoformat(): v for d, v in snap.items() if d >= M1 - timedelta(days=420) and v == v})
    fz = os.path.join(stdir, "freezes.csv"); new = not os.path.exists(fz)
    with open(fz, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["run_utc", "day", "snapshot_last_date", "supply_d-2", "z3", "z7", "z14", "z28", "signals"])
        w.writerows(rows)
    return f"froze {', '.join(r[1] for r in rows) or 'no days (before start)'}; pre-month snapshot for {M1}" if M1 >= START else ""


# ---------------------------------------------------------------- paths and streams
def c349_paths(d, q, qp, hourly, CF, yd, cfd, rates=None):
    """(CUM, LOW, FAV, used_hourly) by UTC hour of the C349 position q on day d (qp = previous day's), per $1 of scale.
    Perp as research c349_lib.hourly_pnl; CFD as c358 cfd_hourly. A day with no hourly bar uses the Yahoo daily fallback of C348F."""
    T0 = base.epoch(d)
    if not any(T0 + 3600 * h in hourly for h in range(24)):
        r = base.coin_paths(d, q, qp, {}, yd, CR_SIDE if cfd else SIDE, swap=CR_SWAP if cfd else None, fund=None if cfd else sum(rates))
        return r[0], r[1], r[2], False
    C, Lo, Fa = [0.0] * 24, [0.0] * 24, [0.0] * 24; cum = 0.0
    for h in range(24):
        t = T0 + 3600 * h; cp, cl = CF[t - 3600], CF[t]; hi, lo = hourly[t][:2] if t in hourly else (cl, cl)
        r, up, dn = cl / cp - 1, hi / cp - 1, lo / cp - 1
        b = -(CR_SIDE if cfd else SIDE) * abs(q - qp) if h == 0 else 0.0
        if cfd:
            b -= CR_SWAP * abs(q) if h == 23 else 0.0
        elif h in (0, 8, 16):
            b -= q * rates[h // 8]
        adv, fav = (dn, up) if q > 0 else (up, dn)
        x = q * r + b; Lo[h] = cum + min(q * adv, q * r) + b; Fa[h] = cum + max(q * fav, q * r) + b; cum += x; C[h] = cum
    return C, Lo, Fa, True


def mix(A, X, w):
    return tuple([A[i][h] + w * X[i][h] for h in range(24)] for i in range(3))


def day_streams(d, Un, Unp, crc, crp, xc, xp, ten):
    """all five streams on day d, per $100K: (E, active, intraday low, note)."""
    z = ([0.0] * 24, [0.0] * 24, [0.0] * 24); oh = 9 + base.utc_off(d); out = {}
    for k, U in (("cfd_fn", Un), ("cfd_ft", Unp)):
        ru, vc, w = CFD_CFG[k]; out[k] = base.cfd_stream(U.get(d, z), mix(crc, xc, w), ru, vc, GSTOP, oh)
    out["cfd_fnf"] = base.cfd_stream(Un.get(d, z), crc, RU_FN, 0.0, GSTOP, oh)
    pp = mix(crp, xp, W349); out["perp"] = base.perp_stream(pp, VT, 0.0); out["perp_bf"] = base.perp_stream(pp, VT, ten)
    return out


def zeros3():
    return ([0.0] * 24, [0.0] * 24, [0.0] * 24)


def add3(X, Y):
    for i in range(3):
        for h in range(24):
            X[i][h] += Y[i][h]


def compute(data, f5, first, last, S, today, wait=False, snap=None):
    """streams for every calendar day first..last (as c348f compute, plus C349). wait=True stops at the first day whose data are not
    complete yet. snap: check mode, one snapshot for every signal and pick (research style) instead of the frozen ones."""
    vix = {d: v[2] for d, v in data["^VIX"].items()}; spx = {d: v[2] for d, v in data["^GSPC"].items()}; rut = {d: v[2] for d, v in data["^RUT"].items()}
    V = {s: base.us_votes(data[s], vix, spx, rut, list(data[s])) for s in base.US}
    Un, evn = base.us_paths(data, f5, V, first, last, False); Unp, evp = base.us_paths(data, f5, V, first, last, True)
    POS = {c: base.ens_positions(data[c]) for c in CRY}; lo = first - timedelta(days=25)
    H = {c: hourly_range(BIN[c], lo, last, today) for c in CRY}; CF = {c: closes_ffill(H[c], lo, last) for c in CRY}
    stable = Stable(snap, last) if snap is not None else None; qprev = S.get("q349") or {c: 0.0 for c in CRY}; out = []; d = first
    while d <= last:
        age = (today - d).days; notes = []
        if wait:
            session = d in data["^GSPC"] or (d.weekday() < 5 and d not in base.HOLIDAYS and not any(e > d for e in data["^GSPC"]))
            if any(d not in data[c] for c in CRY) or (session and any(d not in data[s] for s in base.US + ["^VIX"])):
                break                                         # daily bars not published yet
            if session and d in data["^GSPC"] and not any(d in f5[s] for s in base.FUT) and age <= 2:
                break                                         # 5-minute proxy bars not in yet
            if any(sum(1 for h in range(24) if base.epoch(d) + 3600 * h in H[c]) < 24 for c in CRY) and age <= 2:
                break                                         # Binance hourly bars incomplete
        rates = {}
        for c in CRY:
            r = funding_rates(BIN[c], d)
            if r is None:
                if wait and age <= 3:
                    return out, "waiting for premium-index files"
                r = [FUND_PRE / 3] * 3; notes.append(f"{c} funding assumed 0.03%")
            rates[c] = r
        k, kn = get_pick(S, d, today, snap); sg, sn = get_sig(S, d, stable); notes += kn + sn
        q = {c: (sg[k] * unit(CF[c], d) if k is not None and sg is not None else 0.0) for c in CRY}
        crc, crp, xc, xp = zeros3(), zeros3(), zeros3(), zeros3(); absp = 0.0; fund = {}
        for c in CRY:
            days = list(POS[c]); p = POS[c].get(d, 0.0); j = days.index(d) if d in POS[c] else -1; pp = POS[c][days[j - 1]] if j > 0 else 0.0
            fr = sum(rates[c]); fund[c] = fr; absp += abs(p)
            a = base.coin_paths(d, p, pp, H[c], data[c], base.CR_SIDE, swap=base.CR_SWAP); b = base.coin_paths(d, p, pp, H[c], data[c], base.PERP_SIDE, fund=fr)
            if not a[3]:
                notes.append(f"{c} no hourly bars, daily fallback")
            add3(crc, a[:3]); add3(crp, b[:3])
            add3(xc, c349_paths(d, q[c], qprev[c], H[c], CF[c], data[c], True)[:3]); add3(xp, c349_paths(d, q[c], qprev[c], H[c], CF[c], data[c], False, rates[c])[:3])
        ten = VT * (2 * base.PERP_SIDE * absp + W349 * 2 * SIDE * sum(abs(q[c]) for c in CRY)) if (base.epoch(d) // 86400) % 10 == 0 else 0.0
        St = day_streams(d, Un, Unp, crc, crp, xc, xp, ten)
        evs = [f"{e[1]} {e[2]} {'long' if e[3] > 0 else 'short'} ({e[4]})" for e in evn if e[0] == d]
        evs += [f"FTMO book: {e[1]} {e[2]}" for e in evp if e[0] == d and e[2] != "exit" and e not in evn] + notes
        out.append(dict(date=d, S=St, events=evs, fund=fund, pos={c: POS[c].get(d, 0.0) for c in CRY}, q349=q, pick=NAMES[k] if k is not None else "",
                        sig=sg[k] if k is not None and sg is not None else 0, x349=(xp[0][23], min(xp[1]), xc[0][23], min(xc[1])), ens_perp=crp[0][23]))
        qprev = q; d += D1
    return out, ""


# ---------------------------------------------------------------- run
def new_state():
    return dict(last=str(START - D1), acc={k: base.new_account(k) for k in ACCOUNTS}, sig={}, presnap={}, pick={}, q349=None)


def load_snapshot(path):
    d = json.load(open(path)); S = {}
    for r in d:
        v = (r.get("totalCirculatingUSD") or {}).get("peggedUSD"); S[datetime.fromtimestamp(int(r["date"]), timezone.utc).date()] = float(v) if v is not None else float("nan")
    return dict(sorted(S.items()))


def backtest(a, b, path, snapfile=None):
    """check mode: streams a..b with one DefiLlama snapshot (a file, or fetched now) for all signals and picks, as research did."""
    a, b = date.fromisoformat(a), date.fromisoformat(b); today = datetime.now(timezone.utc).date()
    snap = load_snapshot(snapfile) if snapfile else stable_fetch(); S = new_state(); data, f5 = base.fetch()
    rows, _ = compute(data, f5, a - D1, b, S, today, snap=snap); rows = rows[1:]       # day a-1 seeds the route's prior position
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "pick", "sig", "q_btc", "q_eth", "x349_perp_E", "x349_perp_lowmin", "x349_cfd_E", "x349_cfd_lowmin"]
                   + [f"{k}_{x}" for k in KINDS for x in ("E", "Lo")] + ["ens_perp_E", "fund_btc", "fund_eth", "events"])
        for r in rows:
            w.writerow([r["date"].isoformat(), r["pick"], r["sig"], round(r["q349"]["BTC-USD"], 6), round(r["q349"]["ETH-USD"], 6)] + [round(x, 8) for x in r["x349"]]
                       + [round(r["S"][k][i], 4) for k in KINDS for i in (0, 2)] + [round(r["ens_perp"], 8), round(r["fund"]["BTC-USD"], 8), round(r["fund"]["ETH-USD"], 8), "; ".join(r["events"])])
    print("picks", {k: v.get("name") for k, v in S["pick"].items()})


def main(stdir):
    os.makedirs(stdir, exist_ok=True); sp = os.path.join(stdir, "state.json")
    S = json.load(open(sp)) if os.path.exists(sp) else new_state()
    now = datetime.now(timezone.utc); today = now.date()
    msg = freeze(S, stdir, now); json.dump(S, open(sp, "w"), indent=1)                # saved at once: a later failure keeps the freeze
    if msg:
        print(msg)
    first = date.fromisoformat(S["last"]) + D1; upto = today - D1
    if upto < first:
        print("nothing new to log" + (f" (log starts {START})" if first == START else "")); return
    data, f5 = base.fetch()
    for c in CRY:                                            # drop the still-forming bar of the current UTC day
        data[c] = {d: v for d, v in data[c].items() if d < today}
    rows, why = compute(data, f5, first, upto, S, today, wait=True)
    if not rows:
        print(why or "waiting for data"); return
    fs, fa = os.path.join(stdir, "streams.csv"), os.path.join(stdir, "accounts.csv"); ns, na = not os.path.exists(fs), not os.path.exists(fa)
    with open(fs, "a", newline="") as f1, open(fa, "a", newline="") as f2:
        w1, w2 = csv.writer(f1), csv.writer(f2)
        if ns:
            w1.writerow(["date"] + [f"{k}_{x}" for k in KINDS for x in ("pnl", "low")] + ["ens_btc_pos", "ens_eth_pos", "c349_pick", "c349_sig", "c349_btc_pos",
                        "c349_eth_pos", "c349_perp_per1000", "c349_cfd_per1000", "ens_perp_per1000", "fund_btc", "fund_eth", "events"])
        if na:
            w2.writerow(["date", "account", "attempt", "stage", "day_pnl", "balance", "cash_to_date", "events"])
        for r in rows:
            d = r["date"]
            w1.writerow([d.isoformat()] + [round(r["S"][k][i], 2) for k in KINDS for i in (0, 2)] + [round(r["pos"]["BTC-USD"], 4), round(r["pos"]["ETH-USD"], 4),
                        r["pick"], r["sig"], round(r["q349"]["BTC-USD"], 4), round(r["q349"]["ETH-USD"], 4), round(1000 * r["x349"][0], 2), round(1000 * r["x349"][2], 2),
                        round(1000 * r["ens_perp"], 2), round(r["fund"]["BTC-USD"], 8), round(r["fund"]["ETH-USD"], 8), "; ".join(r["events"])])
            for k in ACCOUNTS:
                a = S["acc"][k]; pnl, ev = base.step(a, k, r["S"], d); nph = len(ACCOUNTS[k]["phases"])
                w2.writerow([d.isoformat(), k, a["attempt"], "dead" if a["dead"] else ("funded" if a["st"] == nph else f"phase {a['st'] + 1}"), round(pnl, 2),
                             round(a["bal"], 2), round(a["cash"], 2), "; ".join(ev)])
            book = sum(S["acc"][k]["cash"] for k in BOOK_B)
            print(d, " ".join(f"{k}={r['S'][k][0]:.0f}" for k in KINDS), f"C349 {r['pick']} {r['sig']:+d}", f"book B cash {book:,.0f}", "; ".join(r["events"]))
    S["last"] = rows[-1]["date"].isoformat(); S["q349"] = rows[-1]["q349"]
    S["book_B_cash"] = round(sum(S["acc"][k]["cash"] for k in BOOK_B), 2); S["book_Bplus_cash"] = round(S["book_B_cash"] + S["acc"]["BF100"]["cash"], 2)
    json.dump(S, open(sp, "w"), indent=1)
    if why:
        print(why)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--backtest":
        backtest(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5] if len(sys.argv) > 5 else None)
    else:
        main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "state"))
