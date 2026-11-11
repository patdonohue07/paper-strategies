"""Scheduler for the paper jobs. GitHub's own cron is throttled on this repo (about 2 runs per 14 hours), so this
workflow stays alive for about 5h45m, starts each job at its exact ET time with `gh workflow run`, then starts its own
successor and exits. An hourly cron on scheduler.yml restarts the chain if it ever breaks.
Rules:
- Before starting a job it asks the Actions API whether that job already has a workflow_dispatch run since the slot
  time, so a handoff, a restart or a duplicate scheduler never starts the same slot twice.
- A slot that is missed (scheduler down) is still started up to GRACE minutes late, never later.
- If another scheduler run younger than HANDOFF_AGE is in progress with a lower run id, this one exits (one leader).
- Kill switch: create ci/SCHEDULER_OFF on main and the chain stops within a few minutes (or disable the workflow).
No secrets: uses only the workflow's GITHUB_TOKEN (as GH_TOKEN) for the Actions API."""
import os, sys, json, time, subprocess
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")
REPO = os.environ.get("GITHUB_REPOSITORY", "patdonohue07/paper-strategies")
SELF_ID = int(os.environ.get("GITHUB_RUN_ID", "0"))
LIFETIME = timedelta(minutes=float(os.environ.get("SCHED_MINUTES", "345")))   # 5h45m; GitHub's job limit is 6h
HANDOFF_AGE = LIFETIME - min(timedelta(minutes=5), LIFETIME / 10)   # an older scheduler is handing off, not a rival
TICK = 20   # seconds between checks
WEEKDAYS, ALL = (0, 1, 2, 3, 4), (0, 1, 2, 3, 4, 5, 6)
# (workflow file, ET times "HH:MM" or "*/N" or ":MM", days, inputs, grace minutes)
JOBS = [
    ("kalshi-maker.yml", "*/10", ALL, {}, 8),
    ("hl-logger.yml", ":07", ALL, {}, 20),
    ("doge-fv.yml", ":03", ALL, {}, 20),
    ("perp-forward-test.yml", ["10:37"], ALL, {}, 30),
    ("bili-entry.yml", ["08:40", "09:02"], WEEKDAYS, {"dry": "false"}, 15),
    ("vix-score.yml", ["08:50"], WEEKDAYS, {}, 30),
    ("funds.yml", ["15:15", "15:32"], WEEKDAYS, {"dry": "false"}, 15),
    ("opt-fwd.yml", ["15:40"], WEEKDAYS, {}, 15),
    ("ftmo-fwd.yml", ["16:20"], WEEKDAYS, {}, 60),
    ("health.yml", ["16:30"], WEEKDAYS, {}, 60),
    ("futures-shadow.yml", ["18:20"], WEEKDAYS, {}, 60),
]

def slots_on(day, job):
    """All slot datetimes (ET) of one job on one calendar day."""
    wf, spec, days, inputs, grace = job
    if day.weekday() not in days: return []
    base = datetime(day.year, day.month, day.day, tzinfo=ET)
    if spec == "*/10": return [base + timedelta(minutes=m) for m in range(0, 1440, 10)]
    if isinstance(spec, str) and spec.startswith(":"): return [base + timedelta(hours=h, minutes=int(spec[1:])) for h in range(24)]
    return [base.replace(hour=int(s[:2]), minute=int(s[3:])) for s in spec]

def log(msg): print(f"{datetime.now(ET):%Y-%m-%d %H:%M:%S} ET  {msg}", flush=True)

def gh(*args, tries=3):
    for k in range(tries):
        r = subprocess.run(["gh", *args], capture_output=True, text=True)
        if r.returncode == 0: return r.stdout
        err = (r.stderr or r.stdout).strip()[:200]; time.sleep(3 * (k + 1))
    raise RuntimeError(f"gh {' '.join(args[:3])}: {err}")

def api(path): return json.loads(gh("api", "-H", "Accept: application/vnd.github+json", path))

def dispatched_since(wf, t):
    """True if wf has any workflow_dispatch run created at or after t (minus 60 s for clock skew)."""
    since = (t - timedelta(seconds=60)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    d = api(f"repos/{REPO}/actions/workflows/{wf}/runs?event=workflow_dispatch&created=%3E%3D{since}&per_page=5")
    return d.get("total_count", 0) > 0

def dispatch(wf, inputs):
    args = ["workflow", "run", wf, "--repo", REPO, "--ref", "main"]
    for k, v in inputs.items(): args += ["-f", f"{k}={v}"]
    gh(*args)

def rivals():
    """Other in-progress or queued scheduler runs younger than HANDOFF_AGE."""
    out = []
    for status in ("in_progress", "queued"):
        for r in api(f"repos/{REPO}/actions/workflows/scheduler.yml/runs?status={status}&per_page=20").get("workflow_runs", []):
            if r["id"] == SELF_ID: continue
            started = datetime.fromisoformat((r.get("run_started_at") or r["created_at"]).replace("Z", "+00:00"))
            if datetime.now(timezone.utc) - started < HANDOFF_AGE: out.append(r)
    return out

def leader_elsewhere():
    """Exit rule: a younger-than-handoff rival with a lower run id is the leader. Queued rivals never lead."""
    try: rs = rivals()
    except Exception as e: log(f"rival check failed ({e}); carrying on"); return None
    lead = [r for r in rs if r["status"] == "in_progress" and r["id"] < SELF_ID]
    return lead[0] if lead else None

def kill_switch():
    r = subprocess.run(["gh", "api", f"repos/{REPO}/contents/ci/SCHEDULER_OFF?ref=main"], capture_output=True, text=True)
    return r.returncode == 0

def start_successor():
    for k in range(6):
        try:
            dispatch("scheduler.yml", {}); log("successor scheduler started"); return True
        except Exception as e: log(f"successor dispatch failed ({e}), retry"); time.sleep(10 * (k + 1))
    return False

def main():
    t0 = datetime.now(timezone.utc)
    log(f"scheduler run {SELF_ID} starting, lifetime {LIFETIME}")
    time.sleep(5)   # let a simultaneous rival register before the check
    lead = leader_elsewhere()
    if lead: log(f"another scheduler (run {lead['id']}) is already in charge; exiting"); return
    fired, last_rival_check = set(), time.time()
    while True:
        now = datetime.now(ET)
        if datetime.now(timezone.utc) - t0 >= LIFETIME:
            if kill_switch(): log("ci/SCHEDULER_OFF exists: not starting a successor"); return
            if not start_successor(): log("could not start successor; the hourly cron will restart the chain")
            return
        if time.time() - last_rival_check > 600:
            last_rival_check = time.time()
            if kill_switch(): log("ci/SCHEDULER_OFF exists: stopping"); return
            lead = leader_elsewhere()
            if lead: log(f"scheduler run {lead['id']} leads; exiting"); return
        for job in JOBS:
            wf, _, _, inputs, grace = job
            for day in (now.date() - timedelta(days=1), now.date()):
                for s in slots_on(day, job):
                    key = (wf, s.isoformat())
                    if key in fired or not (s <= now <= s + timedelta(minutes=grace)): continue
                    try:
                        if dispatched_since(wf, s): log(f"{wf} slot {s:%H:%M} already started; skip")
                        else:
                            dispatch(wf, inputs); late = (now - s).total_seconds() / 60
                            log(f"started {wf} for slot {s:%a %H:%M} ({late:.1f} min after slot){' inputs ' + json.dumps(inputs) if inputs else ''}")
                        fired.add(key)
                    except Exception as e: log(f"ERROR starting {wf} slot {s:%H:%M}: {e} (will retry)")
        time.sleep(TICK)

if __name__ == "__main__":
    main()
