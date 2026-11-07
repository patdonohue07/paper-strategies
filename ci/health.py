"""Daily health report: one markdown file per day on the state-health branch (health/YYYY-MM-DD.md, plus latest.md).
Sections: jobs that ran today and when (vs the scheduler's slots), orders and fills for both Alpaca PAPER accounts,
positions vs today's targets, each job's own summary line, and every error found.
Reads: Actions API (GITHUB_TOKEN), the state-* branches (fetched by the workflow), Alpaca paper API (read-only GETs).
Never prints keys. Standard library only (plus gh on the runner)."""
import os, sys, json, csv, io, subprocess, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone, date
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scheduler import JOBS, slots_on, REPO
ET = ZoneInfo("America/New_York"); OUT = sys.argv[1] if len(sys.argv) > 1 else "health"
now = datetime.now(ET); today = now.date(); T = str(today)
errors, L = [], []
def et(s): return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(ET) if s else None
def gh_api(path):
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if r.returncode: raise RuntimeError(r.stderr.strip()[:200])
    return json.loads(r.stdout)
def show(branch, path):
    r = subprocess.run(["git", "show", f"origin/{branch}:{path}"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None
def rows(branch, path, live_only=True):
    s = show(branch, path)
    if not s: return []
    return [r for r in csv.DictReader(io.StringIO(s)) if (r.get("ts") or r.get("date") or "").startswith(T) and (not live_only or r.get("mode") == "LIVE-PAPER")]

L += [f"# Paper strategies health report {T} ({now:%a %H:%M} ET)", ""]

# ---------------- 1. jobs ----------------
runs, page = [], 1
start = datetime(today.year, today.month, today.day, tzinfo=ET).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
try:
    while True:
        d = gh_api(f"repos/{REPO}/actions/runs?created=%3E%3D{start}&per_page=100&page={page}")
        runs += d.get("workflow_runs", []); page += 1
        if len(d.get("workflow_runs", [])) < 100 or page > 10: break
except Exception as e: errors.append(f"Actions API: {e}")
byname = {}
for r in runs: byname.setdefault(os.path.basename(r["path"]), []).append(r)
L += ["## 1. Jobs today", "", "| Workflow | Runs | First | Last | Failed | Slots on time / due | Late or missed slots |", "|---|---|---|---|---|---|---|"]
for job in JOBS + [("scheduler.yml", None, (), {}, 0)]:
    wf, grace = job[0], job[4]; rs = sorted(byname.get(wf, []), key=lambda r: r["created_at"])
    fails = [r for r in rs if r.get("conclusion") == "failure"]
    for r in fails: errors.append(f"{wf} run failed at {et(r['created_at']):%H:%M} ET: {r['html_url']}")
    due = [s for s in slots_on(today, job) if s + timedelta(minutes=grace) <= now] if job[1] else []
    disp = [et(r["created_at"]) for r in rs if r["event"] == "workflow_dispatch"]
    ontime, bad = 0, []
    for s in due:
        hit = [t for t in disp if s - timedelta(minutes=1) <= t <= s + timedelta(minutes=grace)]
        if hit and (hit[0] - s) <= timedelta(minutes=3): ontime += 1
        elif hit: bad.append(f"{s:%H:%M} late {int((hit[0] - s).total_seconds() // 60)}m")
        else: bad.append(f"{s:%H:%M} missed")
    if bad and wf != "kalshi-maker.yml": errors.append(f"{wf}: " + ", ".join(bad))
    elif len(bad) > 2: errors.append(f"kalshi-maker: {len(bad)} of {len(due)} slots late or missed")
    shown = ", ".join(bad[:6]) + (f" (+{len(bad) - 6} more)" if len(bad) > 6 else "")
    L.append(f"| {wf.replace('.yml', '')} | {len(rs)} | {et(rs[0]['created_at']):%H:%M} | {et(rs[-1]['created_at']):%H:%M} | {len(fails)} | {ontime}/{len(due)} | {shown} |" if rs else
             f"| {wf.replace('.yml', '')} | 0 | | | | 0/{len(due)} | {shown} |")
L.append("")

# ---------------- 2. Alpaca accounts ----------------
def keys(p):
    p = os.path.expanduser(p); return dict(l.strip().split("=", 1) for l in open(p) if "=" in l) if os.path.exists(p) else None
def alp(kv, path):
    req = urllib.request.Request("https://paper-api.alpaca.markets" + path, headers={"APCA-API-KEY-ID": kv["APCA_API_KEY_ID"], "APCA-API-SECRET-KEY": kv["APCA_API_SECRET_KEY"]})
    try: return json.loads(urllib.request.urlopen(req, timeout=30).read())
    except urllib.error.HTTPError as e: return {"error": e.code, "body": e.read().decode()[:150]}
    except Exception as e: return {"error": str(e)[:150]}
live = {"fund": rows("state-funds", "fund_log.csv"), "pa": rows("state-funds", "pa_log.csv"),
        "bili_in": rows("state-funds", "bili_entries.csv"), "bili_out": rows("state-funds", "bili_exits.csv")}
cal_today = None
for name, f, targ_rows in (("Bond fund + BILI (APACKEYID)", "~/.alpaca_paper", live["fund"]), ("Portable alpha (APACKEYID2)", "~/.alpaca_paper2", live["pa"])):
    L += [f"## 2. {name}", ""]; kv = keys(f)
    if not kv: errors.append(f"{name}: no key file on the runner"); L += ["no keys on the runner", ""]; continue
    a = alp(kv, "/v2/account")
    if "error" in a: errors.append(f"{name}: account API {a}"); L += [f"account API error {a}", ""]; continue
    if cal_today is None:
        c = alp(kv, f"/v2/calendar?start={T}&end={T}"); cal_today = bool(isinstance(c, list) and c and c[0]["date"] == T)
    L.append(f"Status {a['status']}, equity ${float(a['equity']):,.0f} (prior close ${float(a['last_equity']):,.0f}, day {float(a['equity']) - float(a['last_equity']):+,.0f}), cash ${float(a['cash']):,.0f}, buying power ${float(a['buying_power']):,.0f}"
             + (", TRADING BLOCKED" if a.get("trading_blocked") or a.get("account_blocked") else ""))
    if a.get("trading_blocked") or a.get("account_blocked"): errors.append(f"{name}: account blocked")
    after = datetime(today.year, today.month, today.day, tzinfo=ET).isoformat()
    os_ = alp(kv, f"/v2/orders?status=all&after={urllib.request.quote(after)}&limit=100&direction=asc")
    L += ["", "Orders today:", ""]
    if isinstance(os_, list) and os_:
        L += ["| Submitted | Symbol | Side | Qty | Filled | Avg price | Type/TIF | Status | Filled at |", "|---|---|---|---|---|---|---|---|---|"]
        for o in os_:
            L.append(f"| {et(o['submitted_at']):%H:%M:%S} | {o['symbol']} | {o['side']} | {o['qty']} | {o['filled_qty']} | {o.get('filled_avg_price') or ''} | {o['type']}/{o['time_in_force']} | {o['status']} | {et(o['filled_at']):%H:%M:%S} |" if o.get("filled_at") else
                     f"| {et(o['submitted_at']):%H:%M:%S} | {o['symbol']} | {o['side']} | {o['qty']} | {o['filled_qty']} | | {o['type']}/{o['time_in_force']} | {o['status']} | |")
            if o["status"] in ("rejected", "expired", "canceled") or (o["status"] == "filled" and o["filled_qty"] != o["qty"]):
                errors.append(f"{name}: order {o['symbol']} {o['side']} {o['qty']} {o['status']} (filled {o['filled_qty']})")
            elif o["status"] not in ("filled",) and now.hour >= 16:
                errors.append(f"{name}: order {o['symbol']} {o['side']} {o['qty']} still {o['status']} after the close")
    elif isinstance(os_, dict): errors.append(f"{name}: orders API {os_}")
    else: L.append("none")
    pos = alp(kv, "/v2/positions"); L += ["", "Positions:", ""]
    tg = {}
    if targ_rows:
        try: tg = json.loads(targ_rows[-1].get("targets") or "{}")
        except Exception: pass
    if isinstance(pos, list):
        L += ["| Symbol | Qty | Market value | % equity | Today's target $ | Unrealized P&L |", "|---|---|---|---|---|---|"]
        eq = float(a["equity"]) or 1
        held = {p["symbol"]: p for p in pos}
        for s in sorted(set(held) | {k for k, v in tg.items() if v}):
            p = held.get(s)
            mv = float(p["market_value"]) if p else 0.0
            L.append(f"| {s} | {p['qty'] if p else 0} | ${mv:,.0f} | {mv / eq:.1%} | {('$' + format(tg[s], ',.0f')) if s in tg else ''} | {('$' + format(float(p['unrealized_pl']), ',.0f')) if p else ''} |")
            if s in tg and abs(mv - tg[s]) > max(0.03 * eq, 5000) and cal_today and now.hour >= 16:
                errors.append(f"{name}: {s} held ${mv:,.0f} vs today's target ${tg[s]:,.0f}")
        if not held and not tg: L.append("| (cash only) | | | | | |")
    else: errors.append(f"{name}: positions API {pos}")
    L.append("")

# ---------------- 3. strategy logs ----------------
L += ["## 3. Strategy logs (today's live rows and each job's own summary)", ""]
if cal_today:
    for k, label in (("fund", "bond fund"), ("pa", "portable alpha")):
        if live[k]:
            r = live[k][-1]; L.append(f"- {label}: {r['ts'][11:19]} state {r['state']}, orders {r['orders']}")
            for o in json.loads(r.get("orders") or "[]"):
                if not (isinstance(o[2], str) and len(o[2]) == 36 and o[2].count("-") == 4): errors.append(f"{label}: order {o} did not get an order id")
        else: errors.append(f"{label}: no LIVE-PAPER row today (funds-close did not trade)")
    for k, label in (("bili_in", "BILI entry"), ("bili_out", "BILI exit")):
        if live[k]:
            r = live[k][-1]; L.append(f"- {label}: {r['ts'][11:19]} " + (f"signal {r.get('signal')}, gap {r.get('gap')}, order {r.get('order')}, {r.get('note')}" if k == "bili_in" else f"held {r.get('qty_held')}, order {r.get('order')}"))
            oid = str(r.get("order") or "")
            if oid not in ("", "none", "None") and not (len(oid) == 36 and oid.count("-") == 4): errors.append(f"{label}: order problem {oid}")
        else: errors.append(f"{label}: no LIVE-PAPER row today")
else: L.append("- not a US trading day: no fund or BILI rows expected")
for branch, path, label in (("state-kalshi", "reports/paper_maker_summary.txt", "Kalshi maker"), ("state-fwd", "summary.txt", "perp forward test"),
                            ("state-fut", "summary.txt", "futures shadow"), ("state-vix", "summary.txt", "VIX scoring")):
    s = show(branch, path)
    L.append(f"- {label}: " + (" / ".join(x.strip() for x in s.strip().splitlines()[:4]) if s else "no summary yet"))
s = show("state-hl", "logger_log.txt")
L.append(f"- Hyperliquid logger: last line `{s.strip().splitlines()[-1][:160]}`" if s else "- Hyperliquid logger: no log yet")
L.append("")

# ---------------- 4. errors ----------------
L += ["## 4. Errors and warnings", ""] + ([f"- {e}" for e in errors] if errors else ["- none"]) + [""]
L.insert(2, f"**{'ALL OK' if not errors else str(len(errors)) + ' problem(s), see section 4'}**\n")
os.makedirs(OUT, exist_ok=True)
txt = "\n".join(L) + "\n"
open(os.path.join(OUT, f"{T}.md"), "w").write(txt); open(os.path.join(OUT, "latest.md"), "w").write(txt)
print(txt)
