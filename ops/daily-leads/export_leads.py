"""One CSV per workspace: named leads first, then signal companies still without a contact. Reads the DB directly."""
import csv, os, subprocess, urllib.parse

OUT = "/Users/shubhangigupta/Desktop/Lead Gen/client-playbooks/lead-lists"
ORGS = ["Shubhangi freelance", "OMG Boxes", "OMG Fitness", "Finance SaaS", "Datapedia Labs", "Leadnius GTM Lab", "Pravaah", "Franklin Parcel", "Pivot Money", "BD Vault AI", "Dhyora", "Quant PM", "Leadnius Community", "Leadnius SaaS", "Gudpals"]
env = dict(os.environ)
line = next(l for l in open("/Users/shubhangigupta/Desktop/Lead Gen/lead-gen-backend/.env") if l.startswith("DATABASE_URL"))
env["PGPASSWORD"] = urllib.parse.unquote(line.split("postgres:", 1)[1].split("@", 1)[0])
PSQL = ["/Library/PostgreSQL/18/bin/psql", "-h", "localhost", "-U", "postgres", "-d", "lead_genius", "--csv", "-c"]


def q(sql):
    r = subprocess.run(PSQL + [sql], env=env, capture_output=True, text=True, check=True)
    return list(csv.DictReader(r.stdout.splitlines()))


os.makedirs(OUT, exist_ok=True)
LINKEDIN_ONLY = {r["name"] for r in q("select name from organization where (settings->'leadRules'->>'linkedinOnly')::boolean")}
summary = []
for org in ORGS:
    o = org.replace("'", "''")
    # event-only mode for Nov-Dec 2026: leads from switched-off signal types are left out; leads from searches that
    # aren't a signal type (Apify / AI LinkedIn search for these workspaces' buyers) stay in
    only_on = " and (st.enabled or st.key is null)" if org in ("Pravaah", "Franklin Parcel") else ""
    # contactable only: a LinkedIn profile, or (unless the workspace is LinkedIn-only) an X/Reddit profile or a published email
    contact = ("l.linkedin like '%linkedin.com/in/%'" if org in LINKEDIN_ONLY else
               "(l.linkedin like '%linkedin.com/in/%' or coalesce(l.profile->>'profileUrl', '') <> '' or l.email <> '')")
    leads = q(f"""select l.name, l.title, l.company, l.linkedin, l.email, coalesce(nullif(l.profile->>'platform', ''), 'linkedin') as platform,
                  l.profile->>'profileUrl' as profile_url, l.signal, st.tier, st.category, l.score,
                  l.profile->>'priority' as priority, l.profile->>'angle' as outreach_angle, l.profile->>'signalDetail' as what_happened, l.profile->>'hook' as source_url, l.created_at::date as found_on
                  from agent_lead l join organization g on g.id = l.org_id
                  left join signal_type st on st.org_id = l.org_id and st.name = l.signal
                  where g.name = '{o}'{only_on} and {contact} and coalesce(l.profile->>'disqualified', 'false') <> 'true'
                  order by l.score desc""")
    named = {r["company"].lower() for r in leads}
    companies = q(f"""select s.company, s.type as signal, st.tier, st.category, s.score, s.detail as what_happened, s.url as source_url,
                      s.detected_at::date as found_on
                      from signal s join organization g on g.id = s.org_id
                      left join signal_type st on st.org_id = s.org_id and st.key = s.signal_key
                      where g.name = '{o}'{only_on} order by case st.tier when 'intent' then 0 when 'hot' then 1 when 'warm' then 2 else 3 end, s.score desc""")
    rest = [c for c in companies if c["company"].lower() not in named]
    path = os.path.join(OUT, org.lower().replace(" ", "-") + "-leads.csv")
    cols = ["name", "title", "company", "platform", "linkedin", "profile_url", "email", "signal", "tier", "category", "score", "priority", "outreach_angle", "what_happened", "source_url", "found_on"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in leads:
            w.writerow({k: r.get(k, "") for k in cols})
    # signal companies with no reachable person yet go to their own file (the scout's find_people works on them)
    ccols = ["company", "signal", "tier", "category", "score", "what_happened", "source_url", "found_on"]
    with open(path.replace("-leads.csv", "-signal-companies.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ccols)
        w.writeheader()
        for c in rest:
            w.writerow({k: c.get(k, "") for k in ccols})
    summary.append((org, len(leads), len(rest), path))
for org, n, c, p in summary:
    print(f"{org}: {n} contactable leads -> {p} ({c} signal companies without a contact in the -signal-companies.csv)")
