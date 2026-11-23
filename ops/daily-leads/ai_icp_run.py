"""User-approved Claude API run (2 Nov 2026): ICP-matched LinkedIn leads until every workspace has --target contactable
leads, under a hard --cap in USD for the whole run (measured from ai_usage). One Haiku web-search call per step (about
$0.07 for ~8 leads in the first trial). A workspace is dropped after two calls in a row that add nothing new.

Usage: ai_icp_run.py --target 30 --cap 5
"""
import argparse
import datetime as dt
import os

from leadnius import ACCOUNTS, HERE, ApiError, call, org_token, psql
import daily_leads

LOG = os.path.join(HERE, "logs", f"{dt.date.today()}-ai-icp.log")


def log(msg):
    line = f"{dt.datetime.now():%H:%M:%S} {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def spent(since_utc):
    return float(psql(f"select coalesce(sum(cost_usd), 0) usd from ai_usage where at >= '{since_utc:%Y-%m-%d %H:%M:%S}'")[0]["usd"])


DEFAULT_PERSONAS = {"Founder / CEO", "Sales leader", "Finance leader", "Marketing / Growth"}
COUNTRIES = ["United States", "Canada", "United Kingdom", "Germany", "Australia", "India", "Singapore", "Ireland",
             "Netherlands", "France", "UAE"]


def slices_for(org):
    """Focus slices for one workspace: each of its own personas x each target country (rotating order)."""
    o = org.replace("'", "''")
    personas = psql(f"select p.name, p.titles from agent_persona p join organization g on g.id = p.org_id where g.name = '{o}'")
    geo = (psql(f"select settings->'company'->>'geographies' g from organization where name = '{o}'")[0]["g"] or "").lower()
    regions = [c for c in COUNTRIES if c.lower() in geo or (c == "United States" and (" us" in f" {geo}" or "usa" in geo))
               or (c == "United Kingdom" and " uk" in f" {geo}")] or ["United States"]
    import json as _j
    ps = [(p["name"], _j.loads(p["titles"] or "[]")[:5]) for p in personas if p["name"] not in DEFAULT_PERSONAS]
    out = []
    for i in range(max(len(ps), 1) * len(regions)):
        if not ps:
            break
        name, titles = ps[i % len(ps)]
        region = regions[(i // len(ps)) % len(regions)]
        out.append(f"{name} ({', '.join(titles)}) in {region}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=30)
    ap.add_argument("--cap", type=float, default=5.0)
    ap.add_argument("--since", default="2026-11-02 02:30:00", help="UTC start of the approved spend (includes the trial call)")
    ap.add_argument("--orgs", help="comma-separated workspaces (default: every workspace with signals)")
    args = ap.parse_args()
    daily_leads.TOTAL_MODE = True
    count = daily_leads.leads_today
    since = dt.datetime.strptime(args.since, "%Y-%m-%d %H:%M:%S")
    ready = {r["name"] for r in psql("select g.name from organization g join signal_type t on t.org_id = g.id "
                                     "where t.is_custom and t.enabled group by g.name")}
    orgs = [o for o in ACCOUNTS if o in ready]
    if args.orgs:
        want = [o.strip() for o in args.orgs.split(",")]
        for o in want:
            if o not in ready:
                log(f"{o}: skipped (no ICP signals yet)")
        orgs = [o for o in want if o in ready]
    misses = {o: 0 for o in orgs}
    slices = {o: slices_for(o) for o in orgs}
    for o in orgs:
        log(f"{o}: {len(slices[o])} focus slices")
    log(f"start: target {args.target}, cap ${args.cap:.2f}; " + ", ".join(f"{o} {count(o)}" for o in orgs))
    while True:
        todo = [o for o in orgs if count(o) < args.target and misses[o] < 4 and slices[o]]
        if not todo:
            break
        todo.sort(key=count)  # furthest behind first
        for org in todo:
            s = spent(since)
            if s >= args.cap - 0.15:
                log(f"cap reached: ${s:.2f} spent")
                return finish(orgs, count, since, args)
            try:
                focus = slices[org].pop(0)
                r = call("POST", "/scout/icp-people", org_token(org), body={"maxSearches": 10, "focus": focus},
                         headers={"X-AI-Approved": "yes"})
                misses[org] = 0 if r["leadsAdded"] else misses[org] + 1
                log(f"{org} [{focus[:60]}]: +{r['leadsAdded']} (found {r['found']}, rejected {r['rejected']}, dropped {r['dropped']}, "
                    f"${r['costUsd']:.3f}) -> {count(org)}/{args.target}")
            except ApiError as e:
                misses[org] += 1
                log(f"{org}: {e}")
    finish(orgs, count, since, args)


def finish(orgs, count, since, args):
    log(f"done. Claude API spent in this approved run: ${spent(since):.2f} of ${args.cap:.2f}")
    for o in orgs:
        n = count(o)
        log(f"SUMMARY {o}: {n}/{args.target}" + ("" if n >= args.target else f" (short by {args.target - n})"))
    os.system(f'cd "{HERE}" && python3 export_leads.py > /dev/null')


if __name__ == "__main__":
    main()
