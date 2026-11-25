"""C391F rolling-cohort forward paper log of the C391 short-horizon prop book (research_lab reports/c391/README.md; prereg
claude/c391f-preregistration.md). Log only: no orders, no account, nothing traded.

Every UTC day from 2026-12-01, a new one-attempt simulated account (a "cohort") is started for each frozen entry in c391f/book.json,
and each cohort is followed for 60 days. The log measures how often attempts started on real forward days reach a first payout
within 30 days (P30) and their cash at day 60, which a single path cannot.
Entries (c391f/book.json, from research c391f_freeze.py):
- S01 MyFundedPerps Elite 3% DLL $10K and S03 Velotrade CLASSIC 2-Step $5K (mix):
  - US CFD leg x ru (c348f us_paths, per $1,000 R) + crypto trend at perp costs x vt (c348f perp paths) + the T1 turn-of-month leg
    x t1 (CFD costs);
  - personal stop g on the hourly combined low (per $100K), then x size.
- S02 MFFU Pro 50K (futures): the US rule K5 in whole micros (c390f fut_streams) + T1 in whole micros, both at the entry's risk;
  intraday low = min over hours of (risk / 1,000) x (K5 path low + T1 path low), as research c391_fast.
- S04 CFT 2-Phase $5K (perp, manual in the US): crypto trend at perp costs x vt.
T1 (C391 stage-1 pick): long each index over the last 4 and first 2 sessions of every month, entered at the close before the window.
Sessions come from Yahoo's realised days plus future weekdays outside c348f HOLIDAYS.
- CFD version: n = 1,000 / (1.5 x ATR14) per index; 1 bp at entry (booked at 20-23 UTC of the entry day), 2.5 bp per calendar night
  on longs and 1 bp at exit, subtracted from that day's hourly values, as research c391_streams.
- Futures: same path without costs, and whole micros as c338.
Engine: c390f step (research c341 sim_year, fixed) with one attempt (a breach ends the cohort), horizon 60 days.
Usage: python3 book_logger.py [STATE_DIR] | python3 book_logger.py --backtest START END OUT.csv
"""
import csv, importlib.util, json, os, sys
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("c390f_logger", os.path.join(HERE, "..", "c390f", "book_logger.py"))
c390 = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(c390); base = c390.base     # base = c348f (day_streams patched by c390f)
BOOK = json.load(open(os.path.join(HERE, "book.json"))); ENT = {e["id"]: e for e in BOOK["entries"]}; BOOKS = BOOK["books"]
START = date.fromisoformat(os.environ.get("C391F_START", "2026-12-01")); LAST_START = START + timedelta(days=304); HORIZON = 60
FUT = sorted({(e["stream"]["risk"], e["stream"]["session"], e["stream"]["K"]) for e in BOOK["entries"] if e["stream"]["kind"] == "fut"})


# ---------------------------------------------------------------- T1 turn-of-month leg
def t1_positions(data, s):
    """{session: 1.0 inside the window, 0.0 outside} for one index, over realised days + future calendar sessions."""
    days = sorted(data[s]); d = days[-1] + timedelta(days=1); end = days[-1] + timedelta(days=50); fut = []
    while d <= end:
        if d.weekday() < 5 and d not in base.HOLIDAYS:
            fut.append(d)
        d += timedelta(days=1)
    sess = days + fut; bym = {}
    for x in sess:
        bym.setdefault((x.year, x.month), []).append(x)
    pos = {}
    for (y, m), lst in bym.items():
        for k, x in enumerate(lst):
            pos[x] = 1.0 if (k < 2 or len(lst) - k <= 4) else 0.0
    return pos, sess


def t1_micro(data, V, risk, sess_chain, first, last):
    acc = {}
    for s in base.US:
        pos, sess = t1_positions(data, s); px = data[s]; days = list(px); sc, atr, C = V[s]; pv, tick = c390.MICRO[s]; rt = 2 * (c390.COMM + tick * pv); n = 0
        nxt = {sess[i]: sess[i + 1] for i in range(len(sess) - 1)}
        for i in range(1, len(days)):
            d = days[i]
            if pos.get(d, 0.0) == 0:
                continue
            x = 0.0; xe = 0.0
            if pos.get(days[i - 1], 0.0) == 0:
                dp = days[i - 1]; per = 1.5 * atr[dp] * C[i - 1] * pv if dp in atr else float("inf"); n = int(risk // per) if per != float("inf") else 0
                if n == 0 and per <= 1.5 * risk:
                    n = 1
                n = min(n, c390.MAXC); xe = -n * rt / 2
                if first <= dp <= last:
                    p_, a_ = acc.get(dp, (0.0, False)); acc[dp] = (p_ + xe, a_ or n > 0)
            x = pos[d] * (C[i] - C[i - 1]) * pv * n - (n * rt if sess_chain else 0.0)
            if pos.get(nxt.get(d), 0.0) == 0:
                x -= n * rt / 2
            if first <= d <= last:
                p_, a_ = acc.get(d, (0.0, False)); acc[d] = (p_ + x, a_ or n > 0)
    return acc


def t1_hours(data, f5, V, first, last, cfd):
    """{date: (CUM[24], LOW[24])} of the T1 leg per $1,000 R (sum over indices), research c391_streams construction on 5-minute bars."""
    out = {}
    def add(d, h, c, l_):
        U = out.setdefault(d, ([0.0] * 24, [0.0] * 24)); U[0][h] += c; U[1][h] += l_
    for s in base.US:
        pos, sess = t1_positions(data, s); px = data[s]; days = list(px); sc, atr, C = V[s]; n = 0.0
        nxt = {sess[i]: sess[i + 1] for i in range(len(sess) - 1)}
        f = f5[base.PROXY[s]]; full = [d for d in f if len(f[d]) >= 74]; fprev = {full[j]: full[j - 1] for j in range(1, len(full))}
        for i in range(1, len(days)):
            d = days[i]
            if pos.get(d, 0.0) == 0:
                continue
            if pos.get(days[i - 1], 0.0) == 0:
                dp = days[i - 1]; n = pos[d] * 1000.0 / (1.5 * atr[dp]) if dp in atr else 0.0
                if cfd and first <= dp <= last:
                    for h in range(20, 24):
                        add(dp, h, -abs(n) * 1e-4, -abs(n) * 1e-4)
            if not (first <= d <= last):
                continue
            eod = n * (C[i] / C[i - 1] - 1); lastd = pos.get(nxt.get(d), 0.0) == 0
            cost = ((abs(n) * 0.00025 * (d - days[i - 1]).days if n > 0 else 0.0) + (abs(n) * 1e-4 if lastd else 0.0)) if cfd else 0.0
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
                        add(d, hh, bk[hh][0] - cost, bk[hh][1] - cost)
                    elif hh > 15 + off:
                        add(d, hh, eod - cost, min(eod, lastc) - cost)
            else:
                for hh in range(20, 24):
                    add(d, hh, eod - cost, min(eod, 0.0) * 1.5 - cost)
    return out


def k_hours(data, f5, V, first, last, K):
    """{date: LOW[24]} of the continuous $1,000-R US rule path at threshold K, summed over the indices (c390f fut_lows, hourly kept)."""
    return _fut_low_hours(data, f5, V, first, last, K)[0]


def _fut_low_hours(data, f5, V, first, last, K):
    """c390f fut_lows with the hourly list returned instead of its minimum (same code otherwise)."""
    LOW, ev = {}, []
    for s in base.US:
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
    return LOW, ev


# ---------------------------------------------------------------- per-entry streams
Z24 = [0.0] * 24


def entry_stream(e, R, X, d):
    st = e["stream"]; k = st["kind"]
    if k == "fut":
        x, a = X["FS"][(st["risk"], st["session"], st["K"])].get(d, (0.0, False)) if st["k_leg"] else (0.0, False)
        if st["t1"]:
            y, b = X["T1M"][(st["risk"], st["session"])].get(d, (0.0, False)); x += y; a = a or b
        lh = [0.0] * 24; s = st["risk"] / 1000.0
        if st["k_leg"]:
            kl = X["KH"][st["K"]].get(d, Z24); lh = [lh[h] + s * kl[h] for h in range(24)]
        if st["t1"]:
            tl = X["T1F"].get(d, (Z24, Z24))[1]; lh = [lh[h] + s * tl[h] for h in range(24)]
        return (x, a, min(min(lh), x, 0.0), "")
    sz = st["size"]
    if k == "mix":
        U, PP = R["Un"], R["crp"]; T = X["T1C"].get(d, (Z24, Z24)); k = 1.0
        if st.get("lev"):                                    # C391 Amendment 1: gross notional per $100K capped at lev x $100K
            g = st["ru"] * X["USNOT"].get(d, 0.0) + st["t1"] * X["T1NOT"].get(d, 0.0) + st["vt"] * R["absp"]
            k = min(1.0, st["lev"] * 1e5 / g) if g > 0 else 1.0
        U = tuple([k * v for v in a] for a in U); PP = tuple([k * v for v in a] for a in PP); T = tuple([k * v for v in a] for a in T)
        E = st["ru"] * U[0][23] + st["vt"] * PP[0][23] + st["t1"] * T[0][23]; lh = [st["ru"] * U[1][h] + st["vt"] * PP[1][h] + st["t1"] * T[1][h] for h in range(24)]
        Lo = min(min(lh), E, 0.0); A = E != 0; note = ""
        if Lo < -st["g"]:
            E = Lo = -st["g"]; note = "stop"
        return (E * sz, A, Lo * sz, note)
    ten = st["vt"] * R["ten"] if st["ten"] else 0.0; PP = R["crp"]
    E = st["vt"] * PP[0][23] - ten; lh = [st["vt"] * PP[1][h] - ten for h in range(24)]
    return (E * sz, E != 0, min(min(lh), E, 0.0) * sz, "")


def notional(data, V, first, last):
    """research c347 US_NOT (K5 CFD chain: entry-day n, held days n x C / entry) and c391 T1 notional (n = 1,000 / (1.5 ATR) on held days),
    per $1,000 R, for the C391 Amendment 1 leverage caps."""
    US, T1 = {}, {}
    for s in base.US:
        px = data[s]; days = list(px); sc, atr, C = V[s]; pos = None
        for i, d in enumerate(days):
            if pos is None:
                if d in sc and abs(sc[d]) >= 5 and d in atr:
                    pos = dict(e=C[i], u=1.5 * atr[d], n=1000.0 / (1.5 * atr[d]), i0=i, sg=base.sgn(sc[d]))
                    if first <= d <= last:
                        US[d] = US.get(d, 0.0) + pos["n"]
                continue
            if first <= d <= last:
                US[d] = US.get(d, 0.0) + pos["n"] * C[i] / pos["e"]
            rt = pos["sg"] * (C[i] / pos["e"] - 1)
            if rt <= -pos["u"] or rt >= 2 * pos["u"] or i - pos["i0"] >= 7:
                pos = None
        tp, _ = t1_positions(data, s); n = 0.0
        for i in range(1, len(days)):
            d = days[i]
            if tp.get(d, 0.0) == 0:
                continue
            if tp.get(days[i - 1], 0.0) == 0:
                n = 1000.0 / (1.5 * atr[days[i - 1]]) if days[i - 1] in atr else 0.0
            if first <= d <= last:
                T1[d] = T1.get(d, 0.0) + n
    return US, T1


def compute(data, f5, first, last, live_today=None, hourly=None, wait=False):
    rows, why = base.compute(data, f5, first, last, live_today=live_today, hourly=hourly, wait=wait)
    if not rows:
        return rows, why
    last = rows[-1]["date"]; vix = {d: v[2] for d, v in data["^VIX"].items()}; spx = {d: v[2] for d, v in data["^GSPC"].items()}
    rut = {d: v[2] for d, v in data["^RUT"].items()}; V = {s: base.us_votes(data[s], vix, spx, rut, list(data[s])) for s in base.US}
    keep = c390.FUT_SPECS
    try:
        c390.FUT_SPECS = FUT; FS = c390.fut_streams(data, V, first, last)
    finally:
        c390.FUT_SPECS = keep
    X = dict(FS=FS, KH={K: k_hours(data, f5, V, first, last, K) for K in sorted({e["stream"]["K"] for e in BOOK["entries"] if e["stream"]["kind"] == "fut"})},
             T1M={(r, s): t1_micro(data, V, r, s, first, last) for r, s, K in FUT}, T1F=t1_hours(data, f5, V, first, last, False), T1C=t1_hours(data, f5, V, first, last, True))
    X['USNOT'], X['T1NOT'] = notional(data, V, first, last)
    for r in rows:
        d = r["date"]; r["S"]["absp"] = sum(abs(v) for v in r["pos"].values()); r["E"] = {i: entry_stream(e, r["S"], X, d) for i, e in ENT.items()}
        r["t1"] = {s: t1_positions(data, s)[0].get(d, 0.0) for s in base.US}
    return rows, why


def backtest(a, b, path):
    a, b = date.fromisoformat(a), date.fromisoformat(b); data, f5 = base.fetch(); rows, _ = compute(data, f5, a, b)
    with open(path, "w", newline="") as f:
        w = csv.writer(f); ids = list(ENT); w.writerow(["date"] + [f"{i}_{x}" for i in ids for x in ("E", "A", "Lo")])
        for r in rows:
            w.writerow([r["date"].isoformat()] + [v for i in ids for v in (round(r["E"][i][0], 4), int(bool(r["E"][i][1])), round(r["E"][i][2], 4))])


# ---------------------------------------------------------------- cohorts
def new_cohort(i, d):
    a = c390.new_account(ENT[i]); a["attempts"] = c390.MAX_ATT        # one attempt: the first breach ends the cohort (sim_year max_attempts=1)
    return dict(entry=i, start=str(d), age=0, acc=a, cash30=None)


def main(stdir):
    os.makedirs(stdir, exist_ok=True); sp = os.path.join(stdir, "state.json")
    S = json.load(open(sp)) if os.path.exists(sp) else dict(last=str(START - timedelta(days=1)), active=[], done=0)
    today = datetime.now(timezone.utc).date(); first = date.fromisoformat(S["last"]) + timedelta(days=1)
    upto = min(today - timedelta(days=1), LAST_START + timedelta(days=HORIZON - 1))
    if upto < first:
        print("nothing new to log" + (f" (log starts {START})" if first == START else "")); return
    data, f5 = base.fetch()
    for c in base.CRY:
        data[c] = {d: v for d, v in data[c].items() if d < today}
    rows, why = compute(data, f5, first, upto, live_today=today, wait=True)
    if not rows:
        print(why or "waiting for data"); return
    ids = list(ENT); fs, fc = os.path.join(stdir, "streams.csv"), os.path.join(stdir, "cohorts.csv"); ns, nc = not os.path.exists(fs), not os.path.exists(fc)
    with open(fs, "a", newline="") as f1, open(fc, "a", newline="") as f2:
        w1, w2 = csv.writer(f1), csv.writer(f2)
        if ns:
            w1.writerow(["date"] + [f"{i}_{x}" for i in ids for x in ("pnl", "low")] + ["t1_window", "btc_pos", "eth_pos", "events"])
        if nc:
            w2.writerow(["entry", "plan", "start", "first_funded", "first_payout", "days_to_payout", "cash_day30", "cash_day60", "end_stage", "events"])
        for r in rows:
            d = r["date"]
            if START <= d <= LAST_START:
                S["active"] += [new_cohort(i, d) for i in ids]
            keep = []
            for c in S["active"]:
                e = ENT[c["entry"]]; _, ev = c390.step(c["acc"], e, r["E"][c["entry"]], None, t=d); c["age"] += 1
                c.setdefault("ev", []).extend(f"{d}: {x}".replace(f"stopped after {c390.MAX_ATT} attempts", "cohort ended (one attempt)") for x in ev if not x.startswith(("stop (stream)", "personal stop")))
                if c["age"] == 31:
                    c["cash30"] = round(c["acc"]["cash"], 2)
                if c["age"] >= HORIZON:
                    a = c["acc"]; fp = a.get("first_pay"); dtp = (date.fromisoformat(fp) - date.fromisoformat(c["start"])).days if fp else ""
                    w2.writerow([c["entry"], e["key"], c["start"], a.get("first_fund") or "", fp or "", dtp, c["cash30"], round(a["cash"], 2), c390.stage(a, e), "; ".join(c["ev"])[:2000]])
                    S["done"] += 1
                else:
                    keep.append(c)
            S["active"] = keep
            w1.writerow([d.isoformat()] + [round(r["E"][i][j], 2) for i in ids for j in (0, 2)] + [int(any(v for v in r["t1"].values())),
                        round(r["pos"]["BTC-USD"], 4), round(r["pos"]["ETH-USD"], 4), "; ".join(r["events"])])
            print(d, " ".join(f"{i}={r['E'][i][0]:.0f}" for i in ids), f"active cohorts {len(S['active'])}", flush=True)
    S["last"] = rows[-1]["date"].isoformat(); json.dump(S, open(sp, "w"))
    if why:
        print(why)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--backtest":
        backtest(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "state"))
