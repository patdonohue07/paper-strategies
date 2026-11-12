"""C226 paper maker on Kalshi hourly crypto ladders (KXSOLD gated; KXBTCD/KXETHD for comparison). Paper only: public data, no orders.
Replays each settled hourly event from public 1-minute candles (quotes) and public trade prints (fills). Rules: see README.md.
Usage: python3 sol_maker.py                      forward mode (state in ./state), events closing from START to now-10 min
       python3 sol_maker.py --replay A B SERIES   replay events closing A..B (YYYY-MM-DD, ET) into ./replay_<SERIES>/
Stdlib only."""
import csv, json, math, os, sys, time, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York"); API = "https://api.elections.kalshi.com/trade-api/v2"; UA = {"User-Agent": "research-client/1.0"}
HERE = os.path.dirname(os.path.abspath(__file__))
START = datetime(2026, 11, 13, 0, 0, tzinfo=ET); END = datetime(2026, 12, 11, 0, 0, tzinfo=ET)
SERIES = ["KXSOLD", "KXBTCD", "KXETHD"]; GATED = "KXSOLD"
SIZE, CAP, M_FIRST, M_LAST = 10, 50, 50, 5
MON = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def get(path):
    for k in range(5):
        try:
            time.sleep(0.1)
            return json.loads(urllib.request.urlopen(urllib.request.Request(API + path, headers=UA), timeout=30).read())
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return {}
            time.sleep(2 + 4 * k)
        except Exception:  # noqa: BLE001
            time.sleep(2 + 4 * k)
    raise RuntimeError(f"GET failed {path[:90]}")


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def mfee(p, n):
    return math.ceil(round(0.0175 * p * (1 - p) * n * 100, 9)) / 100


def ticker(series, close_et):
    return f"{series}-{close_et.year % 100:02d}{MON[close_et.month - 1]}{close_et.day:02d}{close_et.hour:02d}"


def quotes(tickers, ce):
    """ticker -> {T: (bid, ask)} from 1-minute candles ending close-60 min .. close."""
    out = {}
    for i in range(0, len(tickers), 100):
        d = get(f"/markets/candlesticks?market_tickers={','.join(tickers[i:i + 100])}&start_ts={ce - 3720}&end_ts={ce}&period_interval=1")
        for m in d.get("markets", []):
            q = {}
            for c in m.get("candlesticks", []):
                b, a = f(c.get("yes_bid", {}).get("close_dollars")), f(c.get("yes_ask", {}).get("close_dollars"))
                if b is not None and a is not None:
                    q[int(c["end_period_ts"])] = (b, a)
            out[m["market_ticker"]] = q
    return out


def trades(tk, lo, hi):
    out, cur = [], ""
    while True:
        d = get(f"/markets/trades?ticker={tk}&min_ts={lo}&max_ts={hi}&limit=1000" + (f"&cursor={cur}" if cur else ""))
        for x in d.get("trades", []):
            s = x["created_time"].replace("Z", "").split("+")[0]; base, _, frac = s.partition(".")
            t = datetime.strptime(base, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp() + (float("0." + frac) if frac else 0.0)
            out.append((t, f(x.get("yes_price_dollars")), f(x.get("count_fp")) or 0.0, x.get("taker_side")))
        cur = d.get("cursor")
        if not cur or not d.get("trades"):
            return sorted(out)


def simulate(series, close_et):
    """Returns (event_row, fills) or None if not yet settled / not listed."""
    ev = ticker(series, close_et); ce = int(close_et.timestamp())
    ms = get(f"/markets?event_ticker={ev}&limit=1000").get("markets", [])
    if not ms:
        return {"event": ev, "series": series, "status": "unlisted"}, []
    res = {m["ticker"]: m.get("result") for m in ms}
    if any(r not in ("yes", "no") for r in res.values()):
        return None
    Q = quotes(sorted(res), ce); fills = []; inv = {}; cash = {}; fees = {}
    for tk, q in Q.items():
        mins = [T for T in range(ce - 60 * M_FIRST, ce - 60 * M_LAST + 1, 60)
                if (T - 60) in q and q[T - 60][0] > 0 and q[T - 60][1] < 1 and q[T - 60][1] - q[T - 60][0] >= 0.0199
                and 0.10 <= sum(q[T - 60]) / 2 <= 0.90]
        if not mins:
            continue
        tr = trades(tk, mins[0] - 60, mins[-1] + 1); y = 1.0 if res[tk] == "yes" else 0.0; n = 0.0
        for T in mins:
            b, a = q[T - 60]; imp = a - b >= 0.0299; qb, qa = (round(b + 0.01, 2), round(a - 0.01, 2)) if imp else (b, a)
            left_b, left_a = SIZE, SIZE
            for t, p, cnt, side in tr:
                if not (T - 60 < t <= T) or p is None:
                    continue
                if side == "no" and left_b > 0 and n < CAP and (p <= qb + 1e-9 if imp else p < qb - 1e-9):
                    k = min(cnt, left_b, CAP - n); left_b -= k; n += k; px, sgn = qb, 1
                elif side == "yes" and left_a > 0 and n > -CAP and (p >= qa - 1e-9 if imp else p > qa + 1e-9):
                    k = min(cnt, left_a, CAP + n); left_a -= k; n -= k; px, sgn = qa, -1
                else:
                    continue
                if k <= 0:
                    continue
                fe = mfee(px, k); cash[tk] = cash.get(tk, 0.0) - sgn * px * k; fees[tk] = fees.get(tk, 0.0) + fe
                q5 = q.get(T + 300); mid5 = sum(q5) / 2 if q5 and q5[0] > 0 and q5[1] < 1 else ""
                fills.append([ev, tk, T, "buy" if sgn > 0 else "sell", px, k, fe, mid5, y, "improve" if imp else "join"])
        inv[tk] = n
    gross = sum(cash.get(tk, 0.0) + inv[tk] * (1.0 if res[tk] == "yes" else 0.0) for tk in inv)
    fee = sum(fees.values()); contracts = sum(x[5] for x in fills)
    return {"event": ev, "series": series, "status": "ok", "close": close_et.isoformat(), "fills": len(fills), "contracts": round(contracts, 2),
            "pnl_nofee": round(gross, 4), "fees": round(fee, 4), "pnl": round(gross - fee, 4)}, fills


def tstat(vals, groups):
    n = len(vals)
    if n < 3:
        return None
    mu = sum(vals) / n; s = {}
    for v, g in zip(vals, groups):
        s[g] = s.get(g, 0.0) + v - mu
    se = math.sqrt(sum(x * x for x in s.values())) / n
    return mu / se if se > 0 else None


def summarize(d):
    rows = list(csv.DictReader(open(os.path.join(d, "events.csv")))) if os.path.exists(os.path.join(d, "events.csv")) else []
    out = ["# C226 paper maker summary", f"updated {datetime.now(ET):%Y-%m-%d %H:%M} ET", "",
           "| series | events | events w/ fills | contracts | P&L $ | mean/event | day-clustered t | per contract | P&L no fee $ |", "|---|---|---|---|---|---|---|---|---|"]
    for s in SERIES:
        r = [x for x in rows if x["series"] == s and x["status"] == "ok"]
        if not r:
            continue
        v = [float(x["pnl"]) for x in r]; g = [x["close"][:10] for x in r]; c = sum(float(x["contracts"]) for x in r); t = tstat(v, g)
        out.append(f"| {s}{' (gated)' if s == GATED else ''} | {len(r)} | {sum(1 for x in r if int(x['fills']) > 0)} | {c:.0f} | {sum(v):.2f} | "
                   f"{sum(v) / len(v):.4f} | {'' if t is None else f'{t:.2f}'} | {(sum(v) / c if c else 0):.4f} | {sum(float(x['pnl_nofee']) for x in r):.2f} |")
    open(os.path.join(d, "summary.md"), "w").write("\n".join(out) + "\n")


def run(d, series_list, t0, t1):
    os.makedirs(d, exist_ok=True); ep, fp = os.path.join(d, "events.csv"), os.path.join(d, "fills.csv")
    done = {r["event"] for r in csv.DictReader(open(ep))} if os.path.exists(ep) else set()
    cols = ["event", "series", "status", "close", "fills", "contracts", "pnl_nofee", "fees", "pnl"]
    new_e = not os.path.exists(ep); new_f = not os.path.exists(fp)
    with open(ep, "a", newline="") as fe, open(fp, "a", newline="") as ff:
        we, wf = csv.DictWriter(fe, cols), csv.writer(ff)
        if new_e:
            we.writeheader()
        if new_f:
            wf.writerow(["event", "ticker", "T", "side", "price", "qty", "fee", "mid5", "settle", "quote"])
        c = t0; k = 0
        while c <= t1:
            for s in series_list:
                if ticker(s, c) in done:
                    continue
                r = simulate(s, c)
                if r is None:
                    continue
                ev, fl = r; we.writerow({k_: ev.get(k_, "") for k_ in cols}); wf.writerows(fl); k += 1
                if k % 50 == 0:
                    fe.flush(); ff.flush(); print(f"{k} events, last {ev['event']}", flush=True)
            c += timedelta(hours=1)
    summarize(d); print(open(os.path.join(d, "summary.md")).read(), flush=True)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--replay":
        a = datetime.strptime(sys.argv[2], "%Y-%m-%d").replace(tzinfo=ET); b = datetime.strptime(sys.argv[3], "%Y-%m-%d").replace(tzinfo=ET)
        run(os.path.join(HERE, f"replay_{sys.argv[4]}"), [sys.argv[4]], a, b)
        return
    now = datetime.now(ET) - timedelta(minutes=10)
    last = min(now.replace(minute=0, second=0, microsecond=0), END)
    run(os.path.join(HERE, "state"), SERIES, START, last)


if __name__ == "__main__":
    main()
