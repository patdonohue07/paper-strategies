"""C390F forward paper log of the C387 v3.2 prop books (research_lab reports/c387/README.md "FINAL BOOKS v3.2"; prereg
claude/c390f-preregistration.md). Log only: no orders, no account, nothing traded.

Frozen setups: c390f/book.json (research_lab code/c390_freeze.py; 31 distinct plan + setup entries with copy counts):
- AUTO = the fully automated capped book (29 accounts, primary); AUTO_MAX = the automated book with every allowed copy (54);
  FULL = the capped book that also uses accounts traded by hand in the US (41). Copies of one entry are identical paths.
Streams (c348f/book_logger.py loaded unchanged for the data feeds, the US CFD leg, the BTC/ETH trend ensemble, crypto CFD/perp paths):
- fut (futures accounts): the US swing rule (C320 8-vote score, |score| >= K, K = 5 or 4; stop 1.5 x ATR14 on closes, target 2R,
  exit after 7 sessions) on the cash index closes in whole CME micros (MES MNQ M2K MYM: $5/$2/$5/$0.5 a point), n = floor(risk / (1.5
  x ATR x close x point value)), 1 if that is 0 and one micro risks at most 1.5 x risk, at most 50. Costs per micro per side $0.70 +
  one tick; session-chained setups pay a round trip on every held day (flat at the close, re-entry at the reopen). Intraday low =
  min(risk / 1,000 x the day's lowest hourly cumulative low of the continuous $1,000-risk K path (no costs; RTH 5-minute ES=F / NQ=F /
  RTY=F against the prior full session's last close, as research c343), the day's P&L, 0). Research c338 us_stream_int + c343 paths.
- cfd: US CFD leg x ru + crypto $1,000 x vc x ensemble at CFD costs, gap-aware personal stop g (c348f cfd_stream); gap_rule = no US
  entry on the last session before a closure (FTMO). FundedNext's funded stage uses its own funded setup.
- mix: US CFD leg x ru + crypto at perp costs x vt, personal stop g on the hourly combined low (research c387_opt.mix_stream).
- perp: crypto at perp costs x vt (Binance funding estimated from the premium index), 10-day close cost where `ten` (c348f).
All CFD / mix / perp amounts are per $100K and scaled by the account size.
Engine: research c341 sim_year (C387 Amendment 5 fixed version: an account out of attempts stops) on one path: a breach starts a new
attempt (and fee) the next day, at most 3 attempts; monthly fees bill every 30 evaluation days; eval_days expiry; payout rules as
the plan (first_wait, cycle, win_days / win_thr, min_cycle, cap, max_frac, buffer, consistency, new_frac, split, refund,
floor_zero_after_pay). Window 2026-12-01 .. 2027-11-30 (365 UTC days); every account starts its first attempt on 2026-12-01.
Usage: python3 book_logger.py [STATE_DIR] | python3 book_logger.py --backtest START END OUT.csv  (streams, for checking against research)
"""
import csv, importlib.util, json, math, os, sys
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("c348f_logger", os.path.join(HERE, "..", "c348f", "book_logger.py"))
base = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(base)
BOOK = json.load(open(os.path.join(HERE, "book.json"))); ENT = {e["id"]: e for e in BOOK["entries"]}; BOOKS = BOOK["books"]
START = date.fromisoformat(os.environ.get("C390F_START", "2026-12-01")); END = START + timedelta(days=364)
MICRO = {"^GSPC": (5.0, 0.25), "^NDX": (2.0, 0.25), "^RUT": (5.0, 0.10), "^DJI": (0.5, 1.0)}   # point value $, tick (MES MNQ M2K MYM)
COMM, MAXC, MAX_ATT, INF = 0.70, 50, 3, float("inf")
FUT_SPECS = sorted({(e["stream"]["risk"], e["stream"]["session"], e["stream"]["K"]) for e in BOOK["entries"] if e["stream"]["kind"] == "fut"})


# ---------------------------------------------------------------- futures streams (research c338 us_stream_int, c343 paths)
def fut_streams(data, V, first, last):
    """{(risk, session, K): {date: (P&L $, active)}} for every futures spec, integer micros, days first..last."""
    out = {}
    for risk, sess, K in FUT_SPECS:
        acc = {}
        for s in base.US:
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
        out[(risk, sess, K)] = acc
    return out


def fut_lows(data, f5, V, first, last, K):
    """{date: lowest hourly cumulative low} of the continuous $1,000-risk US path at threshold K, summed over the 4 indices, no costs
    (research c343; RTH bars as c348f us_paths: prior full session's last close, roll re-base, a missing hour repeats the previous
    close, hours after the cash close carry the day's close-to-close P&L, a day without a full proxy session books it at 20-23 UTC
    with low = 1.5 x the loss). Also returns the K path's entry / exit events."""
    LOW, ev = {}, []
    for s in base.US:
        px = data[s]; days = list(px); sc, atr, C = V[s]; pos = None
        f = f5[base.PROXY[s]]; full = [d for d in f if len(f[d]) >= 74]; fprev = {full[j]: full[j - 1] for j in range(1, len(full))}
        for i, d in enumerate(days):
            inr = first <= d <= last
            if pos is None:
                if d in sc and abs(sc[d]) >= K and d in atr:
                    pos = dict(sg=base.sgn(sc[d]), e=C[i], u=1.5 * atr[d], n=1000.0 / (1.5 * atr[d]), i0=i)
                    if inr:
                        ev.append((d, f"K{K} {s} entry {'long' if pos['sg'] > 0 else 'short'} ({sc[d]})"))
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
                if inr:
                    ev.append((d, f"K{K} {s} exit ({rt / pos['u']:+.2f}R)"))
                pos = None
    return {d: min(v) for d, v in LOW.items()}, ev


# ---------------------------------------------------------------- per-entry streams
def raw_day(d, Un, Unp, crc, crp, ten):
    """replaces c348f day_streams inside its compute(): keep the hourly inputs, every entry's stream is built below."""
    z = ([0.0] * 24, [0.0] * 24, [0.0] * 24)
    return dict(Un=Un.get(d, z), Unp=Unp.get(d, z), crc=crc, crp=crp, ten=ten, oh=9 + base.utc_off(d))


base.day_streams = raw_day


def mix_stream(U, PP, ru, vt, g):
    E = ru * U[0][23] + vt * PP[0][23]; lh = [ru * U[1][h] + vt * PP[1][h] for h in range(24)]; Lo = min(min(lh), E, 0.0)
    if Lo < -g:
        return -g, E != 0, -g, "stop"
    return E, E != 0, Lo, ""


def entry_streams(e, R, FS, FL, d):
    """(challenge stream, funded stream or None) of one entry on day d; a stream = (P&L, active, intraday low, note)."""
    st = e["stream"]; k = st["kind"]
    if k == "fut":
        x, a = FS[(st["risk"], st["session"], st["K"])].get(d, (0.0, False)); lo = min(st["risk"] / 1000.0 * FL[st["K"]].get(d, 0.0), x, 0.0)
        return (x, a, lo, ""), None
    s = st["size"]; sc = lambda T: (T[0] * s, T[1], T[2] * s, T[3])
    if k == "cfd":
        U = R["Unp"] if st["gap_rule"] else R["Un"]; S = sc(base.cfd_stream(U, R["crc"], st["ru"], st["vc"], st["g"], R["oh"]))
        Sf = sc(base.cfd_stream(U, R["crc"], st["funded"]["ru"], st["funded"]["vc"], st["g"], R["oh"])) if st.get("funded") else None
        return S, Sf
    if k == "mix":
        return sc(mix_stream(R["Un"], R["crp"], st["ru"], st["vt"], st["g"])), None
    return sc(base.perp_stream(R["crp"], st["vt"], st["vt"] * R["ten"] if st["ten"] else 0.0)), None


# ---------------------------------------------------------------- account engine (research c341 sim_year, fixed, one path)
def rules(plan):
    F = plan["funded"]; out = []
    for p in plan["phases"] + [F]:
        fu = p is F
        out.append(dict(tgt=INF if fu else p["target"], mll=p["mll"], eod=p.get("type", "eod") == "eod", lock=p.get("lock", True),
                        dll=p.get("dll") or INF, soft=p.get("soft", True), cons=0.0 if fu else (p.get("cons") or 0.0), mind=0 if fu else p.get("min_days", 0),
                        lka=p.get("lock_at", 0.0)))
    return out


def new_account(e):
    fee = float(e["plan"]["fee"])
    return dict(st=0, bal=0.0, hw=0.0, td=0, best=0.0, age=0, since=0, wins=0, cyc=0.0, cbest=0.0, npay=0, refd=False, fz=False, cash=-fee,
                fees=fee, payouts=0.0, attempts=1, dead=False, restart=False, first_fund=None, first_pay=None, n=0)


def step(a, e, S, Sf=None, t=None):
    """advance one account by one calendar day. S / Sf = (P&L, active, intraday low, note) for the challenge / funded stage.
    Returns (day P&L booked to the balance, events)."""
    plan = e["plan"]; F = plan["funded"]; R = rules(plan); nph = len(plan["phases"]); fee = float(plan["fee"]); ev = []
    if a["restart"] and a["attempts"] >= MAX_ATT:
        a["dead"] = True; a["restart"] = False; ev.append(f"stopped after {MAX_ATT} attempts")
    if a["restart"]:
        a.update(st=0, bal=0.0, hw=0.0, td=0, best=0.0, age=0, since=0, wins=0, cyc=0.0, cbest=0.0, npay=0, refd=False, fz=False, restart=False)
        a["cash"] -= fee; a["fees"] += fee; a["attempts"] += 1; ev.append(f"attempt {a['attempts']} starts (fee ${fee:,.2f})")
    fu = a["st"] == nph; dead = a["dead"]; k = 0.0 if dead else (e["fm"] if fu else e["cm"])
    X = Sf if (fu and Sf is not None) else S; pnl = X[0] * k; low = min(X[2], 0.0) * k
    if X[3] and not dead:
        ev.append(f"{X[3]} (stream)")
    g = e["guard"]
    if g is not None and low < -g:
        pnl = low = -g; ev.append(f"personal stop -${g:,.0f}")
    r = R[a["st"]]; hit = low < -r["dll"]; hard = hit and not r["soft"]
    if hit and r["soft"]:
        pnl = -r["dll"]; low = -r["dll"]; ev.append("soft daily limit")      # C402 fix: a soft breach books exactly -dll
    floor = (a["hw"] - r["mll"]) if r["eod"] else -r["mll"]
    if r["lock"]:
        floor = min(floor, r["lka"])
    if a["fz"]:
        floor = max(floor, r["lka"])                        # C402: lock_at (default 0 = unchanged)
    br = hard or (a["bal"] + low <= floor)
    if br and not dead:
        ev.append(f"BREACH ({'daily' if hard else 'max'} loss) in {'funded' if fu else 'phase ' + str(a['st'] + 1)}")
    if not br:
        a["bal"] += pnl
    a["hw"] = max(a["hw"], a["bal"]); ok = (not br) and not dead
    a["td"] += int(ok and bool(X[1]))
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
            act = plan.get("activation", 0.0)
            a["cash"] -= act; a["fees"] += act
            if a["first_fund"] is None:
                a["first_fund"] = str(t) if t else a["n"]
            if act:
                ev.append(f"activation fee ${act:,.2f}")
            a["n"] += 1; a["restart"] = False
            return pnl, ev                                 # nf: no funded-stage bookkeeping on the day of funding (research ~nf)
    fa = ok and a["st"] == nph
    if fa:
        a["since"] += int(bool(X[1]) or F.get("wait_cal", False))      # C402 fix: waits count days with a position unless calendar days
        a["wins"] += int(pnl >= F.get("win_thr", 0.01)); a["cyc"] += pnl; a["cbest"] = max(a["cbest"], pnl)
    wait = F.get("first_wait", 0) if a["npay"] == 0 else F.get("cycle", 1)
    amt = min(F.get("cap", INF), F.get("max_frac", 1.0) * (a["bal"] - F.get("buffer", 0.0)))
    if F.get("new_frac"):
        amt = min(amt, max(a["cyc"], 0.0) / F["new_frac"])
    okp = fa and a["since"] >= wait and a["wins"] >= F.get("win_days", 0) and a["cyc"] >= F.get("min_cycle", 0.0) and amt >= max(F.get("min_pay", 0.0), 1.0)
    if okp and F.get("cons"):
        okp = a["cbest"] <= F["cons"] * max(a["cyc"], 1e-9)
    if okp:
        p = F["split"] * amt; a["cash"] += p; a["payouts"] += p; a["npay"] += 1; ev.append(f"payout ${p:,.2f}")
        if a["first_pay"] is None:
            a["first_pay"] = str(t) if t else a["n"]
        if plan.get("refund") and not a["refd"] and a["npay"] >= plan.get("refund_n", 1):
            a["cash"] += fee; a["fees"] -= fee; ev.append(f"fee refund ${fee:,.2f}")
        a["refd"] = a["refd"] or a["npay"] >= plan.get("refund_n", 1)
        a["bal"] -= amt; a["since"] = 0; a["wins"] = 0; a["cyc"] = 0.0; a["cbest"] = 0.0
        if F.get("floor_zero_after_pay"):
            a["fz"] = True
    if plan.get("eval_days") and a["st"] < nph and a["age"] >= plan["eval_days"] and not dead:
        if not br:
            ev.append(f"evaluation expired ({plan['eval_days']} days)")
        br = True
    a["restart"] = br and not dead; a["n"] += 1
    return pnl, ev


def stage(a, e):
    return "dead" if a["dead"] else ("funded" if a["st"] == len(e["plan"]["phases"]) else f"phase {a['st'] + 1}")


# ---------------------------------------------------------------- run
def compute(data, f5, first, last, live_today=None, hourly=None, wait=False):
    """c348f compute (unchanged; hourly inputs kept) plus the futures streams and every entry's streams per day."""
    rows, why = base.compute(data, f5, first, last, live_today=live_today, hourly=hourly, wait=wait)
    if not rows:
        return rows, why
    last = rows[-1]["date"]; vix = {d: v[2] for d, v in data["^VIX"].items()}; spx = {d: v[2] for d, v in data["^GSPC"].items()}
    rut = {d: v[2] for d, v in data["^RUT"].items()}; V = {s: base.us_votes(data[s], vix, spx, rut, list(data[s])) for s in base.US}
    FS = fut_streams(data, V, first, last); FL, fev = {}, []
    for K in (5, 4):
        FL[K], ev = fut_lows(data, f5, V, first, last, K); fev += ev
    for r in rows:
        d = r["date"]; r["E"] = {i: entry_streams(e, r["S"], FS, FL, d) for i, e in ENT.items()}
        r["events"] = [x for x in r["events"] if not x.startswith("FTMO book")] + [x[1] for x in fev if x[0] == d]
        r["fut_low"] = {K: FL[K].get(d, 0.0) for K in (5, 4)}
    return rows, why


def backtest(a, b, path):
    a, b = date.fromisoformat(a), date.fromisoformat(b); data, f5 = base.fetch(); rows, _ = compute(data, f5, a, b)
    with open(path, "w", newline="") as f:
        w = csv.writer(f); ids = list(ENT)
        w.writerow(["date"] + [f"{i}_{x}" for i in ids for x in ("E", "A", "Lo", "Ef", "Lof")] + ["futlow_K5", "futlow_K4", "events"])
        for r in rows:
            row = [r["date"].isoformat()]
            for i in ids:
                S, Sf = r["E"][i]; row += [round(S[0], 4), int(bool(S[1])), round(S[2], 4)] + ([round(Sf[0], 4), round(Sf[2], 4)] if Sf else ["", ""])
            w.writerow(row + [round(r["fut_low"][5], 4), round(r["fut_low"][4], 4), "; ".join(r["events"])])


def book_cash(S):
    return {b: round(sum(n * S["acc"][i]["cash"] for i, n in v["entries"].items()), 2) for b, v in BOOKS.items()}


def main(stdir):
    os.makedirs(stdir, exist_ok=True); sp = os.path.join(stdir, "state.json")
    S = json.load(open(sp)) if os.path.exists(sp) else dict(last=str(START - timedelta(days=1)), acc={i: new_account(e) for i, e in ENT.items()})
    today = datetime.now(timezone.utc).date(); first = date.fromisoformat(S["last"]) + timedelta(days=1); upto = min(today - timedelta(days=1), END)
    if upto < first:
        print("nothing new to log" + (f" (log starts {START})" if first == START else (" (window ended)" if first > END else ""))); return
    data, f5 = base.fetch()
    for c in base.CRY:                                       # drop the still-forming bar of the current UTC day
        data[c] = {d: v for d, v in data[c].items() if d < today}
    rows, why = compute(data, f5, first, upto, live_today=today, wait=True)
    if not rows:
        print(why or "waiting for data"); return
    ids = list(ENT); fs, fa, fb = (os.path.join(stdir, x) for x in ("streams.csv", "accounts.csv", "books.csv"))
    new = {x: not os.path.exists(x) for x in (fs, fa, fb)}
    with open(fs, "a", newline="") as f1, open(fa, "a", newline="") as f2, open(fb, "a", newline="") as f3:
        w1, w2, w3 = csv.writer(f1), csv.writer(f2), csv.writer(f3)
        if new[fs]:
            w1.writerow(["date"] + [f"{i}_{x}" for i in ids for x in ("pnl", "low")] + [f"{ENT[i]['id']}_funded_{x}" for i in ids if ENT[i]["stream"].get("funded") for x in ("pnl", "low")]
                        + ["futlow_K5_per1000", "futlow_K4_per1000", "btc_pos", "eth_pos", "fund_btc", "fund_eth", "events"])
        if new[fa]:
            w2.writerow(["date", "entry", "plan", "attempt", "stage", "day_pnl", "balance", "cash_to_date", "events"])
        if new[fb]:
            w3.writerow(["date"] + list(BOOKS))
        for r in rows:
            d = r["date"]
            w1.writerow([d.isoformat()] + [round(r["E"][i][0][j], 2) for i in ids for j in (0, 2)]
                        + [round(r["E"][i][1][j], 2) for i in ids if ENT[i]["stream"].get("funded") for j in (0, 2)]
                        + [round(r["fut_low"][5], 2), round(r["fut_low"][4], 2), round(r["pos"]["BTC-USD"], 4), round(r["pos"]["ETH-USD"], 4),
                           round(r["fund"]["BTC-USD"], 8), round(r["fund"]["ETH-USD"], 8), "; ".join(r["events"])])
            for i in ids:
                a = S["acc"][i]; Sx, Sf = r["E"][i]; pnl, ev = step(a, ENT[i], Sx, Sf, t=d)
                w2.writerow([d.isoformat(), i, ENT[i]["key"], a["attempts"], stage(a, ENT[i]), round(pnl, 2), round(a["bal"], 2), round(a["cash"], 2), "; ".join(ev)])
            bc = book_cash(S); w3.writerow([d.isoformat()] + [bc[b] for b in BOOKS])
            print(d, " ".join(f"{b}={bc[b]:,.0f}" for b in BOOKS), "; ".join(r["events"]), flush=True)
    S["last"] = rows[-1]["date"].isoformat(); S["books"] = book_cash(S)
    json.dump(S, open(sp, "w"), indent=1)
    if why:
        print(why)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--backtest":
        backtest(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "state"))
