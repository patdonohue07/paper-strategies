"""Prints raw Yahoo daily-bar timestamps for the futures and BILI inputs (UTC, exchange local, and the date each script
currently assigns), to find the futures-shadow date-mapping bug. Public data only."""
import json, urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
for sym in ("ZNZ26.CBT", "ZBZ26.CBT", "9626.HK", "HKD=X"):
    d = json.loads(urllib.request.urlopen(urllib.request.Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=3mo&interval=1d", headers={"User-Agent": "student-research-script/1.0"}), timeout=30).read())["chart"]["result"][0]
    m = d["meta"]; tz = ZoneInfo(m["exchangeTimezoneName"]); off = m.get("gmtoffset", 0)
    print(f"\n{sym} tz {m['exchangeTimezoneName']} gmtoffset {off} regularMarketTime {datetime.fromtimestamp(m.get('regularMarketTime', 0), timezone.utc)}")
    for t, c in list(zip(d["timestamp"], d["indicators"]["quote"][0]["close"]))[-40:]:
        u = datetime.fromtimestamp(t, timezone.utc)
        print(f"  utc {u:%a %Y-%m-%d %H:%M}  local {u.astimezone(tz):%a %Y-%m-%d %H:%M %Z}  script-date {datetime.fromtimestamp(t + off, timezone.utc).date()}  close {c}")
