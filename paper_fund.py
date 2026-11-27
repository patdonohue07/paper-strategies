"""Alpaca PAPER fund: Sleeve A = bond calendar (C34 auction short, C43 month-end long) in TLT/IEF;
Sleeve B = long VCIT with an IEF hedge timed by the same calendar (C79-3). Paper endpoint only. Standard library only.
Usage: python3 paper_fund.py [--live]   (default is dry run: computes and logs orders, sends nothing)."""
import os, sys, json, csv, math, urllib.request, urllib.parse, urllib.error
from datetime import datetime, date, timedelta
HERE = os.path.dirname(os.path.abspath(__file__)); LIVE = "--live" in sys.argv
kv = dict(l.strip().split("=", 1) for l in open(os.path.expanduser("~/.alpaca_paper")) if "=" in l)
BASE = kv.get("APCA_BASE", "")
if BASE.rstrip("/") != "https://paper-api.alpaca.markets": raise SystemExit("refusing: base URL is not the Alpaca PAPER endpoint")
H = {"APCA-API-KEY-ID": kv["APCA_API_KEY_ID"], "APCA-API-SECRET-KEY": kv["APCA_API_SECRET_KEY"], "Content-Type": "application/json"}
CFG = {"A_gross": 0.20, "B_long": 0.30, "auction_mult": 1.0, "monthend_mult": 0.75, "auction_trade": False}   # v2 2026-11-04: auction leg tracked only (Pat); month-end sleeve 20% IEF (Pat)
def api(method, url, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, headers=H, method=method)
    try: return json.loads(urllib.request.urlopen(req, timeout=30).read() or b"null")
    except urllib.error.HTTPError as e: return {"error": e.code, "body": e.read().decode()[:300]}
def log(row):
    p = os.path.join(HERE, "fund_log.csv"); new = not os.path.exists(p)
    with open(p, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row)); 
        if new: w.writeheader()
        w.writerow(row)
today = date.today()
cal = api("GET", f"{BASE}/v2/calendar?start={today - timedelta(days=40)}&end={today + timedelta(days=60)}")
days = [date.fromisoformat(c["date"]) for c in cal] if isinstance(cal, list) else []
early = {date.fromisoformat(c["date"]) for c in cal if c.get("close", "16:00") < "16:00"} if isinstance(cal, list) else set()   # v2.1: half days
if today not in days: print("not a trading day"); sys.exit(0)
if today in early: print("early-close day: market already closed at run time, no orders"); sys.exit(0)
i = days.index(today)
# upcoming and recent long-end nominal auctions (10y/20y/30y) from TreasuryDirect
def td(path):
    try: return json.loads(urllib.request.urlopen(urllib.request.Request("https://www.treasurydirect.gov/TA_WS/securities/" + path, headers={"User-Agent": "LehighStudentResearch"}), timeout=30).read())
    except Exception as e: return []
sec = td("upcoming?format=json") + td(f"search?format=json&startDate={(today - timedelta(days=20)).strftime('%m/%d/%Y')}&endDate={(today + timedelta(days=30)).strftime('%m/%d/%Y')}")
auctions = set()
for s in sec:
    t = (s.get("securityTerm") or "") + " " + (s.get("type") or s.get("securityType") or "")
    if "Yes" in (s.get("inflationIndexSecurity"), s.get("inflationProtected"), s.get("floatingRate")) or "FRN" in t: continue
    ad = s.get("auctionDate") or s.get("competitiveAuctionCloseDate")
    if any(k in t for k in ("10-Year", "20-Year", "30-Year", "9-Year", "19-Year", "29-Year")) and ad:
        auctions.add(date.fromisoformat(ad[:10]))
# window state for the position to HOLD from today's close to tomorrow's close
def in_auction_window(k):   # holding period close(k) -> close(k+1) lies inside close(A-6) -> close(A-1)
    for a in auctions:
        if a in days:
            j = days.index(a)
            st = j - 7 if days[j - 6] in early else j - 6   # v2.1: enter a session earlier if the entry day is a half day
            if st <= k <= j - 2: return True
    return False
def in_monthend_window(k):  # close(T-4) -> close(T), T = last trading day of month
    mon = [d for d in days if d.year == days[k].year and d.month == days[k].month]
    if not mon or mon[-1] not in days: return False
    T = days.index(mon[-1]); st = T - 5 if days[T - 4] in early else T - 4   # v2.1: same half-day shift
    return st <= k <= T - 1
A_state = "auction" if in_auction_window(i) else ("monthend" if in_monthend_window(i) else "flat")
acct = api("GET", f"{BASE}/v2/account"); eq = float(acct.get("equity", 0))
def last(sym):
    q = api("GET", f"https://data.alpaca.markets/v2/stocks/{sym}/trades/latest?feed=iex"); return float(q.get("trade", {}).get("p", 0)) or None
px = {s: last(s) for s in ("TLT", "IEF", "VCIT")}
# hedge beta of VCIT on IEF, trailing 120 trading days of daily bars (dividend-adjusted), excess over BIL ignored at this horizon
def bars(sym):
    q = api("GET", f"https://data.alpaca.markets/v2/stocks/{sym}/bars?timeframe=1Day&limit=200&adjustment=all&feed=sip&start={(today - timedelta(days=300)).isoformat()}&end={(today - timedelta(days=1)).isoformat()}")
    return [b["c"] for b in q.get("bars", [])]
v, f = bars("VCIT"), bars("IEF"); n = min(len(v), len(f)) - 1
rv = [v[-k] / v[-k - 1] - 1 for k in range(1, min(n, 120) + 1)]; rf = [f[-k] / f[-k - 1] - 1 for k in range(1, min(n, 120) + 1)]
mv, mf = sum(rv) / len(rv), sum(rf) / len(rf); beta = sum((a - mv) * (b - mf) for a, b in zip(rv, rf)) / sum((b - mf) ** 2 for b in rf)
mult = {"auction": CFG["auction_mult"], "monthend": CFG["monthend_mult"], "flat": 1.0}[A_state]
target_usd = {"TLT": 0.0, "IEF": 0.0, "VCIT": CFG["B_long"] * eq}
track = {}
if A_state == "auction":
    track = {"TLT": -CFG["A_gross"] / 2 * eq, "IEF": -CFG["A_gross"] / 2 * eq, "hedge_extra_IEF": -0.25}   # would-be frozen auction trade, logged only
    if CFG["auction_trade"]: target_usd["TLT"] += track["TLT"]; target_usd["IEF"] += track["IEF"]
if A_state == "monthend": target_usd["IEF"] += CFG["A_gross"] * eq
target_usd["IEF"] -= beta * mult * CFG["B_long"] * eq
pos = api("GET", f"{BASE}/v2/positions"); held = {p["symbol"]: float(p["qty"]) for p in pos} if isinstance(pos, list) else {}
orders = []
for s, usd in target_usd.items():
    if not px[s]: continue
    tgt = int(usd / px[s]); dq = tgt - int(held.get(s, 0))
    if dq == 0: continue
    o = {"symbol": s, "qty": str(abs(dq)), "side": "buy" if dq > 0 else "sell", "type": "market", "time_in_force": "day"}   # v2.2: Alpaca paper let MOC (cls) orders expire on 2026-11-05
    res = api("POST", f"{BASE}/v2/orders", o) if LIVE else {"dry_run": True}
    orders.append((s, dq, res.get("id") or res.get("error") or "dry"))
row = dict(ts=datetime.now().isoformat(timespec="seconds"), mode="LIVE-PAPER" if LIVE else "DRY", state=A_state, equity=round(eq, 2), beta_vcit_ief=round(beta, 3),
           tlt_px=px["TLT"], ief_px=px["IEF"], vcit_px=px["VCIT"], targets=json.dumps({k: round(v_, 0) for k, v_ in target_usd.items()}), orders=json.dumps(orders),
           auctions_seen=",".join(sorted(str(a) for a in auctions)), auction_tracked_only=json.dumps(track))
log(row); print(json.dumps(row, indent=1))
