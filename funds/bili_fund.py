"""C90 BILI pre-open ADR parity forward paper test. Shares the bond fund's Alpaca PAPER account (~/.alpaca_paper); trades only BILI, fixed $100k notional, flat overnight.
Usage: python3 bili_fund.py entry|exit [--live]   (default dry run: computes and logs, sends nothing). Standard library only."""
import os, sys, json, csv, math, statistics, urllib.request, urllib.error
from datetime import datetime, date, timedelta, timezone
HERE = os.path.dirname(os.path.abspath(__file__)); LIVE = "--live" in sys.argv
MODE = "exit" if "exit" in sys.argv else "entry"
CFG = {"sym": "BILI", "hk": "9626.HK", "fx": "HKD=X", "shares_per_adr": 1.0, "thresh": 0.01, "win": 252, "min_obs": 126, "notional": 100000.0}
UA = {"User-Agent": "student-research-script/1.0"}
def keys(p):
    p = os.path.expanduser(p); return dict(l.strip().split("=", 1) for l in open(p) if "=" in l) if os.path.exists(p) else None
kv = keys("~/.alpaca_paper")
if kv is None: raise SystemExit("no ~/.alpaca_paper keys found")
BASE = kv.get("APCA_BASE", "")
if BASE.rstrip("/") != "https://paper-api.alpaca.markets": raise SystemExit("refusing: base URL is not the Alpaca PAPER endpoint")
hdr = lambda k: {"APCA-API-KEY-ID": k["APCA_API_KEY_ID"], "APCA-API-SECRET-KEY": k["APCA_API_SECRET_KEY"], "Content-Type": "application/json"}
H = hdr(kv)
def api(method, url, body=None, h=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers=h or H, method=method)
    try: return json.loads(urllib.request.urlopen(req, timeout=30).read() or b"null")
    except urllib.error.HTTPError as e: return {"error": e.code, "body": e.read().decode()[:300]}
acct = api("GET", f"{BASE}/v2/account")
eq = float(acct.get("equity", 0))
def log(name, row):
    p = os.path.join(HERE, name if LIVE else "dry_" + name); new = not os.path.exists(p)
    with open(p, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if new: w.writeheader()
        w.writerow(row)
today = date.today()
cal = api("GET", f"{BASE}/v2/calendar?start={today - timedelta(days=10)}&end={today}")
if not (isinstance(cal, list) and cal and date.fromisoformat(cal[-1]["date"]) == today): print("not a US trading day"); sys.exit(0)
if MODE == "exit":
    pos = api("GET", f"{BASE}/v2/positions/{CFG['sym']}")
    q = float(pos.get("qty", 0)) if isinstance(pos, dict) and "qty" in pos else 0.0
    res = {}
    if q:
        o = {"symbol": CFG["sym"], "qty": str(abs(int(q))), "side": "sell" if q > 0 else "buy", "type": "market", "time_in_force": "day"}   # v2.2: Alpaca paper let MOC (cls) orders expire on 2026-11-05
        res = api("POST", f"{BASE}/v2/orders", o) if LIVE else {"dry_run": True}
    log("bili_exits.csv", dict(ts=datetime.now().isoformat(timespec="seconds"), mode="LIVE-PAPER" if LIVE else "DRY", qty_held=q, order=res.get("id") or res.get("error") or ("dry" if q else "none"),
                                entry_px=pos.get("avg_entry_price") if isinstance(pos, dict) else None))
    print("exit", q, res.get("id") or res.get("error") or ""); sys.exit(0)
# ---- entry: build the signal ----
def yahoo(sym):
    u = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=2y&interval=1d"
    d = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30).read())["chart"]["result"][0]
    tz = d["meta"].get("exchangeTimezoneName"); off = d["meta"].get("gmtoffset", 0)
    out = {}
    for t, c in zip(d["timestamp"], d["indicators"]["quote"][0]["close"]):
        if c is not None: out[datetime.fromtimestamp(t + off, timezone.utc).date()] = float(c)
    m = d["meta"]; rp, rt = m.get("regularMarketPrice"), m.get("regularMarketTime")   # latest close when the last daily bar is still blank
    if rp and rt:
        dd = datetime.fromtimestamp(rt + off, timezone.utc).date()
        if dd not in out: out[dd] = float(rp)
    return out
err = ""
try: hk, fx = yahoo(CFG["hk"]), yahoo(CFG["fx"])
except Exception as e: hk, fx, err = {}, {}, f"yahoo: {str(e)[:120]}"
b = api("GET", f"https://data.alpaca.markets/v2/stocks/{CFG['sym']}/bars?timeframe=1Day&start={(today - timedelta(days=500)).isoformat()}&end={(today - timedelta(days=1)).isoformat()}&adjustment=raw&feed=sip&limit=1000")
us = {date.fromisoformat(x["t"][:10]): (x["o"], x["c"]) for x in b.get("bars", [])} if isinstance(b, dict) else {}
fxd = sorted(fx)
def fx_before(d):   # last completed FX close strictly before date d
    prior = [x for x in fxd if x < d]; return fx[prior[-1]] if prior else None
def parity(d):
    if d not in hk: return None
    f = fx_before(d); return hk[d] * CFG["shares_per_adr"] / f if f else None
prem = [math.log(us[d][0] / parity(d)) for d in sorted(us) if parity(d)]
prem = prem[-CFG["win"]:]
p_today = parity(today); prior_close = us[max(us)][1] if us else None
sig, fc, gap, reason = 0, None, None, ""
if err: reason = err
elif p_today is None: reason = "no 9626.HK close dated today (HK holiday or data lag)"
elif len(prem) < CFG["min_obs"]: reason = f"only {len(prem)} premium observations"
else:
    fc = p_today * math.exp(statistics.median(prem)); gap = fc / prior_close - 1
    sig = 1 if gap > CFG["thresh"] else (-1 if gap < -CFG["thresh"] else 0)
order, note = None, ""
if sig:
    px = prior_close; qty = int(CFG["notional"] / px)
    if sig < 0:
        a = api("GET", f"{BASE}/v2/assets/{CFG['sym']}")
        if not (a.get("shortable") and a.get("easy_to_borrow")): note = "short skipped: not shortable/easy to borrow"; qty = 0
    if qty:
        o = {"symbol": CFG["sym"], "qty": str(qty), "side": "buy" if sig > 0 else "sell", "type": "market", "time_in_force": "day"}   # sent before the open, fills at the open (paper does not reliably fill opg)
        r = api("POST", f"{BASE}/v2/orders", o) if LIVE else {"dry_run": True}
        order = r.get("id") or r.get("error") or "dry"; note = note or f"{'long' if sig > 0 else 'short'} {qty}"
md = [d for d in sorted(us) if parity(d)]
chk = f"{md[-1]}: parity {parity(md[-1]):.3f} vs US open {us[md[-1]][0]}" if md else ""
row = dict(ts=datetime.now().isoformat(timespec="seconds"), mode="LIVE-PAPER" if LIVE else "DRY", equity=round(eq, 2), hk_close=hk.get(today), fx_prior=fx_before(today) if fx else None,
           parity=round(p_today, 4) if p_today else None, median_prem=round(statistics.median(prem), 5) if prem else None, n_prem=len(prem),
           forecast_open=round(fc, 4) if fc else None, prior_close=prior_close, gap=round(gap, 5) if gap is not None else None, signal=sig, order=order, note=note or reason, last_match=chk, hk_last=str(max(hk)) if hk else None)
log("bili_entries.csv", row); print(json.dumps(row, indent=1))
