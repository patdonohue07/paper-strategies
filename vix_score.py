"""C100 forward scoring of the VIX-augmented SPY variance forecast (no trading).
Each weekday morning: (1) score earlier forecasts whose day has closed, (2) forecast today's squared SPY close-to-close
log return two ways and log both before the open. Baseline: log-HAR (yesterday, 5-day, 22-day mean squared returns).
Augmented: the same plus log of yesterday's VIX-implied daily variance. OLS on log(r^2 + eps), trailing 1,260 days,
refit daily, with a smearing correction. Score: QLIKE = log(v) + r^2 / v (lower is better). Standard library only."""
import os, json, csv, math, urllib.request
from datetime import date, datetime, timedelta
HERE = os.path.dirname(os.path.abspath(__file__)); F = os.path.join(HERE, "vix_forecasts.csv"); EPS = 1e-8; WIN = 1260
kv = dict(l.strip().split("=", 1) for l in open(os.path.expanduser("~/.alpaca_paper")) if "=" in l)
H = {"APCA-API-KEY-ID": kv["APCA_API_KEY_ID"], "APCA-API-SECRET-KEY": kv["APCA_API_SECRET_KEY"]}
def get(u, h=None, raw=False):
    r = urllib.request.urlopen(urllib.request.Request(u, headers=h or {"User-Agent": "student-research-script/1.0"}), timeout=60).read()
    return r.decode() if raw else json.loads(r)
today = date.today()
bars, tok = [], None
while True:
    u = f"https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe=1Day&start=2013-01-01&end={(today - timedelta(days=1)).isoformat()}&adjustment=all&feed=sip&limit=10000" + (f"&page_token={tok}" if tok else "")
    d = get(u, H); bars += [(x["t"][:10], x["c"]) for x in d.get("bars", [])]; tok = d.get("next_page_token")
    if not tok: break
spy = {date.fromisoformat(a): c for a, c in bars}
vix = {}
for line in get("https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv", raw=True).splitlines()[1:]:
    p = line.split(",")
    try: vix[datetime.strptime(p[0], "%m/%d/%Y").date()] = float(p[4])
    except Exception: pass
ds = sorted(d for d in spy if d < today and d in vix)
r2 = {}
for a, b in zip(ds[:-1], ds[1:]): r2[b] = math.log(spy[b] / spy[a]) ** 2
dd = [d for d in ds if d in r2]
def feats(i, aug):   # features known at the close of dd[i], used to forecast dd[i+1] (or today)
    x1 = r2[dd[i]]; x5 = sum(r2[dd[j]] for j in range(i - 4, i + 1)) / 5; x22 = sum(r2[dd[j]] for j in range(i - 21, i + 1)) / 22
    f = [1.0, math.log(x1 + EPS), math.log(x5 + EPS), math.log(x22 + EPS)]
    if aug: f.append(math.log((vix[dd[i]] / 100) ** 2 / 252))
    return f
def ols(X, y):
    k = len(X[0]); A = [[sum(X[r][i] * X[r][j] for r in range(len(X))) for j in range(k)] for i in range(k)]; b = [sum(X[r][i] * y[r] for r in range(len(X))) for i in range(k)]
    for i in range(k):   # Gauss-Jordan
        p = max(range(i, k), key=lambda r: abs(A[r][i])); A[i], A[p] = A[p], A[i]; b[i], b[p] = b[p], b[i]
        for r in range(k):
            if r != i:
                m = A[r][i] / A[i][i]; A[r] = [A[r][c] - m * A[i][c] for c in range(k)]; b[r] -= m * b[i]
    return [b[i] / A[i][i] for i in range(k)]
def forecast(aug):
    n = len(dd) - 1; idx = list(range(max(22, n - WIN), n))   # train pairs (features at i, target at i+1)
    X = [feats(i, aug) for i in idx]; y = [math.log(r2[dd[i + 1]] + EPS) for i in idx]; b = ols(X, y)
    res = [yy - sum(bb * xx for bb, xx in zip(b, x)) for x, yy in zip(X, y)]; smear = sum(math.exp(e) for e in res) / len(res)
    return math.exp(sum(bb * xx for bb, xx in zip(b, feats(n, aug)))) * smear
rows = list(csv.DictReader(open(F))) if os.path.exists(F) else []
for r in rows:   # score
    d = date.fromisoformat(r["date"])
    if not r["realized_r2"] and d in r2:
        x = r2[d]; r["realized_r2"] = f"{x:.10f}"
        for k in ("base", "aug"): r[f"qlike_{k}"] = f"{math.log(float(r['f_' + k])) + x / float(r['f_' + k]):.6f}"
        r["improvement"] = f"{float(r['qlike_base']) - float(r['qlike_aug']):.6f}"
cal = get(f"https://paper-api.alpaca.markets/v2/calendar?start={today}&end={today}", H)
if cal and cal[0]["date"] == str(today) and not any(r["date"] == str(today) for r in rows):
    rows.append(dict(date=str(today), made_at=datetime.now().isoformat(timespec="seconds"), vix_prev=vix[dd[-1]], f_base=f"{forecast(False):.10f}", f_aug=f"{forecast(True):.10f}",
                     realized_r2="", qlike_base="", qlike_aug="", improvement=""))
cols = ["date", "made_at", "vix_prev", "f_base", "f_aug", "realized_r2", "qlike_base", "qlike_aug", "improvement"]
with open(F, "w", newline="") as f: w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
sc = [float(r["improvement"]) for r in rows if r["improvement"]]
s = f"C100 VIX forecast forward scoring, {datetime.now():%Y-%m-%d %H:%M}: {len(sc)} scored days"
if sc: s += f", mean QLIKE improvement {sum(sc)/len(sc):+.4f} (positive = VIX helps), VIX better on {sum(x > 0 for x in sc)/len(sc):.0%} of days; decision at 250 days"
open(os.path.join(HERE, "summary.txt"), "w").write(s + "\n"); print(s); print(rows[-1] if rows else "")
