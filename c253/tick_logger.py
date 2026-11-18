"""C253 tick logger: second-by-second quotes to see how Kalshi's market makers reprice. Every ~1 s: Binance PAXG/USDT (a gold-backed
token, a real-time gold spot proxy; Kalshi settles on Pyth's gold index, whose live API now needs a key), every strike's top of book for today's KXGOLDD / KXSILVERD / KXCOPPERD
(5 PM ET) events, Coinbase BTC-USD and the KXBTCD strikes of the next hourly close (a fast-engine benchmark).
Quotes come from each strike's live order book (the /markets list is a ~15-s cache): the near-money strikes are re-chosen from
the list every 30 s (gold 4, silver 2, copper 2, BTC 3, nearest 50c), then their order books are read every second.
Only changes are written (plus a full snapshot every 60 s). Public data only; no keys, no orders. Weekdays 13:30-14:30 ET.
Line format (gzip JSON, <state>/tape/YYYY-MM-DD.jsonl.gz): {t, full, paxg: [bid, ask], btc: price,
q: {ticker: [bid, ask, bid_size, ask_size, read_time]}}  (q holds only tickers that changed, or all when full=1).
Usage: python3 tick_logger.py <state_dir> [--now MINUTES]"""
import gzip, json, os, sys, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")
STATE = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
API = "https://api.elections.kalshi.com/trade-api/v2"; UA = {"User-Agent": "research-client/1.0"}
END = datetime(2026, 12, 4, 23, 59, tzinfo=ET)   # ten-ish trading days of logging
POOL = ThreadPoolExecutor(max_workers=6)


def get(url):
    try:
        return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=5).read())
    except Exception:  # noqa: BLE001
        return None


def kalshi(series, lo, hi):
    d = get(f"{API}/markets?series_ticker={series}&status=open&limit=1000&min_close_ts={lo}&max_close_ts={hi}")
    if d is None:
        return None          # failed: the caller keeps this series' previous quotes
    return {m["ticker"]: [m.get("yes_bid_dollars"), m.get("yes_ask_dollars"), m.get("yes_bid_size_fp"), m.get("yes_ask_size_fp")] for m in d.get("markets", [])}


def paxg():
    d = get("https://data-api.binance.vision/api/v3/ticker/bookTicker?symbol=PAXGUSDT") or {}
    return [float(d["bidPrice"]), float(d["askPrice"])] if d.get("bidPrice") else None


def ob_top(ticker):
    d = get(f"{API}/markets/{ticker}/orderbook")
    if not d:
        return None
    o = d.get("orderbook_fp") or {}
    yb = [(float(p), float(q)) for p, q in o.get("yes_dollars") or []]; nb = [(float(p), float(q)) for p, q in o.get("no_dollars") or []]
    by = max(yb) if yb else (None, 0.0); bn = max(nb) if nb else (None, 0.0)
    return [by[0], None if bn[0] is None else round(1 - bn[0], 4), by[1], bn[1], round(time.time(), 3)]


def pick(cached, series, k):
    c = [(abs((float(v[0]) + float(v[1])) / 2 - 0.5), t) for t, v in cached.items() if t.startswith(series + "-") and v[0] is not None and v[1] is not None]
    return [t for _, t in sorted(c)[:k]]


def btc():
    d = get("https://api.exchange.coinbase.com/products/BTC-USD/ticker") or {}
    return float(d["price"]) if d.get("price") else None


def log(msg):
    os.makedirs(os.path.join(STATE, "logs"), exist_ok=True)
    line = f"{datetime.now(ET):%Y-%m-%d %H:%M:%S} ET {msg}"; print(line, flush=True)
    with open(os.path.join(STATE, "logs", datetime.now(ET).strftime("%Y-%m") + ".log"), "a") as f:
        f.write(line + "\n")


def main():
    now = datetime.now(ET)
    if now > END:
        log("C253 window over"); return
    test = "--now" in sys.argv
    if now.weekday() >= 5 and not test:
        log("weekend"); return
    if test:
        start, stop = now, now + timedelta(minutes=float(sys.argv[sys.argv.index("--now") + 1]))
    else:
        start, stop = now.replace(hour=13, minute=30, second=0, microsecond=0), now.replace(hour=14, minute=30, second=0, microsecond=0)
        if now > stop:
            log("past 14:30 ET"); return
    while datetime.now(ET) < start:
        time.sleep(2)
    day_close = now.replace(hour=17, minute=0, second=0, microsecond=0)
    if test and now >= day_close:
        day_close += timedelta(days=1)
    mc = int(day_close.timestamp())
    os.makedirs(os.path.join(STATE, "tape"), exist_ok=True); path = os.path.join(STATE, "tape", now.strftime("%Y-%m-%d") + ".jsonl.gz")
    prev, n, nch, last_full, last_pick, chosen, cached = {}, 0, 0, 0, 0, [], {}
    with gzip.open(path, "at") as fh:
        while datetime.now(ET) < stop:
            t0 = time.time(); hc = (int(t0) // 3600 + 1) * 3600
            if t0 - last_pick >= 30 or not chosen:
                ser = [("KXGOLDD", mc), ("KXSILVERD", mc), ("KXCOPPERD", mc), ("KXBTCD", hc)]
                for (s, c), r in zip(ser, POOL.map(lambda x: kalshi(x[0], x[1] - 60, x[1] + 60), ser)):
                    if r is not None:
                        cached = {k: v for k, v in cached.items() if not k.startswith(s + "-")}; cached.update(r)
                chosen = pick(cached, "KXGOLDD", 4) + pick(cached, "KXSILVERD", 2) + pick(cached, "KXCOPPERD", 2) + pick(cached, "KXBTCD", 3)
                last_pick = t0
            jp, jb = POOL.submit(paxg), POOL.submit(btc)
            cur = {}
            for t, r in zip(chosen, POOL.map(ob_top, chosen)):
                cur[t] = r if r is not None else prev.get(t)
            full = t0 - last_full >= 60
            ch = cur if full else {k: v for k, v in cur.items() if prev.get(k) is None or v is None or prev[k][:4] != v[:4]}
            fh.write(json.dumps(dict(t=round(t0, 3), full=int(full), paxg=jp.result(), btc=jb.result(), q=ch, cached=cached if full else None)) + "\n")
            if full:
                last_full = t0; fh.flush()
            prev = cur; n += 1; nch += 0 if full else len(ch)
            time.sleep(max(0.05, 1.0 - (time.time() - t0)))
    log(f"done: {n} polls, {nch} quote changes, {len(prev)} tickers")


if __name__ == "__main__":
    main()
