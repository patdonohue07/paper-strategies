"""C269F scorer: closed paper positions -> per rule / niche vs control / month; mean P&L, t clustered by entry day. Writes <state>/scoreboard.md."""
import json, math, os, sys
from datetime import datetime, timezone
STATE = sys.argv[1] if len(sys.argv) > 1 else "state"


def tstat(x, g):
    n = len(x)
    if n < 3:
        return 0.0
    m = sum(x) / n; cl = {}
    for a, k in zip(x, g):
        cl[k] = cl.get(k, 0.0) + (a - m)
    se = math.sqrt(sum(v * v for v in cl.values())) / n
    return m / se if se > 0 else 0.0


def main():
    p = os.path.join(STATE, "closed.jsonl"); C = [json.loads(l) for l in open(p)] if os.path.exists(p) else []
    rows = ["# C269F forward paper test — scoreboard (" + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC") + ")", "",
            f"Closed positions: {len(C)}", "", "| group | n | mean P&L | t (by entry day) | stress mean | months (n, mean) |", "|---|---|---|---|---|---|"]
    groups = {}
    for c in C:
        grp = f"{c['rule']} {'xyz control' if c['control'] else 'niche'}"; groups.setdefault(grp, []).append(c)
    for k in sorted(groups):
        v = groups[k]; x = [c["pnl"] for c in v]; d = [datetime.fromtimestamp(c["entry_t"], timezone.utc).strftime("%Y-%m-%d") for c in v]
        bym = {}
        for c, dd in zip(v, d):
            bym.setdefault(dd[:7], []).append(c["pnl"])
        rows.append(f"| {k} | {len(v)} | {100 * sum(x) / len(x):+.3f}% | {tstat(x, d):.2f} | {100 * sum(c['pnl_stress'] for c in v) / len(v):+.3f}% | "
                    + ", ".join(f"{m}: {len(a)}, {100 * sum(a) / len(a):+.2f}%" for m, a in sorted(bym.items())) + " |")
    open(os.path.join(STATE, "scoreboard.md"), "w").write("\n".join(rows) + "\n"); print("\n".join(rows))


if __name__ == "__main__":
    main()
