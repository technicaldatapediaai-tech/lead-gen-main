"""Daily lead job: up to TARGET new verified leads per workspace per day.

Order (docs/signal-routing.md): for every workspace, the free pass runs first: free news and job sources, people from
community posts (Stack Exchange, Hacker News, Reddit API if configured) and decision makers on company websites, all
checked by rules plus the free local model (Ollama), never the Claude API. It re-queues the Chrome scout tasks (post searches on LinkedIn, X, Reddit and review sites; decision makers for signal
companies). Then Claude in Chrome works the queues round-robin, one run of up to 15 tasks per workspace per round,
until each workspace has TARGET leads today, its queue is empty, or the deadline passes. When the Claude usage limit is
hit it waits LIMIT_WAIT_S and carries on. No AI-credit lead hunts. The server rejects any person without a LinkedIn,
X or Reddit profile URL, below the fit score, or already a lead, so the counts below are verified, unique leads.

Usage: daily_leads.py [--not-before HH:MM] [--orgs "A,B"]   (launchd runs it daily; see README.md)
"""
import argparse
import datetime as dt
import fcntl
import json
import os
import subprocess
import sys
import threading
import time

from leadnius import ACCOUNTS, HERE, ROOT, call, healthy, org_token, psql

TARGET = 30
TASKS_PER_RUN = 15
MAX_RUNS_PER_ORG = 4
LIMIT_WAIT_S = 1800
DEADLINE = dt.time(23, 30)
LOGS = os.path.join(HERE, "logs")


def log(msg):
    line = f"{dt.datetime.now():%Y-%m-%d %H:%M} {msg}"
    print(line, flush=True)
    with open(os.path.join(LOGS, f"{dt.date.today()}.log"), "a") as f:
        f.write(line + "\n")


TOTAL_MODE = False  # --total: count every contactable lead the workspace has, not just today's


def leads_today(org):
    """Contactable leads created today (local day), or in total with --total. A LinkedIn-only workspace
    (settings.leadRules.linkedinOnly, e.g. Pravaah and Franklin Parcel) counts LinkedIn profiles only."""
    start = dt.datetime.combine(dt.date.today(), dt.time()).astimezone(dt.timezone.utc).replace(tzinfo=None)
    o = org.replace("'", "''")
    when = "" if TOTAL_MODE else f"and l.created_at >= '{start:%Y-%m-%d %H:%M:%S}'"
    rows = psql(f"""select count(*) n from agent_lead l join organization g on g.id = l.org_id
                    where g.name = '{o}' {when} and coalesce(l.profile->>'disqualified', 'false') <> 'true'
                    and (l.linkedin like '%linkedin.com/in/%' or (coalesce((g.settings->'leadRules'->>'linkedinOnly')::boolean, false) = false
                         and (coalesce(l.profile->>'profileUrl', '') <> '' or l.email <> '')))""")
    return int(rows[0]["n"])


def open_tasks(org):
    o = org.replace("'", "''")
    return int(psql(f"""select count(*) n from scout_task t join organization g on g.id = t.org_id
                        where g.name = '{o}' and t.status = 'open'""")[0]["n"])


def ensure_backend():
    if healthy():
        return True
    # a server is listening but busy (e.g. a reload waiting for a long free-pass request): wait, don't start another
    listening = subprocess.run(["lsof", "-nP", "-iTCP:8000", "-sTCP:LISTEN"], capture_output=True, text=True).stdout.strip()
    if listening:
        log("backend busy; waiting for it")
        for _ in range(60):
            time.sleep(30)
            if healthy():
                return True
        log("backend still busy after 30 min")
        return False
    log("backend down: starting uvicorn on :8000")
    cmd = (f'cd "{ROOT}" && source lead-gen-backend/venv/bin/activate && '
           "nohup uvicorn backend.main:app --reload --reload-dir lead-gen-backend --port 8000 > ops/daily-leads/logs/uvicorn.log 2>&1 &")
    subprocess.run(["/bin/zsh", "-c", cmd])
    for _ in range(30):
        time.sleep(5)
        if healthy():
            return True
    log("backend did not start; giving up for today")
    return False


def main():
    global TARGET, TOTAL_MODE
    ap = argparse.ArgumentParser()
    ap.add_argument("--not-before", help="wait until this local time (HH:MM), e.g. when the Claude usage limit resets")
    ap.add_argument("--orgs", help="comma-separated workspaces (default: all in accounts.json, in that order)")
    ap.add_argument("--target", type=int, default=TARGET, help="contactable leads wanted per workspace")
    ap.add_argument("--platform", default="", help="limit the Chrome scout to one platform (e.g. linkedin while X/Reddit are blocked)")
    ap.add_argument("--max-runs", type=int, default=0, help="scout runs per workspace (default: scaled to the target)")
    ap.add_argument("--until", default="23:30", help="stop time HH:MM; earlier than the start means tomorrow (overnight runs)")
    ap.add_argument("--total", action="store_true", help="count all contactable leads, not just today's")
    ap.add_argument("--ai-last", action="store_true",
                    help="ONLY when the user approved it for this run: one Claude API lead hunt per workspace still short at the end")
    args = ap.parse_args()
    TARGET, TOTAL_MODE = args.target, args.total
    max_runs = args.max_runs or max(MAX_RUNS_PER_ORG, -(-TARGET // 6))  # a scout run yields roughly 2-12 leads
    os.makedirs(LOGS, exist_ok=True)
    lock = open(os.path.join(HERE, ".lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        log("another daily run is still going; exiting")
        return
    if args.not_before:
        h, m = map(int, args.not_before.split(":"))
        wait = (dt.datetime.combine(dt.date.today(), dt.time(h, m)) - dt.datetime.now()).total_seconds()
        if wait > 0:
            log(f"waiting until {args.not_before}")
            time.sleep(wait)
    if not ensure_backend():
        return
    orgs = [o.strip() for o in args.orgs.split(",")] if args.orgs else list(ACCOUNTS)
    ready = {r["name"] for r in psql("""select g.name from organization g join signal_type t on t.org_id = g.id
                                        where t.is_custom and t.enabled group by g.name""")}
    for o in [o for o in orgs if o not in ready]:
        log(f"{o}: no custom signals yet (needs its playbook); skipped")
    orgs = [o for o in orgs if o in ready]
    day = dt.date.today()

    # 1. free pass + re-queue scout tasks (no AI hunts). The local-model checks are slow, so this runs in a background
    # thread while the Chrome scout (step 2) starts on the tasks already queued; each workspace's new tasks join as it finishes.
    def free_pass():
        for org in orgs:
            free_one(org)

    def free_one(org):
        try:
            r = call("POST", "/signal-types/run", org_token(org), body={"allowAi": False})
            fp = r.get("freePeople") or {}
            log(f"{org}: free pass found {r['freeFound']} signal companies, {fp.get('community', 0)} leads from community posts, "
                f"{fp.get('website', 0)} from company websites; queued for Chrome {r['chromeQueued']}")
        except Exception as e:  # noqa: BLE001
            log(f"{org}: free pass failed: {e}")

    free_thread = threading.Thread(target=free_pass, daemon=True)
    free_thread.start()

    # 2. Chrome scout, round-robin until every workspace has TARGET leads today
    runs = {o: 0 for o in orgs}
    done = set()
    uh, um = map(int, args.until.split(":"))
    stop = dt.datetime.combine(dt.date.today(), dt.time(uh, um))
    if stop <= dt.datetime.now():
        stop += dt.timedelta(days=1)
    log(f"target {TARGET} contactable leads per workspace ({'all-time' if TOTAL_MODE else 'today'}); up to {max_runs} scout runs each; stops {stop:%d %b %H:%M}")
    while dt.datetime.now() < stop:
        active = [o for o in orgs if o not in done]
        if not active:
            break
        ran = sum(runs.values())
        for org in active:
            if dt.datetime.now() >= stop:
                break
            have = leads_today(org)
            if have >= TARGET or runs[org] >= max_runs or (open_tasks(org) == 0 and not free_thread.is_alive()):
                done.add(org)
                continue
            if open_tasks(org) == 0:  # its free pass may still queue tasks
                continue
            if not ensure_backend():
                return
            log(f"{org}: {have}/{TARGET} leads today, scout run {runs[org] + 1}")
            r = subprocess.run([sys.executable, os.path.join(HERE, "run_scout.py"), org, str(TASKS_PER_RUN), str(TARGET - have)]
                               + ([args.platform] if args.platform else []),
                               cwd=HERE, capture_output=True, text=True)
            with open(os.path.join(LOGS, f"{day}-scout.log"), "a") as f:
                f.write(f"\n=== {org} run {runs[org] + 1} {dt.datetime.now():%H:%M}\n{r.stdout}\n{r.stderr[-1500:]}\n")
            if r.returncode == 3:
                log(f"Claude usage limit hit; waiting {LIMIT_WAIT_S // 60} min")
                time.sleep(LIMIT_WAIT_S)
                break  # restart the round; this org goes again
            runs[org] += 1
            log(f"{org}: now {leads_today(org)}/{TARGET} leads today")
        if sum(runs.values()) == ran:
            time.sleep(60)  # waiting for the free pass to queue tasks

    # 3. last resort, only with the user's approval for this run: one paid lead hunt per workspace still short
    if args.ai_last:
        for org in [o for o in orgs if leads_today(o) < TARGET]:
            try:
                r = call("POST", "/signal-types/hunt", org_token(org), body={"maxSignals": 3, "findContacts": True},
                         headers={"X-AI-Approved": "yes"})
                log(f"{org}: AI lead hunt (approved) added {r['leads']} contactable leads, {len(r['signals'])} signal companies")
            except Exception as e:  # noqa: BLE001
                log(f"{org}: AI lead hunt skipped: {e}")
        spent = psql(f"""select coalesce(sum(cost_usd), 0) usd, count(*) calls from ai_usage
                         where at >= '{dt.datetime.combine(day, dt.time()).astimezone(dt.timezone.utc).replace(tzinfo=None):%Y-%m-%d %H:%M:%S}'""")[0]
        log(f"Claude API today: {spent['calls']} calls, ${float(spent['usd']):.2f}")

    # 3b. summary + lead lists
    summary = {o: leads_today(o) for o in orgs}
    for o, n in summary.items():
        log(f"SUMMARY {o}: {n}/{TARGET} verified new leads today" + ("" if n >= TARGET else f" (short by {TARGET - n})"))
    json.dump({"date": str(day), "target": TARGET, "leads": summary}, open(os.path.join(LOGS, f"{day}-summary.json"), "w"), indent=1)
    subprocess.run([sys.executable, os.path.join(HERE, "export_leads.py")], cwd=HERE)


if __name__ == "__main__":
    main()
