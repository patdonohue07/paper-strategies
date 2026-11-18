"""C275F power order-book logger: Kalshi weekly power-price contracts (ERCOT North/West/Houston, PJM Western/Dominion/AEP-Dayton,
MISO Indiana). Once an hour (~:30 ET via ci/scheduler.py) reads every open market's live order book (the /markets list is a ~15-s
cache) and records the top of book plus the next levels. Public data only; no keys, no orders. Scoring happens offline with the
frozen C275 pricer (research_lab/claude/c275f-preregistration.md). New snapshots stop after 2027-01-22 17:00 ET.
One JSON line per run in <state>/tape/YYYY-MM.jsonl: {t, markets: {ticker: {series, event, strike, strike_type, open, close,
bid, ask, bid_size, ask_size, yes_levels, no_levels, read_time}}}.
Usage: python3 power_logger.py <state_dir>"""
import json, os, sys, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")
STATE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
API = "https://api.elections.kalshi.com/trade-api/v2"; UA = {"User-Agent": "research-client/1.0"}
SERIES = ("KXERCOTNORTHW", "KXERCOTWESTW", "KXERCOTHOUW", "KXPJMWESTW", "KXPJMDOMW", "KXPJMAEPDAYW", "KXMISOINDW")
END = datetime(2027, 1, 22, 17, 0, tzinfo=ET)


def get(url):
    for k in range(3):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15).read())
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return {}
            time.sleep(1 + 2 * k)
        except Exception:  # noqa: BLE001
            time.sleep(1 + 2 * k)
    return {}


def open_markets(s):
    out, cur = [], ""
    while True:
        d = get(f"{API}/markets?series_ticker={s}&status=open&limit=1000" + (f"&cursor={cur}" if cur else ""))
        out += d.get("markets", [])
        cur = d.get("cursor")
        if not cur or not d.get("markets"):
            return out


def book(ticker):
    d = get(f"{API}/markets/{ticker}/orderbook")
    if not d:
        return None
    o = d.get("orderbook_fp") or {}
    yb = sorted(((float(p), float(q)) for p, q in o.get("yes_dollars") or []), reverse=True)
    nb = sorted(((float(p), float(q)) for p, q in o.get("no_dollars") or []), reverse=True)
    return dict(bid=yb[0][0] if yb else None, ask=round(1 - nb[0][0], 4) if nb else None,
                bid_size=yb[0][1] if yb else 0.0, ask_size=nb[0][1] if nb else 0.0,
                yes_levels=yb[:5], no_levels=nb[:5], read_time=round(time.time(), 3))


def log(msg):
    os.makedirs(os.path.join(STATE, "logs"), exist_ok=True)
    line = f"{datetime.now(ET):%Y-%m-%d %H:%M:%S} ET {msg}"; print(line, flush=True)
    with open(os.path.join(STATE, "logs", datetime.now(ET).strftime("%Y-%m") + ".log"), "a") as f:
        f.write(line + "\n")


def main():
    now = datetime.now(ET)
    if now > END:
        log("past the C275F end date; nothing recorded"); return
    mk = {}
    for s in SERIES:
        for m in open_markets(s):
            mk[m["ticker"]] = dict(series=s, event=m["event_ticker"], strike=m.get("floor_strike"), strike_type=m.get("strike_type"),
                                   open=m.get("open_time"), close=m.get("close_time"))
    with ThreadPoolExecutor(max_workers=6) as pool:
        books = dict(zip(mk, pool.map(book, list(mk))))
    n_ok = 0
    for t, b in books.items():
        if b:
            mk[t].update(b); n_ok += 1
    os.makedirs(os.path.join(STATE, "tape"), exist_ok=True)
    with open(os.path.join(STATE, "tape", now.strftime("%Y-%m") + ".jsonl"), "a") as f:
        f.write(json.dumps(dict(t=round(time.time(), 3), markets=mk), separators=(",", ":")) + "\n")
    log(f"open markets {len(mk)} in {len({v['event'] for v in mk.values()})} events; order books read {n_ok}")


if __name__ == "__main__":
    main()
