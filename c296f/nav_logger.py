"""C296F forward paper logger: Vanguard international stock ETFs vs their Admiral mutual-fund classes (stale-NAV test).
Run weekdays at 21:00 ET (ci/scheduler.py), after NAVs are published. For VXUS, VEA, VWO, VGK, VPL and VSS it records today's raw
1-minute SIP bars 15:45-16:00 ET and the SIP NBBO last quote at or before 15:49:00 and 15:59:00 (Alpaca market data; the keys are
used for data only, no orders). It also records Yahoo's last 10 days of daily chart (close = NAV, dividend events) for the six
Admiral funds and six ETFs. Scoring is offline with a scorer hashed before the data is read
(research_lab/claude/c296f-forward-spec.md). Stops after 2027-02-24.
One JSON line per run in <state>/tape/YYYY-MM.jsonl: {t, day, bars: {sym: [[t, c, v, vw], ...]}, quotes: {sym: {"1549": [t, bid, ask],
"1559": [...]}}, yahoo: {ticker: chart result}}.
Usage: python3 nav_logger.py <state_dir>   (keys from ~/.alpaca_paper)"""
import json, os, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")
STATE = sys.argv[1] if len(sys.argv) > 1 else "state"
END = datetime(2027, 2, 24, 23, 59, tzinfo=ET)
ETFS = ["VXUS", "VEA", "VWO", "VGK", "VPL", "VSS"]; MF = ["VTIAX", "VTMGX", "VEMAX", "VEUSX", "VPADX", "VFSAX"]
kv = dict(l.strip().split("=", 1) for l in open(os.path.expanduser("~/.alpaca_paper")) if "=" in l)
AH = {"APCA-API-KEY-ID": kv["APCA_API_KEY_ID"], "APCA-API-SECRET-KEY": kv["APCA_API_SECRET_KEY"]}
UA = {"User-Agent": "research-client/1.0"}


def get(url, headers):
    for k in range(5):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30).read())
        except urllib.error.HTTPError as e:
            if e.code in (400, 404): return None
            time.sleep(15 * (k + 1) if e.code == 429 else 3 + 3 * k)
        except Exception:  # noqa: BLE001
            time.sleep(3 + 3 * k)
    return None


def alpaca(path, q):
    out, tok = {}, None
    while True:
        if tok: q["page_token"] = tok
        d = get(f"https://data.alpaca.markets/v2/stocks/{path}?" + urllib.parse.urlencode(q), AH)
        if d is None: return out
        key = "bars" if path == "bars" else "quotes"
        for s, xs in (d.get(key) or {}).items(): out.setdefault(s, []).extend(xs)
        tok = d.get("next_page_token")
        if not tok: return out


def main():
    now = datetime.now(ET)
    if now > END: print("C296F logging window over"); return
    day = now.strftime("%Y-%m-%d"); ts = lambda hms: datetime.fromisoformat(f"{day}T{hms}").replace(tzinfo=ET).isoformat()
    rec = dict(t=now.isoformat(timespec="seconds"), day=day, bars={}, quotes={}, yahoo={})
    if now.weekday() < 5:
        b = alpaca("bars", dict(symbols=",".join(ETFS), timeframe="1Min", start=ts("15:45:00"), end=ts("16:00:00"), feed="sip", adjustment="raw", limit=10000))
        rec["bars"] = {s: [[x["t"], x["c"], x["v"], x["vw"]] for x in xs] for s, xs in b.items()}
        for lab, a, z in (("1549", "15:48:00", "15:49:00"), ("1559", "15:58:00", "15:59:00")):
            q = alpaca("quotes", dict(symbols=",".join(ETFS), start=ts(a), end=ts(z), feed="sip", limit=10000))
            for s, xs in q.items():
                xs = [x for x in xs if x.get("bp", 0) > 0 and x.get("ap", 0) >= x.get("bp", 0)]
                if xs:
                    x = max(xs, key=lambda y: y["t"]); rec["quotes"].setdefault(s, {})[lab] = [x["t"], x["bp"], x["ap"]]
    for t in MF + ETFS:
        d = get(f"https://query1.finance.yahoo.com/v8/finance/chart/{t}?range=10d&interval=1d&events=div", UA)
        try: rec["yahoo"][t] = d["chart"]["result"][0]
        except Exception: rec["yahoo"][t] = None  # noqa: BLE001
        time.sleep(0.5)
    os.makedirs(os.path.join(STATE, "tape"), exist_ok=True)
    with open(os.path.join(STATE, "tape", f"{day[:7]}.jsonl"), "a") as fh: fh.write(json.dumps(rec) + "\n")
    print(day, "bars", {s: len(v) for s, v in rec["bars"].items()}, "quotes", sorted(rec["quotes"]), "yahoo", sum(v is not None for v in rec["yahoo"].values()))


if __name__ == "__main__":
    main()
