"""C251 gold logger: records the Kalshi daily gold / silver / copper ladders (KXGOLDD, KXSILVERD, KXCOPPERD; today's 5:00 PM ET
event) once a minute from 12:59 to 16:01 ET on weekdays: every strike's top of book (yes bid / ask and sizes) plus the market's
own last price. Public data only; no keys, no orders. Started at 12:55 ET by ci/scheduler.py.
One gzip JSON line per poll in <state>/tape/YYYY-MM-DD.jsonl.gz: {t, series: {S: [[ticker, strike_type, floor, cap, bid, ask,
bid_size, ask_size, last, close_time], ...]}}.
Usage: python3 gold_logger.py <state_dir> [--now N]   (--now N: test, record N polls right away)"""
import gzip, json, os, sys, time, urllib.error, urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")
STATE = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
API = "https://api.elections.kalshi.com/trade-api/v2"; UA = {"User-Agent": "research-client/1.0"}
SERIES = ("KXGOLDD", "KXSILVERD", "KXCOPPERD")
END = datetime(2026, 12, 31, 23, 59, tzinfo=ET)   # last settlement day in the C251 window is Dec 31


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
        with gzip.open(path, "at") as fh:
            fh.write(json.dumps(rec) + "\n")
        n += 1
        if n == 1 or n % 60 == 0:
            log(f"poll {n}: strikes {counts}, took {time.time() - t0:.1f}s")
        time.sleep(max(1, 60 - (time.time() - t0)))
    log(f"done: {n} polls")


if __name__ == "__main__":
    main()
