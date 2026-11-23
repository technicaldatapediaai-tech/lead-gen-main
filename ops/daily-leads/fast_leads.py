"""Fast lead run (user-approved, 1 Nov 2026): contactable leads up to --target per workspace within --minutes.

Runs in parallel threads:
- free pass per workspace, candidates checked by Haiku without web search (~$0.001 per 15; approved);
- Claude API contact search: decision makers for signal companies with no contact (8 per call, ~$0.10-0.15), round-robin,
  until the hard --ai-cap (USD, all workspaces together) is reached;
- three Claude in Chrome scouts (Claude plan, no API credits), one per platform: LinkedIn (+ find_people), X, Reddit,
  bulk mode, each moving round-robin over the workspaces still short.
Every lead goes through the backend's lead rules (contactable, fit >= 65, unique; LinkedIn-only where set).

Usage: fast_leads.py --target 50 --minutes 120 --ai-cap 5
"""
import argparse
import datetime as dt
import os
import subprocess
import sys
import threading
import time

from daily_leads import ensure_backend
from leadnius import ACCOUNTS, HERE, ApiError, call, org_token, psql
import daily_leads

LOGS = os.path.join(HERE, "logs")
APPROVED = {"X-AI-Approved": "yes"}
lock = threading.Lock()


def log(msg):
    line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    with lock:
        print(line, flush=True)
        with open(os.path.join(LOGS, f"{dt.date.today()}-fast.log"), "a") as f:
            f.write(line + "\n")


def spent_since(start):
    utc = start.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return float(psql(f"select coalesce(sum(cost_usd), 0) usd from ai_usage where at >= '{utc:%Y-%m-%d %H:%M:%S}'")[0]["usd"])


def open_for(org, platform):
    o = org.replace("'", "''")
    cond = ("(t.kind = 'find_people' or coalesce(t.payload->>'platform', 'linkedin') = 'linkedin')" if platform == "linkedin"
            else f"t.kind = 'search_posts' and t.payload->>'platform' = '{platform}'")
    return int(psql(f"""select count(*) n from scout_task t join organization g on g.id = t.org_id
                        where g.name = '{o}' and t.status = 'open' and {cond}""")[0]["n"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=50)
    ap.add_argument("--minutes", type=int, default=120)
    ap.add_argument("--ai-cap", type=float, default=5.0)
    ap.add_argument("--no-ai-contacts", action="store_true", help="skip the Claude API contact search (poor yield: ~3% hit rate on 1 Nov)")
    ap.add_argument("--until", help="stop time HH:MM (overrides --minutes)")
    ap.add_argument("--platforms", default="linkedin,x,reddit", help="Chrome scouts to run (X needs a signed-in X; Reddit needs the extension to allow reddit.com)")
    args = ap.parse_args()
    daily_leads.TARGET, daily_leads.TOTAL_MODE = args.target, True
    count = daily_leads.leads_today  # with TOTAL_MODE: all contactable leads (LinkedIn only where the workspace requires it)
    start = dt.datetime.now()
    stop = start + dt.timedelta(minutes=args.minutes)
    if args.until:
        stop = dt.datetime.combine(start.date(), dt.time(*map(int, args.until.split(":"))))
    if not ensure_backend():
        return
    ready = {r["name"] for r in psql("select g.name from organization g join signal_type t on t.org_id = g.id "
                                     "where t.is_custom and t.enabled group by g.name")}
    orgs = [o for o in ACCOUNTS if o in ready]
    short = lambda: [o for o in orgs if count(o) < args.target]  # noqa: E731
    log(f"start: target {args.target} contactable per workspace, stop {stop:%H:%M}, Claude API cap ${args.ai_cap:.2f}; "
        + ", ".join(f"{o} {count(o)}" for o in orgs))

    def free_pass():
        for org in orgs:
            if dt.datetime.now() >= stop:
                return
            try:
                r = call("POST", "/signal-types/run", org_token(org), body={"allowAi": False, "aiQualify": True, "community": False},
                         headers=APPROVED)
                fp = r.get("freePeople") or {}
                log(f"[free] {org}: {r['freeFound']} signal companies, {fp.get('website', 0)} website leads, "
                    f"{fp.get('enriched', 0)} enriched; queued {r['chromeQueued']}")
            except Exception as e:  # noqa: BLE001
                log(f"[free] {org}: failed: {e}")

    def ai_contacts():
        if args.no_ai_contacts:
            return
        exhausted = set()
        while dt.datetime.now() < stop:
            todo = [o for o in short() if o not in exhausted]
            if not todo:
                time.sleep(120)  # the free pass may add signal companies
                exhausted.clear()
                if not short():
                    return
                continue
            for org in todo:
                spent = spent_since(start)
                if spent >= args.ai_cap - 0.2:
                    log(f"[ai] cap reached (${spent:.2f}); stopping Claude API use")
                    return
                try:
                    r = call("POST", "/scout/find-contacts", org_token(org), body={"limit": 8}, headers=APPROVED)
                    log(f"[ai] {org}: {r['checked']} companies checked, +{r['leadsAdded']} leads (${r['costUsd']:.3f}); "
                        f"{r['left']} left; now {count(org)}")
                    if r["checked"] == 0:
                        exhausted.add(org)
                except ApiError as e:
                    log(f"[ai] {org}: {e}")
                    exhausted.add(org)
                if dt.datetime.now() >= stop:
                    return

    def scout(platform):
        runs = {o: 0 for o in orgs}
        # a scout left over from an earlier launch may still be working this platform: let it finish first
        while subprocess.run(["pgrep", "-f", f"run_scout.py .* {platform}$"], capture_output=True).returncode == 0:
            time.sleep(30)
        while dt.datetime.now() < stop:
            todo = [o for o in short() if open_for(o, platform) > 0]
            if not todo:
                time.sleep(90)
                if not short():
                    return
                continue
            todo.sort(key=lambda o: (runs[o], count(o)))  # fewest runs, then fewest leads first
            org = todo[0]
            have = count(org)
            log(f"[{platform}] {org}: {have}/{args.target}, scout run {runs[org] + 1}")
            r = subprocess.run([sys.executable, os.path.join(HERE, "run_scout.py"), org, "15", str(args.target - have), platform],
                               cwd=HERE, capture_output=True, text=True)
            with open(os.path.join(LOGS, f"{dt.date.today()}-fast-scout-{platform}.log"), "a") as f:
                f.write(f"\n=== {org} {dt.datetime.now():%H:%M}\n{r.stdout}\n{r.stderr[-1500:]}\n")
            runs[org] += 1
            if r.returncode == 3:
                log(f"[{platform}] Claude usage limit hit; waiting 20 min")
                time.sleep(1200)
                continue
            log(f"[{platform}] {org}: now {count(org)}/{args.target}")

    threads = [threading.Thread(target=free_pass, name="free"), threading.Thread(target=ai_contacts, name="ai")]
    threads += [threading.Thread(target=scout, args=(p,), name=p) for p in args.platforms.split(",") if p]
    for t in threads:
        t.start()
        time.sleep(20)  # stagger the Chrome scouts so their tabs don't collide on start-up
    for t in threads:
        t.join()

    spent = spent_since(start)
    log(f"done. Claude API spent this run: ${spent:.2f}")
    for o in orgs:
        n = count(o)
        log(f"SUMMARY {o}: {n}/{args.target} contactable leads" + ("" if n >= args.target else f" (short by {args.target - n})"))
    subprocess.run([sys.executable, os.path.join(HERE, "export_leads.py")], cwd=HERE)


if __name__ == "__main__":
    main()
