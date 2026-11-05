"""Alpaca PAPER portable-alpha fund (C88): 100% SPY core + IEF worth 50% of equity during the month-end window
(hold from close of T-4 to close of T, T = last trading day of the month). Margin version of the futures overlay.
Runs in a SEPARATE paper account (keys in ~/.alpaca_paper2) so it never touches the bond paper fund.
Usage: python3 pa_fund.py [--live]   (default dry run: computes and logs, sends nothing). Standard library only."""
import os, sys, json, csv, urllib.request, urllib.error
from datetime import datetime, date, timedelta
HERE = os.path.dirname(os.path.abspath(__file__)); LIVE = "--live" in sys.argv
CFG = {"core_SPY": 1.00, "overlay_IEF": 0.50, "fin_rate_est": 0.0625}   # fin_rate_est = assumed margin rate, used only for the logged drag estimate
def keys(p):
    p = os.path.expanduser(p)
    return dict(l.strip().split("=", 1) for l in open(p) if "=" in l) if os.path.exists(p) else None
kv = keys("~/.alpaca_paper2"); kv1 = keys("~/.alpaca_paper")
if kv is None:
    if LIVE: raise SystemExit("no ~/.alpaca_paper2 yet: run set_alpaca_keys2.command first")
    if kv1 is None: raise SystemExit("no Alpaca key files found (run on the Mac)")
    kv = kv1; print("(dry run using the bond fund's keys for READ-ONLY market data; equity assumed $100,000)")
BASE = kv.get("APCA_BASE", "")
if BASE.rstrip("/") != "https://paper-api.alpaca.markets": raise SystemExit("refusing: base URL is not the Alpaca PAPER endpoint")
def hdr(k): return {"APCA-API-KEY-ID": k["APCA_API_KEY_ID"], "APCA-API-SECRET-KEY": k["APCA_API_SECRET_KEY"], "Content-Type": "application/json"}
H = hdr(kv)
def api(method, url, body=None, h=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers=h or H, method=method)
    try: return json.loads(urllib.request.urlopen(req, timeout=30).read() or b"null")
    except urllib.error.HTTPError as e: return {"error": e.code, "body": e.read().decode()[:300]}
acct = api("GET", f"{BASE}/v2/account")
if LIVE:
    a1 = api("GET", f"{BASE}/v2/account", h=hdr(kv1)) if kv1 else {}
    if a1.get("id") and a1.get("id") == acct.get("id"): raise SystemExit("refusing: ~/.alpaca_paper2 is the SAME account as the bond paper fund")
eq = float(acct.get("equity", 0)) if os.path.exists(os.path.expanduser("~/.alpaca_paper2")) else 100000.0
today = date.today()
cal = api("GET", f"{BASE}/v2/calendar?start={today - timedelta(days=10)}&end={today + timedelta(days=45)}")
days = [date.fromisoformat(c["date"]) for c in cal] if isinstance(cal, list) else []
early = {date.fromisoformat(c["date"]) for c in cal if c.get("close", "16:00") < "16:00"} if isinstance(cal, list) else set()
if today not in days: print("not a trading day"); sys.exit(0)
if today in early: print("early-close day: market already closed at run time, no orders"); sys.exit(0)
i = days.index(today)
def in_monthend_window(k):   # position held from close(k) to close(k+1) lies inside close(T-4) -> close(T)
    mon = [d for d in days if d.year == days[k].year and d.month == days[k].month]
    T = days.index(mon[-1]); start = T - 4
    if days[start] in early: start -= 1   # entry day closes before the 3:42 pm run, so enter one session earlier
    return start <= k <= T - 1
state = "monthend" if in_monthend_window(i) else "core_only"
def last(sym):
    q = api("GET", f"https://data.alpaca.markets/v2/stocks/{sym}/trades/latest?feed=iex"); return float(q.get("trade", {}).get("p", 0)) or None
px = {s: last(s) for s in ("SPY", "IEF")}
target_usd = {"SPY": CFG["core_SPY"] * eq, "IEF": CFG["overlay_IEF"] * eq if state == "monthend" else 0.0}
pos = api("GET", f"{BASE}/v2/positions"); held = {p["symbol"]: float(p["qty"]) for p in pos} if isinstance(pos, list) and os.path.exists(os.path.expanduser("~/.alpaca_paper2")) else {}
orders = []
for s, usd in target_usd.items():
    if not px[s]: continue
    dq = int(usd / px[s]) - int(held.get(s, 0))
    if dq == 0: continue
    o = {"symbol": s, "qty": str(abs(dq)), "side": "buy" if dq > 0 else "sell", "type": "market", "time_in_force": "cls"}
    res = api("POST", f"{BASE}/v2/orders", o) if LIVE else {"dry_run": True}
    orders.append((s, dq, res.get("id") or res.get("error") or "dry"))
borrowed = max(0.0, sum(target_usd.values()) - eq)
row = dict(ts=datetime.now().isoformat(timespec="seconds"), mode="LIVE-PAPER" if LIVE else "DRY", state=state, equity=round(eq, 2),
           spy_px=px["SPY"], ief_px=px["IEF"], targets=json.dumps({k: round(v, 0) for k, v in target_usd.items()}), orders=json.dumps(orders),
           borrowed_est=round(borrowed, 0), fin_drag_today_est=round(borrowed * CFG["fin_rate_est"] / 252, 2))
p = os.path.join(HERE, "pa_log.csv" if LIVE else "pa_log_dry.csv"); new = not os.path.exists(p)
with open(p, "a", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(row))
    if new: w.writeheader()
    w.writerow(row)
print(json.dumps(row, indent=1))
