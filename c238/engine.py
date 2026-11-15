"""Prediction-market cross-venue analytics MVP (Kalshi vs Polymarket). Public endpoints only; no keys, no orders.
For every matched contract pair: rule diff + basis-risk grade, full-depth executable gaps net of each venue's taker fee at
fixed sizes, the largest size that is still profitable, and a consensus fair price. Writes mvp/out/snapshot.json.
Usage: python3 -I mvp/engine.py"""
import json, math, os, re, time, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
HERE = os.path.dirname(os.path.abspath(__file__)); LAB = os.path.dirname(HERE); OUT = os.path.join(HERE, "out")
ET = ZoneInfo("America/New_York"); UA = {"User-Agent": "research-client/1.0"}
KAPI = "https://api.elections.kalshi.com/trade-api/v2"; GAMMA = "https://gamma-api.polymarket.com"; CLOB = "https://clob.polymarket.com"
SIZES = [100, 1000, 10000]   # paired contracts (each pair pays $1 at settlement if both venues settle the same way)
KFEE = 0.07                  # Kalshi taker fee coefficient: fee = 0.07 * p * (1 - p) per contract
MON = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
MONL = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
COINS = {"BTC": ("bitcoin", "KXBTCD", "BTCUSDT", "BTC-USD"), "ETH": ("ethereum", "KXETHD", "ETHUSDT", "ETH-USD"),
         "SOL": ("solana", "KXSOLD", "SOLUSDT", "SOL-USD"), "XRP": ("xrp", "KXXRPD", "XRPUSDT", "XRP-USD")}
FED_MAP = {"C26": "50+ bps decrease", "C25": "25 bps decrease", "H0": "No change", "H25": "25 bps increase", "H26": "50+ bps increase"}


def req(url, body=None):
    for k in range(4):
        try:
            r = urllib.request.Request(url, headers={**UA, **({"Content-Type": "application/json"} if body else {})},
                                       data=json.dumps(body).encode() if body is not None else None)
            return json.loads(urllib.request.urlopen(r, timeout=25).read())
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return None
            time.sleep(1 + 2 * k)
        except Exception:  # noqa: BLE001
            time.sleep(1 + 2 * k)
    return None


# ---------- order books: every book is reduced to ask ladders [(price, size)] for buying YES and buying NO ----------
def kalshi_ladders(ticker):
    ob = (req(f"{KAPI}/markets/{ticker}/orderbook") or {}).get("orderbook_fp", {})
    yb = [(float(p), float(q)) for p, q in ob.get("yes_dollars") or []]; nb = [(float(p), float(q)) for p, q in ob.get("no_dollars") or []]
    buy_yes = sorted((round(1 - p, 4), q) for p, q in nb)   # buying YES lifts resting NO bids
    buy_no = sorted((round(1 - p, 4), q) for p, q in yb)
    return buy_yes, buy_no


def poly_ladders(yes_tok, no_tok, books):
    def asks(t):
        return sorted((float(x["price"]), float(x["size"])) for x in (books.get(t) or {}).get("asks", []))
    return asks(yes_tok), asks(no_tok)


def poly_books(tokens):
    out = {}
    for i in range(0, len(tokens), 40):
        for b in req(f"{CLOB}/books", [{"token_id": t} for t in tokens[i:i + 40]]) or []:
            out[b["asset_id"]] = b
    return out


def touch(lad):
    return lad[0] if lad else (None, 0.0)


# ---------- execution maths ----------
def fill(lad, q, fee):
    """Cost of buying q contracts up a ladder, including fees. None if the book is too thin."""
    left, cost = q, 0.0
    for p, s in lad:
        take = min(left, s); cost += take * (p + fee(p)); left -= take
        if left <= 1e-9:
            return cost
    return None


def max_profitable(la, fa, lb, fb):
    """Walk both ladders together; keep adding pairs while one more pair still costs less than $1. Returns (q, profit)."""
    i = j = 0; ra = la[0][1] if la else 0; rb = lb[0][1] if lb else 0; q = prof = 0.0
    while i < len(la) and j < len(lb):
        pa, pb = la[i][0], lb[j][0]; edge = 1 - (pa + fa(pa)) - (pb + fb(pb))
        if edge <= 0:
            break
        take = min(ra, rb); q += take; prof += take * edge; ra -= take; rb -= take
        if ra <= 1e-9:
            i += 1; ra = la[i][1] if i < len(la) else 0
        if rb <= 1e-9:
            j += 1; rb = lb[j][1] if j < len(lb) else 0
    return q, prof


def kfee(p):
    return KFEE * p * (1 - p)


def pfee_fn(sched):
    if not sched:
        return lambda p: 0.0
    r, e = float(sched.get("rate", 0)), float(sched.get("exponent", 1))
    return lambda p: r * (p * (1 - p)) ** e


def evaluate(kx, pm, pfee):
    """Two directions: (A) YES on Kalshi + NO on Polymarket, (B) NO on Kalshi + YES on Polymarket."""
    k_yes, k_no = kx; p_yes, p_no = pm; res = {}
    for name, la, fa, lb, fb in (("YES Kalshi + NO Polymarket", k_yes, kfee, p_no, pfee), ("NO Kalshi + YES Polymarket", k_no, kfee, p_yes, pfee)):
        row = {"touch_edge": None, "sizes": {}}
        if la and lb:
            row["touch_edge"] = 1 - (la[0][0] + fa(la[0][0])) - (lb[0][0] + fb(lb[0][0]))
        for q in SIZES:
            ca, cb = fill(la, q, fa), fill(lb, q, fb)
            row["sizes"][q] = None if ca is None or cb is None else (q - ca - cb) / q   # edge per pair
        mq, mp = max_profitable(la, fa, lb, fb); row["max_q"] = mq; row["max_profit"] = mp
        res[name] = row
    return res


def mid(lad_yes, lad_no):
    a = touch(lad_yes)[0]; b = touch(lad_no)[0]
    if a is None or b is None:
        return None, None
    bid = 1 - b; return (a + bid) / 2, a - bid   # mid and spread of YES


def fair(km, ks, pmm, ps):
    """Consensus fair YES price: inverse-spread-weighted mid across venues."""
    w = [(m, 1 / max(s, 0.005)) for m, s in ((km, ks), (pmm, ps)) if m is not None and s is not None]
    return sum(m * x for m, x in w) / sum(x for _, x in w) if w else None


# ---------- pair discovery ----------
def fed_pairs():
    pairs = []
    evs = (req(f"{KAPI}/events?series_ticker=KXFEDDECISION&status=open&limit=10&with_nested_markets=true") or {}).get("events", [])
    for e in evs:
        ms = {m["ticker"].split("-")[-1]: m for m in e.get("markets", [])}
        close = min(m["close_time"] for m in ms.values()); d = datetime.fromisoformat(close.replace("Z", "+00:00"))
        month = MONL[d.month - 1]
        hits = (req(f"{GAMMA}/public-search?q=fed%20decision%20in%20{month}&limit_per_type=10") or {}).get("events", [])
        pe = None
        for h in hits:
            if h.get("slug", "").startswith(f"fed-decision-in-{month}") and not h.get("closed") and (h.get("endDate") or "")[:7] == d.strftime("%Y-%m"):
                pe = (req(f"{GAMMA}/events?slug={h['slug']}") or [None])[0]; break
        if not pe:
            continue
        pm = {m["groupItemTitle"]: m for m in pe["markets"]}
        for code, label in FED_MAP.items():
            if code in ms and label in pm:
                k, p = ms[code], pm[label]; toks = json.loads(p["clobTokenIds"])
                pairs.append(dict(family="fed", group=f"FOMC {d:%b %Y}", label=label, k_ticker=k["ticker"], p_slug=p["slug"],
                                  yes_tok=toks[0], no_tok=toks[1], pfee=p.get("feeSchedule") if p.get("feesEnabled") else None,
                                  k_rules=k.get("rules_primary", "") + " " + k.get("rules_secondary", ""), p_rules=pe.get("description", ""),
                                  close=close, p_end=p.get("endDate"), k_market_title=k.get("title"), k_sub=k.get("yes_sub_title"), k_expected=k.get("expected_expiration_time"), k_latest=k.get("latest_expiration_time"), k_close_early=k.get("can_close_early"), k_early_cond=k.get("early_close_condition"), p_fee_type=p.get("feeType"), p_volume=float(p.get("volume") or 0), k_volume=float(k.get("volume_fp") or 0)))
    return pairs


def crypto_pairs(now_et):
    pairs = []
    for day in (now_et.date(), now_et.date() + timedelta(days=1)):
        ev = f"{day.year % 100:02d}{MON[day.month - 1]}{day.day:02d}12"
        for c, (slug, ks, _, _) in COINS.items():
            pe = (req(f"{GAMMA}/events?slug={slug}-above-on-{MONL[day.month - 1]}-{day.day}-{day.year}") or [None])
            pe = pe[0] if pe else None
            km = (req(f"{KAPI}/markets?event_ticker={ks}-{ev}&limit=1000") or {}).get("markets", [])
            if not pe or not km:
                continue
            live = [m for m in km if m.get("status") == "active"]
            for p in pe["markets"]:
                if p.get("closed"):
                    continue
                K = float(p["groupItemTitle"].replace(",", "")); toks = json.loads(p["clobTokenIds"])
                cand = [m for m in km if m.get("floor_strike") is not None and abs(float(m["floor_strike"]) - K) <= max(0.02, K * 1e-6)
                        or (m.get("floor_strike") is not None and abs(float(m["floor_strike"]) - (K - 0.01)) < 1e-6)]
                if not cand:
                    continue
                k = cand[0]
                pairs.append(dict(family="crypto", group=f"{c} above, {day:%b %d} 12:00 ET", coin=c, label=f"{c} > " + (f"{K:,.0f}" if K >= 100 else f"{K:g}"), strike=K,
                                  k_ticker=k["ticker"], k_status=k.get("status"), k_open=k.get("open_time"), p_slug=p["slug"],
                                  yes_tok=toks[0], no_tok=toks[1], pfee=p.get("feeSchedule") if p.get("feesEnabled") else None,
                                  k_rules=k.get("rules_primary", "") + "\n\n" + k.get("rules_secondary", ""), p_rules=pe.get("description", ""), close=k.get("close_time"), p_end=p.get("endDate"), k_market_title=k.get("title"), k_expected=k.get("expected_expiration_time"), k_latest=k.get("latest_expiration_time"), p_fee_type=p.get("feeType"),
                                  tradable_now=k.get("status") == "active", live_rungs=len(live)))
        if pairs:
            break
    return pairs


# ---------- basis risk ----------
def crypto_basis(days=60):
    """Noon-ET settlement basis: Polymarket = Binance <COIN>USDT 1-min candle closing 12:00 ET; Kalshi = CF Benchmarks RTI
    60-second average before 12:00 ET. RTI is not free, so it is proxied by the Coinbase <COIN>-USD 11:59 candle (open+close)/2.
    Returns per coin the distribution of (Binance - proxy) in basis points."""
    out = {}
    today = datetime.now(ET).date()
    for c, (_, _, bsym, cb) in COINS.items():
        diffs = []
        for k in range(1, days + 1):
            d = today - timedelta(days=k); t = datetime(d.year, d.month, d.day, 11, 59, tzinfo=ET).astimezone(timezone.utc)
            ms = int(t.timestamp() * 1000)
            b = req(f"https://data-api.binance.vision/api/v3/klines?symbol={bsym}&interval=1m&startTime={ms}&limit=1")
            cbk = req(f"https://api.exchange.coinbase.com/products/{cb}/candles?granularity=60&start={t:%Y-%m-%dT%H:%M:%SZ}&end={(t + timedelta(minutes=1)):%Y-%m-%dT%H:%M:%SZ}")
            if b and cbk:
                row = [x for x in cbk if x[0] == int(t.timestamp())]
                if row:
                    px = (row[0][3] + row[0][4]) / 2; diffs.append((float(b[0][4]) - px) / px * 1e4)
            time.sleep(0.15)
        if diffs:
            s = sorted(diffs); a = sorted(abs(x) for x in diffs)
            out[c] = dict(n=len(s), median_bp=s[len(s) // 2], p05_bp=s[int(0.05 * (len(s) - 1))], p95_bp=s[int(0.95 * (len(s) - 1))],
                          abs_p95_bp=a[int(0.95 * (len(a) - 1))], abs_max_bp=a[-1], series=[round(x, 2) for x in diffs])
    return out


RULES = {
    "fed": dict(grade="Low", items=[
        ("Event", "Size of the change at the FOMC meeting", "Size of the change at the FOMC meeting", "same"),
        ("Source", "FOMC statement (federalreserve.gov)", "FOMC statement (federalreserve.gov)", "same"),
        ("Measured as", "Change in the target range at the meeting", "Change in the range's upper bound vs. the level before the meeting", "minor"),
        ("Odd-size move (e.g. 12.5 bp)", "Not stated; outcome brackets are exact", "Rounded up to the nearest 25 bp bracket", "differs"),
        ("Meeting cancelled / no statement", "'Fed maintains rate' resolves YES", "'No change' if no statement by the next meeting's end date", "minor"),
        ("Settlement currency", "USD (CFTC-regulated exchange)", "USDC on Polygon (international venue)", "differs"),
        ("Who can trade", "US persons", "International venue is not open to US persons", "differs")]),
    "crypto": dict(grade="Medium", items=[
        ("Event", "Price above strike at 12:00 ET", "Price above strike at 12:00 ET", "same"),
        ("Price source", "CF Benchmarks Real-Time Index (USD, multi-exchange)", "Binance <COIN>/USDT", "differs"),
        ("Calculation", "Average of the 60 seconds before 12:00 ET", "Close of the 1-minute candle ending 12:00 ET", "differs"),
        ("Quote currency", "US dollar", "Tether (USDT)", "differs"),
        ("Strike convention", "Floor strike K - 0.01 (\"above\" = strictly greater)", "\"Above K\"", "minor"),
        ("Settlement currency", "USD (CFTC-regulated exchange)", "USDC on Polygon (international venue)", "differs"),
        ("Who can trade", "US persons", "International venue is not open to US persons", "differs")]),
}


def main():
    os.makedirs(OUT, exist_ok=True)
    now = datetime.now(ET)
    pairs = fed_pairs() + crypto_pairs(now)
    books = poly_books(sorted({t for p in pairs for t in (p["yes_tok"], p["no_tok"])}))
    rows = []
    for p in pairs:
        kx = kalshi_ladders(p["k_ticker"]); time.sleep(0.15)
        pm = poly_ladders(p["yes_tok"], p["no_tok"], books); pf = pfee_fn(p["pfee"])
        km, ks = mid(*kx); pmm, ps = mid(*pm)
        r = {k: v for k, v in p.items() if k not in ("k_rules", "p_rules", "yes_tok", "no_tok")}
        r.update(k_mid=km, k_spread=ks, p_mid=pmm, p_spread=ps, fair=fair(km, ks, pmm, ps),
                 mid_gap=None if km is None or pmm is None else km - pmm,
                 k_depth_top=dict(yes=touch(kx[0]), no=touch(kx[1])), p_depth_top=dict(yes=touch(pm[0]), no=touch(pm[1])),
                 k_depth5=sum(q * pr for pr, q in kx[0][:5]) + sum(q * pr for pr, q in kx[1][:5]),
                 p_depth5=sum(q * pr for pr, q in pm[0][:5]) + sum(q * pr for pr, q in pm[1][:5]),
                 exec=evaluate(kx, pm, pf), pfee_rate=(p["pfee"] or {}).get("rate", 0))
        rows.append(r)
    rules_text = {}
    for p in pairs:
        rules_text.setdefault(p["family"], dict(kalshi=p["k_rules"][:900], polymarket=p["p_rules"][:1400], k_example=p["k_ticker"], p_example=p["p_slug"]))
    snap = dict(generated=now.isoformat(timespec="seconds"), pairs=rows, rules=RULES, rules_text=rules_text,
                basis=crypto_basis() if any(r["family"] == "crypto" for r in rows) else {},
                calibration=json.load(open(os.path.join(LAB, "reports/c231/summary.json"))), sizes=SIZES, kalshi_fee=KFEE)
    json.dump(snap, open(os.path.join(OUT, "snapshot.json"), "w"), indent=1, default=float)
    print(f"{now:%Y-%m-%d %H:%M} ET pairs {len(rows)} ({sum(r['family'] == 'fed' for r in rows)} fed, {sum(r['family'] == 'crypto' for r in rows)} crypto)")
    for r in rows:
        best = max(((n, v["touch_edge"]) for n, v in r["exec"].items() if v["touch_edge"] is not None), key=lambda x: x[1], default=(None, None))
        print(f"  {r['group']:28s} {r['label']:22s} K {r['k_mid']} P {r['p_mid']} gap {r['mid_gap']} best touch edge {best[1]} via {best[0]}")


if __name__ == "__main__":
    main()
