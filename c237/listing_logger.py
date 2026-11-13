"""C237 forward logger: snapshot each new Kalshi market once, 60-90 min after it opens (public data, no keys, no orders).
Research question: are favourites (YES mid 0.80-0.97) overpriced an hour after listing? Analysis happens offline.
Runs for RUN_MINUTES (default 54), one cycle every 5 minutes; data in state/ as hourly gzip shards so each save is small.
Usage: python3 listing_logger.py [state_dir]"""
import gzip, json, os, re, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta
STATE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
B = "https://api.elections.kalshi.com/trade-api/v2"; UA = {"User-Agent": "research-client/1.0"}
END = datetime(2026, 12, 14, 6, 40, tzinfo=timezone.utc).timestamp()   # listings to 2026-12-13 23:59 ET + 90 min window
RUN = float(os.environ.get("RUN_MINUTES", "54")) * 60


def log(msg):
    line = f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}"; print(line, flush=True)
    os.makedirs(os.path.join(STATE, "logs"), exist_ok=True)
    with open(os.path.join(STATE, "logs", datetime.now(timezone.utc).strftime("%Y-%m-%d") + ".log"), "a") as f:
        f.write(line + "\n")


def get(path):
    for k in range(6):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(B + path, headers=UA), timeout=30))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(1 + 3 * k)
        except Exception:
            time.sleep(1 + 3 * k)
    raise RuntimeError("request failed: " + path)


def ts(s):
    return datetime.fromisoformat(re.sub(r"\.\d+", "", s).replace("Z", "+00:00")).timestamp()


def shard(t):
    return os.path.join(STATE, "snap", datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d_%H") + ".jsonl.gz")


def load_seen():
    seen, d = set(), os.path.join(STATE, "snap")
    cut = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d_%H")
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if f[:13] >= cut:
            with gzip.open(os.path.join(d, f), "rt") as g:
                seen |= {json.loads(l)["ticker"] for l in g}
    return seen


def cycle(seen, series):
    now = time.time(); cur = ""; ms = []
    while True:
        d = get(f"/markets?status=open&mve_filter=exclude&limit=1000&min_created_ts={int(now - 86400)}" + (f"&cursor={cur}" if cur else ""))
        ms += d.get("markets", []); cur = d.get("cursor")
        if not cur or not d.get("markets"):
            break
        time.sleep(0.3)
    rows = []
    for m in ms:
        if m["ticker"] in seen or not m.get("open_time"):
            continue
        age = (now - ts(m["open_time"])) / 60
        if not (60 <= age < 90):
            continue
        s = m["event_ticker"].split("-")[0]
        if s not in series:
            r = get(f"/series/{s}"); series[s] = (r or {}).get("series", {}).get("category", ""); time.sleep(0.3)
        rows.append(dict(ticker=m["ticker"], event=m["event_ticker"], series=s, category=series[s], open_time=m["open_time"],
                         close_time=m.get("close_time"), poll=now, age_min=round(age, 2), yes_bid=m.get("yes_bid_dollars"),
                         yes_ask=m.get("yes_ask_dollars"), bid_size=m.get("yes_bid_size_fp"), ask_size=m.get("yes_ask_size_fp"),
                         volume=m.get("volume_fp"), oi=m.get("open_interest_fp"), title=m.get("title"), sub=m.get("yes_sub_title")))
        seen.add(m["ticker"])
    if rows:
        os.makedirs(os.path.join(STATE, "snap"), exist_ok=True)
        with gzip.open(shard(now), "at") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
    return len(ms), len(rows)


def main():
    os.makedirs(STATE, exist_ok=True)
    if time.time() > END:
        log("past end of listing window; nothing to do"); return
    sp = os.path.join(STATE, "series.json"); series = json.load(open(sp)) if os.path.exists(sp) else {}
    seen = load_seen(); t_start = time.time()
    lp = os.path.join(STATE, "last_cycle.txt")
    if os.path.exists(lp):
        gap = (t_start - float(open(lp).read())) / 60
        if gap > 7:
            log(f"GAP {gap:.1f} min since last cycle")
    while True:
        t0 = time.time()
        try:
            n, new = cycle(seen, series); log(f"cycle listed {n} new {new} took {time.time() - t0:.1f}s")
            open(lp, "w").write(str(t0))
        except Exception as e:
            log(f"ERROR {e!r}")
        json.dump(series, open(sp, "w"))
        if time.time() - t_start + 300 > RUN or time.time() > END:
            break
        time.sleep(max(0, 300 - (time.time() - t0)))


if __name__ == "__main__":
    main()
