"""Shadow log of the month-end trade in actual Treasury futures (C91 rule), TY and US. No orders, no account.
Enter at the settle of the 5th-last trading day of the month, exit at the last trading day's settle, in the earliest
quarterly contract whose first notice day is at least 10 calendar days after entry. Cost: two ticks + $5 round trip.
Settles come from Yahoo daily closes for the specific contract (e.g. ZNZ26.CBT); the trading calendar from Alpaca.
Catches up on missed days from price history, so a late or skipped run does not lose a trade. Standard library only.
v1.1 2026-11-07: bar dates now use the exchange time zone per timestamp (zoneinfo). Before, the CURRENT gmtoffset was
applied to every bar, so after the Nov 1 DST change each EDT-era bar (stamped 00:00 New York) landed on the prior day:
the logged Oct 2026 entry was the Oct 27 settle and no bar mapped to Fri Oct 30. Open rows now re-read their entry settle."""
import os, sys, json, csv, urllib.request, urllib.error
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
HERE = os.path.dirname(os.path.abspath(__file__)); LOG = os.path.join(HERE, "fut_log.csv")
ROOTS = {"TY": ("ZN", 1000, 15.625), "US": ("ZB", 1000, 31.25)}   # root: (Yahoo code, $ per point, tick $)
MCODE = {3: "H", 6: "M", 9: "U", 12: "Z"}
kv = dict(l.strip().split("=", 1) for l in open(os.path.expanduser("~/.alpaca_paper")) if "=" in l)
H = {"APCA-API-KEY-ID": kv["APCA_API_KEY_ID"], "APCA-API-SECRET-KEY": kv["APCA_API_SECRET_KEY"]}
def get(url, h=None):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=h or {"User-Agent": "student-research-script/1.0"}), timeout=30).read())
today = date.today()
cal = get(f"https://paper-api.alpaca.markets/v2/calendar?start={today.replace(day=1) - timedelta(days=40)}&end={today + timedelta(days=40)}", H)
days = [date.fromisoformat(c["date"]) for c in cal]
def bizdays_month(y, m): return [d for d in days if d.year == y and d.month == m]
def fnd(y, m):   # first notice day: last business day of the month before the delivery month
    py, pm = (y, m - 1) if m > 1 else (y - 1, 12)
    b = bizdays_month(py, pm)
    if b: return b[-1]
    d = date(y, m, 1) - timedelta(days=1)
    while d.weekday() >= 5: d -= timedelta(days=1)
    return d
def contract(entry):
    y, m = entry.year, entry.month
    for k in range(6):
        mm = ((m - 1 + k) % 12) + 1; yy = y + (m - 1 + k) // 12
        if mm in MCODE and fnd(yy, mm) >= entry + timedelta(days=10): return yy, mm
def closes(sym):
    d = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=6mo&interval=1d")["chart"]["result"][0]
    tz = ZoneInfo(d["meta"].get("exchangeTimezoneName") or "America/New_York"); out = {}
    for t, c in zip(d.get("timestamp", []), d["indicators"]["quote"][0]["close"]):
        if c is None: continue
        lt = datetime.fromtimestamp(t, tz)
        out[lt.date() + timedelta(days=1 if lt.hour >= 17 else 0)] = c   # a stamp at the evening session open belongs to the next day
    return out
rows = list(csv.DictReader(open(LOG))) if os.path.exists(LOG) else []
key = {(r["month"], r["root"]): r for r in rows}
months = {(today.year, today.month)}
p = today.replace(day=1) - timedelta(days=1); months.add((p.year, p.month))   # catch up on last month too
for (y, m) in sorted(months):
    b = bizdays_month(y, m)
    if len(b) < 5: continue
    entry, exit_ = b[-5], b[-1]
    if entry > today: continue
    cy, cm = contract(entry)
    for root, (yc, mult, tick) in ROOTS.items():
        k = (f"{y}-{m:02d}", root)
        r = key.get(k) or {"month": k[0], "root": root, "contract": f"{root}{MCODE[cm]}{cy % 100:02d}", "yahoo": f"{yc}{MCODE[cm]}{cy % 100:02d}.CBT",
                           "entry_date": str(entry), "exit_date": str(exit_), "entry_px": "", "exit_px": "", "pnl_usd": "", "pct_notional": "", "note": ""}
        if r["pnl_usd"]: continue
        try: c = closes(r["yahoo"])
        except Exception as e: r["note"] = f"price fetch failed: {str(e)[:80]}"; key[k] = r; continue
        fix = ""
        if entry in c:   # open rows re-read the entry settle (repairs rows logged before the v1.1 date fix)
            e = round(c[entry], 6)
            if r["entry_px"] and abs(float(r["entry_px"]) - e) > 1e-9: fix = f"; entry corrected {r['entry_px']} -> {e} (v1.1 date fix)"
            r["entry_px"] = e
        if r["entry_px"] and exit_ <= today and exit_ in c:
            a, z = float(r["entry_px"]), c[exit_]; pnl = (z - a) * mult - 2 * tick - 5
            r.update(exit_px=round(z, 6), pnl_usd=round(pnl, 2), pct_notional=round(pnl / (a * mult), 6), note="closed" + fix)
        elif r["entry_px"]: r["note"] = "open" + fix
        else: r["note"] = "waiting for entry settle"
        key[k] = r
out = sorted(key.values(), key=lambda r: (r["month"], r["root"]))
if out:
    with open(LOG, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
done = [r for r in out if r["pnl_usd"]]
summ = [f"Futures shadow log (C91 rule), updated {datetime.now():%Y-%m-%d %H:%M}"]
for root in ROOTS:
    x = [float(r["pnl_usd"]) for r in done if r["root"] == root]
    summ.append(f"{root}: {len(x)} closed months, total ${sum(x):+,.0f}, mean ${sum(x)/len(x):+,.0f}/contract-month" if x else f"{root}: no closed months yet")
summ += [f"  {r['month']} {r['contract']}: {r['note']} entry {r['entry_px']} exit {r['exit_px']} pnl {r['pnl_usd']}" for r in out[-6:]]
open(os.path.join(HERE, "summary.txt"), "w").write("\n".join(summ) + "\n"); print("\n".join(summ))
