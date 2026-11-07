"""One-off pre-Monday check that the plain "day" market orders the funds now send would be accepted by Alpaca PAPER.
READ-ONLY: only GET requests, never places or cancels an order. Never prints keys (only account status fields).
Checks, per account: account active and not blocked, shorting enabled, no stale open orders that could clash
(Alpaca rejects an order when an opposite-side order is open in the same symbol), each symbol's asset flags
(active, tradable, marginable; shortable and easy_to_borrow for IEF and BILI, which can be sold short), a live
price, and buying power against the largest gross book each fund can ask for. Exit code 1 if anything fails."""
import os, json, urllib.request, urllib.error
from datetime import date, timedelta
B = "https://paper-api.alpaca.markets"; D = "https://data.alpaca.markets"
def keys(p): return dict(l.strip().split("=", 1) for l in open(os.path.expanduser(p)) if "=" in l)
def get(kv, url):
    req = urllib.request.Request(url, headers={"APCA-API-KEY-ID": kv["APCA_API_KEY_ID"], "APCA-API-SECRET-KEY": kv["APCA_API_SECRET_KEY"]})
    try: return json.loads(urllib.request.urlopen(req, timeout=30).read())
    except urllib.error.HTTPError as e: return {"error": e.code, "body": e.read().decode()[:150]}
fails, out = [], []
def check(ok, msg):
    out.append(("PASS " if ok else "FAIL ") + msg)
    if not ok: fails.append(msg)
# account: (key file, symbols it trades, symbols it may short, max gross book as a multiple of equity, extra $ notional)
ACCTS = [("bond fund + BILI (APACKEYID)", "~/.alpaca_paper", ["IEF", "TLT", "VCIT", "BILI"], ["IEF", "BILI"], 0.30 + 0.30 + 0.20, 100000),
         ("portable alpha (APACKEYID2)", "~/.alpaca_paper2", ["SPY", "IEF", "TLT"], [], 1.00 + 0.50 + 0.225, 0)]
ids = []
for name, f, syms, shorts, gross, extra in ACCTS:
    kv = keys(f); out.append(f"\n== {name}")
    a = get(kv, B + "/v2/account")
    if "error" in a: check(False, f"account API {a}"); continue
    ids.append(a["id"])
    eq, bp = float(a["equity"]), float(a["buying_power"])
    check(a["status"] == "ACTIVE", f"account status {a['status']}")
    check(not a.get("trading_blocked") and not a.get("account_blocked") and not a.get("trade_suspended_by_user"), "not blocked or suspended")
    if shorts: check(bool(a.get("shorting_enabled")), f"shorting enabled ({a.get('shorting_enabled')})")
    check(float(a.get("multiplier", 1)) >= 2 or gross * eq + extra <= bp, f"margin multiplier {a.get('multiplier')}")
    need = gross * eq + extra
    check(bp >= need, f"buying power ${bp:,.0f} vs largest gross book ${need:,.0f} (equity ${eq:,.0f} x {gross:.3f}{' + $100k BILI' if extra else ''})")
    check(eq >= 25000, f"equity ${eq:,.0f} above the $25k pattern-day-trader floor")
    op = get(kv, B + "/v2/orders?status=open&limit=100")
    check(isinstance(op, list) and not op, f"no open orders left over ({len(op) if isinstance(op, list) else op})")
    for s in syms:
        x = get(kv, B + f"/v2/assets/{s}")
        if "error" in x: check(False, f"{s} asset lookup {x}"); continue
        check(x["status"] == "active" and x["tradable"], f"{s} active and tradable on {x['exchange']}")
        check(bool(x.get("marginable")), f"{s} marginable")
        if s in shorts: check(bool(x.get("shortable")) and bool(x.get("easy_to_borrow")), f"{s} shortable {x.get('shortable')}, easy_to_borrow {x.get('easy_to_borrow')}")
        q = get(kv, D + f"/v2/stocks/{s}/trades/latest?feed=iex")
        p = float(q.get("trade", {}).get("p", 0)) if isinstance(q, dict) else 0
        check(p > 0, f"{s} latest IEX price {p}")
    pos = get(kv, B + "/v2/positions")
    out.append("   positions now: " + (", ".join(f"{p['symbol']} {p['qty']}" for p in pos) if isinstance(pos, list) and pos else "none"))
    t = date.today(); cal = get(kv, B + f"/v2/calendar?start={t}&end={t + timedelta(days=7)}")
    if isinstance(cal, list) and cal: out.append(f"   next sessions: " + ", ".join(f"{c['date']} {c['open']}-{c['close']}" for c in cal[:3]))
check(len(ids) == 2 and ids[0] != ids[1], "the two key pairs are two different accounts")
out.append("\nOrder form both funds now send: {type: market, time_in_force: day}, whole-share qty. Alpaca accepts these during "
           "regular hours (fills at once) and before the open (queued, fills at the 09:30 open). Nothing was sent by this check.")
out.append(f"\nRESULT: {'ALL PASS' if not fails else str(len(fails)) + ' FAIL(S)'}")
print("\n".join(out)); raise SystemExit(1 if fails else 0)
