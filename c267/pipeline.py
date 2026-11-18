"""C267 weekly niche-market pipeline (public data only; no keys, no orders). Standard library only (runs on a bare GitHub runner).
1. Discover Kalshi series in Crypto / Financials / Commodities / Economics whose FIRST market opened within the last 90 days ("new").
2. Keep niche events: open markets whose total top-of-book depth is under $20,000 (institutions don't bother) and 24 h volume under
   10,000 contracts.
3. Price contracts with a known underlying: lognormal digital for above / below / between a level at the close time; zero-drift GBM
   barrier for one-touch (MAX / MIN) contracts. Vol = 30-day realised from the underlying (Binance for crypto, Yahoo otherwise).
   Reference check: the ladder's implied center vs the model's spot; a gap over 0.5% marks the event "reference mismatch" (not flagged).
4. Flag 5c+ edges after fee, confirmed on the live order book (/markets/{t}/orderbook; the /markets list is a ~15-s cache).
5. Log every niche contract (priced or not) with its quotes, so unpriceable series build history for later models.
Writes <state>/scans/YYYY-MM-DD.json.gz and updates <state>/series_first_open.json.
Usage: python3 pipeline.py <state_dir> [--limit N]   (--limit: test on the first N series)"""
import gzip, json, math, os, re, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from statistics import NormalDist, pstdev
N = NormalDist(); API = "https://api.elections.kalshi.com/trade-api/v2"; UA = {"User-Agent": "research-client/1.0"}
STATE = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "state"
LIMIT = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
CATS = ("Crypto", "Financials", "Commodities", "Economics"); NEW_DAYS, DEPTH_MAX, VOL_MAX, EDGE, GAP_MAX = 90, 20000.0, 10000.0, 0.05, 0.005
COINS = {"BTC": "BTCUSDT", "Bitcoin": "BTCUSDT", "ETH": "ETHUSDT", "Ethereum": "ETHUSDT", "SOL": "SOLUSDT", "Solana": "SOLUSDT", "XRP": "XRPUSDT",
         "DOGE": "DOGEUSDT", "Doge": "DOGEUSDT", "ZEC": "ZECUSDT", "BNB": "BNBUSDT", "NEAR": "NEARUSDT", "ADA": "ADAUSDT", "Cardano": "ADAUSDT",
         "HYPE": "HYPEUSDT", "AVAX": "AVAXUSDT", "DOT": "DOTUSDT", "LTC": "LTCUSDT", "LINK": "LINKUSDT", "TON": "TONUSDT", "SUI": "SUIUSDT"}
YAHOO = [(r"USD.?JPY|JPY", "JPY=X"), (r"EUR.?USD", "EURUSD=X"), (r"GBP.?USD", "GBPUSD=X"), (r"AUD.?USD", "AUDUSD=X"), (r"NZD.?USD", "NZDUSD=X"),
         (r"USD.?CAD", "CAD=X"), (r"USD.?CHF", "CHF=X"), (r"USD.?SEK", "SEK=X"), (r"USD.?NOK", "NOK=X"), (r"USD.?BRL", "BRL=X"), (r"USD.?INR", "INR=X"),
         (r"USD.?MXN", "MXN=X"), (r"USD.?CNY|CNH", "CNY=X"), (r"GOLD", "GC=F"), (r"SILVER", "SI=F"), (r"COPPER", "HG=F"), (r"BRENT", "BZ=F"),
         (r"WTI|CRUDE", "CL=F"), (r"NATGAS|NATURAL GAS", "NG=F"), (r"NASDAQ|NDX", "^NDX"), (r"S&P|INX|SPX", "^GSPC"), (r"30Y", "^TYX"),
         (r"10Y|TNOTE|UST.?10", "^TNX"), (r"5Y", "^FVX")]


def get(u, tries=3):
    for k in range(tries):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30).read())
        except Exception:  # noqa: BLE001
            time.sleep(1 + 2 * k)
    return None


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def series_first_open(series, cache):
    if series in cache:
        return cache[series]
    first = None
    for base in (f"{API}/historical/markets?series_ticker={series}&limit=1000", f"{API}/markets?series_ticker={series}&limit=1000"):
        cur = ""
        for _ in range(20):
            d = get(base + (f"&cursor={cur}" if cur else "")) or {}
            for m in d.get("markets", []):
                if m.get("open_time"):
                    o = ts(m["open_time"]); first = o if first is None else min(first, o)
            cur = d.get("cursor")
            if first is not None and time.time() - first > NEW_DAYS * 86400:
                cache[series] = first; return first          # already older than the window: no need to page further
            if not cur or not d.get("markets"):
                break
    cache[series] = first; return first


NOT_PRICE = re.compile(r"export|import|inventor|production|stockpile|rig count|EIA|refinery|demand|supply|volume|downloads|subscribers|jobs|claims", re.I)


def underlying(series, title, rule):
    text = f"{series} {title} {rule}"
    mt = re.search(r"par yield[^.]*?(\d+)-year|(\d+)-year[^.]*?par yield", rule, re.I)
    if mt:                                            # settles on the Treasury's Daily Par Yield Curve: use that series itself
        return ("t", f"{mt.group(1) or mt.group(2)} Yr")
    if NOT_PRICE.search(text) or not re.search(r"price|rate|yield|close|index|value of|level", rule, re.I):
        return None                                   # only contracts whose rules describe a market price
    for k, v in COINS.items():
        if re.search(rf"\b{k}\b", text):
            return ("b", v)
    for pat, sym in YAHOO:
        if re.search(pat, text, re.I):
            return ("y", sym)
    return None


_PX = {}
_UST = None


def ust():
    global _UST
    if _UST is None:
        rows = []
        for yr in (datetime.now(timezone.utc).year - 1, datetime.now(timezone.utc).year):
            u = (f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{yr}/all?"
                 f"type=daily_treasury_yield_curve&field_tdr_date_value={yr}&page&_format=csv")
            try:
                txt = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 research-client/1.0"}), timeout=30).read().decode()
            except Exception:  # noqa: BLE001
                continue
            L = [l.split(",") for l in txt.strip().splitlines()]; hdr = [h.strip('"') for h in L[0]]
            for r in L[1:]:
                m_, d_, y_ = r[0].split("/"); rows.append(({h: r[i] for i, h in enumerate(hdr)}, f"{y_}-{m_}-{d_}"))
        _UST = sorted(rows, key=lambda x: x[1])
    return _UST


def spot_vol(src, sym):
    if (src, sym) in _PX:
        return _PX[(src, sym)]
    out = None
    if src == "t":
        S = [(d, float(r[sym])) for r, d in ust() if r.get(sym) not in (None, "", "N/A")]
        if len(S) > 31:
            v = [x[1] for x in S]; r_ = [math.log(b / a) for a, b in zip(v[-31:], v[-30:])]
            out = (v[-1], pstdev(r_) * math.sqrt(252), time.time(), S)
        _PX[(src, sym)] = out; return out
    if src == "b":
        k = get(f"https://data-api.binance.vision/api/v3/klines?symbol={sym}&interval=1d&limit=40") or []
        p = get(f"https://data-api.binance.vision/api/v3/ticker/price?symbol={sym}") or {}
        cl = [float(x[4]) for x in k]
        if len(cl) > 20 and p.get("price"):
            r = [math.log(b / a) for a, b in zip(cl[-31:], cl[-30:])]
            daily = [(datetime.fromtimestamp(x[0] / 1000, timezone.utc).strftime("%Y-%m-%d"), float(x[2]), float(x[3])) for x in k]   # (date, high, low)
            out = (float(p["price"]), pstdev(r) * math.sqrt(365), time.time(), daily)
    else:
        d = (get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?interval=1d&range=3mo") or {}).get("chart", {}).get("result")
        if d:
            cl = [x for x in d[0]["indicators"]["quote"][0]["close"] if x is not None]; meta = d[0]["meta"]
            if len(cl) > 20:
                r = [math.log(b / a) for a, b in zip(cl[-31:], cl[-30:])]
                q = d[0]["indicators"]["quote"][0]; ts_ = d[0]["timestamp"]
                daily = [(datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d"), h, l) for t, h, l in zip(ts_, q["high"], q["low"]) if h is not None and l is not None]
                out = (float(meta.get("regularMarketPrice") or cl[-1]), pstdev(r) * math.sqrt(252), float(meta.get("regularMarketTime") or 0), daily)
    _PX[(src, sym)] = out; return out


def ob_top(t):
    d = get(f"{API}/markets/{t}/orderbook") or {}; o = d.get("orderbook_fp") or {}
    yb = [(float(p), float(q)) for p, q in o.get("yes_dollars") or []]; nb = [(float(p), float(q)) for p, q in o.get("no_dollars") or []]
    by = max(yb) if yb else (None, 0.0); bn = max(nb) if nb else (None, 0.0)
    return by[0], (None if bn[0] is None else round(1 - bn[0], 4)), by[1], bn[1]


def gbm_touch(S, B, sig, T, up):
    b = math.log(B / S) if up else math.log(S / B); nu = (-0.5 if up else 0.5) * sig * sig
    if b <= 0:
        return 1.0
    s = sig * math.sqrt(T)
    return min(1.0, N.cdf((-b + nu * T) / s) + math.exp(2 * nu * b / (sig * sig)) * N.cdf((-b - nu * T) / s))


MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def period_start(rule):
    mt = re.search(r"(?:between|from|starting|after)\s+([A-Z][a-z]{2})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})", rule)
    if mt and mt.group(1).lower() in MONTHS:
        return f"{mt.group(3)}-{MONTHS[mt.group(1).lower()]:02d}-{int(mt.group(2)):02d}"
    return None


def price(m, S, sig, now, px=None, src=None):
    T = (ts(m["close_time"]) - now) / (365 * 86400)
    if T <= 0 or sig <= 0:
        return None
    rule = m.get("rules_primary", ""); s = sig * math.sqrt(T); kind = m.get("strike_type"); a, b = m.get("floor_strike"), m.get("cap_strike")
    ev = m.get("event_ticker", "")
    touch = (re.search(r"\bever\b|at any (time|point)|one.?touch|\bhit\b|\breach|\bby (jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)|highest|lowest|\bhigh of\b|\blow of\b", rule, re.I)
             or re.search(r"MAX|MIN|HIT|ABOVE.*BY|DIRH|DIRL|HIGH|LOW", ev))
    cdf = lambda k: N.cdf((math.log(k / S) + 0.5 * s * s) / s)
    try:
        if touch:
            K = a if a is not None else b
            if K is None:
                return None
            K = float(K); up = not re.search(r"below|\blow|fall|MIN|DIRL", rule + m.get("event_ticker", ""))
            ps = period_start(rule)
            if ps and px and len(px) > 3 and px[3]:                     # extreme already reached in the period (daily data)
                seen = [x for x in px[3] if x[0] >= ps]
                if src == "t":
                    ext = max(x[1] for x in seen) if seen and up else min(x[1] for x in seen) if seen else None
                else:
                    ext = max(x[1] for x in seen) if seen and up else min(x[2] for x in seen) if seen else None
                if ext is not None and ((up and ext > K) or (not up and ext < K)):
                    return ("touch_already", 1.0)
            if src == "t" or re.search(r"daily|business day|closing|close", rule, re.I):   # checked once a day: Broadie-Glasserman shift
                shift = math.exp(0.5826 * sig * math.sqrt(1 / 252)); K = K * shift if up else K / shift
            return ("touch", gbm_touch(S, K, sig, T, up))
        if kind == "greater" and a is not None:
            return ("digital", 1 - cdf(float(a)))
        if kind == "less" and (b is not None or a is not None):
            return ("digital", cdf(float(b if b is not None else a)))
        if kind == "between" and a is not None and b is not None:
            return ("range", cdf(float(b)) - cdf(float(a)))
    except (ValueError, ZeroDivisionError):
        return None
    return None


def main():
    os.makedirs(os.path.join(STATE, "scans"), exist_ok=True); now = time.time()
    cp = os.path.join(STATE, "series_first_open.json"); cache = json.load(open(cp)) if os.path.exists(cp) else {}
    S = []
    for cat in CATS:
        d = get(f"{API}/series?category={urllib.parse.quote(cat)}&limit=1000") or {}
        S += [(cat, s["ticker"], s.get("title", ""), s.get("frequency"), float(s.get("fee_multiplier") or 1)) for s in d.get("series") or []]
    if LIMIT:
        S = S[:LIMIT]
    rows, new_series = [], 0
    for cat, sid, title, freq, mult in S:
        if freq in ("hourly", "fifteen_min"):
            continue
        fo = series_first_open(sid, cache)
        if fo is None or now - fo > NEW_DAYS * 86400:
            continue
        new_series += 1
        d = get(f"{API}/markets?series_ticker={sid}&status=open&limit=1000") or {}
        ms = d.get("markets", [])
        if not ms:
            continue
        ev = {}
        for m in ms:
            ev.setdefault(m["event_ticker"], []).append(m)
        und = underlying(sid, title, ms[0].get("rules_primary", "")); px = spot_vol(*und) if und else None
        for e, L in ev.items():
            depth = sum(float(m.get("yes_bid_size_fp") or 0) * float(m.get("yes_bid_dollars") or 0) + float(m.get("yes_ask_size_fp") or 0) * (1 - float(m.get("yes_ask_dollars") or 1)) for m in L)
            vol = sum(float(m.get("volume_24h_fp") or 0) for m in L)
            if depth > DEPTH_MAX or vol > VOL_MAX:
                continue
            priced = []
            for m in L:
                r = dict(cat=cat, series=sid, title=title, freq=freq, event=e, ticker=m["ticker"], close=m.get("close_time"), strike=m.get("strike_type"),
                         fl=m.get("floor_strike"), cap=m.get("cap_strike"), list_bid=m.get("yes_bid_dollars"), list_ask=m.get("yes_ask_dollars"),
                         bid_sz=m.get("yes_bid_size_fp"), ask_sz=m.get("yes_ask_size_fp"), vol24=m.get("volume_24h_fp"), depth_event=round(depth, 2),
                         rule=m.get("rules_primary", "")[:240], mult=mult, underlying=und[1] if und else None)
                if px:
                    pr = price(m, px[0], px[1], now, px, und[0])
                    if pr:
                        r.update(model=pr[0], fair=round(pr[1], 4), S=px[0], sig=round(px[1], 4), spot_age_min=round((now - px[2]) / 60) if px[2] else None)
                        priced.append(r)
                rows.append(r)
            # reference check: implied center of the 'greater' ladder vs the model spot
            g = [r for r in priced if r["model"] == "digital" and r["strike"] == "greater" and r["list_bid"] and r["list_ask"]
                 and 0.05 < (float(r["list_bid"]) + float(r["list_ask"])) / 2 < 0.95]
            gap = None
            if len(g) >= 3 and px:
                T = (ts(g[0]["close"]) - now) / (365 * 86400); s = px[1] * math.sqrt(T); fw = []
                for r in g:
                    mid = (float(r["list_bid"]) + float(r["list_ask"])) / 2; fw.append(math.exp(math.log(float(r["fl"])) + 0.5 * s * s - N.inv_cdf(1 - mid) * s))
                fw.sort(); gap = fw[len(fw) // 2] / px[0] - 1
            for r in priced:
                r["center_gap"] = None if gap is None else round(gap, 5)
                if gap is not None and abs(gap) > GAP_MAX:
                    r["flag"] = "reference_mismatch"; continue
                if r["model"] == "touch_already":
                    r["flag"] = "already_touched_check"; continue           # our daily data says touched; the official source decides
                if gap is None and r["model"] != "touch":
                    r["flag"] = "unverified_reference"; continue      # flag only when the ladder-center check could run
                lb, la = r["list_bid"], r["list_ask"]
                if lb is None or la is None:
                    continue
                lb, la = float(lb), float(la); f = r["fair"]; fee = lambda p: 0.07 * p * (1 - p) * r["mult"]
                if (lb > 0 and lb - f - fee(lb) >= EDGE - 0.02) or (la < 1 and f - la - fee(la) >= EDGE - 0.02):
                    b, a, bs, as_ = ob_top(r["ticker"]); r.update(ob_bid=b, ob_ask=a, ob_bid_sz=bs, ob_ask_sz=as_)
                    if a is not None and f - a - fee(a) >= EDGE:
                        r.update(flag="BUY", edge=round(f - a - fee(a), 4), price=a)
                    elif b is not None and b - f - fee(b) >= EDGE:
                        r.update(flag="SELL", edge=round(b - f - fee(b), 4), price=b)
                    time.sleep(0.05)
        time.sleep(0.05)
    json.dump(cache, open(cp, "w"))
    tag = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with gzip.open(os.path.join(STATE, "scans", f"{tag}.json.gz"), "wt") as fh:
        json.dump(dict(t=now, new_series=new_series, rows=rows), fh)
    fl = [r for r in rows if r.get("flag") in ("BUY", "SELL")]
    print(f"{tag}: new series {new_series}, niche contracts logged {len(rows)}, priced {sum(1 for r in rows if 'fair' in r)}, "
          f"reference mismatches {sum(1 for r in rows if r.get('flag') == 'reference_mismatch')}, flagged {len(fl)}", flush=True)
    for r in sorted(fl, key=lambda r: -r["edge"])[:25]:
        print(f"  {r['flag']:4} {r['ticker'][:40]:40} {r['model']:7} fair {r['fair']:.3f} price {r['price']} edge {r['edge']:+.3f} gap {r['center_gap']}", flush=True)


if __name__ == "__main__":
    main()
