"""C120-FWD: Kalshi DOGE vs GBM fair value, forward paper scoring (log only: no orders, no keys, public data).

Frozen rule (research_lab claude/c120-preregistration.md, C112/C114/C120):
- Contracts: KXDOGED ("above K at 17:00 ET") and KXDOGE (ranges), events closing 17:00 ET today.
- Model: GBM digital, mu = 0. Spot = last completed 1h close of Coinbase DOGE-USD (the backtest used the Binance perp;
  Binance blocks US runners; spot/perp basis is small). sigma = std of the last 24 hourly log returns, annualized.
- Signal: at a run 2-6 h before close, buy YES if model - ask > 0.10, buy NO if bid - model > 0.10. First signal per contract.
- Paper fill: the quote seen at the next hourly run (45-100 min later): YES at the ask, NO at 1 - bid. Size at the touch logged.
- Hold to settlement. Fee 0.07 p(1-p) per contract (unrounded, as in the backtest; the rounded per-order fee is logged too).
- Decision: 150 filled paper trades. Pass if mean net > 0 with day-clustered t >= 2.
State lives in dogefv/state (state-dogefv branch): state.json, signals.csv, trades.csv, summary.md, log.txt.
Usage: python3 doge_fv.py [--test]   (--test ignores the ET-hour gate and writes to a temp dir)"""
import urllib.request, json, os, sys, time, math, csv, tempfile, datetime as dt
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York"); UA = {"User-Agent": "research-script/1.0"}
KAPI = "https://api.elections.kalshi.com/trade-api/v2"; CB = "https://api.exchange.coinbase.com/products/DOGE-USD/candles"
TEST = "--test" in sys.argv; K = 0.10; SERIES = ["KXDOGED", "KXDOGE"]; TARGET = 150
D = tempfile.mkdtemp() if TEST else os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
os.makedirs(D, exist_ok=True); SP = os.path.join(D, "state.json")
def log(m):
    s = f"{dt.datetime.now(ET):%Y-%m-%d %H:%M:%S} ET {m}"; print(s, flush=True); open(os.path.join(D, "log.txt"), "a").write(s + "\n")
def get(url):
    err = ""
    for k in range(4):
        try: return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read())
        except Exception as e: err = str(e)[:100]; time.sleep(3 + 5 * k)
    log(f"GET fail {url[:90]} {err}"); return None
def px(m, k):
    v = m.get(k + "_dollars", m.get(k))
    if v in (None, ""): return None
    v = float(v); return v / 100 if v > 1 else v
def num(x):
    try: return float(x)
    except (TypeError, ValueError): return None
N = lambda x: 0.5 * math.erfc(-x / math.sqrt(2))
fee = lambda p: 0.07 * p * (1 - p)
fee_order = lambda p, n: math.ceil(0.07 * n * p * (1 - p) * 100) / 100   # Kalshi rounds up per order, n contracts
st = json.load(open(SP)) if os.path.exists(SP) else {"signals": {}, "trades": {}}
def append(name, row, cols):
    p = os.path.join(D, name); new = not os.path.exists(p)
    with open(p, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if new: w.writeheader()
        w.writerow({c: row.get(c) for c in cols})

def spot_sigma(now_utc):
    """Last completed hourly close and trailing-24h annualized vol from Coinbase 1h candles ([t, low, high, open, close, vol])."""
    c = get(f"{CB}?granularity=3600")
    if not c: return None, None
    c = sorted(c, key=lambda r: r[0])
    done = [r for r in c if r[0] + 3600 <= now_utc.timestamp()]            # bar fully closed
    if len(done) < 26: return None, None
    cl = [r[4] for r in done[-25:]]; lr = [math.log(cl[i] / cl[i - 1]) for i in range(1, len(cl))]
    m = sum(lr) / len(lr); sd = math.sqrt(sum((x - m) ** 2 for x in lr) / (len(lr) - 1))
    return cl[-1], sd * math.sqrt(24 * 365)

def strikes(m):
    st_, fl, cp = m.get("strike_type"), num(m.get("floor_strike")), num(m.get("cap_strike"))
    cs = m.get("custom_strike") or {}
    if st_ == "custom" or st_ is None:
        st_ = cs.get("strike_type", st_); fl = num(cs.get("floor_strike")) if fl is None else fl; cp = num(cs.get("cap_strike")) if cp is None else cp
    return st_, fl, cp

def model(S, sig, hrs, st_, fl, cp):
    s = sig * math.sqrt(hrs / (24 * 365))
    up = lambda K_: N(math.log(S / K_) / s - s / 2)
    if st_ == "greater" and fl: return up(fl)
    if st_ == "less" and cp: return 1 - up(cp)
    if st_ == "between" and fl and cp: return up(fl) - up(cp)
    return None

def markets_closing_today(series, now_et):
    d = get(f"{KAPI}/events?series_ticker={series}&status=open&limit=200") or {}
    out = []
    for e in d.get("events", []):
        ms = (get(f"{KAPI}/markets?event_ticker={e['event_ticker']}&limit=500") or {}).get("markets", [])
        for m in ms:
            close = dt.datetime.fromisoformat(m["close_time"].replace("Z", "+00:00")).astimezone(ET)
            if close.date() == now_et.date() and close.hour == 17 and close.minute == 0: out.append((m, close))
    return out

def run():
    now_utc = dt.datetime.now(dt.timezone.utc); now = now_utc.astimezone(ET)
    log(f"run start (test={TEST})")
    quotes = {}
    in_window = TEST or (11 <= now.hour <= 16)
    if in_window:
        S, sig = spot_sigma(now_utc)
        if S is None: log("no Coinbase candles; skipping signals")
        for series in SERIES:
            for m, close in markets_closing_today(series, now):
                b, a = px(m, "yes_bid"), px(m, "yes_ask"); hrs = (close - now).total_seconds() / 3600
                quotes[m["ticker"]] = dict(bid=b, ask=a, bid_size=m.get("yes_bid_size_fp", m.get("yes_bid_size")), ask_size=m.get("yes_ask_size_fp", m.get("yes_ask_size")), hrs=hrs)
                t = m["ticker"]
                if S is None or t in st["signals"] or not (2 <= hrs <= 6) or b is None or a is None or not (0 < b < a < 1): continue
                st_, fl, cp = strikes(m); pm = model(S, sig, hrs, st_, fl, cp)
                if pm is None: continue
                side = "YES" if pm - a > K else ("NO" if b - pm > K else None)
                if not side: continue
                row = dict(ticker=t, series=series, ts=now.isoformat(), close=close.isoformat(), side=side, model=round(pm, 4), bid=b, ask=a,
                           edge=round(pm - a if side == "YES" else b - pm, 4), spot=S, sigma=round(sig, 4), hrs=round(hrs, 2), strike_type=st_, floor=fl, cap=cp)
                st["signals"][t] = row; append("signals.csv", row, list(row)); log(f"SIGNAL {side} {t} model {pm:.3f} bid {b} ask {a}")
    # paper fills: signals from the previous hourly run, filled at the quote seen now
    for t, s in st["signals"].items():
        if t in st["trades"]: continue
        age = (now - dt.datetime.fromisoformat(s["ts"])).total_seconds() / 60
        if age < 45: continue
        q = quotes.get(t)
        if age > 100 or q is None:
            st["trades"][t] = dict(ticker=t, status="no_fill", reason="missed next run" if age > 100 else "no quote", ts_signal=s["ts"]); continue
        b, a = q["bid"], q["ask"]
        if s["side"] == "YES" and a and 0 < a < 1: cost, size = a, q["ask_size"]
        elif s["side"] == "NO" and b and 0 < b < 1: cost, size = 1 - b, q["bid_size"]
        else: st["trades"][t] = dict(ticker=t, status="no_fill", reason="one-sided book", ts_signal=s["ts"]); continue
        st["trades"][t] = dict(ticker=t, series=s["series"], side=s["side"], ts_signal=s["ts"], ts_fill=now.isoformat(), close=s["close"],
                               cost=cost, touch_size=size, status="open"); log(f"FILL {s['side']} {t} at {cost:.2f} (touch size {size})")
    # settlement
    for t, tr in st["trades"].items():
        if tr.get("status") != "open" or dt.datetime.fromisoformat(tr["close"]) > now - dt.timedelta(minutes=30): continue
        m = (get(f"{KAPI}/markets/{t}") or {}).get("market", {})
        if m.get("result") not in ("yes", "no"): continue
        pay = float((m["result"] == "yes") == (tr["side"] == "YES")); c = tr["cost"]
        tr.update(status="settled", result=m["result"], pnl=round(pay - c - fee(c), 4), pnl_rounded_10=round(10 * (pay - c) - fee_order(c, 10), 2))
        append("trades.csv", tr, ["ticker", "series", "side", "ts_signal", "ts_fill", "close", "cost", "touch_size", "result", "pnl", "pnl_rounded_10"])
        log(f"SETTLED {t} {tr['side']} result {m['result']} pnl {tr['pnl']:+.3f}")
    summary(now); json.dump(st, open(SP, "w"), indent=0)

def summary(now):
    s = [t for t in st["trades"].values() if t.get("status") == "settled"]
    by = {}
    for t in s: by.setdefault(t["close"][:10], []).append(t["pnl"])
    n = len(s); m = sum(t["pnl"] for t in s) / n if n else 0.0; tt = float("nan")
    if len(by) > 2:
        tot = sum(len(v) for v in by.values()); r = [sum(v) - m * len(v) for v in by.values()]
        se = math.sqrt(sum(x * x for x in r) * len(by) / (len(by) - 1)) / tot; tt = m / se if se else float("nan")
    nf = sum(1 for t in st["trades"].values() if t.get("status") == "no_fill")
    txt = (f"# C120-FWD Kalshi DOGE vs GBM: forward paper score\nUpdated {now:%Y-%m-%d %H:%M} ET. Log only: no orders.\n\n"
           f"- Signals: {len(st['signals'])}; paper fills settled: {n} of {TARGET}; open: {sum(1 for t in st['trades'].values() if t.get('status') == 'open')}; no fill: {nf}\n"
           f"- Mean net per contract: {m * 100:+.2f}c; day-clustered t: {tt:.2f} over {len(by)} days\n"
           f"- Win rate: {sum(1 for t in s if t['pnl'] > 0) / n:.0%}\n" if n else
           f"# C120-FWD Kalshi DOGE vs GBM: forward paper score\nUpdated {now:%Y-%m-%d %H:%M} ET. Log only: no orders.\n\n- Signals: {len(st['signals'])}; no settled paper trades yet.\n")
    txt += f"\nDecision at {TARGET} settled trades: pass if mean net > 0 and t >= 2. Backtest reference: 2026-01..09 +7.64c t 2.67 (seen data); Oct 2026 clean 7 trades +7.5c.\n"
    open(os.path.join(D, "summary.md"), "w").write(txt)

if __name__ == "__main__":
    run()
    if TEST: print("TEST state dir:", D); print(open(os.path.join(D, "summary.md")).read())
