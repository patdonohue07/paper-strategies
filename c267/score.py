"""C267 weekly scorer: settle logged flags, score each (series, side) rule month by month, and judge it against the best-of-N random gate
(C266): N = rules with >= 10 settled flags; the null = the same contracts traded on a random side at the same logged quotes; a rule is
ACTIVE only if its trailing-3-month t-stat beats the 95th percentile of the best t among N random rules. Rules whose trailing 3 months
are negative are RETIRED. Standard library only. Writes <state>/results.json and <state>/scoreboard.md.
Usage: python3 score.py <state_dir>"""
import gzip, glob, json, math, os, random, sys, time, urllib.request
from datetime import datetime, timezone
API = "https://api.elections.kalshi.com/trade-api/v2"; UA = {"User-Agent": "research-client/1.0"}
STATE = sys.argv[1] if len(sys.argv) > 1 else "state"


def get(u):
    for k in range(3):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30).read())
        except Exception:  # noqa: BLE001
            time.sleep(1 + k)
    return None


def fee(p, mult):
    return 0.07 * p * (1 - p) * mult


def tstat(x):
    n = len(x)
    if n < 3:
        return 0.0
    m = sum(x) / n; v = sum((a - m) ** 2 for a in x) / (n - 1)
    return m / math.sqrt(v / n) if v > 0 else 0.0


def main():
    now = time.time(); rp = os.path.join(STATE, "results.json"); res = json.load(open(rp)) if os.path.exists(rp) else {}
    F = []
    for p in sorted(glob.glob(os.path.join(STATE, "scans", "*.json.gz"))):
        D = json.load(gzip.open(p, "rt")); day = os.path.basename(p)[:10]
        for r in D["rows"]:
            if r.get("flag") in ("BUY", "SELL") and r.get("ob_bid") is not None and r.get("ob_ask") is not None:
                F.append(dict(r, scan=day))
    for r in F:
        if r["ticker"] not in res and r.get("close") and datetime.fromisoformat(r["close"].replace("Z", "+00:00")).timestamp() < now:
            m = (get(f"{API}/markets/{r['ticker']}") or {}).get("market", {})
            if m.get("result") in ("yes", "no"):
                res[r["ticker"]] = m["result"]
            time.sleep(0.05)
    json.dump(res, open(rp, "w"))
    S = []
    for r in F:
        y = res.get(r["ticker"])
        if y not in ("yes", "no"):
            continue
        y = 1.0 if y == "yes" else 0.0; b, a, mult = float(r["ob_bid"]), float(r["ob_ask"]), float(r.get("mult") or 1)
        pnl_buy, pnl_sell = y - a - fee(a, mult), b - y - fee(b, mult)
        S.append(dict(rule=f"{r['series']}|{r['flag']}", month=r["scan"][:7], scan=r["scan"], pnl=pnl_buy if r["flag"] == "BUY" else pnl_sell, alt=(pnl_buy, pnl_sell)))
    rules = {}
    for s in S:
        rules.setdefault(s["rule"], []).append(s)
    cut = datetime.fromtimestamp(now - 92 * 86400, timezone.utc).strftime("%Y-%m-%d")
    elig = {k: v for k, v in rules.items() if len(v) >= 10}; Nr = max(1, len(elig))
    rnd = random.Random(267); best = []
    for _ in range(1000):
        mx = -1e9
        for k, v in elig.items():
            x = [s["alt"][rnd.randrange(2)] for s in v if s["scan"] >= cut] or [0.0]
            mx = max(mx, tstat(x))
        best.append(mx)
    best.sort(); gate = best[int(0.95 * len(best))] if best else float("inf")
    lines = [f"# C267 niche-market scoreboard ({datetime.now(timezone.utc):%Y-%m-%d})", "",
             f"Settled flags: {len(S)}; rules with >= 10 settled flags: {len(elig)}; best-of-{Nr} random gate (trailing 3 months, 95th pct t): {gate:.2f}", "",
             "| rule (series, side) | settled | mean P&L | t | trailing-3m n | trailing-3m mean | trailing-3m t | status | by month (n, mean) |", "|---|---|---|---|---|---|---|---|---|"]
    for k, v in sorted(rules.items(), key=lambda kv: -len(kv[1])):
        x = [s["pnl"] for s in v]; tr = [s["pnl"] for s in v if s["scan"] >= cut]; tt = tstat(tr)
        status = "ACTIVE" if k in elig and tt > gate and sum(tr) > 0 else "RETIRED" if tr and sum(tr) < 0 else "watch"
        bym = {}
        for s in v:
            bym.setdefault(s["month"], []).append(s["pnl"])
        lines.append(f"| {k} | {len(v)} | {sum(x) / len(x):+.3f} | {tstat(x):.2f} | {len(tr)} | {(sum(tr) / len(tr)) if tr else 0:+.3f} | {tt:.2f} | {status} | "
                     + ", ".join(f"{m}: {len(p)}, {sum(p) / len(p):+.2f}" for m, p in sorted(bym.items())) + " |")
    open(os.path.join(STATE, "scoreboard.md"), "w").write("\n".join(lines) + "\n"); print("\n".join(lines[:8]), flush=True)


if __name__ == "__main__":
    main()
