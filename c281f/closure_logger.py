"""C281F closure order-book logger: stock perps on Hyperliquid builder dexes (xyz, io, para) and Lighter.
Run at 20:00 ET and 10:00 ET every day (ci/scheduler.py). Reads the live order book of each of the 159 frozen C281 perps
(c281f/universe.json) and records best bid / ask, sizes and the top 10 levels; for Hyperliquid dexes also mark, oracle, mid and
funding from metaAndAssetCtxs. Public data only; no keys, no orders. Scoring happens offline with a scorer hashed before the data
is read (research_lab/claude/c281f-preregistration.md). New snapshots stop after 2027-03-01 12:00 ET.
One JSON line per run in <state>/tape/YYYY-MM.jsonl: {t, slot, perps: {"venue:NAME": {bid, ask, bid_size, ask_size, bids, asks,
read_time, [mark, oracle, mid, funding]}}}.
Usage: python3 closure_logger.py <state_dir>"""
import json, os, sys, time, urllib.error, urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "state")
HL = "https://api.hyperliquid.xyz/info"; LT = "https://mainnet.zklighter.elliot.ai/api/v1"
HDR = {"User-Agent": "research-client/1.0", "Content-Type": "application/json"}
END = datetime(2027, 3, 1, 12, 0, tzinfo=ET)
U = json.load(open(os.path.join(HERE, "universe.json")))
NLEV = 10


def req(url, body=None):
    for k in range(4):
        try:
            data = json.dumps(body).encode() if body is not None else None
            return json.loads(urllib.request.urlopen(urllib.request.Request(url, data=data, headers=HDR), timeout=15).read())
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return None
            time.sleep(1 + 2 * k)
        except Exception:  # noqa: BLE001
            time.sleep(1 + 2 * k)
    return None


def pack(bids, asks):
    bids = sorted(bids, key=lambda x: -x[0])[:NLEV]; asks = sorted(asks, key=lambda x: x[0])[:NLEV]
    return dict(bid=bids[0][0] if bids else None, ask=asks[0][0] if asks else None,
                bid_size=bids[0][1] if bids else 0.0, ask_size=asks[0][1] if asks else 0.0,
                bids=bids, asks=asks, read_time=round(time.time(), 3))


def hl_book(coin):
    d = req(HL, {"type": "l2Book", "coin": coin})
    if not d or "levels" not in d:
        return None
    b, a = d["levels"]
    return pack([(float(x["px"]), float(x["sz"])) for x in b], [(float(x["px"]), float(x["sz"])) for x in a])


def lt_book(mid):
    d = req(f"{LT}/orderBookOrders?market_id={mid}&limit=100")
    if not d or "asks" not in d:
        return None
    agg = {"b": defaultdict(float), "a": defaultdict(float)}
    for side, key in (("b", "bids"), ("a", "asks")):
        for o in d.get(key) or []:
            agg[side][float(o["price"])] += float(o["remaining_base_amount"])
    return pack(list(agg["b"].items()), list(agg["a"].items()))


def log(msg):
    os.makedirs(os.path.join(STATE, "logs"), exist_ok=True)
    line = f"{datetime.now(ET):%Y-%m-%d %H:%M:%S} ET {msg}"; print(line, flush=True)
    with open(os.path.join(STATE, "logs", datetime.now(ET).strftime("%Y-%m") + ".log"), "a") as f:
        f.write(line + "\n")


def main():
    now = datetime.now(ET)
    if now > END:
        log("past the C281F end date; nothing recorded"); return
    slot = "eve20" if now.hour >= 15 else "x10"
    ctx = {}
    for dex in ("xyz", "io", "para"):
        m = req(HL, {"type": "metaAndAssetCtxs", "dex": dex})
        if m:
            for a, c in zip(m[0]["universe"], m[1]):
                ctx[a["name"]] = dict(mark=c.get("markPx"), oracle=c.get("oraclePx"), mid=c.get("midPx"), funding=c.get("funding"))
    jobs = [(f"{dex}:{n}", "hl", f"{dex}:{n}") for dex in ("xyz", "io", "para") for n in U[dex]]
    jobs += [(f"lighter:{n}", "lt", U["lighter_ids"][n]) for n in U["lighter"]]
    with ThreadPoolExecutor(max_workers=4) as pool:
        books = list(pool.map(lambda j: hl_book(j[2]) if j[1] == "hl" else lt_book(j[2]), jobs))
    perps, n_ok = {}, defaultdict(int)
    for (key, kind, arg), b in zip(jobs, books):
        if b is None:
            continue
        if kind == "hl" and arg in ctx:
            b.update(ctx[arg])
        perps[key] = b
        if b["bid"] is not None and b["ask"] is not None:
            n_ok[key.split(":")[0]] += 1
    os.makedirs(os.path.join(STATE, "tape"), exist_ok=True)
    with open(os.path.join(STATE, "tape", now.strftime("%Y-%m") + ".jsonl"), "a") as f:
        f.write(json.dumps(dict(t=round(time.time(), 3), slot=slot, perps=perps), separators=(",", ":")) + "\n")
    log(f"slot {slot}: books read {len(perps)}/{len(jobs)}; two-sided " + ", ".join(f"{v} {n_ok[v]}" for v in ("xyz", "io", "para", "lighter")))


if __name__ == "__main__":
    main()
