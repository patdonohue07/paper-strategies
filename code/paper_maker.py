"""C66 live paper maker (paper only; public Kalshi API; no orders). Loops every 5 minutes. State in research_lab/paper_maker/."""
import urllib.request, json, os, sys, time, math, datetime as dt, csv
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York"); UA = {"User-Agent": "student-research-script/1.0"}
API = "https://api.elections.kalshi.com/trade-api/v2"
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "paper_maker"); os.makedirs(D, exist_ok=True)
SP = os.path.join(D, "state.json"); LOG = os.path.join(D, "log.txt")
AB = ["KXBTCD", "KXETHD", "KXDOGED"]; RG = ["KXBTC", "KXETH", "KXDOGE"]
def log(m):
    s = f"{dt.datetime.now(ET):%Y-%m-%d %H:%M} {m}"; print(s, flush=True); open(LOG, "a").write(s + "\n")
def get(p):
    for k in range(4):
        try: return json.loads(urllib.request.urlopen(urllib.request.Request(API + p, headers=UA), timeout=30).read())
        except Exception as e: err = str(e)[:80]; time.sleep(3 + 5 * k)
    log(f"GET fail {p[:80]} {err}"); return {}
def px(m, k):  # price in dollars from either cents or *_dollars fields
    v = m.get(k + "_dollars", m.get(k))
    if v is None: return None
    v = float(v); return v / 100 if v > 1 else v
def fee(p): return math.ceil(0.0175 * p * (1 - p) * 100) / 100
st = json.load(open(SP)) if os.path.exists(SP) else {"orders": {}, "done_events": []}
def save(): json.dump(st, open(SP, "w"))
def place(series, kind):
    d = get(f"/events?series_ticker={series}&status=open&limit=200")
    for e in d.get("events", []):
        et_ = e["event_ticker"]
        if not et_.endswith("17") or et_ in st["done_events"]: continue
        ms = get(f"/markets?event_ticker={et_}&limit=200").get("markets", [])
        if not ms: continue
        close = dt.datetime.fromisoformat(ms[0]["close_time"].replace("Z", "+00:00"))
        now = dt.datetime.now(dt.timezone.utc)
        if not (close - dt.timedelta(hours=12) <= now < close - dt.timedelta(hours=11)): continue
        wk = close.astimezone(ET).weekday() >= 5; placed = 0
        quotes = []
        for m in ms:
            b, a = px(m, "yes_bid"), px(m, "yes_ask")
            if b and a and a > b: quotes.append((m["ticker"], b, a, (a + b) / 2))
        if kind == "ab":
            for t, b, a, mid in quotes:
                if 0.05 <= mid <= 0.35 and a - 0.01 > b: st["orders"][t] = {"ev": et_, "side": "sell", "p": round(a - 0.01, 2), "mid": mid, "wk": wk, "close": close.isoformat(), "filled": False, "touch": False, "last_ts": int(now.timestamp())}; placed += 1
                elif 0.65 <= mid <= 0.95 and b + 0.01 < a: st["orders"][t] = {"ev": et_, "side": "buy", "p": round(b + 0.01, 2), "mid": mid, "wk": wk, "close": close.isoformat(), "filled": False, "touch": False, "last_ts": int(now.timestamp())}; placed += 1
        else:
            if quotes:
                t, b, a, mid = max(quotes, key=lambda q: q[3])
                if b + 0.01 < a: st["orders"][t] = {"ev": et_, "side": "buy", "p": round(b + 0.01, 2), "mid": mid, "wk": wk, "close": close.isoformat(), "filled": False, "touch": False, "last_ts": int(now.timestamp()), "range": True}; placed += 1
        st["done_events"].append(et_); log(f"placed {placed} paper orders on {et_} ({'weekend' if wk else 'weekday'})")
def check_fills():
    now = int(time.time())
    for t, o in st["orders"].items():
        if o.get("settled") or o["filled"]: continue
        tr = get(f"/markets/trades?ticker={t}&min_ts={o['last_ts']}&limit=1000").get("trades", [])
        for x in tr:
            p = px(x, "yes_price")
            if p is None: continue
            if (o["side"] == "buy" and p < o["p"] - 1e-9) or (o["side"] == "sell" and p > o["p"] + 1e-9): o["filled"] = True
            if abs(p - o["p"]) < 1e-9: o["touch"] = True
        o["last_ts"] = now
def settle():
    for t, o in st["orders"].items():
        if o.get("settled"): continue
        if dt.datetime.fromisoformat(o["close"]) > dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=20): continue
        m = get(f"/markets/{t}").get("market") or (get(f"/historical/markets?ticker={t}").get("markets") or [{}])[0]
        r = m.get("result")
        if r not in ("yes", "no"): continue
        y = 1.0 if r == "yes" else 0.0; p = o["p"]
        o["pnl"] = (y - p - fee(p)) if o["side"] == "buy" else (p - y - fee(p)); o["y"] = y; o["settled"] = True
def summary():
    rows = [o for o in st["orders"].values() if o.get("settled")]
    out = [f"C66 paper maker summary {dt.datetime.now(ET):%Y-%m-%d %H:%M ET} (interim, decides nothing)"]
    for lab, f in [("weekend", lambda o: o["wk"]), ("weekday", lambda o: not o["wk"])]:
        for typ, g in [("above/below", lambda o: not o.get("range")), ("range modal", lambda o: o.get("range"))]:
            X = [o for o in rows if f(o) and g(o)]; F = [o for o in X if o["filled"]]
            days = {}
            for o in F: days.setdefault(o["ev"][-7:], []).append(o["pnl"])
            dm = [sum(v) / len(v) for v in days.values()]
            t = (sum(dm) / len(dm)) / ((sum((x - sum(dm) / len(dm)) ** 2 for x in dm) / (len(dm) - 1)) ** 0.5 / len(dm) ** 0.5) if len(dm) > 2 and len(set(dm)) > 1 else float("nan")
            mean = sum(o["pnl"] for o in F) / len(F) if F else float("nan")
            allm = sum(o["pnl"] for o in X) / len(X) if X else float("nan")
            out.append(f"{lab:8s} {typ:12s} orders {len(X):4d} filled {len(F):4d} mean filled P&L {mean*100:+.2f}c t {t:.2f} | if all filled {allm*100:+.2f}c")
    open(os.path.join(D, "..", "reports", "paper_maker_summary.txt"), "w").write("\n".join(out) + "\n")
    with open(os.path.join(D, "orders.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["ticker", "ev", "side", "p", "mid", "wk", "filled", "touch", "settled", "y", "pnl"])
        for t, o in st["orders"].items(): w.writerow([t, o["ev"], o["side"], o["p"], round(o["mid"], 3), o["wk"], o["filled"], o["touch"], o.get("settled"), o.get("y"), o.get("pnl")])
def once():
    try:
        for s in AB: place(s, "ab")
        for s in RG: place(s, "rg")
        check_fills(); settle(); summary(); save()
    except Exception as e: log(f"loop error {str(e)[:150]}")
os.makedirs(os.path.join(D, "..", "reports"), exist_ok=True)
if "--once" in sys.argv: once(); sys.exit()   # GitHub Actions: one pass per scheduled run (fills are read from trade history, so spacing does not matter)
log("paper maker start")
while True:
    once(); time.sleep(300)
