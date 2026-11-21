"""Hourly forward logger of Hyperliquid wallet positions (free public API, read-only, no account).
Each run: coin contexts (mark, OI, funding) + positions of the largest wallets (entry px, liquidation px, leverage),
reduced to per-coin trapped-long measures. Companion to the Binance forward test. Python 3.9, standard library only."""
import json, os, sys, csv, gzip, time, urllib.request
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)
API = "https://api.hyperliquid.xyz/info"; LB = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
NWAL = int(os.environ.get("NWAL", "2000"))
def log(*a):
    s = datetime.now().strftime("%Y-%m-%d %H:%M:%S ") + " ".join(str(x) for x in a); print(s, flush=True)
    open("logger_log.txt", "a").write(s + "\n")
def post(body, tries=5):
    for i in range(tries):
        try:
            req = urllib.request.Request(API, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r: return json.loads(r.read())
        except Exception as e:
            if "429" in str(e): time.sleep(5 * (i + 1))
            else: time.sleep(2 * (i + 1))
    return None
def wallets():
    p = "wallets.json"
    if os.path.exists(p) and time.time() - os.path.getmtime(p) < 86400: return json.load(open(p))
    try:
        with urllib.request.urlopen(urllib.request.Request(LB, headers={"user-agent": "research"}), timeout=120) as r: d = json.loads(r.read())
        rows = d.get("leaderboardRows", [])
        rows.sort(key=lambda x: -float(x.get("accountValue") or 0))
        w = [r["ethAddress"] for r in rows[:NWAL]]
        json.dump(w, open(p, "w")); log("leaderboard: %d accounts, kept top %d by account value" % (len(rows), len(w))); return w
    except Exception as e:
        log("leaderboard failed", repr(e)[:200]); return json.load(open(p)) if os.path.exists(p) else []
def run_once():
    t = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0); ts = t.strftime("%Y-%m-%d %H:00")
    meta = post({"type": "metaAndAssetCtxs"})
    if not meta: log("metaAndAssetCtxs failed"); return
    names = [u["name"] for u in meta[0]["universe"]]; ctx = {n: c for n, c in zip(names, meta[1])}
    W = wallets(); t0 = time.time()
    with ThreadPoolExecutor(6) as ex: states = list(ex.map(lambda a: (a, post({"type": "clearinghouseState", "user": a})), W))
    raw = []
    for a, s in states:
        if not s: continue
        for ap in s.get("assetPositions", []):
            p = ap.get("position", {})
            try: raw.append((a, p["coin"], float(p["szi"]), float(p.get("entryPx") or 0), float(p["liquidationPx"]) if p.get("liquidationPx") else None, (p.get("leverage") or {}).get("value"), float(p.get("positionValue") or 0)))
            except Exception: pass
    os.makedirs("raw", exist_ok=True)
    with gzip.open("raw/positions_%s.csv.gz" % t.strftime("%Y%m%d"), "at", newline="") as f:
        w = csv.writer(f)
        for r in raw: w.writerow((ts,) + r)
    agg = {}
    for a, c, sz, e, lq, lev, pv in raw:
        g = agg.setdefault(c, {"L": [], "S": 0.0})
        if sz > 0: g["L"].append((pv, e, lq))
        elif sz < 0: g["S"] += pv
    new = not os.path.exists("coin_hourly.csv")
    with open("coin_hourly.csv", "a", newline="") as f:
        w = csv.writer(f)
        if new: w.writerow(["hour_utc", "coin", "mark", "oi_coins", "funding", "tracked_long_usd", "tracked_short_usd", "n_long", "uw_share", "deep_uw_share", "liq_within_10pct_share", "liq_within_20pct_share", "top10_long_share"])
        for c, x in ctx.items():
            m = float(x.get("markPx") or 0); g = agg.get(c, {"L": [], "S": 0.0}); L = sum(v for v, e, l in g["L"])
            def sh(cond): return round(sum(v for v, e, l in g["L"] if cond(e, l)) / L, 4) if L else ""
            top = round(sum(sorted((v for v, e, l in g["L"]), reverse=True)[:10]) / L, 4) if L else ""
            w.writerow([ts, c, m, x.get("openInterest"), x.get("funding"), round(L, 2), round(g["S"], 2), len(g["L"]),
                        sh(lambda e, l: e > m), sh(lambda e, l: e >= 1.25 * m), sh(lambda e, l: l is not None and l >= 0.9 * m), sh(lambda e, l: l is not None and l >= 0.8 * m), top])
    log("logged %s: %d coins, %d wallets queried in %.0fs, %d positions" % (ts, len(ctx), len(W), time.time() - t0, len(raw)))
if __name__ == "__main__":
    if "--once" in sys.argv: run_once(); sys.exit()
    while True:   # loop mode: run at about 5 minutes past each hour
        run_once()
        now = time.time(); time.sleep(3600 - (now % 3600) + 300)
