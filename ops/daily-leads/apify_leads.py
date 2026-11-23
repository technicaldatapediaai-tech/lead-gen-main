"""Apify LinkedIn profile search (harvestapi/linkedin-profile-search, no cookies, $0.10 per search page of up to 25
profiles) for the priority workspaces, under a hard cap of search pages (user budget: $2 = 20 pages, 2 Nov 2026).

Every person is saved through services/lead_store.save_people (LinkedIn URL, fit >= 65, no duplicates, LinkedIn-only
where set). Fit is scored by rules, no Claude: the current title must match the search's titles and the location its
region; "changed jobs in the last 90 days" (the new-leader signals) adds to the score.

Run with the backend venv from the Lead Gen folder:
  APIFY_TOKEN=... lead-gen-backend/venv/bin/python ops/daily-leads/apify_leads.py [--pages 20] [--dry-run]
The token is read from the environment or APIFY_TOKEN in lead-gen-backend/.env, never printed.
"""
import argparse
import asyncio
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
ACTOR = "harvestapi~linkedin-profile-search"
# not buyers: vendors, advisers and people outside a company role
EXCLUDE = re.compile(r"\b(consultant|consulting|advisor|adviser|fractional|freelance|interim|coach|student|intern|retired|"
                     r"school|citizen|volunteer|board member|recruit|talent|sales rep|account executive)\b", re.I)
US = ["United States"]

# (workspace, signal name to file the lead under, Apify input, titles that must appear in the person's current title, base score)
SEARCHES = [
    ("Franklin Parcel", "New finance or ops leader (Apify)", {"currentJobTitles": ["CFO", "Chief Financial Officer", "VP Finance", "Controller"],
     "locations": US, "companyHeadcount": ["D", "E"], "searchQuery": "ecommerce OR manufacturing OR distribution", "recentlyChangedJobs": True},
     ["cfo", "chief financial", "finance", "controller"], 78),
    ("Franklin Parcel", "Shipping and logistics leader (Apify)", {"currentJobTitles": ["Director of Logistics", "Logistics Manager", "Shipping Manager",
     "VP Operations", "Director of Operations", "Supply Chain Director"], "locations": US, "companyHeadcount": ["D", "E"],
     "searchQuery": "ecommerce OR manufacturer OR distributor"}, ["logistic", "shipping", "operations", "supply chain"], 70),
    ("Franklin Parcel", "Dental and medical supply leader (Apify)", {"currentJobTitles": ["CFO", "VP Operations", "Director of Operations", "Logistics Manager"],
     "locations": US, "companyHeadcount": ["D", "E"], "searchQuery": "dental supply OR medical supply OR medical device"},
     ["cfo", "financ", "operations", "logistic"], 75),
    ("Pravaah", "New COO or VP Ops at a manufacturer (Apify)", {"currentJobTitles": ["COO", "Chief Operating Officer", "VP Operations", "Vice President of Operations",
     "Plant Manager", "Director of Operations"], "locations": US, "companyHeadcount": ["D"], "searchQuery": "manufacturing", "recentlyChangedJobs": True},
     ["coo", "chief operating", "operations", "plant manager"], 78),
    ("Pravaah", "Manufacturing owner (Apify)", {"currentJobTitles": ["Owner", "President", "CEO", "Founder"], "locations": US, "companyHeadcount": ["D"],
     "searchQuery": "manufacturing OR machine shop OR fabrication", "seniorityLevelIds": ["310", "320"]},
     ["owner", "president", "ceo", "founder"], 72),
    ("Pravaah", "Fleet owner or operations lead (Apify)", {"currentJobTitles": ["Owner", "President", "Fleet Manager", "Director of Operations", "VP Operations"],
     "locations": US, "companyHeadcount": ["C", "D"], "searchQuery": "trucking OR fleet OR transportation"},
     ["owner", "president", "fleet", "operations"], 72),
    ("BD Vault AI", "GovCon BD or proposal leader (Apify)", {"currentJobTitles": ["Director of Business Development", "Capture Manager", "Proposal Manager",
     "VP Business Development", "Head of Proposals"], "locations": US, "companyHeadcount": ["B", "C", "D"],
     "searchQuery": "federal OR government contracting OR GovCon"}, ["business development", "capture", "proposal"], 75),
    ("BD Vault AI", "GovCon founder (Apify)", {"currentJobTitles": ["Founder", "CEO", "President", "Owner"], "locations": US, "companyHeadcount": ["B", "C", "D"],
     "searchQuery": "federal contractor OR government contracting OR 8(a) OR SDVOSB"}, ["founder", "ceo", "president", "owner"], 72),
    ("BD Vault AI", "New BD or capture leader (Apify)", {"currentJobTitles": ["Director of Business Development", "Capture Manager", "VP Business Development",
     "Proposal Manager"], "locations": US, "companyHeadcount": ["B", "C", "D"], "searchQuery": "federal OR government", "recentlyChangedJobs": True},
     ["business development", "capture", "proposal"], 80),
    ("Quant PM", "Tech professional with equity in California (Apify)", {"currentJobTitles": ["Senior Software Engineer", "Staff Software Engineer",
     "Engineering Manager", "Director of Engineering", "Product Director"], "locations": ["California"], "searchQuery": "pre-IPO OR IPO OR RSU",
     "seniorityLevelIds": ["120", "220", "300"]}, ["engineer", "director", "manager", "product"], 66),
    ("Quant PM", "Nearing retirement in California (Apify)", {"currentJobTitles": ["Director", "Vice President", "Senior Director", "Principal"],
     "locations": ["California"], "searchQuery": "retiring OR retirement", "yearsOfExperienceIds": ["5"]}, ["director", "vice president", "principal"], 66),
]


IN = ["India"]
NA = ["United States", "Canada"]
# 2 Nov 2026, second set: the workspaces still under 30 (Leadnius Community, GTM Lab, Pivot Money, Shubhangi freelance,
# OMG Boxes, Finance SaaS, Dhyora)
SHORT = [
    ("Leadnius Community", "Early-stage SaaS founder (Apify)", {"currentJobTitles": ["Founder", "Co-founder", "Founder & CEO", "CTO"],
     "locations": ["United States", "United Kingdom", "Canada", "Australia", "India"], "companyHeadcount": ["B"],
     "searchQuery": "SaaS beta OR early access OR launched", "recentlyPostedOnLinkedIn": True}, ["founder", "ceo", "cto"], 72),
    ("Leadnius Community", "AI tool founder building in public (Apify)", {"currentJobTitles": ["Founder", "Co-founder", "Solo Founder", "Indie Hacker"],
     "locations": ["United States", "United Kingdom", "Canada", "Australia", "India"], "companyHeadcount": ["A", "B"],
     "searchQuery": "AI SaaS OR micro SaaS OR building in public"}, ["founder", "indie", "maker"], 70),
    ("Leadnius GTM Lab", "Sales enablement or L&D head (Apify)", {"currentJobTitles": ["Head of Sales Enablement", "Sales Enablement Manager",
     "Head of L&D", "Learning and Development Manager", "Training Manager"], "locations": ["India", "United States", "United Kingdom"],
     "companyHeadcount": ["D", "E", "F"], "searchQuery": "SaaS OR B2B OR IT services"}, ["enablement", "learning", "l&d", "training"], 72),
    ("Leadnius GTM Lab", "RevOps or sales leader at a B2B company (Apify)", {"currentJobTitles": ["Head of RevOps", "Revenue Operations Director",
     "VP Sales", "Head of Sales", "Sales Operations Manager"], "locations": ["United States", "United Kingdom", "Canada", "Australia", "Germany"],
     "companyHeadcount": ["C", "D", "E"], "searchQuery": "SaaS OR B2B", "recentlyChangedJobs": True}, ["revops", "revenue operations", "sales"], 75),
    ("Pivot Money", "NRI in North America planning a move to India (Apify)", {"locations": NA,
     "searchQuery": "\"moving back to India\" OR \"relocating to India\" OR \"returning to India\" OR R2I"},
     ["engineer", "manager", "director", "consultant", "founder", "product", "scientist", "lead", "analyst", "vp", "head"], 70),
    ("Shubhangi freelance", "Head of growth or RevOps at a B2B SaaS (Apify)", {"currentJobTitles": ["Head of Growth", "Head of RevOps", "Growth Lead",
     "RevOps Manager", "VP Sales"], "locations": ["United States", "United Kingdom", "Canada", "Australia"], "companyHeadcount": ["B", "C", "D"],
     "searchQuery": "B2B SaaS", "recentlyChangedJobs": True}, ["growth", "revops", "revenue", "sales"], 75),
    ("OMG Boxes", "HR or people head at an Indian company (Apify)", {"currentJobTitles": ["Head of HR", "HR Manager", "CHRO", "People and Culture Lead",
     "Employee Engagement Manager"], "locations": IN, "companyHeadcount": ["C", "D", "E"], "searchQuery": "startup OR SaaS OR IT services OR agency"},
     ["hr", "people", "culture", "engagement", "chro", "human resources"], 72),
    ("Finance SaaS", "Finance leader at an MGA, broker or insurer (Apify)", {"currentJobTitles": ["CFO", "Finance Director", "Head of Finance",
     "Financial Controller"], "locations": ["United Kingdom", "United States", "Australia", "Canada"], "companyHeadcount": ["B", "C", "D"],
     "searchQuery": "MGA OR insurance broker OR insurer OR underwriting"}, ["cfo", "finance", "controller"], 74),
    ("Dhyora", "Study-abroad consultancy founder (Apify)", {"currentJobTitles": ["Founder", "Managing Director", "CEO", "Director", "Owner"],
     "locations": IN, "companyHeadcount": ["B", "C", "D"], "searchQuery": "study abroad OR overseas education OR immigration consultant"},
     ["founder", "director", "ceo", "owner"], 74),
]


def token() -> str:
    t = os.environ.get("APIFY_TOKEN", "").strip()
    if not t:
        env = os.path.join(ROOT, "lead-gen-backend", ".env")
        for line in open(env):
            if line.startswith("APIFY_TOKEN="):
                t = line.split("=", 1)[1].strip().strip('"')
    if not t:
        sys.exit("APIFY_TOKEN not set (environment or lead-gen-backend/.env)")
    return t


def recent_runs(limit: int = 20) -> list:
    """This actor's recent runs on the account: (input, items) for each succeeded run, read from Apify's stored datasets
    (reading results again costs nothing)."""
    base = "https://api.apify.com/v2"
    get = lambda u: json.loads(urllib.request.urlopen(u, timeout=120).read().decode())  # noqa: E731
    runs = get(f"{base}/acts/{ACTOR}/runs?token={token()}&desc=1&limit={limit}")["data"]["items"]
    out = []
    for r in runs:
        if r.get("status") != "SUCCEEDED":
            continue
        rec = get(f"{base}/key-value-stores/{r['defaultKeyValueStoreId']}/records/INPUT?token={token()}")
        items = get(f"{base}/datasets/{r['defaultDatasetId']}/items?token={token()}&clean=1")
        out.append((rec, items))
    return out


def run_search(inp: dict) -> list:
    body = {"profileScraperMode": "Short", "maxItems": 25, "takePages": 1, **inp}
    req = urllib.request.Request(f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items?token={token()}",
                                 data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode() or "[]")


def person(item: dict) -> dict:
    """Normalise a short profile (field names vary a little between actor versions)."""
    name = item.get("fullName") or " ".join(x for x in (item.get("firstName"), item.get("lastName")) if x) or item.get("name", "")
    pos = (item.get("currentPositions") or item.get("currentPosition") or item.get("experience") or [{}])
    pos = pos[0] if isinstance(pos, list) and pos else (pos if isinstance(pos, dict) else {})
    title = pos.get("title") or pos.get("position") or item.get("headline", "")
    company = pos.get("companyName") or pos.get("company") or ""
    loc = item.get("location")
    loc = loc.get("linkedinText") or loc.get("text") or "" if isinstance(loc, dict) else (loc or "")
    pid = item.get("publicIdentifier") or ""
    url = (f"https://www.linkedin.com/in/{pid}/" if pid and not pid.startswith("ACw") else
           item.get("linkedinUrl") or item.get("profileUrl") or item.get("url") or "")
    return {"name": name.strip(), "title": (title or "").strip(), "company": (company or "").strip(), "linkedin": url.split("?")[0],
            "location": loc, "headline": item.get("headline", "")}


async def save(org_name: str, signal: str, people: list) -> tuple:
    from sqlmodel import select
    from sqlmodel.ext.asyncio.session import AsyncSession
    from backend.database import engine
    from backend.models.user import Organization
    from backend.services import lead_store
    async with AsyncSession(engine, expire_on_commit=False) as s:
        org = (await s.execute(select(Organization).where(Organization.name == org_name))).scalars().first()
        added, rejected = await lead_store.save_people(s, org.id, signal, people)
        await s.commit()
    await engine.dispose()  # each save runs in its own event loop (asyncio.run); don't reuse pooled connections
    return added, rejected


def contactable(org_name: str) -> int:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import daily_leads
    daily_leads.TOTAL_MODE = True
    return daily_leads.leads_today(org_name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=20, help="hard cap on search pages ($0.10 each)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--recover", action="store_true", help="re-read today's paid runs from Apify (free) and save them; no new searches")
    ap.add_argument("--set", default="priority", choices=["priority", "short"])
    ap.add_argument("--start", type=int, default=0, help="skip the first N searches (already run)")
    ap.add_argument("--target", type=int, default=30, help="skip a workspace once it has this many contactable leads")
    args = ap.parse_args()
    used, total = 0, {}
    cache = {}
    if args.recover:
        for rec, items in recent_runs():
            cache[(rec.get("searchQuery"), tuple(rec.get("currentJobTitles") or []))] = items
        print(f"recovering {len(cache)} stored runs (no new searches)")
    for org, signal, inp, must, base in (SHORT if args.set == "short" else SEARCHES)[args.start:]:
        if args.recover:
            items = cache.get((inp.get("searchQuery"), tuple(inp.get("currentJobTitles") or [])))
            if items is None:
                continue
            people = [p for p in (person(it) for it in items) if p["name"] and "linkedin.com/in/" in p["linkedin"]
                      and any(m in f"{p['title']} {p['headline']}".lower() for m in must)
                      and not EXCLUDE.search(f"{p['title']} {p['company']}") and p["company"]]
            people = [{**p, "platform": "linkedin", "url": p["linkedin"], "score": base, "found_by": "Apify LinkedIn search",
                       "detail": f"{p['title']} at {p['company']} ({p['location']}). Found by LinkedIn search: {signal}."} for p in people]
            added, rejected = asyncio.run(save(org, signal, people))
            total[org] = total.get(org, 0) + added
            print(f"{org} / {signal}: recovered {len(items)} profiles, {len(people)} pass rules, +{added} ({len(rejected)} rejected)")
            continue
        if used >= args.pages:
            print(f"page cap reached ({used} pages, ${used * 0.10:.2f})")
            break
        have = contactable(org)
        if have >= args.target:
            print(f"{org} / {signal}: skipped, already {have}/{args.target}")
            continue
        try:
            items = run_search(inp)
        except Exception as e:  # noqa: BLE001
            print(f"{org} / {signal}: search failed: {e}")
            continue
        used += 1
        people = []
        for it in items:
            p = person(it)
            t = f"{p['title']} {p['headline']}".lower()
            if not p["name"] or "linkedin.com/in/" not in p["linkedin"] or not any(m in t for m in must):
                continue
            if EXCLUDE.search(f"{p['title']} {p['company']}") or not p["company"]:
                continue
            people.append({**p, "platform": "linkedin", "url": p["linkedin"], "score": base,
                           "detail": f"{p['title']} at {p['company']} ({p['location']}). Found by LinkedIn search: {signal}.",
                           "found_by": "Apify LinkedIn search"})
        if args.dry_run:
            print(f"{org} / {signal}: {len(items)} profiles, {len(people)} pass rules (dry run)")
            continue
        added, rejected = asyncio.run(save(org, signal, people))
        total[org] = total.get(org, 0) + added
        print(f"{org} / {signal}: {len(items)} profiles, {len(people)} pass rules, +{added} leads ({len(rejected)} rejected)")
    print(f"done: {used} search pages (${used * 0.10:.2f}); added {total}")


if __name__ == "__main__":
    main()
