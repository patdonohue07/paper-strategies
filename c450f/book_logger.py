"""C450F forward paper log of the final C450 prop book (research_lab reports/c449/README.md and c450/README.md; frozen by research_lab
code/c451_freeze.py and code/c451_book.py into c450f/book.json). Log only: no orders, no account, nothing traded.

Book: 18 frozen entries, 48 accounts; copies of one entry follow one identical path. Every account starts one attempt on 2026-12-01
and is followed for 365 UTC days; day-360 cash is the research comparison point. Research valued each account with one attempt,
so a breach ends the account here too.
Streams (c348f data feeds and helpers, loaded unchanged):
- US legs: the US swing rule (C320 8-vote score, |score| >= 5, 1.5 x ATR14 stop, 2R target, 7 sessions) as c348f us_paths, on
  four indices (US4) or without the Russell (US3).
- Crypto legs: the BTC/ETH trend ensemble (c348f ens_positions) at CFD or perp costs (c348f coin_paths); BTC+ETH (C2) or BTC only.
- Per-day crypto exposure caps (research c445 / c446): Instant Funding 1x of BTC+ETH notional, FTMO US 1x of BTC notional, FunderPro
  1x in evaluation and 0.2x crypto / 2x US notional funded.
- Daily-loss offsets in the engine (open P&L at the reset):
  - FTMO US, Ment, FunderPro: losing positions closed and reopened at the reset (research c445 realize_us / realize_crypto, round
    turn 2 bp US and 20 bp crypto charged that day).
  - CTI: open P&L as is (research c442 open_us / open_crypto).
  - Instant Funding and Velotrade: min(0, open), their limits use the higher of balance or equity (research c450).
- CFT: the $10K daily profit cap after each stage's size multiplier, and the per-trade cap: a position is closed and reopened at $8K
  open profit (15 bp of notional) and any excess above $10K is cut (research c449 / c450).
- Futures:
  - three-down (research c432): long the next CME session after three down cash-index closes (ES, NQ, RTY);
    n = floor(risk / (1.5 x ATR14 x close x point value)) micros, at most 50, scaled to the firm's cap on total micros;
    costs $0.70 plus one tick per side per micro.
  - BluSky: the K-rule trend, session-chained, as c390f fut_streams.
  - Session P&L uses Yahoo 5-minute futures bars from 18:00 ET to 16:10 ET; research used 1-minute bars to 16:09.
  - Not modelled here: research's news flattening (MFFU Pro funded, Topstep), about -$15 to -$33 per account a year.
Engine: c390f step (research c341 sim_year with the C402 fixes, checked against research c402_engine) plus the research C440-C447 keys
this book uses:
- dll_off with the clamp;
- phase_mult;
- qualifying days (min_day_thr / min_day_cost, win_days_first / win_thr_first / win_cost_first);
- pay_gap, cushion, max_pays, cap_forfeit (HyroTrader);
- one attempt.
Usage: python3 book_logger.py [STATE_DIR] | python3 book_logger.py --backtest START END OUT.csv
"""
import csv, importlib.util, json, math, os, sys, urllib.request
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("c348f_logger", os.path.join(HERE, "..", "c348f", "book_logger.py"))
base = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(base)
INF = float("inf")


def _num(x):
    if isinstance(x, dict):
        return {k: _num(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_num(v) for v in x]
    return INF if x == "inf" else (-INF if x == "-inf" else x)


BOOK = _num(json.load(open(os.path.join(HERE, "book.json")))); ENT = {e["id"]: e for e in BOOK["entries"]}
START = date.fromisoformat(os.environ.get("C450F_START", "2026-12-01")); END = START + timedelta(days=364); HORIZON = 360
US4 = ["^GSPC", "^NDX", "^RUT", "^DJI"]; US3 = ["^GSPC", "^NDX", "^DJI"]; TD_IDX = ["^GSPC", "^NDX", "^RUT"]
MICRO = {"^GSPC": (5.0, 0.25), "^NDX": (2.0, 0.25), "^RUT": (5.0, 0.10), "^DJI": (0.5, 1.0)}   # point value $, tick (MES MNQ M2K MYM)
FUTP = {"^GSPC": "ES=F", "^NDX": "NQ=F", "^RUT": "RTY=F"}; COMM, MAXC, MAX_ATT = 0.70, 50, 1
Z24 = ([0.0] * 24, [0.0] * 24, [0.0] * 24)


# ---------------------------------------------------------------- data
def yahoo_5m_all(sym, rng="60d"):
    """{ET datetime: (open, high, low, close)} 5-minute futures bars, all hours (the session runs 18:00 -> 17:00 ET)."""
    d = base.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(sym)}?range={rng}&interval=5m")
    r = d["chart"]["result"][0]; q = r["indicators"]["quote"][0]; out = {}
    for i, t in enumerate(r.get("timestamp", [])):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            continue
        out[datetime.fromtimestamp(t, base.ET)] = (o, h, l, c)
    return dict(sorted(out.items()))


def fetch():
    data, f5 = base.fetch(); f5a = {s: yahoo_5m_all(FUTP[s]) for s in TD_IDX}
    return data, f5, f5a


# ---------------------------------------------------------------- daily-loss offsets, notional, crypto per-trade costs (full history)
def k5_positions(V, data, idx):
    """per index: list of (day i, position dict or None) for the K5 rule (entries at the close, 1.5 ATR stop, 2R, 7 sessions)."""
    out = {}
    for s in idx:
        days = list(data[s]); sc, atr, C = V[s]; pos = None; seq = []
        for i, d in enumerate(days):
            if pos is None:
                if d in sc and abs(sc[d]) >= 5 and d in atr:
                    pos = dict(sg=base.sgn(sc[d]), e=C[i], b=C[i], u=1.5 * atr[d], n=1000.0 / (1.5 * atr[d]), i0=i); seq.append((d, i, "entry", dict(pos)))
                continue
            seq.append((d, i, "held", pos)); rt = pos["sg"] * (C[i] / pos["e"] - 1)
            if rt <= -pos["u"] or rt >= 2 * pos["u"] or i - pos["i0"] >= 7:
                pos = None
        out[s] = (days, C, seq)
    return out


def us_offsets(K5, idx, realize):
    """{date: (offset, cost, notional)} per $100K at ru 1: open P&L at the reset before day d (prior close vs basis); realize=True closes
    and reopens losing positions there (basis -> prior close, 2 bp round turn) and keeps only open profits (research c445 realize_us);
    realize=False is research c442 open_us. Notional is research c347 US_NOT (entry day n, held days n x close / entry)."""
    out = {}
    for s in idx:
        days, C, seq = K5[s]; st = {}
        for d, i, kind, pos in seq:
            o = out.setdefault(d, [0.0, 0.0, 0.0])
            if kind == "entry":
                o[2] += pos["n"]; st = dict(pos); continue
            if st.get("i0") != pos["i0"]:
                st = dict(pos)
            o[2] += st["n"] * C[i] / st["e"]
            if realize:
                op = st["sg"] * st["n"] * (C[i - 1] / st["b"] - 1)
                if op < 0:
                    o[1] += 2e-4 * st["n"] * C[i - 1] / st["b"]; st["b"] = C[i - 1]; op = 0.0
            else:
                op = st["sg"] * st["n"] * (C[i - 1] / st["e"] - 1)
            o[0] += op
    return out


def crypto_offsets(data, POS, coins, realize, rt=2e-3):
    """{date: (offset, cost)} per $100K at vc 1, average-cost basis per coin (research c445 realize_crypto / c442 open_crypto)."""
    out = {}
    for s in coins:
        days = sorted(POS[s]); p = [POS[s][d] for d in days]; C = [data[s][d][2] if d in data[s] else float("nan") for d in days]; avg = 0.0
        for t in range(1, len(days)):
            pp, pn, cp = p[t - 1], p[t], C[t - 1]
            if pn == 0 or not math.isfinite(cp):
                avg = 0.0; continue
            if pp == 0 or base.sgn(pp) != base.sgn(pn):
                avg = cp
            elif abs(pn) > abs(pp):
                avg = (abs(pp) * avg + (abs(pn) - abs(pp)) * cp) / abs(pn)
            op = 1000.0 * pn * (cp / avg - 1) if avg > 0 else 0.0; o = out.setdefault(days[t], [0.0, 0.0])
            if realize and op < 0:
                o[1] += rt * 1000.0 * abs(pn); avg = cp; op = 0.0
            o[0] += op
    return out


def per_trade(data, POS, W, mult, T=8000.0, C10=10000.0, rt=0.0015):
    """CFT per-trade cap (research c450): {date: (cost, cut)} in stream units for positions W x pn; account $ = stream x mult."""
    cost, cut = {}, {}
    for s in base.CRY:
        days = sorted(POS[s]); p = [POS[s][d] for d in days]; C = [data[s][d][2] if d in data[s] else float("nan") for d in days]; avg = 0.0
        for t in range(1, len(days)):
            pp, pn, cp = p[t - 1], p[t], C[t - 1]
            if pn == 0 or not math.isfinite(cp):
                avg = 0.0; continue
            if pp == 0 or base.sgn(pp) != base.sgn(pn):
                avg = cp
            elif abs(pn) > abs(pp):
                avg = (abs(pp) * avg + (abs(pn) - abs(pp)) * cp) / abs(pn)
            if avg <= 0:
                continue
            op = W * pn * (cp / avg - 1) * mult
            if op > C10:
                cut[days[t - 1]] = cut.get(days[t - 1], 0.0) + (op - C10) / mult; cost[days[t]] = cost.get(days[t], 0.0) + rt * W * abs(pn); avg = cp
            elif op >= T:
                cost[days[t]] = cost.get(days[t], 0.0) + rt * W * abs(pn); avg = cp
    return cost, cut


# ---------------------------------------------------------------- futures streams
def sessions(f5a, s, D_prev, D):
    """bars of the CME session for RTH date D: after 18:00 ET on the prior trading day D_prev, up to 16:10 ET on D."""
    a = datetime(D_prev.year, D_prev.month, D_prev.day, 18, 0, tzinfo=base.ET); b = datetime(D.year, D.month, D.day, 16, 10, tzinfo=base.ET)
    return [(t, v) for t, v in f5a[s].items() if a <= t < b]


def threedown(data, V, f5a, risk, first, last):
    """{date: [E, A, Lo, Fa, n_micros, cost]} of the three-down rule at `risk` $ per trade (research c432 positions + stream_pos)."""
    out = {}; legs = {}
    for s in TD_IDX:
        days = list(data[s]); sc, atr, C = V[s]; pv, tick = MICRO[s]; rt = 2 * (COMM + tick * pv)
        for i in range(3, len(days) - 1):
            if not (C[i] < C[i - 1] < C[i - 2] < C[i - 3]) or days[i] not in atr:
                continue
            n = min(int(risk // (1.5 * atr[days[i]] * C[i] * pv)), MAXC); D = days[i + 1]
            if n <= 0 or not (first <= D <= last):
                continue
            bars = sessions(f5a, s, days[i], D); o = out.setdefault(D, [0.0, True, 0.0, 0.0, 0.0, 0.0]); o[4] += n; o[5] += n * rt
            if len(bars) >= 150:
                P0 = bars[0][1][0]; q = n * pv; o[0] += q * (bars[-1][1][3] - P0)
                legs.setdefault(D, []).append([(t, q * (v[2] - P0), q * (v[1] - P0)) for t, v in bars])
            else:                                                   # no futures session: index close-to-close, low x 1.5 (research fallback)
                e = n * pv * (C[i + 1] - C[i]); o[0] += e; o[2] += min(e, 0.0) * 1.5
    for D, o in out.items():
        lo = fa = 0.0
        if D in legs:
            tl, th = {}, {}
            for L in legs[D]:
                for t, l, h in L:
                    tl[t] = tl.get(t, 0.0) + l; th[t] = th.get(t, 0.0) + h
            lo, fa = min(tl.values()), max(th.values())
        o[0] -= o[5]; o[2] = min(o[2] + lo - o[5], o[0], 0.0); o[3] = max(fa - o[5], o[0], 0.0)
    return out


def fut_k(data, V, first, last, risk, K, sess):
    """{date: (P&L $, active)} of the K-rule futures stream (c390f fut_streams), integer micros on four indices."""
    acc = {}
    for s in US4:
        px = data[s]; days = list(px); sc, atr, C = V[s]; pv, tick = MICRO[s]; rt = 2 * (COMM + tick * pv); pos = None
        for i, d in enumerate(days):
            x = 0.0; act = False
            if pos is None:
                if d in sc and abs(sc[d]) >= K and d in atr:
                    per = 1.5 * atr[d] * C[i] * pv; n = int(risk // per)
                    if n == 0 and per <= 1.5 * risk:
                        n = 1
                    n = min(n, MAXC)
                    if n > 0:
                        pos = dict(sg=base.sgn(sc[d]), e=C[i], u=1.5 * atr[d], n=n, i0=i); x = -n * rt / 2; act = True
            else:
                r = pos["sg"] * (C[i] / pos["e"] - 1); x = pos["sg"] * (C[i] - C[i - 1]) * pv * pos["n"]; act = True
                if sess:
                    x -= pos["n"] * rt
                if r <= -pos["u"] or r >= 2 * pos["u"] or i - pos["i0"] >= 7:
                    x -= pos["n"] * rt / 2; pos = None
            if first <= d <= last and (x or act):
                p, a = acc.get(d, (0.0, False)); acc[d] = (p + x, a or act)
    return acc


# ---------------------------------------------------------------- per-entry streams
def scale3(T, k):
    return ([x * k for x in T[0]], [x * k for x in T[1]], [x * k for x in T[2]])


def add3(*Ts):
    return tuple([sum(T[j][h] for T in Ts) for h in range(24)] for j in range(3))


def mix_stream(U, PP, ru, vt, g):
    E = ru * U[0][23] + vt * PP[0][23]; lh = [ru * U[1][h] + vt * PP[1][h] for h in range(24)]; Lo = min(min(lh), E, 0.0)
    if Lo < -g:
        return -g, E != 0, -g, "stop"
    return E, E != 0, Lo, ""


def sized(S, s, cost=0.0, off=None):
    """(E, A, Lo, note, off) in account $ at size s, minus a cost booked that day."""
    return (S[0] * s - cost, S[1], min(S[2] * s - cost, 0.0), S[3], off)


def capk(e_cap, r, vc):
    if not e_cap:
        return 1.0
    basis = abs(r["pos"]["BTC-USD"]) if e_cap["basis"] == "BTC" else abs(r["pos"]["BTC-USD"]) + abs(r["pos"]["ETH-USD"])
    ratio = vc * 1000.0 * basis / 100000.0
    return min(1.0, e_cap["lev"] / max(ratio, 1e-12))


def entry_streams(e, r, X):
    """(evaluation stream, funded stream or None) of one entry on day d; a stream = (P&L, active, intraday low, note, dll offset)."""
    st = e["stream"]; k = st["kind"]; d = r["date"]
    if k == "fut3d":
        o = X["TD"][st["risk"]].get(d)
        if o is None:
            return (0.0, False, 0.0, "", None), None
        E, A, Lo, Fa, n, c = o; ce, cf = st["caps"] or (INF, INF); fm = e["engine"]["fm"]
        ke = min(1.0, ce / max(n, 1e-9)); kf = min(1.0, cf / max(fm * n, 1e-9))
        return (E * ke, A, Lo * ke, "", None), (E * kf, A, Lo * kf, "", None)
    if k == "futk":
        x, a = X["FK"].get(d, (0.0, False)); lo = min(st["risk"] / 1000.0 * X["FL"].get(d, 0.0), x, 0.0)
        return (x, a, lo, "", None), None
    s = st["size"]
    if k == "perp":
        P = add3(*[r["cr"][c][1] for c in base.CRY]); S = base.perp_stream(P, st["vt"], 0.0); S = (S[0] * s, S[1], S[2] * s, S[3])
        if not st.get("day_cap"):
            return (S[0], S[1], S[2], S[3], None), None
        out = []
        for j, m in enumerate(st["stage_mult"]):
            c_, u_ = X["PT"][e["id"]][j]; cst = c_.get(d, 0.0); cut = u_.get(d, 0.0)
            out.append((min(S[0] - cst - cut, st["day_cap"] / m), S[1], min(S[2] - cst, 0.0), S[3], None))
        return out[0], out[1]
    if k == "mix":
        P = add3(*[r["cr"][c][1] for c in base.CRY]); S = mix_stream(r["U4"], P, st["ru"], st["vt"], st["g"])
        off = None
        if st.get("offset"):
            off = min(X["OC2"].get(d, (0.0, 0.0))[0], 0.0) * st["offset"]["vc"] * s
        return sized(S, s, 0.0, off), None
    U = r[st["us"]]; coins = ["BTC-USD"] if st["crypto"] == "BTC" else base.CRY
    CR = add3(*[r["cr"][c][0] for c in coins])
    if k == "cfd":
        kc = capk(st.get("crypto_cap"), r, st["vc"]); S = base.cfd_stream(U, scale3(CR, kc), st["ru"], st["vc"], st["g"], r["oh"])
        o = st.get("offset"); cost = 0.0; off = None
        if o and o["type"] in ("realize", "open"):
            tag = "R" if o["type"] == "realize" else "O"; uo = X[tag + o["us"]].get(d, (0.0, 0.0, 0.0)); co = X[tag + ("B" if o["crypto"] == "BTC" else "C2")].get(d, (0.0, 0.0))
            off = (uo[0] * st["ru"] + co[0] * st["vc"] * kc) * s
            cost = (uo[1] * st["ru"] + co[1] * st["vc"] * kc) * s if o["type"] == "realize" else 0.0
        elif o and o["type"] == "open_neg":
            off = min(X["OC2"].get(d, (0.0, 0.0))[0], 0.0) * st["vc"] * kc * s
        return sized(S, s, cost, off), None
    # cfd_fp: FunderPro Swing caps per stage, realise-at-reset offsets (the engine takes min(evaluation, funded))
    uo = X["RUS4"].get(d, (0.0, 0.0, 0.0)); co = X["RC2"].get(d, (0.0, 0.0))
    crn = st["vc"] * 1000.0 * (abs(r["pos"]["BTC-USD"]) + abs(r["pos"]["ETH-USD"])) / 100000.0; usn = st["ru"] * uo[2] / 100000.0
    ke_c = min(1.0, st["eval_caps"]["crypto"] / max(crn, 1e-12)); kf_c = min(1.0, st["funded_caps"]["crypto"] / max(crn, 1e-12))
    kf_u = min(1.0, st["funded_caps"]["us"] / max(usn, 1e-12))
    Se = base.cfd_stream(U, scale3(CR, ke_c), st["ru"], st["vc"], st["g"], r["oh"]); Sf = base.cfd_stream(scale3(U, kf_u), scale3(CR, kf_c), st["ru"], st["vc"], st["g"], r["oh"])
    off_e = (uo[0] * st["ru"] + co[0] * st["vc"] * ke_c) * s; off_f = (uo[0] * st["ru"] * kf_u + co[0] * st["vc"] * kf_c) * s
    cost_e = (uo[1] * st["ru"] + co[1] * st["vc"] * ke_c) * s; cost_f = (uo[1] * st["ru"] * kf_u + co[1] * st["vc"] * kf_c) * s; off = min(off_e, off_f)
    return sized(Se, s, cost_e, off), sized(Sf, s, cost_f, off)


# ---------------------------------------------------------------- account engine (c390f step + research C440-C447 keys)
def rules(plan):
    F = plan["funded"]; out = []
    for p in plan["phases"] + [F]:
        fu = p is F
        out.append(dict(tgt=INF if fu else p["target"], mll=p["mll"], eod=p.get("type", "eod") == "eod", lock=p.get("lock", True),
                        dll=p.get("dll") or INF, soft=p.get("soft", True), cons=0.0 if fu else (p.get("cons") or 0.0), mind=0 if fu else p.get("min_days", 0),
                        lka=p.get("lock_at", 0.0), qthr=0.0 if fu else p.get("min_day_thr", 0.0), qcost=0.0 if fu else p.get("min_day_cost", 0.0)))
    return out


def new_account(e):
    fee = float(e["plan"]["fee"])
    return dict(st=0, bal=0.0, hw=0.0, td=0, best=0.0, age=0, since=0, wins=0, cyc=0.0, cbest=0.0, npay=0, refd=False, fz=False, wq=0, cash=-fee,
                fees=fee, payouts=0.0, attempts=1, dead=False, restart=False, first_fund=None, first_pay=None, n=0, cash360=None)


def step(a, e, S, Sf=None, t=None):
    """advance one account by one calendar day. S / Sf = (P&L, active, intraday low, note, dll offset) for the challenge / funded stage.
    Returns (day P&L booked to the balance, events)."""
    plan = e["plan"]; F = plan["funded"]; R = rules(plan); nph = len(plan["phases"]); fee = float(plan["fee"]); ev = []; E_ = e["engine"]
    if a["restart"] and a["attempts"] >= MAX_ATT:
        a["dead"] = True; a["restart"] = False; ev.append(f"account ended ({'max payouts reached' if a['npay'] and F.get('max_pays') and a['npay'] >= F['max_pays'] else 'breach'}, one attempt)")
    if a["restart"]:
        a.update(st=0, bal=0.0, hw=0.0, td=0, best=0.0, age=0, since=0, wins=0, cyc=0.0, cbest=0.0, npay=0, refd=False, fz=False, wq=0, restart=False)
        a["cash"] -= fee; a["fees"] += fee; a["attempts"] += 1; ev.append(f"attempt {a['attempts']} starts (fee ${fee:,.2f})")
    fu = a["st"] == nph; dead = a["dead"]
    pm = E_.get("phase_mult"); k = 0.0 if dead else (E_["fm"] if fu else (pm[a["st"]] if pm else E_["cm"]))
    X = Sf if (fu and Sf is not None) else S; pnl = X[0] * k; low = min(X[2], 0.0) * k; off = X[4] if len(X) > 4 else None
    if X[3] and not dead:
        ev.append(f"{X[3]} (stream)")
    g = E_.get("guard")
    if g is not None and low < -g:
        pnl = low = -g; ev.append(f"personal stop -${g:,.0f}")
    r = R[a["st"]]; d_l = r["dll"] + (0.0 if off is None or r["dll"] == INF else max(off * k, -r["dll"]))
    hit = low < -d_l; hard = hit and not r["soft"]
    if hit and r["soft"]:
        pnl = -d_l; low = -d_l; ev.append("soft daily limit")
    floor = (a["hw"] - r["mll"]) if r["eod"] else -r["mll"]
    if r["lock"]:
        floor = min(floor, r["lka"])
    if a["fz"]:
        floor = max(floor, r["lka"])
    br = hard or (a["bal"] + low <= floor)
    if br and not dead:
        ev.append(f"BREACH ({'daily' if hard else 'max'} loss) in {'funded' if fu else 'phase ' + str(a['st'] + 1)}")
    if not br:
        a["bal"] += pnl
    a["hw"] = max(a["hw"], a["bal"]); ok = (not br) and not dead
    q = ok and bool(X[1]) and (r["qthr"] <= 0 or pnl >= r["qthr"])                 # C440: qualifying days
    if q and r["qthr"] > 0 and a["td"] < r["mind"] and not fu:
        a["bal"] -= r["qcost"]
    a["td"] += int(q)
    if ok:
        a["best"] = max(a["best"], pnl)
    evd = ok and not fu; a["age"] += int(evd)
    if plan.get("monthly") and evd and a["age"] % 30 == 0 and a["age"] > 0:
        a["cash"] -= fee; a["fees"] += fee; ev.append(f"monthly fee ${fee:,.2f}")
    r = R[a["st"]]; need = max(r["tgt"], a["best"] / r["cons"]) if r["cons"] > 0 else r["tgt"]
    if evd and a["bal"] >= need and a["td"] >= r["mind"]:
        ev.append(f"passed phase {a['st'] + 1}" + (" -> funded" if a["st"] + 1 == nph else ""))
        a.update(st=a["st"] + 1, bal=0.0, hw=0.0, td=0, best=0.0, age=0)
        if a["st"] == nph:
            act = plan.get("activation", 0.0) or 0.0
            a["cash"] -= act; a["fees"] += act
            if a["first_fund"] is None:
                a["first_fund"] = str(t) if t else a["n"]
            if act:
                ev.append(f"activation fee ${act:,.2f}")
            a["n"] += 1; a["restart"] = False
            return pnl, ev
    fa = ok and a["st"] == nph
    if fa:
        a["since"] += int(bool(X[1]) or F.get("wait_cal", False))
        wdf = int(F.get("win_days_first", 0))
        if a["npay"] == 0 and a["wq"] < wdf and pnl >= float(F.get("win_thr_first", INF)):     # C440: qualifying days before the first payout
            a["bal"] -= float(F.get("win_cost_first", 0.0)); a["wq"] += 1
        a["wins"] += int(pnl >= F.get("win_thr", 0.01)); a["cyc"] += pnl; a["cbest"] = max(a["cbest"], pnl)
    wait = F.get("first_wait", 0) if a["npay"] == 0 else F.get("cycle", 1)
    if E_.get("pay_gap"):
        wait = max(wait, E_["pay_gap"])
    amt = min(F.get("cap", INF), F.get("max_frac", 1.0) * (a["bal"] - F.get("buffer", 0.0) - E_.get("cushion", 0.0) * F["mll"]))
    if F.get("new_frac"):
        amt = min(amt, max(a["cyc"], 0.0) / F["new_frac"])
    okp = (fa and a["since"] >= wait and a["wins"] >= F.get("win_days", 0) and (a["npay"] > 0 or a["wq"] >= int(F.get("win_days_first", 0)))
           and a["cyc"] >= F.get("min_cycle", 0.0) and amt >= max(F.get("min_pay", 0.0) or 0.0, 1.0))
    if okp and F.get("cons"):
        okp = a["cbest"] <= F["cons"] * max(a["cyc"], 1e-9)
    if okp:
        p = F["split"] * amt; a["cash"] += p; a["payouts"] += p; a["npay"] += 1; ev.append(f"payout ${p:,.2f}")
        if a["first_pay"] is None:
            a["first_pay"] = str(t) if t else a["n"]
        if plan.get("refund") and not a["refd"] and a["npay"] >= plan.get("refund_n", 1):
            a["cash"] += fee; a["fees"] -= fee; ev.append(f"fee refund ${fee:,.2f}")
        a["refd"] = a["refd"] or a["npay"] >= plan.get("refund_n", 1)
        a["bal"] = 0.0 if F.get("cap_forfeit") else a["bal"] - amt          # research C416: HyroTrader forfeits profit above the cap
        a["since"] = 0; a["wins"] = 0; a["cyc"] = 0.0; a["cbest"] = 0.0
    if F.get("max_pays") and a["npay"] >= F["max_pays"] and not dead:              # C402: the account ends after max_pays payouts
        br = True
    if okp and F.get("floor_zero_after_pay"):
        a["fz"] = True
    if plan.get("eval_days") and a["st"] < nph and a["age"] >= plan["eval_days"] and not dead:
        if not br:
            ev.append(f"evaluation expired ({plan['eval_days']} days)")
        br = True
    a["restart"] = br and not dead; a["n"] += 1
    return pnl, ev


def stage(a, e):
    return "ended" if a["dead"] else ("funded" if a["st"] == len(e["plan"]["phases"]) else f"phase {a['st'] + 1}")


# ---------------------------------------------------------------- run
def compute(data, f5, f5a, first, last, live_today=None, hourly=None, wait=False):
    """streams for every calendar day first..last. wait=True stops at the first day whose data are not complete yet."""
    vix = {d: v[2] for d, v in data["^VIX"].items()}; spx = {d: v[2] for d, v in data["^GSPC"].items()}; rut = {d: v[2] for d, v in data["^RUT"].items()}
    V = {s: base.us_votes(data[s], vix, spx, rut, list(data[s])) for s in US4}
    U4, ev4 = base.us_paths(data, f5, V, first, last, False)
    keep = base.US; base.US = US3
    try:
        U3, _ = base.us_paths(data, f5, V, first, last, False)
    finally:
        base.US = keep
    POS = {c: base.ens_positions(data[c]) for c in base.CRY}
    if hourly is None:
        hourly = {c: base.binance_hourly(base.BIN[c], first, last) for c in base.CRY}
    K5 = k5_positions(V, data, US4)
    X = dict(RUS4=us_offsets(K5, US4, True), RUS3=us_offsets(K5, US3, True), OUS4=us_offsets(K5, US4, False),
             RC2=crypto_offsets(data, POS, base.CRY, True), RB=crypto_offsets(data, POS, ["BTC-USD"], True), OC2=crypto_offsets(data, POS, base.CRY, False))
    X["TD"] = {e["stream"]["risk"]: None for e in ENT.values() if e["stream"]["kind"] == "fut3d"}
    for rk in X["TD"]:
        X["TD"][rk] = threedown(data, V, f5a, rk, first, last)
    fk = [e for e in ENT.values() if e["stream"]["kind"] == "futk"]
    if fk:
        st = fk[0]["stream"]; X["FK"] = fut_k(data, V, first, last, st["risk"], st["K"], st["session"])
        X["FL"] = fut_lows(data, f5, V, first, last, st["K"])
    X["PT"] = {e["id"]: [per_trade(data, POS, e["stream"]["size"] * e["stream"]["vt"], m) for m in e["stream"]["stage_mult"]]
               for e in ENT.values() if e["stream"].get("trade_cap")}
    out = []; d = first
    while d <= last:
        age = (live_today - d).days if live_today else 99; notes = []
        if wait:
            session = d in data["^GSPC"] or (d.weekday() < 5 and d not in base.HOLIDAYS and not any(x > d for x in data["^GSPC"]))
            if any(d not in data[c] for c in base.CRY) or (session and any(d not in data[s] for s in US4 + ["^VIX"])):
                break
            if session and d in data["^GSPC"] and not any(d in f5[s] for s in base.FUT) and age <= 2:
                break
            if any(sum(1 for h in range(24) if base.epoch(d) + 3600 * h in hourly[c]) < 24 for c in base.CRY) and age <= 2:
                break
        cr = {}; fund = {}
        for c in base.CRY:
            days = sorted(POS[c]); p = POS[c].get(d, 0.0); j = days.index(d) if d in POS[c] else -1; pp = POS[c][days[j - 1]] if j > 0 else 0.0
            fr = base.funding_day(base.BIN[c], d)
            if fr is None:
                if wait and age <= 3:
                    return out, "waiting for premium-index files"
                fr = base.FUND_PRE; notes.append(f"{c} funding assumed 0.03%")
            fund[c] = fr
            cr[c] = (base.coin_paths(d, p, pp, hourly[c], data[c], base.CR_SIDE, swap=base.CR_SWAP), base.coin_paths(d, p, pp, hourly[c], data[c], base.PERP_SIDE, fund=fr))
        r = dict(date=d, US4=U4.get(d, Z24), US3=U3.get(d, Z24), U4=U4.get(d, Z24), cr=cr, pos={c: POS[c].get(d, 0.0) for c in base.CRY}, fund=fund, oh=9 + base.utc_off(d))
        r["E"] = {i: entry_streams(e, r, X) for i, e in ENT.items()}
        r["events"] = [f"{x[1]} {x[2]} {'long' if x[3] > 0 else 'short'} ({x[4]})" for x in ev4 if x[0] == d] + notes
        for rk, T in X["TD"].items():
            if d in T:
                r["events"].append(f"3-down session at ${rk:,.0f} risk: {T[d][4]:.0f} micros, ${T[d][0]:,.2f}")
        out.append(r); d += timedelta(days=1)
    return out, ""


def fut_lows(data, f5, V, first, last, K):
    """{date: lowest hourly cumulative low} of the continuous $1,000-risk US path at threshold K, summed over the 4 indices, no costs
    (c390f fut_lows: RTH 5-minute bars, a day without a full proxy session books it at 20-23 UTC with low = 1.5 x the loss)."""
    LOW = {}
    for s in US4:
        px = data[s]; days = list(px); sc, atr, C = V[s]; pos = None
        f = f5[base.PROXY[s]]; full = [d for d in f if len(f[d]) >= 74]; fprev = {full[j]: full[j - 1] for j in range(1, len(full))}
        for i, d in enumerate(days):
            inr = first <= d <= last
            if pos is None:
                if d in sc and abs(sc[d]) >= K and d in atr:
                    pos = dict(sg=base.sgn(sc[d]), e=C[i], u=1.5 * atr[d], n=1000.0 / (1.5 * atr[d]), i0=i)
                continue
            n = pos["sg"] * pos["n"]; eod = n * (C[i] / C[i - 1] - 1); rt = pos["sg"] * (C[i] / pos["e"] - 1)
            ex = rt <= -pos["u"] or rt >= 2 * pos["u"] or i - pos["i0"] >= 7
            if inr:
                L = LOW.setdefault(d, [0.0] * 24)
                if d in fprev:
                    off = base.utc_off(d); pc = f[fprev[d]][-1][3]; cash = data[base.UNDER[base.PROXY[s]]]; bk = {}
                    if fprev[d] in cash and d in cash:
                        jump = (f[d][-1][3] / cash[d][2]) / (pc / cash[fprev[d]][2])
                        if abs(jump - 1) > 0.002:
                            pc *= jump
                    for m, hi, lo, cl in f[d]:
                        hh = m // 60 + off; cp = n * (cl / pc - 1); lp = min(n * ((lo if n > 0 else hi) / pc - 1), cp); b = bk.get(hh)
                        bk[hh] = (cp, lp) if b is None else (cp, min(b[1], lp))
                    prev = None
                    for hh in range(9 + off, 16 + off):
                        if hh not in bk and prev is not None:
                            bk[hh] = (prev, prev)
                        if hh in bk:
                            prev = bk[hh][0]
                    lastc = n * (f[d][-1][3] / pc - 1)
                    for hh in range(24):
                        if hh in bk:
                            L[hh] += bk[hh][1]
                        elif hh > 15 + off:
                            L[hh] += min(eod, lastc)
                else:
                    for hh in range(20, 24):
                        L[hh] += min(eod, 0.0) * 1.5
            if ex:
                pos = None
    return {d: min(v) for d, v in LOW.items()}


def backtest(a, b, path):
    a, b = date.fromisoformat(a), date.fromisoformat(b); data, f5, f5a = fetch(); rows, _ = compute(data, f5, f5a, a, b)
    with open(path, "w", newline="") as f:
        w = csv.writer(f); ids = list(ENT)
        w.writerow(["date"] + [f"{i}_{x}" for i in ids for x in ("E", "A", "Lo", "off", "Ef", "Lof")])
        for r in rows:
            row = [r["date"].isoformat()]
            for i in ids:
                S, Sf = r["E"][i]; row += [round(S[0], 4), int(bool(S[1])), round(S[2], 4), "" if S[4] is None else round(S[4], 4)] + ([round(Sf[0], 4), round(Sf[2], 4)] if Sf else ["", ""])
            w.writerow(row)


def book_cash(S, key="cash"):
    return round(sum(ENT[i]["count"] * (S["acc"][i][key] if S["acc"][i][key] is not None else S["acc"][i]["cash"]) for i in ENT), 2)


def main(stdir):
    os.makedirs(stdir, exist_ok=True); sp = os.path.join(stdir, "state.json")
    S = json.load(open(sp)) if os.path.exists(sp) else dict(last=str(START - timedelta(days=1)), day=0, acc={i: new_account(e) for i, e in ENT.items()})
    today = datetime.now(timezone.utc).date(); first = date.fromisoformat(S["last"]) + timedelta(days=1); upto = min(today - timedelta(days=1), END)
    if upto < first:
        print("nothing new to log" + (f" (log starts {START})" if first == START else (" (window ended)" if first > END else ""))); return
    data, f5, f5a = fetch()
    for c in base.CRY:                                       # drop the still-forming bar of the current UTC day
        data[c] = {d: v for d, v in data[c].items() if d < today}
    rows, why = compute(data, f5, f5a, first, upto, live_today=today, wait=True)
    if not rows:
        print(why or "waiting for data"); return
    ids = list(ENT); fs, fa, fb = (os.path.join(stdir, x) for x in ("streams.csv", "accounts.csv", "book.csv"))
    new = {x: not os.path.exists(x) for x in (fs, fa, fb)}
    with open(fs, "a", newline="") as f1, open(fa, "a", newline="") as f2, open(fb, "a", newline="") as f3:
        w1, w2, w3 = csv.writer(f1), csv.writer(f2), csv.writer(f3)
        if new[fs]:
            w1.writerow(["date"] + [f"{i}_{x}" for i in ids for x in ("pnl", "low", "off", "pnl_funded", "low_funded")] + ["btc_pos", "eth_pos", "fund_btc", "fund_eth", "events"])
        if new[fa]:
            w2.writerow(["date", "day", "entry", "key", "count", "stage", "day_pnl", "balance", "cash_to_date", "events"])
        if new[fb]:
            w3.writerow(["date", "day", "book_cash", "book_cash_day360", "funded_accounts", "ended_accounts", "payouts_to_date"])
        for r in rows:
            d = r["date"]
            w1.writerow([d.isoformat()] + [x for i in ids for x in (round(r["E"][i][0][0], 2), round(r["E"][i][0][2], 2), "" if r["E"][i][0][4] is None else round(r["E"][i][0][4], 2),
                                                                     "" if r["E"][i][1] is None else round(r["E"][i][1][0], 2), "" if r["E"][i][1] is None else round(r["E"][i][1][2], 2))]
                        + [round(r["pos"]["BTC-USD"], 4), round(r["pos"]["ETH-USD"], 4), round(r["fund"]["BTC-USD"], 8), round(r["fund"]["ETH-USD"], 8), "; ".join(r["events"])])
            for i in ids:
                a = S["acc"][i]; Sx, Sf = r["E"][i]; pnl, ev = step(a, ENT[i], Sx, Sf, t=d)
                if S["day"] + 1 == HORIZON:
                    a["cash360"] = a["cash"]
                w2.writerow([d.isoformat(), S["day"], i, ENT[i]["key"], ENT[i]["count"], stage(a, ENT[i]), round(pnl, 2), round(a["bal"], 2), round(a["cash"], 2), "; ".join(ev)])
            S["day"] += 1
            nf = sum(ENT[i]["count"] for i in ids if stage(S["acc"][i], ENT[i]) == "funded"); ne = sum(ENT[i]["count"] for i in ids if S["acc"][i]["dead"])
            po = round(sum(ENT[i]["count"] * S["acc"][i]["payouts"] for i in ids), 2)
            w3.writerow([d.isoformat(), S["day"], book_cash(S), book_cash(S, "cash360") if S["day"] >= HORIZON else "", nf, ne, po])
            print(d, f"day {S['day']} book cash ${book_cash(S):,.0f} funded {nf} ended {ne} payouts ${po:,.0f}", "; ".join(r["events"]), flush=True)
    S["last"] = rows[-1]["date"].isoformat(); S["book_cash"] = book_cash(S)
    json.dump(S, open(sp, "w"), indent=1)
    if why:
        print(why)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--backtest":
        backtest(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "state"))
