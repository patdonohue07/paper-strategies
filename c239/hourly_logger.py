"""C239 hourly logger: records the Kalshi hourly crypto "above" ladders (KXBTCD, KXETHD, KXSOLD, KXXRPD, KXDOGED) every 15 s
in the last ~2.5 minutes before each hourly close, with a Coinbase spot reading just before (p0) and after (p1) each series pull.
Same record format as the C219 scan (research_lab/code/c219_scan.py), so the frozen C228 model reads it unchanged:
{ts, series: {S: {p0: [price, time], p1: [price, time], t0, t1, markets: [[event, ticker, strike_type, floor, cap, bid, ask,
 bid_sz, ask_sz, close]]}}}
Public data only; no keys, no orders. Started at :56 ET each hour by ci/scheduler.py; polls from :57:40 to :00:20.
Usage: python3 hourly_logger.py <state_dir> [--now]   (--now: test, record the next 3 minutes whatever the clock says)"""
import gzip, json, os, sys, time, urllib.error, urllib.request
from datetime import datetime, timedelta, timezone

STATE = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
API = "https://api.elections.kalshi.com/trade-api/v2"; UA = {"User-Agent": "research-client/1.0"}
SERIES = {"KXBTCD": "BTC-USD", "KXETHD": "ETH-USD", "KXSOLD": "SOL-USD", "KXXRPD": "XRP-USD", "KXDOGED": "DOGE-USD"}
INTERVAL = 15
END = datetime(2026, 12, 7, 0, 5, tzinfo=timezone(timedelta(hours=-5)))   # test window ends with the Dec 7 00:00 ET close


def get(url):
    for k in range(3):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=8).read())
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return {}
            time.sleep(0.5 + k)
        except Exception:  # noqa: BLE001
            time.sleep(0.5 + k)
    return {}


def price(prod):
    t = get(f"https://api.exchange.coinbase.com/products/{prod}/ticker")
    return [float(t["price"]), t.get("time")] if t.get("price") else None


def pull(s, max_close):
    """Open markets of series s closing by max_close (only the event closing this hour)."""
    rows, cur = [], ""
    while True:
        d = get(f"{API}/markets?series_ticker={s}&status=open&limit=1000&max_close_ts={max_close}" + (f"&cursor={cur}" if cur else ""))
        for m in d.get("markets", []):
            rows.append([m["event_ticker"], m["ticker"], m.get("strike_type"), m.get("floor_strike"), m.get("cap_strike"),
                         m.get("yes_bid_dollars"), m.get("yes_ask_dollars"), m.get("yes_bid_size_fp"), m.get("yes_ask_size_fp"),
                         m.get("close_time")])
        cur = d.get("cursor")
        if not cur or not d.get("markets"):
            return rows


def log(msg):
    os.makedirs(os.path.join(STATE, "logs"), exist_ok=True)
    line = f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC {msg}"; print(line, flush=True)
    with open(os.path.join(STATE, "logs", datetime.now(timezone.utc).strftime("%Y-%m") + ".log"), "a") as f:
        f.write(line + "\n")


def main():
    now = time.time()
    if datetime.now(timezone.utc) > END:
        log("C239 window over; nothing recorded"); return
    close = (int(now) // 3600 + 1) * 3600                      # next top of the hour
    if close - now > 600 and "--now" not in sys.argv:
        log(f"started {int(close - now)} s before the next close (too early or too late); exiting"); return
    start, stop = (now, now + 45) if "--now" in sys.argv else (close - 140, close + 20)
    while time.time() < start:
        time.sleep(min(5, start - time.time()))
    os.makedirs(os.path.join(STATE, "tape"), exist_ok=True)
    path = os.path.join(STATE, "tape", "c239_" + datetime.fromtimestamp(close, timezone.utc).strftime("%Y%m%d_%H") + ".jsonl.gz")
    n = nm = 0
    while time.time() < stop:
        t0 = time.time(); rec = dict(ts=datetime.now(timezone.utc).isoformat(), series={})
        for s, prod in SERIES.items():
            a = time.time(); p0 = price(prod); ms = pull(s, close + 60); p1 = price(prod)
            rec["series"][s] = dict(p0=p0, p1=p1, t0=a, t1=time.time(), markets=ms)
        with gzip.open(path, "at") as fh:
            fh.write(json.dumps(rec) + "\n")
        n += 1; nm += sum(len(v["markets"]) for v in rec["series"].values())
        time.sleep(max(0, INTERVAL - (time.time() - t0)))
    log(f"close {datetime.fromtimestamp(close, timezone.utc):%Y-%m-%d %H:%M} UTC: {n} cycles, {nm} market rows, last cycle took {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
