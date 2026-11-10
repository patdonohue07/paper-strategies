"""C125-FWD: forward paper scoring of the two strongest C125 options survivors on REAL Alpaca option quotes (log only: no orders).

Frozen rules (research_lab claude/c125-options-batch-summary.md, claude/c125-fwd-rules.md):
A) F20_02442 put-write, SPY as the SPX proxy (no SPX options on Alpaca). Candidate days: every 5th trading day (anchor 2026-11-09).
   Enter only if SPY close > its 200-day mean and no position is open. Sell 1 put at |delta| closest to 0.10, first expiry >= 60
   calendar days out. Fill: at the BID (primary) and at mid (info). Daily mark: buy back at the ASK once (credit - ask) >= 50% of the
   credit; otherwise hold to expiry, settle at intrinsic on the expiry close.
B) F07_02095 rich-IV short strangles. Daily: 30d ATM IV per name (interpolated in total variance between the two expiries bracketing
   30 days, ATM = strike nearest spot, mean of call and put IV). peer_raw = ln(IV) - ln(median IV of the name's sector);
   peer_dm = peer_raw - mean(peer_raw over the name's trailing <= 252 stored days). Weekly (every 5th trading day, same anchor): the
   3 names with the highest peer_dm (>= 60 stored days of history required) and no open position. Sell the 25-delta call and
   25-delta put, first expiry >= 45 days, at the BID (mid info). Skip if an earnings date (known, or projected last + k*91 days,
   +-7 day buffer) falls between entry and expiry. Hold to expiry, settle at intrinsic.
S) C157 amendment (added 2026-11-10; A and B above are unchanged). Same weekly ranking as B, but peer_dm uses history SEEDED from the
   Bloomberg export (iv_seed.csv: peer_raw per name for the 252 trading days to 2026-09-29, same formula on Bloomberg 30d ATM IV), so
   it can rank from the first candidate day. Seed rows are used only for dates before the name's first stored Alpaca day and age out
   of the trailing window. Each pick logs TWO structures on the same expiry (first >= 45 days): S1 the short 25-delta strangle, and
   S2 an iron condor = S1 plus long 10-delta wings (wing |delta| within 0.04 of 0.10, else no condor). Shorts fill at the bid, wings
   at the ask (mid info). Same earnings skip and no-stacking as B, with its own open list. Hold to expiry, settle at intrinsic.
   Decision at 100 settled picks, each structure separately: pass if mean net > 0 with month-clustered t >= 2.
P&L unit: bp of the underlying price at entry, per 1 share, after $0.0065/share/leg/side commission. No early assignment modeled.
Decision: A at 40 settled trades, B at 100: pass if mean net > 0 with month-clustered t >= 2 on the bid/ask (primary) series.
State: optfwd/state/{state.json, a_trades.csv, b_trades.csv, s_trades.csv, iv_hist.csv, summary.md, log.txt}.
Usage: python3 opt_fwd.py [--mock]   (--mock: synthetic quotes, temp state dir, no network: logic test only)"""
import os, sys, json, math, csv, time, random, tempfile, urllib.request, urllib.parse, datetime as dt
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York"); MOCK = "--mock" in sys.argv; HERE = os.path.dirname(os.path.abspath(__file__))
D = (os.environ.get("OPTFWD_MOCKDIR") or tempfile.mkdtemp()) if MOCK else os.path.join(HERE, "state"); os.makedirs(D, exist_ok=True)
DATA = "https://data.alpaca.markets"; COMM = 0.0065; ANCHOR = dt.date(2026, 11, 9)
SECTOR = {"AAPL": "IT", "ACN": "IT", "ADBE": "IT", "ADI": "IT", "AMAT": "IT", "AMD": "IT", "AVGO": "IT", "CRM": "IT", "CSCO": "IT", "DELL": "IT",
 "ENPH": "IT", "IBM": "IT", "INTC": "IT", "INTU": "IT", "KLAC": "IT", "LRCX": "IT", "MRVL": "IT", "MSFT": "IT", "MSTR": "IT", "MU": "IT",
 "NOW": "IT", "NVDA": "IT", "ON": "IT", "ORCL": "IT", "PANW": "IT", "PLTR": "IT", "QCOM": "IT", "SMCI": "IT", "TXN": "IT", "WDC": "IT",
 "ABBV": "HC", "ABT": "HC", "ALGN": "HC", "AMGN": "HC", "BSX": "HC", "GILD": "HC", "ISRG": "HC", "JNJ": "HC", "LLY": "HC", "MDT": "HC",
 "MRK": "HC", "MRNA": "HC", "PFE": "HC", "REGN": "HC", "SYK": "HC", "TMO": "HC", "UNH": "HC", "VRTX": "HC", "ZTS": "HC",
 "AFRM": "FIN", "BAC": "FIN", "BLK": "FIN", "BRK.B": "FIN", "CB": "FIN", "COIN": "FIN", "GS": "FIN", "HOOD": "FIN", "JPM": "FIN",
 "MA": "FIN", "SPGI": "FIN", "V": "FIN", "ADP": "IND",
 "AMZN": "CD", "BKNG": "CD", "CHWY": "CD", "DKNG": "CD", "ETSY": "CD", "HD": "CD", "LOW": "CD", "MCD": "CD", "TJX": "CD", "TSLA": "CD",
 "UBER": "IND", "CMCSA": "COM", "DIS": "COM", "GOOGL": "COM", "META": "COM", "NFLX": "COM", "PINS": "COM", "RBLX": "COM", "ROKU": "COM",
 "SNAP": "COM", "T": "COM", "VZ": "COM", "CL": "STAP", "COST": "STAP", "KO": "STAP", "PEP": "STAP", "PG": "STAP", "PM": "STAP", "WMT": "STAP",
 "COP": "EN", "CVX": "EN", "XOM": "EN", "CAT": "IND", "ETN": "IND", "FDX": "IND", "GE": "IND", "HON": "IND", "ITW": "IND", "NSC": "IND",
 "RTX": "IND", "UNP": "IND", "APD": "MAT", "LIN": "MAT", "SHW": "MAT", "DUK": "UTIL", "NEE": "UTIL", "SO": "UTIL", "EQIX": "RE"}

def log(m):
    s = f"{dt.datetime.now(ET):%Y-%m-%d %H:%M:%S} ET {m}"; print(s, flush=True); open(os.path.join(D, "log.txt"), "a").write(s + "\n")
if not MOCK:
    kv = dict(l.strip().split("=", 1) for l in open(os.path.expanduser("~/.alpaca_paper")) if "=" in l)
    HDR = {"APCA-API-KEY-ID": kv["APCA_API_KEY_ID"], "APCA-API-SECRET-KEY": kv["APCA_API_SECRET_KEY"], "User-Agent": "research-script/1.0"}
def get(path, **q):
    time.sleep(0.35)   # stay under Alpaca free-tier 200 requests/min
    u = DATA + path + ("?" + urllib.parse.urlencode({k: v for k, v in q.items() if v is not None}) if q else ""); err = ""
    for k in range(4):
        try: return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=HDR), timeout=40).read())
        except Exception as e: err = str(e)[:120]; time.sleep(2 + 4 * k)
    log(f"GET fail {path} {err}"); return None

# ---------------------------------------------------------------- data access (real or mock)
_mock = {}
def stock_closes(sym, days=320):
    """Daily closes (date -> close), oldest first, SIP bars (adjusted), ending at the last completed bar or today."""
    if MOCK:
        rnd = random.Random(hash(sym) % 999); p = 100 + rnd.random() * 400; out = {}; d0 = dt.date.today() - dt.timedelta(days=days * 1.45)
        for i in range(days):
            p *= math.exp(rnd.gauss(0.0004, 0.012)); out[(d0 + dt.timedelta(days=int(i * 1.45))).isoformat()] = p
        return out
    start = (dt.date.today() - dt.timedelta(days=int(days * 1.5))).isoformat(); out = {}; tok = None
    while True:
        r = get("/v2/stocks/bars", symbols=sym, timeframe="1Day", start=start, adjustment="all", feed="sip", limit=10000, page_token=tok) or {}
        for b in (r.get("bars") or {}).get(sym, []): out[b["t"][:10]] = float(b["c"])
        tok = r.get("next_page_token")
        if not tok: break
    return out
def spot(syms):
    if MOCK: return {s: list(stock_closes(s).values())[-1] for s in syms}
    out = {}
    for i in range(0, len(syms), 50):
        r = get("/v2/stocks/snapshots", symbols=",".join(syms[i:i + 50]), feed="iex") or {}
        for s, v in r.items():
            p = (v.get("latestTrade") or {}).get("p") or (v.get("dailyBar") or {}).get("c")
            if p: out[s] = float(p)
    return out
def parse_occ(sym):
    """SPY261218P00600000 -> (root, expiry date, 'C'/'P', strike)."""
    i = len(sym) - 15; return sym[:i], dt.date(2000 + int(sym[i:i + 2]), int(sym[i + 2:i + 4]), int(sym[i + 4:i + 6])), sym[i + 6], int(sym[i + 7:]) / 1000
def chain(und, S, dmin, dmax, kpct=0.25):
    """List of dicts: sym, exp, cp, K, bid, ask, iv, delta for expiries in [today+dmin, today+dmax] and strikes within +-kpct of S."""
    today = dt.date.today(); rows = []
    if MOCK:
        rnd = random.Random(hash(und) % 777); iv0 = 0.2 + rnd.random() * 0.3
        for dd in [d for d in range(dmin, dmax + 1) if (today + dt.timedelta(days=d)).weekday() == 4]:
            T = dd / 365
            for m in [x / 100 for x in range(75, 126)]:
                K = round(S * m, 0)
                for cp in "CP":
                    iv = iv0 * (1 + 0.6 * max(0, 1 - m)); sq = iv * math.sqrt(T); d1 = (math.log(S / K) + 0.5 * iv * iv * T) / sq
                    N = lambda x: 0.5 * math.erfc(-x / math.sqrt(2)); dlt = N(d1) if cp == "C" else N(d1) - 1
                    px = (S * N(d1) - K * N(d1 - sq)) if cp == "C" else (K * N(sq - d1) - S * N(-d1))
                    sp = max(0.01, 0.03 * px); rows.append(dict(sym=f"{und}{(today + dt.timedelta(days=dd)):%y%m%d}{cp}{int(K * 1000):08d}",
                        exp=today + dt.timedelta(days=dd), cp=cp, K=K, bid=max(0.0, round(px - sp, 2)), ask=round(px + sp, 2), iv=iv, delta=dlt))
        return rows
    tok = None
    while True:
        r = get(f"/v1beta1/options/snapshots/{und}", feed="indicative", limit=1000, page_token=tok,
                expiration_date_gte=(today + dt.timedelta(days=dmin)).isoformat(), expiration_date_lte=(today + dt.timedelta(days=dmax)).isoformat(),
                strike_price_gte=f"{S * (1 - kpct):.2f}", strike_price_lte=f"{S * (1 + kpct):.2f}") or {}
        for sym, v in (r.get("snapshots") or {}).items():
            q = v.get("latestQuote") or {}; g = v.get("greeks") or {}
            try: _, ex, cp, K = parse_occ(sym)
            except Exception: continue
            rows.append(dict(sym=sym, exp=ex, cp=cp, K=K, bid=float(q.get("bp") or 0), ask=float(q.get("ap") or 0),
                             iv=v.get("impliedVolatility"), delta=g.get("delta")))
        tok = r.get("next_page_token")
        if not tok: break
    return rows
def quote(sym):
    """Current bid/ask for one option symbol."""
    if MOCK: return _mock.get(sym)
    r = get("/v1beta1/options/snapshots", symbols=sym, feed="indicative") or {}
    q = ((r.get("snapshots") or {}).get(sym) or {}).get("latestQuote") or {}
    return dict(bid=float(q.get("bp") or 0), ask=float(q.get("ap") or 0)) if q else None

# ---------------------------------------------------------------- helpers
st = json.load(open(os.path.join(D, "state.json"))) if os.path.exists(os.path.join(D, "state.json")) else {"a": [], "b": [], "days": []}
st.setdefault("s", [])
def append(name, row, cols):
    p = os.path.join(D, name); new = not os.path.exists(p)
    with open(p, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if new: w.writeheader()
        w.writerow({c: row.get(c) for c in cols})
def first_exp(rows, mind):
    exps = sorted({r["exp"] for r in rows if (r["exp"] - dt.date.today()).days >= mind}); return exps[0] if exps else None
def pick_delta(rows, exp, cp, target):
    c = [r for r in rows if r["exp"] == exp and r["cp"] == cp and r["delta"] is not None and r["bid"] > 0 and r["ask"] > r["bid"]]
    return min(c, key=lambda r: abs(abs(r["delta"]) - target)) if c else None
def is_candidate_day(today, tdays):
    """Every 5th trading day counted from ANCHOR on the stored trading-day list."""
    seq = [d for d in tdays if d >= ANCHOR.isoformat()]; return today.isoformat() in seq and seq.index(today.isoformat()) % 5 == 0
def settle_value(cp, K, S): return max(0.0, (S - K) if cp == "C" else (K - S))
def tstat(pnls, months):
    by = {}
    for x, m in zip(pnls, months): by.setdefault(m, []).append(x)
    n = len(pnls); mu = sum(pnls) / n if n else 0
    if len(by) < 3: return mu, float("nan"), len(by)
    r = [sum(v) - mu * len(v) for v in by.values()]; se = math.sqrt(sum(x * x for x in r) * len(by) / (len(by) - 1)) / n
    return mu, (mu / se if se else float("nan")), len(by)

# ---------------------------------------------------------------- earnings (for B)
def earn_dates():
    out = {}
    for r in csv.DictReader(open(os.path.join(HERE, "earnings_dates.csv"))): out.setdefault(r["ticker"], []).append(dt.date.fromisoformat(r["date"]))
    return out
def earnings_between(tk, a, b, E):
    ds = sorted(E.get(tk, []))
    if not ds: return False
    proj = list(ds) + [ds[-1] + dt.timedelta(days=91 * k) for k in range(1, 9)]
    return any(a - dt.timedelta(days=7) <= d <= b + dt.timedelta(days=7) for d in proj)

# ---------------------------------------------------------------- run
def run():
    now = dt.datetime.now(ET); today = now.date()
    if today.weekday() >= 5 and not MOCK: log("weekend: skip"); return
    log(f"run start mock={MOCK}")
    spy = stock_closes("SPY")
    tdays = sorted(set(st["days"]) | set(spy)); tdays = [d for d in tdays if d <= today.isoformat()]
    if today.isoformat() not in tdays: tdays.append(today.isoformat())
    st["days"] = tdays[-400:]
    names = sorted(SECTOR); px = spot(["SPY"] + names); S_spy = px.get("SPY")
    cand = is_candidate_day(today, st["days"]) or MOCK
    # ---------------- A: SPY put-write
    for p in st["a"]:
        if p["status"] != "open": continue
        exp = dt.date.fromisoformat(p["exp"])
        if today >= exp:
            S = spy.get(exp.isoformat(), S_spy); v = settle_value("P", p["K"], S)
            p.update(status="settled", exit_date=exp.isoformat(), exit_px=v, how="expiry")
        else:
            q = quote(p["sym"])
            if q and q["ask"] > 0 and (p["credit_bid"] - q["ask"]) >= 0.5 * p["credit_bid"]:
                p.update(status="settled", exit_date=today.isoformat(), exit_px=q["ask"], how="tp50", exit_mid=(q["bid"] + q["ask"]) / 2)
        if p["status"] == "settled":
            p["pnl_bp"] = (p["credit_bid"] - p["exit_px"] - COMM * (1 if p["how"] == "expiry" else 2)) / p["S0"] * 1e4
            p["pnl_mid_bp"] = (p["credit_mid"] - p.get("exit_mid", p["exit_px"])) / p["S0"] * 1e4
            append("a_trades.csv", p, ["sym", "entry", "S0", "K", "exp", "credit_bid", "credit_mid", "exit_date", "exit_px", "how", "pnl_bp", "pnl_mid_bp"])
            log(f"A SETTLED {p['sym']} {p['how']} pnl {p['pnl_bp']:+.1f}bp")
    closes = list(spy.values()); ma = sum(closes[-200:]) / 200 if len(closes) >= 200 else None
    a_open = any(p["status"] == "open" for p in st["a"])
    if cand and S_spy and ma and S_spy > ma and not a_open:
        rows = chain("SPY", S_spy, 60, 95, 0.3); ex = first_exp(rows, 60); o = pick_delta(rows, ex, "P", 0.10) if ex else None
        if o:
            if MOCK: _mock[o["sym"]] = dict(bid=o["bid"] * 0.4, ask=o["ask"] * 0.45)
            st["a"].append(dict(sym=o["sym"], entry=today.isoformat(), S0=S_spy, K=o["K"], exp=o["exp"].isoformat(), delta=o["delta"],
                                credit_bid=o["bid"] - COMM, credit_mid=(o["bid"] + o["ask"]) / 2, status="open"))
            log(f"A ENTER sell {o['sym']} K {o['K']} delta {o['delta']:.3f} bid {o['bid']} ask {o['ask']} (SPY {S_spy:.2f} > MA200 {ma:.2f})")
    elif cand: log(f"A no entry: open={a_open} SPY {S_spy} MA200 {ma}")
    # ---------------- B: IV history (daily) + weekly rich-IV short strangles
    ivh_p = os.path.join(D, "iv_hist.csv"); hist = {}
    if MOCK and not os.path.exists(ivh_p):   # mock only: fake 80 days of peer_raw so the ranking path runs
        rnd = random.Random(5)
        for k in range(80, 0, -1):
            for tk in names: append("iv_hist.csv", dict(date=(today - dt.timedelta(days=k)).isoformat(), ticker=tk, peer_raw=rnd.gauss(0, 0.1), iv30=0.3), ["date", "ticker", "peer_raw", "iv30"])
    if os.path.exists(ivh_p):
        for r in csv.DictReader(open(ivh_p)): hist.setdefault(r["ticker"], []).append((r["date"], float(r["peer_raw"]), float(r["iv30"])))
    iv30, chains = {}, {}
    for tk in names:
        S = px.get(tk)
        if not S: continue
        rows = chain(tk, S, 7, 70, 0.12); chains[tk] = rows
        exps = sorted({r["exp"] for r in rows}); pts = []
        for e in exps:
            atm = [r for r in rows if r["exp"] == e and r["iv"]]
            if not atm: continue
            K = min({r["K"] for r in atm}, key=lambda k: abs(k - S)); v = [r["iv"] for r in atm if r["K"] == K]
            pts.append(((e - today).days, sum(v) / len(v)))
        lo = [p for p in pts if p[0] <= 30]; hi = [p for p in pts if p[0] >= 30]
        if lo and hi:
            (d1, v1), (d2, v2) = lo[-1], hi[0]
            w = v1 * v1 * d1 if d2 == d1 else v1 * v1 * d1 + (v2 * v2 * d2 - v1 * v1 * d1) * (30 - d1) / (d2 - d1)
            iv30[tk] = math.sqrt(max(w, 1e-6) / 30)
    sec = {}
    for tk, v in iv30.items(): sec.setdefault(SECTOR[tk], []).append(math.log(v))
    med = {s: sorted(x)[len(x) // 2] if len(x) % 2 else sum(sorted(x)[len(x) // 2 - 1:len(x) // 2 + 1]) / 2 for s, x in sec.items()}
    pdm = {}
    for tk, v in iv30.items():
        pr = math.log(v) - med[SECTOR[tk]]
        if not any(d == today.isoformat() for d, _, _ in hist.get(tk, [])):
            hist.setdefault(tk, []).append((today.isoformat(), pr, v)); append("iv_hist.csv", dict(date=today.isoformat(), ticker=tk, peer_raw=round(pr, 6), iv30=round(v, 5)), ["date", "ticker", "peer_raw", "iv30"])
        h = [x[1] for x in hist[tk][-253:-1]]
        if len(h) >= 60: pdm[tk] = pr - sum(h) / len(h)
    log(f"B iv30 for {len(iv30)} names; peer_dm ready for {len(pdm)}")
    for p in st["b"]:
        if p["status"] != "open": continue
        exp = dt.date.fromisoformat(p["exp"])
        if today >= exp:
            S = px.get(p["und"]) if today == exp else (stock_closes(p["und"], 40).get(exp.isoformat()) or px.get(p["und"]))
            if not S: continue
            v = settle_value("C", p["Kc"], S) + settle_value("P", p["Kp"], S)
            p.update(status="settled", exit_date=exp.isoformat(), S_exp=S, pnl_bp=(p["credit_bid"] - v) / p["S0"] * 1e4, pnl_mid_bp=(p["credit_mid"] - v) / p["S0"] * 1e4)
            append("b_trades.csv", p, ["und", "entry", "S0", "Kc", "Kp", "exp", "peer_dm", "credit_bid", "credit_mid", "exit_date", "S_exp", "pnl_bp", "pnl_mid_bp"])
            log(f"B SETTLED {p['und']} pnl {p['pnl_bp']:+.1f}bp")
    if cand and pdm:
        E = earn_dates(); openb = {p["und"] for p in st["b"] if p["status"] == "open"}; done = 0
        for tk, val in sorted(pdm.items(), key=lambda x: -x[1]):
            if done >= 3: break
            done += 1                                    # the top 3 ranks are the picks; an open/blocked name is skipped, not replaced
            if tk in openb: log(f"B skip {tk}: open"); continue
            rows = chains.get(tk) or []; ex = first_exp(chain(tk, px[tk], 45, 80, 0.3), 45) if rows is not None else None
            if not ex: log(f"B skip {tk}: no expiry >= 45d"); continue
            if earnings_between(tk, today, ex, E): log(f"B skip {tk}: earnings before {ex}"); continue
            rr = chain(tk, px[tk], (ex - today).days, (ex - today).days, 0.3); c = pick_delta(rr, ex, "C", 0.25); pu = pick_delta(rr, ex, "P", 0.25)
            if not (c and pu): log(f"B skip {tk}: no 25d legs"); continue
            cb = c["bid"] + pu["bid"] - 2 * COMM; cm = (c["bid"] + c["ask"] + pu["bid"] + pu["ask"]) / 2
            st["b"].append(dict(und=tk, entry=today.isoformat(), S0=px[tk], Kc=c["K"], Kp=pu["K"], exp=ex.isoformat(), peer_dm=round(val, 4),
                                credit_bid=cb, credit_mid=cm, status="open"))
            log(f"B ENTER short strangle {tk} {pu['K']}P/{c['K']}C exp {ex} peer_dm {val:+.3f} credit bid {cb:.2f} mid {cm:.2f}")
    # ---------------- S: seeded-history ranking; logs the strangle (S1) and the 10-delta-wing iron condor (S2)
    seed = {}; sp = os.path.join(HERE, "iv_seed.csv")
    if os.path.exists(sp):
        for r in csv.DictReader(open(sp)): seed.setdefault(r["ticker"], []).append((r["date"], float(r["peer_raw"])))
    pdm_s = {}
    for tk, v in iv30.items():
        own = [(d, x) for d, x, _ in hist.get(tk, [])]; first = own[0][0] if own else "9999-12-31"
        h = [x[1] for x in ([s for s in seed.get(tk, []) if s[0] < first] + own)[-253:-1]]
        if len(h) >= 60: pdm_s[tk] = (math.log(v) - med[SECTOR[tk]]) - sum(h) / len(h)
    log(f"S seeded peer_dm ready for {len(pdm_s)}")
    for p in st["s"]:
        if p["status"] != "open": continue
        exp = dt.date.fromisoformat(p["exp"])
        if today >= exp:
            S = px.get(p["und"]) if today == exp else (stock_closes(p["und"], 40).get(exp.isoformat()) or px.get(p["und"]))
            if not S: continue
            v = settle_value("C", p["Kc"], S) + settle_value("P", p["Kp"], S)
            p.update(status="settled", exit_date=exp.isoformat(), S_exp=S, pnl_bp=(p["credit_bid"] - v) / p["S0"] * 1e4, pnl_mid_bp=(p["credit_mid"] - v) / p["S0"] * 1e4)
            if p.get("cond_bid") is not None:
                w = settle_value("C", p["Kc2"], S) + settle_value("P", p["Kp2"], S)
                p.update(cond_pnl_bp=(p["cond_bid"] - (v - w)) / p["S0"] * 1e4, cond_pnl_mid_bp=(p["cond_mid"] - (v - w)) / p["S0"] * 1e4)
            append("s_trades.csv", p, ["und", "entry", "S0", "Kc", "Kp", "Kc2", "Kp2", "exp", "peer_dm", "credit_bid", "credit_mid", "cond_bid", "cond_mid",
                                       "exit_date", "S_exp", "pnl_bp", "pnl_mid_bp", "cond_pnl_bp", "cond_pnl_mid_bp"])
            log(f"S SETTLED {p['und']} strangle {p['pnl_bp']:+.1f}bp condor {'n/a' if p.get('cond_pnl_bp') is None else format(p['cond_pnl_bp'], '+.1f') + 'bp'}")
    if cand and pdm_s:
        E = earn_dates(); opens = {p["und"] for p in st["s"] if p["status"] == "open"}; done = 0
        for tk, val in sorted(pdm_s.items(), key=lambda x: -x[1]):
            if done >= 3: break
            done += 1
            if tk in opens: log(f"S skip {tk}: open"); continue
            ex = first_exp(chain(tk, px[tk], 45, 80, 0.3), 45)
            if not ex: log(f"S skip {tk}: no expiry >= 45d"); continue
            if earnings_between(tk, today, ex, E): log(f"S skip {tk}: earnings before {ex}"); continue
            rr = chain(tk, px[tk], (ex - today).days, (ex - today).days, 0.6); c = pick_delta(rr, ex, "C", 0.25); pu = pick_delta(rr, ex, "P", 0.25)
            if not (c and pu): log(f"S skip {tk}: no 25d legs"); continue
            cb = c["bid"] + pu["bid"] - 2 * COMM; cm = (c["bid"] + c["ask"] + pu["bid"] + pu["ask"]) / 2
            rec = dict(und=tk, entry=today.isoformat(), S0=px[tk], Kc=c["K"], Kp=pu["K"], exp=ex.isoformat(), peer_dm=round(val, 4),
                       credit_bid=cb, credit_mid=cm, cond_bid=None, cond_mid=None, Kc2=None, Kp2=None, status="open")
            c2 = pick_delta(rr, ex, "C", 0.10); p2 = pick_delta(rr, ex, "P", 0.10)
            if c2 and p2 and abs(abs(c2["delta"]) - 0.10) <= 0.04 and abs(abs(p2["delta"]) - 0.10) <= 0.04 and c2["K"] > c["K"] and p2["K"] < pu["K"]:
                rec.update(Kc2=c2["K"], Kp2=p2["K"], cond_bid=cb - c2["ask"] - p2["ask"] - 2 * COMM, cond_mid=cm - (c2["bid"] + c2["ask"] + p2["bid"] + p2["ask"]) / 2)
            st["s"].append(rec)
            log(f"S ENTER {tk} strangle {pu['K']}P/{c['K']}C exp {ex} peer_dm {val:+.3f} credit bid {cb:.2f}; condor wings {rec['Kp2']}P/{rec['Kc2']}C credit bid {rec['cond_bid'] if rec['cond_bid'] is None else round(rec['cond_bid'], 2)}")
    summary(now); json.dump(st, open(os.path.join(D, "state.json"), "w"), indent=0, default=str)

def summary(now):
    out = [f"# C125-FWD options forward paper score\nUpdated {now:%Y-%m-%d %H:%M} ET. Log only: no orders. Real Alpaca indicative quotes.\n"]
    for key, lab, target in [("a", "A: SPY 10-delta put-write, 60 DTE, MA200 filter, TP 50% (F20_02442)", 40), ("b", "B: rich-IV short 25d strangles, 45 DTE (F07_02095)", 100)]:
        s = [p for p in st[key] if p["status"] == "settled"]; o = sum(1 for p in st[key] if p["status"] == "open")
        if s:
            mu, t, m = tstat([p["pnl_bp"] for p in s], [p["entry"][:7] for p in s]); mm = sum(p["pnl_mid_bp"] for p in s) / len(s)
            out.append(f"## {lab}\n- Settled {len(s)} of {target}; open {o}\n- Mean net (bid/ask fills) {mu:+.1f} bp, month-clustered t {t:.2f} over {m} months; at mid {mm:+.1f} bp\n- Win rate {sum(1 for p in s if p['pnl_bp'] > 0) / len(s):.0%}\n")
        else: out.append(f"## {lab}\n- No settled trades yet; open {o}\n")
    for col, mid, lab in [("pnl_bp", "pnl_mid_bp", "S1: seeded-history short 25d strangles (C157)"), ("cond_pnl_bp", "cond_pnl_mid_bp", "S2: seeded-history iron condors, 10d wings (C157)")]:
        s = [p for p in st["s"] if p["status"] == "settled" and p.get(col) is not None]; o = sum(1 for p in st["s"] if p["status"] == "open")
        if s:
            mu, t, m = tstat([p[col] for p in s], [p["entry"][:7] for p in s]); mm = sum(p[mid] for p in s) / len(s)
            out.append(f"## {lab}\n- Settled {len(s)} of 100; open {o}\n- Mean net (bid/ask fills) {mu:+.1f} bp, month-clustered t {t:.2f} over {m} months; at mid {mm:+.1f} bp\n- Win rate {sum(1 for p in s if p[col] > 0) / len(s):.0%}; worst {min(p[col] for p in s):+.0f} bp\n")
        else: out.append(f"## {lab}\n- No settled trades yet; open {o}\n")
    out.append("Decision: pass if mean net > 0 and t >= 2 at the target count. Backtest (modeled) holdout: A +27bp/trade t 14.6; B +421bp/trade t 4.1.\n")
    open(os.path.join(D, "summary.md"), "w").write("\n".join(out))

if __name__ == "__main__":
    run()
    if MOCK: print("MOCK state dir:", D); print(open(os.path.join(D, "summary.md")).read())
