"""C238 noon logger: records Kalshi and Polymarket order-book tops for the noon-ET crypto "above" contracts (BTC, ETH, SOL, XRP)
every 15 s from 10:55 to 12:00:30 ET, in the same row format as the Event Contract Monitor tape. Public data only; no keys, no orders.
Usage: python3 noon_logger.py <state_dir> [--minutes N --day YYYY-MM-DD]   (exits at 12:00:30 ET; the options are for testing)"""
import gzip, json, os, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine as E  # noqa: E402

STATE = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
LIMIT = float(sys.argv[sys.argv.index("--minutes") + 1]) * 60 if "--minutes" in sys.argv else None
POLL, REDISCOVER, CHUNK, MAX_SKEW = 15, 300, 12, 3.0
POOL = ThreadPoolExecutor(max_workers=4)


def log(msg):
    os.makedirs(os.path.join(STATE, "logs"), exist_ok=True)
    line = f"{datetime.now(E.ET):%Y-%m-%d %H:%M:%S} ET {msg}"; print(line, flush=True)
    with open(os.path.join(STATE, "logs", datetime.now(E.ET).strftime("%Y-%m-%d") + ".log"), "a") as f:
        f.write(line + "\n")


DAY = sys.argv[sys.argv.index("--day") + 1] if "--day" in sys.argv else None   # test only: record another day's noon contracts


def today_pairs():
    d = datetime.strptime(DAY, "%Y-%m-%d") if DAY else datetime.now(E.ET)
    return [p for p in E.crypto_pairs(datetime.now(E.ET)) if p["k_ticker"].split("-")[1].startswith(f"{d.year % 100:02d}{E.MON[d.month - 1]}{d.day:02d}12")]


def cycle(pairs):
    rows = []
    for i in range(0, len(pairs), CHUNK):
        chunk = pairs[i:i + CHUNK]

        def kal(p):
            try:
                return p["k_ticker"], E.kalshi_ladders(p["k_ticker"]), time.time()
            except Exception:  # noqa: BLE001
                return p["k_ticker"], None, time.time()
        ks = {t: (lad, tt) for t, lad, tt in POOL.map(kal, chunk)}
        toks = sorted({t for p in chunk for t in (p["yes_tok"], p["no_tok"])})
        t0 = time.time(); books = E.poly_books(toks); t_p = (t0 + time.time()) / 2
        for p in chunk:
            kx, t_k = ks.get(p["k_ticker"], (None, None))
            if kx is None:
                continue
            pm = E.poly_ladders(p["yes_tok"], p["no_tok"], books)
            km, ks_ = E.mid(*kx); pmm, ps = E.mid(*pm)
            skew = abs(t_k - t_p)
            status = ("kalshi-closed" if not (kx[0] or kx[1]) else "no-book" if not (pm[0] or pm[1]) else "stale" if skew > MAX_SKEW
                      else "one-sided" if not (kx[0] and kx[1] and pm[0] and pm[1]) else "ok")
            rows.append(dict(id=p["k_ticker"], strike=p["strike"], coin=p["coin"], t_kalshi=t_k, t_poly=t_p, skew=skew, status=status,
                             k_mid=km, k_spread=ks_, p_mid=pmm, p_spread=ps,
                             k_top=dict(yes=E.touch(kx[0]), no=E.touch(kx[1])), p_top=dict(yes=E.touch(pm[0]), no=E.touch(pm[1])),
                             k_book=[lad[:10] for lad in kx], p_book=[lad[:10] for lad in pm]))
    return rows


def main():
    os.makedirs(os.path.join(STATE, "tape"), exist_ok=True)
    start = time.time(); now = datetime.now(E.ET)
    end = now.replace(hour=12, minute=0, second=30, microsecond=0)
    if LIMIT:
        end = now + timedelta(seconds=LIMIT)
    if now >= end:
        log("past 12:00:30 ET; nothing to record today"); return
    while datetime.now(E.ET) < now.replace(hour=10, minute=55, second=0) and not LIMIT:
        time.sleep(10)
    pairs, last_disc, n = [], 0, 0
    path = os.path.join(STATE, "tape", datetime.now(E.ET).strftime("%Y-%m-%d") + ".jsonl.gz")
    while datetime.now(E.ET) < end:
        t0 = time.time()
        if time.time() - last_disc > REDISCOVER or not pairs:
            try:
                pairs = today_pairs(); last_disc = time.time()
                log(f"matched {len(pairs)} noon pairs; Kalshi open on {sum(1 for p in pairs if p.get('tradable_now'))}")
            except Exception as e:  # noqa: BLE001
                log(f"discovery error {e!r}")
        if pairs:
            try:
                rows = cycle(pairs); n += 1
                with gzip.open(path, "at") as f:
                    f.write(json.dumps(dict(t=time.time(), poll=n, rows=rows), default=float) + "\n")
                if n % 20 == 1:
                    log(f"poll {n}: {len(rows)} rows, {sum(1 for r in rows if r['status'] == 'ok')} ok, took {time.time() - t0:.1f}s")
            except Exception as e:  # noqa: BLE001
                log(f"poll error {e!r}")
        time.sleep(max(1, POLL - (time.time() - t0)))
    log(f"done: {n} polls in {(time.time() - start) / 60:.1f} min")


if __name__ == "__main__":
    main()
