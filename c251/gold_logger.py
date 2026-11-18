"""C251 gold logger: records the Kalshi daily gold / silver / copper ladders (KXGOLDD, KXSILVERD, KXCOPPERD; today's 5:00 PM ET
event) once a minute from 12:59 to 16:01 ET on weekdays: every strike's top of book (yes bid / ask and sizes) plus the market's
own last price. Public data only; no keys, no orders. Started at 12:55 ET by ci/scheduler.py.
One gzip JSON line per poll in <state>/tape/YYYY-MM-DD.jsonl.gz: {t, series: {S: [[ticker, strike_type, floor, cap, bid, ask,
bid_size, ask_size, last, close_time], ...]}}.
Amendment 1 (2026-11-17, before any C251 data): the /markets list is a ~15-s cache, so polls from 14:55 to 15:01 ET also read
the live order book of every strike ("ob": {series: {ticker: [bid, ask, bid_size, ask_size, read_time]}}).
Usage: python3 gold_logger.py <state_dir> [--now N]   (--now N: test, record N polls right away)"""
import gzip, json, os, sys, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")
STATE = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
API = "https://api.elections.kalshi.com/trade-api/v2"; UA = {"User-Agent": "research-client/1.0"}
SERIES = ("KXGOLDD", "KXSILVERD", "KXCOPPERD")
END = datetime(2026, 12, 31, 23, 59, tzinfo=ET)
POOL = ThreadPoolExecutor(max_workers=6)   # last settlement day in the C251 window is Dec 31


def get(url):
    for k in range(3):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=10).read())
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return {}
            time.sleep(1 + k)
        except Exception:  # noqa: BLE001
            time.sleep(1 + k)
    return {}


def pull(s, close_ts):
    rows, cur = [], ""
    while True:
        d = get(f"{API}/markets?series_ticker={s}&status=open&limit=1000&min_close_ts={close_ts - 60}&max_close_ts={close_ts + 60}" + (f"&cursor={cur}" if cur else ""))
        for m in d.get("markets", []):
            rows.append([m["ticker"], m.get("strike_type"), m.get("floor_strike"), m.get("cap_strike"), m.get("yes_bid_dollars"), m.get("yes_ask_dollars"),
                         m.get("yes_bid_size_fp"), m.get("yes_ask_size_fp"), m.get("last_price_dollars"), m.get("close_time")])
        cur = d.get("cursor")
        if not cur or not d.get("markets"):
            return rows


def ob_top(ticker):
    """Live top of book from the per-market order book (the /markets list is a ~15-s cache). [yes_bid, yes_ask, bid_size, ask_size, read_time]."""
    d = get(f"{API}/markets/{ticker}/orderbook")
    if not d:
        return None
    o = d.get("orderbook_fp") or {}
    yb = [(float(p), float(q)) for p, q in o.get("yes_dollars") or []]; nb = [(float(p), float(q)) for p, q in o.get("no_dollars") or []]
    by = max(yb) if yb else (None, 0.0); bn = max(nb) if nb else (None, 0.0)
    return [by[0], None if bn[0] is None else round(1 - bn[0], 4), by[1], bn[1], round(time.time(), 3)]


def log(msg):
    os.makedirs(os.path.join(STATE, "logs"), exist_ok=True)
    line = f"{datetime.now(ET):%Y-%m-%d %H:%M:%S} ET {msg}"; print(line, flush=True)
    with open(os.path.join(STATE, "logs", datetime.now(ET).strftime("%Y-%m") + ".log"), "a") as f:
        f.write(line + "\n")


def main():
    now = datetime.now(ET)
    if now > END:
        log("C251 window over; nothing recorded"); return
    if now.weekday() >= 5 and "--now" not in sys.argv:
        log("weekend; nothing recorded"); return
    close = now.replace(hour=17, minute=0, second=0, microsecond=0)
    if "--now" in sys.argv and now >= close:
        close += timedelta(days=1)          # test after hours: record the next event
    close_ts = int(close.timestamp())
    if "--now" in sys.argv:
        n_test = int(sys.argv[sys.argv.index("--now") + 1]); start, stop = now, now + timedelta(minutes=n_test)
    else:
        start, stop = now.replace(hour=12, minute=59, second=0, microsecond=0), now.replace(hour=16, minute=1, second=0, microsecond=0)
        if now > stop:
            log("past 16:01 ET; nothing recorded"); return
    while datetime.now(ET) < start:
        time.sleep(5)
    os.makedirs(os.path.join(STATE, "tape"), exist_ok=True); path = os.path.join(STATE, "tape", now.strftime("%Y-%m-%d") + ".jsonl.gz")
    n = 0; counts = {}
    while datetime.now(ET) < stop:
        t0 = time.time(); rec = dict(t=t0, series={})
        for s in SERIES:
            rec["series"][s] = pull(s, close_ts); counts[s] = len(rec["series"][s])
        hm = datetime.now(ET).hour * 60 + datetime.now(ET).minute
        if 14 * 60 + 55 <= hm <= 15 * 60 + 1 or "--now" in sys.argv:
            rec["ob"] = {s: dict(zip([r[0] for r in rec["series"][s]], POOL.map(ob_top, [r[0] for r in rec["series"][s]]))) for s in SERIES}
        with gzip.open(path, "at") as fh:
            fh.write(json.dumps(rec) + "\n")
        n += 1
        if n == 1 or n % 60 == 0:
            log(f"poll {n}: strikes {counts}, took {time.time() - t0:.1f}s")
        time.sleep(max(1, 60 - (time.time() - t0)))
    log(f"done: {n} polls")


if __name__ == "__main__":
    main()
