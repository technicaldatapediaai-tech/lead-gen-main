# Lead filters, contact enrichment and activity (Lead Agent)

Built 2026-11-17. Three additions to **Lead Agent → Leads** (`/dashboard/agents/leads`):

1. **Filters**: location, signal, channel, persona and more, all with live counts.
2. **Contact**: find a lead's email and phone through the workspace's own data providers.
3. **Activity**: what the lead has posted, commented on, reacted to or reposted on LinkedIn, X and Reddit.

Paid lookups run only when someone clicks. Nothing runs on a schedule.

## Filters (`components/agent/LeadFilters.tsx`)

The filter bar sits above the table. Every option shows how many leads match it. The stat tiles and the CSV export
both follow the filtered rows. "All weeks" in the week picker searches every week at once.

| Filter | Values |
|---|---|
| Search | name, company, title, email, headline |
| Country | countries found on the leads, plus "Location unknown" |
| City / region | free text matched against the location (e.g. "Texas", "Bengaluru") |
| Signal | the signal that found the lead |
| Channel | where the lead came from (LinkedIn search, capture, X, Reddit, Slack, manual…) |
| Persona | the persona the lead was matched to |
| Status | new, contacted, replied… |
| Fit score | hot 80+, warm 60–79, cold under 60 |
| Contact details | has email / phone / LinkedIn / WhatsApp opt-in, or missing email / phone |
| Engagement | the capture action (commented, liked, posted…); shown only when captured leads are present |

### Where location comes from (`services/geo.py`)

`lead_location(lead)` returns `(location, country, source)`. It checks these sources in order:

- **profile**: `profile.location`. Saved by the LinkedIn search and lead capture runbooks (from 2026-11-17), and by
  an Apollo match.
- **detail**: the "(City, Region, Country)" part of the signal text written by Apify LinkedIn searches.
- **phone**: the country calling code.
- **domain**: a country TLD on the email or website (.in, .co.uk, .ae…).

The table marks locations from phone or domain as "(inferred)". Older leads from sources that never sent a location
only show a country when the phone or domain gives one away. Re-running a search refills the rest.

## Contact: email and phone (`services/data_providers.py`, `services/lead_enrich.py`)

**Where**:

- The lead modal's **Contact** tab has Find email, Find phone and Find both.
- The table's **Find contacts (N)** button works on the selected leads, 10 per request. It checks again for pending
  phones after 30 s and 60 s.

**Providers**: each workspace brings its own. Connect them in **Account → Connected IDs**, in the "Contact data
providers" card and the Apify card. Keys are stored encrypted in `org.settings.dataProviders`.

**Waterfall**: providers are tried in this order. The lookup stops at the first hit.

| Field | Order | Notes |
|---|---|---|
| Email | Apollo → Hunter → Apify | Apollo and Apify results are checked with Hunter's verifier when Hunter is connected |
| Phone | Apollo → Apify | Apollo sends phones later. The lead shows "looking up…" and the page checks every 10 s for about 3 minutes |

- Found values only fill **empty** fields. Nothing already on the lead is overwritten.
- `profile.enrichment.{email|phone}` stores `value`, `source`, `status` and `at`. The modal turns this into
  badges: verified, accept-all, unverified, invalid, not found ("tried Apollo, Hunter").
- An Apollo match also fills a missing location.
- If no provider can look up a field, the request returns 422 with "Account → Connected IDs" in the message.

**Approximate costs** (the provider's own credits):

| Provider | Cost |
|---|---|
| Apollo | 1 credit per email, 8 more per mobile |
| Hunter | 1 credit per email found; misses are free; 50 free a month |
| Apify `b2bsearch~linkedin-email-finder` | about $8 per 1,000 found |
| Apify `b2bsearch~linkedin-to-phone` | about $12 per 1,000 found, mostly US numbers |

Each Apify run is capped at $0.05.

**API**:

| Method | Path | Body / result |
|---|---|---|
| GET | `/api/leads/enrich/providers` | `{available: {email: [...], phone: [...]}, providers}` |
| POST | `/api/leads/{id}/enrich` | `{fields: ["email","phone"]}` → the lead |
| POST | `/api/leads/{id}/enrich/check` | picks up a pending Apollo phone (falls back to Apify) |
| POST | `/api/leads/enrich` | `{leadIds (≤10), fields}` → `{results}` |
| POST | `/api/leads/enrich/pending` | `{leadIds}`: checks pending phones in bulk |
| GET | `/api/connections/providers` | Apollo / Hunter / Apify status |
| PUT | `/api/connections/providers/{apollo\|hunter}` | `{key}`: checks it (Hunter: `/v2/account`), saves it encrypted |
| DELETE | `/api/connections/providers/{apollo\|hunter}` | owner / admin |

## Activity (`services/lead_activity.py`, table `lead_activity`, migration 0011)

The lead modal's **Activity** tab. **Refresh activity** reads the lead's last three months through the workspace's
Apify account. Each run is capped at $0.10 and takes 1–3 minutes. The tab polls every 6 s while a run is going.

| Platform | Actor | What it reads |
|---|---|---|
| LinkedIn (`/in/` URL on the lead) | `harvestapi~linkedin-profile-posts` | their posts and reposts |
| | `harvestapi~linkedin-profile-comments` | comments, with the post they commented on |
| | `harvestapi~linkedin-profile-reactions` | likes and reactions, with the post |
| X (profile URL is x.com / twitter.com) | `apidojo~twitter-scraper-lite` | tweets and replies (`from:<handle>`) |
| Reddit (profile URL is a reddit user) | `trudax~reddit-scraper-lite` | posts and comments |

- Rows are saved once per lead, URL and kind. Refreshing adds only the new ones.
- The timeline also includes:
  - the capture event that found the lead ("from lead capture")
  - social posts tagged to the lead
- Each item shows the excerpt of the post it engaged with, the post's author and date, likes and comments, and a
  link to it.
- Without Apify, or without a profile URL, the tab says what's missing and the button stays disabled.

**API**:

| Method | Path | Result |
|---|---|---|
| GET | `/api/leads/{id}/activity` | `{items, run, targets, apifyConnected}` |
| POST | `/api/leads/{id}/activity/refresh` | starts the run in the background (422 without Apify or a profile) |

## Tests

`lead-gen-backend/tests/test_lead_enrichment.py` covers:

- the 422 when no provider is connected
- the email waterfall, with the Apollo phone arriving later
- bulk lookups that keep existing values
- the activity normalisers and targets
- an activity refresh with faked actors
- location inference

Every provider is faked.
