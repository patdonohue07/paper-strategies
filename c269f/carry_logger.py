"""C269F forward paper test: funding carry on Hyperliquid builder-deployed (HIP-3) perps (research_lab claude/c269f-preregistration.md).
Paper only: public info endpoint, no keys, no orders. Standard library only. Run hourly at ~:02 by ci/scheduler.py.
State in <state>: positions.json (open), closed.jsonl (closed positions), logs/. Usage: python3 carry_logger.py <state_dir> [--dry]"""
import json, math, os, sys, time, urllib.request
from datetime import datetime, timezone
STATE = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "state"; DRY = "--dry" in sys.argv
URL = "https://api.hyperliquid.xyz/info"; UA = {"Content-Type": "application/json", "User-Agent": "research-client/1.0"}
TH, VOL_MIN, FEE, FEE_STRESS = 0.0001, 10000.0, 0.00045, 0.0010
RULES = {"A": 24, "B": 72}
END = datetime(2027, 2, 18, 23, 59, tzinfo=timezone.utc).timestamp()


def post(b):
    for k in range(4):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(URL, data=json.dumps(b).encode(), headers=UA), timeout=30).read())
        except Exception:  # noqa: BLE001
            time.sleep(2 + 4 * k)
    return None


def log(msg):
    os.makedirs(os.path.join(STATE, "logs"), exist_ok=True); line = f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC {msg}"; print(line, flush=True)
    with open(os.path.join(STATE, "logs", datetime.now(timezone.utc).strftime("%Y-%m") + ".log"), "a") as f:
        f.write(line + "\n")


def touch(coin):
    b = post({"type": "l2Book", "coin": coin}) or {}
    lv = b.get("levels") or [[], []]
    if not lv[0] or not lv[1]:
        return None
    bid, ask = float(lv[0][0]["px"]), float(lv[1][0]["px"]); return dict(bid=bid, ask=ask, mid=(bid + ask) / 2, bid_sz=float(lv[0][0]["sz"]), ask_sz=float(lv[1][0]["sz"]))


def main():
    now = time.time(); hour = int(now // 3600) * 3600
    pp = os.path.join(STATE, "positions.json"); P = json.load(open(pp)) if os.path.exists(pp) else []
    dexes = [d["name"] for d in (post({"type": "perpDexs"}) or []) if d]
    markets = {}
    for dx in dexes:
        r = post({"type": "metaAndAssetCtxs", "dex": dx})
        if not r:
            continue
        for u, c in zip(r[0]["universe"], r[1]):
            markets[u["name"]] = dict(dex=dx, vol=float(c.get("dayNtlVlm") or 0))
        time.sleep(0.3)
    # 1) accrue funding settled at this hour on open positions; close those due
    still, closed = [], []
    for p in P:
        f = post({"type": "fundingHistory", "coin": p["coin"], "startTime": int((p["last_accrued"] + 1) * 1000)}) or []
        for x in f:
            t = int(x["time"]) // 1000
            if p["last_accrued"] < t <= now:
                p["funding"] += -p["side"] * float(x["fundingRate"]); p["last_accrued"] = t
        if now >= p["entry_t"] + p["hold_h"] * 3600 - 300:
            q = touch(p["coin"])
            if q is None:
                still.append(p); continue
            px = q["bid"] if p["side"] > 0 else q["ask"]; ret = p["side"] * (px / p["entry_px"] - 1)
            p.update(exit_t=now, exit_px=px, exit_mid=q["mid"], price_ret=ret, pnl=ret + p["funding"] - 2 * FEE, pnl_stress=ret + p["funding"] - 2 * FEE_STRESS)
            closed.append(p)
        else:
            still.append(p)
        time.sleep(0.2)
    # 2) new signals from the funding settled at this hour
    opened = 0
    if now <= END:
        busy = {(p["rule"], p["coin"]) for p in still}
        for coin, m in markets.items():
            if m["vol"] < VOL_MIN:
                continue
            f = post({"type": "fundingHistory", "coin": coin, "startTime": int((hour - 1800) * 1000)}) or []
            f = [x for x in f if int(x["time"]) // 1000 >= hour - 600]
            if not f:
                continue
            rate = float(f[-1]["fundingRate"])
            if abs(rate) < TH:
                continue
            q = touch(coin)
            if q is None:
                continue
            side = -1 if rate > 0 else 1
            for rule, H in RULES.items():
                for tag, sd in ((rule, side), (rule + "_flip", -side)) if rule == "A" else ((rule, side),):
                    if (tag, coin) in busy:
                        continue
                    px = q["ask"] if sd > 0 else q["bid"]
                    still.append(dict(rule=tag, coin=coin, dex=m["dex"], control=(m["dex"] == "xyz"), side=sd, signal_rate=rate, entry_t=now, entry_px=px, entry_mid=q["mid"],
                                      touch_size=q["ask_sz"] if sd > 0 else q["bid_sz"], hold_h=H, funding=0.0, last_accrued=hour)); opened += 1
            time.sleep(0.2)
    if not DRY:
        os.makedirs(STATE, exist_ok=True); json.dump(still, open(pp, "w"))
        with open(os.path.join(STATE, "closed.jsonl"), "a") as fh:
            for p in closed:
                fh.write(json.dumps(p) + "\n")
    log(f"markets {len(markets)} (dexes {len(dexes)}), opened {opened}, closed {len(closed)}, open now {len(still)}" + (" [dry]" if DRY else ""))


if __name__ == "__main__":
    main()
