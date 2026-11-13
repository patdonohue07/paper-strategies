"""Forward test of the Binance perp breakdown short + top-trader filter (claude/forward-test-perp-short.md).
Paper only. Re-runs the frozen rule from 2026-10-01 over cached public archive data every day. Standard library only."""
import csv, io, json, os, re, zipfile, urllib.request, urllib.parse, time, math, random, hashlib
from datetime import datetime, timezone, timedelta, date
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__)); MR = os.path.join(HERE, "..", "meme_research")
BASE = "https://data.binance.vision/"; S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
START = datetime(2026, 10, 1, tzinfo=timezone.utc); START_MS = int(START.timestamp() * 1000)
HD = os.path.join(HERE, "hourly"); MD = os.path.join(HERE, "metrics"); os.makedirs(HD, exist_ok=True); os.makedirs(MD, exist_ok=True)
LOG = open(os.path.join(HERE, "fwd_log.txt"), "a")
def log(*a):
    s = datetime.now().strftime("%Y-%m-%d %H:%M ") + " ".join(str(x) for x in a); print(s, flush=True); LOG.write(s + "\n"); LOG.flush()
def fetch(url):
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"user-agent": "forward-test"}), timeout=60) as r: return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            time.sleep(3)
        except Exception as e:
            if "CERTIFICATE_VERIFY_FAILED" in str(e): raise SystemExit("SSL error: run open '/Applications/Python 3*/Install Certificates.command' then rerun")
            time.sleep(3)
    return None
def unzip_rows(z):
    with zipfile.ZipFile(io.BytesIO(z)) as zf: txt = zf.read(zf.namelist()[0]).decode()
    rows = list(csv.reader(io.StringIO(txt)))
    return [r for r in rows if r and r[0][:1].isdigit()] , rows
MEMES = set(json.load(open(os.path.join(MR, "binance", "final_universe.json"))))
ALTS = set(json.load(open(os.path.join(MR, "binance_alt", "universe.json"))))
def listing():
    syms, marker = set(), ""
    while True:
        x = fetch(S3 + "?" + urllib.parse.urlencode(dict(delimiter="/", prefix="data/futures/um/daily/klines/", marker=marker)))
        if not x: break
        x = x.decode(); ps = re.findall(r"<Prefix>data/futures/um/daily/klines/([^/<]+)/</Prefix>", x); syms |= set(ps)
        if "<IsTruncated>true</IsTruncated>" not in x or not ps: break
        marker = "data/futures/um/daily/klines/%s/" % ps[-1]
    return syms
yday = (datetime.now(timezone.utc) - timedelta(days=1)).date()
days = [START.date() + timedelta(days=i) for i in range((yday - START.date()).days + 1)]
# ---- universe
classes = {s: "meme" for s in MEMES}; classes.update({s: "alt" for s in ALTS})
try:
    allsyms = listing()
    for s in allsyms:
        if s.endswith("USDT") and s not in classes: classes[s] = "unclassified"
except Exception as e: log("listing failed", e)
# ---- hourly data cache: hourly/SYM.json = {"rows": {open_ms: [o,h,l,c,qv]}, "days": {date: "ok"|"404"|...}}
def seed(sym):
    rows = {}
    for d in ("binance", "binance_alt"):
        for mo in ("2026-08", "2026-09"):
            f = os.path.join(MR, d, "1h", sym, "%s-1h-%s.csv" % (sym, mo))
            if os.path.exists(f):
                for r in csv.reader(open(f)):
                    if r and r[0][:1].isdigit(): rows[int(r[0])] = [float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[7])]
    return rows
def update(sym):
    p = os.path.join(HD, sym + ".json")
    st = json.load(open(p)) if os.path.exists(p) else {"rows": {}, "days": {}}
    if not st.get("seed_aug") and classes[sym] != "unclassified":
        st["rows"].update({str(k): v for k, v in seed(sym).items()}); st["seed_aug"] = 1
    need = [d for d in days if st["days"].get(str(d)) != "ok" and not (st["days"].get(str(d), "").startswith("404") and (yday - d).days > 3)]
    if classes[sym] == "unclassified" and not st["rows"]:   # only follow new listings that trade now
        need = [d for d in days if d >= START.date() - timedelta(days=0)]
        if fetch(BASE + "data/futures/um/daily/klines/%s/1h/%s-1h-%s.zip" % (sym, sym, yday)) is None: return sym, 0
    n = 0
    for d in need:
        z = fetch(BASE + "data/futures/um/daily/klines/%s/1h/%s-1h-%s.zip" % (sym, sym, d))
        if z is None: st["days"][str(d)] = "404"; continue
        rows, _ = unzip_rows(z)
        for r in rows: st["rows"][str(int(r[0]))] = [float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[7])]
        st["days"][str(d)] = "ok"; n += 1
    json.dump(st, open(p, "w")); return sym, n
syms = sorted(classes)
log("run start: %d symbols (%d meme, %d alt, %d unclassified), days %s to %s" % (len(syms), sum(v == "meme" for v in classes.values()), sum(v == "alt" for v in classes.values()), sum(v == "unclassified" for v in classes.values()), days[0], days[-1]))
with ThreadPoolExecutor(12) as ex: got = sum(n for _, n in ex.map(update, syms))
log("downloaded %d new symbol-days" % got)
# ---- metrics (top-trader account ratio)
def f2(sym, entry_ms):
    t = datetime.fromtimestamp(entry_ms / 1000, timezone.utc); vals = []
    for d in (t.date() - timedelta(days=1), t.date()):
        p = os.path.join(MD, "%s_%s.csv" % (sym, d))
        if not os.path.exists(p):
            z = fetch(BASE + "data/futures/um/daily/metrics/%s/%s-metrics-%s.zip" % (sym, sym, d))
            if z is None:
                if (yday - d).days > 3: open(p, "w").close()
                continue
            open(p, "w").write("\n".join(",".join(r) for r in unzip_rows(z)[1]))
        rd = list(csv.reader(open(p)))
        if not rd: continue
        h = rd[0]; i = h.index("create_time") if "create_time" in h else 0; j = h.index("count_toptrader_long_short_ratio") if "count_toptrader_long_short_ratio" in h else None
        if j is None: continue
        for r in rd[1:]:
            try: ts = datetime.strptime(r[i][:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except Exception: continue
            if ts <= t and r[j] not in ("", "nan"): vals.append((ts, float(r[j])))
    return max(vals)[1] if vals else None
# ---- jump-model EV (C15, q = 0.63), pure python
def jump_ev(rets, seed, q=0.63, N=1000):
    w = sorted(rets); med = w[len(w) // 2]; mad = sorted(abs(x - med) for x in rets)[len(rets) // 2]
    sd = 1.4826 * mad; thr = max(4 * sd, 0.03); J = [abs(x) for x in rets if abs(x) > thr]
    sig = max(sd * math.sqrt(24), 0.005); lam = max(len(J) / (len(rets) / 24), 0.05); jsz = max(sum(J) / len(J) if J else 0, 3 * sd)
    U, D = math.log(1.6), math.log(0.4); rnd = random.Random(seed); tot = 0.0
    for _ in range(N):
        X = 0.0; pay = None
        for _d in range(60):
            Xd = X + rnd.gauss(0, sig)
            pu = 1.0 if Xd >= U else math.exp(-2 * (U - X) * (U - Xd) / sig ** 2)
            pdn = 1.0 if Xd <= D else math.exp(-2 * (X - D) * (Xd - D) / sig ** 2)
            k, L, p = 0, math.exp(-lam), 1.0
            while True:
                p *= rnd.random()
                if p <= L: break
                k += 1
            Jn = sum((-1 if rnd.random() < q else 1) * rnd.expovariate(1 / jsz) for _ in range(min(k, 6)))
            X1 = Xd + Jn
            if rnd.random() < pu or X1 >= U: pay = -0.608; break
            if rnd.random() < pdn or X1 <= D: pay = 0.6; break
            X = X1
        tot += pay if pay is not None else 1 - math.exp(X)
    return tot / N - 0.004
# ---- replay the frozen rule
cache_p = os.path.join(HERE, "signal_cache.json"); cache = json.load(open(cache_p)) if os.path.exists(cache_p) else {}
out = []
for sym in syms:
    p = os.path.join(HD, sym + ".json")
    if not os.path.exists(p): continue
    R = json.load(open(p))["rows"]
    if not R: continue
    T = sorted(int(k) for k in R); O = [R[str(t)][0] for t in T]; H = [R[str(t)][1] for t in T]; L = [R[str(t)][2] for t in T]; C = [R[str(t)][3] for t in T]; Q = [R[str(t)][4] for t in T]
    n = len(T); i = 0; free_from = 0
    while i < n:
        if i < free_from or i < 24: i += 1; continue
        hi = max(C[max(0, i - 719): i + 1]); qv = sum(Q[i - 23: i + 1])
        if not (C[i] <= 0.6 * hi and qv >= 1e6): i += 1; continue
        pe = C[i]; status, xr, j = "open", None, None
        warm = T[i] < START_MS   # September warm-up: carry the position/cooldown state into October, do not log
        for j in range(i + 1, min(i + 1440, n - 1) + 1):
            if H[j] / pe >= 1.6: status, xr = "stop", max(O[j] / pe, 1.6) * 1.005; break
            if L[j] / pe <= 0.4: status, xr = "tp", min(O[j] / pe, 0.4); break
        else:
            j = min(i + 1440, n - 1)
            if j == i + 1440: status, xr = "time", C[j] / pe
        if warm:
            free_from = (j if xr is not None else n) + 7 * 24; i = free_from; continue
        mark = C[n - 1] / pe if n - 1 > i else 1.0
        net = -(xr - 1) - 0.004 if xr is not None else None
        key = "%s_%d" % (sym, T[i])
        c = cache.get(key, {})
        if c.get("f2") is None: c["f2"] = f2(sym, T[i])
        if "ev" not in c and i >= 168:
            rets = [math.log(C[k] / C[k - 1]) for k in range(i - 167, i + 1) if C[k - 1] > 0]
            c["ev"] = round(jump_ev(rets, int(hashlib.md5(key.encode()).hexdigest()[:8], 16)), 4) if len(rets) > 48 else None
        cache[key] = c
        kept = None if c["f2"] is None else c["f2"] > 2.238
        out.append(dict(sym=sym, cls=classes[sym], entry_utc=datetime.fromtimestamp(T[i] / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M"), entry_px=pe,
                        top_trader_ratio=c["f2"], kept=kept, jump_ev=c.get("ev"), status=status,
                        exit_utc=datetime.fromtimestamp(T[j] / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M") if xr is not None else "",
                        net=None if net is None else round(net, 4), open_mark=None if xr is not None else round(-(mark - 1), 4)))
        free_from = (j if xr is not None else n) + 7 * 24; i = free_from
json.dump(cache, open(cache_p, "w"))
F = ["sym", "cls", "entry_utc", "entry_px", "top_trader_ratio", "kept", "jump_ev", "status", "exit_utc", "net", "open_mark"]
with open(os.path.join(HERE, "trades.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, F); w.writeheader(); w.writerows(sorted(out, key=lambda r: r["entry_utc"]))
def stats(rs):
    x = [r["net"] for r in rs]
    if not x: return "n 0"
    m = sum(x) / len(x); g = {}
    for r in rs:
        wk = datetime.strptime(r["entry_utc"], "%Y-%m-%d %H:%M").isocalendar()[:2]; g[wk] = g.get(wk, 0) + r["net"] - m
    se = math.sqrt(sum(v * v for v in g.values())) / len(x); return "n %d, mean %+.2f%%, t %s, wins %d%%" % (len(x), m * 100, "%.2f" % (m / se) if se > 0 and len(g) > 1 else "n/a", round(100 * sum(v > 0 for v in x) / len(x)))
main = [r for r in out if r["cls"] in ("meme", "alt")]
try: EQ = set(json.load(open(os.path.join(HERE, "equity_perps.json")))["equity"])
except Exception: EQ = set()
def omark(rs):
    x = [r["open_mark"] or 0 for r in rs]
    return "n 0" if not x else "n %d, mean mark %+.1f%%" % (len(x), 100 * sum(x) / len(x))
cl = [r for r in main if r["net"] is not None]
lines = ["Forward test, perp breakdown short (frozen rule, paper only). Updated %s. Data through %s UTC." % (datetime.now().strftime("%Y-%m-%d %H:%M"), yday),
         "Signals since 2026-10-01: %d (memes %d, alts %d); open %d; top-trader ratio still pending %d" % (len(main), sum(r["cls"] == "meme" for r in main), sum(r["cls"] == "alt" for r in main), sum(r["net"] is None for r in main), sum(r["kept"] is None for r in main)),
         "", "CLOSED trades (returns before funding):",
         "  KEPT (ratio > 2.238):     " + stats([r for r in cl if r["kept"] is True]),
         "  dropped:                  " + stats([r for r in cl if r["kept"] is False]),
         "  kept + jump EV > 0:       " + stats([r for r in cl if r["kept"] is True and (r["jump_ev"] or -1) > 0]),
         "  memes kept:               " + stats([r for r in cl if r["kept"] is True and r["cls"] == "meme"]),
         "  alts kept:                " + stats([r for r in cl if r["kept"] is True and r["cls"] == "alt"]),
         "", "Verdict when KEPT reaches 100 closed trades: mean > 0 with t > 2.0 and kept > dropped. Until then nothing is decided.",
         "", "REPORT-ONLY SPLIT (added 2026-11-03; does not change the verdict). Stock/ETF perps classified by price in equity_perps.json:",
         "  KEPT crypto only:         " + stats([r for r in cl if r["kept"] is True and r["sym"] not in EQ]),
         "  dropped crypto only:      " + stats([r for r in cl if r["kept"] is False and r["sym"] not in EQ]),
         "  KEPT stock/ETF perps:     " + stats([r for r in cl if r["kept"] is True and r["sym"] in EQ]),
         "  open kept marks, crypto:  " + omark([r for r in main if r["net"] is None and r["kept"] and r["sym"] not in EQ]),
         "  open kept marks, stocks:  " + omark([r for r in main if r["net"] is None and r["kept"] and r["sym"] in EQ]),
         "", "OPEN kept positions (mark = short P&L at last close):"]
for r in [r for r in main if r["net"] is None and r["kept"]]: lines.append("  %-16s %s entry %.6g  mark %+.1f%%%s" % (r["sym"], r["entry_utc"], r["entry_px"], (r["open_mark"] or 0) * 100, "  [stock/ETF]" if r["sym"] in EQ else ""))
un = [r for r in out if r["cls"] == "unclassified"]
lines += ["", "Unclassified new listings (information only): %d signals" % len(un)]
open(os.path.join(HERE, "summary.txt"), "w").write("\n".join(lines) + "\n")
log("done: %d signals (%d in frozen universe), summary.txt written" % (len(out), len(main)))
