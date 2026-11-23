"""Lead scoring + qualification (free: rules only, no Claude API, Apify or Chrome).

Model from the gtm-skills Scout playbook (github.com/gtm-skills/gtm: ICP must-have / nice-to-have / disqualifiers,
signal tiers, score decay, a briefing angle per lead), applied to every workspace's leads:

  score = fit (0-60) + signal (0-40) - decay
    fit:    title matches a persona title 30 (+10 when senior), region 10 (unknown 5), contact route 10 (LinkedIn) / 6
    signal: tier intent 40 / hot 32 / warm 22 / cold 12; leads found by a profile search 15, or 25 when the search
            was "changed jobs in the last 90 days" (new leader)
    decay:  -5 after 30 days, -15 after 90 days
  priority: hot >= 80, warm 65-79, cold < 65; disqualified when a red flag matches (kept, flagged, never deleted)

Writes AgentLead.score and profile.{fitScore, signalScore, priority, disqualified, disqualifyReason, angle,
sourceScore}. Run: python3 ops/daily-leads/lead_scoring.py [--dry-run]
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from leadnius import psql  # noqa: E402

US = ["united states", "usa", "u.s."] + [s.lower() for s in (
    "Alabama Alaska Arizona Arkansas California Colorado Connecticut Delaware Florida Georgia Hawaii Idaho Illinois Indiana Iowa Kansas "
    "Kentucky Louisiana Maine Maryland Massachusetts Michigan Minnesota Mississippi Missouri Montana Nebraska Nevada Ohio Oklahoma Oregon "
    "Pennsylvania Tennessee Texas Utah Vermont Virginia Washington Wisconsin Wyoming").split()] + [
    "new hampshire", "new jersey", "new mexico", "new york", "north carolina", "north dakota", "rhode island", "south carolina",
    "south dakota", "west virginia", "district of columbia"]
CA, UK, AU, DE, IN = ["canada", "ontario", "british columbia", "alberta", "quebec", "toronto", "vancouver"], \
    ["united kingdom", "england", "scotland", "wales", "london"], ["australia", "sydney", "melbourne"], \
    ["germany", "deutschland", "berlin", "munich"], ["india", "bengaluru", "bangalore", "mumbai", "pune", "delhi", "hyderabad",
                                                     "chennai", "kerala", "gujarat", "punjab", "kolkata", "noida", "gurgaon", "gurugram"]
ME = ["united arab emirates", "uae", "dubai", "saudi arabia", "qatar"]
COUNTRIES = US + CA + UK + AU + DE + IN + ME + [
    "france", "spain", "italy", "netherlands", "ireland", "singapore", "brazil", "mexico", "nigeria", "pakistan", "philippines",
    "south africa", "kenya", "indonesia", "vietnam", "japan", "china", "israel", "sweden", "poland", "portugal", "new zealand"]

SENIOR = re.compile(r"\b(founder|co-?founder|ceo|cfo|coo|cto|cmo|cro|chro|chief|owner|president|vp|vice president|head|director|"
                    r"managing director|partner|principal|general manager)\b", re.I)
EDU_GOV = r"school|district|university|college|county|city of|state of|department of"
BASE_TITLE_DQ = r"intern|student|recruiter|talent acquisition|sales representative|account executive|\bsdr\b|\bbdr\b|consultant|" \
                r"advisor|adviser|freelance|fractional|retired|professor|teacher|lecturer|volunteer|board member|coach"

# per workspace: allowed regions (strict = out-of-region location disqualifies), title and company red flags
RULES = {
    "Pravaah": dict(regions=US, strict=True, title_dq=BASE_TITLE_DQ, company_dq=EDU_GOV + r"|bank|capital|consulting"),
    "Franklin Parcel": dict(regions=US, strict=True, title_dq=BASE_TITLE_DQ, company_dq=EDU_GOV + r"|bank|credit union"),
    "BD Vault AI": dict(regions=US, strict=True, title_dq=BASE_TITLE_DQ,
                        company_dq=EDU_GOV + r"|bank|capital|investment|ventures|credit union|hospital"),
    "Quant PM": dict(regions=["california"], strict=True, title_dq=r"intern|student|recruiter", company_dq=r"$^"),
    "Pivot Money": dict(regions=US + CA, strict=True, title_dq=r"intern|student|recruiter", company_dq=r"$^"),
    "Dhyora": dict(regions=IN, strict=True, title_dq=BASE_TITLE_DQ.replace("consultant|", ""), company_dq=r"university|college"),
    "OMG Boxes": dict(regions=IN, strict=True, title_dq=BASE_TITLE_DQ.replace("recruiter|talent acquisition|", ""),
                      company_dq=EDU_GOV),
    "OMG Fitness": dict(regions=US + CA + IN + AU + DE + ME, strict=False, title_dq=r"intern|student|recruiter", company_dq=r"$^"),
    "Finance SaaS": dict(regions=US + UK + DE + AU + CA, strict=True, title_dq=BASE_TITLE_DQ, company_dq=EDU_GOV),
    "Datapedia Labs": dict(regions=US + CA + DE + UK + AU + IN, strict=True, title_dq=BASE_TITLE_DQ, company_dq=EDU_GOV),
    "Leadnius GTM Lab": dict(regions=IN + US + UK + CA + AU + DE, strict=True,
                             title_dq=BASE_TITLE_DQ.replace("recruiter|talent acquisition|", ""),
                             company_dq=EDU_GOV + r"|hospital|clinic|restaurant|foods|masala|outfitters|law firm|\bllp\b"),
    "Shubhangi freelance": dict(regions=US + UK + CA + AU + DE + IN, strict=False, title_dq=BASE_TITLE_DQ, company_dq=EDU_GOV),
    "Leadnius Community": dict(regions=US + CA + UK + AU + IN, strict=False, title_dq=BASE_TITLE_DQ, company_dq=EDU_GOV),
}
TIER_POINTS = {"intent": 40, "hot": 32, "warm": 22, "cool": 12}


def location_of(text: str) -> str:
    m = re.search(r"\(([^()]*,[^()]*)\)", text or "")  # "(Sonoma, California, United States)"
    return (m.group(1) if m else "").lower()


def has(words, text):
    return any(re.search(r"\b" + re.escape(w) + r"\b", text) for w in words)


def score_lead(org, lead, persona_words, now):
    r = RULES[org]
    title, company = (lead["title"] or "").lower(), (lead["company"] or "").lower()
    detail = lead["detail"] or ""
    # location only from profile-search results ("Title at Company (City, State, Country)"), where the format is reliable
    loc = location_of(detail) if lead.get("found_by") in ("Apify LinkedIn search", "AI LinkedIn search") else ""
    reasons = []
    if re.search(r"\b(" + r["title_dq"] + r")\b", title):
        reasons.append(f"title red flag ({re.search(r'(' + r['title_dq'] + r')', title).group(0)})")
    if re.search(r"\b(" + r["company_dq"] + r")\b", company):
        reasons.append(f"company red flag ({re.search(r'(' + r['company_dq'] + r')', company).group(0)})")
    in_region = has(r["regions"], loc) if loc else None
    if loc and not in_region and r["strict"] and has(COUNTRIES, loc):
        reasons.append(f"outside the target region ({loc})")
    title_fit = any(w in title for w in persona_words) if title else False
    fit = (30 if title_fit else 10) + (10 if title_fit and SENIOR.search(title) else 0) \
        + (10 if in_region else 5 if in_region is None else 0) \
        + (10 if "linkedin.com/in/" in (lead["linkedin"] or "") else 6)
    tier = lead["tier"] or ""
    new_leader = bool(re.search(r"\bnew\b|changed jobs|joined|appointed", (lead["signal"] or "").lower()))
    signal = TIER_POINTS.get(tier) or (25 if new_leader else 15)
    age = (now - lead["created_at"]).days
    decay = 15 if age > 90 else 5 if age > 30 else 0
    total = max(0, min(100, fit + signal - decay))
    priority = "disqualified" if reasons else "hot" if total >= 80 else "warm" if total >= 65 else "cold"
    why = lead["rationale"] or ("New in role: new leaders change vendors and processes in their first 90 days." if new_leader else
                                "Fits the ICP but no trigger yet: open with a relevant insight, not a pitch.")
    hook = re.split(r"(?<=[.!?])\s", detail.replace("Found by LinkedIn search:", "").strip(), 1)[0][:160]
    angle = f"Why now: {why} Lead with: {hook or lead['signal']}"
    return total, fit, signal, priority, "; ".join(reasons), angle


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    now = datetime.utcnow()
    summary = {}
    values = []
    for org in RULES:
        o = org.replace("'", "''")
        personas = psql(f"select p.titles from agent_persona p join organization g on g.id = p.org_id where g.name = '{o}'")
        words = {w.lower() for row in personas for t in json.loads(row["titles"] or "[]") for w in re.findall(r"[A-Za-z&]+", t)
                 if len(w) > 2 and w.lower() not in ("and", "the", "head", "senior", "manager", "lead")} | \
                {t.lower() for row in personas for t in json.loads(row["titles"] or "[]")}
        leads = psql(f"""select l.id, l.title, l.company, l.linkedin, l.signal, l.score, l.created_at,
                                l.profile->>'signalDetail' detail, l.profile->>'foundBy' found_by, coalesce(l.profile->>'sourceScore', l.score::text) source_score,
                                st.tier, st.rationale
                         from agent_lead l join organization g on g.id = l.org_id
                         left join signal_type st on st.org_id = l.org_id and st.name = l.signal
                         where g.name = '{o}'""")
        counts = {"hot": 0, "warm": 0, "cold": 0, "disqualified": 0}
        for ld in leads:
            ld["created_at"] = datetime.fromisoformat(ld["created_at"].split(".")[0])
            total, fit, sig, pri, reason, angle = score_lead(org, ld, words, now)
            counts[pri] += 1
            patch = {"fitScore": fit, "signalScore": sig, "priority": pri, "disqualified": pri == "disqualified",
                     "disqualifyReason": reason, "angle": angle, "sourceScore": int(ld["source_score"] or 0),
                     "scoredAt": now.strftime("%Y-%m-%d")}
            values.append((ld["id"], total, json.dumps(patch)))
            if args.dry_run and pri == "disqualified":
                print(f"  DQ {org}: {ld['title'][:40]} | {ld['company'][:30]} -> {reason}")
        summary[org] = counts
    if not args.dry_run and values:
        for i in range(0, len(values), 200):
            rows = ",".join(f"('{lid}'::uuid, {total}, $j${patch}$j$::jsonb)" for lid, total, patch in values[i:i + 200])
            psql(f"""update agent_lead l set score = v.score, profile = coalesce(l.profile, '{{}}'::jsonb) || v.patch
                     from (values {rows}) as v(id, score, patch) where l.id = v.id returning l.id""")
    for org, c in summary.items():
        print(f"{org}: hot {c['hot']}, warm {c['warm']}, cold {c['cold']}, disqualified {c['disqualified']}")


if __name__ == "__main__":
    main()
